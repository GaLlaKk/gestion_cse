import os
import threading
import tkinter as tk
import traceback
from contextlib import redirect_stderr, redirect_stdout
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk

from tkinterdnd2 import TkinterDnD

from app.ui.constants import (
    OUTPUT_DIRECTORY,
    ACTIVE_DIRECTORY_OUTPUT,
    TITLES,
)
from app.ui.active_directory_panel import ActiveDirectoryPanelMixin
from app.ui.input_files import InputFilesMixin
from app.ui.swile_config_editor import SwileConfigEditorMixin
from services.version import __version__
from services.swile_service import (
    execute_swile_action,
)
from services.active_directory_export import run_active_directory_export

class _OutputWriter:
    def __init__(self, app):
        """Relie les sorties du traitement au panneau de résultats Tkinter."""
        self.app = app
        self.parts = []

    def write(self, text):
        """Mémorise le texte et programme son affichage dans l’interface."""
        if text:
            self.parts.append(text)
            self.app.after(0, self.app._append_output, text)
        return len(text)

    def flush(self):
        """Fournit l’opération attendue par les flux de sortie."""
        pass

    def getvalue(self):
        """Retourne l’ensemble du texte écrit pendant le traitement."""
        return "".join(self.parts)


class CSEFileManager(
    InputFilesMixin,
    SwileConfigEditorMixin,
    ActiveDirectoryPanelMixin,
    TkinterDnD.Tk,
):
    def __init__(self):
        """Construit la fenêtre, ses onglets et les panneaux de suivi."""
        super().__init__()
        self.title(f"Gestion des fichiers CSE — {__version__}")
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = min(1500, max(960, int(screen_width * 0.9)))
        window_height = min(900, max(620, int(screen_height * 0.84)))
        self.geometry(f"{window_width}x{window_height}")
        self.minsize(960, 620)
        self.configure(padx=14, pady=12)
        self.file_labels = {}
        self.run_buttons = []
        self.is_running = False
        self.current_action = None
        self.device_code_dialog = None
        self.download_photos = tk.BooleanVar(value=False)
        self.addition_filter_rows = {}
        self.addition_filter_default_values = {}
        self.addition_filter_default_entries = {}
        self.addition_filter_rules_frames = {}
        self.addition_filter_add_buttons = {}
        self.addition_filter_toggle_controls = {}
        self.addition_filter_expanded = {
            "email": tk.BooleanVar(value=False),
            "poste": tk.BooleanVar(value=False),
        }
        self.addition_filter_sections = {}
        self.work_location_mapping_controls = []
        self.scrollable_tab_areas = {}
        self.bind_all("<MouseWheel>", self._on_tab_mousewheel)
        self.bind_all("<Button-4>", self._on_tab_mousewheel)
        self.bind_all("<Button-5>", self._on_tab_mousewheel)
        self._build_heading()
        self._build_layout()
        self._build_results_panel()
        active_directory_tab = tk.Frame(self.tabs)
        swile_tab = tk.Frame(self.tabs, padx=12, pady=12)
        self.tabs.add(active_directory_tab, text="liste_salarie_active_directory")
        self.tabs.add(swile_tab, text="swile_active_directory")
        self._build_active_directory_tab(active_directory_tab)
        self._build_swile_tab(swile_tab)
        self._load_work_location_mapping()
        self._load_active_directory_config()
        self._refresh_file_labels()
        self._set_previous_export_section_default_visibility()
        self.after(100, self._position_main_pane_sash)

    def _build_heading(self):
        """Construit l’en-tête de la fenêtre."""
        heading = tk.Frame(self)
        heading.pack(fill="x", pady=(0, 10))
        tk.Label(
            heading,
            text="Gestion des fichiers CSE",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            heading,
            text=(
                "Choisissez un traitement, vérifiez les fichiers requis, "
                "puis lancez l’action. Vous pouvez déposer un CSV ou le "
                "sélectionner avec « Parcourir »."
            ),
            justify="left",
            wraplength=1100,
            fg="#555555",
        ).pack(anchor="w", pady=(3, 0))

    def _build_layout(self):
        """Construit le panneau principal et le conteneur d’onglets."""
        self.main_pane = tk.PanedWindow(
            self,
            orient="horizontal",
            sashwidth=6,
            sashrelief="raised",
            bd=0,
            bg=self.cget("bg"),
        )
        self.main_pane.pack(fill="both", expand=True)
        workspace = tk.Frame(self.main_pane)
        self.tabs = ttk.Notebook(workspace)
        self.tabs.pack(fill="both", expand=True)
        self.main_pane.add(workspace, minsize=620, stretch="always")

    def _build_results_panel(self):
        """Construit le panneau de suivi, de progression et de résultats."""
        results_panel = tk.LabelFrame(
            self.main_pane,
            text="Suivi et résultats",
            padx=10,
            pady=8,
        )
        results_panel.pack_propagate(False)
        self.main_pane.add(results_panel, minsize=260, width=350, stretch="last")
        tk.Label(
            results_panel,
            text="État",
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).pack(fill="x")
        self.status = tk.StringVar(value="Vérification des fichiers d’entrée…")
        tk.Label(
            results_panel,
            textvariable=self.status,
            anchor="nw",
            justify="left",
            wraplength=320,
            fg="#444444",
        ).pack(fill="x", pady=(3, 10))
        self.progress_frame = tk.Frame(results_panel)
        self.progress_label = tk.StringVar(value="")
        tk.Label(
            self.progress_frame,
            textvariable=self.progress_label,
            anchor="w",
            justify="left",
            wraplength=320,
        ).pack(fill="x", pady=(0, 3))
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            mode="indeterminate",
            maximum=100,
        )
        self.progress_bar.pack(fill="x")
        self.progress_count = 0
        tk.Label(
            results_panel,
            text="Détail du dernier traitement",
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).pack(fill="x")
        self.output = ScrolledText(
            results_panel,
            height=8,
            wrap="word",
            state="disabled",
        )
        self.output.pack(fill="both", expand=True, pady=(4, 8))

    def _build_active_directory_tab(self, active_directory_tab):
        """Construit l’onglet de génération de l’export Active Directory."""
        active_directory_content = self._create_scrollable_tab(
            active_directory_tab, padx=12, pady=12
        )

        tk.Label(
            active_directory_content,
            text=(
                "Génère la liste des salariés depuis Microsoft Active Directory. "
                "Une connexion Microsoft peut être demandée dans cette fenêtre."
            ),
            anchor="w",
            justify="left",
            wraplength=900,
            fg="#555555",
        ).pack(fill="x", pady=(0, 10))
        active_directory_columns = tk.Frame(active_directory_content)
        active_directory_columns.pack(fill="both", expand=True)
        active_directory_primary = tk.Frame(active_directory_columns)
        active_directory_primary.pack(fill="x")
        active_directory_optional = tk.Frame(active_directory_columns)
        active_directory_optional.pack(fill="x", pady=(4, 0))
        generation_section = tk.LabelFrame(
            active_directory_primary,
            text="Générer l’export",
            padx=10,
            pady=8,
        )
        generation_section.pack(fill="x", pady=(0, 8))
        self._create_run_button(
            generation_section,
            "Générer la liste Active Directory",
            "active_directory",
        )
        ttk.Checkbutton(
            generation_section,
            text="Récupérer les photos (les photos déjà téléchargées seront conservées)",
            variable=self.download_photos,
        ).pack(anchor="w", pady=(3, 0))
        self._build_active_directory_config_section(active_directory_primary)
        self._build_previous_export_section(active_directory_optional)

    def _build_swile_tab(self, swile_tab):
        """Construit l’onglet Swile et ses sous-onglets."""
        swile_subtabs = ttk.Notebook(swile_tab)
        swile_subtabs.pack(fill="both", expand=True)
        compare_lists_tab = tk.Frame(swile_subtabs)
        location_values_tab = tk.Frame(swile_subtabs)
        swile_subtabs.add(compare_lists_tab, text="Comparer les listes")
        swile_subtabs.add(
            location_values_tab, text="Valeurs de lieu de travail"
        )
        compare_lists_content = self._create_scrollable_tab(
            compare_lists_tab, padx=8, pady=8
        )
        location_values_content = self._create_scrollable_tab(
            location_values_tab, padx=8, pady=8
        )

        compare_section = tk.Frame(compare_lists_content, padx=10, pady=8)
        compare_section.pack(fill="both", expand=True, pady=4)
        compare_section.columnconfigure(0, weight=1, uniform="compare")
        compare_section.columnconfigure(1, weight=1, uniform="compare")
        self._create_input_card("swile", compare_section).grid(
            row=0, column=0, sticky="nsew", padx=(0, 6), pady=4
        )
        self._create_input_card("active_directory", compare_section).grid(
            row=0, column=1, sticky="nsew", padx=(6, 0), pady=4
        )
        compare_actions = tk.Frame(compare_section)
        compare_actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._create_run_button(
            compare_actions,
            "Comparer les listes et préparer les ajouts Swile",
            "all",
        )
        self._build_addition_filter_toggles(compare_section)
        self._build_location_values_section(location_values_content)
        self._create_work_location_mapping_editor(location_values_content)

    def _create_scrollable_tab(self, parent, padx=0, pady=0):
        """Ajoute un contenu défilant verticalement dans un onglet."""
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            parent,
            orient="vertical",
            command=canvas.yview,
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        content = tk.Frame(canvas, padx=padx, pady=pady)
        content_window = canvas.create_window(
            (0, 0), window=content, anchor="nw"
        )
        content.bind(
            "<Configure>",
            lambda _event: canvas.configure(
                scrollregion=canvas.bbox("all")
            ),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(
                content_window, width=event.width
            ),
        )
        self.scrollable_tab_areas[str(content)] = canvas
        return content

    def _on_tab_mousewheel(self, event):
        """Fait défiler l’onglet sous le pointeur avec la molette."""
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            canvas = self.scrollable_tab_areas.get(str(widget))
            if canvas is not None:
                if event.num == 4:
                    scroll_units = -1
                elif event.num == 5:
                    scroll_units = 1
                else:
                    scroll_units = -1 if event.delta > 0 else 1
                    if abs(event.delta) >= 120:
                        scroll_units = -int(event.delta / 120)
                canvas.yview_scroll(scroll_units, "units")
                return "break"
            widget = widget.master
        return None

    def _position_main_pane_sash(self):
        """Place le séparateur initial pour réserver une largeur aux résultats."""
        pane_width = self.main_pane.winfo_width()
        if pane_width > 0:
            sash_position = max(
                620,
                min(pane_width - 260, pane_width - 360),
            )
            self.main_pane.sash_place(0, sash_position, 0)

    def _create_run_button(self, parent, label, action):
        """Crée une rangée d’action avec l’accès aux résultats associés."""
        actions = tk.Frame(parent)
        actions.pack(fill="x", pady=(0, 4))
        button = tk.Button(
            actions,
            text=f"▶  {label}",
            command=lambda selected=action: self._run(selected),
            bg="#176b35",
            fg="#ffffff",
            activebackground="#12552a",
            activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
        )
        button.pack(side="left", anchor="w")
        self.run_buttons.append(button)
        tk.Button(
            actions,
            text="📂  Ouvrir le dossier de résultats",
            command=self._open_output_directory,
            bg="#0a4f8a",
            fg="#ffffff",
            activebackground="#073b68",
            activeforeground="#ffffff",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=12,
            pady=7,
            cursor="hand2",
        ).pack(side="left", padx=(8, 0), anchor="w")

    def _run(self, action):
        """Vérifie les entrées et démarre le traitement dans un thread."""
        if self.is_running:
            return
        if action == "location_values" and self.work_location_mapping_dirty:
            if not messagebox.askyesno(
                "Mapping non enregistré",
                "Enregistrer le mapping modifié avant de générer le fichier ?",
                parent=self,
            ):
                return
            self._save_work_location_mapping()
            if self.work_location_mapping_dirty:
                return
        try:
            if action == "active_directory":
                previous_export_path = self._current_file(
                    "active_directory_previous"
                )
                self.is_running = True
                self.current_action = action
                self.status.set("Collecte Active Directory en cours…")
                self._set_run_buttons_state("disabled")
                self._set_config_controls_state("disabled")
                self._start_active_directory_progress()
                self._set_output(
                    "Démarrage de la collecte Active Directory…\n"
                    "Les demandes de connexion apparaîtront ci-dessous.\n"
                )
                threading.Thread(
                    target=self._run_worker,
                    args=(
                        action,
                        None,
                        None,
                        None,
                        self.download_photos.get(),
                        previous_export_path,
                    ),
                    daemon=True,
                ).start()
                return

            self.progress_frame.pack_forget()
            swile_path = self._current_file("swile")
            active_directory_path = self._current_file("active_directory")
            actions_requiring_swile = {
                "compare",
                "additions",
                "all",
                "location_values",
            }
            template_path = None
            required_inputs = []
            if action in actions_requiring_swile:
                required_inputs.append((swile_path, TITLES["swile"]))
            required_inputs.append(
                (active_directory_path, TITLES["active_directory"])
            )
            missing = [
                label for path, label in required_inputs if path is None
            ]
            if missing:
                messagebox.showerror(
                    "Fichiers manquants",
                    "Ajoutez les fichiers suivants dans les zones prévues :\n"
                    + "\n".join(f"• {name}" for name in missing),
                    parent=self,
                )
                return

            self.is_running = True
            self.current_action = action
            self.status.set("Traitement en cours…")
            self._set_run_buttons_state("disabled")
            self._set_config_controls_state("disabled")
            self._set_output("Traitement en cours…\n")
            threading.Thread(
                target=self._run_worker,
                args=(action, swile_path, active_directory_path, template_path),
                daemon=True,
            ).start()
        except OSError as error:
            self._finish_run("", str(error), 1)

    def _run_worker(
        self,
        action,
        swile_path,
        active_directory_path,
        template_path,
        download_photos=False,
        previous_export_path=None,
    ):
        """Exécute l’export AD ou l’action Swile hors du thread graphique."""
        output_writer = _OutputWriter(self)
        active_directory_export_path = None
        try:
            with redirect_stdout(output_writer), redirect_stderr(output_writer):
                if action == "active_directory":
                    active_directory_export_path = run_active_directory_export(
                        on_device_code=self._schedule_device_code_dialog,
                        download_photos=download_photos,
                        previous_export_path=previous_export_path,
                        on_progress=self._schedule_active_directory_progress,
                    )
                else:
                    result = execute_swile_action(
                        action,
                        swile_path,
                        active_directory_path,
                        template_path=template_path,
                    )
                    print(result)
            self.after(
                0,
                lambda: self._finish_run(
                    output_writer.getvalue(),
                    "",
                    0,
                    active_directory_export_path=(
                        active_directory_export_path
                        if action == "active_directory"
                        else None
                    ),
                ),
            )
        except Exception:
            error = traceback.format_exc()
            output_writer.write(error)
            self.after(0, lambda message=error: self._finish_run("", message, 1))

    def _finish_run(
        self,
        stdout,
        stderr,
        returncode,
        active_directory_export_path=None,
    ):
        """Rétablit l’interface et affiche le résultat ou l’erreur du traitement."""
        completed_action = self.current_action
        if self.device_code_dialog is not None:
            if self.device_code_dialog.winfo_exists():
                self.device_code_dialog.destroy()
            self.device_code_dialog = None
        self.is_running = False
        self._set_run_buttons_state("normal")
        self._set_config_controls_state("normal")
        if self.progress_bar.cget("mode") == "indeterminate":
            self.progress_bar.stop()
        if completed_action == "active_directory" and returncode == 0:
            self._update_active_directory_progress(
                self.progress_count,
                int(float(self.progress_bar.cget("maximum"))),
                "complete",
            )
        if self.current_action == "active_directory" and returncode != 0:
            self.progress_label.set(
                "Collecte interrompue après "
                f"{self.progress_count} personne(s)."
            )
        self.current_action = None
        result = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
        if not result:
            result = "Traitement terminé." if returncode == 0 else "Échec du traitement."
        self._set_output(result)
        self.status.set(
            "Traitement terminé." if returncode == 0 else "Le traitement a échoué."
        )
        self._refresh_file_labels()
        if completed_action == "active_directory" and returncode == 0:
            self._set_previous_export_section_default_visibility()
            if active_directory_export_path is not None:
                self._copy_input_file(
                    active_directory_export_path,
                    "active_directory",
                )
        if returncode != 0:
            messagebox.showerror(
                "Échec du traitement",
                "Une erreur est survenue. Consultez le détail ci-dessous.",
                parent=self,
            )

    def _set_run_buttons_state(self, state):
        """Active ou désactive tous les boutons de lancement."""
        for button in self.run_buttons:
            button.configure(state=state)

    def _set_config_controls_state(self, state):
        """Active ou désactive les deux formulaires de configuration."""
        for control in (
            self.active_directory_config_controls
            + self.work_location_mapping_controls
        ):
            control.configure(state=state)
        if state == "normal":
            self._refresh_work_location_rule_rows()
            for filter_name in self.addition_filter_rows:
                self._refresh_addition_filter_rule_rows(filter_name)

    def _set_output(self, text):
        """Remplace le contenu du panneau de résultats."""
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def _append_output(self, text):
        """Ajoute une sortie au panneau et fait défiler jusqu’à la fin."""
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _open_output_directory(self):
        """Ouvre le dossier de résultats correspondant à l’onglet actif."""
        output_directory = (
            ACTIVE_DIRECTORY_OUTPUT
            if self.tabs.index("current") == 0
            else OUTPUT_DIRECTORY
        )
        if output_directory.exists():
            os.startfile(output_directory)
        else:
            messagebox.showinfo(
                "Dossier non disponible",
                f"Le dossier de sortie n’existe pas encore : {output_directory}",
                parent=self,
            )

def main():
    """Lance la fenêtre principale et sa boucle événementielle Tkinter."""
    app = CSEFileManager()
    app.mainloop()


if __name__ == "__main__":
    main()
