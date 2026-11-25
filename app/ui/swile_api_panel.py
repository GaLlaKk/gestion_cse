import threading
import tkinter as tk
import traceback
from contextlib import redirect_stderr, redirect_stdout
from tkinter import messagebox
from tkinter import ttk

from services.swile_api_config import (
    SWILE_API_CONFIG_PATH,
    load_swile_api_credentials,
    save_swile_api_credentials,
)
from services.swile_api_service import SwileApiClient


class SwileApiPanelMixin:
    """Onglet d’intégration Swile API (authentification et POC salariés)."""

    def _build_swile_api_tab(self, swile_api_tab):
        """Construit l’onglet Swile API et ses sous-onglets."""
        swile_api_subtabs = ttk.Notebook(swile_api_tab)
        swile_api_subtabs.pack(fill="both", expand=True)
        self.swile_api_subtabs = swile_api_subtabs
        auth_tab = tk.Frame(swile_api_subtabs)
        list_tab = tk.Frame(swile_api_subtabs)
        create_tab = tk.Frame(swile_api_subtabs)
        deactivate_tab = tk.Frame(swile_api_subtabs)
        swile_api_subtabs.add(auth_tab, text="Authentification")
        swile_api_subtabs.add(list_tab, text="Liste des salariés")
        swile_api_subtabs.add(create_tab, text="Création des salariés")
        swile_api_subtabs.add(deactivate_tab, text="Désactivation des salariés")

        self._build_swile_api_auth_tab(auth_tab)
        self._build_swile_api_list_tab(list_tab)
        self._build_swile_api_create_tab(create_tab)
        self._build_swile_api_deactivate_tab(deactivate_tab)
        self._set_swile_api_connected(False)
        self._load_swile_api_credentials()

    def _build_swile_api_auth_tab(self, parent):
        """Construit le sous-onglet d’authentification Swile."""
        section = tk.LabelFrame(parent, text="Connexion à l’API Swile", padx=10, pady=8)
        section.pack(fill="x", padx=10, pady=10)
        tk.Label(
            section,
            text=(
                f"Configuration locale : {SWILE_API_CONFIG_PATH}\n"
                "Le client_secret est chiffré localement avant sauvegarde."
            ),
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", pady=(0, 8))

        client_id_row = tk.Frame(section)
        client_id_row.pack(fill="x", pady=(0, 6))
        tk.Label(client_id_row, text="SWILE_CLIENT_ID", width=18, anchor="w").pack(
            side="left"
        )
        self.swile_api_client_id_var = tk.StringVar(value="")
        self.swile_api_client_id_entry = tk.Entry(
            client_id_row, textvariable=self.swile_api_client_id_var
        )
        self.swile_api_client_id_entry.pack(side="left", fill="x", expand=True)

        secret_row = tk.Frame(section)
        secret_row.pack(fill="x")
        tk.Label(secret_row, text="SWILE_CLIENT_SECRET", width=18, anchor="w").pack(
            side="left"
        )
        self.swile_api_client_secret_var = tk.StringVar(value="")
        self.swile_api_client_secret_entry = tk.Entry(
            secret_row, textvariable=self.swile_api_client_secret_var, show="•"
        )
        self.swile_api_client_secret_entry.pack(side="left", fill="x", expand=True)

        actions = tk.Frame(section)
        actions.pack(fill="x", pady=(8, 0))
        self.swile_api_save_button = tk.Button(
            actions,
            text="Enregistrer",
            command=self._save_swile_api_credentials,
        )
        self.swile_api_save_button.pack(side="left")
        self.swile_api_reload_button = tk.Button(
            actions, text="Recharger", command=self._load_swile_api_credentials
        )
        self.swile_api_reload_button.pack(side="left", padx=(6, 0))
        self.swile_api_connect_button = tk.Button(
            actions, text="Connexion", command=self._connect_swile_api
        )
        self.swile_api_connect_button.pack(side="left", padx=(6, 0))
        self.swile_api_auth_status = tk.StringVar(value="Configuration à renseigner.")
        tk.Label(
            actions,
            textvariable=self.swile_api_auth_status,
            anchor="e",
            fg="#555555",
        ).pack(side="right", fill="x", expand=True)

        self.swile_api_controls.extend(
            (
                self.swile_api_client_id_entry,
                self.swile_api_client_secret_entry,
                self.swile_api_save_button,
                self.swile_api_reload_button,
                self.swile_api_connect_button,
            )
        )

    def _build_swile_api_list_tab(self, parent):
        """Construit le sous-onglet de listing salariés via API."""
        section = tk.LabelFrame(parent, text="Salariés Swile actifs", padx=10, pady=8)
        section.pack(fill="both", expand=True, padx=10, pady=10)
        self.swile_api_refresh_button = tk.Button(
            section,
            text="Afficher la liste complète depuis l’API",
            command=self._refresh_swile_api_employees,
        )
        self.swile_api_refresh_button.pack(anchor="w", pady=(0, 8))
        columns = ("email", "prenom", "nom", "matricule", "id")
        self.swile_api_employees_tree = ttk.Treeview(
            section,
            columns=columns,
            show="headings",
            height=14,
        )
        headings = {
            "email": ("Email", 240),
            "prenom": ("Prénom", 130),
            "nom": ("Nom", 170),
            "matricule": ("Matricule", 150),
            "id": ("ID Swile", 220),
        }
        for column, (title, width) in headings.items():
            self.swile_api_employees_tree.heading(column, text=title)
            self.swile_api_employees_tree.column(column, width=width, anchor="w")
        y_scroll = ttk.Scrollbar(
            section, orient="vertical", command=self.swile_api_employees_tree.yview
        )
        self.swile_api_employees_tree.configure(yscrollcommand=y_scroll.set)
        self.swile_api_employees_tree.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")
        self.swile_api_controls.append(self.swile_api_refresh_button)

    def _build_swile_api_create_tab(self, parent):
        """Construit le sous-onglet POC de préparation des créations."""
        section = tk.LabelFrame(parent, text="Provisionnement (POC)", padx=10, pady=8)
        section.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(
            section,
            text=(
                "POC : ce sous-onglet sera branché dans un second temps. "
                "La récupération de la liste salariés via API est déjà opérationnelle."
            ),
            anchor="w",
            justify="left",
            wraplength=820,
            fg="#555555",
        ).pack(fill="x")

    def _build_swile_api_deactivate_tab(self, parent):
        """Construit le sous-onglet POC de préparation des désactivations."""
        section = tk.LabelFrame(parent, text="Déprovisionnement (POC)", padx=10, pady=8)
        section.pack(fill="both", expand=True, padx=10, pady=10)
        tk.Label(
            section,
            text=(
                "POC : ce sous-onglet sera branché dans un second temps. "
                "La récupération de la liste salariés via API est déjà opérationnelle."
            ),
            anchor="w",
            justify="left",
            wraplength=820,
            fg="#555555",
        ).pack(fill="x")

    def _set_swile_api_connected(self, connected):
        """Active les sous-onglets nécessitant une connexion API valide."""
        state = "normal" if connected else "disabled"
        for tab_index in (1, 2, 3):
            self.swile_api_subtabs.tab(tab_index, state=state)
        self.swile_api_connected = connected

    def _load_swile_api_credentials(self):
        """Charge les identifiants depuis le fichier local."""
        try:
            credentials = load_swile_api_credentials()
        except (OSError, UnicodeError, ValueError) as error:
            self.swile_api_auth_status.set("Configuration invalide.")
            messagebox.showerror(
                "Configuration Swile API invalide", str(error), parent=self
            )
            return
        self.swile_api_client_id_var.set(credentials["client_id"])
        self.swile_api_client_secret_var.set(credentials["client_secret"])
        if credentials["client_id"] and credentials["client_secret"]:
            self.swile_api_auth_status.set("Identifiants chargés.")
        else:
            self.swile_api_auth_status.set("Configuration à renseigner.")

    def _save_swile_api_credentials(self):
        """Valide et sauvegarde les identifiants Swile API."""
        try:
            save_swile_api_credentials(
                self.swile_api_client_id_var.get(),
                self.swile_api_client_secret_var.get(),
            )
        except (OSError, UnicodeError, ValueError) as error:
            self.swile_api_auth_status.set("Enregistrement impossible.")
            messagebox.showerror(
                "Configuration Swile API invalide", str(error), parent=self
            )
            return
        self.swile_api_auth_status.set("Configuration enregistrée.")

    def _connect_swile_api(self):
        """Teste les identifiants et ouvre les sous-onglets API."""

        def connect_task():
            client = SwileApiClient(
                self.swile_api_client_id_var.get(),
                self.swile_api_client_secret_var.get(),
            )
            client.list_employees(limit=1)
            self.swile_api_client = client
            return "Connexion Swile API réussie."

        self._run_swile_api_task(
            "Connexion à l’API Swile en cours…",
            connect_task,
            on_success=lambda _message: (
                self._set_swile_api_connected(True),
                self.swile_api_auth_status.set("Connecté à l’API Swile."),
            ),
        )

    def _refresh_swile_api_employees(self):
        """Charge la liste complète des salariés depuis l’API Swile."""
        if not self.swile_api_connected:
            messagebox.showerror(
                "Connexion requise",
                "Connectez-vous d’abord dans le sous-onglet Authentification.",
                parent=self,
            )
            return

        def list_task():
            employees = self.swile_api_client.list_employees(limit=100)
            rows = [self.swile_api_client.to_swile_row(employee) for employee in employees]
            return rows

        self._run_swile_api_task(
            "Récupération des salariés Swile en cours…",
            list_task,
            on_success=self._display_swile_api_employees,
        )

    def _display_swile_api_employees(self, rows):
        """Affiche la liste des salariés Swile dans le tableau."""
        self.swile_api_employees_tree.delete(*self.swile_api_employees_tree.get_children())
        for row in rows:
            self.swile_api_employees_tree.insert(
                "",
                "end",
                values=(
                    row.get("Email", ""),
                    row.get("Prénom", ""),
                    row.get("Nom", ""),
                    row.get("Matricule", ""),
                    row.get("ID Swile", ""),
                ),
            )
        self._set_output(
            "Liste salariés Swile récupérée.\n"
            f"Total : {len(rows)} utilisateur(s)."
        )
        self.status.set("Traitement terminé.")

    def _run_swile_api_task(self, status_message, task, on_success=None):
        """Exécute une action Swile API dans un thread non bloquant."""
        if self.is_running:
            return
        self.is_running = True
        self.current_action = "swile_api"
        self.status.set(status_message)
        self._set_output(f"{status_message}\n")
        self._set_run_buttons_state("disabled")
        self._set_config_controls_state("disabled")
        threading.Thread(
            target=self._run_swile_api_worker,
            args=(task, on_success),
            daemon=True,
        ).start()

    def _run_swile_api_worker(self, task, on_success):
        """Exécute la tâche API puis restaure l’interface."""
        output_writer = _SwileApiOutputWriter(self)
        try:
            with redirect_stdout(output_writer), redirect_stderr(output_writer):
                result = task()
                if isinstance(result, str):
                    print(result)
            self.after(
                0,
                lambda: self._finish_swile_api_task(
                    output_writer.getvalue(),
                    "",
                    0,
                    result,
                    on_success,
                ),
            )
        except Exception:
            error = traceback.format_exc()
            output_writer.write(error)
            self.after(
                0,
                lambda message=error: self._finish_swile_api_task(
                    "",
                    message,
                    1,
                    None,
                    on_success,
                ),
            )

    def _finish_swile_api_task(
        self, stdout, stderr, returncode, result_payload, on_success
    ):
        """Finalise l’exécution d’une tâche API Swile."""
        self.is_running = False
        self.current_action = None
        self._set_run_buttons_state("normal")
        self._set_config_controls_state("normal")
        if returncode == 0 and on_success is not None:
            on_success(result_payload)
        result = "\n".join(part for part in (stdout.strip(), stderr.strip()) if part)
        if result and (
            on_success is None or on_success is not self._display_swile_api_employees
        ):
            self._set_output(result)
        if returncode != 0:
            self.status.set("Le traitement a échoué.")
            messagebox.showerror(
                "Échec du traitement Swile API",
                "Une erreur est survenue. Consultez le détail ci-dessous.",
                parent=self,
            )
        elif on_success is not self._display_swile_api_employees:
            self.status.set("Traitement terminé.")


class _SwileApiOutputWriter:
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

