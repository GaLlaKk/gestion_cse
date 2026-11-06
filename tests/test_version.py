import unittest

from services.version import __version__


class VersionTests(unittest.TestCase):
    def test_version_is_defined(self):
        """Vérifie qu’une version non vide est disponible."""
        self.assertTrue(__version__)
