import csv
import os
import tempfile
import unittest
from pathlib import Path

from services.csv_files import latest_input_file, read_csv
from services.swile_service import compare_users, generate_additions


class CsvFilesTests(unittest.TestCase):
    def test_read_csv_accepts_utf8_bom_and_checks_required_columns(self):
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
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            valid_files = (
                "collaborators-old.csv",
                "collaborators-new.csv",
                "collaborators-new-trouves.csv",
                "collaborators-additions-20261026.csv",
                "collaborators_template_090d2568-c182-4cf4-8b3a-81fefee3a297.csv",
            )
            for timestamp, name in enumerate(valid_files, start=1):
                path = directory / name
                path.touch()
                os.utime(path, (timestamp, timestamp))

            selected = latest_input_file(directory, "collaborators*.csv", "Swile")

            self.assertEqual(selected.name, "collaborators-new.csv")


class SwileServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.input_directory = self.root / "in"
        self.output_directory = self.root / "out"
        self.input_directory.mkdir()
        self.swile_path = self._write_csv(
            "swile.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [
                {
                    "Prénom": "Ana",
                    "Nom": "Doe",
                    "Email": "ana@epsilon-france.com",
                    "Matricule": "a1",
                },
                {
                    "Prénom": "Zoé",
                    "Nom": "Absent",
                    "Email": "zoe@example.net",
                    "Matricule": "z9",
                },
            ],
            ";",
        )
        self.active_directory_path = self._write_csv(
            "active-directory.csv",
            ["Nom", "Email", "Identifiant", "Poste"],
            [
                {
                    "Nom": "Ana Doe",
                    "Email": "ana@epsilon-france.com",
                    "Identifiant": "a1",
                    "Poste": "Analyste",
                },
                {
                    "Nom": "Jean Nouveau",
                    "Email": "jean@epsilon-france.com",
                    "Identifiant": "J-2",
                    "Poste": "Analyste",
                },
            ],
            ",",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _write_csv(self, name, fieldnames, rows, delimiter):
        path = self.input_directory / name
        with path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=fieldnames, delimiter=delimiter
            )
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_compare_users_writes_found_and_missing_csvs(self):
        found_path, missing_path, found_count, missing_count = compare_users(
            self.swile_path,
            self.active_directory_path,
            self.output_directory,
        )

        self.assertEqual((found_count, missing_count), (1, 1))
        with found_path.open(encoding="utf-8-sig", newline="") as stream:
            found_rows = list(csv.DictReader(stream, delimiter=";"))
        with missing_path.open(encoding="utf-8-sig", newline="") as stream:
            missing_rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(found_rows[0]["Email"], "ana@epsilon-france.com")
        self.assertEqual(missing_rows[0]["Email"], "zoe@example.net")

    def test_generate_additions_preserves_original_identifier(self):
        template_path = self._write_csv(
            "template.csv", ["Prénom", "Nom", "Email", "Matricule"], [], ";"
        )
        output_path = self.output_directory / "collaborators-additions-test.csv"

        result = generate_additions(
            self.swile_path,
            self.active_directory_path,
            template_path,
            output_path,
            "epsilon-france.com",
        )

        self.assertEqual(result[0], 1)
        self.assertEqual(result[2], 0)
        self.assertTrue(result[1].exists())
        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(rows[0]["Matricule"], "J-2")


if __name__ == "__main__":
    unittest.main()
