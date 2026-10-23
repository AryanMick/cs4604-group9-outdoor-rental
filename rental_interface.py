"""Read-only Flask interface for the Outdoor Rental MySQL database."""
from __future__ import annotations

from datetime import datetime
import math

from flask import Flask, abort, redirect, render_template, request, url_for
import pymysql

import db_tools

app = Flask(__name__)

VIEWS = ("reservation_details", "employee_details")
CHOICES = (*db_tools.TABLES, *VIEWS)
ROWS_PER_PAGE = 20


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
    try:
        data = read_database()
        return render_template("index.html", choices=CHOICES, error=None, **data)
    except (RuntimeError, pymysql.MySQLError) as exc:
        return (
            render_template(
                "index.html",
                choices=CHOICES,
                connection=None,
                counts={},
                total_rows=0,
                error=str(exc),
            ),
            503,
        )


@app.route("/go")
def choose_table():
    table = request.args.get("table", "")
    if table not in CHOICES:
        abort(404)
    return redirect(url_for("show_table", table=table))


@app.route("/table/<table>")
def show_table(table: str):
    if table not in CHOICES:
        abort(404)
    try:
        page = request.args.get("page", default=1, type=int) or 1
        data = read_database(table, page)
        return render_template("table.html", choices=CHOICES, error=None, **data)
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
                error=str(exc),
            ),
            503,
        )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=False)
