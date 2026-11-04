import sys
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from services.paths import bundled_resource, project_root


class RuntimePathTests(unittest.TestCase):
    def test_frozen_project_root_is_executable_directory(self):
        """Vérifie que le mode exécutable utilise le dossier de l’application."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            executable = Path(temporary_directory) / "GestionCSE.exe"
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(executable)),
            ):
                self.assertTrue(
                    os.path.samefile(project_root(), temporary_directory)
                )

    def test_bundled_resource_uses_pyinstaller_extraction_directory(self):
        """Vérifie que les ressources gelées utilisent le dossier PyInstaller."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(sys, "_MEIPASS", temporary_directory, create=True):
                self.assertEqual(
                    bundled_resource("data", "template.csv"),
                    Path(temporary_directory) / "data" / "template.csv",
                )


if __name__ == "__main__":
    unittest.main()
