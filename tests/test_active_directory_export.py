import csv
import tempfile
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from services import active_directory_export
from services.graph_client import GRAPH_BASE_URL

CONFIG_JSON = (
    '{"start_user_email":"start@example.com",'
    '"client_id":"client-id","authority":"authority",'
    '"report_domain":"example.com","scopes":["scope"]}'
)
DEVICE_FLOW = {"user_code": "ABCD1234", "message": "Sign in"}


def batch_post(request_graph):
    """Simule `POST /$batch` en rejouant chaque sous-requête sur `request_graph`."""

    def post(url, json=None, **_kwargs):
        responses = []
        for item in json["requests"]:
            inner = request_graph(GRAPH_BASE_URL + item["url"])
            responses.append(
                {
                    "id": item["id"],
                    "status": inner.status_code,
                    "headers": {},
                    "body": inner.json.return_value,
                }
            )
        outer = Mock(status_code=200)
        outer.json.return_value = {"responses": responses}
        outer.raise_for_status.return_value = None
        return outer

    return post


def graph_response(status_code=200, payload=None, content=None):
    """Construit une réponse Graph simulée."""
    response = Mock(status_code=status_code)
    if content is not None:
        response.content = content
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def authenticated_client():
    """Crée un client MSAL simulé dont l’authentification réussit."""
    client = Mock()
    client.initiate_device_flow.return_value = DEVICE_FLOW
    client.acquire_token_by_device_flow.return_value = {
        "access_token": "token"
    }
    return client


def write_config(root):
    """Écrit la configuration minimale d’export et retourne son chemin."""
    config_path = Path(root) / "config.json"
    config_path.write_text(CONFIG_JSON, encoding="utf-8")
    return config_path


def write_previous_export(path, rows):
    """Écrit un export Active Directory précédent minimal."""
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["Nom", "Email", "Identifiant", "Poste"],
            delimiter=",",
        )
        writer.writeheader()
        writer.writerows(rows)


def read_rows(path):
    """Lit les lignes d’un export généré."""
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def start_user_payload():
    """Retourne la réponse Graph du compte de départ."""
    return {
        "id": "root-id",
        "displayName": "Start User",
        "mail": "start@example.com",
        "userPrincipalName": "start@example.com",
        "jobTitle": "Analyste",
        "officeLocation": "Paris",
        "department": "Services",
    }


@contextmanager
def patched_export(
    config_path,
    output_directory,
    request_graph,
    client=None,
    logger=None,
    patch_sleep=False,
):
    """Isole l’export AD : configuration, MSAL, journal et appels Graph."""
    client = client or authenticated_client()
    logger = logger or Mock()
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                active_directory_export,
                "get_config_path",
                return_value=config_path,
            )
        )
        stack.enter_context(
            patch.object(
                active_directory_export,
                "initialize_output",
                return_value=(logger, output_directory, "20261028"),
            )
        )
        stack.enter_context(
            patch.object(
                active_directory_export,
                "PublicClientApplication",
                return_value=client,
            )
        )
        stack.enter_context(
            patch.object(requests.Session, "get", side_effect=request_graph)
        )
        stack.enter_context(
            patch.object(
                requests.Session,
                "post",
                side_effect=batch_post(request_graph),
            )
        )
        if patch_sleep:
            stack.enter_context(patch("services.graph_client.time.sleep"))
        yield logger


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
            config_path = write_config(temporary_directory)
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

            with patched_export(
                config_path,
                Path(temporary_directory),
                request_graph=Mock(),
                client=client,
            ) as logger:
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
            config_path = write_config(root)
            output_directory = root / "out"
            output_directory.mkdir()
            final_path = (
                output_directory / "20261028_liste_salarie_active_directory.csv"
            )
            progress_updates = []

            def request_graph(url, **_kwargs):
                """Fournit les réponses Graph attendues par la collecte simulée."""
                if "/users/start@example.com?" in url:
                    return graph_response(payload=start_user_payload())
                if "/users/root-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/start@example.com/directReports" in url:
                    self.assertFalse(final_path.exists())
                    self.assertEqual(
                        len(list(output_directory.glob("*.tmp"))), 1
                    )
                    return graph_response(payload={"value": []})
                self.fail(f"URL Graph inattendue : {url}")

            with patched_export(
                config_path, output_directory, request_graph
            ) as logger:
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
            rows = read_rows(final_path)
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
                    (1, 500, "complete"),
                ],
            )

    def test_export_downloads_photos_in_parallel_without_failing_on_error(self):
        """Vérifie que les photos sont téléchargées et qu’une erreur reste non bloquante."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = write_config(root)
            output_directory = root / "out"
            output_directory.mkdir()

            def user(identifier, mail):
                return {
                    "id": identifier,
                    "displayName": identifier,
                    "mail": mail,
                    "userPrincipalName": mail,
                }

            def request_graph(url, **_kwargs):
                if "/users/start@example.com?" in url:
                    return graph_response(payload=user("root-id", "start@example.com"))
                if "/directReports" in url and "start@example.com" in url:
                    return graph_response(
                        payload={
                            "value": [
                                {"id": "child-id", "mail": "child@example.com"}
                            ]
                        }
                    )
                if "/users/child-id?" in url:
                    return graph_response(payload=user("child-id", "child@example.com"))
                if "/directReports" in url:
                    return graph_response(payload={"value": []})
                if "/users/root-id/photo/$value" in url:
                    return graph_response(content=b"jpg")
                if "/users/child-id/photo/$value" in url:
                    raise requests.ConnectionError("coupure photo")
                self.fail(f"URL Graph inattendue : {url}")

            with patched_export(
                config_path, output_directory, request_graph, patch_sleep=True
            ) as logger:
                result_path = active_directory_export.run_active_directory_export(
                    download_photos=True
                )

            self.assertIsNotNone(result_path)
            self.assertTrue(
                (output_directory / "photos" / "start_root-id.jpg").is_file()
            )
            logger.exception.assert_called()

    def test_export_does_not_publish_csv_when_no_users_are_exported(self):
        """Vérifie qu’aucun CSV d’en-tête seul n’est publié."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = write_config(root)
            output_directory = root / "out"
            output_directory.mkdir()

            def request_graph(url, **_kwargs):
                """Retourne un compte externe sans rapport à exporter."""
                if "/users/start@example.com?" in url:
                    return graph_response(
                        payload={
                            "id": "root-id",
                            "displayName": "External User",
                            "mail": "external.ext@example.com",
                            "userPrincipalName": "start@example.com",
                        }
                    )
                if "/users/root-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/start@example.com/directReports" in url:
                    return graph_response(payload={"value": []})
                self.fail(f"URL Graph inattendue : {url}")

            with patched_export(config_path, output_directory, request_graph):
                result_path = active_directory_export.run_active_directory_export()

            self.assertIsNone(result_path)
            self.assertEqual(list(output_directory.glob("*.csv")), [])
            self.assertEqual(list(output_directory.glob("*.tmp")), [])
            self.assertFalse(
                (output_directory / active_directory_export.RESUME_STATE_FILENAME)
                .exists()
            )

    def test_export_resumes_after_connection_error(self):
        """Vérifie la reprise automatique après une coupure réseau pendant la collecte."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = write_config(root)
            output_directory = root / "out"
            output_directory.mkdir()
            final_path = (
                output_directory / "20261028_liste_salarie_active_directory.csv"
            )
            resume_state_path = (
                output_directory / active_directory_export.RESUME_STATE_FILENAME
            )
            phase = {"value": "fail"}

            def request_graph(url, **_kwargs):
                """Simule une coupure réseau puis un succès au redémarrage."""
                if "/users/start@example.com?" in url:
                    return graph_response(payload=start_user_payload())
                if "/users/root-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/start@example.com/directReports" in url:
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

            with patched_export(
                config_path, output_directory, request_graph, patch_sleep=True
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
            self.assertEqual(
                [row["Email"] for row in read_rows(final_path)],
                ["start@example.com", "child@example.com"],
            )

    def test_export_appends_visible_users_from_previous_export(self):
        """Vérifie l’ajout des comptes encore visibles absents de l’export."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = write_config(root)
            output_directory = root / "out"
            output_directory.mkdir()
            previous_export_path = root / "previous.csv"
            write_previous_export(
                previous_export_path,
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
                ],
            )
            final_path = (
                output_directory / "20261028_liste_salarie_active_directory.csv"
            )

            def request_graph(url, **_kwargs):
                """Fournit les réponses Graph prévues pour les utilisateurs."""
                if "/users/start@example.com?" in url:
                    return graph_response(payload=start_user_payload())
                if "/users/root-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/start@example.com/directReports" in url:
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

            with patched_export(config_path, output_directory, request_graph):
                result_path = active_directory_export.run_active_directory_export(
                    previous_export_path=previous_export_path
                )

            self.assertEqual(result_path, final_path)
            rows = read_rows(final_path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(
                [row["Email"] for row in rows],
                ["start@example.com", "legacy@example.com"],
            )

    def test_export_does_not_append_missing_users_from_previous_export(self):
        """Vérifie que les comptes absents de Graph ne sont pas ajoutés."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = write_config(root)
            output_directory = root / "out"
            output_directory.mkdir()
            previous_export_path = root / "previous.csv"
            write_previous_export(
                previous_export_path,
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
                ],
            )

            def request_graph(url, **_kwargs):
                """Fournit les réponses Graph prévues, dont le compte absent."""
                if "/users/start@example.com?" in url:
                    return graph_response(payload=start_user_payload())
                if "/users/root-id/manager" in url:
                    return graph_response(status_code=404)
                if "/users/start@example.com/directReports" in url:
                    return graph_response(payload={"value": []})
                if "/users/deleted@example.com?" in url:
                    return graph_response(status_code=404)
                self.fail(f"URL Graph inattendue : {url}")

            with patched_export(config_path, output_directory, request_graph):
                result_path = active_directory_export.run_active_directory_export(
                    previous_export_path=previous_export_path
                )

            rows = read_rows(result_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Email"], "start@example.com")
