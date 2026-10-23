# Outdoor Equipment Rental Management System

CS4604 — Group 9. MySQL 8.4 database with a local browser interface and 300
synthetic sample records.

## Set up on Windows, macOS, or Linux

1. Install [MySQL Community 8.4](https://dev.mysql.com/downloads/mysql/8.4.html) and [Python 3.10 or newer](https://www.python.org/downloads/).
2. Start the MySQL server.
3. [Download the project ZIP](https://github.com/AryanMick/cs4604-group9-outdoor-rental/archive/refs/heads/main.zip) and extract it.
4. Copy `db_config.example.json` to `db_config.json`. Fill in the host, port,
   MySQL username, password, and database name. Keep this private file out of
   shared ZIP files and source control.
5. Open a terminal in the extracted project folder and run:

```sh
python -m pip install -r requirements.txt
python db_tools.py setup
python rental_interface.py
```

Use `python3` in place of `python` if your system requires it. The MySQL
account needs permission to create the configured database and create objects
inside it.

6. Open [http://127.0.0.1:5001](http://127.0.0.1:5001) in Chrome. The dashboard
shows the real connection state and live counts for all ten tables. Select a
table or view to see 20 rows per page. Tables with 40 rows have two pages.
Stop the interface with `Ctrl+C` in its terminal.

Run `setup` once on an absent or completely empty database. It never drops or
resets data. If setup fails, MySQL may have committed partial schema objects;
the error explains how to continue with a new empty database.

To check an already configured database without changing it:

```sh
python db_tools.py status
```

## Add or remove data

The browser interface is local and read-only. Open MySQL Workbench and connect
with the same settings from `db_config.json`. Select the
`outdoor_rental_group9` schema, then open a SQL tab.

Add a customer:

```sql
INSERT INTO customer (first_name, last_name, email)
VALUES ('Sam', 'Lee', 'SamLee@gmail.com');
```

Delete that customer:

```sql
DELETE FROM customer
WHERE email = 'SamLee@gmail.com';
```

Use your own values for other records. MySQL rejects deletion of a customer
that is linked to a reservation. Refresh the browser page after a change.

## Files

- `01_schema.sql` defines ten normalized InnoDB tables, constraints, indexes,
  and two joined views.
- `02_sample_data.sql` contains the 300 synthetic records.
- `verify_database.py` checks counts, keys, foreign keys, unique and CHECK
  constraints, orphan rows, reservation overlap, and rejected invalid data.
- [Normalized_Schema_Report.md](Normalized_Schema_Report.md) explains the
  design decisions, keys, types, and normalization.
- [Submission_Screenshots](Submission_Screenshots/README.md) contains the
  evidence captured from the running browser interface.
