import csv
from datetime import datetime

from domain.normalization import (
    normalize_matricule,
    normalize_name,
)
from domain.matching import compare_users as match_users
from domain.swile_additions import (
    build_additions,
)
from services.csv_files import DEFAULT_TEMPLATE_FILE, read_csv
from services.paths import bundled_resource, project_root
from services.swile_config import (
    load_addition_filters,
    load_work_location_mapping,
    map_work_location_value,
)


def _compare_summary(swile_path, active_directory_path, output_directory):
    """Lance la comparaison et retourne les lignes de résumé."""
    found_path, not_found_path, found_count, not_found_count = compare_users(
        swile_path, active_directory_path, output_directory
    )
    return [
        f"Utilisateurs trouvés : {found_count} -> {found_path}",
        f"Utilisateurs non trouvés : {not_found_count} -> {not_found_path}",
    ]


def _additions_summary(
    swile_path,
    active_directory_path,
    template_path,
    output_directory,
    output_path,
    ignored_output_path,
    report_domain,
):
    """Génère les ajouts et retourne les lignes de résumé."""
    root = project_root()
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
    lines = [
        f"Ajouts à importer : {addition_count} -> {additions_output_path}",
        "Ajouts ignorés (filtre sur le poste) : "
        f"{ignored_count} -> {ignored_path}",
        f"Lignes exclues par le filtre de poste : {excluded_management}",
        f"Lignes exclues par le filtre d’e-mail : {excluded_external}",
        f"Déjà présents dans Swile : {excluded_existing}",
    ]
    if excluded_invalid:
        lines.append(
            f"Lignes ignorées faute de nom exploitable : {excluded_invalid}"
        )
    return lines


def _location_values_summary(
    swile_path,
    active_directory_path,
    output_directory,
    output_path,
    report_domain,
):
    """Génère les valeurs de lieu et retourne les lignes de résumé."""
    location_values_output_path = output_path or (
        output_directory
        / f"collaborators-site-rattachement-{datetime.now():%Y%m%dt%H%M%S}.csv"
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
    lines = [
        "Valeurs de lieu de travail générées : "
        f"{generated_count} -> {generated_path}"
    ]
    if missing_work_location_column:
        lines.append(
            "La colonne 'Lieu de travail' est absente du fichier Active "
            "Directory ; la valeur 'Autre' a été appliquée."
        )
    return lines


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
    """Orchestre comparaison, ajouts Swile ou génération des lieux."""
    output_directory = output_directory or (
        project_root() / "swile_active_directory" / "out"
    )
    results = []
    if action in ("compare", "all"):
        results.extend(
            _compare_summary(swile_path, active_directory_path, output_directory)
        )
    if action in ("additions", "all"):
        results.extend(
            _additions_summary(
                swile_path,
                active_directory_path,
                template_path,
                output_directory,
                output_path,
                ignored_output_path,
                report_domain,
            )
        )
    if action == "location_values":
        results.extend(
            _location_values_summary(
                swile_path,
                active_directory_path,
                output_directory,
                output_path,
                report_domain,
            )
        )
    return "\n".join(results)


def compare_users(swile_path, active_directory_path, output_directory):
    """Compare les CSV Swile et AD puis écrit les fichiers trouvés et absents."""
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
    not_found_path = output_directory / (
        f"collaborators-disables-{datetime.now():%Y%m%dt%H%M%S}.csv"
    )

    for output_path, users in (
        (found_path, found_users),
        (not_found_path, not_found_users),
    ):
        if not users:
            continue
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
    filters_config_path=None,
):
    """Génère les CSV d’ajouts Swile et d’ajouts ignorés."""
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
    ) = build_additions(
        swile_users,
        active_directory_users,
        report_domain,
        load_addition_filters(filters_config_path),
    )

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
        if not users:
            continue
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


LOCATION_VALUE_COLUMNS = (
    "Prénom",
    "Nom de famille",
    "E-mail",
    "Matricule",
    "Valeur",
)


def _read_active_directory_users_with_locations(active_directory_path):
    """Lit l’export AD; indique si la colonne « Lieu de travail » manque."""
    required_columns = {"Nom", "Email", "Identifiant", "Poste"}
    try:
        _, users = read_csv(
            active_directory_path,
            ",",
            required_columns | {"Lieu de travail"},
        )
    except ValueError as error:
        if "Lieu de travail" not in str(error):
            raise
        _, users = read_csv(active_directory_path, ",", required_columns)
        return users, True
    return users, False


def _index_active_directory_users(active_directory_users):
    """Indexe les comptes AD par e-mail, matricule normalisé et nom normalisé."""
    by_email, by_matricule, by_name = {}, {}, {}
    for user in active_directory_users:
        email_key = (user.get("Email") or "").strip().casefold()
        if email_key:
            by_email[email_key] = user
        matricule_key = normalize_matricule(user.get("Identifiant") or "")
        if matricule_key:
            by_matricule[matricule_key] = user
        name_key = normalize_name(user.get("Nom") or "")
        if name_key:
            by_name[name_key] = user
    return by_email, by_matricule, by_name


def generate_work_location_values(
    swile_path,
    active_directory_path,
    output_path,
    report_domain,
    mapping_config_path=None,
    filters_config_path=None,
):
    """Crée les valeurs pour les Swile trouvés et les ajouts filtrés."""
    work_location_mapping = load_work_location_mapping(mapping_config_path)
    _, swile_users = read_csv(
        swile_path, ";", {"Prénom", "Nom", "Email", "Matricule"}
    )
    (
        active_directory_users,
        missing_work_location_column,
    ) = _read_active_directory_users_with_locations(active_directory_path)

    found_users, _ = match_users(swile_users, active_directory_users)
    additions = build_additions(
        swile_users,
        active_directory_users,
        report_domain,
        load_addition_filters(filters_config_path),
    )[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    by_email, by_matricule, by_name = _index_active_directory_users(
        active_directory_users
    )

    generated_rows = []
    for user in found_users + additions:
        email = (user.get("Email") or "").strip()
        first_name = (user.get("Prénom") or "").strip()
        last_name = (user.get("Nom") or "").strip()
        swile_matricule = (user.get("Matricule") or "").strip()
        active_directory_user = (
            by_email.get(email.casefold())
            or by_matricule.get(normalize_matricule(swile_matricule))
            or by_name.get(normalize_name(f"{first_name} {last_name}"))
        )
        work_location = None
        matricule = swile_matricule
        if active_directory_user:
            matricule = (
                active_directory_user.get("Identifiant") or swile_matricule
            ).strip()
            if not missing_work_location_column:
                work_location = active_directory_user.get("Lieu de travail")
        generated_rows.append(
            {
                "Prénom": first_name,
                "Nom de famille": last_name,
                "E-mail": email,
                "Matricule": matricule,
                "Valeur": map_work_location_value(
                    work_location, work_location_mapping
                ),
            }
        )

    if generated_rows:
        with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
            writer = csv.DictWriter(
                csv_file, fieldnames=LOCATION_VALUE_COLUMNS, delimiter=";"
            )
            writer.writeheader()
            writer.writerows(generated_rows)

    return output_path, len(generated_rows), missing_work_location_column
