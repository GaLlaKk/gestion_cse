import csv
import json
import logging
from datetime import datetime
from pathlib import Path

import requests
from msal import PublicClientApplication

# --- CONFIGURATION ---
config_path = Path(__file__).resolve().with_name("organigramme.config.json")
with config_path.open(encoding="utf-8") as config_file:
    config = json.load(config_file)

required_string_settings = (
    "start_user_email",
    "client_id",
    "authority",
    "report_domain",
    "output_directory",
)
for setting_name in required_string_settings:
    if not isinstance(config.get(setting_name), str) or not config[setting_name].strip():
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

output_dir = (config_path.parent / config["output_directory"]).resolve()
output_dir.mkdir(parents=True, exist_ok=True)
run_started_at = datetime.now()
date_prefix = run_started_at.strftime("%Y%m%d")
log_filename = f"{date_prefix}_{run_started_at.strftime('%H%M%S_%f')}_organigramme.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(output_dir / log_filename, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)
logger.info("Démarrage de la génération de l'organigramme.")

START_USER_EMAIL = config["start_user_email"]
CLIENT_ID = config["client_id"]
AUTHORITY = config["authority"]
SCOPES = scopes
REPORT_DOMAIN = config["report_domain"].lstrip("@").casefold()

# --- AUTHENTIFICATION ---
app = PublicClientApplication(CLIENT_ID, authority=AUTHORITY)
flow = app.initiate_device_flow(scopes=SCOPES)
if "user_code" not in flow:
    raise Exception("Impossible d'initier la connexion.")

print("--- CONNEXION REQUISE ---")
print(flow["message"])
result = app.acquire_token_by_device_flow(flow)

if "access_token" not in result:
    raise Exception(f"Erreur d'authentification : {result.get('error_description')}")

headers = {"Authorization": f"Bearer {result['access_token']}"}

# --- PARCOURS DE L'ARBRE (Méthode descendante) ---
processed_ids = set()
org_data = []


def get_user_details(user_id_or_email):
    url = (
        "https://graph.microsoft.com/v1.0/users/"
        f"{user_id_or_email}?$select=id,displayName,mail,userPrincipalName,"
        "jobTitle,department"
    )
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json()
    return None


def get_manager_email(user_id):
    url = (
        f"https://graph.microsoft.com/v1.0/users/{user_id}/manager?$select=mail"
    )
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        return res.json().get("mail")
    return None


def fetch_hierarchy_recursive(user_id_or_email):
    user_info = get_user_details(user_id_or_email)
    if not user_info:
        logger.warning("Utilisateur introuvable : %s", user_id_or_email)
        return
    logger.info("Informations utilisateur : %s", user_info)
    user_id = user_info["id"]

    # Éviter les boucles infinies ou les doublons
    if user_id in processed_ids:
        return
    processed_ids.add(user_id)

    logger.info(
        "Traitement : %s (%s)",
        user_info.get("displayName"),
        user_info.get("mail"),
    )

    # Récupérer le manager
    manager_email = get_manager_email(user_id)

    # Récupérer les collaborateurs directs
    reports_url = f"https://graph.microsoft.com/v1.0/users/{user_id}/directReports?$select=id,mail,displayName"
    rep_resp = requests.get(reports_url, headers=headers)

    direct_reports_data = []
    direct_reports_emails = []

    if rep_resp.status_code == 200:
        direct_reports_data = rep_resp.json().get("value", [])
        direct_reports_emails = [
            r["mail"] for r in direct_reports_data if r.get("mail")
        ]

    # Construction de l'entrée utilisateur
    user_entry = {
        "id": user_id,
        "identity": {
            "name": user_info.get("displayName"),
            "email": user_info.get("mail"),
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
            "manager_email": manager_email,
            "direct_reports": direct_reports_emails,
        },
    }

    org_data.append(user_entry)

    # Appel récursif pour chaque collaborateur direct
    for report in direct_reports_data:
        mail = report.get("mail")
        logger.info("Vérification du collaborateur : %s", mail)
        if mail and mail.casefold().endswith(f"@{REPORT_DOMAIN}"):
            fetch_hierarchy_recursive(report["id"])


# Lancement de la collecte à partir du point d'entrée
fetch_hierarchy_recursive(START_USER_EMAIL)

# --- EXPORT CSV ---
csv_filename = f"{date_prefix}_organisation_branche.csv"
csv_path = output_dir / csv_filename

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

logger.info(
    "Terminé : %s personnes exportées dans %s.",
    len(org_data),
    csv_path,
)