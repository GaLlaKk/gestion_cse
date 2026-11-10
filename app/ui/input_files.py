import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from tkinterdnd2 import DND_FILES

from app.ui.constants import (
    ACTIVE_DIRECTORY_INPUT,
    ACTIVE_DIRECTORY_OUTPUT,
    DEFAULT_TEMPLATE_FILE,
    DELIMITERS,
    INPUT_DIRECTORY,
    INPUT_HIGHLIGHTS,
    INSTRUCTIONS,
    REQUIRED_COLUMNS,
    TITLES,
)
from services.csv_files import latest_valid_csv_in_directories, read_csv
from services.paths import bundled_resource


class InputFilesMixin:
    """Cartes de sélection, dépôt et copie des CSV d’entrée."""

    def _create_input_card(self, kind, parent):
        """Construit une carte de sélection ou de dépôt pour un fichier CSV."""
        card = tk.LabelFrame(parent, text=TITLES[kind], padx=10, pady=9)

        description = tk.Frame(card)
        description.pack(fill="x", expand=True)
        highlight_text, highlight_color = INPUT_HIGHLIGHTS[kind]
        expected_file = tk.Frame(description)
        expected_file.pack(anchor="w", pady=(0, 5))
        tk.Label(
            expected_file,
            text="📄  FICHIER ATTENDU :",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", padx=(0, 4))
        tk.Label(
            expected_file,
            text=highlight_text,
            bg="#e8edf2",
            fg=highlight_color,
            font=("Segoe UI", 9, "bold"),
            padx=6,
            pady=2,
        ).pack(side="left")
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
        if kind == "active_directory_previous":
            return latest_valid_csv_in_directories(
                (input_directory, ACTIVE_DIRECTORY_OUTPUT),
                DELIMITERS[kind],
                REQUIRED_COLUMNS[kind],
            )
        candidates = self._files_of_kind(input_directory, kind)
        return max(
            candidates,
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
            if kind in ("active_directory", "active_directory_previous"):
                os.utime(destination, None)
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
                os.utime(destination, None)
            self.status.set(f"Dernier export copié : {source.name}")
            self._refresh_file_labels()
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror(
                "Copie impossible",
                f"Impossible de copier le dernier export Active Directory :\n{error}",
                parent=self,
            )
