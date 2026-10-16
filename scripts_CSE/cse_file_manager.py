import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from tkinterdnd2 import DND_FILES, TkinterDnD

from swile_active_directory import (
    DEFAULT_TEMPLATE_FILE,
    latest_input_file,
    read_csv,
)


ROOT_DIRECTORY = Path(__file__).resolve().parent
SWILE_DIRECTORY = ROOT_DIRECTORY / "swile_active_directory"
INPUT_DIRECTORY = SWILE_DIRECTORY / "in"
OUTPUT_DIRECTORY = SWILE_DIRECTORY / "out"
ACTIVE_DIRECTORY_OUTPUT = (
    ROOT_DIRECTORY / "liste_salarie_active_directory" / "out"
)
SWILE_SCRIPT = ROOT_DIRECTORY / "swile_active_directory.py"
REQUIRED_COLUMNS = {
    "swile": {"Prénom", "Nom", "Email", "Matricule"},
    "active_directory": {"Nom", "Email", "Poste"},
    "template": {"Prénom", "Nom", "Email"},
}
DESTINATIONS = {
    "swile": "collaborators_swile.csv",
    "active_directory": "liste_salarie_active_directory.csv",
    "template": DEFAULT_TEMPLATE_FILE,
}
TITLES = {
    "swile": "Liste actuelle des salariés Swile",
    "active_directory": "Export des salariés Active Directory",
    "template": "Modèle CSV Swile",
}
INSTRUCTIONS = {
    "swile": "Déposez ici le CSV Swile actuel (séparateur « ; »).",
    "active_directory": "Déposez ici un export Active Directory (séparateur « , »).",
    "template": "Déposez ici le modèle d’import Swile (séparateur « ; »).",
}


class CSEFileManager(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gestion des fichiers CSE")
        self.geometry("760x760")
        self.minsize(650, 650)
        self.configure(padx=20, pady=16)
        self.file_labels = {}
        self.run_buttons = []
        self.is_running = False

        tk.Label(
            self,
            text="Préparer les fichiers CSE",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        tk.Label(
            self,
            text=(
                "Déposez chaque CSV dans la zone correspondante ou utilisez "
                "« Parcourir ». Les fichiers seront rangés dans le dossier in."
            ),
            justify="left",
            wraplength=700,
        ).pack(anchor="w", pady=(4, 12))

        for kind in ("swile", "active_directory", "template"):
            self._create_input_card(kind)

        actions = tk.LabelFrame(self, text="Traitements", padx=10, pady=8)
        actions.pack(fill="x", pady=(10, 8))
        for label, action in (
            ("Comparer les listes", "compare"),
            ("Préparer les ajouts Swile", "additions"),
            ("Tout faire", "all"),
        ):
            button = tk.Button(
                actions,
                text=label,
                command=lambda selected=action: self._run(selected),
                padx=8,
                pady=5,
            )
            button.pack(side="left", padx=(0, 8))
            self.run_buttons.append(button)

        footer = tk.Frame(self)
        footer.pack(fill="x", pady=(0, 8))
        tk.Button(
            footer,
            text="Ouvrir les résultats",
            command=self._open_output_directory,
        ).pack(side="left")
        self.status = tk.StringVar(value="Vérification des fichiers d’entrée…")
        tk.Label(footer, textvariable=self.status, anchor="e").pack(
            side="right", fill="x", expand=True, padx=(12, 0)
        )

        tk.Label(self, text="Résultat du dernier traitement", anchor="w").pack(
            fill="x"
        )
        self.output = ScrolledText(self, height=8, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True, pady=(3, 0))
        self._refresh_file_labels()

    def _create_input_card(self, kind):
        card = tk.LabelFrame(self, text=TITLES[kind], padx=10, pady=7)
        card.pack(fill="x", pady=4)

        description = tk.Frame(card)
        description.pack(side="left", fill="x", expand=True)
        tk.Label(
            description,
            text=INSTRUCTIONS[kind],
            anchor="w",
            justify="left",
        ).pack(fill="x")
        tk.Label(
            description,
            text=f"Destination : {INPUT_DIRECTORY / DESTINATIONS[kind]}",
            anchor="w",
            fg="#555555",
        ).pack(fill="x", pady=(3, 0))

        label = tk.Label(
            description,
            text="Aucun fichier trouvé",
            anchor="w",
            fg="#555555",
        )
        label.pack(fill="x", pady=(3, 0))
        self.file_labels[kind] = label

        drop_zone = tk.Label(
            card,
            text="Glisser-déposer",
            relief="groove",
            padx=10,
            pady=8,
            width=17,
        )
        drop_zone.pack(side="right", padx=(10, 0))
        drop_zone.drop_target_register(DND_FILES)
        drop_zone.dnd_bind(
            "<<Drop>>",
            lambda event, selected=kind: self._handle_drop(event, selected),
        )
        tk.Button(
            card,
            text="Parcourir…",
            command=lambda selected=kind: self._browse(selected),
        ).pack(side="right")

        if kind == "active_directory":
            tk.Button(
                card,
                text="Copier la dernière version",
                command=self._copy_latest_active_directory,
            ).pack(side="right", padx=(0, 8))

    def _current_file(self, kind):
        try:
            if kind == "swile":
                return latest_input_file(
                    INPUT_DIRECTORY, "collaborators*.csv", "Swile"
                )
            if kind == "active_directory":
                return latest_input_file(
                    INPUT_DIRECTORY,
                    "*liste_salarie_active_directory.csv",
                    "Active Directory",
                )
            template_path = INPUT_DIRECTORY / DEFAULT_TEMPLATE_FILE
            if template_path.is_file():
                return template_path
        except FileNotFoundError:
            return None
        return None

    def _refresh_file_labels(self):
        missing = []
        for kind, label in self.file_labels.items():
            path = self._current_file(kind)
            if path is None:
                label.configure(text="Aucun fichier trouvé dans in", fg="#a33")
                missing.append(TITLES[kind])
            else:
                label.configure(text=f"Prêt : {path.name}", fg="#176b35")

        if missing:
            self.status.set(f"Fichier(s) à fournir : {', '.join(missing)}")
        else:
            self.status.set("Tous les fichiers nécessaires sont prêts.")

    def _browse(self, kind):
        path = filedialog.askopenfilename(
            title=f"Choisir : {TITLES[kind]}",
            filetypes=[("Fichiers CSV", "*.csv"), ("Tous les fichiers", "*.*")],
        )
        if path:
            self._copy_input_file(Path(path), kind)

    def _handle_drop(self, event, kind):
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
        try:
            if not source.is_file() or source.suffix.casefold() != ".csv":
                raise ValueError("Sélectionnez un fichier CSV existant.")
            delimiter = "," if kind == "active_directory" else ";"
            read_csv(source, delimiter, REQUIRED_COLUMNS[kind])
            destination = INPUT_DIRECTORY / DESTINATIONS[kind]
            INPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

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
        try:
            source = latest_input_file(
                ACTIVE_DIRECTORY_OUTPUT,
                "*_liste_salarie_active_directory.csv",
                "export Active Directory",
            )
            delimiter = ","
            read_csv(source, delimiter, REQUIRED_COLUMNS["active_directory"])
            destination = INPUT_DIRECTORY / DESTINATIONS["active_directory"]
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
        if self.is_running:
            return
        try:
            swile_path = self._current_file("swile")
            active_directory_path = self._current_file("active_directory")
            template_path = (
                self._current_file("template")
                if action in ("additions", "all")
                else None
            )
            missing = [
                label
                for path, label in (
                    (swile_path, TITLES["swile"]),
                    (active_directory_path, TITLES["active_directory"]),
                )
                if path is None
            ]
            if action in ("additions", "all") and template_path is None:
                missing.append(TITLES["template"])
            if missing:
                messagebox.showerror(
                    "Fichiers manquants",
                    "Ajoutez les fichiers suivants dans les zones prévues :\n"
                    + "\n".join(f"• {name}" for name in missing),
                    parent=self,
                )
                return

            command = [
                sys.executable,
                str(SWILE_SCRIPT),
                action,
                "--swile-file",
                str(swile_path),
                "--active-directory-file",
                str(active_directory_path),
            ]
            if template_path is not None:
                command.extend(("--template-file", str(template_path)))
            self.is_running = True
            self.status.set("Traitement en cours…")
            self._set_run_buttons_state("disabled")
            self._set_output("Traitement en cours…\n")
            threading.Thread(
                target=self._run_worker,
                args=(command,),
                daemon=True,
            ).start()
        except OSError as error:
            self._finish_run("", str(error), 1)

    def _run_worker(self, command):
        try:
            result = subprocess.run(
                command,
                cwd=ROOT_DIRECTORY,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.after(
                0,
                lambda: self._finish_run(
                    result.stdout, result.stderr, result.returncode
                ),
            )
        except OSError as error:
            self.after(0, lambda: self._finish_run("", str(error), 1))

    def _finish_run(self, stdout, stderr, returncode):
        self.is_running = False
        self._set_run_buttons_state("normal")
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
        for button in self.run_buttons:
            button.configure(state=state)

    def _set_output(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def _open_output_directory(self):
        OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
        if hasattr(os, "startfile"):
            os.startfile(OUTPUT_DIRECTORY)
        else:
            messagebox.showinfo(
                "Dossier des résultats",
                str(OUTPUT_DIRECTORY),
                parent=self,
            )


if __name__ == "__main__":
    CSEFileManager().mainloop()
