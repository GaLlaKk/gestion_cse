import argparse
import csv
import unicodedata
from pathlib import Path


DEFAULT_SWILE_FILE = (
    "collaborators-4aabb62b-ee87-4cba-a43b-9174ea1ef65f-2026-10-15.csv"
)
DEFAULT_ACTIVE_DIRECTORY_FILE = "20261015_liste_salarie_active_directory.csv"
APPLICATION_DIRECTORY = Path(__file__).resolve().parent / "compare_swile_active_directory"


def read_csv(path, delimiter, required_columns):
    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=delimiter)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"Le fichier est vide ou sans en-tête : {path}")

        missing_columns = set(required_columns) - set(fieldnames)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Colonne(s) manquante(s) dans {path} : {missing}")

        rows = [row for row in reader if row]

    return fieldnames, rows


def remove_diacritics(value):
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )


def normalize_matricule(value):
    return "".join(
        character
        for character in remove_diacritics(value.strip())
        if not character.isspace() and character != "-"
    )


def normalize_name(value):
    return "".join(
        character
        for character in remove_diacritics(value.strip())
        if character.isalnum()
    )


def active_directory_keys(user):
    email = (user.get("Email") or "").strip().casefold()
    full_name = (user.get("Nom") or "").strip()
    name_parts = full_name.split()

    # L'AD expose le nom d'affichage, pas le matricule Swile :
    # on suppose le format « prénom(s) nom(s) » pour en dériver la clé.
    matricule = ""
    if len(name_parts) >= 2:
        first_name = name_parts[0]
        last_name = "".join(name_parts[1:])
        matricule = normalize_matricule(f"{last_name}_{first_name}")

    return {
        "email": email,
        "matricule": matricule,
        "name": normalize_name(full_name),
    }


def compare_users(swile_path, active_directory_path, output_directory):
    swile_columns, swile_users = read_csv(
        swile_path, ";", {"Prénom", "Nom", "Email", "Matricule"}
    )
    _, active_directory_users = read_csv(
        active_directory_path, ",", {"Nom", "Email"}
    )

    active_directory_keys_by_type = {
        "email": set(),
        "matricule": set(),
        "name": set(),
    }
    for user in active_directory_users:
        for key_type, key in active_directory_keys(user).items():
            if key:
                active_directory_keys_by_type[key_type].add(key)

    found_users = []
    not_found_users = []
    for user in swile_users:
        user_keys = {
            "email": (user.get("Email") or "").strip().casefold(),
            "matricule": normalize_matricule(user.get("Matricule") or ""),
            "name": normalize_name(
                f"{user.get('Prénom') or ''}{user.get('Nom') or ''}"
            ),
        }
        if any(
            key and key in active_directory_keys_by_type[key_type]
            for key_type, key in user_keys.items()
        ):
            found_users.append(user)
        else:
            not_found_users.append(user)

    output_directory.mkdir(parents=True, exist_ok=True)
    found_path = output_directory / f"{swile_path.stem}-trouves.csv"
    not_found_path = output_directory / f"{swile_path.stem}-non-trouves.csv"

    for output_path, users in (
        (found_path, found_users),
        (not_found_path, not_found_users),
    ):
        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(
                csv_file, fieldnames=swile_columns, delimiter=";"
            )
            writer.writeheader()
            writer.writerows(users)

    return found_path, not_found_path, len(found_users), len(not_found_users)


def main():
    input_directory = APPLICATION_DIRECTORY / "in"
    output_directory = APPLICATION_DIRECTORY / "out"
    parser = argparse.ArgumentParser(
        description=(
            "Compare les salariés Swile avec les utilisateurs actifs "
            "de l'Active Directory par e-mail, matricule dérivé et nom complet."
        )
    )
    parser.add_argument(
        "--swile-file",
        type=Path,
        default=input_directory / DEFAULT_SWILE_FILE,
        help="CSV Swile séparé par des points-virgules.",
    )
    parser.add_argument(
        "--active-directory-file",
        type=Path,
        default=input_directory / DEFAULT_ACTIVE_DIRECTORY_FILE,
        help="CSV Active Directory séparé par des virgules.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        help="Dossier des résultats (par défaut : compare_swile_active_directory/out).",
    )
    args = parser.parse_args()

    output_directory = args.output_directory or output_directory
    found_path, not_found_path, found_count, not_found_count = compare_users(
        args.swile_file, args.active_directory_file, output_directory
    )
    print(f"Utilisateurs trouvés : {found_count} -> {found_path}")
    print(f"Utilisateurs non trouvés : {not_found_count} -> {not_found_path}")


if __name__ == "__main__":
    main()
