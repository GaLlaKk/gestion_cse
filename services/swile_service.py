import csv
from datetime import date

from domain.matching import compare_users as match_users
from domain.swile_additions import build_additions
from services.csv_files import DEFAULT_TEMPLATE_FILE, read_csv
from services.paths import bundled_resource, project_root


def execute_swile_action(
    action,
    swile_path,
    active_directory_path,
    template_path=None,
    output_directory=None,
    output_path=None,
    ignored_output_path=None,
    report_domain="epsilon-france.com",
):
    root = project_root()
    output_directory = output_directory or (
        root / "swile_active_directory" / "out"
    )
    output_path = output_path or (
        output_directory / f"collaborators-additions-{date.today():%Y%m%d}.csv"
    )
    results = []

    if action in ("compare", "all"):
        found_path, not_found_path, found_count, not_found_count = compare_users(
            swile_path, active_directory_path, output_directory
        )
        results.extend(
            (
                f"Utilisateurs trouvés : {found_count} -> {found_path}",
                f"Utilisateurs non trouvés : {not_found_count} -> {not_found_path}",
            )
        )

    if action in ("additions", "all"):
        template_path = template_path or (
            root / "swile_active_directory" / "in" / DEFAULT_TEMPLATE_FILE
        )
        if not template_path.exists():
            template_path = bundled_resource(
                "swile_active_directory", "in", DEFAULT_TEMPLATE_FILE
            )
        (
            addition_count,
            ignored_path,
            ignored_count,
            excluded_management,
            excluded_existing,
            excluded_invalid,
            excluded_external,
        ) = generate_additions(
            swile_path,
            active_directory_path,
            template_path,
            output_path,
            report_domain,
            ignored_output_path,
        )
        results.extend(
            (
                f"Ajouts à importer : {addition_count} -> {output_path}",
                "Ajouts ignorés (postes de direction) : "
                f"{ignored_count} -> {ignored_path}",
                f"Postes de direction exclus : {excluded_management}",
                f"Adresses externes .ext exclues : {excluded_external}",
                f"Déjà présents dans Swile : {excluded_existing}",
            )
        )
        if excluded_invalid:
            results.append(
                f"Lignes ignorées faute de nom exploitable : {excluded_invalid}"
            )

    return "\n".join(results)


def compare_users(swile_path, active_directory_path, output_directory):
    swile_columns, swile_users = read_csv(
        swile_path, ";", {"Prénom", "Nom", "Email", "Matricule"}
    )
    _, active_directory_users = read_csv(
        active_directory_path, ",", {"Nom", "Email"}
    )
    found_users, not_found_users = match_users(
        swile_users, active_directory_users
    )

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
    template_columns, _ = read_csv(
        template_path,
        ";",
        {"Prénom", "Nom", "Email", "Matricule"},
    )
    _, active_directory_users = read_csv(
        active_directory_path, ",", {"Nom", "Email", "Identifiant", "Poste"}
    )
    (
        additions,
        ignored_additions,
        excluded_management,
        excluded_existing,
        excluded_invalid,
        excluded_external,
    ) = build_additions(swile_users, active_directory_users, report_domain)

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
