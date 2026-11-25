import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

from services.file_retention import cleanup_processing_files


class FileRetentionTests(unittest.TestCase):
    def test_cleanup_deletes_only_old_processing_files(self):
        """Supprime les anciens fichiers de traitement sans toucher au reste."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            old_processing = (
                root / "swile_active_directory" / "out" / "old.csv"
            )
            old_ekie_processing = root / "ekie" / "out" / "old.xlsx"
            new_processing = (
                root / "liste_salarie_active_directory" / "out" / "new.csv"
            )
            old_non_processing = root / "services" / "do_not_touch.py"
            old_processing.parent.mkdir(parents=True, exist_ok=True)
            old_ekie_processing.parent.mkdir(parents=True, exist_ok=True)
            new_processing.parent.mkdir(parents=True, exist_ok=True)
            old_non_processing.parent.mkdir(parents=True, exist_ok=True)
            old_processing.write_text("old", encoding="utf-8")
            old_ekie_processing.write_text("old-ekie", encoding="utf-8")
            new_processing.write_text("new", encoding="utf-8")
            old_non_processing.write_text("safe", encoding="utf-8")

            old_timestamp = (
                datetime.now() - timedelta(days=120)
            ).timestamp()
            now_timestamp = datetime.now().timestamp()
            os.utime(old_processing, (old_timestamp, old_timestamp))
            os.utime(old_ekie_processing, (old_timestamp, old_timestamp))
            os.utime(old_non_processing, (old_timestamp, old_timestamp))
            os.utime(new_processing, (now_timestamp, now_timestamp))

            logger = Mock()
            deleted_count = cleanup_processing_files(root, logger)

            self.assertEqual(deleted_count, 2)
            self.assertFalse(old_processing.exists())
            self.assertFalse(old_ekie_processing.exists())
            self.assertTrue(new_processing.exists())
            self.assertTrue(old_non_processing.exists())
            logger.info.assert_called_once()


if __name__ == "__main__":
    unittest.main()
