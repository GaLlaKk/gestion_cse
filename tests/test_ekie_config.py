import json
import tempfile
import unittest
from pathlib import Path

from services.ekie_config import (
    load_cse_member_emails,
    load_ekie_config,
    save_ekie_config,
)


class EkieConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.config_path = self.root / "ekie.config.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_missing_config_returns_empty_members(self):
        config = load_ekie_config(self.config_path)

        self.assertEqual(config, {"cse_member_emails": []})
        self.assertEqual(load_cse_member_emails(self.config_path), set())

    def test_save_and_load_normalize_emails(self):
        save_ekie_config(
            {
                "cse_member_emails": [
                    " Alice@Example.com ",
                    "alice@example.com",
                    "BOB@example.com",
                ]
            },
            self.config_path,
        )

        loaded = load_ekie_config(self.config_path)
        self.assertEqual(
            loaded["cse_member_emails"],
            ["alice@example.com", "bob@example.com"],
        )
        self.assertEqual(
            load_cse_member_emails(self.config_path),
            {"alice@example.com", "bob@example.com"},
        )
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(raw, loaded)

    def test_invalid_email_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "invalide"):
            save_ekie_config({"cse_member_emails": ["not-an-email"]}, self.config_path)


if __name__ == "__main__":
    unittest.main()

