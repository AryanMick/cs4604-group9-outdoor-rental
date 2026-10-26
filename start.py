"""Launch the project with a local Python environment and your own MySQL server."""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Thread
import venv
import webbrowser

PROJECT = Path(__file__).resolve().parent
VENV = PROJECT / ".venv"
APP_URL = "http://127.0.0.1:5001"


def open_browser(url: str) -> None:
    """Use the default browser on Windows, macOS, or Linux."""
    try:
        if webbrowser.open(url, new=2):
            return
    except (webbrowser.Error, OSError):
        pass
    print(f"Open {url} in your browser.", flush=True)


def serve_interface(app) -> None:
    """Reserve the port before opening the browser, then serve the interface."""
    from werkzeug.serving import make_server

    with make_server("127.0.0.1", 5001, app, threaded=True) as server:
        print(f"Opening {APP_URL}. Stop with Ctrl+C.", flush=True)
        Thread(target=open_browser, args=(APP_URL,), daemon=True).start()
        server.serve_forever()


def run_in_project_environment() -> int:
    """Install dependencies once, then run this script with the local interpreter."""
    python = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        print("Creating the project's Python environment...", flush=True)
        venv.EnvBuilder(with_pip=True).create(VENV)
    requirements = PROJECT / "requirements.txt"
    stamp = VENV / ".requirements-installed"
    installed = stamp.read_text(encoding="utf-8") if stamp.is_file() else ""
    required = requirements.read_text(encoding="utf-8")
    if installed != required:
        print("Installing the project's Python packages...", flush=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(requirements)], check=True)
        stamp.write_text(required, encoding="utf-8")
    return subprocess.call([str(python), str(PROJECT / "start.py")], cwd=PROJECT)


def create_config(db_tools) -> None:
    """Ask once for this computer's existing MySQL connection settings."""
    print("First-time setup: enter your own MySQL connection settings.")
    print("MySQL Community 8.4 must already be installed and running.")
    settings = {
        "host": input("MySQL host [127.0.0.1]: ").strip() or "127.0.0.1",
        "port": input("MySQL port [3306]: ").strip() or "3306",
        "database": input("Project database [outdoor_rental_group9]: ").strip() or "outdoor_rental_group9",
        "user": input("MySQL username [root]: ").strip() or "root",
        "password": getpass.getpass("Your MySQL password (hidden): "),
    }
    try:
        settings["port"] = int(settings["port"])
    except ValueError as exc:
        raise RuntimeError("The MySQL port must be a number. Run python start.py again.") from exc
    if not 1 <= settings["port"] <= 65535:
        raise RuntimeError("The MySQL port must be between 1 and 65535.")
    if not re.fullmatch(r"[A-Za-z0-9_]+", settings["database"]):
        raise RuntimeError("Use only letters, numbers, and underscores in the database name.")
    descriptor = os.open(db_tools.CONFIG_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as config_file:
        json.dump(settings, config_file, indent=2)
        config_file.write("\n")
    print("Saved private connection settings. Future launches reuse them.")


def prepare_database(db_tools) -> None:
    """Initialize an empty database; preserve and reuse a complete existing schema."""
    settings = db_tools.load_config()
    connection = db_tools.connect(include_database=False)
    try:
        db_tools.validate_server(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema=%s",
                (settings["database"],),
            )
            objects = dict(cursor.fetchall())
    finally:
        connection.close()
    if not objects:
        db_tools.setup()
        return
    expected = {table: "BASE TABLE" for table in db_tools.TABLES}
    expected.update({"reservation_details": "VIEW", "employee_details": "VIEW"})
    missing = [name for name, kind in expected.items() if objects.get(name) != kind]
    if missing:
        raise RuntimeError(
            "The configured database has an incomplete or different schema. "
            "Missing expected tables/views: " + ", ".join(missing) + ". "
            "No data was changed. Inspect it or choose a new empty database in db_config.json."
        )
    print("Using the existing database; its data is preserved.")


def main() -> int:
    if sys.version_info < (3, 10):
        raise RuntimeError("Install Python 3.10 or newer, then run python start.py again.")
    if Path(sys.prefix).resolve() != VENV.resolve():
        return run_in_project_environment()
    import db_tools
    import pymysql

    if not db_tools.CONFIG_FILE.is_file():
        create_config(db_tools)
    try:
        prepare_database(db_tools)
    except pymysql.MySQLError as exc:
        raise RuntimeError(
            "Could not prepare the MySQL database. Install/start MySQL Community 8.4 "
            "and check your own host, port, username, password, and database permissions "
            "in db_config.json. MySQL reported: " + str(exc)
        ) from exc
    from rental_interface import app

    serve_interface(app)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped. Database data is preserved.")
        sys.exit(0)
    except (RuntimeError, OSError, subprocess.CalledProcessError, EOFError) as exc:
        print(f"Startup error: {exc}", file=sys.stderr)
        sys.exit(1)
