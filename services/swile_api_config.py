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


def load_swile_api_credentials(config_path=None):
    """Charge les identifiants Swile API depuis le fichier de configuration."""
    config_path = Path(config_path or SWILE_API_CONFIG_PATH)
    if not config_path.exists():
        return {"client_id": "", "client_secret": ""}
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
    unknown_keys = config.keys() - {"client_id", "client_secret_encrypted"}
    if unknown_keys:
        raise ValueError(
            "Clé(s) inconnue(s) dans la configuration Swile API "
            f"{config_path} : {sorted(unknown_keys)}"
        )

    client_id = (config.get("client_id") or "").strip()
    encrypted_secret = config.get("client_secret_encrypted")
    if not isinstance(client_id, str):
        raise ValueError(
            f"'client_id' doit être une chaîne dans {config_path}."
        )
    if not isinstance(encrypted_secret, str) or not encrypted_secret.strip():
        return {"client_id": client_id, "client_secret": ""}
    client_secret = _decrypt_secret(encrypted_secret, config_path)
    return {"client_id": client_id, "client_secret": client_secret}


def save_swile_api_credentials(client_id, client_secret, config_path=None):
    """Enregistre les identifiants Swile API (secret chiffré)."""
    config_path = Path(config_path or SWILE_API_CONFIG_PATH)
    normalized_client_id = (client_id or "").strip()
    normalized_secret = (client_secret or "").strip()
    if not normalized_client_id:
        raise ValueError("Le client_id Swile est requis.")
    if not normalized_secret:
        raise ValueError("Le client_secret Swile est requis.")

    config = {
        "client_id": normalized_client_id,
        "client_secret_encrypted": _encrypt_secret(normalized_secret),
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)

    def write_config(stream):
        json.dump(config, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    atomic_write(config_path, write_config, encoding="utf-8", newline="\n")
    return config_path

