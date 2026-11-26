from datetime import datetime

from openpyxl import Workbook

from services.csv_files import read_csv
from services.ekie_config import load_cse_member_emails
from services.paths import project_root

EKIE_HEADERS = ("email", "first_name", "last_name", "is_cse_member")


def _format_result_path(path):
    """Retourne un chemin relatif au projet quand c’est possible."""
    try:
        return path.relative_to(project_root())
    except ValueError:
        return path


def _split_name_parts(full_name):
    """Découpe un nom complet en prénom / nom de famille."""
    words = [word for word in (full_name or "").strip().split() if word]
    if not words:
        return "", ""
    if len(words) == 1:
        return words[0], ""
    return words[0], " ".join(words[1:])


def _extract_first_and_last_name(active_directory_user):
    """Retourne prénom / nom depuis les colonnes AD disponibles."""
    first_name = (
        active_directory_user.get("Prénom")
        or active_directory_user.get("Prenom")
        or ""
    ).strip()
    last_name = (active_directory_user.get("Nom de famille") or "").strip()
    nom = (active_directory_user.get("Nom") or "").strip()
    if first_name and not last_name:
        lower_nom = nom.casefold()
        lower_first_name = first_name.casefold()
        if lower_nom.startswith(f"{lower_first_name} "):
            last_name = nom[len(first_name) :].strip()
        elif nom and lower_nom != lower_first_name:
            last_name = nom
    if not first_name and not last_name:
        first_name, last_name = _split_name_parts(nom)
    return first_name, last_name


def generate_ekie_employee_list(
    active_directory_path,
    output_path=None,
    cse_members_config_path=None,
):
    """Génère le fichier XLSX d’import Ekie à partir d’un export AD CSV."""
    _, active_directory_users = read_csv(
        active_directory_path,
        ",",
        {"Nom", "Email", "Identifiant"},
    )
    output_path = output_path or (
        project_root()
        / "ekie"
        / "out"
        / f"ekie_import-{datetime.now():%Y%m%dt%H%M%S}.xlsx"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cse_member_emails = load_cse_member_emails(cse_members_config_path)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "salaries"
    worksheet.append(EKIE_HEADERS)

    generated_count = 0
    for active_directory_user in active_directory_users:
        email = (active_directory_user.get("Email") or "").strip()
        first_name, last_name = _extract_first_and_last_name(
            active_directory_user
        )
        worksheet.append(
            (
                email,
                first_name,
                last_name,
                "VRAI" if email.casefold() in cse_member_emails else "FAUX",
            )
        )
        generated_count += 1

    workbook.save(output_path)
    workbook.close()
    return output_path, generated_count


def execute_ekie_export(
    active_directory_path,
    output_path=None,
    cse_members_config_path=None,
):
    """Produit le résumé textuel de génération pour l’onglet Ekie."""
    generated_path, generated_count = generate_ekie_employee_list(
        active_directory_path,
        output_path=output_path,
        cse_members_config_path=cse_members_config_path,
    )
    return (
        f"Lignes exportées pour Ekie : {generated_count}\n"
        f"-> {_format_result_path(generated_path)}"
    )

