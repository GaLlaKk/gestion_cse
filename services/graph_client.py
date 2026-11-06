import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MAX_RATE_LIMIT_RETRIES = 5
REQUEST_TIMEOUT_SECONDS = 30


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


class GraphClient:
    """Client Microsoft Graph avec nouvelles tentatives sur erreurs réseau et 429."""

    def __init__(self, access_token, logger):
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.logger = logger

    def get(self, url):
        """Interroge Microsoft Graph en respectant les limites de débit."""
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
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
            time.sleep(delay)
