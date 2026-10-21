# Outdoor Equipment Rental Management System

CS4604 — Group 9

This is a small database project with a Python window for viewing the tables.

- DBMS: PostgreSQL 15.14
- Interface: Python 3 with Tkinter
- Database driver: psycopg2
- Data: 10 tables and 300 sample records, with at least 20 records in every table

## Run on this Mac

Unzip the project and double-click **Open Rental Interface.command**. It starts the local database, loads the tables on the first run, and opens the interface. Later runs keep the existing data.

You can also open Terminal in the project folder and run:

```sh
python3 db_tools.py setup
python3 rental_interface.py
```

If the database driver is missing, install it first:

```sh
python3 -m pip install -r requirements.txt
```

PostgreSQL and Python with Tkinter must be installed. They are already installed on the Mac used to test this project. The launcher uses `python3` from your PATH. If PostgreSQL is installed elsewhere, set `GROUP9_PG_BIN` to its `bin` folder. The launcher is for macOS; the SQL files use PostgreSQL syntax.

## Use the interface

Choose a table from the dropdown. **Refresh data** reloads its rows, **Test connection** checks the live database connection, and **Row counts** lists the number of records in each table. The interface displays data; it does not edit records.

For the assignment, capture each populated table and the green **Connection established successfully** message. Add your own screenshots to your submission. If the window first appears blank, click inside it.

## Main files

| File | Purpose |
|---|---|
| `01_schema.sql` | Creates the tables, keys, constraints, and views |
| `02_sample_data.sql` | Inserts the sample records |
| `db_tools.py` | Starts PostgreSQL and loads the SQL files |
| `rental_interface.py` | Displays the data in a Tkinter window |
| `Normalized_Schema_Report.md` | Explains the schema corrections and normalization |
| `Corrected_Relational_Schema.svg` | Shows the corrected tables and relationships |
| `Corrected_Relational_Schema.mmd` | Editable source for the schema diagram |

The SQL files are loaded once into an empty project database. Run the launcher again to reopen it. Runtime database files are created in `../work/group9_runtime/` next to the extracted project folder.

Close the interface, then double-click **Stop Database.command** to stop the project database. Alternatively:

```sh
python3 db_tools.py stop
```
