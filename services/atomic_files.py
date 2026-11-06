import tempfile
from pathlib import Path


def atomic_write(path, write, mode="w", **open_options):
    """Écrit via un fichier temporaire voisin puis remplace `path` atomiquement."""
    path = Path(path)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode=mode,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
            **open_options,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            write(temporary_file)
        temporary_path.replace(path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return path
