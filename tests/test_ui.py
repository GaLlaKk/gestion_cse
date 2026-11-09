import json
import tempfile
import tkinter
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from services.version import __version__

try:
    probe = tkinter.Tk()
    probe.destroy()
    DISPLAY_ERROR = None
except tkinter.TclError as error:
    DISPLAY_ERROR = str(error)

if DISPLAY_ERROR is None:
    from app.ui.cse_desktop_app import CSEFileManager

AD_CONFIG = {
    "start_user_email": "start@societe.fr",
    "client_id": "client-id",
    "authority": "https://login.microsoftonline.com/organizations",
    "scopes": ["User.ReadBasic.All"],
    "report_domain": "societe.fr",
}


@unittest.skipIf(DISPLAY_ERROR, f"Aucun affichage Tk disponible : {DISPLAY_ERROR}")
class DesktopAppTests(unittest.TestCase):
    def setUp(self):
        """Isole les fichiers de configuration et les boîtes de dialogue."""
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.swile_config = self.root / "swile.config.json"
        self.ad_config = self.root / "liste_salarie_active_directory.config.json"
        self.stack = ExitStack()
        self.stack.enter_context(
            patch("services.active_directory_config.project_root", return_value=self.root)
        )
        self.stack.enter_context(
            patch("services.swile_service.SWILE_CONFIG_PATH", self.swile_config)
        )
        self.stack.enter_context(
            patch(
                "services.swile_service.LEGACY_SWILE_CONFIG_PATH",
                self.root / "legacy.json",
            )
        )
        self.messagebox = {}
        for module in ("swile_config_editor", "active_directory_panel"):
            self.messagebox[module] = self.stack.enter_context(
                patch(f"app.ui.{module}.messagebox")
            )
        self.app = None

    def tearDown(self):
        """Détruit la fenêtre puis restaure l’environnement."""
        if self.app is not None:
            self.app.progress_bar.stop()
            for job in self.app.tk.splitlist(self.app.tk.call("after", "info")):
                self.app.after_cancel(job)
            self.app.destroy()
        self.stack.close()
        self.temporary_directory.cleanup()

    def create_app(self):
        self.app = CSEFileManager()
        self.app.update()
        return self.app

    def test_window_is_built_with_version_tabs_and_filters(self):
        """Vérifie le titre versionné, les onglets et les sections de filtres."""
        app = self.create_app()
        self.assertIn(__version__, app.title())
        self.assertEqual(
            [app.tabs.tab(tab, "text") for tab in app.tabs.tabs()],
            ["liste_salarie_active_directory", "swile_active_directory"],
        )
        self.assertEqual(set(app.addition_filter_sections), {"email", "poste"})

    def test_work_location_mapping_round_trip(self):
        """Vérifie l’enregistrement puis le rechargement du mapping des lieux."""
        app = self.create_app()
        app.work_location_default_value.set("Ailleurs")
        app._add_work_location_rule("paris; 133", "Paris 133", mark_dirty=True)
        self.assertTrue(app.work_location_mapping_dirty)

        app._save_work_location_mapping()

        saved = json.loads(self.swile_config.read_text(encoding="utf-8"))
        self.assertEqual(saved["default_value"], "Ailleurs")
        self.assertIn(
            {"patterns": [["paris", "133"]], "value": "Paris 133"},
            saved["rules"],
        )
        self.assertFalse(app.work_location_mapping_dirty)

        app._load_work_location_mapping()
        patterns = [row["pattern"].get() for row in app.work_location_mapping_rows]
        self.assertIn("paris; 133", patterns)

    def test_incomplete_rule_is_rejected_without_writing_file(self):
        """Vérifie qu’une règle sans valeur n’est pas enregistrée."""
        app = self.create_app()
        app._add_work_location_rule("lille", "", mark_dirty=True)

        app._save_work_location_mapping()

        self.messagebox["swile_config_editor"].showerror.assert_called_once()
        self.assertFalse(self.swile_config.exists())

    def test_missing_active_directory_config_opens_the_section(self):
        """Vérifie que la configuration absente déplie le panneau."""
        app = self.create_app()
        self.assertTrue(app.active_directory_config_expanded.get())
        self.assertIn(
            "à renseigner", app.active_directory_config_status.get()
        )

    def test_valid_active_directory_config_is_collapsed(self):
        """Vérifie que la configuration valide est chargée et repliée."""
        self.ad_config.write_text(json.dumps(AD_CONFIG), encoding="utf-8")
        app = self.create_app()
        self.assertFalse(app.active_directory_config_expanded.get())
        self.assertEqual(
            app.active_directory_config_vars["client_id"].get(), "client-id"
        )
        self.assertEqual(
            app.active_directory_scopes_editor.get("1.0", "end-1c"),
            "User.ReadBasic.All",
        )

    def test_active_directory_config_is_saved_from_fields(self):
        """Vérifie l’enregistrement des champs et des scopes saisis."""
        app = self.create_app()
        for field, value in AD_CONFIG.items():
            if field != "scopes":
                app.active_directory_config_vars[field].set(value)
        app.active_directory_scopes_editor.delete("1.0", "end")
        app.active_directory_scopes_editor.insert("1.0", "A.Read\n\n B.Read \n")

        app._save_active_directory_config()

        saved = json.loads(self.ad_config.read_text(encoding="utf-8"))
        self.assertEqual(saved["scopes"], ["A.Read", "B.Read"])
        self.assertEqual(saved["start_user_email"], "start@societe.fr")
        self.assertFalse(app.active_directory_config_dirty)

    def test_example_active_directory_config_is_not_saved(self):
        """Vérifie le refus d’une configuration contenant les valeurs d’exemple."""
        app = self.create_app()
        app.active_directory_config_vars["start_user_email"].set(
            "prenom.nom@exemple.fr"
        )

        app._save_active_directory_config()

        self.messagebox["active_directory_panel"].showerror.assert_called_once()
        self.assertFalse(self.ad_config.exists())

    def test_progress_bar_fills_and_holds_on_completion(self):
        """Vérifie la progression déterminée puis le remplissage final."""
        app = self.create_app()
        app._start_active_directory_progress()
        app._update_active_directory_progress(50, 200, "collecting")
        self.assertEqual(str(app.progress_bar.cget("mode")), "determinate")
        self.assertIn("25 %", app.progress_label.get())

        app._update_active_directory_progress(120, 200, "complete")
        self.assertEqual(
            float(app.progress_bar.cget("value")),
            float(app.progress_bar.cget("maximum")),
        )
        self.assertIn("120", app.progress_label.get())

    def test_successful_active_directory_run_fills_progress_bar_on_finish(self):
        """Vérifie que la fin réussie fige la barre à son maximum."""
        app = self.create_app()
        app.current_action = "active_directory"
        app.progress_count = 50
        app.progress_bar.configure(mode="determinate", maximum=200, value=50)

        with (
            patch.object(app, "_set_run_buttons_state"),
            patch.object(app, "_set_config_controls_state"),
            patch.object(app, "_set_output"),
            patch.object(app, "_refresh_file_labels"),
            patch.object(app, "_set_previous_export_section_default_visibility"),
        ):
            app._finish_run("", "", 0)

        self.assertEqual(str(app.progress_bar.cget("mode")), "determinate")
        self.assertEqual(
            float(app.progress_bar.cget("value")),
            float(app.progress_bar.cget("maximum")),
        )
        self.assertIn("Collecte terminée", app.progress_label.get())


if __name__ == "__main__":
    unittest.main()
