from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

PROCESSING_DIRECTORIES = (
    Path("swile_active_directory") / "in",
    Path("swile_active_directory") / "out",
    Path("liste_salarie_active_directory") / "in",
    Path("liste_salarie_active_directory") / "out",
    Path("log"),
)
RETENTION_DAYS = 90


def cleanup_processing_files(root_directory: Path, logger) -> int:
    """Supprime les fichiers de traitement de plus de 90 jours."""
    threshold = datetime.now().timestamp() - timedelta(
        days=RETENTION_DAYS
    ).total_seconds()
    deleted_count = 0

    for relative_directory in PROCESSING_DIRECTORIES:
        directory = root_directory / relative_directory
        if not directory.is_dir():
            continue
        for file_path in directory.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.stat().st_mtime > threshold:
                continue
            file_path.unlink(missing_ok=True)
            deleted_count += 1

    logger.info(
        "Nettoyage RGPD : %s fichier(s) de traitement supprimé(s) (> %s jours).",
        deleted_count,
        RETENTION_DAYS,
    )
    return deleted_count
