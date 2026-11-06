import json
from pathlib import Path

from services.atomic_files import atomic_write
from services.paths import project_root


def get_config_path():
    """Retourne le chemin du fichier de configuration Active Directory."""
    return project_root() / "liste_salarie_active_directory.config.json"


DEFAULT_CONFIG = {
    "start_user_email": "prenom.nom@exemple.fr",
    "client_id": "1fec8e78-bce4-4aaf-ab1b-5451cc387264",
    "authority": "https://login.microsoftonline.com/organizations",
    "scopes": ["User.ReadBasic.All"],
    "report_domain": "exemple.fr",
}
EXAMPLE_ONLY_SETTINGS = ("start_user_email", "report_domain")


def apply_config_defaults(config):
    """Complète les paramètres absents ou vides avec les valeurs par défaut."""
    completed = dict(config)
    for name, default in DEFAULT_CONFIG.items():
        value = completed.get(name)
        if value is None or value == "" or value == []:
            completed[name] = list(default) if isinstance(default, list) else default
        elif isinstance(value, str) and not value.strip():
            completed[name] = default
    return completed


def validate_config(config, config_path):
    """Vérifie les champs obligatoires de la configuration Active Directory."""
    if not isinstance(config, dict):
        raise ValueError(
            f"La configuration doit être un objet JSON dans {config_path}."
        )
    config = apply_config_defaults(config)
    for setting_name in EXAMPLE_ONLY_SETTINGS:
        if config[setting_name] == DEFAULT_CONFIG[setting_name]:
            raise ValueError(
                f"Le paramètre '{setting_name}' contient une valeur d’exemple "
                f"à remplacer dans {config_path}."
            )

    required_string_settings = (
        "start_user_email",
        "client_id",
        "authority",
        "report_domain",
    )
    for setting_name in required_string_settings:
        if (
            not isinstance(config.get(setting_name), str)
            or not config[setting_name].strip()
        ):
            raise ValueError(
                f"Le paramètre '{setting_name}' doit être une chaîne non vide "
                f"dans {config_path}."
            )

    scopes = config.get("scopes")
    if not isinstance(scopes, list) or not scopes or not all(
        isinstance(scope, str) and scope.strip() for scope in scopes
    ):
        raise ValueError(
            f"Le paramètre 'scopes' doit être une liste de chaînes non vides "
            f"dans {config_path}."
        )
    return scopes


def save_active_directory_config(contents, config_path=None):
    """Valide puis remplace atomiquement le fichier de configuration AD."""
    config_path = Path(config_path or get_config_path())
    config = json.loads(contents)
    validate_config(config, config_path)

    atomic_write(
        config_path,
        lambda stream: stream.write(contents),
        encoding="utf-8",
    )
    return config_path
