# Outdoor Equipment Rental Management System

CS4604 — Group 9. MySQL 8.4 database with a local browser interface and 300
synthetic sample records.

**Start here:** [Detailed project walkthrough and presentation guide](docs/PROJECT_WALKTHROUGH.md).

## First-time setup (Windows, macOS, or Linux)

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
```

Use `python3` in place of `python` if your system requires it. These commands
work in Windows PowerShell, macOS Terminal, or a Linux terminal. The MySQL
account needs permission to create the configured database and create objects
inside it.

Run `setup` once on an absent or completely empty database. It never drops or
resets data. If setup fails, MySQL may have committed partial schema objects;
the error explains how to continue with a new empty database.

## Normal startup and status

Start MySQL, then open a terminal in the project folder. Check the configured
database and start the interface:

```sh
python db_tools.py status
python rental_interface.py
```

Open [http://127.0.0.1:5001](http://127.0.0.1:5001) in Chrome. The dashboard
shows the real connection state and live counts for all ten tables. Select a
table or view to see 20 rows per page. Tables with 40 rows have two pages.
Stop the interface with `Ctrl+C` in its terminal. The `status` command checks
the database without changing it.

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

## Project folders

```text
Group9_Outdoor_Rental/
├── database/       SQL schema and sample data
├── docs/           Relational diagram and normalization report
├── submission/     Submission README, PDF, and verification results
│   └── screenshots/  17 browser screenshots and their file list
├── tests/          Interface tests that do not need MySQL
├── templates/      Browser page templates
├── static/         Browser styles
├── db_tools.py
├── rental_interface.py
├── verify_database.py
├── db_config.example.json
├── requirements.txt
└── README.md
```

- [database/01_schema.sql](database/01_schema.sql) defines ten normalized InnoDB
  tables, constraints, indexes, and two joined views.
- [database/02_sample_data.sql](database/02_sample_data.sql) contains the 300
  synthetic records.
- [docs/Normalized_Schema_Report.md](docs/Normalized_Schema_Report.md) explains
  the design decisions, keys, types, and normalization. The same folder holds
  the [relational diagram](docs/Corrected_Relational_Schema.svg) and its Mermaid source.
- [submission/README.md](submission/README.md) lists the materials to submit,
  including [Deliverables.pdf](submission/Deliverables.pdf), database check
  results, and [screenshots](submission/screenshots/README.md).
- `templates/` and `static/` contain the interface pages and styles.
- `tests/` contains the interface route tests. Run them from the project folder:

```sh
python -m unittest discover -s tests -v
```

To check counts, keys, constraints, orphan rows, reservation overlap, and
rejected invalid data against the live database, run:

```sh
python verify_database.py
```

Trial database changes are rolled back. The report is saved to
`submission/verification_results.json`. Your private `db_config.json` stays
in the project root beside the Python scripts.
