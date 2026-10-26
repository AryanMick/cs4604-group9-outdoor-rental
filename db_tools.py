"""Set up or inspect the Group 9 database on an existing MySQL server."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

PACKAGE = Path(__file__).resolve().parent
CONFIG_FILE = Path(os.environ.get("GROUP9_DB_CONFIG", PACKAGE / "db_config.json"))
TABLES = (
    "business",
    "rental_equipment",
    "customer",
    "reservation",
    "payment",
    "manager",
    "employee",
    "admin",
    "defines_access",
    "admin_privileges",
)
EXPECTED_COUNTS = {
    "business": 20,
    "rental_equipment": 40,
    "customer": 30,
    "reservation": 40,
    "payment": 30,
    "manager": 20,
    "employee": 20,
    "admin": 20,
    "defines_access": 40,
    "admin_privileges": 40,
}


def load_config() -> dict:
    """Read and validate the private connection settings."""
    if not CONFIG_FILE.is_file():
        raise RuntimeError(
            "Copy db_config.example.json to db_config.json and enter your MySQL credentials."
        )
    try:
        settings = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        config = {
            "host": str(settings["host"]),
            "port": int(settings["port"]),
            "database": str(settings["database"]),
            "user": str(settings["user"]),
            "password": str(settings["password"]),
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(
            "Check db_config.json. It must use the same fields as db_config.example.json."
        ) from exc
    if not re.fullmatch(r"[A-Za-z0-9_]+", config["database"]):
        raise RuntimeError("The database name may contain only letters, numbers, and underscores.")
    if not 1 <= config["port"] <= 65535:
        raise RuntimeError("The MySQL port must be between 1 and 65535.")
    return config


def connect(include_database: bool = True):
    """Open a PyMySQL connection using db_config.json."""
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError(
            "Install the Python packages: python -m pip install -r requirements.txt"
        ) from exc
    config = load_config()
    parameters = {
        "host": config["host"],
        "port": config["port"],
        "user": config["user"],
        "password": config["password"],
        "charset": "utf8mb4",
        "connect_timeout": 5,
        "autocommit": False,
    }
    if include_database:
        parameters["database"] = config["database"]
    return pymysql.connect(**parameters)


def parse_version(version_text: str) -> tuple[int, int, int]:
    """Return the numeric part of a MySQL version such as 8.4.3."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version_text)
    if not match:
        raise RuntimeError(f"Could not read the MySQL server version: {version_text}")
    return tuple(int(part) for part in match.groups())


def validate_server(connection) -> str:
    """Require a MySQL release that enforces CHECK constraints."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT VERSION(), @@version_comment")
        version, comment = cursor.fetchone()
    if "MariaDB" in version or "MariaDB" in comment:
        raise RuntimeError("This project requires MySQL 8.4, not MariaDB.")
    if parse_version(version) < (8, 0, 16):
        raise RuntimeError(
            "MySQL 8.0.16 or newer is required because older releases ignore CHECK constraints. "
            "MySQL 8.4 is recommended."
        )
    return version


def sql_statements(filename: str) -> list[str]:
    """Read the project's simple SQL files as individual statements."""
    text = (PACKAGE / "database" / filename).read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if not line.lstrip().startswith("--")]
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def setup() -> None:
    """Create and populate the configured database only when it is absent or empty."""
    config = load_config()
    database = config["database"]
    server = connect(include_database=False)
    try:
        version = validate_server(server)
        with server.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name=%s",
                (database,),
            )
            database_exists = cursor.fetchone()[0] == 1
            if not database_exists:
                cursor.execute(
                    f"CREATE DATABASE `{database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci"
                )
        server.commit()
    finally:
        server.close()

    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s",
                (database,),
            )
            object_count = cursor.fetchone()[0]
        if object_count:
            raise RuntimeError(
                f"Refusing setup: database '{database}' already contains {object_count} "
                "table or view object(s). No data was changed."
            )

        try:
            with connection.cursor() as cursor:
                for statement in sql_statements("01_schema.sql"):
                    cursor.execute(statement)
        except Exception as exc:
            connection.rollback()
            raise RuntimeError(
                "Schema setup failed. MySQL commits DDL statements automatically, so the database "
                "may now be partially created. No objects were deleted; inspect or choose a new "
                "empty database before trying again."
            ) from exc

        try:
            with connection.cursor() as cursor:
                for statement in sql_statements("02_sample_data.sql"):
                    cursor.execute(statement)
            connection.commit()
        except Exception as exc:
            connection.rollback()
            raise RuntimeError(
                "Sample-data loading failed and its transaction was rolled back. The schema remains "
                "because MySQL DDL cannot be wrapped in an atomic transaction. No objects were deleted."
            ) from exc
    finally:
        connection.close()

    print(f"Database created and 300 sample rows loaded with MySQL {version}.")
    status_report()


def status_report() -> dict:
    """Query the configured database and print live connection details and counts."""
    config = load_config()
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION(), DATABASE(), CURRENT_USER(), CONNECTION_ID()")
            version, database, user, connection_id = cursor.fetchone()
            counts = {}
            for table in TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                counts[table] = cursor.fetchone()[0]
    finally:
        connection.close()
    report = {
        "database": database,
        "user": user,
        "server": f"MySQL {version}",
        "connection_id": connection_id,
        "interface_language": "Python 3 / Flask",
        "driver": "PyMySQL",
        "host": config["host"],
        "port": config["port"],
        "table_counts": counts,
        "total_rows": sum(counts.values()),
    }
    print(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "status"), nargs="?", default="setup")
    args = parser.parse_args()
    if args.action == "setup":
        setup()
    else:
        status_report()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Database error: {exc}", file=sys.stderr)
        if exc.__cause__ is not None:
            print(f"Cause: {exc.__cause__}", file=sys.stderr)
        sys.exit(1)
