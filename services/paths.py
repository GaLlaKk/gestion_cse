import sys
from pathlib import Path


def project_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def bundled_resource(*parts):
    bundle_directory = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])
    )
    return bundle_directory.joinpath(*parts)
