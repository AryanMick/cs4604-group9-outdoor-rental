"""Flask interface for the Outdoor Rental MySQL database."""
from __future__ import annotations

from datetime import datetime
import math
import secrets

from flask import Flask, abort, flash, get_flashed_messages, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import pymysql

import db_tools
import customer_routes
import customer_service
import table_actions

app = Flask(__name__)
# Per-process key: sessions (and flashes) reset whenever the server restarts.
app.secret_key = secrets.token_hex(32)
app.register_blueprint(customer_routes.bp)

VIEWS = ("reservation_details", "employee_details")
CHOICES = (*db_tools.TABLES, *VIEWS)
ROWS_PER_PAGE = 20

def is_logged_in() -> bool:
    return session.get("role") in {"customer", "staff", "admin"}

def is_customer() -> bool:
    return session.get("role") == "customer"

def is_staff() -> bool:
    """True for a signed-in staff account."""
    return session.get("role") == "staff"


def is_admin() -> bool:
    """True for the admin role."""
    return session.get("role") == "admin"

def is_elevated() -> bool:
    """True for staff and admin roles."""
    return session.get("role") in {"staff", "admin"}

def deny_unless_staff() -> None:
    """Abort with 403 for customers and 401 for visitors who are not logged in."""
    if not is_staff():
        abort(403 if is_logged_in() else 401)

def deny_unless_admin() -> None:
    """Abort with 403 for customers and 401 for visitors who are not logged in."""
    if not is_admin():
        abort(403 if is_logged_in() else 401)

def deny_unless_elevated() -> None:
    """Abort with 403 for customers and 401 for visitors who are not logged in."""
    if not is_elevated():
        abort(403 if is_logged_in() else 401)

def deny_unless_logged_in() -> None:
    """Abort with 401 for visitors who are not logged in."""
    if not is_logged_in():
        abort(401)

def read_database(table: str | None = None, page: int = 1) -> dict:
    """Run the live connection check, counts, and optional table query."""
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION(), DATABASE(), CURRENT_USER(), CONNECTION_ID()")
            version, database, user, connection_id = cursor.fetchone()

            counts = {}
            for name in db_tools.TABLES:
                cursor.execute(f"SELECT COUNT(*) FROM `{name}`")
                counts[name] = cursor.fetchone()[0]

            result = {
                "connection": {
                    "version": version,
                    "database": database,
                    "user": user,
                    "connection_id": connection_id,
                    "checked": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
                },
                "counts": counts,
                "total_rows": sum(counts.values()),
            }

            if table is not None:
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
                row_count = cursor.fetchone()[0]
                total_pages = max(1, math.ceil(row_count / ROWS_PER_PAGE))
                page = min(max(page, 1), total_pages)
                offset = (page - 1) * ROWS_PER_PAGE
                cursor.execute(
                    f"SELECT * FROM `{table}` ORDER BY 1, 2 LIMIT %s OFFSET %s",
                    (ROWS_PER_PAGE, offset),
                )
                result.update(
                    {
                        "table": table,
                        "columns": [column[0] for column in cursor.description],
                        "rows": cursor.fetchall(),
                        "row_count": row_count,
                        "page": page,
                        "total_pages": total_pages,
                    }
                )
            return result
    finally:
        connection.close()


@app.route("/")
def dashboard():
    if is_customer():
        return redirect(url_for("customer.select_business"))
    try:
        data = read_database()
        return render_template("index.html", choices=CHOICES, error=None, **data)
    except (RuntimeError, pymysql.MySQLError) as exc:
        return (
            render_template(
                "index.html",
                choices=None,
                connection=None,
                counts={},
                total_rows=0,
                error=str(exc),
            ),
            503,
        )


@app.route("/go")
def choose_table():
    deny_unless_elevated()
    table = request.args.get("table", "")
    if not table:
        return redirect(request.referrer or url_for("dashboard"))
    if table not in CHOICES:
        abort(404)
    return redirect(url_for("show_table", table=table))


@app.route("/table/<table>")
def show_table(table: str):
    deny_unless_elevated()
    if table not in CHOICES:
        abort(404)
    try:
        page = request.args.get("page", default=1, type=int) or 1
        data = read_database(table, page)
        required = table_actions.required_columns(table) if table in table_actions.TABLE_PRIMARY_KEYS else set()
        return render_template("table.html", choices=CHOICES, error=None, required_columns=required, **data)
    except (RuntimeError, pymysql.MySQLError) as exc:
        return (
            render_template(
                "table.html",
                choices=CHOICES,
                table=table,
                connection=None,
                counts={},
                total_rows=0,
                columns=(),
                rows=(),
                row_count=0,
                page=1,
                total_pages=1,
                required_columns=set(),
                error=str(exc),
            ),
            503,
        )


@app.context_processor
def inject_form_helpers():
    """Expose the CSRF token, flashed messages, and login state to every template."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return {
        "csrf_token": session["csrf_token"],
        "messages": get_flashed_messages(with_categories=True),
        "insertable": set(table_actions.TABLE_PRIMARY_KEYS),
        "primary_keys": table_actions.TABLE_PRIMARY_KEYS,
        "base_tables": db_tools.TABLES,
        "logged_in": is_logged_in(),
        "is_elevated": is_elevated(),
        "is_admin": is_admin(),
    }


@app.route("/table/<table>/insert", methods=["POST"])
def insert_row(table: str):
    deny_unless_admin()
    if table not in table_actions.TABLE_PRIMARY_KEYS:
        abort(404)
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    # Blank fields are left out so the database applies AUTO_INCREMENT/NULL defaults.
    values = {
        name: value.strip()
        for name, value in request.form.items()
        if name != "csrf_token" and value.strip() != ""
    }
    try:
        new_id = table_actions.insert_record(table, values)
        flash(f"Record added to {table}" + (f" (id {new_id})." if new_id else "."), "success")
    except (ValueError, RuntimeError, pymysql.MySQLError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("show_table", table=table))


@app.route("/table/<table>/delete", methods=["POST"])
def delete_row(table: str):
    deny_unless_admin()
    if table not in table_actions.TABLE_PRIMARY_KEYS:
        abort(404)
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    key_values = {
        name: value.strip()
        for name, value in request.form.items()
        if name != "csrf_token"
    }
    try:
        table_actions.delete_record(table, key_values)
        flash(f"Record deleted from {table}.", "success")
    except (ValueError, RuntimeError, pymysql.MySQLError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("show_table", table=table))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    try:
        connection = db_tools.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT account_id, password_hash, role, customer_id
                    FROM auth_account
                    WHERE email = %s
                    """,
                    (email,),
                )
                account = cursor.fetchone()
        finally:
            connection.close()
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Login database failure")
        flash("Unable to sign in. Check the database connection and try again.", "error")
        return render_template("auth/login.html"), 503

    if account is None or not check_password_hash(account[1], password):
        flash("Invalid email or password.", "error")
        return render_template("auth/login.html"), 401

    role = account[2].lower()
    if role == "customer":
        try:
            cart_id = customer_service.start_customer_session(account[3])
        except (RuntimeError, pymysql.MySQLError):
            app.logger.exception("Customer cart setup failed")
            flash("Unable to open your cart. Please try signing in again.", "error")
            return render_template("auth/login.html"), 503

    # Only save the login once both the password and customer cart are ready.
    session.clear()
    session["account_id"] = account[0]
    session["role"] = role
    if role == "customer":
        session["customer_id"] = account[3]
        session["cart_id"] = cart_id

    return redirect(url_for("dashboard"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/register.html")
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    try:
        connection = db_tools.connect()
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Registration connection failure")
        flash("Unable to connect to the database.", "error")
        return render_template("auth/register.html"), 503
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO customer (first_name, last_name)
                VALUES (%s, %s)
                """,
                (first_name, last_name),
            )
            customer_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO auth_account (email, password_hash, role, customer_id)
                VALUES (%s, %s, 'CUSTOMER', %s)
                """,
                (email, generate_password_hash(password), customer_id),
            )
            account_id = cursor.lastrowid
        connection.commit()
    except pymysql.err.IntegrityError as exc:
        connection.rollback()

        if exc.args and exc.args[0] == 1062: # Duplicate email
            flash("That email is already registered.", "error")
            return render_template("auth/register.html"), 409

        app.logger.exception("Registration constraint failed")
        flash("Unable to create the account.", "error")
        return render_template("auth/register.html"), 400
    except pymysql.MySQLError:
        connection.rollback()
        app.logger.exception("Registration database failure")
        flash("Unable to create the account.", "error")
        return render_template("auth/register.html"), 503
    finally:
        connection.close()

    role = "customer"
    try:
        cart_id = customer_service.start_customer_session(customer_id)
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Customer cart setup failed")
        flash("Your account was created, but we could not start your session. Please sign in.", "warning")
        return render_template("auth/login.html"), 503
    session.clear()
    session["account_id"] = account_id
    session["role"] = role
    session["customer_id"] = customer_id
    session["cart_id"] = cart_id

    return redirect(url_for("dashboard"))

@app.route("/logout", methods=["POST"])
def logout():
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    if is_customer() and isinstance(session.get("customer_id"), int):
        try:
            customer_service.end_customer_session(session["customer_id"])
        except (RuntimeError, pymysql.MySQLError):
            pass  # The next customer login resets the cart anyway.
    session.clear()
    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
