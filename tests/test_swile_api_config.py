import json
import tempfile
import unittest
from pathlib import Path

from services.swile_api_config import (
    load_swile_api_settings,
    load_swile_api_credentials,
    load_swile_api_subscribed_product_ids,
    save_swile_api_credentials,
    save_swile_api_subscribed_product_ids,
)


class SwileApiConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.config_path = self.root / "swile_api.config.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_missing_config_returns_empty_credentials(self):
        credentials = load_swile_api_credentials(self.config_path)

        self.assertEqual(credentials, {"client_id": "", "client_secret": ""})

    def test_save_and_load_credentials(self):
        save_swile_api_credentials("client-id", "client-secret", self.config_path)

        credentials = load_swile_api_credentials(self.config_path)
        self.assertEqual(credentials["client_id"], "client-id")
        self.assertEqual(credentials["client_secret"], "client-secret")
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["client_id"], "client-id")
        self.assertNotEqual(raw["client_secret_encrypted"], "client-secret")
        self.assertEqual(raw["subscribed_product_ids"], [])

    def test_save_and_load_subscribed_products(self):
        save_swile_api_subscribed_product_ids(
            ["prod-a", " prod-b ", "prod-a", ""],
            self.config_path,
        )

        products = load_swile_api_subscribed_product_ids(self.config_path)

        self.assertEqual(products, ["prod-a", "prod-b"])

    def test_save_credentials_preserves_subscribed_products(self):
        save_swile_api_subscribed_product_ids(["prod-a"], self.config_path)

        save_swile_api_credentials("client-id", "client-secret", self.config_path)

        settings = load_swile_api_settings(self.config_path)
        self.assertEqual(settings["subscribed_product_ids"], ["prod-a"])

    def test_invalid_encrypted_secret_is_rejected(self):
        self.config_path.write_text(
            json.dumps(
                {
                    "client_id": "client-id",
                    "client_secret_encrypted": "invalid-token",
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "déchiffrer"):
            load_swile_api_credentials(self.config_path)


if __name__ == "__main__":
    unittest.main()

