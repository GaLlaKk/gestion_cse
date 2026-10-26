import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.paths import bundled_resource, project_root


class RuntimePathTests(unittest.TestCase):
    def test_frozen_project_root_is_executable_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            executable = Path(temporary_directory) / "GestionCSE.exe"
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(executable)),
            ):
                self.assertEqual(project_root(), Path(temporary_directory))

    def test_bundled_resource_uses_pyinstaller_extraction_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(sys, "_MEIPASS", temporary_directory, create=True):
                self.assertEqual(
                    bundled_resource("data", "template.csv"),
                    Path(temporary_directory) / "data" / "template.csv",
                )


if __name__ == "__main__":
    unittest.main()
