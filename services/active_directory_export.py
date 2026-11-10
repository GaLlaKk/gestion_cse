import csv
import json
import logging
import tempfile
import time
from contextlib import contextmanager
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path

from msal import PublicClientApplication

from services.active_directory_config import (
    apply_config_defaults,
    get_config_path,
    validate_config,
)
from services.ad_photos import download_user_photo as _download_user_photo
from services.ad_progress import (
    DEFAULT_ESTIMATED_PEOPLE,
    estimate_previous_export_count,
    next_progress_estimate,
)
from services.ad_state import (
    ExportState as _ExportState,
    add_exported_keys as _add_exported_keys,
    has_exported_key as _has_exported_key,
    restore_resume_state as _restore_resume_state,
    save_resume_state as _save_resume_state,
)
from services.csv_files import read_csv
from services.graph_client import GraphClient

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
RESUME_STATE_FILENAME = ".liste_salarie_active_directory.resume.json"


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


MAX_INTERMEDIATE_LEVELS = 2
MAX_CONCURRENT_REQUESTS = 6
MAX_PHOTO_WORKERS = 4
BATCH_ACCOUNTS = 10
RESUME_SAVE_INTERVAL_SECONDS = 5.0


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
        self._photo_executor = None

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

    def _fetch_remaining_direct_reports(self, page):
        """Complète une première page de rapports directs (pagination)."""
        reports = list(page.get("value", []))
        url = page.get("@odata.nextLink")
        while url:
            response = self.graph.get(url)
            response.raise_for_status()
            page = response.json()
            reports.extend(page.get("value", []))
            url = page.get("@odata.nextLink")
        return reports

    def fetch_user_records(self, identifiers, with_direct_reports=True):
        """Récupère des comptes, leur responsable et leurs rapports directs.

        Les requêtes (compte avec responsable en `$expand`, rapports directs)
        sont regroupées dans des appels `$batch`. Retourne une liste alignée sur
        `identifiers`, avec None pour un compte introuvable.
        """
        urls = []
        for identifier in identifiers:
            urls.append(
                f"/users/{identifier}"
                "?$select=id,displayName,mail,userPrincipalName,"
                "jobTitle,department,officeLocation"
                "&$expand=manager($select=mail)"
            )
            if with_direct_reports:
                urls.append(
                    f"/users/{identifier}/directReports"
                    "?$select=id,mail,displayName"
                )
        responses = self.graph.batch_get(urls)
        stride = 2 if with_direct_reports else 1

        records = []
        for position, identifier in enumerate(identifiers):
            user_response = responses[stride * position]
            if user_response.status_code == 404:
                records.append(None)
                continue
            user_response.raise_for_status()
            direct_reports = []
            if with_direct_reports:
                reports_response = responses[stride * position + 1]
                reports_response.raise_for_status()
                direct_reports = self._fetch_remaining_direct_reports(
                    reports_response.json()
                )
            records.append(
                self._build_user_record(
                    identifier, user_response.json(), direct_reports
                )
            )
        return records

    def _build_user_record(self, identifier, user_info, direct_reports_data):
        """Assemble l’entrée d’un compte à partir des réponses Graph."""
        user_id = user_info["id"]
        email = user_info.get("mail")
        is_epsilon_user = self.is_report_domain_email(email)

        manager_email = None
        if is_epsilon_user or identifier == self.start_user_email:
            manager_email = (user_info.get("manager") or {}).get("mail")

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

    @contextmanager
    def photo_downloads(self):
        """Active le téléchargement parallèle des photos et attend sa fin."""
        with ThreadPoolExecutor(max_workers=MAX_PHOTO_WORKERS) as executor:
            self._photo_executor = executor
            try:
                yield
            finally:
                self._photo_executor = None

    def _download_photo(self, user_entry):
        """Télécharge la photo d’un compte ; une erreur n’interrompt pas l’export."""
        try:
            _download_user_photo(
                user_entry["id"],
                user_entry["identity"]["username"],
                self.output_dir / "photos",
                self.graph.get,
            )
        except Exception:
            self.logger.exception(
                "Impossible de récupérer la photo du compte %s.",
                _account_reference(user_entry),
            )

    def _export_user(self, writer, user_entry, keys_by_type):
        """Planifie la photo si demandée, puis écrit la ligne du compte."""
        if self.download_photos and self._photo_executor is not None:
            self._photo_executor.submit(self._download_photo, user_entry)
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

    def collect_hierarchy(self, writer, state, resume_state_path, flush=None):
        """Parcourt la hiérarchie en flux continu et sauvegarde l’état de reprise.

        Les comptes en attente sont regroupés en lots traités en parallèle ; dès
        qu’un lot se termine, ses rapports directs alimentent la file sans
        attendre la fin d’un niveau. Les photos sont téléchargées en parallèle.
        """
        waiting = {
            identifier: (is_root, levels)
            for identifier, is_root, levels in state.pending
        }
        inflight = {}
        inflight_ids = set()

        def snapshot_pending():
            in_progress = [item for chunk in inflight.values() for item in chunk]
            return in_progress + [
                (identifier, is_root, levels)
                for identifier, (is_root, levels) in waiting.items()
            ]

        def save_state():
            if flush is not None:
                flush()
            state.pending = snapshot_pending()
            _save_resume_state(resume_state_path, state.to_resume_dict())

        last_save = time.monotonic()
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
            try:
                while waiting or inflight:
                    free_slots = MAX_CONCURRENT_REQUESTS - len(inflight)
                    while waiting and free_slots > 0:
                        size = max(
                            1,
                            min(BATCH_ACCOUNTS, -(-len(waiting) // free_slots)),
                        )
                        chunk = [
                            (identifier, *waiting.pop(identifier))
                            for identifier in list(waiting)[:size]
                        ]
                        future = executor.submit(
                            self.fetch_user_records,
                            [item[0] for item in chunk],
                        )
                        inflight[future] = chunk
                        inflight_ids.update(item[0] for item in chunk)
                        free_slots -= 1

                    done, _ = wait(inflight, return_when=FIRST_COMPLETED)
                    for future in done:
                        results = future.result()
                        chunk = inflight.pop(future)
                        inflight_ids.difference_update(item[0] for item in chunk)
                        self._process_chunk(
                            writer, state, chunk, results, waiting, inflight_ids
                        )

                    if (
                        time.monotonic() - last_save
                        >= RESUME_SAVE_INTERVAL_SECONDS
                    ):
                        save_state()
                        last_save = time.monotonic()
            except BaseException:
                for future in inflight:
                    future.cancel()
                save_state()
                raise
        save_state()

        self.logger.info(
            "Collecte terminée : %s comptes examinés, %s personnes retenues.",
            len(state.processed_ids),
            state.exported_count,
        )

    def _process_chunk(
        self, writer, state, chunk, results, waiting, inflight_ids
    ):
        """Traite les comptes d’un lot et met leurs rapports directs en attente."""
        discovered = {}
        for (user_id_or_email, is_root, intermediate_levels), result in zip(
            chunk, results
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
                discovered,
            )
        for report_id, levels in discovered.items():
            if report_id in inflight_ids:
                continue
            previous = waiting.get(report_id)
            if previous is None or levels < previous[1]:
                waiting[report_id] = (False, levels)

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
        candidates = []
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
            candidates.append(candidate)

        chunks = [
            candidates[start : start + BATCH_ACCOUNTS]
            for start in range(0, len(candidates), BATCH_ACCOUNTS)
        ]
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
            fetched = executor.map(
                lambda chunk: self.fetch_user_records(
                    chunk, with_direct_reports=False
                ),
                chunks,
            )
            for result in (item for batch in fetched for item in batch):
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
            with collector.photo_downloads():
                collector.collect_hierarchy(
                    writer,
                    state,
                    resume_state_path,
                    flush=output_stream.flush,
                )
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
