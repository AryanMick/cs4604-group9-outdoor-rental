"""Flask interface for the Outdoor Rental MySQL database."""
from __future__ import annotations

from datetime import datetime
import math
import secrets
from pathlib import Path

from flask import Flask, abort, flash, get_flashed_messages, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import pymysql

import admin_views
import db_tools
import customer_routes
import customer_service
import manager_service
import reports
import staff_service
import table_actions

app = Flask(__name__)
# Per-process key: sessions (and flashes) reset whenever the server restarts.
app.secret_key = secrets.token_hex(32)
app.register_blueprint(customer_routes.bp)

VIEWS = ("reservation_details", "employee_details")
CHOICES = (*db_tools.TABLES, *VIEWS)
ROWS_PER_PAGE = 20
app.config["MAX_CONTENT_LENGTH"] = manager_service.MAX_JPEG_BYTES + 128 * 1024

def is_logged_in() -> bool:
    return session.get("role") in {"customer", "employee", "manager", "admin"}

def is_customer() -> bool:
    return session.get("role") == "customer"

def is_employee() -> bool:
    """True for a signed-in employee"""
    return session.get("role") == "employee"

def is_manager() -> bool:
    """True for a signed-in manager"""
    return session.get("role") == "manager"

def is_staff() -> bool:
    """True for a signed-in staff account."""
    return is_employee() or is_manager()

def is_admin() -> bool:
    """True for the admin role."""
    return session.get("role") == "admin"

def is_elevated() -> bool:
    """True for staff and admin roles."""
    return is_staff() or is_admin()

def deny_unless_staff() -> None:
    """Abort with 403 for customers/admins and 401 for visitors who are not logged in."""
    if not is_staff():
        abort(403 if is_logged_in() else 401)

def deny_unless_employee() -> None:
    """Abort with 401 if not logged in. 403 if not employee"""
    if not is_employee():
        abort(403 if is_logged_in() else 401)

def deny_unless_manager() -> None:
    """Abort with 401 if not logged in. 403 if not manager"""
    if not is_manager():
        abort(403 if is_logged_in() else 401)

def deny_unless_admin() -> None:
    """Abort with 403 for customers/staff and 401 for visitors who are not logged in."""
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
                count_filter = " WHERE status <> 'RETIRED'" if name == "rental_equipment" and is_staff() else ""
                cursor.execute(f"SELECT COUNT(*) FROM `{name}`{count_filter}")
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
                staff_equipment_filter = table == "rental_equipment" and is_staff()
                where_clause = " WHERE status <> 'RETIRED'" if staff_equipment_filter else ""
                cursor.execute(f"SELECT COUNT(*) FROM `{table}`{where_clause}")
                row_count = cursor.fetchone()[0]
                total_pages = max(1, math.ceil(row_count / ROWS_PER_PAGE))
                page = min(max(page, 1), total_pages)
                offset = (page - 1) * ROWS_PER_PAGE
                cursor.execute(
                    f"SELECT * FROM `{table}`{where_clause} ORDER BY 1, 2 LIMIT %s OFFSET %s",
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
    if not is_logged_in():
        return redirect(url_for("login"))
    if is_customer():
        return redirect(url_for("customer.select_business"))
    if is_manager():
        return redirect(url_for("manager_dashboard"))
    if is_employee():
        return redirect(url_for("employee_dashboard"))
    try:
        data = read_database()
        report = reports.admin_report()
        return render_template("index.html", choices=CHOICES, error=None, report=report, **data)
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


def _staff_panel_data(tab: str, business_id: int) -> dict:
    """Data for the rentals, business-data, and checkout tabs shared by managers and employees."""
    if tab == "rentals":
        return {"rentals": staff_service.list_rentals(business_id)}
    if tab == "business":
        kind = "manager" if is_manager() else "employee"
        return {"sections": reports.report_set(kind, business_id)}
    if tab == "checkout":
        return {"options": staff_service.checkout_options(business_id)}
    return {}


@app.route("/admin/reports")
def admin_reports():
    deny_unless_admin()
    try:
        return render_template("admin/screen.html", title="System reports",
                               description="Overall statistics for the whole system.",
                               sections=reports.report_set("admin"), screen=None)
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Admin reports failed")
        abort(503)


@app.route("/admin/view/<screen>")
def admin_screen(screen: str):
    deny_unless_admin()
    if screen not in admin_views.SCREENS:
        abort(404)
    try:
        data = admin_views.run_screen(screen)
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Admin screen failed")
        abort(503)
    return render_template("admin/screen.html", title=data["title"], description=data["description"],
                           sections=[data], screen=screen)


@app.route("/manager")
def manager_dashboard():
    deny_unless_manager()
    business_id = session.get("business_id")
    if not isinstance(business_id, int):
        abort(403)
    tab = request.args.get("tab", "rentals")
    if tab not in {"rentals", "business", "checkout", "equipment"}:
        abort(404)
    try:
        business_name = manager_service.get_business_name(business_id)
        if business_name is None:
            abort(404)
        equipment = manager_service.list_equipment(business_id) if tab == "equipment" else []
        return render_template(
            "manager/dashboard.html", business_name=business_name, active_tab=tab, equipment=equipment,
            **_staff_panel_data(tab, business_id),
        )
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Manager dashboard database failure")
        flash("Unable to load your business dashboard. Check the database connection and try again.", "error")
        return render_template(
            "manager/dashboard.html", business_name="My Business", active_tab="none", equipment=[],
        ), 503


@app.route("/employee")
def employee_dashboard():
    deny_unless_employee()
    business_id = session.get("business_id")
    if not isinstance(business_id, int):
        abort(403)
    tab = request.args.get("tab", "rentals")
    if tab not in {"rentals", "business", "checkout"}:
        abort(404)
    try:
        business_name = manager_service.get_business_name(business_id)
        if business_name is None:
            abort(404)
        return render_template(
            "employee/dashboard.html", business_name=business_name, active_tab=tab,
            **_staff_panel_data(tab, business_id),
        )
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Employee dashboard database failure")
        flash("Unable to load your business dashboard. Check the database connection and try again.", "error")
        return render_template(
            "employee/dashboard.html", business_name="My Business", active_tab="none",
        ), 503


@app.route("/staff/checkout", methods=["POST"])
def staff_checkout():
    deny_unless_staff()
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    business_id = session.get("business_id")
    if not isinstance(business_id, int):
        abort(403)
    try:
        result = staff_service.checkout_customer(
            business_id,
            request.form.get("customer_id", ""),
            request.form.get("equipment_id", ""),
            request.form.get("start", ""),
            request.form.get("end", ""),
            request.form.get("card_number", ""),
            request.form.get("expiry", ""),
            request.form.get("security_code", ""),
        )
        flash(
            f"Checked out {result['equipment_type']} (reservation #{result['reservation_id']}, "
            f"payment #{result['payment_id']}, ${result['total']}).",
            "success",
        )
    except customer_service.BookingError as exc:
        flash(str(exc), "error")
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Staff checkout failed")
        flash("Unable to complete the checkout. Check the database connection and try again.", "error")
    endpoint = "manager_dashboard" if is_manager() else "employee_dashboard"
    return redirect(url_for(endpoint, tab="checkout"))


def _manager_equipment_redirect():
    return redirect(url_for("manager_dashboard", tab="equipment"))


def _manager_business_id() -> int:
    business_id = session.get("business_id")
    if not isinstance(business_id, int):
        abort(403)
    return business_id


def _manager_image_upload() -> tuple[str | None, bytes | None]:
    image = request.files.get("image")
    if image is None or not image.filename:
        return None, None
    return image.filename, image.stream.read(manager_service.MAX_JPEG_BYTES + 1)


@app.route("/manager/equipment/add", methods=["POST"])
def manager_add_equipment():
    deny_unless_manager()
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    filename, content = _manager_image_upload()
    if filename is None:
        flash("Choose a JPG image for this equipment.", "error")
        return _manager_equipment_redirect()
    try:
        manager_service.create_equipment(
            _manager_business_id(),
            request.form.get("equipment_type", ""),
            request.form.get("description", ""),
            request.form.get("rate", ""),
            request.form.get("rate_unit", ""),
            request.form.get("status", "AVAILABLE"),
            filename,
            content,
            Path(app.static_folder) / "img",
        )
        flash("Equipment added to your business.", "success")
    except manager_service.ManagerEquipmentError as exc:
        flash(str(exc), "error")
    except (RuntimeError, OSError, pymysql.MySQLError):
        app.logger.exception("Manager equipment creation failed")
        flash("Unable to add equipment. Check the database and image file, then try again.", "error")
    return _manager_equipment_redirect()


@app.route("/manager/equipment/<int:equipment_id>/update", methods=["POST"])
def manager_update_equipment(equipment_id: int):
    deny_unless_manager()
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    filename, content = _manager_image_upload()
    try:
        manager_service.update_equipment(
            _manager_business_id(), equipment_id,
            request.form.get("equipment_type", ""),
            request.form.get("description", ""),
            request.form.get("rate", ""),
            request.form.get("rate_unit", ""),
            request.form.get("status", ""),
            filename, content, Path(app.static_folder) / "img",
        )
        flash("Equipment details updated.", "success")
    except manager_service.ManagerEquipmentError as exc:
        flash(str(exc), "error")
    except (RuntimeError, OSError, pymysql.MySQLError):
        app.logger.exception("Manager equipment update failed")
        flash("Unable to update equipment. Check the database and image file, then try again.", "error")
    return _manager_equipment_redirect()


@app.route("/manager/equipment/<int:equipment_id>/delete", methods=["POST"])
def manager_delete_equipment(equipment_id: int):
    deny_unless_manager()
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    try:
        manager_service.retire_equipment(
            _manager_business_id(), equipment_id, Path(app.static_folder) / "img",
        )
        flash("Equipment removed from your active business inventory. Rental history was preserved.", "success")
    except manager_service.ManagerEquipmentError as exc:
        flash(str(exc), "error")
    except (RuntimeError, OSError, pymysql.MySQLError):
        app.logger.exception("Manager equipment removal failed")
        flash("Unable to remove equipment. Check the database connection and try again.", "error")
    return _manager_equipment_redirect()


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
        "is_customer": is_customer(),
        "is_elevated": is_elevated(),
        "is_admin": is_admin(),
        "is_manager": is_manager(),
        "is_employee": is_employee()
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


@app.route("/table/<table>/update", methods=["POST"])
def update_row(table: str):
    deny_unless_admin()
    if table not in table_actions.TABLE_PRIMARY_KEYS:
        abort(404)
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)
    primary_keys = table_actions.TABLE_PRIMARY_KEYS[table]
    key_values = {
        name: request.form.get(f"key_{name}", "").strip() for name in primary_keys
    }
    # Blank fields are saved as NULL.
    values = {
        name: value.strip() if value.strip() != "" else None
        for name, value in request.form.items()
        if name not in ("csrf_token", "page") and not name.startswith("key_")
    }
    try:
        table_actions.update_record(table, key_values, values)
        flash(f"Record updated in {table}.", "success")
    except (ValueError, RuntimeError, pymysql.MySQLError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("show_table", table=table, page=request.form.get("page", 1, type=int)))


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
                    SELECT aa.account_id, aa.password_hash, aa.role,
                           aa.customer_id, aa.employee_id, aa.manager_id, aa.admin_id,
                           m.business_id,
                           e.manager_id
                    FROM auth_account as aa
                    LEFT JOIN employee e ON e.employee_id = aa.employee_id
                    LEFT JOIN manager m ON m.manager_id = COALESCE(aa.manager_id, e.manager_id)
                    WHERE aa.email = %s
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
    match (role):
        case "customer":
            session["customer_id"] = account[3]
            session["role_id"] = account[3]
            session["cart_id"] = cart_id
        case "employee":
            session["role_id"] = account[4]
            session["manager_id"] = account[8]
            session["business_id"] = account[7]
        case "manager":
            session["role_id"] = account[5]
            session["business_id"] = account[7]
        case "admin":
            session["role_id"] = account[6]

    return redirect(url_for("dashboard"))

@app.route("/profile", methods=["GET"])
def profile():
    deny_unless_logged_in()

    try:
        connection = db_tools.connect()
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Profile connection failure")
        flash("Unable to connect to the database.", "error")
        return redirect(url_for("dashboard")), 503

    try:
        with connection.cursor() as cursor:
            if is_customer():
                cursor.execute(
                    """
                    SELECT aa.email, c.first_name, c.last_name
                    FROM  auth_account as aa
                    LEFT JOIN customer c on c.customer_id = aa.customer_id
                    WHERE aa.account_id = %s
                    """,
                    (session["account_id"])
                )
            elif is_employee():
                cursor.execute(
                    """
                    SELECT aa.email, e.first_name, e.last_name,
                           m.first_name, m.last_name,
                           b.business_name, b.address
                    FROM  auth_account as aa
                    LEFT JOIN employee e on e.employee_id = aa.employee_id
                    LEFT JOIN manager m on m.manager_id = e.manager_id
                    LEFT JOIN business b on b.business_id = m.business_id
                    WHERE aa.account_id = %s
                    """,
                    (session["account_id"])
                )
            elif is_manager():
                cursor.execute(
                    """
                    SELECT aa.email, m.first_name, m.last_name,
                            b.business_name, b.address
                    FROM  auth_account as aa
                    LEFT JOIN manager m on m.manager_id = aa.manager_id
                    LEFT JOIN business b on b.business_id = m.business_id
                    WHERE aa.account_id = %s
                    """,
                    (session["account_id"])
                )
            elif is_admin():
                cursor.execute(
                    """
                    SELECT aa.email, a.first_name, a.last_name
                    FROM  auth_account as aa
                    LEFT JOIN admin a on a.admin_id = aa.admin_id
                    WHERE aa.account_id = %s
                    """,
                    (session["account_id"])
                )
            else:
                app.logger.exception("Invalid role in get profile")
                flash("Invalid role. Log out and back in again", "error")
                return redirect(url_for("dashboard")), 503
            profile_data = cursor.fetchone()
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Profile database failure")
        flash("Unable to view profile. Check the database connection and try again.", "error")
        return redirect(url_for("dashboard")), 503
    finally:
        connection.close()

    if profile_data is None:
        # The account was deleted while this session was still signed in.
        session.clear()
        flash("This account no longer exists. Please sign in again.", "error")
        return redirect(url_for("login"))

    return render_template("auth/profile.html", profile=profile_data)

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

@app.route("/profile/change_password", methods=["GET", "POST"])
def change_password():
    deny_unless_logged_in()
    if (request.method == "GET"):
        return render_template("auth/change_password.html")
    token = session.get("csrf_token")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400)

    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if (confirm_password != new_password):
        flash("Passwords must match", "error")
        return render_template("auth/change_password.html")

    try:
        connection = db_tools.connect()
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Change password connection failure")
        flash("Unable to connect to the database.", "error")
        return redirect(url_for("dashboard")), 503

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT password_hash
                FROM auth_account
                WHERE account_id = %s
                """,
                (session["account_id"])
            )
            account = cursor.fetchone()
            if (account is None):
                flash("Could not fetch account", "error")
                return render_template("auth/change_password.html")
            if not check_password_hash(account[0], current_password):
                flash("That is not your current password", "error")
                return render_template("auth/change_password.html"), 401

            cursor.execute(
                """
                UPDATE auth_account
                SET password_hash = %s
                WHERE account_id = %s
                """,
                (generate_password_hash(new_password), session["account_id"])
            )
            connection.commit()

    except (RuntimeError, pymysql.MySQLError):
        connection.rollback()
        app.logger.exception("Change password database failure")
        flash("Unable to change password. Check the database connection and try again.", "error")
        return redirect(url_for("profile")), 503
    finally:
        connection.close()

    flash("Successfully changed password")
    return redirect(url_for("profile"))

@app.route("/new_business", methods=["GET", "POST"])
def new_business():
    deny_unless_admin()
    if (request.method == "GET"):
        return render_template("auth/new_business.html")

    business_name = request.form.get("business_name", "").strip()
    business_address = request.form.get("business_address", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    try:
        connection = db_tools.connect()
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Registration connection failure")
        flash("Unable to connect to the database.", "error")
        return render_template("auth/new_business.html"), 503
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO business (business_name, address)
                VALUES (%s, %s)
                """,
                (business_name, business_address),
            )
            business_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO manager (first_name, last_name, business_id)
                VALUES (%s, %s, %s)
                """,
                (first_name, last_name, business_id)
            )
            manager_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO auth_account (email, password_hash, role, manager_id)
                VALUES (%s, %s, 'MANAGER', %s)
                """,
                (email, generate_password_hash(password), manager_id),
            )
        connection.commit()
    except pymysql.err.IntegrityError as exc:
        connection.rollback()

        if exc.args and exc.args[0] == 1062: # Duplicate email
            flash("That email is already registered.", "error")
            return render_template("auth/new_business.html"), 409

        app.logger.exception("Registration constraint failed")
        flash("Unable to create the account.", "error")
        return render_template("auth/new_business.html"), 400
    except pymysql.MySQLError:
        connection.rollback()
        app.logger.exception("Registration database failure")
        flash("Unable to create the account.", "error")
        return render_template("auth/new_business.html"), 503
    finally:
        connection.close()

    flash("Successfully made a new business and manager account")
    return redirect(url_for("dashboard"))

@app.route("/new_admin", methods=["GET", "POST"])
def new_admin():
    deny_unless_admin()
    if (request.method == "GET"):
        return render_template("auth/new_admin.html")
    
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    try:
        connection = db_tools.connect()
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Registration connection failure")
        flash("Unable to connect to the database.", "error")
        return render_template("auth/new_admin.html"), 503
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO admin (first_name, last_name)
                VALUES (%s, %s)
                """,
                (first_name, last_name),
            )
            admin_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO auth_account (email, password_hash, role, admin_id)
                VALUES (%s, %s, 'ADMIN', %s)
                """,
                (email, generate_password_hash(password), admin_id),
            )
        connection.commit()
    except pymysql.err.IntegrityError as exc:
        connection.rollback()

        if exc.args and exc.args[0] == 1062: # Duplicate email
            flash("That email is already registered.", "error")
            return render_template("auth/new_admin.html"), 409

        app.logger.exception("Registration constraint failed")
        flash("Unable to create the account.", "error")
        return render_template("auth/new_admin.html"), 400
    except pymysql.MySQLError:
        connection.rollback()
        app.logger.exception("Registration database failure")
        flash("Unable to create the account.", "error")
        return render_template("auth/new_admin.html"), 503
    finally:
        connection.close()

    flash("Successfully made a new admin account")
    return redirect(url_for("dashboard"))

def _staff_form_options() -> dict:
    """Business / manager choices (by name) for admins creating staff accounts."""
    if not is_admin():
        return {}
    try:
        return {
            "businesses": reports._query("SELECT business_id, business_name FROM business ORDER BY business_name"),
            "managers": reports._query(
                "SELECT m.manager_id, CONCAT(m.first_name, ' ', m.last_name, ' - ', b.business_name) AS label "
                "FROM manager m JOIN business b ON b.business_id = m.business_id ORDER BY b.business_name, m.last_name"),
        }
    except (RuntimeError, pymysql.MySQLError):
        return {"businesses": [], "managers": []}


@app.route("/new_employee", methods=["GET", "POST"])
def new_employee():
    deny_unless_elevated()
    if (request.method == "GET"):
        return render_template("auth/new_employee.html", **_staff_form_options())
    
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    manager_id = request.form.get("manager_id", type=int) if is_admin() else session["role_id"]
    if not manager_id:
        flash("Choose a manager.", "error")
        return render_template("auth/new_employee.html", **_staff_form_options()), 400
    try:
        connection = db_tools.connect()
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Registration connection failure")
        flash("Unable to connect to the database.", "error")
        return render_template("auth/new_employee.html"), 503
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO employee (first_name, last_name, manager_id)
                VALUES (%s, %s, %s)
                """,
                (first_name, last_name, manager_id),
            )
            employee_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO auth_account (email, password_hash, role, employee_id)
                VALUES (%s, %s, 'EMPLOYEE', %s)
                """,
                (email, generate_password_hash(password), employee_id),
            )
        connection.commit()
    except pymysql.err.IntegrityError as exc:
        connection.rollback()

        if exc.args and exc.args[0] == 1062: # Duplicate email
            flash("That email is already registered.", "error")
            return render_template("auth/register.html"), 409

        app.logger.exception("Registration constraint failed")
        flash("Unable to create the account.", "error")
        return render_template("auth/new_employee.html"), 400
    except pymysql.MySQLError:
        connection.rollback()
        app.logger.exception("Registration database failure")
        flash("Unable to create the account.", "error")
        return render_template("auth/new_employee.html"), 503
    finally:
        connection.close()

    flash("Successfully made a new employee account")
    return redirect(url_for("dashboard"))

@app.route("/new_manager", methods=["GET", "POST"])
def new_manager():
    deny_unless_elevated()
    if (request.method == "GET"):
        return render_template("auth/new_manager.html", **_staff_form_options())
    
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    business_id = request.form.get("business_id", type=int) if is_admin() else session["business_id"]
    if not business_id:
        flash("Choose a business.", "error")
        return render_template("auth/new_manager.html", **_staff_form_options()), 400
    try:
        connection = db_tools.connect()
    except (RuntimeError, pymysql.MySQLError):
        app.logger.exception("Registration connection failure")
        flash("Unable to connect to the database.", "error")
        return render_template("auth/new_manager.html"), 503
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO manager (first_name, last_name, business_id)
                VALUES (%s, %s, %s)
                """,
                (first_name, last_name, business_id),
            )
            manager_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO auth_account (email, password_hash, role, manager_id)
                VALUES (%s, %s, 'MANAGER', %s)
                """,
                (email, generate_password_hash(password), manager_id),
            )
        connection.commit()
    except pymysql.err.IntegrityError as exc:
        connection.rollback()

        if exc.args and exc.args[0] == 1062: # Duplicate email
            flash("That email is already registered.", "error")
            return render_template("auth/new_manager.html"), 409

        app.logger.exception("Registration constraint failed")
        flash("Unable to create the account.", "error")
        return render_template("auth/new_manager.html"), 400
    except pymysql.MySQLError:
        connection.rollback()
        app.logger.exception("Registration database failure")
        flash("Unable to create the account.", "error")
        return render_template("auth/new_manager.html"), 503
    finally:
        connection.close()

    flash("Successfully made a new manager account")
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
