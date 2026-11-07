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
        with patch.object(requests.Session, "get", return_value=ok) as get:
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
                requests.Session,
                "get",
                side_effect=[response(429, {"Retry-After": "2"}), ok],
            ),
            patch.object(graph_client.time, "sleep") as sleep,
        ):
            result = GraphClient("jeton", Mock()).get("https://exemple/api")
        self.assertIs(result, ok)
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 2.0, delta=0.5)

    def test_rate_limit_pauses_requests_of_other_threads(self):
        """Vérifie qu’un 429 suspend aussi les requêtes suivantes."""
        client = GraphClient("jeton", Mock())
        with patch.object(graph_client.time, "sleep") as sleep:
            client._block_for(5)
            with patch.object(
                requests.Session, "get", return_value=response(200)
            ):
                client.get("https://exemple/api")
        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 5, delta=0.5)

    def test_batch_get_returns_ordered_responses_and_retries_throttled(self):
        """Vérifie l’ordre des réponses `$batch` et la relance des sous-requêtes 429."""

        def outer(items):
            result = Mock(status_code=200)
            result.json.return_value = {"responses": items}
            return result

        post = Mock(
            side_effect=[
                outer(
                    [
                        {"id": "1", "status": 200, "body": {"n": 1}},
                        {
                            "id": "0",
                            "status": 429,
                            "headers": {"Retry-After": "1"},
                            "body": None,
                        },
                    ]
                ),
                outer([{"id": "0", "status": 200, "body": {"n": 0}}]),
            ]
        )
        with (
            patch.object(requests.Session, "post", post),
            patch.object(graph_client.time, "sleep"),
        ):
            results = GraphClient("jeton", Mock()).batch_get(["/a", "/b"])
        self.assertEqual([item.json() for item in results], [{"n": 0}, {"n": 1}])
        retried = post.call_args_list[1].kwargs["json"]["requests"]
        self.assertEqual(
            retried, [{"id": "0", "method": "GET", "url": "/a"}]
        )

    def test_batch_get_splits_into_batches_of_twenty(self):
        """Vérifie la limite de 20 sous-requêtes par appel `$batch`."""

        def post(url, json=None, **_kwargs):
            result = Mock(status_code=200)
            result.json.return_value = {
                "responses": [
                    {"id": item["id"], "status": 200, "body": {}}
                    for item in json["requests"]
                ]
            }
            return result

        with patch.object(
            requests.Session, "post", side_effect=post
        ) as mocked_post:
            results = GraphClient("jeton", Mock()).batch_get(
                [f"/u{n}" for n in range(45)]
            )
        self.assertEqual(len(results), 45)
        self.assertEqual(mocked_post.call_count, 3)

    def test_network_error_is_raised_after_last_retry(self):
        """Vérifie que l’erreur réseau est propagée après épuisement des essais."""
        with (
            patch.object(
                requests.Session,
                "get",
                side_effect=requests.ConnectionError("réseau"),
            ) as get,
            patch.object(graph_client.time, "sleep"),
        ):
            with self.assertRaises(requests.ConnectionError):
                GraphClient("jeton", Mock()).get("https://exemple/api")
        self.assertEqual(get.call_count, graph_client.MAX_RATE_LIMIT_RETRIES + 1)
