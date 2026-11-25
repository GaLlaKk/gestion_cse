import json
from pathlib import Path

from services.atomic_files import atomic_write
from services.paths import project_root

EKIE_CONFIG_PATH = project_root() / "ekie.config.json"


def _normalize_member_email(email):
    """Normalise une adresse e-mail de membre CSE."""
    if not isinstance(email, str) or not email.strip():
        raise ValueError(
            "Chaque e-mail de membre CSE doit être une chaîne non vide."
        )
    normalized = email.strip().casefold()
    if "@" not in normalized:
        raise ValueError(
            f"Adresse e-mail de membre CSE invalide : {email!r}."
        )
    return normalized


def _validate_config(config, config_path):
    """Valide la structure de configuration Ekie."""
    if not isinstance(config, dict):
        raise ValueError(
            f"La configuration Ekie doit être un objet JSON : {config_path}"
        )
    unknown_keys = config.keys() - {"cse_member_emails"}
    if unknown_keys:
        raise ValueError(
            "Clé(s) inconnue(s) dans la configuration Ekie "
            f"{config_path} : {sorted(unknown_keys)}"
        )
    emails = config.get("cse_member_emails", [])
    if not isinstance(emails, list):
        raise ValueError(
            "'cse_member_emails' doit être une liste dans la configuration "
            f"Ekie : {config_path}"
        )

    normalized = []
    seen = set()
    for email in emails:
        normalized_email = _normalize_member_email(email)
        if normalized_email in seen:
            continue
        seen.add(normalized_email)
        normalized.append(normalized_email)
    return {"cse_member_emails": normalized}


def load_ekie_config(config_path=None):
    """Charge la configuration Ekie ou retourne une liste vide par défaut."""
    config_path = Path(config_path or EKIE_CONFIG_PATH)
    if not config_path.exists():
        return {"cse_member_emails": []}
    try:
        with config_path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Configuration Ekie invalide ({config_path}) : {error}"
        ) from error
    return _validate_config(config, config_path)


def load_cse_member_emails(config_path=None):
    """Retourne l’ensemble des e-mails CSE normalisés pour l’export Ekie."""
    return set(load_ekie_config(config_path)["cse_member_emails"])


def save_ekie_config(config, config_path=None):
    """Enregistre atomiquement la configuration Ekie validée."""
    config_path = Path(config_path or EKIE_CONFIG_PATH)
    normalized_config = _validate_config(config, config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    def write_config(stream):
        json.dump(normalized_config, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    atomic_write(config_path, write_config, encoding="utf-8", newline="\n")
    return config_path

