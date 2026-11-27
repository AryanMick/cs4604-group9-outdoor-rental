from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import manager_service
import reports
import rental_interface
import staff_service
from rental_interface import app

EMPTY_REPORT = {
    "totals": {"reservations": 0, "customers": 0, "revenue": 0, "average_rental": 0},
    "by_status": [], "by_equipment": [], "top_customers": [],
}


def _patch_staff_data():
    return (
        patch.object(staff_service, "list_rentals", return_value=[]),
        patch.object(reports, "business_report", return_value=EMPTY_REPORT),
        patch.object(staff_service, "checkout_options", return_value={"customers": [], "equipment": []}),
    )


class ManagerDashboardTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        for staff_patch in _patch_staff_data():
            staff_patch.start()
            self.addCleanup(staff_patch.stop)
        with self.client.session_transaction() as session:
            session.update(role="manager", role_id=7, business_id=3, csrf_token="manager-token")

    def test_manager_lands_on_business_tab_with_business_name(self):
        with patch.object(manager_service, "get_business_name", return_value="Summit Rentals"):
            response = self.client.get("/", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Summit Rentals Rentals", response.data)
        self.assertIn(b"Summit Rentals data", response.data)
        self.assertIn(b"Customer checkout", response.data)
        self.assertIn(b"Update equipment", response.data)
        self.assertIn(b'href="/manager?tab=rentals" aria-current="page"', response.data)
        self.assertNotIn(b"Equipment name", response.data)

    def test_manager_login_redirects_into_manager_workspace(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (101, "unused-hash", "MANAGER", None, None, 7, None, 3, None)
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        with patch.object(rental_interface.db_tools, "connect", return_value=connection):
            with patch.object(rental_interface, "check_password_hash", return_value=True):
                with patch.object(manager_service, "get_business_name", return_value="Summit Rentals"):
                    response = self.client.post(
                        "/login", data={"csrf_token": token, "email": "manager@example.com", "password": "secret"},
                        follow_redirects=True,
                    )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Summit Rentals data", response.data)
        with self.client.session_transaction() as session:
            self.assertEqual(session["role"], "manager")
            self.assertEqual(session["role_id"], 7)
            self.assertEqual(session["business_id"], 3)

    def test_manager_can_open_blank_rentals_tab(self):
        with patch.object(manager_service, "get_business_name", return_value="Summit Rentals"):
            response = self.client.get("/manager?tab=rentals")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Summit Rentals Rentals", response.data)
        self.assertNotIn(b"Equipment name", response.data)

    def test_new_manager_form_uses_manager_wording(self):
        response = self.client.get("/new_manager")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"New Manager", response.data)
        self.assertIn(b"Register a new manager account.", response.data)
        self.assertNotIn(b"Register a new employee account.", response.data)

    def test_equipment_tab_lists_business_inventory(self):
        equipment = [{
            "equipment_id": 9, "equipment_type": "Trail Bike", "description": "Hardtail",
            "rate": "25.00", "rate_unit": "HOUR", "image_url": "img/placeholder.svg", "status": "AVAILABLE",
        }]
        with patch.object(manager_service, "get_business_name", return_value="Summit Rentals"):
            with patch.object(manager_service, "list_equipment", return_value=equipment) as listing:
                response = self.client.get("/manager?tab=equipment")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Trail Bike", response.data)
        listing.assert_called_once_with(3)

    def test_customer_checkout_tab_stays_blank(self):
        with patch.object(manager_service, "get_business_name", return_value="Summit Rentals"):
            with patch.object(manager_service, "list_equipment") as listing:
                response = self.client.get("/manager?tab=checkout")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Customer checkout", response.data)
        self.assertNotIn(b"Equipment name", response.data)
        listing.assert_not_called()

    def test_equipment_routes_require_manager_and_csrf(self):
        with self.client.session_transaction() as session:
            session.clear()
        response = self.client.post("/manager/equipment/9/delete")
        self.assertEqual(response.status_code, 401)
        with self.client.session_transaction() as session:
            session.update(role="manager", business_id=3, csrf_token="right-token")
        response = self.client.post("/manager/equipment/9/delete", data={"csrf_token": "wrong-token"})
        self.assertEqual(response.status_code, 400)

    def test_add_route_passes_uploaded_jpg_and_session_business(self):
        upload = (BytesIO(b"\xff\xd8\xffmock-jpeg"), "gear.jpg")
        form = {
            "csrf_token": "manager-token", "equipment_type": "Trail Bike", "description": "Hardtail",
            "rate": "25.00", "rate_unit": "HOUR", "status": "AVAILABLE", "image": upload,
        }
        with patch.object(manager_service, "create_equipment") as create:
            response = self.client.post("/manager/equipment/add", data=form, content_type="multipart/form-data")
 
        self.assertEqual(create.call_args.args[0], 3)
        self.assertEqual(create.call_args.args[1:8], ("Trail Bike", "Hardtail", "25.00", "HOUR", "AVAILABLE", "gear.jpg", b"\xff\xd8\xffmock-jpeg"))


class EmployeeDashboardTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        for staff_patch in _patch_staff_data():
            staff_patch.start()
            self.addCleanup(staff_patch.stop)

    def test_employee_login_lands_on_business_rentals_tab(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (102, "unused-hash", "EMPLOYEE", None, 12, None, None, 3, 7)
        self.client.get("/login")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        with patch.object(rental_interface.db_tools, "connect", return_value=connection):
            with patch.object(rental_interface, "check_password_hash", return_value=True):
                with patch.object(manager_service, "get_business_name", return_value="Summit Rentals"):
                    response = self.client.post(
                        "/login", data={"csrf_token": token, "email": "employee@example.com", "password": "secret"},
                        follow_redirects=True,
                    )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Employee dashboard", response.data)
        self.assertIn(b"Summit Rentals Rentals", response.data)
        self.assertIn(b"Summit Rentals data", response.data)
        self.assertIn(b"Customer checkout", response.data)
        self.assertNotIn(b"Equipment name", response.data)
        self.assertIn(b'href="/employee?tab=rentals" aria-current="page"', response.data)
        with self.client.session_transaction() as session:
            self.assertEqual(session["role"], "employee")
            self.assertEqual(session["role_id"], 12)
            self.assertEqual(session["business_id"], 3)

    def test_employee_customer_checkout_tab_stays_blank(self):
        with self.client.session_transaction() as session:
            session.update(role="employee", role_id=12, business_id=3, csrf_token="employee-token")
        with patch.object(manager_service, "get_business_name", return_value="Summit Rentals"):
            response = self.client.get("/employee?tab=checkout")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Customer checkout", response.data)
        self.assertNotIn(b"Equipment name", response.data)

    def test_employee_business_data_tab_is_available_and_active(self):
        with self.client.session_transaction() as session:
            session.update(role="employee", role_id=12, business_id=3, csrf_token="employee-token")
        with patch.object(manager_service, "get_business_name", return_value="Summit Rentals"):
            response = self.client.get("/employee?tab=business")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Summit Rentals data", response.data)
        self.assertIn(b'href="/employee?tab=business" aria-current="page"', response.data)


class StaffAndAdminActionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_staff_checkout_requires_staff_and_csrf_then_uses_session_business(self):
        self.assertEqual(self.client.post("/staff/checkout").status_code, 401)
        with self.client.session_transaction() as session:
            session.update(role="employee", business_id=3, csrf_token="tok")
        self.assertEqual(self.client.post("/staff/checkout", data={"csrf_token": "bad"}).status_code, 400)
        form = {
            "csrf_token": "tok", "customer_id": "5", "equipment_id": "9", "start": "2030-01-01T10:00",
            "end": "2030-01-01T12:00", "card_number": "4111111111111111", "expiry": "2030-01", "security_code": "123",
        }
        result = {"equipment_type": "Kayak", "reservation_id": 1, "payment_id": 2, "total": "10.00"}
        with patch.object(staff_service, "checkout_customer", return_value=result) as checkout:
            response = self.client.post("/staff/checkout", data=form)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(checkout.call_args.args[:3], (3, "5", "9"))

    def test_admin_update_route_passes_key_and_nulls_blank_values(self):
        with self.client.session_transaction() as session:
            session.update(role="admin", csrf_token="tok")
        form = {"csrf_token": "tok", "key_customer_id": "4", "first_name": "Ada", "last_name": " "}
        with patch.object(rental_interface.table_actions, "update_record") as update:
            response = self.client.post("/table/customer/update", data=form)
        self.assertEqual(response.status_code, 302)
        update.assert_called_once_with("customer", {"customer_id": "4"}, {"first_name": "Ada", "last_name": None})
        with self.client.session_transaction() as session:
            session["role"] = "manager"
        self.assertEqual(self.client.post("/table/customer/update", data=form).status_code, 403)


class ManagerEquipmentServiceTests(unittest.TestCase):
    def test_create_saves_jpg_and_persists_equipment_id_filename(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.lastrowid = 77
        with tempfile.TemporaryDirectory() as temporary_directory:
            image_dir = Path(temporary_directory) / "img"
            with patch.object(manager_service.db_tools, "connect", return_value=connection):
                equipment_id = manager_service.create_equipment(
                    3, "Trail Bike", "Hardtail", "25", "HOUR", "AVAILABLE",
                    "bike.JPG", b"\xff\xd8\xfffake-jpg", image_dir,
                )
            self.assertEqual(equipment_id, 77)
            update_call = next(call for call in cursor.execute.call_args_list if call.args[0].startswith("UPDATE"))
            image_url = update_call.args[1][0]
            self.assertRegex(image_url, r"^img/equipment-77-[0-9a-f]{12}\.jpg$")
            self.assertEqual((image_dir / Path(image_url).name).read_bytes(), b"\xff\xd8\xfffake-jpg")
            connection.commit.assert_called_once()

    def test_rejects_non_jpeg_content_even_with_jpg_extension(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(manager_service.ManagerEquipmentError, "not a valid JPG"):
                manager_service.create_equipment(
                    3, "Trail Bike", "Hardtail", "25", "HOUR", "AVAILABLE",
                    "fake.jpg", b"not-an-image", Path(temporary_directory),
                )

    def test_retirement_is_blocked_by_reserved_rental(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [("img/placeholder.svg",), (1,)]
        with patch.object(manager_service.db_tools, "connect", return_value=connection):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with self.assertRaisesRegex(manager_service.ManagerEquipmentError, "active or scheduled rental"):
                    manager_service.retire_equipment(3, 9, Path(temporary_directory))
        connection.rollback.assert_called_once()
        self.assertFalse(any(call.args[0].startswith("UPDATE") for call in cursor.execute.call_args_list))

    def test_retirement_is_blocked_by_future_cart_item(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [("img/placeholder.svg",), (0,), (1,)]
        with patch.object(manager_service.db_tools, "connect", return_value=connection):
            with tempfile.TemporaryDirectory() as temporary_directory:
                with self.assertRaisesRegex(manager_service.ManagerEquipmentError, "customer's active or future cart"):
                    manager_service.retire_equipment(3, 9, Path(temporary_directory))
        connection.rollback.assert_called_once()
        self.assertFalse(any(call.args[0].startswith("UPDATE") for call in cursor.execute.call_args_list))

    def test_retirement_soft_hides_equipment_and_preserves_history(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [("img/placeholder.svg",), (0,), (0,)]
        with patch.object(manager_service.db_tools, "connect", return_value=connection):
            with tempfile.TemporaryDirectory() as temporary_directory:
                manager_service.retire_equipment(3, 9, Path(temporary_directory))
        connection.commit.assert_called_once()
        queries = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertTrue(any("SET status='RETIRED'" in query for query in queries))
        self.assertFalse(any(query.startswith("DELETE FROM rental_equipment") for query in queries))


if __name__ == "__main__":
    unittest.main()