import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests
from requests.adapters import HTTPAdapter

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MAX_RATE_LIMIT_RETRIES = 5
REQUEST_TIMEOUT_SECONDS = 30
MAX_BATCH_SIZE = 20
RETRYABLE_BATCH_STATUSES = frozenset({429, 503, 504})
DEFAULT_POOL_SIZE = 16


def retry_delay_seconds(retry_after, attempt):
    """Déduit le délai d’attente d’un en-tête Retry-After (secondes ou date)."""
    try:
        return float(retry_after)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(retry_after)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0, (retry_at - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return 2**attempt


class BatchResponse:
    """Réponse individuelle d’un `$batch`, avec l’interface utile de `Response`."""

    def __init__(self, status_code, headers, body):
        self.status_code = status_code
        self.headers = headers
        self._body = body

    def json(self):
        """Retourne le corps JSON de la réponse."""
        return self._body

    def raise_for_status(self):
        """Lève `HTTPError` pour un statut 4xx/5xx."""
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"Erreur Microsoft Graph {self.status_code} dans un lot de requêtes."
            )


class GraphClient:
    """Client Microsoft Graph avec nouvelles tentatives sur erreurs réseau et 429.

    Les connexions sont réutilisées (session partagée) et un 429 suspend toutes
    les requêtes, y compris celles des autres threads, jusqu’à la fin du délai.
    """

    def __init__(self, access_token, logger, pool_size=DEFAULT_POOL_SIZE):
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.logger = logger
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=1, pool_maxsize=pool_size)
        self.session.mount("https://", adapter)
        self._blocked_until = 0.0
        self._block_lock = threading.Lock()

    def _block_for(self, delay):
        """Suspend toutes les requêtes pendant `delay` secondes."""
        with self._block_lock:
            self._blocked_until = max(
                self._blocked_until, time.monotonic() + delay
            )

    def _wait_if_blocked(self):
        """Attend la fin d’une limitation de débit signalée par un autre thread."""
        with self._block_lock:
            remaining = self._blocked_until - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)

    def _request(self, method, url, **kwargs):
        """Envoie une requête en respectant les limites de débit."""
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            self._wait_if_blocked()
            try:
                response = getattr(self.session, method)(
                    url,
                    headers=self.headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    **kwargs,
                )
            except requests.RequestException as error:
                if attempt == MAX_RATE_LIMIT_RETRIES:
                    raise
                delay = 2**attempt
                self.logger.warning(
                    "Erreur reseau vers Microsoft Graph (%s) ; nouvelle tentative "
                    "dans %.1f s.",
                    error,
                    delay,
                )
                time.sleep(delay)
                continue
            if response.status_code != 429:
                return response

            if attempt == MAX_RATE_LIMIT_RETRIES:
                response.raise_for_status()

            delay = retry_delay_seconds(
                response.headers.get("Retry-After", ""), attempt
            )
            self.logger.warning(
                "Microsoft Graph limite les requêtes (429) ; nouvelle tentative "
                "dans %.1f s.",
                delay,
            )
            self._block_for(delay)

    def get(self, url):
        """Interroge Microsoft Graph en respectant les limites de débit."""
        return self._request("get", url)

    def batch_get(self, relative_urls):
        """Exécute des GET via `$batch` ; retourne les réponses dans l’ordre.

        Les URL sont relatives à `GRAPH_BASE_URL`. Les sous-requêtes limitées
        (429/503/504) sont rejouées après une attente partagée.
        """
        results = [None] * len(relative_urls)
        pending = list(range(len(relative_urls)))
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            retry = []
            delay = 0.0
            for start in range(0, len(pending), MAX_BATCH_SIZE):
                chunk = pending[start : start + MAX_BATCH_SIZE]
                response = self._request(
                    "post",
                    f"{GRAPH_BASE_URL}/$batch",
                    json={
                        "requests": [
                            {
                                "id": str(index),
                                "method": "GET",
                                "url": relative_urls[index],
                            }
                            for index in chunk
                        ]
                    },
                )
                response.raise_for_status()
                for item in response.json().get("responses", []):
                    index = int(item["id"])
                    results[index] = BatchResponse(
                        item["status"],
                        item.get("headers") or {},
                        item.get("body"),
                    )
                    if (
                        item["status"] in RETRYABLE_BATCH_STATUSES
                        and attempt < MAX_RATE_LIMIT_RETRIES
                    ):
                        retry.append(index)
                        delay = max(
                            delay,
                            retry_delay_seconds(
                                (item.get("headers") or {}).get(
                                    "Retry-After", ""
                                ),
                                attempt,
                            ),
                        )
                missing = [index for index in chunk if results[index] is None]
                if missing:
                    raise requests.HTTPError(
                        "Réponse $batch Microsoft Graph incomplète."
                    )
            if not retry:
                break
            self.logger.warning(
                "Microsoft Graph limite %s sous-requête(s) d’un lot ; "
                "nouvelle tentative dans %.1f s.",
                len(retry),
                delay,
            )
            self._block_for(delay)
            pending = retry
        return results
