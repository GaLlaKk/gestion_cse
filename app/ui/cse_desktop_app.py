import json
import os
import shutil
import threading
import tkinter as tk
import traceback
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk

from tkinterdnd2 import DND_FILES, TkinterDnD

from services.csv_files import read_csv
from services.paths import bundled_resource, project_root
from services.swile_service import execute_swile_action
from services.active_directory_export import (
    get_config_path,
    run_active_directory_export,
    save_active_directory_config,
    validate_config,
)

ROOT_DIRECTORY = project_root()
SWILE_DIRECTORY = ROOT_DIRECTORY / "swile_active_directory"
INPUT_DIRECTORY = SWILE_DIRECTORY / "in"
OUTPUT_DIRECTORY = SWILE_DIRECTORY / "out"
ACTIVE_DIRECTORY_OUTPUT = ROOT_DIRECTORY / "liste_salarie_active_directory" / "out"
ACTIVE_DIRECTORY_INPUT = ROOT_DIRECTORY / "liste_salarie_active_directory" / "in"
REQUIRED_COLUMNS = {
    "swile": {"Prénom", "Nom", "Email", "Matricule"},
    "active_directory": {"Nom", "Email", "Identifiant", "Poste"},
    "active_directory_previous": {"Nom", "Email", "Identifiant", "Poste"},
    "template": {"Prénom", "Nom", "Email", "Matricule"},
}
TITLES = {
    "swile": "FICHIER SWILE - Liste actuelle des salariés",
    "active_directory": "FICHIER ACTIVE DIRECTORY - Export des salariés",
    "active_directory_previous": "FICHIER ACTIVE DIRECTORY PRECEDENT (optionnel)",
    "template": "MODELE SWILE - CSV d'import",
}
INSTRUCTIONS = {
    "swile": "CSV SWILE ATTENDU ici (séparateur « ; »).",
    "active_directory": "CSV ACTIVE DIRECTORY ATTENDU ici (séparateur « , »).",
    "active_directory_previous": (
        "CSV ACTIVE DIRECTORY PRECEDENT (optionnel) pour compléter "
        "les comptes manquants s’ils sont toujours visibles."
    ),
    "template": "MODELE SWILE ATTENDU ici (séparateur « ; »).",
}
INPUT_HIGHLIGHTS = {
    "swile": ("SWILE", "#0a4f8a"),
    "active_directory": ("ACTIVE DIRECTORY", "#176b35"),
    "active_directory_previous": ("ACTIVE DIRECTORY PRECEDENT", "#0f5b7a"),
    "template": ("MODELE SWILE", "#71f19e"),
}
DELIMITERS = {
    "swile": ";",
    "active_directory": ",",
    "active_directory_previous": ",",
    "template": ";",
}
DEFAULT_TEMPLATE_FILE = (
    "collaborators_template_090d2568-c182-4cf4-8b3a-81fefee3a297.csv"
)
ACTIVE_DIRECTORY_CONFIG_FIELDS = (
    ("start_user_email", "Adresse de départ"),
    ("client_id", "Identifiant de l’application"),
    ("authority", "Autorité Microsoft"),
    ("report_domain", "Domaine de rapport"),
)


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


class CSEFileManager(TkinterDnD.Tk):
    def __init__(self):
        """Construit la fenêtre, ses onglets et les panneaux de suivi."""
        super().__init__()
        self.title("Gestion des fichiers CSE")
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

        active_directory_tab = tk.Frame(self.tabs, padx=12, pady=12)
        swile_tab = tk.Frame(self.tabs, padx=12, pady=12)
        self.tabs.add(active_directory_tab, text="liste_salarie_active_directory")
        self.tabs.add(swile_tab, text="swile_active_directory")

        tk.Label(
            active_directory_tab,
            text=(
                "Génère la liste des salariés depuis Microsoft Active Directory. "
                "Une connexion Microsoft peut être demandée dans cette fenêtre."
            ),
            anchor="w",
            justify="left",
            wraplength=900,
            fg="#555555",
        ).pack(fill="x", pady=(0, 10))
        active_directory_columns = tk.Frame(active_directory_tab)
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
        config_container = tk.Frame(active_directory_primary)
        config_container.pack(fill="x", pady=(0, 8))
        self.active_directory_config_expanded = tk.BooleanVar(value=False)
        self.active_directory_config_toggle = ttk.Checkbutton(
            config_container,
            text="Afficher la configuration Active Directory",
            variable=self.active_directory_config_expanded,
            command=self._toggle_active_directory_config,
        )
        self.active_directory_config_toggle.pack(anchor="w")
        config_section = tk.LabelFrame(
            config_container,
            text="Paramètres Active Directory",
            padx=10,
            pady=7,
        )
        self.active_directory_config_section = config_section
        tk.Label(
            config_section,
            text=f"Fichier : {get_config_path()}",
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(fill="x", pady=(0, 4))
        config_fields = tk.Frame(config_section)
        config_fields.pack(fill="x", expand=True)
        config_fields.columnconfigure(1, weight=1)
        config_fields.columnconfigure(3, weight=1)
        self.active_directory_config_vars = {}
        self.active_directory_config_controls = []
        for index, (field, label) in enumerate(
            ACTIVE_DIRECTORY_CONFIG_FIELDS
        ):
            row = (index // 2) * 2
            column = (index % 2) * 2
            tk.Label(config_fields, text=label, anchor="w").grid(
                row=row,
                column=column,
                sticky="w",
                padx=(0, 6 if column == 0 else 12),
                pady=(2, 0),
            )
            value = tk.StringVar()
            entry = tk.Entry(config_fields, textvariable=value)
            entry.grid(
                row=row + 1,
                column=column,
                columnspan=2,
                sticky="ew",
                padx=(0, 12 if column == 0 else 0),
                pady=(0, 4),
            )
            entry.bind("<KeyRelease>", self._mark_active_directory_config_dirty)
            entry.bind("<<Paste>>", self._mark_active_directory_config_dirty)
            self.active_directory_config_vars[field] = value
            self.active_directory_config_controls.append(entry)

        scopes_row = len(ACTIVE_DIRECTORY_CONFIG_FIELDS)
        tk.Label(
            config_fields,
            text="Autorisations (scopes, une par ligne)",
            anchor="w",
        ).grid(row=scopes_row, column=0, columnspan=4, sticky="w")
        self.active_directory_scopes_editor = ScrolledText(
            config_fields,
            height=3,
            wrap="word",
        )
        self.active_directory_scopes_editor.grid(
            row=scopes_row + 1,
            column=0,
            columnspan=4,
            sticky="ew",
        )
        self.active_directory_scopes_editor.bind(
            "<KeyRelease>", self._mark_active_directory_config_dirty
        )
        self.active_directory_scopes_editor.bind(
            "<<Paste>>", self._mark_active_directory_config_dirty
        )
        self.active_directory_config_controls.append(
            self.active_directory_scopes_editor
        )
        self.active_directory_config_dirty = False
        config_actions = tk.Frame(config_section)
        config_actions.pack(fill="x", pady=(5, 0))
        self.active_directory_config_status = tk.StringVar(value="")
        save_config_button = tk.Button(
            config_actions,
            text="Enregistrer la configuration",
            command=self._save_active_directory_config,
        )
        save_config_button.pack(side="left")
        reload_config_button = tk.Button(
            config_actions,
            text="Recharger",
            command=self._load_active_directory_config,
        )
        reload_config_button.pack(side="left", padx=(6, 0))
        self.active_directory_config_controls.extend(
            (
                self.active_directory_config_toggle,
                save_config_button,
                reload_config_button,
            )
        )
        tk.Label(
            config_actions,
            textvariable=self.active_directory_config_status,
            anchor="e",
            fg="#555555",
        ).pack(side="right", fill="x", expand=True, padx=(8, 0))
        previous_export_section = tk.LabelFrame(
            active_directory_optional,
            text="Complément de configuration facultatif",
            padx=10,
            pady=8,
        )
        previous_export_section.pack(fill="x", pady=(0, 8))
        tk.Label(
            previous_export_section,
            text=(
                "Un export précédent peut servir à conserver les comptes "
                "encore visibles qui ne sont pas retournés par la collecte."
            ),
            anchor="w",
            justify="left",
            wraplength=380,
            fg="#555555",
        ).pack(fill="x", pady=(0, 4))
        self._create_input_card(
            "active_directory_previous", previous_export_section
        ).pack(fill="x", pady=4)
        tk.Label(
            active_directory_optional,
            text=f"CSV créé dans : {ACTIVE_DIRECTORY_OUTPUT}",
            anchor="w",
            justify="left",
            wraplength=480,
            fg="#555555",
        ).pack(fill="x", pady=(8, 0))
        tk.Label(
            active_directory_optional,
            text=f"Journaux : {ROOT_DIRECTORY / 'log'}",
            anchor="w",
            justify="left",
            wraplength=480,
            fg="#555555",
        ).pack(fill="x", pady=(4, 0))

        swile_subtabs = ttk.Notebook(swile_tab)
        swile_subtabs.pack(fill="both", expand=True)
        compare_lists_tab = tk.Frame(swile_subtabs, padx=8, pady=8)
        location_values_tab = tk.Frame(swile_subtabs, padx=8, pady=8)
        swile_subtabs.add(compare_lists_tab, text="Comparer les listes")
        swile_subtabs.add(
            location_values_tab, text="Valeurs de lieu de travail"
        )

        compare_section = tk.Frame(compare_lists_tab, padx=10, pady=8)
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
        
        location_values_section = tk.LabelFrame(
            location_values_tab,
            text="Générer les valeurs de lieu de travail",
            padx=10,
            pady=8,
        )
        location_values_section.pack(fill="x", pady=(0, 4))
        self._create_run_button(
            location_values_section,
            "Générer le CSV Prénom / Nom de famille / E-mail / Matricule / Valeur",
            "location_values",
        )
        tk.Label(
            location_values_section,
            text=(
                "Cette étape utilise le fichier ACTIVE DIRECTORY déposé dans "
                "l'onglet « Comparer les listes » "
                "et produit un CSV avec les colonnes Prénom, Nom de famille, "
                "E-mail, Matricule et Valeur."
            ),
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(fill="x", pady=(2, 2))
        tk.Label(
            location_values_section,
            text=(
                "Valeurs générées automatiquement : Paris 145, Lille 5.9, "
                "Paris 133 ou Autre."
            ),
            anchor="w",
            justify="left",
            wraplength=760,
            fg="#555555",
        ).pack(fill="x")

        self._load_active_directory_config()
        self._refresh_file_labels()
        self.after(100, self._position_main_pane_sash)

    def _position_main_pane_sash(self):
        """Place le séparateur initial pour réserver une largeur aux résultats."""
        pane_width = self.main_pane.winfo_width()
        if pane_width > 0:
            sash_position = max(
                620,
                min(pane_width - 260, pane_width - 360),
            )
            self.main_pane.sash_place(0, sash_position, 0)

    def _load_active_directory_config(self):
        """Charge les paramètres AD et ouvre le panneau si la config est invalide."""
        if self.active_directory_config_dirty and not messagebox.askyesno(
            "Recharger la configuration ?",
            "Les modifications non enregistrées seront perdues. Continuer ?",
            parent=self,
        ):
            return
        config_path = get_config_path()
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            if not isinstance(config, dict):
                raise ValueError(
                    "La configuration doit contenir un objet JSON."
                )
            for field, _ in ACTIVE_DIRECTORY_CONFIG_FIELDS:
                value = config.get(field, "")
                self.active_directory_config_vars[field].set(
                    value if isinstance(value, str) else json.dumps(value)
                )
            scopes = config.get("scopes", [])
            if isinstance(scopes, list):
                scopes_text = "\n".join(str(scope) for scope in scopes)
            else:
                scopes_text = json.dumps(scopes)
            self.active_directory_scopes_editor.delete("1.0", "end")
            self.active_directory_scopes_editor.insert("1.0", scopes_text)
            self.active_directory_config_dirty = False
            try:
                validate_config(config, config_path)
            except ValueError as error:
                self.active_directory_config_status.set(
                    f"Configuration à compléter : {error}"
                )
                self.active_directory_config_expanded.set(True)
            else:
                self.active_directory_config_status.set(
                    "Configuration chargée."
                )
                self.active_directory_config_expanded.set(False)
        except (OSError, UnicodeError, ValueError) as error:
            self.active_directory_config_status.set(
                f"Configuration à renseigner : {error}"
            )
            self.active_directory_config_expanded.set(True)
        self._toggle_active_directory_config()

    def _toggle_active_directory_config(self):
        """Affiche ou replie les paramètres Active Directory."""
        if self.active_directory_config_expanded.get():
            if not self.active_directory_config_section.winfo_manager():
                self.active_directory_config_section.pack(
                    fill="x", pady=(0, 8)
                )
            self.active_directory_config_toggle.configure(
                text="Masquer la configuration Active Directory"
            )
        else:
            self.active_directory_config_section.pack_forget()
            self.active_directory_config_toggle.configure(
                text="Afficher la configuration Active Directory"
            )

    def _save_active_directory_config(self):
        """Valide et enregistre les champs de configuration Active Directory."""
        config = {
            field: value.get()
            for field, value in self.active_directory_config_vars.items()
        }
        config["scopes"] = [
            scope.strip()
            for scope in self.active_directory_scopes_editor.get(
                "1.0", "end-1c"
            ).splitlines()
            if scope.strip()
        ]
        contents = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
        try:
            save_active_directory_config(contents)
        except (OSError, UnicodeError, ValueError) as error:
            self.active_directory_config_status.set("Enregistrement impossible.")
            messagebox.showerror(
                "Configuration invalide",
                str(error),
                parent=self,
            )
            return
        self.active_directory_config_dirty = False
        self.active_directory_config_status.set("Configuration enregistrée.")

    def _mark_active_directory_config_dirty(self, event):
        """Signale que l’utilisateur a modifié un champ de configuration."""
        if event.widget is not None:
            self.active_directory_config_dirty = True

    def _create_run_button(self, parent, label, action):
        """Crée une rangée d’action avec l’accès aux résultats associés."""
        actions = tk.Frame(parent)
        actions.pack(fill="x", pady=(0, 4))
        button = tk.Button(
            actions,
            text=label,
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
            text="Ouvrir le dossier de résultats",
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

    def _create_input_card(self, kind, parent):
        """Construit une carte de sélection ou de dépôt pour un fichier CSV."""
        card = tk.LabelFrame(parent, text=TITLES[kind], padx=10, pady=9)

        description = tk.Frame(card)
        description.pack(fill="x", expand=True)
        highlight_text, highlight_background = INPUT_HIGHLIGHTS[kind]
        tk.Label(
            description,
            text=f"FICHIER ATTENDU : {highlight_text}",
            anchor="w",
            justify="left",
            bg=highlight_background,
            fg="#ffffff",
            font=("Segoe UI", 9, "bold"),
            padx=6,
            pady=2,
        ).pack(anchor="w", pady=(0, 5))
        tk.Label(
            description,
            text=INSTRUCTIONS[kind],
            anchor="w",
            justify="left",
            wraplength=420,
        ).pack(fill="x", pady=(0, 3))
        tk.Label(
            description,
            text=(
                "Destination : "
                f"{self._input_directory_for_kind(kind)} "
                "(nom d’origine conservé)"
            ),
            anchor="w",
            justify="left",
            fg="#555555",
            wraplength=420,
        ).pack(fill="x")

        label = tk.Label(
            description,
            text="Aucun fichier trouvé",
            anchor="w",
            fg="#555555",
            wraplength=420,
        )
        label.pack(fill="x", pady=(5, 0))
        self.file_labels[kind] = label

        drop_zone = tk.Label(
            card,
            text="Déposer un CSV",
            relief="groove",
            padx=8,
            pady=6,
        )
        drop_zone.pack(fill="x", expand=True, pady=(8, 0))
        drop_zone.drop_target_register(DND_FILES)
        drop_zone.dnd_bind(
            "<<Drop>>",
            lambda event, selected=kind: self._handle_drop(event, selected),
        )
        actions = tk.Frame(card)
        actions.pack(fill="x", pady=(6, 0))
        tk.Button(
            actions,
            text="Parcourir…",
            command=lambda selected=kind: self._browse(selected),
        ).pack(side="right")

        if kind == "active_directory":
            tk.Button(
                actions,
                text="Copier le dernier export",
                command=self._copy_latest_active_directory,
            ).pack(side="right", padx=(0, 6))
        return card

    @staticmethod
    def _input_directory_for_kind(kind):
        """Retourne le dossier de destination associé au type de fichier."""
        if kind == "active_directory_previous":
            return ACTIVE_DIRECTORY_INPUT
        return INPUT_DIRECTORY

    def _current_file(self, kind):
        """Sélectionne le fichier valide le plus récent pour le type demandé."""
        input_directory = self._input_directory_for_kind(kind)
        return max(
            self._files_of_kind(input_directory, kind),
            key=lambda path: path.stat().st_mtime,
            default=None,
        )

    @staticmethod
    def _files_of_kind(directory, kind):
        """Liste les CSV lisibles qui contiennent les colonnes attendues."""
        required_columns = REQUIRED_COLUMNS[kind]
        candidates = []
        for path in directory.glob("*.csv"):
            try:
                columns, _ = read_csv(
                    path, DELIMITERS[kind], required_columns
                )
            except (OSError, UnicodeError, ValueError):
                continue

            if kind == "swile" and "Matricule" not in columns:
                continue
            candidates.append(path)
        if kind == "template":
            bundled_template = bundled_resource(
                "swile_active_directory", "in", DEFAULT_TEMPLATE_FILE
            )
            if not candidates and bundled_template.is_file():
                candidates.append(bundled_template)
        return candidates

    def _refresh_file_labels(self):
        """Actualise l’état des fichiers affichés et le statut général."""
        for kind, label in self.file_labels.items():
            path = self._current_file(kind)
            if path is None:
                input_directory = self._input_directory_for_kind(kind)
                label.configure(
                    text=f"Aucun fichier trouvé dans {input_directory.name}",
                    fg="#a33",
                )
            else:
                label.configure(text=f"Prêt : {path.name}", fg="#176b35")

        missing_main_inputs = [
            TITLES[kind]
            for kind in ("swile", "active_directory")
            if self._current_file(kind) is None
        ]
        if missing_main_inputs:
            self.status.set(
                f"Fichier(s) requis pour comparer : {', '.join(missing_main_inputs)}"
            )
        else:
            self.status.set("Tous les fichiers nécessaires sont prêts.")

    def _browse(self, kind):
        """Ouvre le sélecteur de fichiers pour choisir un CSV."""
        path = filedialog.askopenfilename(
            title=f"Choisir : {TITLES[kind]}",
            filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")],
        )
        if path:
            self._copy_input_file(Path(path), kind)

    def _handle_drop(self, event, kind):
        """Valide le dépôt d’un seul fichier puis le transmet à la copie."""
        paths = self.tk.splitlist(event.data)
        if len(paths) != 1:
            messagebox.showerror(
                "Un seul fichier requis",
                "Déposez un seul fichier CSV à la fois.",
                parent=self,
            )
            return
        self._copy_input_file(Path(paths[0]), kind)

    def _copy_input_file(self, source, kind):
        """Valide et copie un CSV vers le dossier d’entrée correspondant."""
        try:
            if not source.is_file() or source.suffix.casefold() != ".csv":
                raise ValueError("Sélectionnez un fichier CSV existant.")
            read_csv(source, DELIMITERS[kind], REQUIRED_COLUMNS[kind])
            input_directory = self._input_directory_for_kind(kind)
            destination = input_directory / source.name
            input_directory.mkdir(parents=True, exist_ok=True)

            if source.resolve() == destination.resolve():
                self._refresh_file_labels()
                return
            if destination.exists() and not messagebox.askyesno(
                "Remplacer le fichier ?",
                f"{destination.name} existe déjà. Voulez-vous le remplacer ?",
                parent=self,
            ):
                return

            shutil.copy2(source, destination)
            self.status.set(f"Fichier enregistré : {destination.name}")
            self._refresh_file_labels()
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror("Fichier invalide", str(error), parent=self)

    def _copy_latest_active_directory(self):
        """Copie le dernier export AD valide vers les fichiers Swile."""
        try:
            candidates = self._files_of_kind(
                ACTIVE_DIRECTORY_OUTPUT, "active_directory"
            )
            if not candidates:
                raise FileNotFoundError(
                    "Aucun export Active Directory valide trouvé dans "
                    f"{ACTIVE_DIRECTORY_OUTPUT}."
                )
            source = max(candidates, key=lambda path: path.stat().st_mtime)
            read_csv(
                source,
                DELIMITERS["active_directory"],
                REQUIRED_COLUMNS["active_directory"],
            )
            destination = INPUT_DIRECTORY / source.name
            INPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
            if destination.exists() and source.resolve() != destination.resolve():
                if not messagebox.askyesno(
                    "Remplacer le fichier ?",
                    f"{destination.name} existe déjà. Voulez-vous le remplacer "
                    f"par la dernière version ({source.name}) ?",
                    parent=self,
                ):
                    return
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            self.status.set(f"Dernier export copié : {source.name}")
            self._refresh_file_labels()
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror(
                "Copie impossible",
                f"Impossible de copier le dernier export Active Directory :\n{error}",
                parent=self,
            )

    def _run(self, action):
        """Vérifie les entrées et démarre le traitement dans un thread."""
        if self.is_running:
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
        try:
            with redirect_stdout(output_writer), redirect_stderr(output_writer):
                if action == "active_directory":
                    run_active_directory_export(
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
                lambda: self._finish_run(output_writer.getvalue(), "", 0),
            )
        except Exception:
            error = traceback.format_exc()
            output_writer.write(error)
            self.after(0, lambda message=error: self._finish_run("", message, 1))

    def _schedule_device_code_dialog(self, verification_uri, user_code):
        """Programme l’ouverture de la fenêtre de connexion sur le thread Tk."""
        self.after(
            0,
            self._show_device_code_dialog,
            verification_uri,
            user_code,
        )

    def _start_active_directory_progress(self):
        """Affiche une animation pendant l’authentification Microsoft."""
        self.progress_count = 0
        self.progress_frame.pack(fill="x", pady=(0, 10))
        self.progress_bar.configure(mode="indeterminate", value=0)
        self.progress_label.set("Connexion à Microsoft…")
        self.progress_bar.start(12)

    def _schedule_active_directory_progress(
        self,
        completed_count,
        estimated_total,
        phase,
    ):
        """Transmet une mise à jour de progression au thread graphique."""
        self.after(
            0,
            self._update_active_directory_progress,
            completed_count,
            estimated_total,
            phase,
        )

    def _update_active_directory_progress(
        self,
        completed_count,
        estimated_total,
        phase,
    ):
        """Actualise la barre et le pourcentage de collecte Active Directory."""
        self.progress_count = completed_count
        if self.progress_bar.cget("mode") == "indeterminate":
            self.progress_bar.stop()
        self.progress_bar.configure(
            mode="determinate",
            maximum=max(1, estimated_total),
        )
        if phase == "complete":
            self.progress_bar.configure(value=max(1, estimated_total))
            self.progress_label.set(
                f"Collecte terminée : {completed_count} personne(s) exportée(s)."
            )
            return

        percentage = min(
            99,
            int(completed_count * 100 / max(1, estimated_total)),
        )
        self.progress_bar.configure(
            value=min(completed_count, estimated_total)
        )
        if phase == "connecting":
            self.progress_bar.configure(mode="indeterminate", value=0)
            self.progress_bar.start(12)
            self.progress_label.set(
                f"Connexion Microsoft… estimation : environ "
                f"{estimated_total} personnes."
            )
        else:
            self.progress_label.set(
                f"{percentage} % — {completed_count} personne(s) "
                f"sur environ {estimated_total}."
            )

    def _show_device_code_dialog(self, verification_uri, user_code):
        """Affiche le code d’appareil et les actions pour se connecter."""
        dialog = tk.Toplevel(self)
        self.device_code_dialog = dialog
        dialog.title("Connexion Microsoft requise")
        dialog.transient(self)
        dialog.resizable(False, False)

        content = tk.Frame(dialog, padx=20, pady=16)
        content.pack(fill="both", expand=True)
        tk.Label(
            content,
            text="Copiez ce code, puis saisissez-le sur la page Microsoft :",
            wraplength=380,
            justify="left",
        ).pack(anchor="w")
        tk.Label(
            content,
            text=user_code,
            font=("Segoe UI", 20, "bold"),
            pady=10,
        ).pack()
        tk.Label(
            content,
            text=verification_uri,
            fg="#1769aa",
            wraplength=380,
        ).pack(anchor="w", pady=(0, 12))

        buttons = tk.Frame(content)
        buttons.pack(fill="x")
        copy_status = tk.StringVar(value="")

        def copy_code():
            """Copie le code de connexion dans le presse-papiers."""
            dialog.clipboard_clear()
            dialog.clipboard_append(user_code)
            dialog.update()
            copy_status.set("Code copié dans le presse-papiers.")

        tk.Button(
            buttons,
            text="Copier le code",
            command=copy_code,
        ).pack(side="left")
        tk.Button(
            buttons,
            text="Ouvrir la page de connexion",
            command=lambda: self._open_device_code_page(verification_uri),
        ).pack(side="right")
        tk.Label(content, textvariable=copy_status, fg="#176b35").pack(
            anchor="w", pady=(8, 0)
        )

    def _open_device_code_page(self, verification_uri):
        """Ouvre la page Microsoft de connexion avec le code d’appareil."""
        if not webbrowser.open(verification_uri):
            messagebox.showerror(
                "Ouverture impossible",
                "Impossible d’ouvrir la page de connexion Microsoft.",
                parent=self,
            )

    def _finish_run(self, stdout, stderr, returncode):
        """Rétablit l’interface et affiche le résultat ou l’erreur du traitement."""
        if self.device_code_dialog is not None:
            if self.device_code_dialog.winfo_exists():
                self.device_code_dialog.destroy()
            self.device_code_dialog = None
        self.is_running = False
        self._set_run_buttons_state("normal")
        self._set_config_controls_state("normal")
        if self.progress_bar.cget("mode") == "indeterminate":
            self.progress_bar.stop()
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
        """Active ou désactive les contrôles de configuration Active Directory."""
        for control in self.active_directory_config_controls:
            control.configure(state=state)

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
