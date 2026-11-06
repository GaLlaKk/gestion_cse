import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.swile_service import (
    compare_users,
    generate_additions,
    generate_work_location_values,
    load_addition_filters,
    load_work_location_mapping,
    map_work_location_value,
    save_work_location_mapping,
)


class SwileServiceTests(unittest.TestCase):
    def setUp(self):
        """Prépare les CSV de test partagés par les tests du service Swile."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.input_directory = self.root / "in"
        self.output_directory = self.root / "out"
        self.input_directory.mkdir()
        self.swile_path = self._write_csv(
            "swile.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [
                {
                    "Prénom": "Ana",
                    "Nom": "Doe",
                    "Email": "ana@epsilon-france.com",
                    "Matricule": "a1",
                },
                {
                    "Prénom": "Zoé",
                    "Nom": "Absent",
                    "Email": "zoe@example.net",
                    "Matricule": "z9",
                },
            ],
            ";",
        )
        self.active_directory_path = self._write_csv(
            "active-directory.csv",
            ["Nom", "Email", "Identifiant", "Poste"],
            [
                {
                    "Nom": "Ana Doe",
                    "Email": "ana@epsilon-france.com",
                    "Identifiant": "a1",
                    "Poste": "Analyste",
                },
                {
                    "Nom": "Jean Nouveau",
                    "Email": "jean@epsilon-france.com",
                    "Identifiant": "J-2",
                    "Poste": "Analyste",
                },
            ],
            ",",
        )

    def tearDown(self):
        """Supprime le dossier temporaire créé pour le test."""
        self.temporary_directory.cleanup()

    def _write_csv(self, name, fieldnames, rows, delimiter):
        """Écrit un CSV de test dans le dossier d’entrée temporaire."""
        path = self.input_directory / name
        with path.open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=fieldnames, delimiter=delimiter
            )
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_work_location_mapping_uses_current_defaults_without_config(self):
        """Vérifie le mapping existant quand le fichier de configuration manque."""
        mapping = load_work_location_mapping(
            self.root / "configuration-absente.json"
        )

        self.assertEqual(
            map_work_location_value(
                "FR Paris 145-151 rue de Courcelles", mapping
            ),
            "Paris 145",
        )
        self.assertEqual(
            map_work_location_value("29 Avenue De La Marne", mapping),
            "Lille 5.9",
        )
        self.assertEqual(
            map_work_location_value("FR Paris 133", mapping), "Paris 133"
        )
        self.assertEqual(map_work_location_value("Bordeaux", mapping), "Autre")

    def test_work_location_mapping_loads_custom_rules(self):
        """Vérifie le chargement des règles personnalisées et leur normalisation."""
        config_path = self.root / "swile.config.json"
        config_path.write_text(
            json.dumps(
                {
                    "default_value": "Autre site",
                    "rules": [
                        {
                            "patterns": [["avenue", "marne"]],
                            "value": "Nouveau site",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        mapping = load_work_location_mapping(config_path)

        self.assertEqual(
            map_work_location_value("29 AVENUE DE LA MARNE", mapping),
            "Nouveau site",
        )
        self.assertEqual(
            map_work_location_value("Bordeaux", mapping), "Autre site"
        )

    def test_generate_work_location_values_uses_custom_configuration(self):
        """Vérifie que la génération applique le fichier de mapping personnalisé."""
        active_directory_path = self._write_csv(
            "active-directory-custom-locations.csv",
            ["Nom", "Email", "Identifiant", "Poste", "Lieu de travail"],
            [
                {
                    "Nom": "Ana Doe",
                    "Email": "ana@epsilon-france.com",
                    "Identifiant": "a1",
                    "Poste": "Analyste",
                    "Lieu de travail": "Bordeaux",
                },
                {
                    "Nom": "Jean Nouveau",
                    "Email": "jean@epsilon-france.com",
                    "Identifiant": "J-2",
                    "Poste": "Analyste",
                    "Lieu de travail": "Bordeaux",
                },
            ],
            ",",
        )
        config_path = self.root / "swile.config.json"
        config_path.write_text(
            json.dumps(
                {
                    "default_value": "Autre site",
                    "rules": [
                        {
                            "patterns": [["bordeaux"]],
                            "value": "Siège Bordeaux",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        output_path = self.output_directory / "custom-location-values.csv"

        generate_work_location_values(
            self.swile_path,
            active_directory_path,
            output_path,
            "epsilon-france.com",
            config_path,
        )

        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(
            [row["Valeur"] for row in rows],
            ["Siège Bordeaux", "Siège Bordeaux"],
        )

    def test_work_location_mapping_rejects_invalid_configuration(self):
        """Vérifie qu’une configuration présente mais invalide est signalée."""
        config_path = self.root / "swile.config.json"
        config_path.write_text('{"default_value": "Autre", "rules": [{}]}')

        with self.assertRaisesRegex(ValueError, "règle 1"):
            load_work_location_mapping(config_path)

    def test_work_location_mapping_is_saved_and_reloaded(self):
        """Vérifie l’enregistrement atomique et le rechargement du mapping."""
        config_path = self.root / "swile.config.json"
        mapping = {
            "default_value": "Autre site",
            "rules": [
                {
                    "patterns": [["paris", "courcelles"]],
                    "value": "Paris siège",
                }
            ],
        }

        self.assertEqual(
            save_work_location_mapping(mapping, config_path),
            config_path,
        )
        self.assertEqual(load_work_location_mapping(config_path), mapping)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_addition_filters_default_to_current_behavior_without_config(self):
        """Vérifie que l’absence de filtres conserve le paramétrage historique."""
        filters = load_addition_filters(
            self.root / "configuration-absente.json"
        )

        self.assertEqual(
            filters["email"]["rules"][0]["patterns"],
            [[".ext@"]],
        )
        self.assertEqual(filters["email"]["rules"][0]["value"], "exclure")
        self.assertIn(
            ["directrice"],
            filters["poste"]["rules"][0]["patterns"],
        )

    def test_addition_filters_share_configuration_with_work_locations(self):
        """Vérifie que la sauvegarde du mapping conserve les filtres définis."""
        config_path = self.root / "swile.config.json"
        mapping = {
            "default_value": "Autre site",
            "rules": [],
        }
        filters = {
            "email": {
                "default_value": "inclure",
                "rules": [
                    {"patterns": [[".externe"]], "value": "exclure"}
                ],
            },
            "poste": {
                "default_value": "inclure",
                "rules": [
                    {"patterns": [["responsable"]], "value": "exclure"}
                ],
            },
        }

        save_work_location_mapping(mapping, config_path, filters)

        self.assertEqual(load_work_location_mapping(config_path), mapping)
        self.assertEqual(load_addition_filters(config_path), filters)
        saved_config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved_config["filters"], filters)

    def test_swile_configuration_reads_legacy_location_filename(self):
        """Vérifie la lecture de l’ancien nom avant une sauvegarde migrée."""
        legacy_path = self.root / "lieux_travail.config.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "default_value": "Autre",
                    "rules": [],
                    "filters": {
                        "email": {
                            "default_value": "exclure",
                            "rules": [],
                        },
                        "poste": {
                            "default_value": "inclure",
                            "rules": [],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        with (
            patch(
                "services.swile_service.SWILE_CONFIG_PATH",
                self.root / "swile.config.json",
            ),
            patch(
                "services.swile_service.LEGACY_SWILE_CONFIG_PATH",
                legacy_path,
            ),
        ):
            filters = load_addition_filters()
            mapping = load_work_location_mapping()

        self.assertEqual(filters["email"]["default_value"], "exclure")
        self.assertEqual(mapping, {"default_value": "Autre", "rules": []})

    def test_generate_additions_applies_filters_from_shared_configuration(self):
        """Vérifie que la génération des ajouts lit les filtres du JSON."""
        template_path = self._write_csv(
            "template-filters.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [],
            ";",
        )
        active_directory_path = self._write_csv(
            "active-directory-filters.csv",
            ["Nom", "Email", "Identifiant", "Poste"],
            [
                {
                    "Nom": "Alice Externe",
                    "Email": "alice.ext@epsilon-france.com",
                    "Identifiant": "filter_a99",
                    "Poste": "Analyste",
                },
                {
                    "Nom": "Bob Lead",
                    "Email": "bob@epsilon-france.com",
                    "Identifiant": "filter_b99",
                    "Poste": "Team Lead",
                },
            ],
            ",",
        )
        config_path = self.root / "swile.config.json"
        config_path.write_text(
            json.dumps(
                {
                    "default_value": "Autre",
                    "rules": [],
                    "filters": {
                        "email": {
                            "default_value": "inclure",
                            "rules": [],
                        },
                        "poste": {
                            "default_value": "inclure",
                            "rules": [
                                {
                                    "patterns": [["lead"]],
                                    "value": "exclure",
                                }
                            ],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        output_path = self.output_directory / "custom-additions.csv"

        result = generate_additions(
            self.swile_path,
            active_directory_path,
            template_path,
            output_path,
            "epsilon-france.com",
            filters_config_path=config_path,
        )

        self.assertEqual(result[0], 1)
        self.assertEqual(result[2], 1)
        self.assertEqual(result[6], 0)
        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(rows[0]["Email"], "alice.ext@epsilon-france.com")

    def test_invalid_work_location_mapping_does_not_replace_file(self):
        """Vérifie qu’un mapping invalide ne modifie pas le fichier enregistré."""
        config_path = self.root / "swile.config.json"
        config_path.write_text('{"default_value": "Avant"}', encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "rules"):
            save_work_location_mapping(
                {"default_value": "Après", "rules": "invalide"},
                config_path,
            )

        self.assertEqual(
            config_path.read_text(encoding="utf-8"),
            '{"default_value": "Avant"}',
        )

    def test_compare_users_writes_found_and_missing_csvs(self):
        """Vérifie l’écriture des résultats de comparaison dans deux CSV."""
        found_path, missing_path, found_count, missing_count = compare_users(
            self.swile_path,
            self.active_directory_path,
            self.output_directory,
        )

        self.assertEqual((found_count, missing_count), (1, 1))
        with found_path.open(encoding="utf-8-sig", newline="") as stream:
            found_rows = list(csv.DictReader(stream, delimiter=";"))
        with missing_path.open(encoding="utf-8-sig", newline="") as stream:
            missing_rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(found_rows[0]["Email"], "ana@epsilon-france.com")
        self.assertEqual(missing_rows[0]["Email"], "zoe@example.net")

    def test_compare_users_does_not_write_empty_result_files(self):
        """Vérifie que la comparaison ne crée pas de CSV sans résultat."""
        empty_swile_path = self._write_csv(
            "swile-empty.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [],
            ";",
        )

        found_path, missing_path, found_count, missing_count = compare_users(
            empty_swile_path,
            self.active_directory_path,
            self.output_directory,
        )

        self.assertEqual((found_count, missing_count), (0, 0))
        self.assertFalse(found_path.exists())
        self.assertFalse(missing_path.exists())

    def test_generate_additions_does_not_write_empty_result_files(self):
        """Vérifie que les ajouts ne créent pas de CSV sans résultat."""
        all_users_swile_path = self._write_csv(
            "swile-all-users.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [
                {
                    "Prénom": "Ana",
                    "Nom": "Doe",
                    "Email": "ana@epsilon-france.com",
                    "Matricule": "a1",
                },
                {
                    "Prénom": "Jean",
                    "Nom": "Nouveau",
                    "Email": "jean@epsilon-france.com",
                    "Matricule": "J-2",
                },
            ],
            ";",
        )
        template_path = self._write_csv(
            "empty-results-template.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [],
            ";",
        )
        output_path = self.output_directory / "empty-additions.csv"

        result = generate_additions(
            all_users_swile_path,
            self.active_directory_path,
            template_path,
            output_path,
            "epsilon-france.com",
        )

        self.assertEqual((result[0], result[2]), (0, 0))
        self.assertFalse(output_path.exists())
        self.assertFalse(result[1].exists())

    def test_generate_work_location_values_does_not_write_empty_file(self):
        """Vérifie que les valeurs de lieu ne créent pas de CSV vide."""
        empty_swile_path = self._write_csv(
            "swile-empty-locations.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [],
            ";",
        )
        empty_active_directory_path = self._write_csv(
            "active-directory-empty-locations.csv",
            ["Nom", "Email", "Identifiant", "Poste", "Lieu de travail"],
            [],
            ",",
        )
        output_path = self.output_directory / "empty-attribute-values.csv"

        result_path, generated_count, _ = generate_work_location_values(
            empty_swile_path,
            empty_active_directory_path,
            output_path,
            "epsilon-france.com",
        )

        self.assertEqual(result_path, output_path)
        self.assertEqual(generated_count, 0)
        self.assertFalse(output_path.exists())

    def test_generate_additions_preserves_original_identifier(self):
        """Vérifie que l’ajout conserve le matricule AD d’origine."""
        template_path = self._write_csv(
            "template.csv", ["Prénom", "Nom", "Email", "Matricule"], [], ";"
        )
        output_path = self.output_directory / "collaborators-additions-test.csv"

        result = generate_additions(
            self.swile_path,
            self.active_directory_path,
            template_path,
            output_path,
            "epsilon-france.com",
        )

        self.assertEqual(result[0], 1)
        self.assertEqual(result[2], 0)
        self.assertFalse(result[1].exists())
        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(rows[0]["Matricule"], "J-2")

    def test_generate_work_location_values_uses_expected_value_mapping(self):
        """Vérifie les correspondances d’adresses vers les sites Swile."""
        swile_path = self._write_csv(
            "swile-locations.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [
                {
                    "Prénom": "Alice",
                    "Nom": "Martin-Swile",
                    "Email": "alice@epsilon-france.com",
                    "Matricule": "swile_a",
                },
                {
                    "Prénom": "Bob",
                    "Nom": "Durand-Swile",
                    "Email": "bob@epsilon-france.com",
                    "Matricule": "swile_b",
                },
                {
                    "Prénom": "Chloe",
                    "Nom": "Petit-Swile",
                    "Email": "chloe@epsilon-france.com",
                    "Matricule": "swile_c",
                },
                {
                    "Prénom": "Denis",
                    "Nom": "Dupont-Swile",
                    "Email": "denis@epsilon-france.com",
                    "Matricule": "swile_d",
                },
            ],
            ";",
        )
        active_directory_path = self._write_csv(
            "active-directory-locations.csv",
            ["Nom", "Email", "Identifiant", "Poste", "Lieu de travail"],
            [
                {
                    "Nom": "Alice Martin",
                    "Email": "alice@epsilon-france.com",
                    "Identifiant": "martin_a",
                    "Poste": "Analyste",
                    "Lieu de travail": "FR Paris 145-151 rue de Courcelles",
                },
                {
                    "Nom": "Bob Durand",
                    "Email": "bob@epsilon-france.com",
                    "Identifiant": "durand_b",
                    "Poste": "Analyste",
                    "Lieu de travail": "29 Avenue De La Marne",
                },
                {
                    "Nom": "Chloe Petit",
                    "Email": "chloe@epsilon-france.com",
                    "Identifiant": "petit_c",
                    "Poste": "Analyste",
                    "Lieu de travail": "FR Paris 133",
                },
                {
                    "Nom": "Denis Dupont",
                    "Email": "denis@epsilon-france.com",
                    "Identifiant": "dupont_d",
                    "Poste": "Analyste",
                    "Lieu de travail": "Bordeaux",
                },
                {
                    "Nom": "Paul Externe",
                    "Email": "paul.ext@epsilon-france.com",
                    "Identifiant": "externe_p",
                    "Poste": "Analyste",
                    "Lieu de travail": "FR Paris 145-151 rue de Courcelles",
                },
                {
                    "Nom": "NomUnique",
                    "Email": "invalid@epsilon-france.com",
                    "Identifiant": "invalid_i",
                    "Poste": "Analyste",
                    "Lieu de travail": "FR Paris 145-151 rue de Courcelles",
                },
            ],
            ",",
        )
        output_path = self.output_directory / "attribute-values.csv"

        (
            result_path,
            generated_count,
            missing_work_location_column,
        ) = generate_work_location_values(
            swile_path,
            active_directory_path,
            output_path,
            "epsilon-france.com",
        )

        self.assertEqual(result_path, output_path)
        self.assertEqual(generated_count, 4)
        self.assertFalse(missing_work_location_column)
        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(
            [row["Valeur"] for row in rows],
            ["Paris 145", "Lille 5.9", "Paris 133", "Autre"],
        )
        self.assertEqual(
            [row["Matricule"] for row in rows],
            ["martin_a", "durand_b", "petit_c", "dupont_d"],
        )
        self.assertEqual(rows[0]["Prénom"], "Alice")
        self.assertEqual(rows[0]["Nom de famille"], "Martin-Swile")
        self.assertEqual(rows[0]["E-mail"], "alice@epsilon-france.com")

    def test_generate_work_location_values_handles_missing_column(self):
        """Vérifie la valeur de repli quand le CSV AD n’a pas le lieu."""
        swile_path = self._write_csv(
            "swile-no-location.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [
                {
                    "Prénom": "Alice",
                    "Nom": "Martin-Swile",
                    "Email": "alice@epsilon-france.com",
                    "Matricule": "swile_a",
                },
                {
                    "Prénom": "Bob",
                    "Nom": "Durand-Swile",
                    "Email": "bob@epsilon-france.com",
                    "Matricule": "swile_b",
                },
            ],
            ";",
        )
        active_directory_path = self._write_csv(
            "active-directory-no-location.csv",
            ["Nom", "Email", "Identifiant", "Poste"],
            [
                {
                    "Nom": "Alice Martin",
                    "Email": "alice@epsilon-france.com",
                    "Identifiant": "martin_a",
                    "Poste": "Analyste",
                },
                {
                    "Nom": "Bob Durand",
                    "Email": "bob@epsilon-france.com",
                    "Identifiant": "durand_b",
                    "Poste": "Analyste",
                },
            ],
            ",",
        )
        output_path = self.output_directory / "attribute-values-fallback.csv"

        (
            _result_path,
            generated_count,
            missing_work_location_column,
        ) = generate_work_location_values(
            swile_path,
            active_directory_path,
            output_path,
            "epsilon-france.com",
            filters_config_path=self.root / "missing-filters.json",
        )

        self.assertEqual(generated_count, 2)
        self.assertTrue(missing_work_location_column)
        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual([row["Valeur"] for row in rows], ["Autre", "Autre"])
        self.assertEqual([row["Matricule"] for row in rows], ["martin_a", "durand_b"])
        self.assertEqual(
            [row["Nom de famille"] for row in rows],
            ["Martin-Swile", "Durand-Swile"],
        )

    def test_generate_work_location_values_uses_found_users_and_filtered_additions(
        self,
    ):
        """Vérifie les Swile trouvés et les ajouts admissibles uniquement."""
        swile_path = self._write_csv(
            "swile-filtered-sources.csv",
            ["Prénom", "Nom", "Email", "Matricule"],
            [
                {
                    "Prénom": "Alice",
                    "Nom": "Martin",
                    "Email": "alice@epsilon-france.com",
                    "Matricule": "swile_a",
                },
                {
                    "Prénom": "Non",
                    "Nom": "Trouve",
                    "Email": "not-found@epsilon-france.com",
                    "Matricule": "swile_missing",
                },
            ],
            ";",
        )
        active_directory_path = self._write_csv(
            "active-directory-filtered-sources.csv",
            ["Nom", "Email", "Identifiant", "Poste", "Lieu de travail"],
            [
                {
                    "Nom": "Alice Martin",
                    "Email": "alice@epsilon-france.com",
                    "Identifiant": "martin_a",
                    "Poste": "Analyste",
                    "Lieu de travail": "FR Paris 145-151 rue de Courcelles",
                },
                {
                    "Nom": "Ajoute Admissible",
                    "Email": "added@epsilon-france.com",
                    "Identifiant": "added_a",
                    "Poste": "Analyste",
                    "Lieu de travail": "29 Avenue De La Marne",
                },
                {
                    "Nom": "Ajoute Externe",
                    "Email": "external.ext@epsilon-france.com",
                    "Identifiant": "external_a",
                    "Poste": "Analyste",
                    "Lieu de travail": "FR Paris 145-151 rue de Courcelles",
                },
                {
                    "Nom": "Ajoute Direction",
                    "Email": "director@epsilon-france.com",
                    "Identifiant": "director_a",
                    "Poste": "Directeur",
                    "Lieu de travail": "FR Paris 133",
                },
            ],
            ",",
        )
        output_path = self.output_directory / "attribute-values-filtered-sources.csv"
        filters_config_path = self.root / "swile-filters.json"
        filters_config_path.write_text(
            json.dumps(
                {
                    "filters": {
                        "email": {
                            "default_value": "inclure",
                            "rules": [
                                {
                                    "patterns": [[".ext@"]],
                                    "value": "exclure",
                                }
                            ],
                        },
                        "poste": {
                            "default_value": "inclure",
                            "rules": [
                                {
                                    "patterns": [["directeur"]],
                                    "value": "exclure",
                                }
                            ],
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        (
            _result_path,
            generated_count,
            missing_work_location_column,
        ) = generate_work_location_values(
            swile_path,
            active_directory_path,
            output_path,
            "epsilon-france.com",
            filters_config_path=filters_config_path,
        )

        self.assertEqual(generated_count, 2)
        self.assertFalse(missing_work_location_column)
        with output_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream, delimiter=";"))
        self.assertEqual(
            [row["E-mail"] for row in rows],
            ["alice@epsilon-france.com", "added@epsilon-france.com"],
        )
        self.assertEqual(
            [row["Valeur"] for row in rows], ["Paris 145", "Lille 5.9"]
        )
        self.assertEqual([row["Matricule"] for row in rows], ["martin_a", "added_a"])


if __name__ == "__main__":
    unittest.main()
