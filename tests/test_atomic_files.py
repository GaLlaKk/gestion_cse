import tempfile
import unittest
from pathlib import Path

from services.atomic_files import atomic_write


class AtomicWriteTests(unittest.TestCase):
    def test_replaces_file_and_leaves_no_temporary_file(self):
        """Vérifie le remplacement du fichier sans résidu temporaire."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data.txt"
            target.write_text("ancien", encoding="utf-8")
            atomic_write(
                target, lambda stream: stream.write("nouveau"), encoding="utf-8"
            )
            self.assertEqual(target.read_text(encoding="utf-8"), "nouveau")
            self.assertEqual(
                [path.name for path in Path(directory).iterdir()], ["data.txt"]
            )

    def test_failed_write_keeps_existing_file(self):
        """Vérifie qu’une erreur d’écriture préserve l’ancien contenu."""
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "data.txt"
            target.write_text("ancien", encoding="utf-8")

            def failing_write(stream):
                stream.write("partiel")
                raise RuntimeError("échec")

            with self.assertRaises(RuntimeError):
                atomic_write(target, failing_write, encoding="utf-8")
            self.assertEqual(target.read_text(encoding="utf-8"), "ancien")
            self.assertEqual(
                [path.name for path in Path(directory).iterdir()], ["data.txt"]
            )
