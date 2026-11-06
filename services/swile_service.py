import csv
import copy
import json
import tempfile
from datetime import date, datetime
from pathlib import Path

from domain.normalization import (
    normalize_matricule,
    normalize_name,
    remove_diacritics,
)
from domain.matching import compare_users as match_users
from domain.swile_additions import (
    DEFAULT_ADDITION_FILTERS,
    build_additions,
)
from services.csv_files import DEFAULT_TEMPLATE_FILE, read_csv
from services.paths import bundled_resource, project_root

SWILE_CONFIG_PATH = project_root() / "swile.config.json"
LEGACY_SWILE_CONFIG_PATH = (
    project_root() / "lieux_travail.config.json"
)
DEFAULT_WORK_LOCATION_MAPPING = {
    "default_value": "Autre",
    "rules": [
        {
            "patterns": [
                ["145-151 rue de courcelles"],
                ["paris", "courcelles"],
                ["paris", "145"],
            ],
            "value": "Paris 145",
        },
        {
            "patterns": [
                ["29 avenue de la marne"],
                ["wasquehal"],
            ],
            "value": "Lille 5.9",
        },
        {
            "patterns": [["paris", "133"]],
            "value": "Paris 133",
        },
    ],
}


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
                "Ajouts ignorés (filtre sur le poste) : "
                f"{ignored_count} -> {ignored_path}",
                f"Lignes exclues par le filtre de poste : {excluded_management}",
                f"Lignes exclues par le filtre d’e-mail : {excluded_external}",
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


def load_work_location_mapping(config_path=None):
    """Charge et valide le mapping des lieux, avec repli si le fichier manque."""
    config_path = _resolve_swile_config_path(config_path)
    if not config_path.exists():
        mapping = copy.deepcopy(DEFAULT_WORK_LOCATION_MAPPING)
    else:
        try:
            with config_path.open(encoding="utf-8") as config_file:
                mapping = json.load(config_file)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Configuration des lieux invalide ({config_path}) : {error}"
            ) from error

    validated_mapping = _validate_work_location_mapping(mapping, config_path)
    return {
        key: value
        for key, value in validated_mapping.items()
        if key != "filters"
    }


def load_addition_filters(config_path=None):
    """Charge les filtres des ajouts ou applique les filtres historiques."""
    config_path = _resolve_swile_config_path(config_path)
    if not config_path.exists():
        return copy.deepcopy(DEFAULT_ADDITION_FILTERS)

    try:
        with config_path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Configuration des filtres invalide ({config_path}) : {error}"
        ) from error

    if not isinstance(config, dict):
        raise ValueError(
            f"La configuration des filtres doit être un objet JSON : "
            f"{config_path}"
        )
    filters = config.get("filters", {})
    return _validate_addition_filters(filters, config_path)


def _validate_addition_filters(filters, config_path):
    """Valide les règles de filtrage des e-mails et des postes."""
    if not isinstance(filters, dict):
        raise ValueError(f"'filters' doit être un objet JSON : {config_path}")
    unknown_keys = filters.keys() - DEFAULT_ADDITION_FILTERS.keys()
    if unknown_keys:
        raise ValueError(
            f"Clé(s) de filtre inconnue(s) {sorted(unknown_keys)} : "
            f"{config_path}"
        )

    validated_filters = copy.deepcopy(DEFAULT_ADDITION_FILTERS)
    for filter_name, default_config in validated_filters.items():
        if filter_name not in filters:
            continue
        filter_config = filters[filter_name]
        if not isinstance(filter_config, dict):
            raise ValueError(
                f"'filters.{filter_name}' doit être un objet JSON : "
                f"{config_path}"
            )
        unknown_filter_keys = filter_config.keys() - {
            "default_value",
            "rules",
        }
        if unknown_filter_keys:
            raise ValueError(
                f"Clé(s) inconnue(s) dans 'filters.{filter_name}' : "
                f"{sorted(unknown_filter_keys)} ({config_path})"
            )
        default_value = filter_config.get(
            "default_value", default_config["default_value"]
        )
        rules = filter_config.get("rules", default_config["rules"])
        if default_value not in ("inclure", "exclure"):
            raise ValueError(
                f"'filters.{filter_name}.default_value' doit valoir "
                f"'inclure' ou 'exclure' : {config_path}"
            )
        if not isinstance(rules, list):
            raise ValueError(
                f"'filters.{filter_name}.rules' doit être une liste : "
                f"{config_path}"
            )
        validated_rules = []
        for index, rule in enumerate(rules, start=1):
            if not isinstance(rule, dict) or rule.keys() - {
                "patterns",
                "value",
            }:
                raise ValueError(
                    f"La règle {index} de 'filters.{filter_name}' doit "
                    f"contenir uniquement 'patterns' et 'value' : "
                    f"{config_path}"
                )
            patterns = rule.get("patterns")
            value = rule.get("value")
            if (
                not isinstance(patterns, list)
                or not patterns
                or value not in ("inclure", "exclure")
            ):
                raise ValueError(
                    f"La règle {index} de 'filters.{filter_name}' doit "
                    f"contenir des 'patterns' et une 'value' égale à "
                    f"'inclure' ou 'exclure' : {config_path}"
                )
            for pattern in patterns:
                if (
                    not isinstance(pattern, list)
                    or not pattern
                    or any(
                        not isinstance(term, str) or not term.strip()
                        for term in pattern
                    )
                ):
                    raise ValueError(
                        f"Chaque motif de la règle {index} de "
                        f"'filters.{filter_name}' doit être une liste de "
                        f"termes non vides : {config_path}"
                    )
            validated_rules.append(
                {
                    "patterns": [
                        [term.strip() for term in pattern]
                        for pattern in patterns
                    ],
                    "value": value,
                }
            )
        validated_filters[filter_name] = {
            "default_value": default_value,
            "rules": validated_rules,
        }
    return validated_filters


def _resolve_swile_config_path(config_path=None):
    """Privilégie le nom commun et lit l’ancien nom pour migrer les installations."""
    if config_path is not None:
        return Path(config_path)
    if SWILE_CONFIG_PATH.exists() or not LEGACY_SWILE_CONFIG_PATH.exists():
        return SWILE_CONFIG_PATH
    return LEGACY_SWILE_CONFIG_PATH


def _validate_work_location_mapping(mapping, config_path):
    """Valide la structure et le contenu du mapping des lieux."""
    if not isinstance(mapping, dict):
        raise ValueError(
            f"La configuration des lieux doit être un objet JSON : {config_path}"
        )
    default_value = mapping.get("default_value")
    rules = mapping.get("rules")
    if not isinstance(default_value, str) or not default_value.strip():
        raise ValueError(
            f"'default_value' doit être une chaîne non vide : {config_path}"
        )
    if not isinstance(rules, list):
        raise ValueError(f"'rules' doit être une liste : {config_path}")

    for index, rule in enumerate(rules, start=1):
        if not isinstance(rule, dict):
            raise ValueError(
                f"La règle {index} doit être un objet : {config_path}"
            )
        patterns = rule.get("patterns")
        value = rule.get("value")
        if (
            not isinstance(value, str)
            or not value.strip()
            or not isinstance(patterns, list)
            or not patterns
        ):
            raise ValueError(
                f"La règle {index} doit contenir 'value' et 'patterns' : "
                f"{config_path}"
            )
        for pattern in patterns:
            if (
                not isinstance(pattern, list)
                or not pattern
                or any(
                    not isinstance(term, str) or not term.strip()
                    for term in pattern
                )
            ):
                raise ValueError(
                    f"Chaque motif de la règle {index} doit être une liste "
                    f"de termes non vides : {config_path}"
                )
    return mapping


def save_work_location_mapping(mapping, config_path=None, filters=None):
    """Enregistre atomiquement le mapping des lieux et les filtres Swile."""
    config_path = Path(config_path or SWILE_CONFIG_PATH)
    existing_config = {}
    if config_path.exists():
        try:
            with config_path.open(encoding="utf-8") as config_file:
                existing_config = json.load(config_file)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Configuration des lieux invalide ({config_path}) : {error}"
            ) from error
        if not isinstance(existing_config, dict):
            raise ValueError(
                f"La configuration des lieux doit être un objet JSON : "
                f"{config_path}"
            )

    updated_config = {**existing_config, **mapping}
    updated_config["filters"] = _validate_addition_filters(
        filters if filters is not None else existing_config.get("filters", {}),
        config_path,
    )
    _validate_work_location_mapping(updated_config, config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=config_path.parent,
            prefix=f".{config_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(
                updated_config,
                temporary_file,
                indent=2,
                ensure_ascii=False,
            )
            temporary_file.write("\n")
        temporary_path.replace(config_path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return config_path


def map_work_location_value(work_location, mapping=None):
    """Associe un lieu de travail à la première règle de configuration."""
    normalized_location = remove_diacritics((work_location or "").strip())
    mapping = mapping or load_work_location_mapping()
    for rule in mapping["rules"]:
        for pattern in rule["patterns"]:
            if all(
                remove_diacritics(term.strip()) in normalized_location
                for term in pattern
            ):
                return rule["value"]
    return mapping["default_value"]


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
    try:
        _, active_directory_users = read_csv(
            active_directory_path,
            ",",
            {"Nom", "Email", "Identifiant", "Poste", "Lieu de travail"},
        )
    except ValueError as error:
        if "Lieu de travail" not in str(error):
            raise
        missing_work_location_column = True
        _, active_directory_users = read_csv(
            active_directory_path,
            ",",
            {"Nom", "Email", "Identifiant", "Poste"},
        )
    else:
        missing_work_location_column = False

    found_users, _ = match_users(swile_users, active_directory_users)
    additions = build_additions(
        swile_users,
        active_directory_users,
        report_domain,
        load_addition_filters(filters_config_path),
    )[0]
    source_users = found_users + additions
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
    for user in source_users:
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
                    ),
                    work_location_mapping,
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
