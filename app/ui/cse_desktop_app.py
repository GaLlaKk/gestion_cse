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
from services.active_directory_export import run_active_directory_export

ROOT_DIRECTORY = project_root()
SWILE_DIRECTORY = ROOT_DIRECTORY / "swile_active_directory"
INPUT_DIRECTORY = SWILE_DIRECTORY / "in"
OUTPUT_DIRECTORY = SWILE_DIRECTORY / "out"
ACTIVE_DIRECTORY_OUTPUT = ROOT_DIRECTORY / "liste_salarie_active_directory" / "out"
REQUIRED_COLUMNS = {
    "swile": {"Prénom", "Nom", "Email", "Matricule"},
    "active_directory": {"Nom", "Email", "Identifiant", "Poste"},
    "template": {"Prénom", "Nom", "Email", "Matricule"},
}
TITLES = {
    "swile": "FICHIER SWILE - Liste actuelle des salariés",
    "active_directory": "FICHIER ACTIVE DIRECTORY - Export des salariés",
    "template": "MODELE SWILE - CSV d'import",
}
INSTRUCTIONS = {
    "swile": "CSV SWILE ATTENDU ici (séparateur « ; »).",
    "active_directory": "CSV ACTIVE DIRECTORY ATTENDU ici (séparateur « , »).",
    "template": "MODELE SWILE ATTENDU ici (séparateur « ; »).",
}
INPUT_HIGHLIGHTS = {
    "swile": ("SWILE", "#0a4f8a"),
    "active_directory": ("ACTIVE DIRECTORY", "#176b35"),
    "template": ("MODELE SWILE", "#71f19e"),
}
DELIMITERS = {
    "swile": ";",
    "active_directory": ",",
    "template": ";",
}
DEFAULT_TEMPLATE_FILE = (
    "collaborators_template_090d2568-c182-4cf4-8b3a-81fefee3a297.csv"
)


class _OutputWriter:
    def __init__(self, app):
        self.app = app
        self.parts = []

    def write(self, text):
        if text:
            self.parts.append(text)
            self.app.after(0, self.app._append_output, text)
        return len(text)

    def flush(self):
        pass

    def getvalue(self):
        return "".join(self.parts)


class CSEFileManager(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gestion des fichiers CSE")
        self.geometry("1050x860")
        self.minsize(820, 720)
        self.configure(padx=20, pady=16)
        self.file_labels = {}
        self.run_buttons = []
        self.is_running = False
        self.device_code_dialog = None
        self.download_photos = tk.BooleanVar(value=False)

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

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, pady=(4, 8))
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
            wraplength=700,
        ).pack(fill="x", pady=(0, 8))
        self._create_run_button(
            active_directory_tab,
            "Générer la liste Active Directory",
            "active_directory",
        )
        ttk.Checkbutton(
            active_directory_tab,
            text="Récupérer les photos (les photos déjà téléchargées seront conservées)",
            variable=self.download_photos,
        ).pack(anchor="w", pady=(0, 8))
        tk.Label(
            active_directory_tab,
            text=f"CSV créé dans : {ACTIVE_DIRECTORY_OUTPUT}",
            anchor="w",
            justify="left",
            wraplength=700,
        ).pack(fill="x", pady=(8, 0))
        tk.Label(
            active_directory_tab,
            text=f"Journaux : {ROOT_DIRECTORY / 'log'}",
            anchor="w",
            justify="left",
            wraplength=700,
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
        for kind in ("swile", "active_directory"):
            self._create_input_card(kind, compare_section)

        self._create_run_button(
            compare_section,
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

    def _create_run_button(self, parent, label, action):
        button = tk.Button(
            parent,
            text=label,
            command=lambda selected=action: self._run(selected),
            padx=8,
            pady=5,
        )
        button.pack(anchor="w", pady=(0, 4))
        self.run_buttons.append(button)

    def _create_input_card(self, kind, parent):
        card = tk.LabelFrame(parent, text=TITLES[kind], padx=10, pady=7)
        card.pack(fill="x", pady=4)

        description = tk.Frame(card)
        description.pack(side="left", fill="x", expand=True)
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
        ).pack(fill="x", pady=(0, 4))
        tk.Label(
            description,
            text=INSTRUCTIONS[kind],
            anchor="w",
            justify="left",
            wraplength=300,
        ).pack(fill="x")
        tk.Label(
            description,
            text=f"Destination : {INPUT_DIRECTORY} (nom d’origine conservé)",
            anchor="w",
            justify="left",
            fg="#555555",
            wraplength=300,
        ).pack(fill="x", pady=(3, 0))

        label = tk.Label(
            description,
            text="Aucun fichier trouvé",
            anchor="w",
            fg="#555555",
            wraplength=300,
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
        return max(
            self._files_of_kind(INPUT_DIRECTORY, kind),
            key=lambda path: path.stat().st_mtime,
            default=None,
        )

    @staticmethod
    def _files_of_kind(directory, kind):
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
        for kind, label in self.file_labels.items():
            path = self._current_file(kind)
            if path is None:
                label.configure(text="Aucun fichier trouvé dans in", fg="#a33")
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
            read_csv(source, DELIMITERS[kind], REQUIRED_COLUMNS[kind])
            destination = INPUT_DIRECTORY / source.name
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
        if self.is_running:
            return
        try:
            if action == "active_directory":
                self.is_running = True
                self.status.set("Collecte Active Directory en cours…")
                self._set_run_buttons_state("disabled")
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
                    ),
                    daemon=True,
                ).start()
                return

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
            self.status.set("Traitement en cours…")
            self._set_run_buttons_state("disabled")
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
    ):
        output_writer = _OutputWriter(self)
        try:
            with redirect_stdout(output_writer), redirect_stderr(output_writer):
                if action == "active_directory":
                    run_active_directory_export(
                        on_device_code=self._schedule_device_code_dialog,
                        download_photos=download_photos,
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
        self.after(
            0,
            self._show_device_code_dialog,
            verification_uri,
            user_code,
        )

    def _show_device_code_dialog(self, verification_uri, user_code):
        dialog = tk.Toplevel(self)
        self.device_code_dialog = dialog
        dialog.title("Connexion Microsoft requise")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.grab_set()

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
        if not webbrowser.open(verification_uri):
            messagebox.showerror(
                "Ouverture impossible",
                "Impossible d’ouvrir la page de connexion Microsoft.",
                parent=self,
            )

    def _finish_run(self, stdout, stderr, returncode):
        if self.device_code_dialog is not None:
            if self.device_code_dialog.winfo_exists():
                self.device_code_dialog.destroy()
            self.device_code_dialog = None
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

    def _append_output(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.configure(state="disabled")

    def _open_output_directory(self):
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
    app = CSEFileManager()
    app.mainloop()


if __name__ == "__main__":
    main()
