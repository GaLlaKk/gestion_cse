import os
import tempfile
import unittest
from pathlib import Path

from services.csv_files import (
    latest_input_file,
    latest_valid_csv_in_directories,
    read_csv,
)


class CsvFilesTests(unittest.TestCase):
    def test_read_csv_accepts_utf8_bom_and_checks_required_columns(self):
        """Vérifie la lecture d’un CSV UTF-8 BOM et le contrôle des colonnes."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "swile.csv"
            path.write_text(
                "\ufeffPrénom;Email\nAlice;alice@example.com\n",
                encoding="utf-8",
            )

            columns, rows = read_csv(path, ";", {"Prénom", "Email"})

            self.assertEqual(columns, ["Prénom", "Email"])
            self.assertEqual(rows[0]["Prénom"], "Alice")
            with self.assertRaisesRegex(ValueError, "Nom"):
                read_csv(path, ";", {"Nom"})

    def test_latest_input_skips_template_and_generated_results(self):
        """Vérifie la sélection d’entrée sans modèle ni résultat généré."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            valid_files = (
                "collaborators-old.csv",
                "collaborators-new.csv",
                "collaborators-new-trouves.csv",
                "collaborators-disable-20261026t120000.csv",
                "collaborators-additions-20261026.csv",
                "collaborators_template_090d2568-c182-4cf4-8b3a-81fefee3a297.csv",
            )
            for timestamp, name in enumerate(valid_files, start=1):
                path = directory / name
                path.touch()
                os.utime(path, (timestamp, timestamp))

            selected = latest_input_file(directory, "collaborators*.csv", "Swile")

            self.assertEqual(selected.name, "collaborators-new.csv")

    def test_latest_valid_csv_is_selected_across_input_and_output_folders(self):
        """Sélectionne le dernier export valide parmi les dossiers fournis."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            input_directory = root / "in"
            output_directory = root / "out"
            input_directory.mkdir()
            output_directory.mkdir()
            required_columns = ["Nom", "Email", "Identifiant", "Poste"]
            old_path = input_directory / "export-manuel.csv"
            old_path.write_text(
                "Nom,Email,Identifiant,Poste\n"
                "Ancien,ancien@example.com,ancien,Analyste\n",
                encoding="utf-8",
            )
            latest_path = output_directory / "20261104_export.csv"
            latest_path.write_text(
                "Nom,Email,Identifiant,Poste\n"
                "Récent,recent@example.com,recent,Analyste\n",
                encoding="utf-8",
            )
            invalid_path = output_directory / "export-invalide.csv"
            invalid_path.write_text("Nom,Email\nInvalide,x@example.com\n")
            os.utime(old_path, (1_700_000_000, 1_700_000_000))
            os.utime(latest_path, (1_700_000_100, 1_700_000_100))
            os.utime(invalid_path, (1_700_000_200, 1_700_000_200))

            selected = latest_valid_csv_in_directories(
                (input_directory, output_directory),
                ",",
                required_columns,
            )

            self.assertEqual(selected, latest_path)

            os.utime(old_path, (1_700_000_300, 1_700_000_300))
            selected = latest_valid_csv_in_directories(
                (input_directory, output_directory),
                ",",
                required_columns,
            )
            self.assertEqual(selected, old_path)
