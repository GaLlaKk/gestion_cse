import logging

from services.ad_progress import LOGGER_NAME
from services.atomic_files import atomic_write
from services.graph_client import GRAPH_BASE_URL


def download_user_photo(user_id, identifier, photo_directory, request_graph):
    """Télécharge et met en cache la photo Graph d’un utilisateur."""
    logger = logging.getLogger(LOGGER_NAME)
    account_reference = identifier or user_id
    safe_identifier = "".join(
        "_" if character in '<>:"/\\|?*' else character
        for character in (identifier or "inconnu")
    ).rstrip(" .")
    photo_path = photo_directory / f"{safe_identifier}_{user_id}.jpg"
    if photo_path.is_file() and photo_path.stat().st_size > 0:
        logger.info(
            "Photo réutilisée depuis le cache pour le compte %s.",
            account_reference,
        )
        return photo_path

    response = request_graph(
        f"{GRAPH_BASE_URL}/users/{user_id}/photo/$value"
    )
    if response.status_code == 404:
        logger.info(
            "Aucune photo disponible pour le compte %s.",
            account_reference,
        )
        return None
    response.raise_for_status()
    if not response.content:
        raise ValueError(f"La photo de l’utilisateur {user_id} est vide.")

    photo_directory.mkdir(parents=True, exist_ok=True)
    atomic_write(
        photo_path,
        lambda stream: stream.write(response.content),
        mode="wb",
    )
    logger.info("Photo récupérée pour le compte %s.", account_reference)
    return photo_path
