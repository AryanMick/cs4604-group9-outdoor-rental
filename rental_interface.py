"""Python/Tkinter interface for viewing real rows from the Group 9 database."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import tkinter as tk
from tkinter import messagebox, ttk

import psycopg2
from psycopg2 import sql

import db_tools


class RentalInterface(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CS4604 Group 9 - Outdoor Equipment Rental Management System")
        self.geometry("1390x930")
        self.minsize(1100, 740)
        self.connection = None
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.style.configure("Treeview", rowheight=26, font=("Helvetica", 11))
        self.style.configure("Treeview.Heading", font=("Helvetica", 11, "bold"), padding=8)
        self.style.configure("Title.TLabel", font=("Helvetica", 20, "bold"))
        self.style.configure("Sub.TLabel", font=("Helvetica", 11))
        self.style.configure("Connected.TLabel", background="#e6f3e9", foreground="#175e2d", padding=12,
                             font=("Helvetica", 12, "bold"))
        self.style.configure("Offline.TLabel", background="#fbe9e9", foreground="#9b1c1c", padding=12)
        self.configure(background="#f6f7f8")

        outer = ttk.Frame(self, padding=20)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Outdoor Equipment Rental Management System", style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text="CS4604  |  Group 9  |  DBMS: PostgreSQL  |  Interface language: Python 3 (Tkinter)",
                  style="Sub.TLabel").pack(anchor="w", pady=(8, 14))

        self.banner = ttk.Label(outer, text="Connecting to PostgreSQL...", style="Offline.TLabel")
        self.banner.pack(fill="x")
        self.connection_info = tk.StringVar()
        ttk.Label(outer, textvariable=self.connection_info, style="Sub.TLabel").pack(anchor="w", pady=(7, 12))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 12))
        ttk.Label(controls, text="Table or view:").pack(side="left", padx=(0, 10))
        self.selected = tk.StringVar(value="customer")
        self.choices = ttk.Combobox(controls, state="readonly", width=30, textvariable=self.selected,
                                   values=(*db_tools.TABLES, "reservation_details", "employee_details"))
        self.choices.pack(side="left")
        self.choices.bind("<<ComboboxSelected>>", lambda event: self.load_table())
        ttk.Button(controls, text="Refresh data", command=self.load_table).pack(side="left", padx=10)
        ttk.Button(controls, text="Test connection", command=self.test_connection).pack(side="left")
        ttk.Button(controls, text="Row counts", command=self.show_counts).pack(side="left", padx=10)

        self.table_title = tk.StringVar()
        ttk.Label(outer, textvariable=self.table_title, font=("Helvetica", 14, "bold")).pack(anchor="w", pady=(0, 8))
        grid = ttk.Frame(outer)
        grid.pack(fill="both", expand=True)
        grid.rowconfigure(0, weight=1)
        grid.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(grid, show="headings", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(grid, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(grid, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.tag_configure("odd", background="#eef3f7")
        self.query = tk.StringVar()
        ttk.Label(outer, textvariable=self.query, font=("Menlo", 10)).pack(anchor="w", pady=(12, 0))
        ttk.Label(outer, text="Data is read directly from PostgreSQL. Sample records are fictional.",
                  style="Sub.TLabel").pack(anchor="w", pady=(7, 0))
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.initial_connect)

    def initial_connect(self):
        if self.test_connection():
            self.load_table()

    def ensure_connection(self):
        if self.connection is None or self.connection.closed:
            self.connection = db_tools.connect()
            # Each click issues a fresh read transaction and releases its snapshot.
            self.connection.autocommit = True

    def test_connection(self):
        try:
            self.ensure_connection()
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user, current_setting('server_version'), pg_backend_pid()")
                database, user, version, pid = cursor.fetchone()
            self.banner.configure(text=f"Connection established successfully  |  PostgreSQL {version}  |  Database: {database}",
                                  style="Connected.TLabel")
            host = self.connection.info.host
            port = self.connection.info.port
            self.connection_info.set(f"Driver: psycopg2  |  User: {user}  |  Host: {host}  |  Port: {port}  |  Backend PID: {pid}  |  Checked: {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}")
            return True
        except (psycopg2.Error, RuntimeError) as exc:
            self.failed_connection(exc)
            return False

    def failed_connection(self, error):
        self.banner.configure(text="Connection failed - start the database and test again.", style="Offline.TLabel")
        self.connection_info.set("No successful database connection is currently verified.")
        if self.connection is not None:
            self.connection.close()
        self.connection = None
        messagebox.showerror("Database connection", str(error), parent=self)

    def display(self, columns, rows):
        self.tree.delete(*self.tree.get_children())
        self.tree.configure(columns=columns)
        wide = {"business_name": 245, "address": 440, "email": 285, "equipment_type": 220,
                "privilege": 250, "table_name": 230, "customer": 190, "manager": 190}
        for col in columns:
            width = wide.get(col, 155 if col.endswith("_date") else 140)
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, minwidth=90, stretch=True)
        for index, row in enumerate(rows):
            values = []
            for value in row:
                if value is None:
                    values.append("NULL")
                elif isinstance(value, Decimal):
                    values.append(f"{value:.2f}")
                else:
                    values.append(str(value))
            self.tree.insert("", "end", values=values, tags=("odd",) if index % 2 else ())

    def load_table(self):
        table = self.selected.get()
        if table not in (*db_tools.TABLES, "reservation_details", "employee_details"):
            return
        try:
            self.ensure_connection()
            with self.connection.cursor() as cursor:
                # Identifiers use psycopg2.sql, never string interpolation.
                cursor.execute(sql.SQL("SELECT * FROM rental.{} ORDER BY 1, 2").format(sql.Identifier(table)))
                columns = [column.name for column in cursor.description]
                rows = cursor.fetchall()
            self.display(columns, rows)
            self.table_title.set(f"rental.{table}  |  {len(rows)} rows")
            self.query.set(f"SELECT * FROM rental.{table} ORDER BY 1, 2;")
            self.test_connection()
        except (psycopg2.Error, RuntimeError) as exc:
            self.tree.delete(*self.tree.get_children())
            self.table_title.set("Data unavailable")
            self.failed_connection(exc)

    def show_counts(self):
        try:
            self.ensure_connection()
            rows = []
            with self.connection.cursor() as cursor:
                for table in db_tools.TABLES:
                    cursor.execute(sql.SQL("SELECT count(*) FROM rental.{}").format(sql.Identifier(table)))
                    rows.append((table, cursor.fetchone()[0]))
            self.display(("table_name", "row_count"), rows)
            self.table_title.set("All 10 base tables - live PostgreSQL row counts")
            self.query.set("SELECT count(*) FROM rental.<table>;  -- each table queried individually")
            self.test_connection()
        except (psycopg2.Error, RuntimeError) as exc:
            self.failed_connection(exc)

    def close(self):
        if self.connection is not None:
            self.connection.close()
        self.destroy()


if __name__ == "__main__":
    RentalInterface().mainloop()
