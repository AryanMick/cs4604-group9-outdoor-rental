# Outdoor Equipment Rental Management System

CS4604 — Group 9. PostgreSQL database with a Python interface and 300 sample records.

## Run

1. Install and start PostgreSQL 15+. Install Python 3 with Tkinter.
2. Download the project. Copy `db_config.example.json` to `db_config.json` and enter your PostgreSQL username and password. Adjust the host and port if needed.
3. Open a terminal in the project folder and run:

```sh
python -m pip install -r requirements.txt
python db_tools.py setup
python rental_interface.py
```

Use `python3` if your computer uses that command instead of `python`. Your PostgreSQL account needs permission to create the project database.

## Use

Select a table to view its data. Click **Test connection** to check the connection. Take screenshots of the populated tables and successful connection for submission.

Close the window when finished. Keep `db_config.json` private.
