"""Tests for finding equipment across businesses."""
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customer_service
from rental_interface import app


class BusinessSearchServiceTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchall.return_value = [
            (1, "Alpine Rentals", "First Street", "Kayak", "Touring boat"),
            (1, "Alpine Rentals", "First Street", "Kayak", "Another boat"),
            (1, "Alpine Rentals", "First Street", "Tent", "Four person"),
            (2, "Boat Shop", "Second Street", "Canoe", "A touring boat"),
            (3, "Empty Shop", "Third Street", None, None),
        ]
        connect = patch.object(customer_service.db_tools, "connect", return_value=self.connection)
        connect.start()
        self.addCleanup(connect.stop)

    def test_blank_search_keeps_all_businesses_including_empty(self):
        results = customer_service.list_businesses("  ")
        self.assertEqual([b["business_id"] for b in results], [1, 2, 3])
        self.assertTrue(all(not b["matching_equipment"] for b in results))
        self.assertIn("e.status <> 'RETIRED'", self.cursor.execute.call_args.args[0])
        self.connection.close.assert_called_once()

    def test_search_matches_type_description_and_business_name(self):
        results = customer_service.list_businesses(" TOURING ")
        self.assertEqual([b["business_id"] for b in results], [1, 2])
        self.assertEqual(results[0]["matching_equipment"], ["Kayak"])
        self.assertEqual(results[1]["matching_equipment"], ["Canoe"])
        self.assertEqual(customer_service.list_businesses("ALPINE")[0]["business_id"], 1)
        self.assertEqual(customer_service.list_businesses("missing"), [])

    def test_database_error_propagates_and_connection_closes(self):
        self.cursor.execute.side_effect = pymysql.OperationalError(2003, "unavailable")
        with self.assertRaises(pymysql.MySQLError):
            customer_service.list_businesses("tent")
        self.connection.close.assert_called_once()


class BusinessSearchPageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session.update(role="customer", customer_id=1, cart_id=1, csrf_token="token")
        count = patch.object(customer_service, "cart_count", return_value=0)
        count.start()
        self.addCleanup(count.stop)

    def test_search_results_link_to_matching_equipment(self):
        results = [
            {"business_id": 1, "business_name": "Alpine", "address": "First",
             "matching_equipment": ["Kayak"]},
            {"business_id": 2, "business_name": "Kayak Shop", "address": "Second",
             "matching_equipment": []},
        ]
        with patch.object(customer_service, "list_businesses", return_value=results) as search:
            response = self.client.get("/shop?q=+kayak+")
        self.assertEqual(response.status_code, 200)
        search.assert_called_once_with("kayak")
        self.assertIn(b'/shop/1?q=kayak', response.data)
        self.assertIn(b'/shop/2', response.data)
        self.assertIn(b"Matching equipment: Kayak", response.data)
        self.assertNotIn(b"/shop/2?q=", response.data)

    def test_no_results_and_escaped_query(self):
        with patch.object(customer_service, "list_businesses", return_value=[]):
            response = self.client.get("/shop", query_string={"q": '<tent>'})
        self.assertIn(b"No businesses match your search", response.data)
        self.assertIn(b"&lt;tent&gt;", response.data)

    def test_browse_filters_results_and_keeps_query_in_date_filter(self):
        items = [
            {"equipment_id": 1, "equipment_type": "Kayak", "description": "Boat", "rate": Decimal("10"),
             "rate_unit": "DAY", "image_url": "img/placeholder.svg", "availability": "free"},
            {"equipment_id": 2, "equipment_type": "Tent", "description": "Shelter", "rate": Decimal("10"),
             "rate_unit": "DAY", "image_url": "img/placeholder.svg", "availability": "free"},
        ]
        with patch.object(customer_service, "get_business", return_value={
            "business_id": 1, "business_name": "Alpine", "address": "First",
        }), patch.object(customer_service, "list_equipment", return_value=items):
            response = self.client.get("/shop/1?q=kayak")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<h2>Kayak</h2>", response.data)
        self.assertNotIn(b"<h2>Tent</h2>", response.data)
        self.assertIn(b'name="q" value="kayak"', response.data)
        self.assertIn(b"Show all equipment", response.data)

    def test_browse_combines_search_and_dates_and_clear_links(self):
        items = [{
            "equipment_id": 1, "equipment_type": "Kayak", "description": "Boat", "rate": Decimal("10"),
            "rate_unit": "DAY", "image_url": "img/placeholder.svg", "availability": "partial",
        }]
        with patch.object(customer_service, "get_business", return_value={
            "business_id": 1, "business_name": "Alpine", "address": "First",
        }), patch.object(customer_service, "list_equipment", return_value=items) as list_equipment:
            response = self.client.get("/shop/1", query_string={
                "q": "tent", "from": "2030-01-01 09:00", "to": "2030-01-02 09:00",
            })
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(list_equipment.call_args.args[1])
        self.assertIsNotNone(list_equipment.call_args.args[2])
        self.assertIn(b"No equipment matches your search that time range.", response.data)
        self.assertIn(b'href="/shop/1?q=tent">Clear dates', response.data)
        self.assertIn(b'from=2030-01-01+09:00&amp;to=2030-01-02+09:00">Show all equipment', response.data)


if __name__ == "__main__":
    unittest.main()
