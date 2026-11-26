import threading
import tkinter as tk
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, timedelta
from tkinter import messagebox
from tkinter import ttk

from app.ui.constants import DELIMITERS, REQUIRED_COLUMNS
from domain.normalization import normalize_matricule, split_full_name
from services.csv_files import read_csv
from services.swile_api_config import (
    SWILE_API_CONFIG_PATH,
    load_swile_api_settings,
    save_swile_api_credentials,
    save_swile_api_subscribed_product_ids,
)
from services.swile_api_service import SwileApiClient, SwileApiError


class SwileApiPanelMixin:
    """Onglet d’intégration Swile API (authentification et opérations salariés)."""

    def _build_swile_api_tab(self, swile_api_tab):
        """Construit l’onglet Swile API et ses sous-onglets."""
        self.swile_api_products_by_id = {}
        self.swile_api_saved_product_ids = []
        self.swile_api_create_candidates = {}
        self.swile_api_deactivate_candidates = {}

        swile_api_subtabs = ttk.Notebook(swile_api_tab)
        swile_api_subtabs.pack(fill="both", expand=True)
        self.swile_api_subtabs = swile_api_subtabs
        auth_tab = tk.Frame(swile_api_subtabs)
        products_tab = tk.Frame(swile_api_subtabs)
        list_tab = tk.Frame(swile_api_subtabs)
        create_tab = tk.Frame(swile_api_subtabs)
        deactivate_tab = tk.Frame(swile_api_subtabs)
        swile_api_subtabs.add(auth_tab, text="Authentification")
        swile_api_subtabs.add(products_tab, text="Liste des produits")
        swile_api_subtabs.add(list_tab, text="Liste des salariés")
        swile_api_subtabs.add(create_tab, text="Création des salariés")
        swile_api_subtabs.add(deactivate_tab, text="Suppression des salariés")

        self._build_swile_api_auth_tab(auth_tab)
        self._build_swile_api_products_tab(products_tab)
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

    def _build_swile_api_products_tab(self, parent):
        """Construit le sous-onglet de listing des produits Swile."""
        section = tk.LabelFrame(parent, text="Produits Swile", padx=10, pady=8)
        section.pack(fill="both", expand=True, padx=10, pady=10)
        self.swile_api_refresh_products_button = tk.Button(
            section,
            text="Afficher les produits disponibles",
            command=self._refresh_swile_api_products,
        )
        self.swile_api_refresh_products_button.pack(anchor="w", pady=(0, 8))
        columns = ("id", "type", "nom", "actif", "souscrit")
        self.swile_api_products_tree = ttk.Treeview(
            section,
            columns=columns,
            show="headings",
            height=14,
        )
        headings = {
            "id": ("ID Produit", 260),
            "type": ("Type", 120),
            "nom": ("Nom", 170),
            "actif": ("Actif", 80),
            "souscrit": ("Souscrit le", 120),
        }
        for column, (title, width) in headings.items():
            self.swile_api_products_tree.heading(column, text=title)
            self.swile_api_products_tree.column(column, width=width, anchor="w")
        y_scroll = ttk.Scrollbar(
            section, orient="vertical", command=self.swile_api_products_tree.yview
        )
        self.swile_api_products_tree.configure(yscrollcommand=y_scroll.set)
        self.swile_api_products_tree.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")
        self.swile_api_controls.append(self.swile_api_refresh_products_button)

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
        """Construit le sous-onglet de préparation des créations."""
        section = tk.LabelFrame(parent, text="Provisionnement", padx=10, pady=8)
        section.pack(fill="both", expand=True, padx=10, pady=10)

        product_config = tk.LabelFrame(
            section,
            text="Produits à abonner par défaut",
            padx=10,
            pady=8,
        )
        product_config.pack(fill="x")
        tk.Label(
            product_config,
            text=(
                f"Configuration locale : {SWILE_API_CONFIG_PATH}\n"
                "Sélectionnez les produits à affecter lors de la création."
            ),
            anchor="w",
            justify="left",
            wraplength=820,
        ).pack(fill="x", pady=(0, 6))

        self.swile_api_product_listbox = tk.Listbox(
            product_config,
            selectmode="multiple",
            exportselection=False,
            height=6,
        )
        self.swile_api_product_listbox.pack(fill="x")

        config_actions = tk.Frame(product_config)
        config_actions.pack(fill="x", pady=(6, 0))
        self.swile_api_save_products_button = tk.Button(
            config_actions,
            text="Enregistrer les produits",
            command=self._save_swile_api_product_ids,
        )
        self.swile_api_save_products_button.pack(side="left")
        self.swile_api_reload_products_button = tk.Button(
            config_actions,
            text="Recharger les produits enregistrés",
            command=self._reload_swile_api_product_ids,
        )
        self.swile_api_reload_products_button.pack(side="left", padx=(6, 0))
        self.swile_api_product_config_status = tk.StringVar(value="")
        tk.Label(
            config_actions,
            textvariable=self.swile_api_product_config_status,
            anchor="e",
            fg="#555555",
        ).pack(side="right", fill="x", expand=True)

        actions = tk.Frame(section)
        actions.pack(fill="x", pady=(8, 6))
        self.swile_api_prepare_additions_button = tk.Button(
            actions,
            text="Préparer les ajouts",
            command=self._prepare_swile_api_additions,
        )
        self.swile_api_prepare_additions_button.pack(side="left")
        self.swile_api_select_all_additions_button = tk.Button(
            actions,
            text="Tout sélectionner",
            command=lambda: self._set_swile_api_create_selection(True),
        )
        self.swile_api_select_all_additions_button.pack(side="left", padx=(6, 0))
        self.swile_api_select_none_additions_button = tk.Button(
            actions,
            text="Tout désélectionner",
            command=lambda: self._set_swile_api_create_selection(False),
        )
        self.swile_api_select_none_additions_button.pack(side="left", padx=(6, 0))
        self.swile_api_add_all_button = tk.Button(
            actions,
            text="Ajouter les personnes à Swile",
            command=lambda: self._add_swile_api_candidates(False),
        )
        self.swile_api_add_all_button.pack(side="left", padx=(6, 0))
        self.swile_api_add_selected_button = tk.Button(
            actions,
            text="Ajouter les personnes sélectionnées de Swile",
            command=lambda: self._add_swile_api_candidates(True),
        )
        self.swile_api_add_selected_button.pack(side="left", padx=(6, 0))

        columns = ("selected", "matricule", "email", "prenom", "nom")
        self.swile_api_create_tree = ttk.Treeview(
            section,
            columns=columns,
            show="headings",
            height=12,
        )
        headings = {
            "selected": ("Sélection", 95),
            "matricule": ("Matricule AD", 130),
            "email": ("Email", 220),
            "prenom": ("Prénom", 120),
            "nom": ("Nom", 160),
        }
        for column, (title, width) in headings.items():
            self.swile_api_create_tree.heading(column, text=title)
            self.swile_api_create_tree.column(column, width=width, anchor="w")
        create_scroll = ttk.Scrollbar(
            section, orient="vertical", command=self.swile_api_create_tree.yview
        )
        self.swile_api_create_tree.configure(yscrollcommand=create_scroll.set)
        self.swile_api_create_tree.pack(side="left", fill="both", expand=True)
        create_scroll.pack(side="right", fill="y")

        self.swile_api_controls.extend(
            (
                self.swile_api_product_listbox,
                self.swile_api_save_products_button,
                self.swile_api_reload_products_button,
                self.swile_api_prepare_additions_button,
                self.swile_api_select_all_additions_button,
                self.swile_api_select_none_additions_button,
                self.swile_api_add_all_button,
                self.swile_api_add_selected_button,
            )
        )

    def _build_swile_api_deactivate_tab(self, parent):
        """Construit le sous-onglet de préparation des suppressions."""
        section = tk.LabelFrame(parent, text="Déprovisionnement", padx=10, pady=8)
        section.pack(fill="both", expand=True, padx=10, pady=10)

        actions = tk.Frame(section)
        actions.pack(fill="x", pady=(0, 6))
        self.swile_api_prepare_deletions_button = tk.Button(
            actions,
            text="Préparer les suppressions",
            command=self._prepare_swile_api_deletions,
        )
        self.swile_api_prepare_deletions_button.pack(side="left")
        self.swile_api_select_all_deletions_button = tk.Button(
            actions,
            text="Tout sélectionner",
            command=lambda: self._set_swile_api_deactivate_selection(True),
        )
        self.swile_api_select_all_deletions_button.pack(side="left", padx=(6, 0))
        self.swile_api_select_none_deletions_button = tk.Button(
            actions,
            text="Tout désélectionner",
            command=lambda: self._set_swile_api_deactivate_selection(False),
        )
        self.swile_api_select_none_deletions_button.pack(side="left", padx=(6, 0))
        self.swile_api_delete_selected_button = tk.Button(
            actions,
            text="Supprimer les personnes sélectionnées de Swile",
            command=self._deprovision_swile_api_candidates,
        )
        self.swile_api_delete_selected_button.pack(side="left", padx=(6, 0))

        columns = ("selected", "matricule", "email", "prenom", "nom", "id")
        self.swile_api_deactivate_tree = ttk.Treeview(
            section,
            columns=columns,
            show="headings",
            height=12,
        )
        headings = {
            "selected": ("Sélection", 95),
            "matricule": ("Matricule Swile", 130),
            "email": ("Email", 220),
            "prenom": ("Prénom", 120),
            "nom": ("Nom", 160),
            "id": ("ID Swile", 180),
        }
        for column, (title, width) in headings.items():
            self.swile_api_deactivate_tree.heading(column, text=title)
            self.swile_api_deactivate_tree.column(column, width=width, anchor="w")
        deactivate_scroll = ttk.Scrollbar(
            section,
            orient="vertical",
            command=self.swile_api_deactivate_tree.yview,
        )
        self.swile_api_deactivate_tree.configure(yscrollcommand=deactivate_scroll.set)
        self.swile_api_deactivate_tree.pack(side="left", fill="both", expand=True)
        deactivate_scroll.pack(side="right", fill="y")

        self.swile_api_controls.extend(
            (
                self.swile_api_prepare_deletions_button,
                self.swile_api_select_all_deletions_button,
                self.swile_api_select_none_deletions_button,
                self.swile_api_delete_selected_button,
            )
        )

    def _set_swile_api_connected(self, connected):
        """Active les sous-onglets nécessitant une connexion API valide."""
        state = "normal" if connected else "disabled"
        for tab_index in (1, 2, 3, 4):
            self.swile_api_subtabs.tab(tab_index, state=state)
        self.swile_api_connected = connected

    def _load_swile_api_credentials(self):
        """Charge les identifiants depuis le fichier local."""
        try:
            settings = load_swile_api_settings()
        except (OSError, UnicodeError, ValueError) as error:
            self.swile_api_auth_status.set("Configuration invalide.")
            messagebox.showerror(
                "Configuration Swile API invalide", str(error), parent=self
            )
            return
        self.swile_api_client_id_var.set(settings["client_id"])
        self.swile_api_client_secret_var.set(settings["client_secret"])
        self.swile_api_saved_product_ids = settings["subscribed_product_ids"]
        self._refresh_swile_api_product_selector()
        if settings["client_id"] and settings["client_secret"]:
            self.swile_api_auth_status.set("Identifiants chargés.")
        else:
            self.swile_api_auth_status.set("Configuration à renseigner.")
        if self.swile_api_saved_product_ids:
            self.swile_api_product_config_status.set(
                "Produits enregistrés rechargés."
            )
        else:
            self.swile_api_product_config_status.set(
                "Aucun produit enregistré."
            )

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

    def _reload_swile_api_product_ids(self):
        """Recharge les produits enregistrés dans la configuration locale."""
        try:
            self.swile_api_saved_product_ids = load_swile_api_settings()[
                "subscribed_product_ids"
            ]
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror(
                "Configuration Swile API invalide", str(error), parent=self
            )
            return
        self._refresh_swile_api_product_selector()
        if self.swile_api_saved_product_ids:
            self.swile_api_product_config_status.set(
                "Produits enregistrés rechargés."
            )
        else:
            self.swile_api_product_config_status.set(
                "Aucun produit enregistré."
            )

    def _refresh_swile_api_product_selector(self):
        """Rafraîchit la liste de sélection des produits à abonner."""
        listbox = self.swile_api_product_listbox
        listbox.delete(0, tk.END)
        products = sorted(
            self.swile_api_products_by_id.values(),
            key=lambda product: (product.get("name") or "", product.get("id") or ""),
        )
        for product in products:
            product_id = product.get("id") or ""
            name = (product.get("name") or "").strip()
            kind = (product.get("kind") or "").strip()
            if name and kind:
                label = f"{name} ({kind}) — {product_id}"
            elif name:
                label = f"{name} — {product_id}"
            else:
                label = product_id
            listbox.insert(tk.END, label)

        selected_ids = set(self.swile_api_saved_product_ids)
        for index, product in enumerate(products):
            product_id = (product.get("id") or "").strip()
            if product_id and product_id in selected_ids:
                listbox.selection_set(index)

    def _selected_swile_api_product_ids(self):
        """Retourne les identifiants produits sélectionnés dans l’UI."""
        selected_indices = self.swile_api_product_listbox.curselection()
        products = sorted(
            self.swile_api_products_by_id.values(),
            key=lambda product: (product.get("name") or "", product.get("id") or ""),
        )
        selected_ids = []
        for index in selected_indices:
            product = products[index]
            product_id = (product.get("id") or "").strip()
            if product_id:
                selected_ids.append(product_id)
        return selected_ids

    def _save_swile_api_product_ids(self):
        """Enregistre la sélection des produits à abonner par défaut."""
        product_ids = self._selected_swile_api_product_ids()
        if not product_ids:
            messagebox.showerror(
                "Produits manquants",
                "Sélectionnez au moins un produit dans la liste.",
                parent=self,
            )
            return
        try:
            save_swile_api_subscribed_product_ids(product_ids)
        except (OSError, UnicodeError, ValueError) as error:
            self.swile_api_product_config_status.set("Enregistrement impossible.")
            messagebox.showerror(
                "Configuration Swile API invalide", str(error), parent=self
            )
            return
        self.swile_api_saved_product_ids = product_ids
        self.swile_api_product_config_status.set("Produits enregistrés.")

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

    def _refresh_swile_api_products(self):
        """Charge la liste complète des produits depuis l’API Swile."""
        if not self.swile_api_connected:
            messagebox.showerror(
                "Connexion requise",
                "Connectez-vous d’abord dans le sous-onglet Authentification.",
                parent=self,
            )
            return

        def list_task():
            products = self.swile_api_client.list_products()
            rows = [self.swile_api_client.to_product_row(product) for product in products]
            return {"products": products, "rows": rows}

        self._run_swile_api_task(
            "Récupération des produits Swile en cours…",
            list_task,
            on_success=self._display_swile_api_products,
        )

    def _display_swile_api_products(self, payload):
        """Affiche la liste des produits Swile et met à jour la sélection."""
        rows = payload["rows"]
        products = payload["products"]
        self.swile_api_products_tree.delete(*self.swile_api_products_tree.get_children())
        for row in rows:
            self.swile_api_products_tree.insert(
                "",
                "end",
                values=(
                    row.get("ID Produit", ""),
                    row.get("Type", ""),
                    row.get("Nom", ""),
                    row.get("Actif", ""),
                    row.get("Souscrit le", ""),
                ),
            )
        self.swile_api_products_by_id = {
            (product.get("id") or "").strip(): product for product in products
        }
        self._refresh_swile_api_product_selector()
        self._set_output(
            "Liste produits Swile récupérée.\n"
            f"Total : {len(rows)} produit(s)."
        )
        self.status.set("Traitement terminé.")

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

    @staticmethod
    def _split_names_for_provisioning(full_name, email):
        """Sépare prénom/nom avec fallback si le nom AD est incomplet."""
        split = split_full_name(full_name)
        if split:
            return split
        email_local_part = (email or "").split("@")[0].strip()
        fallback = email_local_part or (full_name or "").strip() or "Inconnu"
        return fallback, fallback

    def _prepare_swile_api_additions(self):
        """Prépare la liste AD absente de Swile à partir du matricule/login AD."""
        if not self.swile_api_connected:
            messagebox.showerror(
                "Connexion requise",
                "Connectez-vous d’abord dans le sous-onglet Authentification.",
                parent=self,
            )
            return
        active_directory_path = self._current_file("active_directory")
        if active_directory_path is None:
            messagebox.showerror(
                "Fichier manquant",
                "Ajoutez un export Active Directory valide avant de préparer les ajouts.",
                parent=self,
            )
            return

        def prepare_task():
            _, active_directory_users = read_csv(
                active_directory_path,
                DELIMITERS["active_directory"],
                REQUIRED_COLUMNS["active_directory"],
            )
            swile_employees = self.swile_api_client.list_employees(limit=100)
            swile_matricules = {
                normalize_matricule(employee.get("employeeNumber") or "")
                for employee in swile_employees
                if employee.get("employeeNumber")
            }
            candidates = []
            for user in active_directory_users:
                matricule_ad = (user.get("Identifiant") or "").strip()
                normalized_matricule = normalize_matricule(matricule_ad)
                if not normalized_matricule or normalized_matricule in swile_matricules:
                    continue
                email = (user.get("Email") or "").strip()
                full_name = (user.get("Nom") or "").strip()
                first_name, last_name = self._split_names_for_provisioning(
                    full_name, email
                )
                candidates.append(
                    {
                        "selected": True,
                        "Matricule": matricule_ad,
                        "Email": email,
                        "Prénom": first_name,
                        "Nom": last_name,
                    }
                )
            return candidates

        self._run_swile_api_task(
            "Préparation des ajouts Swile en cours…",
            prepare_task,
            on_success=self._display_swile_api_additions,
        )

    def _display_swile_api_additions(self, candidates):
        """Affiche les salariés AD absents de Swile pour provisionnement."""
        self.swile_api_create_tree.delete(*self.swile_api_create_tree.get_children())
        self.swile_api_create_candidates = {}
        for candidate in candidates:
            iid = self.swile_api_create_tree.insert(
                "",
                "end",
                values=(
                    "Oui",
                    candidate["Matricule"],
                    candidate["Email"],
                    candidate["Prénom"],
                    candidate["Nom"],
                ),
            )
            self.swile_api_create_candidates[iid] = candidate
        self._set_output(
            "Préparation des ajouts terminée.\n"
            f"Total à provisionner : {len(candidates)} collaborateur(s)."
        )
        self.status.set("Traitement terminé.")

    def _set_swile_api_create_selection(self, selected):
        """Applique une sélection globale sur la liste des ajouts préparés."""
        for iid in self.swile_api_create_tree.get_children():
            candidate = self.swile_api_create_candidates[iid]
            candidate["selected"] = selected
            self.swile_api_create_tree.set(iid, "selected", "Oui" if selected else "Non")

    def _add_swile_api_candidates(self, selected_only):
        """Provisionne des collaborateurs puis les abonne aux produits configurés."""
        if not self.swile_api_connected:
            messagebox.showerror(
                "Connexion requise",
                "Connectez-vous d’abord dans le sous-onglet Authentification.",
                parent=self,
            )
            return
        if not self.swile_api_create_candidates:
            messagebox.showerror(
                "Préparation requise",
                "Préparez d’abord la liste des ajouts.",
                parent=self,
            )
            return
        product_ids = self._selected_swile_api_product_ids()
        if not product_ids:
            messagebox.showerror(
                "Produits manquants",
                "Sélectionnez puis enregistrez les produits à abonner.",
                parent=self,
            )
            return
        candidates = []
        for candidate in self.swile_api_create_candidates.values():
            if selected_only and not candidate["selected"]:
                continue
            candidates.append(candidate)
        if not candidates:
            messagebox.showerror(
                "Sélection vide",
                "Aucune personne sélectionnée pour la création.",
                parent=self,
            )
            return

        def add_task():
            created_count = 0
            existing_count = 0
            enrolled_count = 0
            already_enrolled_count = 0
            errors = []
            for candidate in candidates:
                try:
                    employee, created = self.swile_api_client.provision_employee(
                        candidate["Email"],
                        candidate["Prénom"],
                        candidate["Nom"],
                        candidate["Matricule"],
                    )
                    employee_id = (employee.get("id") or "").strip()
                    if not employee_id:
                        raise SwileApiError(
                            "Le salarié Swile retourné ne contient pas d’identifiant."
                        )
                    if created:
                        created_count += 1
                    else:
                        existing_count += 1
                    for product_id in product_ids:
                        enrollment = self.swile_api_client.enroll_employee_to_product(
                            employee_id,
                            product_id,
                        )
                        if enrollment.get("alreadyEnrolled"):
                            already_enrolled_count += 1
                        else:
                            enrolled_count += 1
                except (ValueError, SwileApiError) as error:
                    errors.append(
                        f"- {candidate['Email'] or candidate['Matricule']} : {error}"
                    )
            return {
                "created_count": created_count,
                "existing_count": existing_count,
                "enrolled_count": enrolled_count,
                "already_enrolled_count": already_enrolled_count,
                "errors": errors,
                "processed_count": len(candidates),
                "products_count": len(product_ids),
            }

        status_message = (
            "Provisionnement des personnes sélectionnées en cours…"
            if selected_only
            else "Provisionnement des nouveaux arrivants en cours…"
        )
        self._run_swile_api_task(
            status_message,
            add_task,
            on_success=self._display_swile_api_additions_result,
        )

    def _display_swile_api_additions_result(self, result):
        """Affiche le résumé des créations/inscriptions réalisées."""
        lines = [
            "Création et abonnement terminés.",
            f"- Collaborateurs traités : {result['processed_count']}",
            f"- Produits appliqués : {result['products_count']}",
            f"- Créés : {result['created_count']}",
            f"- Déjà existants : {result['existing_count']}",
            f"- Inscriptions créées : {result['enrolled_count']}",
            f"- Inscriptions déjà actives : {result['already_enrolled_count']}",
        ]
        if result["errors"]:
            lines.append(f"- Erreurs : {len(result['errors'])}")
            lines.extend(result["errors"])
        self._set_output("\n".join(lines))
        self.status.set("Traitement terminé.")

    def _prepare_swile_api_deletions(self):
        """Prépare la liste Swile absente de l’Active Directory."""
        if not self.swile_api_connected:
            messagebox.showerror(
                "Connexion requise",
                "Connectez-vous d’abord dans le sous-onglet Authentification.",
                parent=self,
            )
            return
        active_directory_path = self._current_file("active_directory")
        if active_directory_path is None:
            messagebox.showerror(
                "Fichier manquant",
                "Ajoutez un export Active Directory valide avant de préparer les suppressions.",
                parent=self,
            )
            return

        def prepare_task():
            _, active_directory_users = read_csv(
                active_directory_path,
                DELIMITERS["active_directory"],
                REQUIRED_COLUMNS["active_directory"],
            )
            active_directory_matricules = {
                normalize_matricule(user.get("Identifiant") or "")
                for user in active_directory_users
                if user.get("Identifiant")
            }
            swile_employees = self.swile_api_client.list_employees(limit=100)
            candidates = []
            for employee in swile_employees:
                normalized_matricule = normalize_matricule(
                    employee.get("employeeNumber") or ""
                )
                if (
                    not normalized_matricule
                    or normalized_matricule in active_directory_matricules
                ):
                    continue
                candidate = self.swile_api_client.to_swile_row(employee)
                candidate["selected"] = True
                candidates.append(candidate)
            return candidates

        self._run_swile_api_task(
            "Préparation des suppressions Swile en cours…",
            prepare_task,
            on_success=self._display_swile_api_deletions,
        )

    def _display_swile_api_deletions(self, candidates):
        """Affiche les salariés Swile absents d’AD à supprimer."""
        self.swile_api_deactivate_tree.delete(*self.swile_api_deactivate_tree.get_children())
        self.swile_api_deactivate_candidates = {}
        for candidate in candidates:
            iid = self.swile_api_deactivate_tree.insert(
                "",
                "end",
                values=(
                    "Oui",
                    candidate.get("Matricule", ""),
                    candidate.get("Email", ""),
                    candidate.get("Prénom", ""),
                    candidate.get("Nom", ""),
                    candidate.get("ID Swile", ""),
                ),
            )
            self.swile_api_deactivate_candidates[iid] = candidate
        self._set_output(
            "Préparation des suppressions terminée.\n"
            f"Total à supprimer : {len(candidates)} collaborateur(s)."
        )
        self.status.set("Traitement terminé.")

    def _set_swile_api_deactivate_selection(self, selected):
        """Applique une sélection globale sur la liste des suppressions."""
        for iid in self.swile_api_deactivate_tree.get_children():
            candidate = self.swile_api_deactivate_candidates[iid]
            candidate["selected"] = selected
            self.swile_api_deactivate_tree.set(
                iid,
                "selected",
                "Oui" if selected else "Non",
            )

    def _deprovision_swile_api_candidates(self):
        """Supprime les collaborateurs sélectionnés avec leftAt à J-1."""
        if not self.swile_api_connected:
            messagebox.showerror(
                "Connexion requise",
                "Connectez-vous d’abord dans le sous-onglet Authentification.",
                parent=self,
            )
            return
        if not self.swile_api_deactivate_candidates:
            messagebox.showerror(
                "Préparation requise",
                "Préparez d’abord la liste des suppressions.",
                parent=self,
            )
            return
        candidates = [
            candidate
            for candidate in self.swile_api_deactivate_candidates.values()
            if candidate["selected"]
        ]
        if not candidates:
            messagebox.showerror(
                "Sélection vide",
                "Aucune personne sélectionnée pour la suppression.",
                parent=self,
            )
            return
        left_at = (date.today() - timedelta(days=1)).isoformat()

        def delete_task():
            deleted_count = 0
            managed_by_hris_count = 0
            errors = []
            for candidate in candidates:
                try:
                    self.swile_api_client.deprovision_employee(
                        candidate.get("ID Swile", ""),
                        left_at,
                    )
                    deleted_count += 1
                except (ValueError, SwileApiError) as error:
                    if "MANAGED_BY_HRIS" in str(error):
                        managed_by_hris_count += 1
                        continue
                    errors.append(
                        f"- {candidate.get('Email') or candidate.get('ID Swile')} : {error}"
                    )
            return {
                "deleted_count": deleted_count,
                "managed_by_hris_count": managed_by_hris_count,
                "errors": errors,
                "processed_count": len(candidates),
                "left_at": left_at,
            }

        self._run_swile_api_task(
            "Suppression des collaborateurs sélectionnés en cours…",
            delete_task,
            on_success=self._display_swile_api_deletions_result,
        )

    def _display_swile_api_deletions_result(self, result):
        """Affiche le résumé des suppressions réalisées."""
        lines = [
            "Suppression des collaborateurs terminée.",
            f"- Date leftAt appliquée : {result['left_at']}",
            f"- Collaborateurs traités : {result['processed_count']}",
            f"- Supprimés : {result['deleted_count']}",
            f"- Gérés par SIRH (non supprimés) : {result['managed_by_hris_count']}",
        ]
        if result["errors"]:
            lines.append(f"- Erreurs : {len(result['errors'])}")
            lines.extend(result["errors"])
        self._set_output("\n".join(lines))
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
        if result and on_success is None:
            self._set_output(result)
        if returncode != 0:
            self.status.set("Le traitement a échoué.")
            messagebox.showerror(
                "Échec du traitement Swile API",
                "Une erreur est survenue. Consultez le détail ci-dessous.",
                parent=self,
            )
        elif on_success is None:
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
