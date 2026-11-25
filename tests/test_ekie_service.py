import csv
import tempfile
import unittest
from pathlib import Path

from openpyxl import load_workbook

from services.ekie_service import (
    execute_ekie_export,
    generate_ekie_employee_list,
)


class EkieServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.active_directory_path = self.root / "active-directory.csv"
        self.output_path = self.root / "out" / "template_import_salariees.xlsx"
        self.config_path = self.root / "ekie.config.json"
        with self.active_directory_path.open(
            "w", newline="", encoding="utf-8-sig"
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["Nom", "Email", "Identifiant", "Poste"],
                delimiter=",",
            )
            writer.writeheader()
            writer.writerows(
                [
                    {
                        "Nom": "Ana Doe",
                        "Email": "ana@epsilon-france.com",
                        "Identifiant": "a1",
                        "Poste": "Analyste",
                    },
                    {
                        "Nom": "Zoé Martin",
                        "Email": "zoe@epsilon-france.com",
                        "Identifiant": "z9",
                        "Poste": "Analyste",
                    },
                ]
            )
        self.config_path.write_text(
            '{"cse_member_emails": ["zoe@epsilon-france.com"]}',
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_generate_ekie_employee_list_creates_expected_xlsx(self):
        generated_path, generated_count = generate_ekie_employee_list(
            self.active_directory_path,
            output_path=self.output_path,
            cse_members_config_path=self.config_path,
        )

        self.assertEqual(generated_path, self.output_path)
        self.assertEqual(generated_count, 2)
        workbook = load_workbook(self.output_path, data_only=True)
        worksheet = workbook.active
        rows = list(worksheet.iter_rows(values_only=True))
        workbook.close()
        self.assertEqual(
            rows[0],
            ("email", "first_name", "last_name", "is_cse_member"),
        )
        self.assertEqual(
            rows[1],
            ("ana@epsilon-france.com", "Ana", "Doe", "FAUX"),
        )
        self.assertEqual(
            rows[2],
            ("zoe@epsilon-france.com", "Zoé", "Martin", "VRAI"),
        )

    def test_execute_ekie_export_returns_summary(self):
        summary = execute_ekie_export(
            self.active_directory_path,
            output_path=self.output_path,
            cse_members_config_path=self.config_path,
        )

        self.assertIn("Lignes exportées pour Ekie : 2", summary)
        self.assertIn("template_import_salariees.xlsx", summary)


if __name__ == "__main__":
    unittest.main()

