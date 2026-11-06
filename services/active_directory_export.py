import csv
import json
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests
from msal import PublicClientApplication

from domain.normalization import active_directory_keys
from services.active_directory_config import (
    apply_config_defaults,
    get_config_path,
    validate_config,
)
from services.atomic_files import atomic_write
from services.csv_files import read_csv
from services.graph_client import GRAPH_BASE_URL, GraphClient

CSV_HEADERS = (
    "Nom",
    "Email",
    "Identifiant",
    "Poste",
    "Lieu de travail",
    "Business Unit",
    "Manager Email",
    "Collaborateurs à charge",
)
DEFAULT_ESTIMATED_PEOPLE = 500
PROGRESS_EXPORT_COLUMNS = {"Nom", "Email", "Identifiant", "Poste"}
RESUME_STATE_FILENAME = ".liste_salarie_active_directory.resume.json"


def estimate_previous_export_count(output_dir):
    """Estime le volume de la collecte d’après le dernier export valide."""
    logger = logging.getLogger(__name__)
    previous_exports = sorted(
        Path(output_dir).glob("*_liste_salarie_active_directory.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for previous_export in previous_exports:
        try:
            _, rows = read_csv(
                previous_export,
                ",",
                PROGRESS_EXPORT_COLUMNS,
            )
        except (OSError, UnicodeError, ValueError) as error:
            logger.warning(
                "Impossible d’utiliser %s pour estimer la progression : %s",
                previous_export,
                error,
            )
            continue
        if rows:
            return len(rows)
    logger.info(
        "Aucun export précédent exploitable pour l’estimation; "
        "utilisation de la valeur par défaut de %s personnes.",
        DEFAULT_ESTIMATED_PEOPLE,
    )
    return DEFAULT_ESTIMATED_PEOPLE


def next_progress_estimate(current_estimate, completed_count):
    """Augmente la cible de progression lorsqu’elle est atteinte."""
    if completed_count < current_estimate:
        return current_estimate
    return completed_count + max(100, current_estimate // 2)


class LevelIconFormatter(logging.Formatter):
    LEVEL_ICONS = {
        logging.DEBUG: "🔎",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔥",
    }

    def format(self, record):
        """Préfixe le message journalisé avec l’icône du niveau."""
        icon = self.LEVEL_ICONS.get(record.levelno, "•")
        return f"{icon} {super().format(record)}"


def _download_user_photo(user_id, identifier, photo_directory, request_graph):
    """Télécharge et met en cache la photo Graph d’un utilisateur."""
    logger = logging.getLogger(__name__)
    account_reference = identifier or user_id
    safe_identifier = "".join(
        "_" if character in '<>:"/\\|?*' else character
        for character in (identifier or "inconnu")
    ).rstrip(" .")
    photo_path = photo_directory / f"{safe_identifier}_{user_id}.jpg"
    if photo_path.is_file() and photo_path.stat().st_size > 0:
        logger.info(
            "Photo réutilisée depuis le cache pour le compte %s.",
            account_reference,
        )
        return photo_path

    response = request_graph(
        f"{GRAPH_BASE_URL}/users/{user_id}/photo/$value"
    )
    if response.status_code == 404:
        logger.info(
            "Aucune photo disponible pour le compte %s.",
            account_reference,
        )
        return None
    response.raise_for_status()
    if not response.content:
        raise ValueError(f"La photo de l’utilisateur {user_id} est vide.")

    photo_directory.mkdir(parents=True, exist_ok=True)
    atomic_write(
        photo_path,
        lambda stream: stream.write(response.content),
        mode="wb",
    )
    logger.info("Photo récupérée pour le compte %s.", account_reference)
    return photo_path


def initialize_output(config_path):
    """Prépare les dossiers, le journal et le préfixe de cette exécution."""
    application_directory = config_path.parent
    output_dir = application_directory / "liste_salarie_active_directory" / "out"
    log_dir = application_directory / "log"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    run_started_at = datetime.now()
    date_prefix = run_started_at.strftime("%Y%m%dt%H%M%S")
    log_filename = (
        f"{date_prefix}_{run_started_at.strftime('%H%M%S_%f')}"
        "_liste_salarie_active_directory.log"
    )
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    formatter = LevelIconFormatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (
        logging.FileHandler(log_dir / log_filename, encoding="utf-8"),
        logging.StreamHandler(),
    ):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.info("Démarrage de la génération de la liste_salarie_active_directory.")
    return logger, output_dir, date_prefix


def _csv_row_from_user_entry(user_entry):
    """Convertit un compte Graph en champs de l’export Active Directory."""
    return {
        "Nom": user_entry["identity"]["name"],
        "Email": user_entry["identity"]["email"],
        "Identifiant": user_entry["identity"]["username"],
        "Poste": user_entry["professional_info"]["job_title"],
        "Lieu de travail": user_entry["professional_info"]["work_location"],
        "Business Unit": user_entry["professional_info"]["business_unit"],
        "Manager Email": user_entry["hierarchy"]["manager_email"],
        "Collaborateurs à charge": ", ".join(
            user_entry["hierarchy"]["direct_reports"]
        ),
    }


def _save_resume_state(resume_state_path, state):
    """Enregistre atomiquement l'etat de reprise de l'export AD."""
    atomic_write(
        resume_state_path,
        lambda stream: json.dump(state, stream),
        encoding="utf-8",
    )


def _load_resume_state(resume_state_path, logger):
    """Charge l'etat de reprise s'il est present et valide."""
    if not resume_state_path.is_file():
        return None
    try:
        with resume_state_path.open(encoding="utf-8") as state_file:
            state = json.load(state_file)
        if not isinstance(state, dict):
            raise ValueError("format d'etat invalide")
        required_keys = {
            "temporary_csv_path",
            "pending",
            "processed_ids",
            "exported_count",
        }
        missing_keys = required_keys - set(state.keys())
        if missing_keys:
            raise ValueError(
                "cles manquantes: " + ", ".join(sorted(missing_keys))
            )
        return state
    except (OSError, ValueError, json.JSONDecodeError) as error:
        logger.warning(
            "Etat de reprise ignore car invalide (%s): %s",
            resume_state_path,
            error,
        )
        return None


MAX_INTERMEDIATE_LEVELS = 2
MAX_CONCURRENT_REQUESTS = 8
EXPORT_KEY_TYPES = ("email", "matricule", "name")


def _new_key_index():
    """Crée l’index vide des clés métier des lignes déjà exportées."""
    return {key_type: set() for key_type in EXPORT_KEY_TYPES}


def _add_exported_keys(keys_by_type, row):
    """Ajoute les clés d’identification d’une ligne déjà exportée."""
    for key_type, key in active_directory_keys(row).items():
        if key:
            keys_by_type[key_type].add(key)


def _has_exported_key(keys_by_type, row):
    """Indique si une ligne est déjà présente selon ses clés métier."""
    return any(
        key and key in keys_by_type[key_type]
        for key_type, key in active_directory_keys(row).items()
    )


def _account_reference(user_entry):
    """Retourne l’identifiant le plus lisible d’un compte pour les journaux."""
    identity = user_entry["identity"]
    return identity["email"] or identity["username"] or user_entry["id"]


class ActiveDirectoryAuthenticationError(RuntimeError):
    """Échec de l’authentification Microsoft."""


def _load_config(config_path, logger):
    """Charge et valide la configuration; retourne la configuration et les scopes."""
    try:
        with config_path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
        if isinstance(config, dict):
            config = apply_config_defaults(config)
        scopes = validate_config(config, config_path)
    except Exception:
        logger.exception(
            "Impossible de charger ou valider la configuration Active Directory."
        )
        raise
    return config, scopes


def _acquire_access_token(config, scopes, logger, on_device_code):
    """Authentifie l’utilisateur par flux d’appareil et retourne le jeton."""
    logger.info("Initialisation de l’authentification Microsoft.")
    try:
        app = PublicClientApplication(
            config["client_id"], authority=config["authority"]
        )
        flow = app.initiate_device_flow(scopes=scopes)
        if "user_code" not in flow:
            raise ActiveDirectoryAuthenticationError(
                "Impossible d'initier la connexion."
            )

        if on_device_code is None:
            print("--- CONNEXION REQUISE ---")
            print(flow["message"])
        else:
            on_device_code(
                flow.get("verification_uri", "https://login.microsoft.com/device"),
                flow["user_code"],
            )
        result = app.acquire_token_by_device_flow(flow)

        if "access_token" not in result:
            logger.error("L’authentification Microsoft a échoué.")
            raise ActiveDirectoryAuthenticationError(
                f"Erreur d'authentification : {result.get('error_description')}"
            )
    except Exception:
        logger.exception("Échec de l’authentification Microsoft.")
        raise
    logger.info("Authentification Microsoft réussie.")
    return result["access_token"]


class _ExportState:
    """État mutable de la collecte, sérialisable pour une reprise."""

    def __init__(self, start_user_email):
        self.pending = [(start_user_email, True, 0)]
        self.processed_ids = set()
        self.exported_count = 0
        self.keys_by_type = _new_key_index()
        self.temporary_path = None

    def to_resume_dict(self):
        """Représente l’état dans le format JSON de reprise."""
        return {
            "temporary_csv_path": str(self.temporary_path),
            "pending": [
                {
                    "user_id_or_email": user_id_or_email,
                    "is_root": is_root,
                    "intermediate_levels": intermediate_levels,
                }
                for user_id_or_email, is_root, intermediate_levels in self.pending
            ],
            "processed_ids": sorted(self.processed_ids),
            "exported_count": self.exported_count,
        }


class ActiveDirectoryCollector:
    """Parcourt la hiérarchie Graph et écrit les comptes retenus."""

    def __init__(
        self,
        config,
        graph,
        logger,
        output_dir,
        download_photos=False,
        on_progress=None,
        estimated_people=DEFAULT_ESTIMATED_PEOPLE,
    ):
        self.start_user_email = config["start_user_email"]
        self.report_domain = config["report_domain"].lstrip("@").casefold()
        self.graph = graph
        self.logger = logger
        self.output_dir = output_dir
        self.download_photos = download_photos
        self.on_progress = on_progress
        self.estimated_people = estimated_people

    def is_report_domain_email(self, email):
        """Indique si l’adresse appartient au domaine de rapport."""
        return email is not None and email.casefold().endswith(
            f"@{self.report_domain}"
        )

    def is_external_email(self, email):
        """Reconnaît l’adresse externe exclue du domaine de rapport."""
        return email is not None and email.casefold().endswith(
            f".ext@{self.report_domain}"
        )

    def report_progress(self, completed_count):
        """Réévalue la cible de progression et notifie l’interface."""
        if self.on_progress is None:
            return
        self.estimated_people = next_progress_estimate(
            self.estimated_people, completed_count
        )
        self.on_progress(completed_count, self.estimated_people, "collecting")

    def _fetch_manager_email(self, user_id):
        """Retourne l’e-mail du responsable, ou None s’il n’existe pas."""
        response = self.graph.get(
            f"{GRAPH_BASE_URL}/users/{user_id}/manager?$select=mail"
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get("mail")

    def _fetch_direct_reports(self, user_id):
        """Retourne tous les rapports directs d’un compte (pagination incluse)."""
        url = (
            f"{GRAPH_BASE_URL}/users/{user_id}/directReports"
            "?$select=id,mail,displayName"
        )
        reports = []
        while url:
            response = self.graph.get(url)
            response.raise_for_status()
            page = response.json()
            reports.extend(page.get("value", []))
            url = page.get("@odata.nextLink")
        return reports

    def fetch_user_record(self, user_id_or_email):
        """Récupère un compte, son responsable et ses rapports directs."""
        user_response = self.graph.get(
            f"{GRAPH_BASE_URL}/users/{user_id_or_email}"
            "?$select=id,displayName,mail,userPrincipalName,"
            "jobTitle,department,officeLocation"
        )
        if user_response.status_code == 404:
            return None
        user_response.raise_for_status()
        user_info = user_response.json()
        user_id = user_info["id"]
        email = user_info.get("mail")
        is_epsilon_user = self.is_report_domain_email(email)

        manager_email = None
        if is_epsilon_user or user_id_or_email == self.start_user_email:
            manager_email = self._fetch_manager_email(user_id)
        direct_reports_data = self._fetch_direct_reports(user_id)

        user_principal_name = user_info.get("userPrincipalName")
        user_entry = {
            "id": user_id,
            "identity": {
                "name": user_info.get("displayName"),
                "email": email,
                "username": (
                    user_principal_name.split("@", 1)[0]
                    if user_principal_name
                    else None
                ),
            },
            "professional_info": {
                "job_title": user_info.get("jobTitle"),
                "business_unit": user_info.get("department"),
                "work_location": user_info.get("officeLocation"),
            },
            "hierarchy": {
                "manager_email": (
                    None
                    if self.is_external_email(manager_email)
                    else manager_email
                ),
                "direct_reports": [
                    report["mail"]
                    for report in direct_reports_data
                    if report.get("mail")
                    and not self.is_external_email(report["mail"])
                ],
            },
        }
        return user_entry, direct_reports_data, is_epsilon_user

    def _export_user(self, writer, user_entry, keys_by_type):
        """Récupère la photo si demandée, puis écrit la ligne du compte."""
        if self.download_photos:
            try:
                _download_user_photo(
                    user_entry["id"],
                    user_entry["identity"]["username"],
                    self.output_dir / "photos",
                    self.graph.get,
                )
            except requests.HTTPError:
                self.logger.exception(
                    "Impossible de récupérer la photo du compte %s.",
                    _account_reference(user_entry),
                )
        row = _csv_row_from_user_entry(user_entry)
        writer.writerow([row[column] for column in CSV_HEADERS])
        _add_exported_keys(keys_by_type, row)

    def _next_intermediate_levels(self, mail, intermediate_levels):
        """Retourne le niveau intermédiaire suivant, ou None si la branche s’arrête."""
        if self.is_report_domain_email(mail):
            return 0
        if intermediate_levels < MAX_INTERMEDIATE_LEVELS:
            return intermediate_levels + 1
        return None

    def _process_account(
        self, writer, state, result, is_root, intermediate_levels, next_pending
    ):
        """Traite un compte collecté : écriture éventuelle et rapports à suivre."""
        user_entry, direct_reports_data, is_epsilon_user = result
        user_id = user_entry["id"]
        if user_id in state.processed_ids:
            return
        state.processed_ids.add(user_id)

        self.logger.info(
            "Compte Active Directory examiné : %s.",
            _account_reference(user_entry),
        )
        if (
            is_root or is_epsilon_user
        ) and not self.is_external_email(user_entry["identity"]["email"]):
            self._export_user(writer, user_entry, state.keys_by_type)
            state.exported_count += 1
            self.report_progress(state.exported_count)

        for report in direct_reports_data:
            mail = report.get("mail")
            if not mail:
                continue
            next_levels = self._next_intermediate_levels(
                mail, intermediate_levels
            )
            if next_levels is None:
                continue
            report_id = report["id"]
            previous = next_pending.get(report_id)
            if report_id not in state.processed_ids and (
                previous is None or next_levels < previous
            ):
                next_pending[report_id] = next_levels

    def collect_hierarchy(self, writer, state, resume_state_path):
        """Parcourt la hiérarchie par niveaux et sauvegarde l’état de reprise."""
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
            while state.pending:
                batch = state.pending
                results = executor.map(
                    self.fetch_user_record,
                    (item[0] for item in batch),
                )
                next_pending = {}

                for (user_id_or_email, is_root, intermediate_levels), result in zip(
                    batch, results
                ):
                    if result is None:
                        self.logger.warning(
                            "Compte %s introuvable dans Microsoft Graph.",
                            user_id_or_email,
                        )
                        continue
                    self._process_account(
                        writer,
                        state,
                        result,
                        is_root,
                        intermediate_levels,
                        next_pending,
                    )

                state.pending = [
                    (report_id, False, levels)
                    for report_id, levels in next_pending.items()
                ]
                _save_resume_state(resume_state_path, state.to_resume_dict())

        self.logger.info(
            "Collecte terminée : %s comptes examinés, %s personnes retenues.",
            len(state.processed_ids),
            state.exported_count,
        )

    def _missing_previous_rows(self, previous_export_path, keys_by_type):
        """Retourne les lignes de l’export précédent absentes de l’export courant."""
        if not previous_export_path.is_file():
            raise FileNotFoundError(
                "Le fichier d’export précédent est introuvable : "
                f"{previous_export_path}"
            )
        self.logger.info(
            "Comparaison avec l’export précédent : %s.",
            previous_export_path,
        )
        _, previous_rows = read_csv(
            previous_export_path,
            ",",
            {"Nom", "Email", "Identifiant", "Poste"},
        )
        missing_rows = [
            row
            for row in previous_rows
            if not _has_exported_key(keys_by_type, row)
        ]
        self.logger.info(
            "Comparaison export précédent : %s ligne(s), %s absente(s) du "
            "fichier courant.",
            len(previous_rows),
            len(missing_rows),
        )
        return missing_rows

    def append_previous_users(self, writer, state, previous_export_path):
        """Ajoute les comptes encore visibles absents de l’export précédent."""
        if previous_export_path is None:
            self.logger.info("Aucun fichier d’export précédent fourni.")
            return 0

        appended_count = 0
        visible_count = 0
        checked_users = set()
        for previous_row in self._missing_previous_rows(
            previous_export_path, state.keys_by_type
        ):
            candidate = (previous_row.get("Email") or "").strip()
            if not candidate:
                candidate = (previous_row.get("Identifiant") or "").strip()
            if not candidate:
                continue
            candidate_key = candidate.casefold()
            if candidate_key in checked_users:
                continue
            checked_users.add(candidate_key)

            result = self.fetch_user_record(candidate)
            if result is None:
                continue
            user_entry, _direct_reports_data, is_epsilon_user = result
            email = user_entry["identity"]["email"]
            is_start_user = (email or "").casefold() == (
                self.start_user_email.casefold()
            )
            if not (
                is_epsilon_user or is_start_user
            ) or self.is_external_email(email):
                continue

            visible_count += 1
            row = _csv_row_from_user_entry(user_entry)
            if _has_exported_key(state.keys_by_type, row):
                continue
            self._export_user(writer, user_entry, state.keys_by_type)
            appended_count += 1
            self.report_progress(state.exported_count + appended_count)

        self.logger.info(
            "Comparaison export précédent : %s compte(s) encore visible(s), "
            "%s ajouté(s).",
            visible_count,
            appended_count,
        )
        return appended_count


def _restore_resume_state(resume_state_path, state, logger):
    """Recharge un export interrompu dans `state`; retourne True si la reprise a eu lieu."""
    resume_state = _load_resume_state(resume_state_path, logger)
    if resume_state is None:
        return False
    candidate_path = Path(resume_state["temporary_csv_path"])
    try:
        _, resumed_rows = read_csv(
            candidate_path,
            ",",
            PROGRESS_EXPORT_COLUMNS,
        )
        pending = [
            (
                item["user_id_or_email"],
                item["is_root"],
                item["intermediate_levels"],
            )
            for item in resume_state["pending"]
        ]
        processed_ids = set(resume_state["processed_ids"])
    except (KeyError, TypeError, ValueError, OSError, UnicodeError) as error:
        logger.warning(
            "Reprise impossible avec l'etat enregistre (%s) : %s. "
            "Un nouvel export complet sera lance.",
            candidate_path,
            error,
        )
        resume_state_path.unlink(missing_ok=True)
        return False

    state.pending = pending
    state.processed_ids = processed_ids
    for resumed_row in resumed_rows:
        _add_exported_keys(state.keys_by_type, resumed_row)
    state.exported_count = len(resumed_rows)
    state.temporary_path = candidate_path
    logger.info(
        "Reprise d'un export interrompu : %s ligne(s) deja ecrite(s), "
        "%s compte(s) en attente.",
        state.exported_count,
        len(pending),
    )
    return True


def _create_temporary_export(output_dir, csv_filename):
    """Crée le CSV temporaire de l’export avec son en-tête."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        newline="",
        encoding="utf-8",
        dir=output_dir,
        prefix=f".{csv_filename}.",
        suffix=".tmp",
        delete=False,
    ) as temporary_file:
        csv.writer(temporary_file).writerow(list(CSV_HEADERS))
        return Path(temporary_file.name)


def run_active_directory_export(
    on_device_code=None,
    download_photos=False,
    previous_export_path=None,
    on_progress=None,
):
    """Collecte la hiérarchie Graph et publie le CSV après réussite complète."""
    if previous_export_path is not None:
        previous_export_path = Path(previous_export_path)
    config_path = get_config_path()
    logger, output_dir, date_prefix = initialize_output(config_path)
    estimated_people = estimate_previous_export_count(output_dir)
    if on_progress is not None:
        on_progress(0, estimated_people, "connecting")

    config, scopes = _load_config(config_path, logger)
    access_token = _acquire_access_token(config, scopes, logger, on_device_code)
    collector = ActiveDirectoryCollector(
        config,
        GraphClient(access_token, logger),
        logger,
        output_dir,
        download_photos=download_photos,
        on_progress=on_progress,
        estimated_people=estimated_people,
    )

    logger.info(
        "Récupération des photos %s.",
        "activée" if download_photos else "désactivée",
    )
    logger.info("Démarrage de la collecte de la hiérarchie Active Directory.")
    resume_state_path = output_dir / RESUME_STATE_FILENAME
    csv_filename = f"{date_prefix}_liste_salarie_active_directory.csv"
    csv_path = output_dir / csv_filename
    state = _ExportState(collector.start_user_email)
    _restore_resume_state(resume_state_path, state, logger)

    if on_progress is not None:
        collector.estimated_people = max(
            collector.estimated_people, state.exported_count
        )
        on_progress(
            state.exported_count, collector.estimated_people, "collecting"
        )

    appended_from_previous = 0
    try:
        if state.temporary_path is None:
            state.temporary_path = _create_temporary_export(
                output_dir, csv_filename
            )
            _save_resume_state(resume_state_path, state.to_resume_dict())

        with state.temporary_path.open(
            "a", newline="", encoding="utf-8"
        ) as output_stream:
            writer = csv.writer(output_stream)
            collector.collect_hierarchy(writer, state, resume_state_path)
            appended_from_previous = collector.append_previous_users(
                writer, state, previous_export_path
            )

        if state.exported_count + appended_from_previous:
            state.temporary_path.replace(csv_path)
        else:
            state.temporary_path.unlink(missing_ok=True)
            state.temporary_path = None
        resume_state_path.unlink(missing_ok=True)
    except Exception:
        logger.exception(
            "Échec de la collecte ou de l’écriture de l’export Active Directory."
        )
        if state.temporary_path is not None:
            logger.info(
                "Un état de reprise est conserve dans %s pour reprendre "
                "automatiquement au prochain lancement.",
                resume_state_path,
            )
        raise

    total_exported = state.exported_count + appended_from_previous
    if total_exported:
        logger.info(
            "Terminé : %s personnes exportées (+%s depuis l’export précédent) "
            "dans %s.",
            state.exported_count,
            appended_from_previous,
            csv_path,
        )
    else:
        logger.info(
            "Terminé : aucun compte à exporter ; aucun fichier CSV créé."
        )
    if on_progress is not None:
        on_progress(
            total_exported,
            max(collector.estimated_people, total_exported),
            "complete",
        )

    return csv_path if total_exported else None


def main():
    """Lance la génération de l’export depuis la ligne de commande."""
    run_active_directory_export()


if __name__ == "__main__":
    main()
