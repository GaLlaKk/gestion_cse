import csv
from datetime import date, datetime

from domain.normalization import (
    normalize_matricule,
    normalize_name,
    remove_diacritics,
)
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
        additions_output_path = output_path or (
            output_directory
            / f"collaborators-additions-{datetime.now():%Y%m%dt%H%M%S}.csv"
        )
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
            additions_output_path,
            report_domain,
            ignored_output_path,
        )
        results.extend(
            (
                f"Ajouts à importer : {addition_count} -> {additions_output_path}",
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

    if action == "location_values":
        location_values_output_path = output_path or (
            output_directory
            / f"collaborators-attribute-values-{date.today():%Y%m%dt%H%M%S}.csv"
        )
        (
            generated_path,
            generated_count,
            missing_work_location_column,
        ) = generate_work_location_values(
            swile_path,
            active_directory_path,
            location_values_output_path,
            report_domain,
        )
        results.extend(
            (
                "Valeurs de lieu de travail générées : "
                f"{generated_count} -> {generated_path}",
            )
        )
        if missing_work_location_column:
            results.append(
                "La colonne 'Lieu de travail' est absente du fichier Active "
                "Directory ; la valeur 'Autre' a été appliquée."
            )

    return "\n".join(results)


def compare_users(swile_path, active_directory_path, output_directory):
    swile_columns, swile_users = read_csv(
        swile_path, ";", {"Prénom", "Nom", "Email", "Matricule"}
    )
    _, active_directory_users = read_csv(
        active_directory_path, ",", {"Nom", "Email", "Identifiant"}
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


def map_work_location_value(work_location):
    normalized_location = remove_diacritics((work_location or "").strip())
    if not normalized_location:
        return "Autre"
    if (
        "145-151 rue de courcelles" in normalized_location
        or (
            "paris" in normalized_location
            and "courcelles" in normalized_location
        )
    ):
        return "Paris 145"
    if (
        "29 avenue de la marne" in normalized_location
        or "wasquehal" in normalized_location
    ):
        return "Lille 5.9"
    if (
        "paris 133" in normalized_location
        or ("paris" in normalized_location and "133" in normalized_location)
    ):
        return "Paris 133"
    return "Autre"


def generate_work_location_values(
    swile_path,
    active_directory_path,
    output_path,
    _report_domain,
):
    _, swile_users = read_csv(
        swile_path, ";", {"Prénom", "Nom", "Email", "Matricule"}
    )
    missing_work_location_column = False
    try:
        _, active_directory_users = read_csv(
            active_directory_path, ",", {"Nom", "Email", "Lieu de travail"}
        )
    except ValueError as error:
        if "Lieu de travail" not in str(error):
            raise
        missing_work_location_column = True
        _, active_directory_users = read_csv(
            active_directory_path, ",", {"Nom", "Email"}
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    locations_by_email = {}
    locations_by_matricule = {}
    locations_by_name = {}
    for user in active_directory_users:
        email_key = (user.get("Email") or "").strip().casefold()
        if email_key:
            locations_by_email[email_key] = user
        matricule_key = normalize_matricule(user.get("Identifiant") or "")
        if matricule_key:
            locations_by_matricule[matricule_key] = user
        name_key = normalize_name(user.get("Nom") or "")
        if name_key:
            locations_by_name[name_key] = user

    generated_rows = []
    for user in swile_users:
        email = (user.get("Email") or "").strip()
        first_name = (user.get("Prénom") or "").strip()
        last_name = (user.get("Nom") or "").strip()

        swile_matricule = (user.get("Matricule") or "").strip()
        normalized_email = email.casefold()
        matched_active_directory_user = (
            locations_by_email.get(normalized_email)
            or locations_by_matricule.get(normalize_matricule(swile_matricule))
            or locations_by_name.get(normalize_name(f"{first_name} {last_name}"))
        )
        matricule = (
            (
                (
                    matched_active_directory_user.get("Identifiant")
                    if matched_active_directory_user
                    else ""
                )
                or swile_matricule
            ).strip()
        )
        generated_rows.append(
            {
                "Prénom": first_name,
                "Nom de famille": last_name,
                "E-mail": email,
                "Matricule": matricule,
                "Valeur": map_work_location_value(
                    (
                        matched_active_directory_user.get("Lieu de travail")
                        if (
                            matched_active_directory_user
                            and not missing_work_location_column
                        )
                        else None
                    )
                ),
            }
        )

    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=(
                "Prénom",
                "Nom de famille",
                "E-mail",
                "Matricule",
                "Valeur",
            ),
            delimiter=";",
        )
        writer.writeheader()
        writer.writerows(generated_rows)

    return (
        output_path,
        len(generated_rows),
        missing_work_location_column,
    )
