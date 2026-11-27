"""Aggregate (GROUP BY / SUM / COUNT / AVG) reports for each user type."""
from __future__ import annotations

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
