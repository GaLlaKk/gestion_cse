import json
from pathlib import Path

from domain.normalization import active_directory_keys
from services.ad_progress import PROGRESS_EXPORT_COLUMNS
from services.atomic_files import atomic_write
from services.csv_files import read_csv

EXPORT_KEY_TYPES = ("email", "matricule", "name")


def new_key_index():
    """Crée l’index vide des clés métier des lignes déjà exportées."""
    return {key_type: set() for key_type in EXPORT_KEY_TYPES}


def add_exported_keys(keys_by_type, row):
    """Ajoute les clés d’identification d’une ligne déjà exportée."""
    for key_type, key in active_directory_keys(row).items():
        if key:
            keys_by_type[key_type].add(key)


def has_exported_key(keys_by_type, row):
    """Indique si une ligne est déjà présente selon ses clés métier."""
    return any(
        key and key in keys_by_type[key_type]
        for key_type, key in active_directory_keys(row).items()
    )


class ExportState:
    """État mutable de la collecte, sérialisable pour une reprise."""

    def __init__(self, start_user_email):
        self.pending = [(start_user_email, True, 0)]
        self.processed_ids = set()
        self.exported_count = 0
        self.keys_by_type = new_key_index()
        self.temporary_path = None

    def to_resume_dict(self):
        """Représente l’état dans le format JSON de reprise."""
        return {
            "temporary_csv_path": str(self.temporary_path),
            "pending": [
                {
                    "user_id_or_email": user_id_or_email,
                    "is_root": is_root,
                    "intermediate_levels": intermediate_levels,
                }
                for user_id_or_email, is_root, intermediate_levels in self.pending
            ],
            "processed_ids": sorted(self.processed_ids),
            "exported_count": self.exported_count,
        }


def save_resume_state(resume_state_path, state):
    """Enregistre atomiquement l'etat de reprise de l'export AD."""
    atomic_write(
        resume_state_path,
        lambda stream: json.dump(state, stream),
        encoding="utf-8",
    )


def load_resume_state(resume_state_path, logger):
    """Charge l'etat de reprise s'il est present et valide."""
    if not resume_state_path.is_file():
        return None
    try:
        with resume_state_path.open(encoding="utf-8") as state_file:
            state = json.load(state_file)
        if not isinstance(state, dict):
            raise ValueError("format d'etat invalide")
        required_keys = {
            "temporary_csv_path",
            "pending",
            "processed_ids",
            "exported_count",
        }
        missing_keys = required_keys - set(state.keys())
        if missing_keys:
            raise ValueError(
                "cles manquantes: " + ", ".join(sorted(missing_keys))
            )
        return state
    except (OSError, ValueError, json.JSONDecodeError) as error:
        logger.warning(
            "Etat de reprise ignore car invalide (%s): %s",
            resume_state_path,
            error,
        )
        return None


def restore_resume_state(resume_state_path, state, logger):
    """Recharge un export interrompu dans `state`; retourne True si la reprise a eu lieu."""
    resume_state = load_resume_state(resume_state_path, logger)
    if resume_state is None:
        return False
    candidate_path = Path(resume_state["temporary_csv_path"])
    try:
        _, resumed_rows = read_csv(
            candidate_path,
            ",",
            PROGRESS_EXPORT_COLUMNS,
        )
        pending = [
            (
                item["user_id_or_email"],
                item["is_root"],
                item["intermediate_levels"],
            )
            for item in resume_state["pending"]
        ]
        processed_ids = set(resume_state["processed_ids"])
    except (KeyError, TypeError, ValueError, OSError, UnicodeError) as error:
        logger.warning(
            "Reprise impossible avec l'etat enregistre (%s) : %s. "
            "Un nouvel export complet sera lance.",
            candidate_path,
            error,
        )
        resume_state_path.unlink(missing_ok=True)
        return False

    state.pending = pending
    state.processed_ids = processed_ids
    for resumed_row in resumed_rows:
        add_exported_keys(state.keys_by_type, resumed_row)
    state.exported_count = len(resumed_rows)
    state.temporary_path = candidate_path
    logger.info(
        "Reprise d'un export interrompu : %s ligne(s) deja ecrite(s), "
        "%s compte(s) en attente.",
        state.exported_count,
        len(pending),
    )
    return True
