import unittest
from unittest.mock import MagicMock

from services.swile_api_service import SwileApiClient


def _response(status_code, payload, content_type="application/json"):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = payload
    mock.text = str(payload)
    mock.headers = {"Content-Type": content_type}
    return mock


class SwileApiServiceTests(unittest.TestCase):
    def test_list_employees_fetches_all_pages(self):
        session = MagicMock()
        session.post.return_value = _response(
            200,
            {
                "access_token": "token",
                "token_type": "Bearer",
                "expires_in": 120,
            },
        )
        session.get.side_effect = [
            _response(
                200,
                {
                    "data": [
                        {
                            "id": "1",
                            "email": "a@example.com",
                            "firstName": "A",
                            "lastName": "One",
                            "employeeNumber": "a1",
                        }
                    ],
                    "nextCursor": "cursor-1",
                },
            ),
            _response(
                200,
                {
                    "data": [
                        {
                            "id": "2",
                            "email": "b@example.com",
                            "firstName": "B",
                            "lastName": "Two",
                            "employeeNumber": "b2",
                        }
                    ],
                    "nextCursor": None,
                },
            ),
        ]
        client = SwileApiClient("id", "secret", session=session)

        employees = client.list_employees()

        self.assertEqual(len(employees), 2)
        self.assertEqual(employees[0]["email"], "a@example.com")
        self.assertEqual(employees[1]["employeeNumber"], "b2")
        self.assertEqual(session.post.call_count, 1)
        self.assertEqual(session.get.call_count, 2)

    def test_to_swile_row_maps_expected_columns(self):
        row = SwileApiClient.to_swile_row(
            {
                "id": "uuid",
                "email": "ada@example.com",
                "firstName": "Ada",
                "lastName": "Lovelace",
                "employeeNumber": "HR-42",
            }
        )

        self.assertEqual(
            row,
            {
                "Prénom": "Ada",
                "Nom": "Lovelace",
                "Email": "ada@example.com",
                "Matricule": "HR-42",
                "ID Swile": "uuid",
            },
        )


if __name__ == "__main__":
    unittest.main()

