import json
import tempfile
import unittest
from pathlib import Path

from services import active_directory_config


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

            result_path = active_directory_config.save_active_directory_config(
                contents, config_path
            )

            self.assertEqual(result_path, config_path)
            self.assertEqual(config_path.read_text(encoding="utf-8"), contents)
            self.assertEqual(list(config_path.parent.glob("*.tmp")), [])
            self.assertEqual(
                active_directory_config.validate_config(
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
                active_directory_config.save_active_directory_config(
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
        del config["start_user_email"]

        with self.assertRaisesRegex(ValueError, "start_user_email"):
            active_directory_config.validate_config(config, "config.json")

    def test_config_defaults_fill_missing_values(self):
        """Vérifie les valeurs par défaut et le rejet des exemples."""
        config = active_directory_config.apply_config_defaults(
            {"report_domain": "", "authority": " "}
        )

        self.assertEqual(
            config["authority"],
            "https://login.microsoftonline.com/organizations",
        )
        self.assertEqual(config["scopes"], ["User.ReadBasic.All"])
        with self.assertRaisesRegex(ValueError, "exemple"):
            active_directory_config.validate_config(config, "config.json")
