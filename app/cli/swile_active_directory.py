import argparse
from datetime import date
from pathlib import Path

from services.csv_files import DEFAULT_TEMPLATE_FILE, latest_input_file
from services.swile_service import compare_users, generate_additions

ROOT_DIRECTORY = Path(__file__).resolve().parents[2]
APPLICATION_DIRECTORY = ROOT_DIRECTORY / "swile_active_directory"


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
