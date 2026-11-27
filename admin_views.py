"""Name-based, operation-oriented admin screens (no raw IDs shown)."""
from __future__ import annotations

import reports

SCREENS = {
    "businesses": (
        "Rental businesses",
        "Every business with its manager, staff and equipment totals.",
        "SELECT b.business_name AS business, b.address, "
        "(SELECT GROUP_CONCAT(CONCAT(m.first_name, ' ', m.last_name) SEPARATOR ', ') "
        " FROM manager m WHERE m.business_id = b.business_id) AS managers, "
        "(SELECT COUNT(*) FROM employee em JOIN manager m ON m.manager_id = em.manager_id "
        " WHERE m.business_id = b.business_id) AS employees, "
        "(SELECT COUNT(*) FROM rental_equipment e WHERE e.business_id = b.business_id) AS equipment "
        "FROM business b ORDER BY b.business_name",
    ),
    "customers": (
        "Customers",
        "Customer accounts with their rental counts.",
        "SELECT CONCAT(c.first_name, ' ', c.last_name) AS customer, a.email, "
        "COUNT(r.reservation_id) AS reservations "
        "FROM customer c LEFT JOIN auth_account a ON a.customer_id = c.customer_id "
        "LEFT JOIN reservation r ON r.customer_id = c.customer_id "
        "GROUP BY c.customer_id, c.first_name, c.last_name, a.email ORDER BY c.last_name, c.first_name",
    ),
    "staff": (
        "Managers and employees",
        "Who works where.",
        "SELECT CONCAT(m.first_name, ' ', m.last_name) AS person, 'Manager' AS role, "
        "b.business_name AS business FROM manager m JOIN business b ON b.business_id = m.business_id "
        "UNION ALL SELECT CONCAT(em.first_name, ' ', em.last_name), 'Employee', b.business_name "
        "FROM employee em JOIN manager m ON m.manager_id = em.manager_id "
        "JOIN business b ON b.business_id = m.business_id ORDER BY business, role, person",
    ),
    "admins": (
        "Administrators",
        "Admin users and their email addresses.",
        "SELECT CONCAT(ad.first_name, ' ', ad.last_name) AS administrator, a.email "
        "FROM admin ad LEFT JOIN auth_account a ON a.admin_id = ad.admin_id "
        "ORDER BY ad.last_name, ad.first_name",
    ),
    "equipment": (
        "Equipment",
        "All equipment with its business and current rate.",
        "SELECT e.equipment_type AS equipment, b.business_name AS business, e.rate, "
        "e.rate_unit AS per, e.status FROM rental_equipment e "
        "JOIN business b ON b.business_id = e.business_id ORDER BY b.business_name, e.equipment_type",
    ),
    "reservations": (
        "Reservations",
        "All reservations by customer, business and equipment (latest first).",
        "SELECT CONCAT(c.first_name, ' ', c.last_name) AS customer, b.business_name AS business, "
        "e.equipment_type AS equipment, r.checkout_date AS start, r.due_date AS end, r.status "
        "FROM reservation r JOIN customer c ON c.customer_id = r.customer_id "
        "JOIN rental_equipment e ON e.equipment_id = r.equipment_id "
        "JOIN business b ON b.business_id = e.business_id ORDER BY r.checkout_date DESC LIMIT 300",
    ),
    "payments": (
        "Payments",
        "Payments with the customer who paid (latest first).",
        "SELECT CONCAT(c.first_name, ' ', c.last_name) AS customer, p.amount, "
        "p.payment_date AS paid_on, CONCAT('**** ', p.card_last4) AS card "
        "FROM payment p JOIN reservation r ON r.payment_id = p.payment_id "
        "JOIN customer c ON c.customer_id = r.customer_id "
        "GROUP BY p.payment_id, c.customer_id, c.first_name, c.last_name, p.amount, p.payment_date, p.card_last4 "
        "ORDER BY p.payment_date DESC LIMIT 300",
    ),
}


def run_screen(key: str) -> dict:
    title, description, sql = SCREENS[key]
    rows = reports._query(sql)
    columns = list(rows[0]) if rows else []
    return {
        "key": key,
        "title": title,
        "description": description,
        "headers": [name.replace("_", " ").capitalize() for name in columns],
        "rows": [[reports._cell(name, row[name]) if name in reports.MONEY_COLUMNS or name == "amount"
                  or name == "rate" else ("—" if row[name] is None else str(row[name]))
                  for name in columns] for row in rows],
    }
