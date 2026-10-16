import argparse
import csv
import re
import unicodedata
from datetime import date
from pathlib import Path


APPLICATION_DIRECTORY = Path(__file__).resolve().parent / "swile_active_directory"
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


def latest_input_file(input_directory, pattern, description):
    candidates = list(input_directory.glob(pattern))
    if pattern == "collaborators*.csv":
        candidates = [
            path
            for path in candidates
            if not path.stem.startswith("collaborators-additions")
            and not path.stem.endswith(("-trouves", "-non-trouves"))
            and path.name != DEFAULT_TEMPLATE_FILE
        ]
    if not candidates:
        raise FileNotFoundError(
            f"Aucun fichier {description} trouvé dans {input_directory}."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


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
    ignored_output_path=None,
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
    ignored_additions = []
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

        addition = {
            "Prénom": first_name,
            "Nom": last_name,
            "Email": email,
        }
        if is_direction_position(user.get("Poste")):
            excluded_management += 1
            ignored_additions.append(addition)
        else:
            additions.append(addition)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if ignored_output_path is None:
        if "-additions" in output_path.stem:
            ignored_stem = output_path.stem.replace(
                "-additions", "-ignored-additions", 1
            )
        else:
            ignored_stem = f"{output_path.stem}-ignored-additions"
        ignored_output_path = output_path.with_name(f"{ignored_stem}.csv")
    ignored_output_path.parent.mkdir(parents=True, exist_ok=True)

    for csv_path, users in (
        (output_path, additions),
        (ignored_output_path, ignored_additions),
    ):
        with csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=template_columns,
                delimiter=";",
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(users)

    return (
        len(additions),
        ignored_output_path,
        len(ignored_additions),
        excluded_management,
        excluded_existing,
        excluded_invalid,
        excluded_external,
    )


def main():
    input_directory = APPLICATION_DIRECTORY / "in"
    output_directory = APPLICATION_DIRECTORY / "out"
    parser = argparse.ArgumentParser(
        description="Comparer Swile à l'Active Directory et préparer des ajouts."
    )
    parser.add_argument(
        "action",
        choices=("compare", "additions", "all"),
        help="Traitement à effectuer : comparaison, ajouts, ou les deux.",
    )
    parser.add_argument(
        "--swile-file",
        type=Path,
        default=None,
        help="CSV Swile dans in, séparé par des points-virgules.",
    )
    parser.add_argument(
        "--active-directory-file",
        type=Path,
        default=None,
        help="CSV Active Directory dans in, séparé par des virgules.",
    )
    parser.add_argument(
        "--template-file",
        type=Path,
        default=input_directory / DEFAULT_TEMPLATE_FILE,
        help="Modèle CSV Swile dans in.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=output_directory,
        help="Dossier de sortie de la comparaison (par défaut : swile_active_directory/out).",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        default=output_directory
        / f"collaborators-additions-{date.today():%Y%m%d}.csv",
        help="Fichier de sortie pour les ajouts.",
    )
    parser.add_argument(
        "--ignored-output-file",
        type=Path,
        default=None,
        help=(
            "Fichier de sortie pour les ajouts écartés (par défaut : "
            "même dossier, avec ignored-additions dans le nom)."
        ),
    )
    parser.add_argument(
        "--report-domain",
        default="epsilon-france.com",
        help="Domaine des employés à inclure (par défaut : epsilon-france.com).",
    )
    args = parser.parse_args()
    swile_path = args.swile_file or latest_input_file(
        input_directory, "collaborators*.csv", "Swile"
    )
    active_directory_path = args.active_directory_file or latest_input_file(
        input_directory,
        "*liste_salarie_active_directory.csv",
        "Active Directory",
    )

    if args.action in ("compare", "all"):
        found_path, not_found_path, found_count, not_found_count = compare_users(
            swile_path, active_directory_path, args.output_directory
        )
        print(f"Utilisateurs trouvés : {found_count} -> {found_path}")
        print(f"Utilisateurs non trouvés : {not_found_count} -> {not_found_path}")

    if args.action in ("additions", "all"):
        (
            addition_count,
            ignored_output_path,
            ignored_addition_count,
            excluded_management,
            excluded_existing,
            excluded_invalid,
            excluded_external,
        ) = generate_additions(
            swile_path,
            active_directory_path,
            args.template_file,
            args.output_file,
            args.report_domain,
            args.ignored_output_file,
        )
        print(f"Ajouts à importer : {addition_count} -> {args.output_file}")
        print(
            f"Ajouts ignorés (postes de direction) : "
            f"{ignored_addition_count} -> {ignored_output_path}"
        )
        print(f"Postes de direction exclus : {excluded_management}")
        print(f"Adresses externes .ext exclues : {excluded_external}")
        print(f"Déjà présents dans Swile : {excluded_existing}")
        if excluded_invalid:
            print(f"Lignes ignorées faute de nom exploitable : {excluded_invalid}")


if __name__ == "__main__":
    main()
