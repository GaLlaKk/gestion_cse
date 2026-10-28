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

from services.paths import project_root


def _download_user_photo(user_id, identifier, photo_directory, request_graph):
    logger = logging.getLogger(__name__)
    safe_identifier = "".join(
        "_" if character in '<>:"/\\|?*' else character
        for character in (identifier or "inconnu")
    ).rstrip(" .")
    photo_path = photo_directory / f"{safe_identifier}_{user_id}.jpg"
    if photo_path.is_file() and photo_path.stat().st_size > 0:
        logger.info("Photo réutilisée depuis le cache.")
        return photo_path

    response = request_graph(
        f"https://graph.microsoft.com/v1.0/users/{user_id}/photo/$value"
    )
    if response.status_code == 404:
        logger.info("Aucune photo disponible pour un compte.")
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
    logger.info("Photo récupérée.")
    return photo_path


def get_config_path():
    return project_root() / "liste_salarie_active_directory.config.json"


def initialize_output(config_path):
    application_directory = config_path.parent
    output_dir = application_directory / "liste_salarie_active_directory" / "out"
    log_dir = application_directory / "log"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    run_started_at = datetime.now()
    date_prefix = run_started_at.strftime("%Y%m%d")
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
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    for handler in (
        logging.FileHandler(log_dir / log_filename, encoding="utf-8"),
        logging.StreamHandler(),
    ):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.info("Démarrage de la génération de la liste_salarie_active_directory.")
    return logger, output_dir, date_prefix


def run_active_directory_export(on_device_code=None, download_photos=False):
    config_path = get_config_path()
    logger, output_dir, date_prefix = initialize_output(config_path)
    try:
        with config_path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)

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
            "jobTitle,department"
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

    def fetch_hierarchy():
        org_data = []
        processed_ids = set()
        pending = [(START_USER_EMAIL, True, 0)]

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
                        logger.warning("Compte introuvable dans Microsoft Graph.")
                        continue

                    user_entry, direct_reports_data, is_epsilon_user = result
                    user_id = user_entry["id"]
                    if user_id in processed_ids:
                        continue
                    processed_ids.add(user_id)

                    logger.info("Compte Active Directory traité.")
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
                                    "Impossible de récupérer une photo de compte."
                                )
                        org_data.append(user_entry)

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
            len(org_data),
        )
        return org_data

    logger.info(
        "Récupération des photos %s.",
        "activée" if download_photos else "désactivée",
    )
    logger.info("Démarrage de la collecte de la hiérarchie Active Directory.")
    try:
        org_data = fetch_hierarchy()
    except Exception:
        logger.exception("Échec de la collecte de la hiérarchie Active Directory.")
        raise
    csv_filename = f"{date_prefix}_liste_salarie_active_directory.csv"
    csv_path = output_dir / csv_filename

    try:
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Nom",
                    "Email",
                    "Identifiant",
                    "Poste",
                    "Business Unit",
                    "Manager Email",
                    "Collaborateurs à charge",
                ]
            )

            for entry in org_data:
                writer.writerow(
                    [
                        entry["identity"]["name"],
                        entry["identity"]["email"],
                        entry["identity"]["username"],
                        entry["professional_info"]["job_title"],
                        entry["professional_info"]["business_unit"],
                        entry["hierarchy"]["manager_email"],
                        ", ".join(entry["hierarchy"]["direct_reports"]),
                    ]
                )
    except Exception:
        logger.exception("Échec de l’écriture de l’export Active Directory.")
        raise

    logger.info(
        "Terminé : %s personnes exportées dans %s.",
        len(org_data),
        csv_path,
    )
    return csv_path


def main():
    run_active_directory_export()


if __name__ == "__main__":
    main()
