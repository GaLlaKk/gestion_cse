import base64
import json
import platform
from hashlib import sha256
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from services.atomic_files import atomic_write
from services.paths import project_root

SWILE_API_CONFIG_PATH = project_root() / "swile_api.config.json"
_SWILE_API_KEY_PREFIX = b"GestionCSE::SwileApi::Credentials::v1"
_ALLOWED_CONFIG_KEYS = {
    "client_id",
    "client_secret_encrypted",
    "subscribed_product_ids",
}


def _build_fernet():
    """Construit la clé de chiffrement locale utilisée pour le secret Swile."""
    machine_anchor = f"{platform.node()}::{Path.home()}".encode("utf-8")
    key_material = sha256(_SWILE_API_KEY_PREFIX + machine_anchor).digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def _encrypt_secret(secret):
    """Chiffre le secret client Swile pour stockage local."""
    return _build_fernet().encrypt(secret.encode("utf-8")).decode("utf-8")


def _decrypt_secret(encrypted_secret, config_path):
    """Déchiffre le secret client Swile stocké localement."""
    try:
        return _build_fernet().decrypt(
            encrypted_secret.encode("utf-8")
        ).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as error:
        raise ValueError(
            "Impossible de déchiffrer le secret Swile stocké "
            f"dans {config_path}. Reconfigurez l’authentification."
        ) from error


def _load_raw_swile_api_config(config_path):
    """Lit et valide le JSON de configuration Swile API."""
    if not config_path.exists():
        return {}
    try:
        with config_path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Configuration Swile API invalide ({config_path}) : {error}"
        ) from error
    if not isinstance(config, dict):
        raise ValueError(
            f"La configuration Swile API doit être un objet JSON : {config_path}"
        )
    unknown_keys = config.keys() - _ALLOWED_CONFIG_KEYS
    if unknown_keys:
        raise ValueError(
            "Clé(s) inconnue(s) dans la configuration Swile API "
            f"{config_path} : {sorted(unknown_keys)}"
        )
    return config


def _normalize_product_ids(product_ids):
    """Nettoie, déduplique et ordonne les identifiants produits Swile."""
    if product_ids is None:
        return []
    if not isinstance(product_ids, list):
        raise ValueError("'subscribed_product_ids' doit être une liste.")
    normalized_ids = []
    seen = set()
    for product_id in product_ids:
        if not isinstance(product_id, str):
            raise ValueError(
                "Chaque identifiant produit Swile doit être une chaîne."
            )
        normalized = product_id.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        normalized_ids.append(normalized)
    return normalized_ids


def load_swile_api_credentials(config_path=None):
    """Charge les identifiants Swile API depuis le fichier de configuration."""
    settings = load_swile_api_settings(config_path)
    return {
        "client_id": settings["client_id"],
        "client_secret": settings["client_secret"],
    }


def load_swile_api_subscribed_product_ids(config_path=None):
    """Charge la liste locale des produits Swile à abonner par défaut."""
    settings = load_swile_api_settings(config_path)
    return settings["subscribed_product_ids"]


def load_swile_api_settings(config_path=None):
    """Charge les identifiants et produits Swile API depuis la configuration."""
    config_path = Path(config_path or SWILE_API_CONFIG_PATH)
    config = _load_raw_swile_api_config(config_path)

    raw_client_id = config.get("client_id")
    client_id = "" if raw_client_id is None else raw_client_id
    encrypted_secret = config.get("client_secret_encrypted")
    if not isinstance(client_id, str):
        raise ValueError(
            f"'client_id' doit être une chaîne dans {config_path}."
        )
    client_id = client_id.strip()
    subscribed_product_ids = _normalize_product_ids(
        config.get("subscribed_product_ids")
    )
    if not isinstance(encrypted_secret, str) or not encrypted_secret.strip():
        return {
            "client_id": client_id,
            "client_secret": "",
            "subscribed_product_ids": subscribed_product_ids,
        }
    client_secret = _decrypt_secret(encrypted_secret, config_path)
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "subscribed_product_ids": subscribed_product_ids,
    }


def save_swile_api_credentials(client_id, client_secret, config_path=None):
    """Enregistre les identifiants Swile API (secret chiffré)."""
    config_path = Path(config_path or SWILE_API_CONFIG_PATH)
    existing = _load_raw_swile_api_config(config_path)
    normalized_client_id = (client_id or "").strip()
    normalized_secret = (client_secret or "").strip()
    if not normalized_client_id:
        raise ValueError("Le client_id Swile est requis.")
    if not normalized_secret:
        raise ValueError("Le client_secret Swile est requis.")

    config = {
        "client_id": normalized_client_id,
        "client_secret_encrypted": _encrypt_secret(normalized_secret),
        "subscribed_product_ids": _normalize_product_ids(
            existing.get("subscribed_product_ids")
        ),
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)

    def write_config(stream):
        json.dump(config, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    atomic_write(config_path, write_config, encoding="utf-8", newline="\n")
    return config_path


def save_swile_api_subscribed_product_ids(product_ids, config_path=None):
    """Enregistre les produits Swile à abonner par défaut."""
    config_path = Path(config_path or SWILE_API_CONFIG_PATH)
    existing = _load_raw_swile_api_config(config_path)
    existing_client_id = existing.get("client_id")
    if existing_client_id is None:
        normalized_client_id = ""
    elif isinstance(existing_client_id, str):
        normalized_client_id = existing_client_id.strip()
    else:
        raise ValueError(
            f"'client_id' doit être une chaîne dans {config_path}."
        )
    config = {
        "client_id": normalized_client_id,
        "client_secret_encrypted": existing.get("client_secret_encrypted"),
        "subscribed_product_ids": _normalize_product_ids(product_ids),
    }
    if not isinstance(config["client_secret_encrypted"], str):
        config.pop("client_secret_encrypted")
    config_path.parent.mkdir(parents=True, exist_ok=True)

    def write_config(stream):
        json.dump(config, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    atomic_write(config_path, write_config, encoding="utf-8", newline="\n")
    return config_path

