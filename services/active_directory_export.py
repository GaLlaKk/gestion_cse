import csv
import json
import logging
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from msal import PublicClientApplication

from domain.normalization import active_directory_keys
from services.csv_files import read_csv
from services.paths import project_root

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


class LevelIconFormatter(logging.Formatter):
    LEVEL_ICONS = {
        logging.DEBUG: "🔎",
        logging.INFO: "ℹ️",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🔥",
    }

    def format(self, record):
        icon = self.LEVEL_ICONS.get(record.levelno, "•")
        return f"{icon} {super().format(record)}"


def _download_user_photo(user_id, identifier, photo_directory, request_graph):
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
        f"https://graph.microsoft.com/v1.0/users/{user_id}/photo/$value"
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
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=photo_directory,
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(response.content)
        temporary_path.replace(photo_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    logger.info("Photo récupérée pour le compte %s.", account_reference)
    return photo_path


def get_config_path():
    return project_root() / "liste_salarie_active_directory.config.json"


def validate_config(config, config_path):
    if not isinstance(config, dict):
        raise ValueError(
            f"La configuration doit être un objet JSON dans {config_path}."
        )

    required_string_settings = (
        "start_user_email",
        "client_id",
        "authority",
        "report_domain",
    )
    for setting_name in required_string_settings:
        if (
            not isinstance(config.get(setting_name), str)
            or not config[setting_name].strip()
        ):
            raise ValueError(
                f"Le paramètre '{setting_name}' doit être une chaîne non vide "
                f"dans {config_path}."
            )

    scopes = config.get("scopes")
    if not isinstance(scopes, list) or not scopes or not all(
        isinstance(scope, str) and scope.strip() for scope in scopes
    ):
        raise ValueError(
            f"Le paramètre 'scopes' doit être une liste de chaînes non vides "
            f"dans {config_path}."
        )
    return scopes


def save_active_directory_config(contents, config_path=None):
    config_path = Path(config_path or get_config_path())
    config = json.loads(contents)
    validate_config(config, config_path)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(contents)
        temporary_path.replace(config_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return config_path


def initialize_output(config_path):
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


def run_active_directory_export(
    on_device_code=None,
    download_photos=False,
    previous_export_path=None,
):
    if previous_export_path is not None:
        previous_export_path = Path(previous_export_path)
    config_path = get_config_path()
    logger, output_dir, date_prefix = initialize_output(config_path)
    try:
        with config_path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
        scopes = validate_config(config, config_path)
    except Exception:
        logger.exception(
            "Impossible de charger ou valider la configuration Active Directory."
        )
        raise

    START_USER_EMAIL = config["start_user_email"]
    CLIENT_ID = config["client_id"]
    AUTHORITY = config["authority"]
    SCOPES = scopes
    REPORT_DOMAIN = config["report_domain"].lstrip("@").casefold()
    MAX_INTERMEDIATE_LEVELS = 2
    MAX_CONCURRENT_REQUESTS = 8
    MAX_RATE_LIMIT_RETRIES = 5
    REQUEST_TIMEOUT_SECONDS = 30

    def is_external_epsilon_email(email):
        return (
            email is not None
            and email.casefold().endswith(f".ext@{REPORT_DOMAIN}")
        )

    logger.info("Initialisation de l’authentification Microsoft.")
    try:
        app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise Exception("Impossible d'initier la connexion.")

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
            raise Exception(
                f"Erreur d'authentification : {result.get('error_description')}"
            )
    except Exception:
        logger.exception("Échec de l’authentification Microsoft.")
        raise
    logger.info("Authentification Microsoft réussie.")

    headers = {"Authorization": f"Bearer {result['access_token']}"}

    def request_graph(url):
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            response = requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            if response.status_code != 429:
                return response

            if attempt == MAX_RATE_LIMIT_RETRIES:
                response.raise_for_status()

            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(retry_after)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    delay = max(
                        0,
                        (retry_at - datetime.now(timezone.utc)).total_seconds(),
                    )
                except (TypeError, ValueError, OverflowError):
                    delay = 2**attempt

            logger.warning(
                "Microsoft Graph limite les requêtes (429) ; nouvelle tentative "
                "dans %.1f s.",
                delay,
            )
            time.sleep(delay)

    def fetch_user_record(user_id_or_email):
        user_url = (
            "https://graph.microsoft.com/v1.0/users/"
            f"{user_id_or_email}?$select=id,displayName,mail,userPrincipalName,"
            "jobTitle,department,officeLocation"
        )
        user_response = request_graph(user_url)
        if user_response.status_code == 404:
            return None
        user_response.raise_for_status()
        user_info = user_response.json()
        user_id = user_info["id"]
        email = user_info.get("mail")
        is_epsilon_user = (
            email is not None
            and email.casefold().endswith(f"@{REPORT_DOMAIN}")
        )

        manager_email = None
        if is_epsilon_user or user_id_or_email == START_USER_EMAIL:
            manager_url = (
                f"https://graph.microsoft.com/v1.0/users/{user_id}/manager"
                "?$select=mail"
            )
            manager_response = request_graph(manager_url)
            if manager_response.status_code != 404:
                manager_response.raise_for_status()
                manager_email = manager_response.json().get("mail")

        reports_url = (
            f"https://graph.microsoft.com/v1.0/users/{user_id}/directReports"
            "?$select=id,mail,displayName"
        )
        direct_reports_data = []
        while reports_url:
            reports_response = request_graph(reports_url)
            reports_response.raise_for_status()
            reports_page = reports_response.json()
            direct_reports_data.extend(reports_page.get("value", []))
            reports_url = reports_page.get("@odata.nextLink")

        user_entry = {
            "id": user_id,
            "identity": {
                "name": user_info.get("displayName"),
                "email": email,
                "username": (
                    user_info["userPrincipalName"].split("@", 1)[0]
                    if user_info.get("userPrincipalName")
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
                    if is_external_epsilon_email(manager_email)
                    else manager_email
                ),
                "direct_reports": [
                    report["mail"]
                    for report in direct_reports_data
                    if report.get("mail")
                    and not is_external_epsilon_email(report["mail"])
                ],
            },
        }
        return user_entry, direct_reports_data, is_epsilon_user

    def add_exported_keys(keys_by_type, row):
        for key_type, key in active_directory_keys(row).items():
            if key:
                keys_by_type[key_type].add(key)

    def has_exported_key(keys_by_type, row):
        return any(
            key and key in keys_by_type[key_type]
            for key_type, key in active_directory_keys(row).items()
        )

    def fetch_hierarchy(writer):
        exported_count = 0
        processed_ids = set()
        pending = [(START_USER_EMAIL, True, 0)]
        exported_keys_by_type = {"email": set(), "matricule": set(), "name": set()}

        with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
            while pending:
                batch = pending
                pending = []
                results = executor.map(
                    fetch_user_record,
                    (item[0] for item in batch),
                )
                next_pending = {}

                for (user_id_or_email, is_root, intermediate_levels), result in zip(
                    batch, results
                ):
                    if result is None:
                        logger.warning(
                            "Compte %s introuvable dans Microsoft Graph.",
                            user_id_or_email,
                        )
                        continue

                    user_entry, direct_reports_data, is_epsilon_user = result
                    user_id = user_entry["id"]
                    if user_id in processed_ids:
                        continue
                    processed_ids.add(user_id)

                    account_reference = (
                        user_entry["identity"]["email"]
                        or user_entry["identity"]["username"]
                        or user_id
                    )
                    logger.info(
                        "Compte Active Directory examiné : %s.",
                        account_reference,
                    )
                    if (is_root or is_epsilon_user) and not is_external_epsilon_email(
                        user_entry["identity"]["email"]
                    ):
                        if download_photos:
                            try:
                                _download_user_photo(
                                    user_id,
                                    user_entry["identity"]["username"],
                                    output_dir / "photos",
                                    request_graph,
                                )
                            except requests.HTTPError:
                                logger.exception(
                                    "Impossible de récupérer la photo du compte %s.",
                                    account_reference,
                                )
                        row = _csv_row_from_user_entry(user_entry)
                        writer.writerow([row[column] for column in CSV_HEADERS])
                        add_exported_keys(exported_keys_by_type, row)
                        exported_count += 1

                    for report in direct_reports_data:
                        mail = report.get("mail")
                        if not mail:
                            continue
                        if mail.casefold().endswith(f"@{REPORT_DOMAIN}"):
                            next_levels = 0
                        elif intermediate_levels < MAX_INTERMEDIATE_LEVELS:
                            next_levels = intermediate_levels + 1
                        else:
                            continue

                        report_id = report["id"]
                        previous = next_pending.get(report_id)
                        if report_id not in processed_ids and (
                            previous is None or next_levels < previous
                        ):
                            next_pending[report_id] = next_levels

                pending = [
                    (report_id, False, levels)
                    for report_id, levels in next_pending.items()
                ]

        logger.info(
            "Collecte terminée : %s comptes examinés, %s personnes retenues.",
            len(processed_ids),
            exported_count,
        )
        return exported_count, exported_keys_by_type

    def append_visible_previous_users(writer, exported_keys_by_type):
        if previous_export_path is None:
            logger.info("Aucun fichier d’export précédent fourni.")
            return 0
        if not previous_export_path.is_file():
            raise FileNotFoundError(
                "Le fichier d’export précédent est introuvable : "
                f"{previous_export_path}"
            )

        logger.info(
            "Comparaison avec l’export précédent : %s.",
            previous_export_path,
        )
        _, previous_rows = read_csv(
            previous_export_path,
            ",",
            {"Nom", "Email", "Identifiant", "Poste"},
        )
        missing_rows = [
            row for row in previous_rows if not has_exported_key(exported_keys_by_type, row)
        ]
        logger.info(
            "Comparaison export précédent : %s ligne(s), %s absente(s) du fichier courant.",
            len(previous_rows),
            len(missing_rows),
        )

        appended_count = 0
        visible_count = 0
        checked_users = set()
        for previous_row in missing_rows:
            candidate = (previous_row.get("Email") or "").strip()
            if not candidate:
                candidate = (previous_row.get("Identifiant") or "").strip()
            if not candidate:
                continue
            candidate_key = candidate.casefold()
            if candidate_key in checked_users:
                continue
            checked_users.add(candidate_key)

            result = fetch_user_record(candidate)
            if result is None:
                continue
            user_entry, _direct_reports_data, is_epsilon_user = result
            is_start_user = (
                (user_entry["identity"]["email"] or "").casefold()
                == START_USER_EMAIL.casefold()
            )
            if (
                not (is_epsilon_user or is_start_user)
                or is_external_epsilon_email(user_entry["identity"]["email"])
            ):
                continue

            visible_count += 1
            row = _csv_row_from_user_entry(user_entry)
            if has_exported_key(exported_keys_by_type, row):
                continue
            if download_photos:
                account_reference = (
                    user_entry["identity"]["email"]
                    or user_entry["identity"]["username"]
                    or user_entry["id"]
                )
                try:
                    _download_user_photo(
                        user_entry["id"],
                        user_entry["identity"]["username"],
                        output_dir / "photos",
                        request_graph,
                    )
                except requests.HTTPError:
                    logger.exception(
                        "Impossible de récupérer la photo du compte %s.",
                        account_reference,
                    )
            writer.writerow([row[column] for column in CSV_HEADERS])
            add_exported_keys(exported_keys_by_type, row)
            appended_count += 1

        logger.info(
            "Comparaison export précédent : %s compte(s) encore visible(s), %s ajouté(s).",
            visible_count,
            appended_count,
        )
        return appended_count

    logger.info(
        "Récupération des photos %s.",
        "activée" if download_photos else "désactivée",
    )
    logger.info("Démarrage de la collecte de la hiérarchie Active Directory.")
    csv_filename = f"{date_prefix}_liste_salarie_active_directory.csv"
    csv_path = output_dir / csv_filename
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=output_dir,
            prefix=f".{csv_filename}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            writer = csv.writer(temporary_file)
            writer.writerow(list(CSV_HEADERS))
            exported_count, exported_keys_by_type = fetch_hierarchy(writer)
            appended_from_previous = append_visible_previous_users(
                writer,
                exported_keys_by_type,
            )
        temporary_path.replace(csv_path)
    except Exception:
        logger.exception(
            "Échec de la collecte ou de l’écriture de l’export Active Directory."
        )
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    logger.info(
        "Terminé : %s personnes exportées (+%s depuis l’export précédent) dans %s.",
        exported_count,
        appended_from_previous,
        csv_path,
    )
    return csv_path


def main():
    run_active_directory_export()


if __name__ == "__main__":
    main()
