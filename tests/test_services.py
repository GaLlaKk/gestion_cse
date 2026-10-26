import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from services import active_directory_export
from services.csv_files import latest_input_file, read_csv
from services.swile_service import compare_users, generate_additions


class ActiveDirectoryExportTests(unittest.TestCase):
    def test_photo_is_downloaded_once_and_reused_from_cache(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo_directory = Path(temporary_directory) / "photos"
            response = Mock(status_code=200, content=b"photo-bytes")
            response.raise_for_status.return_value = None
            request_graph = Mock(return_value=response)

            photo_path = active_directory_export._download_user_photo(
                "user-id", "jdupont", photo_directory, request_graph
            )
            cached_path = active_directory_export._download_user_photo(
                "user-id", "jdupont", photo_directory, request_graph
            )

            self.assertEqual(
                photo_path, photo_directory / "jdupont_user-id.jpg"
            )
            self.assertEqual(cached_path, photo_path)
            self.assertEqual(photo_path.read_bytes(), b"photo-bytes")
            request_graph.assert_called_once_with(
                "https://graph.microsoft.com/v1.0/users/user-id/photo/$value"
            )

    def test_missing_photo_is_not_written(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo_directory = Path(temporary_directory) / "photos"
            response = Mock(status_code=404)
            request_graph = Mock(return_value=response)

            photo_path = active_directory_export._download_user_photo(
                "user-id", "jdupont", photo_directory, request_graph
            )

            self.assertIsNone(photo_path)
            self.assertFalse(photo_directory.exists())
            request_graph.assert_called_once()

    def test_photo_filename_sanitizes_windows_path_characters(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo_directory = Path(temporary_directory) / "photos"
            response = Mock(status_code=200, content=b"photo-bytes")
            response.raise_for_status.return_value = None
            request_graph = Mock(return_value=response)

            photo_path = active_directory_export._download_user_photo(
                "user-id",
                "user/name",
                photo_directory,
                request_graph,
            )

            self.assertEqual(photo_path.name, "user_name_user-id.jpg")

    def test_device_code_is_forwarded_to_callback(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            config_path.write_text(
                (
                    '{"start_user_email":"start@example.com",'
                    '"client_id":"client-id","authority":"authority",'
                    '"report_domain":"example.com","scopes":["scope"]}'
                ),
                encoding="utf-8",
            )
            flow = {
                "user_code": "ABCD1234",
                "verification_uri": "https://login.microsoft.com/device",
                "message": "Sign in with code ABCD1234",
            }
            callback = Mock()
            client = Mock()
            client.initiate_device_flow.return_value = flow
            client.acquire_token_by_device_flow.return_value = {
                "error_description": "Authentication did not complete."
            }

            with (
                patch.object(
                    active_directory_export,
                    "get_config_path",
                    return_value=config_path,
                ),
                patch.object(
                    active_directory_export,
                    "initialize_output",
                    return_value=(Mock(), Path(temporary_directory), "20260101"),
                ),
                patch.object(
                    active_directory_export,
                    "PublicClientApplication",
                    return_value=client,
                ),
            ):
                with self.assertRaisesRegex(
                    Exception, "Authentication did not complete"
                ):
                    active_directory_export.run_active_directory_export(
                        on_device_code=callback
                    )

            callback.assert_called_once_with(
                "https://login.microsoft.com/device", "ABCD1234"
            )
            client.acquire_token_by_device_flow.assert_called_once_with(flow)


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
