import unittest

from domain.matching import compare_users
from domain.normalization import normalize_matricule, normalize_name
from domain.swile_additions import build_additions


class NormalizationTests(unittest.TestCase):
    def test_normalize_name_ignores_diacritics_and_punctuation(self):
        self.assertEqual(normalize_name("Élodie O'Neil"), "elodieoneil")

    def test_normalize_matricule_ignores_spaces_and_hyphens(self):
        self.assertEqual(normalize_matricule(" AB- 12 "), "ab12")


class MatchingTests(unittest.TestCase):
    def test_match_swile_matricule_against_active_directory_identifiant(self):
        swile_user = {
            "Prénom": "Alice",
            "Nom": "Martin",
            "Email": "swile@example.com",
            "Matricule": " AB-12 ",
        }
        active_directory_user = {
            "Nom": "Different Person",
            "Email": "ad@example.com",
            "Identifiant": "ab12",
        }

        found, missing = compare_users([swile_user], [active_directory_user])

        self.assertEqual(found, [swile_user])
        self.assertEqual(missing, [])

    def test_match_uses_email_matricule_or_name(self):
        swile_users = [
            {
                "Prénom": "Alice",
                "Nom": "Martin",
                "Email": "different@example.com",
                "Matricule": "A-12",
            },
            {
                "Prénom": "Bob",
                "Nom": "Durand",
                "Email": "bob@example.com",
                "Matricule": "B-20",
            },
            {
                "Prénom": "Chloé",
                "Nom": "Petit",
                "Email": "c@example.com",
                "Matricule": "C-30",
            },
        ]
        active_directory_users = [
            {
                "Nom": "Alice Martin",
                "Email": "other@example.com",
                "Identifiant": "a12",
            },
            {
                "Nom": "Different Name",
                "Email": "BOB@example.com",
                "Identifiant": "other",
            },
            {
                "Nom": "Chloe Petit",
                "Email": "other2@example.com",
                "Identifiant": "other2",
            },
        ]

        found, missing = compare_users(swile_users, active_directory_users)

        self.assertEqual(len(found), 3)
        self.assertEqual(missing, [])


class AdditionsTests(unittest.TestCase):
    def test_build_additions_filters_existing_external_management_and_invalid(self):
        current_swile = [
            {
                "Prénom": "Ana",
                "Nom": "Doe",
                "Email": "ana@epsilon-france.com",
                "Matricule": "a1",
            }
        ]
        active_directory = [
            {
                "Nom": "Ana Doe",
                "Email": "ana@epsilon-france.com",
                "Identifiant": "a1",
                "Poste": "Analyste",
            },
            {
                "Nom": "Jean Nouveau",
                "Email": "jean@epsilon-france.com",
                "Identifiant": "j2",
                "Poste": "Analyste",
            },
            {
                "Nom": "Marie Direction",
                "Email": "marie@epsilon-france.com",
                "Identifiant": "d3",
                "Poste": "Directrice",
            },
            {
                "Nom": "Paul Externe",
                "Email": "paul.ext@epsilon-france.com",
                "Identifiant": "p4",
                "Poste": "Analyste",
            },
            {
                "Nom": "NomUnique",
                "Email": "invalid@epsilon-france.com",
                "Identifiant": "i5",
                "Poste": "Analyste",
            },
        ]

        (
            additions,
            ignored,
            excluded_management,
            excluded_existing,
            excluded_invalid,
            excluded_external,
        ) = build_additions(
            current_swile, active_directory, "epsilon-france.com"
        )

        self.assertEqual([row["Matricule"] for row in additions], ["j2"])
        self.assertEqual([row["Matricule"] for row in ignored], ["d3"])
        self.assertEqual(excluded_management, 1)
        self.assertEqual(excluded_existing, 1)
        self.assertEqual(excluded_invalid, 1)
        self.assertEqual(excluded_external, 1)


if __name__ == "__main__":
    unittest.main()
