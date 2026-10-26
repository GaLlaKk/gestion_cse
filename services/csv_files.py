import csv
from pathlib import Path

DEFAULT_TEMPLATE_FILE = (
    "collaborators_template_090d2568-c182-4cf4-8b3a-81fefee3a297.csv"
)


def latest_input_file(input_directory, pattern, description):
    candidates = list(input_directory.glob(pattern))
    if pattern == "collaborators*.csv":
        candidates = [
            path
            for path in candidates
            if not path.stem.startswith("collaborators-additions")
            and not path.stem.endswith(("-trouves", "-non-trouves"))
            and path.name != DEFAULT_TEMPLATE_FILE
        ]
    if not candidates:
        raise FileNotFoundError(
            f"Aucun fichier {description} trouvé dans {input_directory}."
        )
    return max(candidates, key=lambda path: path.stat().st_mtime)


def read_csv(path, delimiter, required_columns):
    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=delimiter)
        fieldnames = reader.fieldnames
        if fieldnames is None:
            raise ValueError(f"Le fichier est vide ou sans en-tête : {path}")

        missing_columns = set(required_columns) - set(fieldnames)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ValueError(f"Colonne(s) manquante(s) dans {path} : {missing}")

        rows = [row for row in reader if row]

    return fieldnames, rows
