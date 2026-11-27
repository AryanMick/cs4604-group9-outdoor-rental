"""Record actions: insert, update, and delete for allowlisted base tables."""
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
    "cart": ("cart_id",),
    "cart_item": ("cart_item_id",),
    "auth_account": ("account_id",),
}


def _required_columns(cursor, table: str) -> set[str]:
    """Columns that are NOT NULL with no default and no AUTO_INCREMENT."""
    cursor.execute(
        "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND IS_NULLABLE = 'NO' "
        "AND COLUMN_DEFAULT IS NULL AND LOCATE('auto_increment', EXTRA) = 0",
        (table,),
    )
    return {row[0] for row in cursor.fetchall()}


def required_columns(table: str) -> set[str]:
    """Return the columns an inserted row must supply for an allowlisted table."""
    if table not in TABLE_PRIMARY_KEYS:
        raise ValueError(f"Unknown table: {table!r}")
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            return _required_columns(cursor, table)
    finally:
        connection.close()


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

            missing = sorted(_required_columns(cursor, table) - set(values))
            if missing:
                raise ValueError(f"Required field(s) missing for {table}: {', '.join(missing)}")

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


def update_record(table: str, key_values: dict, values: dict) -> None:
    """Update the columns in `values` on one row identified by its complete primary key.

    Primary-key columns cannot be changed. A value of None sets the column to NULL.
    Raises ValueError for bad input or constraint/FK violations.
    """
    if table not in TABLE_PRIMARY_KEYS:
        raise ValueError(f"Unknown table: {table!r}")
    primary_keys = TABLE_PRIMARY_KEYS[table]
    if any(not str(key_values.get(column, "")).strip() for column in primary_keys):
        raise ValueError(f"Primary-key value(s) required for {table}: {', '.join(primary_keys)}")
    changes = {column: value for column, value in values.items() if column not in primary_keys}
    if not changes:
        raise ValueError("No values were provided to update.")

    import pymysql

    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                (table,),
            )
            valid_columns = {row[0] for row in cursor.fetchall()}
            unknown = [column for column in changes if column not in valid_columns]
            if unknown:
                raise ValueError(f"Unknown column(s) for {table}: {', '.join(map(str, unknown))}")

            assignments = ", ".join(f"`{column}` = %s" for column in changes)
            conditions = " AND ".join(f"`{column}` = %s" for column in primary_keys)
            cursor.execute(
                f"UPDATE `{table}` SET {assignments} WHERE {conditions}",
                [*changes.values(), *(key_values[column] for column in primary_keys)],
            )
            if cursor.rowcount == 0:
                cursor.execute(
                    f"SELECT 1 FROM `{table}` WHERE {conditions}",
                    [key_values[column] for column in primary_keys],
                )
                if cursor.fetchone() is None:
                    raise ValueError("That record no longer exists.")
        connection.commit()
    except (pymysql.err.IntegrityError, pymysql.err.DataError, pymysql.err.OperationalError) as exc:
        connection.rollback()
        raise ValueError(f"Could not update {table}: {exc.args[-1]}") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def delete_record(table: str, key_values: dict) -> None:
    """Delete one row identified by its complete primary key.

    Raises ValueError for bad input or constraint/FK violations, and RuntimeError
    for database setup problems. Foreign-key restrictions prevent deleting a
    referenced row; related rows are never deleted automatically.
    """
    if table not in TABLE_PRIMARY_KEYS:
        raise ValueError(f"Unknown table: {table!r}")
    if not isinstance(key_values, dict) or not key_values:
        raise ValueError("Primary-key values must be provided as a non-empty dictionary.")

    primary_keys = TABLE_PRIMARY_KEYS[table]
    missing = [column for column in primary_keys if column not in key_values]
    extra = [column for column in key_values if column not in primary_keys]
    if missing:
        raise ValueError(f"Missing primary-key field(s) for {table}: {', '.join(missing)}")
    if extra:
        raise ValueError(f"Unexpected key field(s) for {table}: {', '.join(map(str, extra))}")
    if any(key_values[column] is None for column in primary_keys):
        raise ValueError("Primary-key values cannot be None.")

    import pymysql  # imported here so db_tools can report a missing package first

    connection = db_tools.connect()
    try:
        conditions = " AND ".join(f"`{column}` = %s" for column in primary_keys)
        parameters = [key_values[column] for column in primary_keys]
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM `{table}` WHERE {conditions}", parameters)
        connection.commit()
    except (pymysql.err.IntegrityError, pymysql.err.DataError, pymysql.err.OperationalError) as exc:
        connection.rollback()
        raise ValueError(f"Could not delete from {table}: {exc.args[-1]}") from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
