"""Load the Group 9 project using the PostgreSQL connection in db_config.json.

Without a config file, use a dedicated local instance on Unix systems.
Its runtime data lives in ../work/group9_runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PACKAGE = Path(__file__).resolve().parent
CONFIG_FILE = Path(os.environ.get("GROUP9_DB_CONFIG", PACKAGE / "db_config.json"))
RUNTIME = Path(os.environ.get("GROUP9_RUNTIME_DIR", PACKAGE.parent / "work" / "group9_runtime"))
DATA = RUNTIME / "postgres_data"
PORT = 55439
DATABASE = "outdoor_rental_group9"
USER = "group9"
# Each runtime directory gets its own short socket name.
SOCKET = Path(tempfile.gettempdir()) / ("cs4604-" + hashlib.sha256(str(RUNTIME).encode()).hexdigest()[:10])
TABLES = ("business", "rental_equipment", "customer", "reservation", "payment",
          "manager", "employee", "admin", "defines_access", "admin_privileges")


def pg_bin() -> Path:
    candidates = [os.environ.get("GROUP9_PG_BIN"), "/opt/homebrew/opt/postgresql@15/bin",
                  "/opt/homebrew/opt/postgresql@16/bin", "/opt/homebrew/opt/postgresql@17/bin",
                  "/opt/homebrew/opt/postgresql@18/bin", "/usr/local/opt/postgresql@15/bin"]
    found = shutil.which("pg_ctl")
    if found:
        candidates.insert(1, str(Path(found).parent))
    for candidate in candidates:
        if candidate and (Path(candidate) / "initdb").is_file():
            return Path(candidate)
    raise RuntimeError("PostgreSQL server tools are missing. Install PostgreSQL and set GROUP9_PG_BIN to its bin folder.")


def run_pg(name: str, *args: str, **kwargs):
    return subprocess.run([str(pg_bin() / name), *map(str, args)], check=True, **kwargs)


def connection_parameters(dbname=None) -> dict:
    if not CONFIG_FILE.is_file() and (os.name == "nt" or "GROUP9_DB_CONFIG" in os.environ):
        raise RuntimeError("Copy db_config.example.json to db_config.json and enter your PostgreSQL connection details.")
    parameters = {"host": str(SOCKET), "port": PORT, "dbname": DATABASE,
                  "user": USER, "connect_timeout": 5, "application_name": "CS4604 Group 9"}
    if CONFIG_FILE.is_file():
        try:
            settings = json.loads(CONFIG_FILE.read_text())
            for key in ("host", "port", "dbname", "user", "password"):
                parameters[key] = settings[key]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Check db_config.json. Use the same fields as db_config.example.json.") from exc
    if dbname is not None:
        parameters["dbname"] = dbname
    return parameters


def connect(dbname=None):
    try:
        import psycopg2
    except ImportError as exc:
        raise RuntimeError("Install the Python driver: python3 -m pip install -r requirements.txt") from exc
    return psycopg2.connect(**connection_parameters(dbname))


def start() -> None:
    connection_parameters()
    if CONFIG_FILE.is_file():
        print("Using the PostgreSQL server from db_config.json.")
        return
    RUNTIME.mkdir(parents=True, exist_ok=True)
    SOCKET.mkdir(mode=0o700, parents=True, exist_ok=True)
    SOCKET.chmod(0o700)
    if not (DATA / "PG_VERSION").exists():
        run_pg("initdb", "-D", str(DATA), "-U", USER, "--encoding=UTF8", "--locale=C",
               "--auth-local=trust", "--auth-host=reject")
        with (DATA / "postgresql.conf").open("a") as config:
            config.write("\n# This project accepts only local Unix-socket connections.\n")
            config.write("listen_addresses = ''\n")
            config.write(f"port = {PORT}\n")
            config.write("unix_socket_directories = '" + str(SOCKET).replace("'", "''") + "'\n")
            config.write("unix_socket_permissions = 0700\n")
    status = subprocess.run([str(pg_bin() / "pg_ctl"), "-D", str(DATA), "status"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if status.returncode != 0:
        run_pg("pg_ctl", "-D", str(DATA), "-l", str(RUNTIME / "postgres.log"), "-w", "start")
    (RUNTIME / "connection.json").write_text(json.dumps(connection_parameters(), indent=2) + "\n")


def setup() -> None:
    start()
    database = connection_parameters()["dbname"]
    connection = connect("postgres")
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
            exists = cursor.fetchone() is not None
        if not exists:
            # CREATE DATABASE cannot run in a transaction block.
            from psycopg2 import sql
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database)))
    finally:
        connection.close()
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regnamespace('rental')")
            exists = cursor.fetchone()[0] is not None
            if not exists:
                # Keep both standalone SQL scripts in one atomic setup transaction.
                for filename in ("01_schema.sql", "02_sample_data.sql"):
                    script = (PACKAGE / filename).read_text()
                    script = "\n".join(line for line in script.splitlines()
                                       if line.strip() not in ("BEGIN;", "COMMIT;"))
                    cursor.execute(script)
    print("Database ready. Existing project data was preserved." if exists else "Database created and sample data loaded.")
    status_report()


def status_report() -> dict:
    from psycopg2 import sql
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, version()")
            dbname, user, version = cursor.fetchone()
            counts = {}
            for table in TABLES:
                cursor.execute(sql.SQL("SELECT count(*) FROM rental.{}").format(sql.Identifier(table)))
                counts[table] = cursor.fetchone()[0]
    parameters = connection_parameters()
    report = {"database": dbname, "user": user, "server": version,
              "interface_language": "Python 3", "driver": "psycopg2",
              "host": parameters["host"], "port": parameters["port"], "table_counts": counts}
    print(json.dumps(report, indent=2))
    return report


def stop() -> None:
    connection_parameters()
    if CONFIG_FILE.is_file():
        print("Close the interface when finished. Manage the PostgreSQL server separately.")
        return
    if (DATA / "PG_VERSION").exists():
        run_pg("pg_ctl", "-D", str(DATA), "-m", "fast", "-w", "stop")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("setup", "start", "status", "stop"), nargs="?", default="setup")
    args = parser.parse_args()
    if args.action == "setup":
        setup()
    elif args.action == "start":
        start()
    elif args.action == "status":
        status_report()
    elif args.action == "stop":
        stop()


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        sys.exit(1)
