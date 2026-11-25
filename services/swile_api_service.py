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

    def _api_get(self, path, params=None):
        response = self.session.get(
            f"{self.base_url}{path}",
            headers={"Authorization": f"Bearer {self._get_access_token()}"},
            params=params or {},
            timeout=30,
        )
        if response.status_code == 401:
            self._request_token()
            response = self.session.get(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self._get_access_token()}"},
                params=params or {},
                timeout=30,
            )
        if response.status_code >= 400:
            raise SwileApiError(
                f"Appel Swile {path} en erreur ({response.status_code}) : "
                f"{self._format_api_error(response)}"
            )
        return response.json()

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

