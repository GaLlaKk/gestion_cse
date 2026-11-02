import argparse
from pathlib import Path

from services.csv_files import DEFAULT_TEMPLATE_FILE, latest_input_file
from services.paths import project_root
from services.swile_service import execute_swile_action

ROOT_DIRECTORY = project_root()
APPLICATION_DIRECTORY = ROOT_DIRECTORY / "swile_active_directory"


def main():
    input_directory = APPLICATION_DIRECTORY / "in"
    output_directory = APPLICATION_DIRECTORY / "out"
    actions_needing_swile = {"compare", "additions", "all", "location_values"}
    actions_needing_template = {"additions", "all"}
    parser = argparse.ArgumentParser(
        description=(
            "Comparer Swile à l'Active Directory, préparer des ajouts, "
            "ou générer un fichier de valeurs d'attribut."
        )
    )
    parser.add_argument(
        "action",
        choices=("compare", "additions", "all", "location_values"),
        help=(
            "Traitement à effectuer : comparaison, ajouts, les deux, "
            "ou génération des valeurs de lieu de travail."
        ),
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
        default=None,
        help=(
            "Fichier de sortie personnalisé (ajouts ou valeurs de lieu de travail)."
        ),
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

    swile_path = None
    if args.action in actions_needing_swile:
        swile_path = args.swile_file or latest_input_file(
            input_directory, "collaborators*.csv", "Swile"
        )
    active_directory_path = args.active_directory_file or latest_input_file(
        input_directory,
        "*liste_salarie_active_directory.csv",
        "Active Directory",
    )
    template_path = args.template_file if args.action in actions_needing_template else None

    print(
        execute_swile_action(
            args.action,
            swile_path,
            active_directory_path,
            template_path=template_path,
            output_directory=args.output_directory,
            output_path=args.output_file,
            ignored_output_path=args.ignored_output_file,
            report_domain=args.report_domain,
        )
    )


if __name__ == "__main__":
    main()
