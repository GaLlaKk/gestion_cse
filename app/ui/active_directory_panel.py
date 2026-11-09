import json
import tkinter as tk
import webbrowser
from tkinter import messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk


from services.active_directory_config import (
    apply_config_defaults,
    get_config_path,
    save_active_directory_config,
    validate_config,
)
from app.ui.constants import (
    ROOT_DIRECTORY,
    ACTIVE_DIRECTORY_OUTPUT,
    ACTIVE_DIRECTORY_CONFIG_FIELDS,
)


class ActiveDirectoryPanelMixin:
    """Configuration, progression et connexion de l’export Active Directory."""

    def _build_active_directory_config_section(self, active_directory_primary):
        """Construit la génération, les photos et la configuration repliable."""
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

    def _build_previous_export_section(self, active_directory_optional):
        """Construit le complément facultatif d’export précédent."""
        self.previous_export_expanded = tk.BooleanVar(value=False)
        self.previous_export_toggle = ttk.Checkbutton(
            active_directory_optional,
            text="Afficher le complément de configuration facultatif",
            variable=self.previous_export_expanded,
            command=self._toggle_previous_export_section,
        )
        self.previous_export_toggle.pack(anchor="w", pady=(0, 4))
        previous_export_container = tk.Frame(active_directory_optional)
        previous_export_container.pack(fill="x")
        previous_export_section = tk.LabelFrame(
            previous_export_container,
            text="Complément de configuration facultatif",
            padx=10,
            pady=8,
        )
        self.previous_export_section = previous_export_section
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
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                config = {}
            if not isinstance(config, dict):
                raise ValueError(
                    "La configuration doit contenir un objet JSON."
                )
            config = apply_config_defaults(config)
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

    def _toggle_previous_export_section(self):
        """Affiche ou masque le complément d’export précédent."""
        if self.previous_export_expanded.get():
            if not self.previous_export_section.winfo_manager():
                self.previous_export_section.pack(
                    fill="x", pady=(0, 8)
                )
            self.previous_export_toggle.configure(
                text="Masquer le complément de configuration facultatif"
            )
        else:
            self.previous_export_section.pack_forget()
            self.previous_export_toggle.configure(
                text="Afficher le complément de configuration facultatif"
            )

    def _set_previous_export_section_default_visibility(self):
        """Ouvre le complément uniquement si aucun export précédent n’existe."""
        self.previous_export_expanded.set(
            self._current_file("active_directory_previous") is None
        )
        self._toggle_previous_export_section()

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
