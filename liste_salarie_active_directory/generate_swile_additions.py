import argparse
import csv
import re
from datetime import date
from pathlib import Path

from compare_swile_active_directory import (
    active_directory_keys,
    normalize_matricule,
    normalize_name,
    remove_diacritics,
    read_csv,
)


DEFAULT_SWILE_FILE = (
    "collaborators-4aabb62b-ee87-4cba-a43b-9174ea1ef65f-2026-10-15.csv"
)
DEFAULT_ACTIVE_DIRECTORY_FILE = "20261015_liste_salarie_active_directory.csv"
DEFAULT_TEMPLATE_FILE = (
    "collaborators_template_090d2568-c182-4cf4-8b3a-81fefee3a297.csv"
)
DIRECTION_TITLES = {
    "ceo",
    "coo",
    "dg",
    "dga",
    "pdg",
    "directeur",
    "directrice",
    "directreur",
    "direction",
    "president",
    "presidente",
}


def is_direction_position(job_title):
    title_tokens = set(
        re.findall(r"[a-z0-9]+", remove_diacritics(job_title or ""))
    )
    return bool(title_tokens & DIRECTION_TITLES)


def split_full_name(full_name):
    name_parts = (full_name or "").strip().split(maxsplit=1)
    if len(name_parts) < 2:
        return None
    return name_parts[0], name_parts[1]


def generate_additions(
    swile_path,
    active_directory_path,
    template_path,
    output_path,
    report_domain,
):
    _, swile_users = read_csv(
        swile_path, ";", {"Prénom", "Nom", "Email", "Matricule"}
    )
    template_columns, _ = read_csv(template_path, ";", {"Prénom", "Nom", "Email"})
    _, active_directory_users = read_csv(
        active_directory_path, ",", {"Nom", "Email", "Poste"}
    )

    existing_keys = {"email": set(), "matricule": set(), "name": set()}
    for user in swile_users:
        email = (user.get("Email") or "").strip().casefold()
        matricule = normalize_matricule(user.get("Matricule") or "")
        name = normalize_name(
            f"{user.get('Prénom') or ''}{user.get('Nom') or ''}"
        )
        if email:
            existing_keys["email"].add(email)
        if matricule:
            existing_keys["matricule"].add(matricule)
        if name:
            existing_keys["name"].add(name)

    additions = []
    excluded_management = 0
    excluded_existing = 0
    excluded_invalid = 0
    excluded_external = 0
    seen_emails = set()
    normalized_domain = report_domain.lstrip("@").casefold()

    for user in active_directory_users:
        email = (user.get("Email") or "").strip()
        normalized_email = email.casefold()
        if not normalized_email.endswith(f"@{normalized_domain}"):
            continue
        if normalized_email.endswith(f".ext@{normalized_domain}"):
            excluded_external += 1
            continue
        if is_direction_position(user.get("Poste")):
            excluded_management += 1
            continue

        name_parts = split_full_name(user.get("Nom"))
        if not email or name_parts is None:
            excluded_invalid += 1
            continue
        if normalized_email in seen_emails:
            continue
        seen_emails.add(normalized_email)

        first_name, last_name = name_parts
        keys = active_directory_keys(user)
        name_key = normalize_name(f"{first_name}{last_name}")
        if any(
            (
                keys["email"]
                and keys["email"] in existing_keys["email"],
                keys["matricule"]
                and keys["matricule"] in existing_keys["matricule"],
                name_key and name_key in existing_keys["name"],
            )
        ):
            excluded_existing += 1
            continue

        additions.append(
            {
                "Prénom": first_name,
                "Nom": last_name,
                "Email": email,
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=template_columns,
            delimiter=";",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(additions)

    return (
        len(additions),
        excluded_management,
        excluded_existing,
        excluded_invalid,
        excluded_external,
    )


def main():
    script_directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description=(
            "Génère un CSV Swile avec les personnes de la liste "
            "liste_salarie_active_directory absentes de la liste actuelle, "
            "hors postes de direction."
        )
    )
    parser.add_argument(
        "--swile-file",
        type=Path,
        default=script_directory / DEFAULT_SWILE_FILE,
        help="CSV Swile actuel, séparé par des points-virgules.",
    )
    parser.add_argument(
        "--active-directory-file",
        type=Path,
        default=script_directory / DEFAULT_ACTIVE_DIRECTORY_FILE,
        help="CSV liste_salarie_active_directory, séparé par des virgules.",
    )
    parser.add_argument(
        "--template-file",
        type=Path,
        default=script_directory / DEFAULT_TEMPLATE_FILE,
        help="Modèle CSV Swile d'ajout.",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=script_directory
        / f"collaborators-additions-{date.today():%Y%m%d}.csv",
        help="CSV de sortie (par défaut : à côté du script).",
    )
    parser.add_argument(
        "--report-domain",
        default="epsilon-france.com",
        help="Domaine des employés à inclure (par défaut : epsilon-france.com).",
    )
    args = parser.parse_args()

    (
        addition_count,
        excluded_management,
        excluded_existing,
        excluded_invalid,
        excluded_external,
    ) = generate_additions(
        args.swile_file,
        args.active_directory_file,
        args.template_file,
        args.output_file,
        args.report_domain,
    )
    print(f"Ajouts à importer : {addition_count} -> {args.output_file}")
    print(f"Postes de direction exclus : {excluded_management}")
    print(f"Adresses externes .ext exclues : {excluded_external}")
    print(f"Déjà présents dans Swile : {excluded_existing}")
    if excluded_invalid:
        print(f"Lignes ignorées faute de nom exploitable : {excluded_invalid}")


if __name__ == "__main__":
    main()
