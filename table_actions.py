"""Record actions: insert_record is implemented; delete_record is still a shell."""
from __future__ import annotations

import db_tools

# Base-table allowlist, matching database/01_schema.sql; views are excluded.
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


def insert_record(table: str, values: dict) -> int:
    """Insert one row into an allowlisted table and return the new AUTO_INCREMENT id (0 if none).

    Raises ValueError for bad input or constraint/FK violations, RuntimeError for setup problems.
    """
    # Table names cannot be parameterized, so only allowlisted names reach the SQL string.
    if table not in TABLE_PRIMARY_KEYS:
        raise ValueError(f"Unknown table: {table!r}")
    if not values:
        raise ValueError("No values were provided to insert.")

    import pymysql  # imported here so db_tools can report a missing package first

    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            # Column names also cannot be parameterized; check them against the real schema.
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                (table,),
            )
            valid_columns = {row[0] for row in cursor.fetchall()}
            unknown = [column for column in values if column not in valid_columns]
            if unknown:
                raise ValueError(f"Unknown column(s) for {table}: {', '.join(map(str, unknown))}")

            columns = list(values)
            column_sql = ", ".join(f"`{column}`" for column in columns)
            placeholders = ", ".join(["%s"] * len(columns))
            # Values are bound by the driver, which prevents SQL injection.
            cursor.execute(
                f"INSERT INTO `{table}` ({column_sql}) VALUES ({placeholders})",
                [values[column] for column in columns],
            )
            new_id = cursor.lastrowid or 0
        connection.commit()
        return new_id
    except (pymysql.err.IntegrityError, pymysql.err.DataError, pymysql.err.OperationalError) as exc:
        # Duplicate keys, FK/CHECK failures, bad data types, and similar rejections.
        connection.rollback()
        raise ValueError(f"Could not insert into {table}: {exc.args[-1]}") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_record(table: str, key_values: dict) -> None:
    """Future deletion entry point; always raises until implemented."""
    # TODO: Require every primary-key field, including both composite-key fields.
    # TODO: Validate the table/key allowlists, parameterize values, and handle
    # transaction commit/rollback and foreign-key errors without cascading deletes.
    raise NotImplementedError("Record deletion is not implemented.")
