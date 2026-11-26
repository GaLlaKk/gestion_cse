import time

import requests


class SwileApiError(RuntimeError):
    """Erreur fonctionnelle de communication avec l’API Swile."""


class SwileApiClient:
    """Client API Swile (OAuth client credentials + endpoints salariés)."""

    def __init__(
        self,
        client_id,
        client_secret,
        base_url="https://integrations.swile.co",
        session=None,
    ):
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.access_token = None
        self.token_expires_at = 0.0
        if not self.client_id or not self.client_secret:
            raise ValueError("Les identifiants Swile API sont requis.")

    def _format_api_error(self, response):
        content_type = (response.headers.get("Content-Type") or "").casefold()
        if "application/problem+json" in content_type or "application/json" in content_type:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            detail = payload.get("detail") or payload.get("error_description")
            title = payload.get("title") or payload.get("error")
            if detail and title:
                return f"{title} — {detail}"
            return detail or title or response.text.strip()
        return response.text.strip()

    def _request_token(self):
        response = self.session.post(
            f"{self.base_url}/v1/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=30,
        )
        if response.status_code >= 400:
            raise SwileApiError(
                "Authentification Swile impossible "
                f"({response.status_code}) : {self._format_api_error(response)}"
            )
        payload = response.json()
        token = payload.get("access_token")
        expires_in = payload.get("expires_in")
        if not token or not isinstance(expires_in, int):
            raise SwileApiError(
                "Réponse OAuth Swile invalide : access_token/expires_in manquant."
            )
        self.access_token = token
        self.token_expires_at = time.time() + max(0, expires_in - 5)
        return token

    def _get_access_token(self):
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token
        return self._request_token()

    def _api_request(self, method, path, params=None, json_payload=None):
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self._get_access_token()}"},
            params=params or {},
            json=json_payload,
            timeout=30,
        )
        if response.status_code == 401:
            self._request_token()
            response = self.session.request(
                method,
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self._get_access_token()}"},
                params=params or {},
                json=json_payload,
                timeout=30,
            )
        return response

    def _decode_json_response(self, response):
        if not response.text.strip():
            return None
        content_type = (response.headers.get("Content-Type") or "").casefold()
        if "json" in content_type:
            return response.json()
        return None

    def _api_get(self, path, params=None):
        response = self._api_request("GET", path, params=params)
        if response.status_code >= 400:
            raise SwileApiError(
                f"Appel Swile {path} en erreur ({response.status_code}) : "
                f"{self._format_api_error(response)}"
            )
        return response.json()

    def _api_post(self, path, payload):
        response = self._api_request("POST", path, json_payload=payload)
        if response.status_code >= 400:
            raise SwileApiError(
                f"Appel Swile {path} en erreur ({response.status_code}) : "
                f"{self._format_api_error(response)}"
            )
        return self._decode_json_response(response)

    def _api_delete(self, path, params=None):
        response = self._api_request("DELETE", path, params=params)
        if response.status_code >= 400:
            raise SwileApiError(
                f"Appel Swile {path} en erreur ({response.status_code}) : "
                f"{self._format_api_error(response)}"
            )
        return self._decode_json_response(response)

    def list_products(self):
        """Récupère les produits de l’entreprise disponibles via l’API Swile."""
        payload = self._api_get("/v1/products")
        data = payload.get("data")
        if not isinstance(data, list):
            raise SwileApiError(
                "Réponse Swile invalide : 'data' n’est pas une liste."
            )
        return data

    def list_employees(self, limit=100, search=None):
        """Récupère tous les salariés actifs de Swile (pagination curseur)."""
        employees = []
        cursor = None
        while True:
            params = {"limit": min(max(int(limit), 1), 100)}
            if cursor:
                params["cursor"] = cursor
            if search:
                params["search"] = search
            payload = self._api_get("/v1/employees", params=params)
            data = payload.get("data")
            if not isinstance(data, list):
                raise SwileApiError(
                    "Réponse Swile invalide : 'data' n’est pas une liste."
                )
            employees.extend(data)
            cursor = payload.get("nextCursor")
            if not cursor:
                break
        return employees

    def find_employee_by_email(self, email):
        """Recherche un salarié Swile existant par e-mail exact."""
        target_email = (email or "").strip().casefold()
        if not target_email:
            raise ValueError("L’e-mail du salarié est requis.")
        employees = self.list_employees(limit=100, search=target_email)
        for employee in employees:
            current_email = (employee.get("email") or "").strip().casefold()
            if current_email == target_email:
                return employee
        return None

    def provision_employee(self, email, first_name, last_name, employee_number):
        """Crée un salarié Swile ou retourne l’existant en cas de conflit e-mail."""
        payload = {
            "email": (email or "").strip(),
            "firstName": (first_name or "").strip(),
            "lastName": (last_name or "").strip(),
            "employeeNumber": (employee_number or "").strip(),
        }
        if not payload["email"] or not payload["firstName"] or not payload["lastName"]:
            raise ValueError(
                "email, firstName et lastName sont requis pour provisionner un salarié."
            )
        response = self._api_request("POST", "/v1/employees", json_payload=payload)
        if response.status_code == 409:
            existing = self.find_employee_by_email(payload["email"])
            if existing is None:
                raise SwileApiError(
                    "Création refusée (409) et salarié introuvable par e-mail : "
                    f"{payload['email']}."
                )
            return existing, False
        if response.status_code >= 400:
            raise SwileApiError(
                "Provisionnement Swile impossible "
                f"({response.status_code}) : {self._format_api_error(response)}"
            )
        created = self._decode_json_response(response) or {}
        return created, True

    def enroll_employee_to_product(
        self,
        employee_id,
        product_id,
        invitation_language="fr-FR",
    ):
        """Inscrit un salarié Swile à un produit (idempotent)."""
        normalized_employee_id = (employee_id or "").strip()
        normalized_product_id = (product_id or "").strip()
        if not normalized_employee_id:
            raise ValueError("L’identifiant salarié Swile est requis.")
        if not normalized_product_id:
            raise ValueError("L’identifiant produit Swile est requis.")
        response = self._api_request(
            "POST",
            f"/v1/employees/{normalized_employee_id}/enrollments",
            json_payload={
                "productId": normalized_product_id,
                "invitation": {"language": invitation_language},
            },
        )
        if response.status_code == 409:
            return {
                "employeeId": normalized_employee_id,
                "productId": normalized_product_id,
                "alreadyEnrolled": True,
            }
        if response.status_code >= 400:
            raise SwileApiError(
                "Inscription au produit impossible "
                f"({response.status_code}) : {self._format_api_error(response)}"
            )
        payload = self._decode_json_response(response)
        if isinstance(payload, dict):
            payload["alreadyEnrolled"] = False
            return payload
        return {
            "employeeId": normalized_employee_id,
            "productId": normalized_product_id,
            "alreadyEnrolled": False,
        }

    def deprovision_employee(self, employee_id, left_at):
        """Déprovisionne un salarié Swile à la date leftAt fournie."""
        normalized_employee_id = (employee_id or "").strip()
        normalized_left_at = (left_at or "").strip()
        if not normalized_employee_id:
            raise ValueError("L’identifiant salarié Swile est requis.")
        if not normalized_left_at:
            raise ValueError("La date leftAt est requise (YYYY-MM-DD).")
        response = self._api_request(
            "DELETE",
            f"/v1/employees/{normalized_employee_id}",
            params={"leftAt": normalized_left_at},
        )
        if response.status_code >= 400:
            raise SwileApiError(
                "Déprovisionnement impossible "
                f"({response.status_code}) : {self._format_api_error(response)}"
            )
        payload = self._decode_json_response(response)
        if isinstance(payload, dict):
            return payload
        return {
            "employeeId": normalized_employee_id,
            "leftAt": normalized_left_at,
        }

    @staticmethod
    def to_swile_row(employee):
        """Projette un salarié Swile API vers les colonnes métier de l’app."""
        return {
            "Prénom": (employee.get("firstName") or "").strip(),
            "Nom": (employee.get("lastName") or "").strip(),
            "Email": (employee.get("email") or "").strip(),
            "Matricule": (employee.get("employeeNumber") or "").strip(),
            "ID Swile": employee.get("id") or "",
        }

    @staticmethod
    def to_product_row(product):
        """Projette un produit Swile API vers les colonnes UI."""
        return {
            "ID Produit": (product.get("id") or "").strip(),
            "Type": (product.get("kind") or "").strip(),
            "Nom": (product.get("name") or "").strip(),
            "Actif": "Oui" if product.get("active") else "Non",
            "Souscrit le": (product.get("subscribedAt") or "").strip(),
        }

