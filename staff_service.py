"""Database logic shared by employees and managers for their own business."""
from __future__ import annotations

from datetime import datetime

import pymysql

import customer_service
import db_tools
from customer_service import BookingError

RENTAL_LIMIT = 200


def list_rentals(business_id: int) -> list[dict]:
    """Every reservation for this business's equipment, newest first."""
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.reservation_id, CONCAT(c.first_name, ' ', c.last_name), e.equipment_type, "
                "r.status, r.checkout_date, r.due_date, r.payment_id, e.rate, e.rate_unit "
                "FROM reservation r "
                "JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
                "JOIN customer c ON c.customer_id = r.customer_id "
                "WHERE e.business_id = %s "
                "ORDER BY r.checkout_date DESC, r.reservation_id DESC LIMIT %s",
                (business_id, RENTAL_LIMIT),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()
    now = customer_service.current_time()
    return [
        {
            "reservation_id": r[0], "customer": r[1], "equipment_type": r[2], "status": r[3],
            "start_at": r[4], "end_at": r[5], "payment_id": r[6],
            "price": customer_service.calculate_price(r[7], r[8], r[4], r[5]),
            "overdue": r[3] == "RESERVED" and r[5] <= now,
        }
        for r in rows
    ]


def checkout_options(business_id: int) -> dict:
    """Customers and bookable equipment for the staff checkout form."""
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT customer_id, first_name, last_name FROM customer ORDER BY last_name, first_name, customer_id"
            )
            customers = [{"customer_id": r[0], "name": f"{r[1]} {r[2]}"} for r in cursor.fetchall()]
            cursor.execute(
                "SELECT equipment_id, equipment_type, rate, rate_unit FROM rental_equipment "
                "WHERE business_id = %s AND status = 'AVAILABLE' ORDER BY equipment_type, equipment_id",
                (business_id,),
            )
            equipment = [
                {"equipment_id": r[0], "equipment_type": r[1], "rate": r[2], "rate_unit": r[3]}
                for r in cursor.fetchall()
            ]
        return {"customers": customers, "equipment": equipment}
    finally:
        connection.close()


def checkout_customer(
    business_id: int, customer_id: str, equipment_id: str, start_text: str, end_text: str,
    card_number: str, expiry: str, security_code: str,
) -> dict:
    """Book one item for a customer at the counter: one payment and one reservation."""
    try:
        customer_key, equipment_key = int(customer_id), int(equipment_id)
    except (TypeError, ValueError) as exc:
        raise BookingError("Choose a customer and a piece of equipment.") from exc
    start = customer_service.parse_datetime(start_text.replace("T", " "))
    end = customer_service.parse_datetime(end_text.replace("T", " "))
    last4 = customer_service._parse_card_fields(card_number, expiry, security_code)

    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM customer WHERE customer_id = %s", (customer_key,))
            if cursor.fetchone() is None:
                raise BookingError("That customer was not found.")
            cursor.execute(
                "SELECT equipment_type, rate, rate_unit, business_id FROM rental_equipment "
                "WHERE equipment_id = %s",
                (equipment_key,),
            )
            item = cursor.fetchone()
            if item is None or item[3] != business_id:
                raise BookingError("That equipment does not belong to your business.")
            customer_service._check_item(
                cursor, equipment_key, start, end, customer_service.current_time(), lock=True,
            )
            price = customer_service.calculate_price(item[1], item[2], start, end)
            cursor.execute(
                "INSERT INTO payment (amount, payment_date, card_last4) VALUES (%s, %s, %s)",
                (price, datetime.now().replace(microsecond=0), last4),
            )
            payment_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO reservation (equipment_id, customer_id, payment_id, status, checkout_date, due_date) "
                "VALUES (%s, %s, %s, 'RESERVED', %s, %s)",
                (equipment_key, customer_key, payment_id, start, end),
            )
            reservation_id = cursor.lastrowid
        connection.commit()
        return {
            "reservation_id": reservation_id, "payment_id": payment_id,
            "equipment_type": item[0], "total": price,
        }
    except pymysql.MySQLError as exc:
        connection.rollback()
        raise BookingError(f"The reservation could not be completed: {exc.args[-1]}") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
