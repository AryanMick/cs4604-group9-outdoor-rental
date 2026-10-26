"""Small route tests that do not require a running MySQL server."""
from unittest import TestCase
from unittest.mock import patch

import rental_interface


def sample_data(table=None, page=1):
    data = {
        "connection": {
            "version": "8.4.13",
            "database": "outdoor_rental_group9",
            "user": "tester@localhost",
            "connection_id": 42,
            "checked": "2026-10-22 12:00:00 EDT",
        },
        "counts": dict(rental_interface.db_tools.EXPECTED_COUNTS),
        "total_rows": 300,
    }
    if table:
        data.update(
            {
                "table": table,
                "columns": ("customer_id", "first_name", "email"),
                "rows": ((21, "Sam", "SamTurner@gmail.com"),),
                "row_count": 30,
                "page": page,
                "total_pages": 2,
            }
        )
    return data


class InterfaceRoutesTest(TestCase):
    def setUp(self):
        rental_interface.app.config["TESTING"] = True
        self.client = rental_interface.app.test_client()

    @patch("rental_interface.read_database", side_effect=sample_data)
    def test_dashboard_shows_verified_connection_and_all_counts(self, _read):
        response = self.client.get("/")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Connection and queries successful", page)
        self.assertIn("300 total records", page)
        self.assertIn("admin_privileges", page)

    @patch("rental_interface.read_database", side_effect=sample_data)
    def test_table_page_shows_rows_and_pagination(self, read):
        response = self.client.get("/table/customer?page=2")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        read.assert_called_once_with("customer", 2)
        self.assertIn("SamTurner@gmail.com", page)
        self.assertIn("page 2 of 2", page)

    def test_unknown_table_is_rejected(self):
        self.assertEqual(self.client.get("/table/not_a_table").status_code, 404)

    @patch("rental_interface.read_database", side_effect=RuntimeError("test connection failure"))
    def test_database_error_is_red_and_never_claims_success(self, _read):
        response = self.client.get("/")
        page = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 503)
        self.assertIn("Database connection failed", page)
        self.assertIn("test connection failure", page)
        self.assertIn("Row counts unavailable", page)
        self.assertNotIn("0 total records", page)
        self.assertNotIn("Connection and queries successful", page)


if __name__ == "__main__":
    import unittest

    unittest.main()
