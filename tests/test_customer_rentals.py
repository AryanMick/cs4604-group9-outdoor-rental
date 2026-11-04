"""Customer rentals and demo login tests, without touching the configured MySQL database."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import MagicMock, patch

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customer_service as cs
from rental_interface import app

NOW = datetime(2026, 11, 4, 12)
FUTURE = datetime(2026, 11, 5, 9)
END = datetime(2026, 11, 6, 9)


def rental(reservation_id=1, payment_id=10, status="RESERVED", start=FUTURE, end=END):
    return (
        reservation_id, payment_id, status, start, end, "Kayak", "A touring kayak.",
        "img/missing.jpg", "Outdoor Shop", Decimal("18.00"), "DAY", Decimal("36.00"),
    )


class RentalsServiceTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.connect = patch.object(cs.db_tools, "connect", return_value=self.connection)
        self.connect.start()
        self.addCleanup(self.connect.stop)
        self.clock = patch.object(cs, "current_time", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def get(self, rows):
        self.cursor.fetchall.return_value = rows
        return cs.get_customer_rentals(31)

    def test_empty_and_customer_scoped_query(self):
        self.assertEqual(self.get([]), {"pending": [], "active": [], "history": []})
        sql, parameters = self.cursor.execute.call_args.args
        self.assertIn("WHERE r.customer_id=%s", sql)
        self.assertEqual(parameters, (31,))
        self.connection.close.assert_called_once()

    def test_multiple_items_share_order_and_payment_not_unpaid_reservations(self):
        result = self.get([
            rental(), rental(2), rental(3, None), rental(4, None),
        ])
        self.assertEqual(len(result["pending"]), 3)
        self.assertEqual(len(result["pending"][0]["items"]), 2)
        self.assertEqual(result["pending"][0]["payment_total"], Decimal("36"))
        self.assertEqual(result["pending"][0]["items"][0]["price"], Decimal("18"))

    def test_status_and_time_boundaries_including_overdue(self):
        result = self.get([
            rental(1), rental(2, start=NOW),
            rental(3, start=datetime(2026, 11, 2), end=NOW),
            rental(4, status="RETURNED"), rental(5, status="CANCELLED"),
        ])
        self.assertEqual(len(result["pending"][0]["items"]), 1)
        self.assertEqual(len(result["active"][0]["items"]), 2)
        self.assertFalse(result["active"][0]["items"][0]["overdue"])
        self.assertTrue(result["active"][0]["items"][1]["overdue"])
        self.assertEqual(len(result["history"][0]["items"]), 2)

    def test_missing_joined_data_dates_and_payment(self):
        row = (1, None, "RESERVED", None, None, None, None, None, None, None, None, None)
        item = self.get([row])["active"][0]["items"][0]
        self.assertEqual(item["equipment_type"], "Equipment unavailable")
        self.assertEqual(item["business_name"], "Business unavailable")
        self.assertIsNone(item["price"])

    def test_database_failure_closes_connection_and_propagates(self):
        self.cursor.execute.side_effect = pymysql.OperationalError(2003, "Connection unavailable")
        with self.assertRaises(pymysql.MySQLError):
            cs.get_customer_rentals(31)
        self.connection.close.assert_called_once()

    def test_unexpected_status_is_not_silently_hidden(self):
        with self.assertRaisesRegex(RuntimeError, "unsupported"):
            self.get([rental(status="INVALID")])


class CustomerPageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.count = patch.object(cs, "cart_count", return_value=0)
        self.count.start()
        self.addCleanup(self.count.stop)

    def login_session(self, customer_id=31):
        with self.client.session_transaction() as session:
            session.update(role="customer", customer_id=customer_id, cart_id=1, csrf_token="token")

    def test_login_screen_is_explicitly_demo(self):
        response = self.client.get("/login/customer")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"not real authentication", response.data)
        self.assertIn(b"Continue as Demo Customer", response.data)
        self.assertNotIn(b"My Rentals</a>", response.data)

    def test_demo_login_requires_csrf_and_populates_session(self):
        with patch.object(cs, "start_customer_session", return_value=(31, 100)) as start:
            self.assertEqual(self.client.post("/login/customer").status_code, 400)
            self.client.get("/login/customer")
            with self.client.session_transaction() as session:
                token = session["csrf_token"]
            response = self.client.post("/login/customer", data={"csrf_token": token})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.location.endswith("/shop"))
            start.assert_called_once()
            with self.client.session_transaction() as session:
                self.assertEqual(session["customer_id"], 31)
                self.assertEqual(session["cart_id"], 100)

    def test_login_database_error_displays_notice(self):
        self.client.get("/login/customer")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        with patch.object(cs, "start_customer_session", side_effect=RuntimeError("Demo account missing")):
            with self.assertLogs(app.logger, level="ERROR"):
                response = self.client.post(
                    "/login/customer", data={"csrf_token": token}, follow_redirects=True,
                )
        self.assertIn(b"Demo account missing", response.data)

    def test_visitors_staff_and_incomplete_sessions_cannot_fetch_rentals(self):
        with patch.object(cs, "get_customer_rentals") as get:
            for role in (None, "staff", "customer"):
                with self.client.session_transaction() as session:
                    session.clear()
                    if role:
                        session["role"] = role
                response = self.client.get("/rentals")
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.location.endswith("/login/customer"))
            get.assert_not_called()

    def test_rentals_use_session_not_query_parameter_and_support_future_customers(self):
        self.login_session(42)
        with patch.object(cs, "get_customer_rentals", return_value={
            "pending": [], "active": [], "history": [],
        }) as get:
            response = self.client.get("/rentals?customer_id=31")
        get.assert_called_once_with(42)
        self.assertEqual(response.status_code, 200)
        for empty in (b"no reservations awaiting pickup", b"no active rentals", b"no returned or cancelled"):
            self.assertIn(empty, response.data)
        self.assertIn(b'aria-current="page"', response.data)

    def test_missing_data_renders_and_placeholder_is_served(self):
        self.login_session()
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [
            (1, None, "RESERVED", None, None, None, None, None, None, None, None, None),
        ]
        with patch.object(cs.db_tools, "connect", return_value=connection):
            response = self.client.get("/rentals")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Equipment unavailable", response.data)
        self.assertIn(b"No description available", response.data)
        self.assertIn(b"placeholder.svg", response.data)
        placeholder = self.client.get("/static/img/placeholder.svg")
        self.assertEqual(placeholder.status_code, 200)
        placeholder.close()

    def test_image_filter_uses_existing_image_and_rejects_outside_paths(self):
        with app.test_request_context():
            from customer_routes import rental_image
            self.assertEqual(rental_image("img/placeholder.svg"), "/static/img/placeholder.svg")
            self.assertEqual(rental_image("../README.md"), "/static/img/placeholder.svg")
            self.assertEqual(rental_image(None), "/static/img/placeholder.svg")

    def test_database_errors_return_503_not_empty_success(self):
        self.login_session()
        with patch.object(cs, "get_customer_rentals", side_effect=pymysql.OperationalError(2003, "Offline")):
            with self.assertLogs(app.logger, level="ERROR"):
                response = self.client.get("/rentals")
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"Something went wrong", response.data)


class SQLiteCursor:
    """Adapt placeholders and MySQL lock clauses for the in-memory integration test."""
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cursor.close()

    def execute(self, sql, parameters=()):
        sql = sql.replace("%s", "?").replace(" FOR UPDATE", "").replace(" FOR SHARE", "")
        return self.cursor.execute(sql, parameters)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    @property
    def lastrowid(self):
        return self.cursor.lastrowid


class SQLiteConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return SQLiteCursor(self.connection)

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        pass  # Keep the private in-memory database alive between service calls.


class CheckoutIntegrationTests(unittest.TestCase):
    def test_real_service_checkout_is_immediately_visible_and_customer_scoped(self):
        def parse_timestamp(value):
            return datetime.fromisoformat(value.decode())

        sqlite3.register_converter("DATETIME", parse_timestamp)
        database = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
        self.addCleanup(database.close)
        database.executescript("""
            CREATE TABLE business (business_id INTEGER PRIMARY KEY, business_name TEXT);
            CREATE TABLE rental_equipment (
                equipment_id INTEGER PRIMARY KEY, equipment_type TEXT, description TEXT,
                image_url TEXT, business_id INTEGER, rate INTEGER, rate_unit TEXT, status TEXT
            );
            CREATE TABLE cart (cart_id INTEGER PRIMARY KEY, customer_id INTEGER);
            CREATE TABLE cart_item (
                cart_item_id INTEGER PRIMARY KEY, cart_id INTEGER, equipment_id INTEGER,
                start_at DATETIME, end_at DATETIME
            );
            CREATE TABLE payment (
                payment_id INTEGER PRIMARY KEY, amount NUMERIC, payment_date DATETIME, card_last4 TEXT
            );
            CREATE TABLE reservation (
                reservation_id INTEGER PRIMARY KEY, equipment_id INTEGER, customer_id INTEGER,
                payment_id INTEGER, status TEXT, checkout_date DATETIME, due_date DATETIME
            );
            INSERT INTO business VALUES (1, 'Outdoor Shop');
            INSERT INTO rental_equipment VALUES (1, 'Kayak', 'Touring kayak', NULL, 1, 18, 'DAY', 'AVAILABLE');
            INSERT INTO rental_equipment VALUES (2, 'Tent', 'Two-person tent', NULL, 1, 12, 'DAY', 'AVAILABLE');
            INSERT INTO cart VALUES (1, 31);
            INSERT INTO cart_item VALUES (1, 1, 1, '2026-11-05 09:00', '2026-11-06 09:00');
            INSERT INTO cart_item VALUES (2, 1, 2, '2026-11-05 09:00', '2026-11-06 09:00');
            INSERT INTO reservation VALUES (1, 1, 42, NULL, 'RETURNED', '2026-10-01 09:00', '2026-10-02 09:00');
        """)
        # SQLite accepts neither Decimal parameters nor MySQL row locks.
        sqlite3.register_adapter(Decimal, str)
        with patch.object(cs.db_tools, "connect", return_value=SQLiteConnection(database)):
            with patch.object(cs, "current_time", return_value=NOW):
                order = cs.checkout(31, 1, "4242 4242", "2028-05", "123")
                sections = cs.get_customer_rentals(31)
                other_customer = cs.get_customer_rentals(42)
        self.assertEqual(order["total"], Decimal("30"))
        self.assertEqual(len(sections["pending"]), 1)
        saved = sections["pending"][0]
        self.assertEqual(saved["payment_id"], order["payment_id"])
        self.assertEqual({i["equipment_type"] for i in saved["items"]}, {"Kayak", "Tent"})
        self.assertEqual(saved["payment_total"], 30)
        self.assertEqual(sections["history"], [])
        self.assertEqual(len(other_customer["history"]), 1)
        self.assertEqual(database.execute("SELECT COUNT(*) FROM cart_item").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
