"""Database logic for the customer shopping flow: browsing, cart, and checkout."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import re

import pymysql

import db_tools

DATETIME_FORMAT = "%Y-%m-%d %H:%M"
MINUTES_PER_DAY = 24 * 60


class BookingError(ValueError):
    """A problem the customer can fix, such as an unavailable time or bad card field."""


def current_time() -> datetime:
    return datetime.now().replace(second=0, microsecond=0)


def parse_datetime(text: str) -> datetime:
    try:
        return datetime.strptime(str(text).strip(), DATETIME_FORMAT)
    except ValueError as exc:
        raise BookingError("Enter a valid date and time.") from exc


def calculate_price(rate: Decimal, rate_unit: str, start: datetime, end: datetime) -> Decimal:
    """Hourly items are prorated by the half hour; day items are whole 24-hour days."""
    minutes = int((end - start).total_seconds() // 60)
    if rate_unit == "DAY":
        amount = Decimal(rate) * (minutes // MINUTES_PER_DAY)
    else:
        amount = Decimal(rate) * minutes / 60
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def describe_duration(rate_unit: str, start: datetime, end: datetime) -> str:
    minutes = int((end - start).total_seconds() // 60)
    if rate_unit == "DAY":
        days = minutes // MINUTES_PER_DAY
        return f"{days} day" + ("" if days == 1 else "s")
    hours = Decimal(minutes) / 60
    text = f"{hours:.1f}".rstrip("0").rstrip(".")
    return f"{text} hour" + ("" if hours == 1 else "s")


def validate_window(rate_unit: str, equipment_status: str, start: datetime, end: datetime, now: datetime) -> None:
    """Check the booking rules that do not need other reservations."""
    if equipment_status == "MAINTENANCE":
        raise BookingError("This equipment is under maintenance and cannot be reserved.")
    if equipment_status != "AVAILABLE":
        raise BookingError("This equipment is not available.")
    for moment in (start, end):
        if moment.minute not in (0, 30) or moment.second != 0:
            raise BookingError("Times must be on the hour or half hour.")
    if start < now:
        raise BookingError("The start time has already passed.")
    if end <= start:
        raise BookingError("The end must be after the start.")
    if rate_unit == "DAY" and int((end - start).total_seconds() // 60) % MINUTES_PER_DAY != 0:
        raise BookingError("Day-rate equipment must be rented in whole 24-hour days.")


def coverage(blocked: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> str:
    """Return 'free', 'partial', or 'blocked' for [start, end) against blocked intervals."""
    clipped = sorted((max(s, start), min(e, end)) for s, e in blocked if s < end and e > start)
    if not clipped:
        return "free"
    covered = timedelta()
    run_start, run_end = clipped[0]
    for s, e in clipped[1:]:
        if s <= run_end:
            run_end = max(run_end, e)
        else:
            covered += run_end - run_start
            run_start, run_end = s, e
    covered += run_end - run_start
    return "blocked" if covered >= end - start else "partial"


def _cart_for_customer(cursor, cart_id: int, customer_id: int) -> None:
    cursor.execute("SELECT 1 FROM cart WHERE cart_id=%s AND customer_id=%s", (cart_id, customer_id))
    if cursor.fetchone() is None:
        raise BookingError("Your cart was not found. Log out and log in again.")


def _check_item(cursor, equipment_id: int, start: datetime, end: datetime, now: datetime, lock: bool = False) -> None:
    """Raise BookingError if the equipment cannot be reserved for the range."""
    cursor.execute(
        "SELECT status, rate_unit FROM rental_equipment WHERE equipment_id=%s" + (" FOR UPDATE" if lock else ""),
        (equipment_id,),
    )
    row = cursor.fetchone()
    if row is None:
        raise BookingError("This equipment no longer exists.")
    validate_window(row[1], row[0], start, end, now)
    cursor.execute(
        "SELECT COUNT(*) FROM reservation WHERE equipment_id=%s AND status='RESERVED' "
        "AND checkout_date < %s AND due_date > %s" + (" FOR SHARE" if lock else ""),
        (equipment_id, end, start),
    )
    if cursor.fetchone()[0]:
        raise BookingError("That time overlaps an existing reservation.")


def start_customer_session(customer_id: int) -> int:
    """Create a fresh cart for the authenticated customer and return its ID."""
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT customer_id FROM customer WHERE customer_id=%s FOR UPDATE",
                (customer_id,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("The customer linked to this account was not found.")
            _delete_cart(cursor, customer_id)
            cursor.execute("INSERT INTO cart (customer_id) VALUES (%s)", (customer_id,))
            cart_id = cursor.lastrowid
        connection.commit()
        return cart_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _delete_cart(cursor, customer_id: int) -> None:
    cursor.execute(
        "DELETE FROM cart_item WHERE cart_id IN (SELECT cart_id FROM cart WHERE customer_id=%s)",
        (customer_id,),
    )
    cursor.execute("DELETE FROM cart WHERE customer_id=%s", (customer_id,))


def end_customer_session(customer_id: int) -> None:
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            _delete_cart(cursor, customer_id)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def equipment_matches(item: dict, query: str) -> bool:
    """Match equipment by type or description, ignoring case."""
    term = query.strip().casefold()
    return term in item["equipment_type"].casefold() or term in item["description"].casefold()


def list_businesses(query: str = "") -> list[dict]:
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT b.business_id, b.business_name, b.address, e.equipment_type, e.description "
                "FROM business b LEFT JOIN rental_equipment e "
                "ON e.business_id=b.business_id AND e.status <> 'RETIRED' "
                "ORDER BY b.business_name, b.business_id, e.equipment_type"
            )
            businesses = {}
            term = query.strip().casefold()
            for business_id, name, address, equipment_type, description in cursor.fetchall():
                business = businesses.setdefault(business_id, {
                    "business_id": business_id, "business_name": name, "address": address,
                    "matching_equipment": [],
                })
                if term and equipment_type and equipment_matches(
                    {"equipment_type": equipment_type, "description": description}, term
                ) and equipment_type not in business["matching_equipment"]:
                    business["matching_equipment"].append(equipment_type)
            return [
                business for business in businesses.values()
                if not term or term in business["business_name"].casefold() or business["matching_equipment"]
            ]
    finally:
        connection.close()


def get_business(business_id: int) -> dict | None:
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT business_id, business_name, address FROM business WHERE business_id=%s", (business_id,))
            row = cursor.fetchone()
            return {"business_id": row[0], "business_name": row[1], "address": row[2]} if row else None
    finally:
        connection.close()


def get_customer_rentals(customer_id: int) -> dict[str, list[dict]]:
    """Group this customer's reservations by time section and shared payment."""
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.reservation_id, r.payment_id, r.status, r.checkout_date, r.due_date, "
                "e.equipment_type, e.description, e.image_url, b.business_name, "
                "e.rate, e.rate_unit, p.amount "
                "FROM reservation r "
                "LEFT JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
                "LEFT JOIN business b ON b.business_id = e.business_id "
                "LEFT JOIN payment p ON p.payment_id = r.payment_id "
                "WHERE r.customer_id=%s ORDER BY r.checkout_date DESC, r.reservation_id",
                (customer_id,),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    now = current_time()
    sections: dict[str, dict[tuple[str, int], dict]] = {
        "pending": {}, "active": {}, "history": {},
    }
    for row in rows:
        reservation_id, payment_id, status, start, end = row[:5]
        if status in ("RETURNED", "CANCELLED"):
            section = "history"
        elif status == "RESERVED" and start is not None and start > now:
            section = "pending"
        elif status == "RESERVED":
            # A passed due date does not prove that the equipment was returned.
            section = "active"
        else:
            raise RuntimeError("A rental has an unsupported reservation status.")
        key = ("payment", payment_id) if payment_id is not None else ("reservation", reservation_id)
        orders = sections[section]
        if key not in orders:
            orders[key] = {
                "payment_id": payment_id, "reservation_id": reservation_id,
                "payment_total": row[11], "items": [],
            }
        price = None
        if row[9] is not None and row[10] in ("DAY", "HOUR") and start is not None and end is not None and end > start:
            price = calculate_price(row[9], row[10], start, end)
        orders[key]["items"].append({
            "reservation_id": reservation_id, "status": status, "start_at": start, "end_at": end,
            "equipment_type": row[5] or "Equipment unavailable",
            "description": row[6] or "No description available.",
            "image_url": row[7], "business_name": row[8] or "Business unavailable",
            "price": price,
            "overdue": status == "RESERVED" and end is not None and end <= now,
        })
    return {name: list(orders.values()) for name, orders in sections.items()}


def list_equipment(business_id: int, filter_start: datetime | None = None, filter_end: datetime | None = None) -> list[dict]:
    """List a business's non-retired equipment, optionally limited to a time range.

    With a range, items that are blocked for all of it (including maintenance and past
    time) are dropped and partly blocked items are flagged 'partial'.
    """
    now = current_time()
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT equipment_id, equipment_type, description, rate, rate_unit, image_url, status "
                "FROM rental_equipment WHERE business_id=%s AND status <> 'RETIRED' "
                "ORDER BY equipment_type, equipment_id",
                (business_id,),
            )
            items = [
                {
                    "equipment_id": r[0], "equipment_type": r[1], "description": r[2], "rate": r[3],
                    "rate_unit": r[4], "image_url": r[5], "status": r[6],
                }
                for r in cursor.fetchall()
            ]
            blocked: dict[int, list[tuple[datetime, datetime]]] = {}
            if items and filter_start is not None:
                marks = ", ".join(["%s"] * len(items))
                cursor.execute(
                    f"SELECT equipment_id, checkout_date, due_date FROM reservation "
                    f"WHERE status='RESERVED' AND due_date > %s AND equipment_id IN ({marks})",
                    [now, *[item["equipment_id"] for item in items]],
                )
                for equipment_id, start, end in cursor.fetchall():
                    blocked.setdefault(equipment_id, []).append((start, end))
    finally:
        connection.close()

    result = []
    for item in items:
        if item["status"] == "MAINTENANCE":
            if filter_start is not None:
                continue
            item["availability"] = "maintenance"
        elif filter_start is None:
            item["availability"] = "free"
        else:
            intervals = [(datetime.min, now), *blocked.get(item["equipment_id"], [])]
            state = coverage(intervals, filter_start, filter_end)
            if state == "blocked":
                continue
            item["availability"] = state
        result.append(item)
    return result


def get_equipment_availability(equipment_id: int, cart_id: int | None = None) -> dict | None:
    """Return the data the booking calendar needs, or None for unknown or retired equipment."""
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT equipment_type, rate, rate_unit, status FROM rental_equipment WHERE equipment_id=%s",
                (equipment_id,),
            )
            row = cursor.fetchone()
            if row is None or row[3] == "RETIRED":
                return None
            now = current_time()
            cursor.execute(
                "SELECT checkout_date, due_date FROM reservation "
                "WHERE equipment_id=%s AND status='RESERVED' AND due_date > %s ORDER BY checkout_date",
                (equipment_id, now),
            )
            blocked = [[s.strftime(DATETIME_FORMAT), e.strftime(DATETIME_FORMAT)] for s, e in cursor.fetchall()]
            in_cart = False
            if cart_id is not None:
                cursor.execute(
                    "SELECT 1 FROM cart_item WHERE cart_id=%s AND equipment_id=%s", (cart_id, equipment_id)
                )
                in_cart = cursor.fetchone() is not None
    finally:
        connection.close()
    bookable = row[3] == "AVAILABLE"
    return {
        "equipment_type": row[0],
        "rate": str(row[1]),
        "rate_unit": row[2],
        "bookable": bookable,
        "reason": None if bookable else "This equipment is under maintenance and cannot be reserved.",
        "in_cart": in_cart,
        "now": now.strftime(DATETIME_FORMAT),
        "blocked": blocked,
    }


def add_to_cart(cart_id: int, customer_id: int, equipment_id: int, start_text: str, end_text: str) -> int:
    """Validate the request and add it to the cart; return the new cart size."""
    start, end = parse_datetime(start_text), parse_datetime(end_text)
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            _cart_for_customer(cursor, cart_id, customer_id)
            cursor.execute(
                "SELECT 1 FROM cart_item WHERE cart_id=%s AND equipment_id=%s", (cart_id, equipment_id)
            )
            if cursor.fetchone():
                raise BookingError("This equipment is already in your cart.")
            _check_item(cursor, equipment_id, start, end, current_time())
            cursor.execute(
                "INSERT INTO cart_item (cart_id, equipment_id, start_at, end_at) VALUES (%s, %s, %s, %s)",
                (cart_id, equipment_id, start, end),
            )
            cursor.execute("SELECT COUNT(*) FROM cart_item WHERE cart_id=%s", (cart_id,))
            count = cursor.fetchone()[0]
        connection.commit()
        return count
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def cart_count(cart_id: int) -> int:
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM cart_item WHERE cart_id=%s", (cart_id,))
            return cursor.fetchone()[0]
    finally:
        connection.close()


def get_cart(cart_id: int, customer_id: int) -> dict:
    """Return cart items with prices, plus a problem message for any item that is no longer bookable."""
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            _cart_for_customer(cursor, cart_id, customer_id)
            cursor.execute(
                "SELECT ci.cart_item_id, ci.equipment_id, e.equipment_type, e.description, e.image_url, "
                "b.business_name, e.rate, e.rate_unit, ci.start_at, ci.end_at "
                "FROM cart_item ci JOIN rental_equipment e ON e.equipment_id = ci.equipment_id "
                "JOIN business b ON b.business_id = e.business_id "
                "WHERE ci.cart_id=%s ORDER BY ci.cart_item_id",
                (cart_id,),
            )
            rows = cursor.fetchall()
            now = current_time()
            items = []
            total = Decimal("0.00")
            for r in rows:
                problem = None
                try:
                    _check_item(cursor, r[1], r[8], r[9], now)
                except BookingError as exc:
                    problem = str(exc)
                price = calculate_price(r[6], r[7], r[8], r[9])
                total += price
                items.append(
                    {
                        "cart_item_id": r[0], "equipment_id": r[1], "equipment_type": r[2],
                        "description": r[3], "image_url": r[4], "business_name": r[5],
                        "rate": r[6], "rate_unit": r[7], "start_at": r[8], "end_at": r[9],
                        "price": price, "duration": describe_duration(r[7], r[8], r[9]), "problem": problem,
                    }
                )
        return {"items": items, "total": total, "has_problem": any(i["problem"] for i in items)}
    finally:
        connection.close()


def remove_cart_item(cart_id: int, cart_item_id: int) -> None:
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM cart_item WHERE cart_item_id=%s AND cart_id=%s", (cart_item_id, cart_id))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _parse_card_fields(card_number: str, expiry: str, security_code: str) -> str:
    """Check only that the fields are a number and a date; return the last four card digits."""
    digits = re.sub(r"[\s-]", "", card_number or "")
    if not digits.isdigit() or len(digits) < 4:
        raise BookingError("Enter the card number using digits only (at least 4).")
    expiry = (expiry or "").strip()
    for pattern in ("%Y-%m", "%m/%y"):
        try:
            datetime.strptime(expiry, pattern)
            break
        except ValueError:
            continue
    else:
        raise BookingError("Enter the expiration date as a month and year.")
    if not (security_code or "").strip().isdigit():
        raise BookingError("Enter the security code using digits only.")
    return digits[-4:]


def checkout(customer_id: int, cart_id: int, card_number: str, expiry: str, security_code: str) -> dict:
    """Pay for the whole cart: one payment, one reservation per item, then empty the cart.

    Only the last four card digits are stored; the rest of the card fields are discarded.
    """
    last4 = _parse_card_fields(card_number, expiry, security_code)
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            _cart_for_customer(cursor, cart_id, customer_id)
            cursor.execute(
                "SELECT ci.cart_item_id, ci.equipment_id, e.equipment_type, e.rate, e.rate_unit, ci.start_at, ci.end_at "
                "FROM cart_item ci JOIN rental_equipment e ON e.equipment_id = ci.equipment_id "
                "WHERE ci.cart_id=%s ORDER BY ci.cart_item_id",
                (cart_id,),
            )
            rows = cursor.fetchall()
            if not rows:
                raise BookingError("Your cart is empty.")
            now = current_time()
            items = []
            total = Decimal("0.00")
            for r in rows:
                try:
                    _check_item(cursor, r[1], r[5], r[6], now, lock=True)
                except BookingError as exc:
                    raise BookingError(f"{r[2]}: {exc}") from exc
                price = calculate_price(r[3], r[4], r[5], r[6])
                total += price
                items.append({"equipment_id": r[1], "equipment_type": r[2], "start_at": r[5], "end_at": r[6], "price": price})

            cursor.execute(
                "INSERT INTO payment (amount, payment_date, card_last4) VALUES (%s, %s, %s)",
                (total, datetime.now().replace(microsecond=0), last4),
            )
            payment_id = cursor.lastrowid
            for item in items:
                cursor.execute(
                    "INSERT INTO reservation (equipment_id, customer_id, payment_id, status, checkout_date, due_date) "
                    "VALUES (%s, %s, %s, 'RESERVED', %s, %s)",
                    (item["equipment_id"], customer_id, payment_id, item["start_at"], item["end_at"]),
                )
                item["reservation_id"] = cursor.lastrowid
            cursor.execute("DELETE FROM cart_item WHERE cart_id=%s", (cart_id,))
        connection.commit()
        return {"payment_id": payment_id, "total": total, "last4": last4, "items": items}
    except pymysql.MySQLError as exc:
        connection.rollback()
        raise BookingError(f"The reservation could not be completed: {exc.args[-1]}") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
