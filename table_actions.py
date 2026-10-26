"""Placeholders for future record actions; no database operations are implemented."""

# Base-table allowlist, matching database/01_schema.sql; views are excluded.
# TODO: Reuse db_tools.connect() for MySQL when implementing these actions.
TABLE_PRIMARY_KEYS = {
    "business": ("business_id",),
    "rental_equipment": ("equipment_id",),
    "customer": ("customer_id",),
    "reservation": ("reservation_id",),
    "payment": ("payment_id",),
    "manager": ("manager_id",),
    "employee": ("employee_id",),
    "admin": ("admin_id",),
    "defines_access": ("admin_id", "employee_id"),
    "admin_privileges": ("admin_id", "privilege"),
}


def insert_record(table: str, values: dict) -> None:
    """Future insertion entry point; always raises until implemented."""
    # TODO: Validate allowlisted table/columns and values before parameterized SQL.
    # TODO: Add transaction commit/rollback and useful constraint/FK error handling.
    raise NotImplementedError("Record insertion is not implemented.")


def delete_record(table: str, key_values: dict) -> None:
    """Future deletion entry point; always raises until implemented."""
    # TODO: Require every primary-key field, including both composite-key fields.
    # TODO: Validate the table/key allowlists, parameterize values, and handle
    # transaction commit/rollback and foreign-key errors without cascading deletes.
    raise NotImplementedError("Record deletion is not implemented.")
