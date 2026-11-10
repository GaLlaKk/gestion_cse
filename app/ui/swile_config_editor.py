import tkinter as tk
from tkinter import messagebox
from tkinter import ttk


from services.swile_config import (
    SWILE_CONFIG_PATH,
    load_addition_filters,
    load_work_location_mapping,
    save_work_location_mapping,
)


class SwileConfigEditorMixin:
    """Éditeurs du mapping des lieux et des filtres d’ajouts Swile."""

    def _build_addition_filter_toggles(self, compare_section):
        """Construit les filtres d’ajouts repliables."""
        addition_filters_section = tk.Frame(compare_section)
        addition_filters_section.grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(10, 0)
        )
        for filter_name, filter_title in (
            (
                "email",
                "Filtrage des adresses e-mail "
                "(fichier de création des ajouts Swile)",
            ),
            (
                "poste",
                "Filtrage des postes "
                "(fichier de création des ajouts Swile)",
            ),
        ):
            filter_container = tk.Frame(addition_filters_section)
            filter_container.pack(fill="x")
            filter_toggle = ttk.Checkbutton(
                filter_container,
                text=(
                    "Afficher le filtrage des e-mails pour le fichier de "
                    "création des ajouts Swile"
                    if filter_name == "email"
                    else "Afficher le filtrage des postes pour le fichier "
                    "de création des ajouts Swile"
                ),
                variable=self.addition_filter_expanded[filter_name],
                command=lambda selected=filter_name: (
                    self._toggle_addition_filter_section(selected)
                ),
            )
            filter_toggle.pack(anchor="w", pady=(0, 4))
            self.addition_filter_toggle_controls[filter_name] = filter_toggle
            self.work_location_mapping_controls.append(filter_toggle)
            filter_section = self._create_addition_filter_editor(
                filter_container,
                filter_name,
                filter_title,
            )
            self.addition_filter_sections[filter_name] = filter_section

    def _build_location_values_section(self, location_values_content):
        """Construit la section de génération des valeurs de lieu."""
        location_values_section = tk.LabelFrame(
            location_values_content,
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
                "Cette étape génère un CSV à partir des salariés Swile trouvés "
                "dans Active Directory et des ajouts admissibles selon les "
                "filtres configurés dans « Comparer les listes »."
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

    def _create_work_location_mapping_editor(self, parent):
        """Construit l’éditeur graphique du mapping des lieux de travail."""
        section = tk.LabelFrame(
            parent,
            text="Configurer le mapping des lieux",
            padx=10,
            pady=8,
        )
        section.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(
            section,
            text=(
                f"Fichier : {SWILE_CONFIG_PATH}\n"
                "Pour les lieux, les règles sont évaluées de haut en bas et "
                "tous les mots-clés d’un motif doivent apparaître. Pour les "
                "filtres, la première règle correspondante décide d’inclure "
                "ou d’exclure; tous les termes d’un motif sont requis."
            ),
            anchor="w",
            justify="left",
            wraplength=760,
        ).pack(fill="x", pady=(0, 6))

        default_row = tk.Frame(section)
        default_row.pack(fill="x", pady=(0, 6))
        tk.Label(default_row, text="Valeur par défaut :", anchor="w").pack(
            side="left"
        )
        self.work_location_default_value = tk.StringVar(value="Autre")
        self.work_location_default_entry = tk.Entry(
            default_row,
            textvariable=self.work_location_default_value,
            width=28,
        )
        self.work_location_default_entry.pack(side="left", padx=(6, 0))
        self.work_location_default_entry.bind(
            "<KeyRelease>", self._mark_work_location_mapping_dirty
        )
        self.work_location_default_entry.bind(
            "<<Paste>>", self._mark_work_location_mapping_dirty
        )

        header = tk.Frame(section)
        header.pack(fill="x")
        header.columnconfigure(0, weight=3)
        header.columnconfigure(1, weight=2)
        tk.Label(header, text="Mots-clés (séparés par ;)").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        tk.Label(header, text="Valeur Swile").grid(
            row=0, column=1, sticky="w"
        )
        self.work_location_rules_frame = tk.Frame(section)
        self.work_location_rules_frame.columnconfigure(0, weight=1)
        self.work_location_rules_frame.pack(fill="x")
        self.work_location_mapping_rows = []
        self.work_location_mapping_dirty = False

        actions = tk.Frame(section)
        actions.pack(fill="x", pady=(6, 0))
        self.work_location_add_button = tk.Button(
            actions,
            text="＋ Ajouter une règle",
            command=lambda: self._add_work_location_rule(mark_dirty=True),
        )
        self.work_location_add_button.pack(side="left")
        self.work_location_save_button = tk.Button(
            actions,
            text="Enregistrer la configuration",
            command=self._save_work_location_mapping,
        )
        self.work_location_save_button.pack(side="left", padx=(6, 0))
        self.work_location_reload_button = tk.Button(
            actions,
            text="Recharger",
            command=self._load_work_location_mapping,
        )
        self.work_location_reload_button.pack(side="left", padx=(6, 0))
        self.work_location_mapping_status = tk.StringVar(value="")
        tk.Label(
            actions,
            textvariable=self.work_location_mapping_status,
            anchor="e",
            fg="#555555",
        ).pack(side="right", fill="x", expand=True, padx=(8, 0))
        self.work_location_mapping_controls.extend(
            (
                self.work_location_add_button,
                self.work_location_save_button,
                self.work_location_reload_button,
            )
        )

    def _create_addition_filter_editor(
        self, parent, filter_name, filter_title
    ):
        """Construit l’éditeur de règles pour un filtre des ajouts."""
        filter_section = tk.LabelFrame(
            parent,
            text=filter_title,
            padx=8,
            pady=5,
        )
        default_frame = tk.Frame(filter_section)
        default_frame.pack(fill="x", pady=(0, 4))
        tk.Label(
            default_frame,
            text="Valeur par défaut :",
            anchor="w",
        ).pack(side="left")
        default_value = tk.StringVar(value="inclure")
        default_entry = ttk.Combobox(
            default_frame,
            textvariable=default_value,
            values=("inclure", "exclure"),
            state="readonly",
            width=12,
        )
        default_entry.pack(side="left", padx=(6, 0))
        default_entry.bind(
            "<<ComboboxSelected>>", self._mark_work_location_mapping_dirty
        )
        self.addition_filter_default_values[filter_name] = default_value
        self.addition_filter_default_entries[filter_name] = default_entry
        self.work_location_mapping_controls.append(default_entry)
        header = tk.Frame(filter_section)
        header.pack(fill="x")
        header.columnconfigure(0, weight=3)
        header.columnconfigure(1, weight=1)
        tk.Label(header, text="Motifs (termes séparés par ;)").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        tk.Label(header, text="Valeur").grid(row=0, column=1, sticky="w")
        rules_frame = tk.Frame(filter_section)
        rules_frame.columnconfigure(0, weight=1)
        rules_frame.pack(fill="x")
        self.addition_filter_rows[filter_name] = []
        self.addition_filter_rules_frames[filter_name] = rules_frame
        add_button = tk.Button(
            filter_section,
            text="＋ Ajouter une règle",
            command=lambda selected=filter_name: (
                self._add_addition_filter_rule(selected, mark_dirty=True)
            ),
        )
        add_button.pack(anchor="w", pady=(4, 0))
        self.addition_filter_add_buttons[filter_name] = add_button
        self.work_location_mapping_controls.append(add_button)
        return filter_section

    def _toggle_addition_filter_section(self, filter_name):
        """Affiche ou masque un panneau de règles de filtrage des ajouts."""
        section = self.addition_filter_sections[filter_name]
        if self.addition_filter_expanded[filter_name].get():
            if not section.winfo_manager():
                section.pack(fill="x", pady=(0, 8))
        else:
            section.pack_forget()

    def _add_work_location_rule(self, pattern="", value="", mark_dirty=False):
        """Ajoute une ligne de mots-clés et sa valeur Swile associée."""
        row_frame = tk.Frame(self.work_location_rules_frame)
        row_frame.columnconfigure(0, weight=3)
        row_frame.columnconfigure(1, weight=2)
        pattern_var = tk.StringVar(value=pattern)
        value_var = tk.StringVar(value=value)
        pattern_entry = tk.Entry(row_frame, textvariable=pattern_var)
        pattern_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        value_entry = tk.Entry(row_frame, textvariable=value_var)
        value_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6))
        pattern_entry.bind("<KeyRelease>", self._mark_work_location_mapping_dirty)
        pattern_entry.bind("<<Paste>>", self._mark_work_location_mapping_dirty)
        value_entry.bind("<KeyRelease>", self._mark_work_location_mapping_dirty)
        value_entry.bind("<<Paste>>", self._mark_work_location_mapping_dirty)
        move_up_button = tk.Button(
            row_frame,
            text="↑",
            width=2,
            command=lambda selected=row_frame: self._move_work_location_rule(
                selected, -1
            ),
        )
        move_up_button.grid(row=0, column=2, padx=(0, 2))
        move_down_button = tk.Button(
            row_frame,
            text="↓",
            width=2,
            command=lambda selected=row_frame: self._move_work_location_rule(
                selected, 1
            ),
        )
        move_down_button.grid(row=0, column=3, padx=(0, 2))
        remove_button = tk.Button(
            row_frame,
            text="×",
            width=2,
            command=lambda selected=row_frame: self._remove_work_location_rule(
                selected
            ),
        )
        remove_button.grid(row=0, column=4)
        row = {
            "frame": row_frame,
            "pattern": pattern_var,
            "value": value_var,
            "controls": (
                pattern_entry,
                value_entry,
                move_up_button,
                move_down_button,
                remove_button,
            ),
            "move_up": move_up_button,
            "move_down": move_down_button,
        }
        self.work_location_mapping_rows.append(row)
        self.work_location_mapping_controls.extend(row["controls"])
        self._refresh_work_location_rule_rows()
        if mark_dirty:
            self.work_location_mapping_dirty = True

    def _refresh_work_location_rule_rows(self):
        """Actualise l’ordre et l’état des commandes de déplacement."""
        last_index = len(self.work_location_mapping_rows) - 1
        for index, row in enumerate(self.work_location_mapping_rows):
            row["frame"].grid(
                row=index,
                column=0,
                sticky="ew",
                pady=2,
            )
            row["move_up"].configure(state="disabled" if index == 0 else "normal")
            row["move_down"].configure(
                state="disabled" if index == last_index else "normal"
            )

    def _add_addition_filter_rule(
        self, filter_name, pattern="", value="exclure", mark_dirty=False
    ):
        """Ajoute un motif et son action à l’un des filtres d’ajouts."""
        row_frame = tk.Frame(self.addition_filter_rules_frames[filter_name])
        row_frame.columnconfigure(0, weight=3)
        row_frame.columnconfigure(1, weight=1)
        pattern_var = tk.StringVar(value=pattern)
        value_var = tk.StringVar(value=value)
        pattern_entry = tk.Entry(row_frame, textvariable=pattern_var)
        pattern_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        pattern_entry.bind(
            "<KeyRelease>", self._mark_work_location_mapping_dirty
        )
        pattern_entry.bind(
            "<<Paste>>", self._mark_work_location_mapping_dirty
        )
        value_entry = ttk.Combobox(
            row_frame,
            textvariable=value_var,
            values=("inclure", "exclure"),
            state="readonly",
            width=12,
        )
        value_entry.grid(row=0, column=1, sticky="w", padx=(0, 6))
        value_entry.bind(
            "<<ComboboxSelected>>", self._mark_work_location_mapping_dirty
        )
        move_up_button = tk.Button(
            row_frame,
            text="↑",
            width=2,
            command=lambda selected=row_frame: self._move_addition_filter_rule(
                filter_name, selected, -1
            ),
        )
        move_up_button.grid(row=0, column=2, padx=(0, 2))
        move_down_button = tk.Button(
            row_frame,
            text="↓",
            width=2,
            command=lambda selected=row_frame: self._move_addition_filter_rule(
                filter_name, selected, 1
            ),
        )
        move_down_button.grid(row=0, column=3, padx=(0, 2))
        remove_button = tk.Button(
            row_frame,
            text="×",
            width=2,
            command=lambda selected=row_frame: self._remove_addition_filter_rule(
                filter_name, selected
            ),
        )
        remove_button.grid(row=0, column=4)
        row = {
            "frame": row_frame,
            "pattern": pattern_var,
            "value": value_var,
            "controls": (
                pattern_entry,
                value_entry,
                move_up_button,
                move_down_button,
                remove_button,
            ),
            "move_up": move_up_button,
            "move_down": move_down_button,
        }
        self.addition_filter_rows[filter_name].append(row)
        self.work_location_mapping_controls.extend(row["controls"])
        self._refresh_addition_filter_rule_rows(filter_name)
        if mark_dirty:
            self.work_location_mapping_dirty = True

    def _refresh_addition_filter_rule_rows(self, filter_name):
        rows = self.addition_filter_rows[filter_name]
        last_index = len(rows) - 1
        for index, row in enumerate(rows):
            row["frame"].grid(row=index, column=0, sticky="ew", pady=2)
            row["move_up"].configure(state="disabled" if index == 0 else "normal")
            row["move_down"].configure(
                state="disabled" if index == last_index else "normal"
            )

    def _move_addition_filter_rule(self, filter_name, row_frame, offset):
        rows = self.addition_filter_rows[filter_name]
        current_index = next(
            index
            for index, row in enumerate(rows)
            if row["frame"] is row_frame
        )
        target_index = current_index + offset
        if not 0 <= target_index < len(rows):
            return
        row = rows.pop(current_index)
        rows.insert(target_index, row)
        self._refresh_addition_filter_rule_rows(filter_name)
        self.work_location_mapping_dirty = True

    def _remove_addition_filter_rule(self, filter_name, row_frame):
        rows = self.addition_filter_rows[filter_name]
        row_index = next(
            index
            for index, row in enumerate(rows)
            if row["frame"] is row_frame
        )
        row = rows.pop(row_index)
        for control in row["controls"]:
            self.work_location_mapping_controls.remove(control)
        row_frame.destroy()
        self._refresh_addition_filter_rule_rows(filter_name)
        self.work_location_mapping_dirty = True

    def _move_work_location_rule(self, row_frame, offset):
        """Déplace une règle d’un rang et met à jour son ordre de priorité."""
        current_index = next(
            index
            for index, row in enumerate(self.work_location_mapping_rows)
            if row["frame"] is row_frame
        )
        target_index = current_index + offset
        if not 0 <= target_index < len(self.work_location_mapping_rows):
            return
        row = self.work_location_mapping_rows.pop(current_index)
        self.work_location_mapping_rows.insert(target_index, row)
        self._refresh_work_location_rule_rows()
        self.work_location_mapping_dirty = True

    def _remove_work_location_rule(self, row_frame):
        """Supprime une règle du formulaire."""
        row_index = next(
            index
            for index, row in enumerate(self.work_location_mapping_rows)
            if row["frame"] is row_frame
        )
        row = self.work_location_mapping_rows.pop(row_index)
        for control in row["controls"]:
            self.work_location_mapping_controls.remove(control)
        row_frame.destroy()
        self._refresh_work_location_rule_rows()
        self.work_location_mapping_dirty = True

    def _mark_work_location_mapping_dirty(self, event):
        """Signale une modification non enregistrée du mapping."""
        if event.widget is not None:
            self.work_location_mapping_dirty = True

    def _load_work_location_mapping(self):
        """Charge les règles du fichier ou les règles par défaut."""
        if self.work_location_mapping_dirty and not messagebox.askyesno(
            "Recharger le mapping ?",
            "Les modifications non enregistrées seront perdues. Continuer ?",
            parent=self,
        ):
            return
        try:
            mapping = load_work_location_mapping()
            filters = load_addition_filters()
        except (OSError, UnicodeError, ValueError) as error:
            self.work_location_mapping_status.set("Chargement impossible.")
            messagebox.showerror(
                "Configuration du mapping invalide",
                str(error),
                parent=self,
            )
            return

        for row in self.work_location_mapping_rows:
            row["frame"].destroy()
        self.work_location_mapping_rows.clear()
        for filter_name, rows in self.addition_filter_rows.items():
            for row in rows:
                row["frame"].destroy()
            rows.clear()
        self.work_location_mapping_controls = [
            self.work_location_default_entry,
            *self.addition_filter_default_entries.values(),
            *self.addition_filter_add_buttons.values(),
            *self.addition_filter_toggle_controls.values(),
            self.work_location_add_button,
            self.work_location_save_button,
            self.work_location_reload_button,
        ]
        self.work_location_default_value.set(mapping["default_value"])
        for filter_name, filter_config in filters.items():
            self.addition_filter_default_values[filter_name].set(
                filter_config["default_value"]
            )
            for rule in filter_config["rules"]:
                for pattern in rule["patterns"]:
                    self._add_addition_filter_rule(
                        filter_name,
                        ";".join(pattern),
                        rule["value"],
                    )
        for rule in mapping["rules"]:
            for pattern in rule["patterns"]:
                self._add_work_location_rule(
                    "; ".join(pattern),
                    rule["value"],
                )
        for filter_name, rows in self.addition_filter_rows.items():
            self.addition_filter_expanded[filter_name].set(
                filter_name == "poste" and not rows
            )
            self._toggle_addition_filter_section(filter_name)
        self.work_location_mapping_dirty = False
        self.work_location_mapping_status.set("Configuration chargée.")

    def _save_work_location_mapping(self):
        """Valide et enregistre le mapping modifié depuis l’interface."""
        rules = []
        for index, row in enumerate(self.work_location_mapping_rows, start=1):
            terms = [
                term.strip()
                for term in row["pattern"].get().split(";")
            ]
            value = row["value"].get().strip()
            if not all(terms) or not value:
                messagebox.showerror(
                    "Règle incomplète",
                    f"La règle {index} doit contenir des mots-clés et une valeur.",
                    parent=self,
                )
                return
            rules.append(
                {
                    "patterns": [terms],
                    "value": value,
                }
            )
        mapping = {
            "description": (
                "Les mots-clés d'une règle sont tous requis. "
                "Les règles sont évaluées dans l'ordre."
            ),
            "default_value": self.work_location_default_value.get().strip(),
            "rules": rules,
        }
        filters = {}
        for filter_name, rows in self.addition_filter_rows.items():
            default_value = self.addition_filter_default_values[
                filter_name
            ].get()
            if default_value not in ("inclure", "exclure"):
                messagebox.showerror(
                    "Valeur de filtre invalide",
                    f"Le filtre « {filter_name} » doit avoir une valeur par "
                    "défaut inclure ou exclure.",
                    parent=self,
                )
                return
            filter_rules = []
            for index, row in enumerate(rows, start=1):
                terms = [
                    term.strip()
                    for term in row["pattern"].get().split(";")
                ]
                value = row["value"].get()
                if not all(terms) or value not in ("inclure", "exclure"):
                    messagebox.showerror(
                        "Règle de filtre incomplète",
                        f"La règle {index} du filtre « {filter_name} » doit "
                        "contenir des termes et une valeur valide.",
                        parent=self,
                    )
                    return
                filter_rules.append(
                    {
                        "patterns": [terms],
                        "value": value,
                    }
                )
            filters[filter_name] = {
                "default_value": default_value,
                "rules": filter_rules,
            }
        try:
            save_work_location_mapping(mapping, filters=filters)
        except (OSError, UnicodeError, ValueError) as error:
            self.work_location_mapping_status.set("Enregistrement impossible.")
            messagebox.showerror(
                "Configuration invalide",
                str(error),
                parent=self,
            )
            return
        self.work_location_mapping_dirty = False
        self.work_location_mapping_status.set("Configuration enregistrée.")
