import sys
from pathlib import Path


def project_root():
    """Retourne le dossier racine du projet ou celui de l’exécutable gelé."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundled_resource(*parts):
    """Construit le chemin d’une ressource embarquée ou du projet."""
    bundle_directory = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])
    )
    return bundle_directory.joinpath(*parts)
