# Outdoor Equipment Rental Management System

CS4604 — Group 9. PostgreSQL database with a Python interface and 300 sample records.

## Set up

1. Install PostgreSQL 15+ and Python 3 with Tkinter. Start PostgreSQL.
2. Click **Code → Download ZIP** and unzip the project.
3. Copy `db_config.example.json` and rename the copy `db_config.json`. Open it and enter your PostgreSQL username and password. Change the host and port if needed.
4. Open a terminal in the project folder and run:

```sh
python -m pip install -r requirements.txt
python db_tools.py setup
python rental_interface.py
```

Use `python3` if `python` is not recognized. Your PostgreSQL account needs permission to create the database. Keep `db_config.json` private.

## View data

Choose a table from the dropdown or **Tables** menu. Use **Next page** in that menu for more rows. Click **Test connection** to check the connection. Take screenshots of the tables and successful connection before submitting.

## Add or remove data

The app only displays data. Open PostgreSQL's SQL Shell (`psql`) using the connection details in `db_config.json`, then select the project database:

```sql
\c outdoor_rental_group9
```

Add a customer:

```sql
INSERT INTO rental.customer (first_name, last_name, email)
VALUES ('Sam', 'Lee', 'sam.lee@example.com');
```

Remove that same customer:

```sql
DELETE FROM rental.customer
WHERE email = 'sam.lee@example.com';
```

Use your own values for other records. A customer linked to a reservation cannot be deleted. Click **Refresh data** in the app to see your changes. Close the window when finished.

## Submission files

The [screenshots](Submission_Screenshots/README.md) show all tables and the working connection. The [schema report](Normalized_Schema_Report.md) explains the corrected design and data types.
