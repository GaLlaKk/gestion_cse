import copy
import json
from pathlib import Path

from domain.normalization import remove_diacritics
from domain.swile_additions import DEFAULT_ADDITION_FILTERS
from services.atomic_files import atomic_write
from services.paths import project_root

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


def _validate_patterns(patterns, rule_label, config_path):
    """Vérifie que chaque motif est une liste non vide de termes non vides."""
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
                f"Chaque motif de la règle {rule_label} doit être une liste "
                f"de termes non vides : {config_path}"
            )


def _validate_filter_rule(index, rule, filter_name, config_path):
    """Valide une règle de filtre et retourne sa version normalisée."""
    scope = f"'filters.{filter_name}'"
    if not isinstance(rule, dict) or rule.keys() - {"patterns", "value"}:
        raise ValueError(
            f"La règle {index} de {scope} doit contenir uniquement "
            f"'patterns' et 'value' : {config_path}"
        )
    patterns = rule.get("patterns")
    value = rule.get("value")
    if (
        not isinstance(patterns, list)
        or not patterns
        or value not in ("inclure", "exclure")
    ):
        raise ValueError(
            f"La règle {index} de {scope} doit contenir des 'patterns' et "
            f"une 'value' égale à 'inclure' ou 'exclure' : {config_path}"
        )
    _validate_patterns(patterns, f"{index} de {scope}", config_path)
    return {
        "patterns": [[term.strip() for term in pattern] for pattern in patterns],
        "value": value,
    }


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
        validated_filters[filter_name] = {
            "default_value": default_value,
            "rules": [
                _validate_filter_rule(index, rule, filter_name, config_path)
                for index, rule in enumerate(rules, start=1)
            ],
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
        _validate_patterns(patterns, str(index), config_path)
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

    def write_config(stream):
        json.dump(updated_config, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    atomic_write(config_path, write_config, encoding="utf-8", newline="\n")
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
