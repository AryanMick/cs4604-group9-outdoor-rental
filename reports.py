"""Aggregate (GROUP BY / SUM / COUNT / AVG) reports for each user type."""
from __future__ import annotations

from decimal import Decimal

import db_tools

# Rental price from the current rate; matches customer_service.calculate_price.
PRICE_SQL = (
    "CASE WHEN e.rate_unit = 'DAY' "
    "THEN e.rate * FLOOR(TIMESTAMPDIFF(MINUTE, r.checkout_date, r.due_date) / 1440) "
    "ELSE e.rate * TIMESTAMPDIFF(MINUTE, r.checkout_date, r.due_date) / 60 END"
)


def _query(sql: str, params: tuple = ()) -> list[dict]:
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            names = [column[0] for column in cursor.description]
            return [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        connection.close()


def business_report(business_id: int) -> dict:
    """Totals, per-status counts, per-equipment and per-customer figures for one business."""
    totals = _query(
        f"SELECT COUNT(*) AS reservations, COUNT(DISTINCT r.customer_id) AS customers, "
        f"COALESCE(SUM({PRICE_SQL}), 0) AS revenue, COALESCE(AVG({PRICE_SQL}), 0) AS average_rental "
        "FROM reservation r JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
        "WHERE e.business_id = %s AND r.status <> 'CANCELLED'",
        (business_id,),
    )[0]
    by_status = _query(
        "SELECT r.status, COUNT(*) AS reservations FROM reservation r "
        "JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
        "WHERE e.business_id = %s GROUP BY r.status ORDER BY r.status",
        (business_id,),
    )
    by_equipment = _query(
        f"SELECT e.equipment_type, COUNT(r.reservation_id) AS reservations, "
        f"COALESCE(SUM({PRICE_SQL}), 0) AS revenue, "
        "COALESCE(AVG(TIMESTAMPDIFF(MINUTE, r.checkout_date, r.due_date)) / 60, 0) AS average_hours "
        "FROM rental_equipment e "
        "LEFT JOIN reservation r ON r.equipment_id = e.equipment_id AND r.status <> 'CANCELLED' "
        "WHERE e.business_id = %s AND e.status <> 'RETIRED' "
        "GROUP BY e.equipment_type ORDER BY revenue DESC, e.equipment_type",
        (business_id,),
    )
    top_customers = _query(
        f"SELECT CONCAT(c.first_name, ' ', c.last_name) AS customer, COUNT(*) AS reservations, "
        f"SUM({PRICE_SQL}) AS spent "
        "FROM reservation r JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
        "JOIN customer c ON c.customer_id = r.customer_id "
        "WHERE e.business_id = %s AND r.status <> 'CANCELLED' "
        "GROUP BY c.customer_id, c.first_name, c.last_name ORDER BY spent DESC, customer LIMIT 5",
        (business_id,),
    )
    return {
        "totals": totals, "by_status": by_status,
        "by_equipment": by_equipment, "top_customers": top_customers,
    }


def admin_report() -> dict:
    """System-wide figures across every business."""
    totals = _query(
        "SELECT (SELECT COUNT(*) FROM business) AS businesses, "
        "(SELECT COUNT(*) FROM customer) AS customers, "
        "(SELECT COUNT(*) FROM reservation) AS reservations, "
        "COUNT(*) AS payments, COALESCE(SUM(amount), 0) AS revenue, "
        "COALESCE(AVG(amount), 0) AS average_payment, COALESCE(MAX(amount), 0) AS largest_payment "
        "FROM payment"
    )[0]
    by_business = _query(
        f"SELECT b.business_name, COUNT(DISTINCT e.equipment_id) AS equipment, "
        f"COUNT(r.reservation_id) AS reservations, COALESCE(SUM({PRICE_SQL}), 0) AS revenue "
        "FROM business b LEFT JOIN rental_equipment e ON e.business_id = b.business_id "
        "LEFT JOIN reservation r ON r.equipment_id = e.equipment_id AND r.status <> 'CANCELLED' "
        "GROUP BY b.business_id, b.business_name ORDER BY revenue DESC, b.business_name"
    )
    by_status = _query(
        "SELECT status, COUNT(*) AS reservations FROM reservation GROUP BY status ORDER BY status"
    )
    top_equipment = _query(
        "SELECT e.equipment_type, b.business_name, COUNT(*) AS reservations "
        "FROM reservation r JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
        "JOIN business b ON b.business_id = e.business_id "
        "WHERE r.status <> 'CANCELLED' "
        "GROUP BY e.equipment_id, e.equipment_type, b.business_name "
        "ORDER BY reservations DESC, e.equipment_type LIMIT 5"
    )
    staff = _query(
        "SELECT b.business_name, COUNT(DISTINCT m.manager_id) AS managers, "
        "COUNT(DISTINCT em.employee_id) AS employees "
        "FROM business b LEFT JOIN manager m ON m.business_id = b.business_id "
        "LEFT JOIN employee em ON em.manager_id = m.manager_id "
        "GROUP BY b.business_id, b.business_name ORDER BY b.business_name"
    )
    return {
        "totals": totals, "by_business": by_business, "by_status": by_status,
        "top_equipment": top_equipment, "staff": staff,
    }


def customer_report(customer_id: int) -> dict:
    """One customer's spending and rental habits."""
    totals = _query(
        "SELECT COUNT(DISTINCT p.payment_id) AS payments, COALESCE(SUM(p.amount), 0) AS total_spent, "
        "COALESCE(AVG(p.amount), 0) AS average_payment "
        "FROM payment p WHERE p.payment_id IN "
        "(SELECT payment_id FROM reservation WHERE customer_id = %s AND payment_id IS NOT NULL)",
        (customer_id,),
    )[0]
    totals["reservations"] = _query(
        "SELECT COUNT(*) AS n FROM reservation WHERE customer_id = %s", (customer_id,)
    )[0]["n"]
    by_business = _query(
        "SELECT b.business_name, COUNT(*) AS reservations FROM reservation r "
        "JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
        "JOIN business b ON b.business_id = e.business_id "
        "WHERE r.customer_id = %s AND r.status <> 'CANCELLED' "
        "GROUP BY b.business_id, b.business_name ORDER BY reservations DESC, b.business_name",
        (customer_id,),
    )
    favorites = _query(
        "SELECT e.equipment_type, COUNT(*) AS reservations FROM reservation r "
        "JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
        "WHERE r.customer_id = %s AND r.status <> 'CANCELLED' "
        "GROUP BY e.equipment_type ORDER BY reservations DESC, e.equipment_type LIMIT 3",
        (customer_id,),
    )
    return {"totals": totals, "by_business": by_business, "favorites": favorites}


# ---------------------------------------------------------------------------
# Report sets: each user type gets several labelled reports. Together they use
# COUNT, SUM, AVG, MIN and MAX. Each entry is (title, aggregates, SQL, parameter count).
# ---------------------------------------------------------------------------
_HOURS = "TIMESTAMPDIFF(MINUTE, r.checkout_date, r.due_date) / 60"
_RES = (
    "FROM reservation r JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
    "JOIN business b ON b.business_id = e.business_id "
)
MONEY_COLUMNS = {
    "total_paid", "average_payment", "smallest_payment", "largest_payment", "estimated_cost",
    "total_revenue", "average_rental", "smallest_rental", "largest_rental", "revenue", "spent",
    "min_rate", "max_rate", "average_rate", "total_payments", "average_revenue",
}

CUSTOMER_REPORTS = (
    ("My payment summary", "COUNT, SUM, AVG, MIN, MAX",
     "SELECT COUNT(*) AS payments, SUM(amount) AS total_paid, AVG(amount) AS average_payment, "
     "MIN(amount) AS smallest_payment, MAX(amount) AS largest_payment FROM payment "
     "WHERE payment_id IN (SELECT payment_id FROM reservation "
     "WHERE customer_id = %s AND payment_id IS NOT NULL)", 1),
    ("My rentals by status", "COUNT",
     "SELECT status, COUNT(*) AS rentals FROM reservation WHERE customer_id = %s "
     "GROUP BY status ORDER BY status", 1),
    ("Where I rent", "COUNT, SUM",
     f"SELECT b.business_name AS business, COUNT(*) AS rentals, SUM({PRICE_SQL}) AS estimated_cost "
     f"{_RES} WHERE r.customer_id = %s AND r.status <> 'CANCELLED' "
     "GROUP BY b.business_id, b.business_name ORDER BY rentals DESC, business", 1),
    ("My favourite equipment", "COUNT, SUM",
     f"SELECT e.equipment_type AS equipment, COUNT(*) AS rentals, SUM({_HOURS}) AS total_hours "
     f"{_RES} WHERE r.customer_id = %s AND r.status <> 'CANCELLED' "
     "GROUP BY e.equipment_type ORDER BY rentals DESC, equipment LIMIT 5", 1),
    ("My rental lengths (hours)", "COUNT, MIN, MAX, AVG",
     f"SELECT COUNT(*) AS rentals, MIN({_HOURS}) AS shortest_hours, MAX({_HOURS}) AS longest_hours, "
     f"AVG({_HOURS}) AS average_hours {_RES} WHERE r.customer_id = %s AND r.status <> 'CANCELLED'", 1),
)

BUSINESS_REPORTS = (
    ("Rental revenue summary", "COUNT, SUM, AVG, MIN, MAX",
     f"SELECT COUNT(*) AS rentals, SUM({PRICE_SQL}) AS total_revenue, AVG({PRICE_SQL}) AS average_rental, "
     f"MIN({PRICE_SQL}) AS smallest_rental, MAX({PRICE_SQL}) AS largest_rental "
     f"{_RES} WHERE e.business_id = %s AND r.status <> 'CANCELLED'", 1),
    ("Rentals by status", "COUNT",
     f"SELECT r.status, COUNT(*) AS rentals {_RES} WHERE e.business_id = %s "
     "GROUP BY r.status ORDER BY r.status", 1),
    ("Equipment performance", "COUNT, SUM, AVG",
     f"SELECT e.equipment_type AS equipment, COUNT(r.reservation_id) AS rentals, "
     f"COALESCE(SUM({PRICE_SQL}), 0) AS revenue, COALESCE(AVG({_HOURS}), 0) AS average_hours "
     "FROM rental_equipment e LEFT JOIN reservation r ON r.equipment_id = e.equipment_id "
     "AND r.status <> 'CANCELLED' WHERE e.business_id = %s AND e.status <> 'RETIRED' "
     "GROUP BY e.equipment_type ORDER BY revenue DESC, equipment", 1),
    ("Top customers", "COUNT, SUM",
     f"SELECT CONCAT(c.first_name, ' ', c.last_name) AS customer, COUNT(*) AS rentals, "
     f"SUM({PRICE_SQL}) AS spent {_RES} JOIN customer c ON c.customer_id = r.customer_id "
     "WHERE e.business_id = %s AND r.status <> 'CANCELLED' "
     "GROUP BY c.customer_id, c.first_name, c.last_name ORDER BY spent DESC, customer LIMIT 5", 1),
    ("Equipment rates by unit", "COUNT, MIN, MAX, AVG",
     "SELECT e.rate_unit AS rate_unit, COUNT(*) AS items, MIN(e.rate) AS min_rate, "
     "MAX(e.rate) AS max_rate, AVG(e.rate) AS average_rate FROM rental_equipment e "
     "WHERE e.business_id = %s AND e.status <> 'RETIRED' GROUP BY e.rate_unit", 1),
)

MANAGER_EXTRA_REPORTS = (
    ("Monthly revenue", "COUNT, SUM, AVG",
     f"SELECT DATE_FORMAT(r.checkout_date, '%%Y-%%m') AS month, COUNT(*) AS rentals, "
     f"SUM({PRICE_SQL}) AS revenue, AVG({PRICE_SQL}) AS average_revenue "
     f"{_RES} WHERE e.business_id = %s AND r.status <> 'CANCELLED' GROUP BY month ORDER BY month", 1),
    ("Employees per manager", "COUNT",
     "SELECT CONCAT(m.first_name, ' ', m.last_name) AS manager, COUNT(em.employee_id) AS employees "
     "FROM manager m LEFT JOIN employee em ON em.manager_id = m.manager_id "
     "WHERE m.business_id = %s GROUP BY m.manager_id, m.first_name, m.last_name ORDER BY manager", 1),
)

ADMIN_REPORTS = (
    ("System summary", "COUNT, SUM, AVG, MIN, MAX",
     "SELECT (SELECT COUNT(*) FROM business) AS businesses, (SELECT COUNT(*) FROM customer) AS customers, "
     "(SELECT COUNT(*) FROM reservation) AS reservations, COUNT(*) AS payments, "
     "SUM(amount) AS total_revenue, AVG(amount) AS average_payment, "
     "MIN(amount) AS smallest_payment, MAX(amount) AS largest_payment FROM payment", 0),
    ("Revenue by business", "COUNT, SUM, AVG",
     f"SELECT b.business_name AS business, COUNT(r.reservation_id) AS rentals, "
     f"COALESCE(SUM({PRICE_SQL}), 0) AS revenue, COALESCE(AVG({PRICE_SQL}), 0) AS average_rental "
     "FROM business b LEFT JOIN rental_equipment e ON e.business_id = b.business_id "
     "LEFT JOIN reservation r ON r.equipment_id = e.equipment_id AND r.status <> 'CANCELLED' "
     "GROUP BY b.business_id, b.business_name ORDER BY revenue DESC, business", 0),
    ("Rentals by status", "COUNT",
     "SELECT status, COUNT(*) AS rentals FROM reservation GROUP BY status ORDER BY status", 0),
    ("Most-rented equipment", "COUNT",
     f"SELECT e.equipment_type AS equipment, b.business_name AS business, COUNT(*) AS rentals "
     f"{_RES} WHERE r.status <> 'CANCELLED' GROUP BY e.equipment_id, e.equipment_type, b.business_name "
     "ORDER BY rentals DESC, equipment LIMIT 10", 0),
    ("Staff per business", "COUNT",
     "SELECT b.business_name AS business, COUNT(DISTINCT m.manager_id) AS managers, "
     "COUNT(DISTINCT em.employee_id) AS employees FROM business b "
     "LEFT JOIN manager m ON m.business_id = b.business_id "
     "LEFT JOIN employee em ON em.manager_id = m.manager_id "
     "GROUP BY b.business_id, b.business_name ORDER BY business", 0),
    ("Equipment rates by type", "COUNT, MIN, MAX, AVG",
     "SELECT equipment_type AS equipment, COUNT(*) AS items, MIN(rate) AS min_rate, "
     "MAX(rate) AS max_rate, AVG(rate) AS average_rate FROM rental_equipment "
     "WHERE status <> 'RETIRED' GROUP BY equipment_type ORDER BY equipment", 0),
    ("Payments by month", "COUNT, SUM, AVG",
     "SELECT DATE_FORMAT(payment_date, '%Y-%m') AS month, COUNT(*) AS payments, "
     "SUM(amount) AS total_payments, AVG(amount) AS average_payment FROM payment "
     "GROUP BY month ORDER BY month", 0),
    ("Top customers", "COUNT, SUM",
     f"SELECT CONCAT(c.first_name, ' ', c.last_name) AS customer, COUNT(*) AS rentals, "
     f"SUM({PRICE_SQL}) AS spent {_RES} JOIN customer c ON c.customer_id = r.customer_id "
     "WHERE r.status <> 'CANCELLED' GROUP BY c.customer_id, c.first_name, c.last_name "
     "ORDER BY spent DESC, customer LIMIT 10", 0),
)

REPORT_DEFINITIONS = {
    "customer": CUSTOMER_REPORTS,
    "employee": BUSINESS_REPORTS,
    "manager": BUSINESS_REPORTS + MANAGER_EXTRA_REPORTS,
    "admin": ADMIN_REPORTS,
}


def _cell(column: str, value) -> str:
    if value is None:
        return "—"
    if isinstance(value, (Decimal, float)):
        return f"${value:,.2f}" if column in MONEY_COLUMNS else f"{value:,.2f}"
    return str(value)


def report_set(kind: str, identifier: int | None = None) -> list[dict]:
    """Run every report for a user type ('customer', 'employee', 'manager', 'admin')."""
    sections = []
    for title, aggregates, sql, parameter_count in REPORT_DEFINITIONS[kind]:
        # Statements without parameters are not %-formatted by the driver.
        statement = sql.replace("%%", "%") if parameter_count == 0 else sql
        rows = _query(statement, (identifier,) * parameter_count if parameter_count else None)
        columns = list(rows[0]) if rows else []
        sections.append({
            "title": title,
            "aggregates": aggregates,
            "headers": [name.replace("_", " ").capitalize() for name in columns],
            "rows": [[_cell(name, row[name]) for name in columns] for row in rows],
        })
    return sections