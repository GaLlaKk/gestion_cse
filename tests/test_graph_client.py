import unittest
from unittest.mock import Mock, patch

import requests

from services import graph_client
from services.graph_client import GraphClient, retry_delay_seconds


def response(status_code, headers=None):
    return Mock(status_code=status_code, headers=headers or {})


class RetryDelayTests(unittest.TestCase):
    def test_numeric_retry_after_is_used(self):
        """Vérifie la lecture d’un Retry-After en secondes."""
        self.assertEqual(retry_delay_seconds("3", 0), 3.0)

    def test_invalid_retry_after_uses_exponential_backoff(self):
        """Vérifie le repli exponentiel sur un en-tête illisible."""
        self.assertEqual(retry_delay_seconds("", 3), 8)


class GraphClientTests(unittest.TestCase):
    def test_sends_bearer_token_and_returns_non_throttled_response(self):
        """Vérifie l’en-tête d’autorisation et le retour direct d’une réponse."""
        ok = response(200)
        with patch.object(graph_client.requests, "get", return_value=ok) as get:
            result = GraphClient("jeton", Mock()).get("https://exemple/api")
        self.assertIs(result, ok)
        self.assertEqual(
            get.call_args.kwargs["headers"], {"Authorization": "Bearer jeton"}
        )

    def test_retries_after_rate_limit_then_succeeds(self):
        """Vérifie l’attente puis la nouvelle tentative après un 429."""
        ok = response(200)
        with (
            patch.object(
                graph_client.requests,
                "get",
                side_effect=[response(429, {"Retry-After": "2"}), ok],
            ),
            patch.object(graph_client.time, "sleep") as sleep,
        ):
            result = GraphClient("jeton", Mock()).get("https://exemple/api")
        self.assertIs(result, ok)
        sleep.assert_called_once_with(2.0)

    def test_network_error_is_raised_after_last_retry(self):
        """Vérifie que l’erreur réseau est propagée après épuisement des essais."""
        with (
            patch.object(
                graph_client.requests,
                "get",
                side_effect=requests.ConnectionError("réseau"),
            ) as get,
            patch.object(graph_client.time, "sleep"),
        ):
            with self.assertRaises(requests.ConnectionError):
                GraphClient("jeton", Mock()).get("https://exemple/api")
        self.assertEqual(get.call_count, graph_client.MAX_RATE_LIMIT_RETRIES + 1)
