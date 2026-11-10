import logging
from pathlib import Path

from services.csv_files import read_csv

LOGGER_NAME = "services.active_directory_export"
DEFAULT_ESTIMATED_PEOPLE = 500
PROGRESS_EXPORT_COLUMNS = {"Nom", "Email", "Identifiant", "Poste"}


def estimate_previous_export_count(output_dir):
    """Estime le volume de la collecte d’après le dernier export valide."""
    logger = logging.getLogger(LOGGER_NAME)
    previous_exports = sorted(
        Path(output_dir).glob("*_liste_salarie_active_directory.csv"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for previous_export in previous_exports:
        try:
            _, rows = read_csv(
                previous_export,
                ",",
                PROGRESS_EXPORT_COLUMNS,
            )
        except (OSError, UnicodeError, ValueError) as error:
            logger.warning(
                "Impossible d’utiliser %s pour estimer la progression : %s",
                previous_export,
                error,
            )
            continue
        if rows:
            return len(rows)
    logger.info(
        "Aucun export précédent exploitable pour l’estimation; "
        "utilisation de la valeur par défaut de %s personnes.",
        DEFAULT_ESTIMATED_PEOPLE,
    )
    return DEFAULT_ESTIMATED_PEOPLE


def next_progress_estimate(current_estimate, completed_count):
    """Augmente la cible de progression lorsqu’elle est atteinte."""
    if completed_count < current_estimate:
        return current_estimate
    return completed_count + max(100, current_estimate // 2)
