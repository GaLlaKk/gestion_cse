import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from services import active_directory_export
from services.csv_files import (
    latest_input_file,
    latest_valid_csv_in_directories,
    read_csv,
)
from services.swile_service import (
    compare_users,
    generate_additions,
    generate_work_location_values,
    load_work_location_mapping,
    map_work_location_value,
    save_work_location_mapping,
)


class ActiveDirectoryConfigTests(unittest.TestCase):
    def test_save_valid_config_atomically_replaces_file(self):
        """Vérifie la sauvegarde et le remplacement atomique d’une configuration valide."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            config_path.write_text("ancienne configuration", encoding="utf-8")
            contents = (
                '{\n  "start_user_email": "user@example.com",\n'
                '  "client_id": "client-id",\n'
                '  "authority": "authority",\n'
                '  "report_domain": "example.com",\n'
                '  "scopes": ["scope"]\n}'
            )

            result_path = active_directory_export.save_active_directory_config(
                contents, config_path
            )

            self.assertEqual(result_path, config_path)
            self.assertEqual(config_path.read_text(encoding="utf-8"), contents)
            self.assertEqual(list(config_path.parent.glob("*.tmp")), [])
            self.assertEqual(
                active_directory_export.validate_config(
                    json.loads(contents), config_path
                ),
                ["scope"],
            )

    def test_invalid_config_does_not_replace_existing_file(self):
        """Vérifie qu’une configuration invalide ne remplace pas le fichier existant."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            original_contents = "configuration existante"
            config_path.write_text(original_contents, encoding="utf-8")

            with self.assertRaises(ValueError):
                active_directory_export.save_active_directory_config(
                    "{invalid json", config_path
                )

            self.assertEqual(
                config_path.read_text(encoding="utf-8"), original_contents
            )
            self.assertEqual(list(config_path.parent.glob("*.tmp")), [])

    def test_config_validation_rejects_missing_required_setting(self):
        """Vérifie le rejet d’un paramètre obligatoire absent."""
        config = {
            "start_user_email": "user@example.com",
            "client_id": "client-id",
            "authority": "authority",
            "report_domain": "example.com",
            "scopes": ["scope"],
        }
        del config["client_id"]

        with self.assertRaisesRegex(ValueError, "client_id"):
            active_directory_export.validate_config(config, "config.json")


class ActiveDirectoryExportTests(unittest.TestCase):
    def test_progress_estimate_uses_previous_export_volume(self):
        """Vérifie que l’estimation reprend le volume du dernier export."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            output_directory = Path(temporary_directory)
            export_path = (
                output_directory / "20261028_liste_salarie_active_directory.csv"
            )
            with export_path.open(
                "w", newline="", encoding="utf-8"
            ) as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["Nom", "Email", "Identifiant", "Poste"],
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "Nom": f"User {index}",
                            "Email": f"user{index}@example.com",
                            "Identifiant": f"user{index}",
                            "Poste": "Analyste",
                        }
                        for index in range(3)
                    ]
                )

            self.assertEqual(
                active_directory_export.estimate_previous_export_count(
                    output_directory
                ),
                3,
            )

    def test_progress_estimate_defaults_and_grows_when_surpassed(self):
        """Vérifie la cible par défaut et son augmentation en cas de dépassement."""
        self.assertEqual(
            active_directory_export.estimate_previous_export_count(
                Path("dossier-inexistant")
            ),
            500,
        )
        self.assertEqual(
            active_directory_export.next_progress_estimate(500, 500),
            750,
        )
        self.assertEqual(
            active_directory_export.next_progress_estimate(500, 120),
            500,
        )

    def test_log_is_rotated_for_each_export_run(self):
        """Vérifie que chaque exécution écrit dans un nouveau journal."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "config.json"
            first_logger, _, _ = active_directory_export.initialize_output(
                config_path
            )
            first_logger.info("Action du premier lancement.")
            log_directory = Path(temporary_directory) / "log"
            first_log = next(log_directory.glob("*.log"))

            second_logger, _, _ = active_directory_export.initialize_output(
                config_path
            )
            try:
                second_logger.info("Action du second lancement.")
                logs = list(log_directory.glob("*.log"))
                second_log = next(path for path in logs if path != first_log)
                first_content = first_log.read_text(encoding="utf-8")
                second_content = second_log.read_text(encoding="utf-8")

                self.assertIn("Action du premier lancement.", first_content)
                self.assertNotIn("Action du second lancement.", first_content)
                self.assertIn("Action du second lancement.", second_content)
            finally:
                for handler in second_logger.handlers[:]:
                    second_logger.removeHandler(handler)
                    handler.close()

    def test_photo_is_downloaded_once_and_reused_from_cache(self):
        """Vérifie le téléchargement initial et la réutilisation de la photo en cache."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo_directory = Path(temporary_directory) / "photos"
            response = Mock(status_code=200, content=b"photo-bytes")
            response.raise_for_status.return_value = None
            request_graph = Mock(return_value=response)

            with self.assertLogs(
                "services.active_directory_export", level="INFO"
            ) as captured_logs:
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
            self.assertIn(
                "Photo récupérée pour le compte jdupont.",
                captured_logs.output[0],
            )
            self.assertIn(
                "Photo réutilisée depuis le cache pour le compte jdupont.",
                captured_logs.output[1],
            )
            request_graph.assert_called_once_with(
                "https://graph.microsoft.com/v1.0/users/user-id/photo/$value"
            )

    def test_missing_photo_is_not_written(self):
        """Vérifie qu’une réponse Graph 404 ne crée pas de fichier photo."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            photo_directory = Path(temporary_directory) / "photos"
            response = Mock(status_code=404)
            request_graph = Mock(return_value=response)

            with self.assertLogs(
                "services.active_directory_export", level="INFO"
            ) as captured_logs:
                photo_path = active_directory_export._download_user_photo(
                    "user-id", "jdupont", photo_directory, request_graph
                )

            self.assertIsNone(photo_path)
            self.assertFalse(photo_directory.exists())
            self.assertIn(
                "Aucune photo disponible pour le compte jdupont.",
                captured_logs.output[0],
            )
            request_graph.assert_called_once()

    def test_photo_filename_sanitizes_windows_path_characters(self):
        """Vérifie la suppression des caractères interdits dans le nom de photo."""
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
        """Vérifie que l’URL et le code d’appareil sont transmis au callback."""
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
            logger = Mock()
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
                    return_value=(logger, Path(temporary_directory), "20260101"),
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
            logger.error.assert_any_call("L’authentification Microsoft a échoué.")
            logger.exception.assert_any_call(
                "Échec de l’authentification Microsoft."
            )

    def test_export_writes_rows_to_temporary_csv_before_publishing(self):
        """Vérifie l’écriture temporaire des lignes avant publication du CSV."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "config.json"
            config_path.write_text(
                (
                    '{"start_user_email":"start@example.com",'
                    '"client_id":"client-id","authority":"authority",'
                    '"report_domain":"example.com","scopes":["scope"]}'
                ),
                encoding="utf-8",
            )
            output_directory = root / "out"
            output_directory.mkdir()
            final_path = (
                output_directory / "20261028_liste_salarie_active_directory.csv"
            )
            flow = {"user_code": "ABCD1234", "message": "Sign in"}
            client = Mock()
            client.initiate_device_flow.return_value = flow
            client.acquire_token_by_device_flow.return_value = {
                "access_token": "token"
            }
            logger = Mock()
            progress_updates = []

            def graph_response(status_code=200, payload=None):
                """Construit une réponse Graph simulée pour le scénario."""
                response = Mock(status_code=status_code)
                response.json.return_value = payload
                response.raise_for_status.return_value = None
                return response

            def request_graph(url, **_kwargs):
                """Fournit les réponses Graph attendues par la collecte simulée."""
                if "/users/start@example.com?" in url:
                    return graph_response(
                        payload={
                            "id": "root-id",
                            "displayName": "Start User",
                            "mail": "start@example.com",
                            "userPrincipalName": "start@example.com",
                            "jobTitle": "Analyste",
                            "officeLocation": "Paris",
                            "department": "Services",
                        }
                    )
                if "/users/root-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/root-id/directReports" in url:
                    self.assertFalse(final_path.exists())
                    self.assertEqual(
                        len(list(output_directory.glob("*.tmp"))), 1
                    )
                    return graph_response(payload={"value": []})
                self.fail(f"URL Graph inattendue : {url}")

            with (
                patch.object(
                    active_directory_export,
                    "get_config_path",
                    return_value=config_path,
                ),
                patch.object(
                    active_directory_export,
                    "initialize_output",
                    return_value=(logger, output_directory, "20261028"),
                ),
                patch.object(
                    active_directory_export,
                    "PublicClientApplication",
                    return_value=client,
                ),
                patch.object(
                    active_directory_export.requests,
                    "get",
                    side_effect=request_graph,
                ),
            ):
                result_path = active_directory_export.run_active_directory_export(
                    on_progress=lambda completed, estimate, phase: (
                        progress_updates.append((completed, estimate, phase))
                    )
                )

            self.assertEqual(result_path, final_path)
            logger.info.assert_any_call(
                "Compte Active Directory examiné : %s.",
                "start@example.com",
            )
            with final_path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Email"], "start@example.com")
            self.assertEqual(rows[0]["Lieu de travail"], "Paris")
            self.assertEqual(list(output_directory.glob("*.tmp")), [])
            self.assertEqual(
                progress_updates,
                [
                    (0, 500, "connecting"),
                    (0, 500, "collecting"),
                    (1, 500, "collecting"),
                    (1, 1, "complete"),
                ],
            )

    def test_export_resumes_after_connection_error(self):
        """Vérifie la reprise automatique après une coupure réseau pendant la collecte."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "config.json"
            config_path.write_text(
                (
                    '{"start_user_email":"start@example.com",'
                    '"client_id":"client-id","authority":"authority",'
                    '"report_domain":"example.com","scopes":["scope"]}'
                ),
                encoding="utf-8",
            )
            output_directory = root / "out"
            output_directory.mkdir()
            final_path = (
                output_directory / "20261028_liste_salarie_active_directory.csv"
            )
            resume_state_path = (
                output_directory / active_directory_export.RESUME_STATE_FILENAME
            )

            flow = {"user_code": "ABCD1234", "message": "Sign in"}
            client = Mock()
            client.initiate_device_flow.return_value = flow
            client.acquire_token_by_device_flow.return_value = {
                "access_token": "token"
            }
            logger = Mock()

            def graph_response(status_code=200, payload=None):
                """Construit une réponse Graph simulée pour le scénario."""
                response = Mock(status_code=status_code)
                response.json.return_value = payload
                response.raise_for_status.return_value = None
                return response

            phase = {"value": "fail"}

            def request_graph(url, **_kwargs):
                """Simule une coupure réseau puis un succès au redémarrage."""
                if "/users/start@example.com?" in url:
                    return graph_response(
                        payload={
                            "id": "root-id",
                            "displayName": "Start User",
                            "mail": "start@example.com",
                            "userPrincipalName": "start@example.com",
                            "jobTitle": "Analyste",
                            "officeLocation": "Paris",
                            "department": "Services",
                        }
                    )
                if "/users/root-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/root-id/directReports" in url:
                    return graph_response(
                        payload={
                            "value": [
                                {
                                    "id": "child-id",
                                    "mail": "child@example.com",
                                    "displayName": "Child User",
                                }
                            ]
                        }
                    )
                if "/users/child-id?" in url:
                    if phase["value"] == "fail":
                        raise requests.ConnectionError(
                            "Remote end closed connection without response"
                        )
                    return graph_response(
                        payload={
                            "id": "child-id",
                            "displayName": "Child User",
                            "mail": "child@example.com",
                            "userPrincipalName": "child@example.com",
                            "jobTitle": "Consultant",
                            "officeLocation": "Lille",
                            "department": "Data",
                        }
                    )
                if "/users/child-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/child-id/directReports" in url:
                    return graph_response(payload={"value": []})
                self.fail(f"URL Graph inattendue : {url}")

            with (
                patch.object(
                    active_directory_export,
                    "get_config_path",
                    return_value=config_path,
                ),
                patch.object(
                    active_directory_export,
                    "initialize_output",
                    return_value=(logger, output_directory, "20261028"),
                ),
                patch.object(
                    active_directory_export,
                    "PublicClientApplication",
                    return_value=client,
                ),
                patch.object(
                    active_directory_export.requests,
                    "get",
                    side_effect=request_graph,
                ),
            ):
                with self.assertRaises(requests.ConnectionError):
                    active_directory_export.run_active_directory_export()

                self.assertTrue(resume_state_path.is_file())
                self.assertEqual(len(list(output_directory.glob("*.tmp"))), 1)

                phase["value"] = "success"
                result_path = active_directory_export.run_active_directory_export()

            self.assertEqual(result_path, final_path)
            self.assertFalse(resume_state_path.exists())
            self.assertEqual(len(list(output_directory.glob("*.tmp"))), 0)
            with final_path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(
                [row["Email"] for row in rows],
                ["start@example.com", "child@example.com"],
            )

    def test_export_appends_visible_users_from_previous_export(self):
        """Vérifie l’ajout des comptes encore visibles absents de l’export."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "config.json"
            config_path.write_text(
                (
                    '{"start_user_email":"start@example.com",'
                    '"client_id":"client-id","authority":"authority",'
                    '"report_domain":"example.com","scopes":["scope"]}'
                ),
                encoding="utf-8",
            )
            output_directory = root / "out"
            output_directory.mkdir()
            previous_export_path = root / "previous.csv"
            with previous_export_path.open(
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
                            "Nom": "Start User",
                            "Email": "start@example.com",
                            "Identifiant": "start",
                            "Poste": "Analyste",
                        },
                        {
                            "Nom": "Legacy User",
                            "Email": "legacy@example.com",
                            "Identifiant": "legacy",
                            "Poste": "Consultant",
                        },
                    ]
                )

            final_path = (
                output_directory / "20261028_liste_salarie_active_directory.csv"
            )
            flow = {"user_code": "ABCD1234", "message": "Sign in"}
            client = Mock()
            client.initiate_device_flow.return_value = flow
            client.acquire_token_by_device_flow.return_value = {
                "access_token": "token"
            }
            logger = Mock()

            def graph_response(status_code=200, payload=None):
                """Construit une réponse Graph simulée pour le scénario."""
                response = Mock(status_code=status_code)
                response.json.return_value = payload
                response.raise_for_status.return_value = None
                return response

            def request_graph(url, **_kwargs):
                """Fournit les réponses Graph prévues pour les utilisateurs."""
                if "/users/start@example.com?" in url:
                    return graph_response(
                        payload={
                            "id": "root-id",
                            "displayName": "Start User",
                            "mail": "start@example.com",
                            "userPrincipalName": "start@example.com",
                            "jobTitle": "Analyste",
                            "officeLocation": "Paris",
                            "department": "Services",
                        }
                    )
                if "/users/root-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/root-id/directReports" in url:
                    return graph_response(payload={"value": []})
                if "/users/legacy@example.com?" in url:
                    return graph_response(
                        payload={
                            "id": "legacy-id",
                            "displayName": "Legacy User",
                            "mail": "legacy@example.com",
                            "userPrincipalName": "legacy@example.com",
                            "jobTitle": "Consultant",
                            "officeLocation": "Lille",
                            "department": "Data",
                        }
                    )
                if "/users/legacy-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/legacy-id/directReports" in url:
                    return graph_response(payload={"value": []})
                self.fail(f"URL Graph inattendue : {url}")

            with (
                patch.object(
                    active_directory_export,
                    "get_config_path",
                    return_value=config_path,
                ),
                patch.object(
                    active_directory_export,
                    "initialize_output",
                    return_value=(logger, output_directory, "20261028"),
                ),
                patch.object(
                    active_directory_export,
                    "PublicClientApplication",
                    return_value=client,
                ),
                patch.object(
                    active_directory_export.requests,
                    "get",
                    side_effect=request_graph,
                ),
            ):
                result_path = active_directory_export.run_active_directory_export(
                    previous_export_path=previous_export_path
                )

            self.assertEqual(result_path, final_path)
            with final_path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                [row["Email"] for row in rows],
                ["start@example.com", "legacy@example.com"],
            )

    def test_export_does_not_append_missing_users_from_previous_export(self):
        """Vérifie que les comptes absents de Graph ne sont pas ajoutés."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "config.json"
            config_path.write_text(
                (
                    '{"start_user_email":"start@example.com",'
                    '"client_id":"client-id","authority":"authority",'
                    '"report_domain":"example.com","scopes":["scope"]}'
                ),
                encoding="utf-8",
            )
            output_directory = root / "out"
            output_directory.mkdir()
            previous_export_path = root / "previous.csv"
            with previous_export_path.open(
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
                            "Nom": "Start User",
                            "Email": "start@example.com",
                            "Identifiant": "start",
                            "Poste": "Analyste",
                        },
                        {
                            "Nom": "Deleted User",
                            "Email": "deleted@example.com",
                            "Identifiant": "deleted",
                            "Poste": "Consultant",
                        },
                    ]
                )

            flow = {"user_code": "ABCD1234", "message": "Sign in"}
            client = Mock()
            client.initiate_device_flow.return_value = flow
            client.acquire_token_by_device_flow.return_value = {
                "access_token": "token"
            }
            logger = Mock()

            def graph_response(status_code=200, payload=None):
                """Construit une réponse Graph simulée pour le scénario."""
                response = Mock(status_code=status_code)
                response.json.return_value = payload
                response.raise_for_status.return_value = None
                return response

            def request_graph(url, **_kwargs):
                """Fournit les réponses Graph prévues, dont le compte absent."""
                if "/users/start@example.com?" in url:
                    return graph_response(
                        payload={
                            "id": "root-id",
                            "displayName": "Start User",
                            "mail": "start@example.com",
                            "userPrincipalName": "start@example.com",
                            "jobTitle": "Analyste",
                            "officeLocation": "Paris",
                            "department": "Services",
                        }
                    )
                if "/users/root-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/root-id/directReports" in url:
                    return graph_response(payload={"value": []})
                if "/users/deleted@example.com?" in url:
                    return graph_response(status_code=404)
                self.fail(f"URL Graph inattendue : {url}")

            with (
                patch.object(
                    active_directory_export,
                    "get_config_path",
                    return_value=config_path,
                ),
                patch.object(
                    active_directory_export,
                    "initialize_output",
                    return_value=(logger, output_directory, "20261028"),
                ),
                patch.object(
                    active_directory_export,
                    "PublicClientApplication",
                    return_value=client,
                ),
                patch.object(
                    active_directory_export.requests,
                    "get",
                    side_effect=request_graph,
                ),
            ):
                result_path = active_directory_export.run_active_directory_export(
                    previous_export_path=previous_export_path
                )

            with result_path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Email"], "start@example.com")


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


class SwileServiceTests(unittest.TestCase):
    def setUp(self):
        """Prépare les CSV de test partagés par les tests du service Swile."""
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
        """Supprime le dossier temporaire créé pour le test."""
        self.temporary_directory.cleanup()

    def _write_csv(self, name, fieldnames, rows, delimiter):
        """Écrit un CSV de test dans le dossier d’entrée temporaire."""
        path = self.input_directory / name
        with path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=fieldnames, delimiter=delimiter
            )
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_work_location_mapping_uses_current_defaults_without_config(self):
        """Vérifie le mapping existant quand le fichier de configuration manque."""
        mapping = load_work_location_mapping(
            self.root / "configuration-absente.json"
        )

        self.assertEqual(
            map_work_location_value(
                "FR Paris 145-151 rue de Courcelles", mapping
            ),
            "Paris 145",
        )
        self.assertEqual(
            map_work_location_value("29 Avenue De La Marne", mapping),
            "Lille 5.9",
        )
        self.assertEqual(
            map_work_location_value("FR Paris 133", mapping), "Paris 133"
        )
        self.assertEqual(map_work_location_value("Bordeaux", mapping), "Autre")

    def test_work_location_mapping_loads_custom_rules(self):
        """Vérifie le chargement des règles personnalisées et leur normalisation."""
        config_path = self.root / "lieux_travail.config.json"
        config_path.write_text(
            json.dumps(
                {
                    "default_value": "Autre site",
                    "rules": [
                        {
                            "patterns": [["avenue", "marne"]],
                            "value": "Nouveau site",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        mapping = load_work_location_mapping(config_path)

        self.assertEqual(
            map_work_location_value("29 AVENUE DE LA MARNE", mapping),
            "Nouveau site",
        )
        self.assertEqual(
            map_work_location_value("Bordeaux", mapping), "Autre site"
        )

    def test_generate_work_location_values_uses_custom_configuration(self):
        """Vérifie que la génération applique le fichier de mapping personnalisé."""
        active_directory_path = self._write_csv(
            "active-directory-custom-locations.csv",
            ["Nom", "Email", "Identifiant", "Lieu de travail"],
            [
                {
                    "Nom": "Ana Doe",
                    "Email": "ana@epsilon-france.com",
                    "Identifiant": "a1",
                    "Lieu de travail": "Bordeaux",
                }
            ],
            ",",
        )
        config_path = self.root / "lieux_travail.config.json"
        config_path.write_text(
            json.dumps(
                {
                    "default_value": "Autre site",
                    "rules": [
                        {
                            "patterns": [["bordeaux"]],
                            "value": "Siège Bordeaux",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        output_path = self.output_directory / "custom-location-values.csv"

        generate_work_location_values(
            self.swile_path,
            active_directory_path,
            output_path,
            "epsilon-france.com",
            config_path,
        )

        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(
            [row["Valeur"] for row in rows],
            ["Siège Bordeaux", "Autre site"],
        )

    def test_work_location_mapping_rejects_invalid_configuration(self):
        """Vérifie qu’une configuration présente mais invalide est signalée."""
        config_path = self.root / "lieux_travail.config.json"
        config_path.write_text('{"default_value": "Autre", "rules": [{}]}')

        with self.assertRaisesRegex(ValueError, "règle 1"):
            load_work_location_mapping(config_path)

    def test_work_location_mapping_is_saved_and_reloaded(self):
        """Vérifie l’enregistrement atomique et le rechargement du mapping."""
        config_path = self.root / "lieux_travail.config.json"
        mapping = {
            "default_value": "Autre site",
            "rules": [
                {
                    "patterns": [["paris", "courcelles"]],
                    "value": "Paris siège",
                }
            ],
        }

        self.assertEqual(
            save_work_location_mapping(mapping, config_path),
            config_path,
        )
        self.assertEqual(load_work_location_mapping(config_path), mapping)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_invalid_work_location_mapping_does_not_replace_file(self):
        """Vérifie qu’un mapping invalide ne modifie pas le fichier enregistré."""
        config_path = self.root / "lieux_travail.config.json"
        config_path.write_text('{"default_value": "Avant"}', encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "rules"):
            save_work_location_mapping(
                {"default_value": "Après", "rules": "invalide"},
                config_path,
            )

        self.assertEqual(
            config_path.read_text(encoding="utf-8"),
            '{"default_value": "Avant"}',
        )

    def test_compare_users_writes_found_and_missing_csvs(self):
        """Vérifie l’écriture des résultats de comparaison dans deux CSV."""
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
        """Vérifie que l’ajout conserve le matricule AD d’origine."""
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

    def test_generate_work_location_values_uses_expected_value_mapping(self):
        """Vérifie les correspondances d’adresses vers les sites Swile."""
        swile_path = self._write_csv(
            "swile-locations.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [
                {
                    "Prénom": "Alice",
                    "Nom": "Martin-Swile",
                    "Email": "alice@epsilon-france.com",
                    "Matricule": "swile_a",
                },
                {
                    "Prénom": "Bob",
                    "Nom": "Durand-Swile",
                    "Email": "bob@epsilon-france.com",
                    "Matricule": "swile_b",
                },
                {
                    "Prénom": "Chloe",
                    "Nom": "Petit-Swile",
                    "Email": "chloe@epsilon-france.com",
                    "Matricule": "swile_c",
                },
                {
                    "Prénom": "Denis",
                    "Nom": "Dupont-Swile",
                    "Email": "denis@epsilon-france.com",
                    "Matricule": "swile_d",
                },
            ],
            ";",
        )
        active_directory_path = self._write_csv(
            "active-directory-locations.csv",
            ["Nom", "Email", "Identifiant", "Lieu de travail"],
            [
                {
                    "Nom": "Alice Martin",
                    "Email": "alice@epsilon-france.com",
                    "Identifiant": "martin_a",
                    "Lieu de travail": "FR Paris 145-151 rue de Courcelles",
                },
                {
                    "Nom": "Bob Durand",
                    "Email": "bob@epsilon-france.com",
                    "Identifiant": "durand_b",
                    "Lieu de travail": "29 Avenue De La Marne",
                },
                {
                    "Nom": "Chloe Petit",
                    "Email": "chloe@epsilon-france.com",
                    "Identifiant": "petit_c",
                    "Lieu de travail": "FR Paris 133",
                },
                {
                    "Nom": "Denis Dupont",
                    "Email": "denis@epsilon-france.com",
                    "Identifiant": "dupont_d",
                    "Lieu de travail": "Bordeaux",
                },
                {
                    "Nom": "Paul Externe",
                    "Email": "paul.ext@epsilon-france.com",
                    "Identifiant": "externe_p",
                    "Lieu de travail": "FR Paris 145-151 rue de Courcelles",
                },
                {
                    "Nom": "NomUnique",
                    "Email": "invalid@epsilon-france.com",
                    "Identifiant": "invalid_i",
                    "Lieu de travail": "FR Paris 145-151 rue de Courcelles",
                },
            ],
            ",",
        )
        output_path = self.output_directory / "attribute-values.csv"

        (
            result_path,
            generated_count,
            missing_work_location_column,
        ) = generate_work_location_values(
            swile_path,
            active_directory_path,
            output_path,
            "epsilon-france.com",
        )

        self.assertEqual(result_path, output_path)
        self.assertEqual(generated_count, 4)
        self.assertFalse(missing_work_location_column)
        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(
            [row["Valeur"] for row in rows],
            ["Paris 145", "Lille 5.9", "Paris 133", "Autre"],
        )
        self.assertEqual(
            [row["Matricule"] for row in rows],
            ["martin_a", "durand_b", "petit_c", "dupont_d"],
        )
        self.assertEqual(rows[0]["Prénom"], "Alice")
        self.assertEqual(rows[0]["Nom de famille"], "Martin-Swile")
        self.assertEqual(rows[0]["E-mail"], "alice@epsilon-france.com")

    def test_generate_work_location_values_handles_missing_column(self):
        """Vérifie la valeur de repli quand le CSV AD n’a pas le lieu."""
        swile_path = self._write_csv(
            "swile-no-location.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [
                {
                    "Prénom": "Alice",
                    "Nom": "Martin-Swile",
                    "Email": "alice@epsilon-france.com",
                    "Matricule": "swile_a",
                },
                {
                    "Prénom": "Bob",
                    "Nom": "Durand-Swile",
                    "Email": "bob@epsilon-france.com",
                    "Matricule": "swile_b",
                },
            ],
            ";",
        )
        active_directory_path = self._write_csv(
            "active-directory-no-location.csv",
            ["Nom", "Email", "Identifiant"],
            [
                {
                    "Nom": "Alice Martin",
                    "Email": "alice@epsilon-france.com",
                    "Identifiant": "martin_a",
                },
                {
                    "Nom": "Bob Durand",
                    "Email": "bob@epsilon-france.com",
                    "Identifiant": "durand_b",
                },
            ],
            ",",
        )
        output_path = self.output_directory / "attribute-values-fallback.csv"

        (
            _result_path,
            generated_count,
            missing_work_location_column,
        ) = generate_work_location_values(
            swile_path,
            active_directory_path,
            output_path,
            "epsilon-france.com",
        )

        self.assertEqual(generated_count, 2)
        self.assertTrue(missing_work_location_column)
        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual([row["Valeur"] for row in rows], ["Autre", "Autre"])
        self.assertEqual([row["Matricule"] for row in rows], ["martin_a", "durand_b"])
        self.assertEqual(
            [row["Nom de famille"] for row in rows],
            ["Martin-Swile", "Durand-Swile"],
        )

    def test_generate_work_location_values_keeps_all_swile_rows(self):
        """Vérifie que la génération conserve toutes les lignes Swile."""
        swile_path = self._write_csv(
            "swile-all-kept.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [
                {
                    "Prénom": "Alice",
                    "Nom": "Martin",
                    "Email": "alice@epsilon-france.com",
                    "Matricule": "swile_a",
                },
                {
                    "Prénom": "Bob",
                    "Nom": "Durand",
                    "Email": "bob@gmail.com",
                    "Matricule": "swile_b",
                },
                {
                    "Prénom": "",
                    "Nom": "",
                    "Email": "",
                    "Matricule": "swile_c",
                },
            ],
            ";",
        )
        active_directory_path = self._write_csv(
            "active-directory-all-kept.csv",
            ["Nom", "Email", "Identifiant", "Lieu de travail"],
            [
                {
                    "Nom": "Alice Martin",
                    "Email": "alice@epsilon-france.com",
                    "Identifiant": "martin_a",
                    "Lieu de travail": "FR Paris 145-151 rue de Courcelles",
                }
            ],
            ",",
        )
        output_path = self.output_directory / "attribute-values-all-kept.csv"

        (
            _result_path,
            generated_count,
            missing_work_location_column,
        ) = generate_work_location_values(
            swile_path,
            active_directory_path,
            output_path,
            "epsilon-france.com",
        )

        self.assertEqual(generated_count, 3)
        self.assertFalse(missing_work_location_column)
        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["Valeur"], "Paris 145")
        self.assertEqual(rows[1]["Valeur"], "Autre")
        self.assertEqual(rows[2]["Valeur"], "Autre")


if __name__ == "__main__":
    unittest.main()
