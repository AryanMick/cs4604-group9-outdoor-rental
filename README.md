# Outdoor Equipment Rental Management System

CS4604 Group 9 — MySQL and Python with Flask

## Run it

1. Install [Python 3.10 or newer](https://www.python.org/downloads/) and [MySQL 8.4](https://dev.mysql.com/downloads/mysql/8.4.html), then start MySQL
2. Download and extract the [latest project](https://github.com/AryanMick/cs4604-group9-outdoor-rental/archive/refs/heads/main.zip), or run `git pull` in your existing clone
3. Open a terminal in the folder containing `start.py` and run:

```sh
python start.py
```

On Windows, try `py start.py` if Python is not found
On macOS or Linux, try `python3 start.py`

The first run installs the packages and asks for your MySQL login
Use the username and password from your own MySQL installation
It saves them privately in `db_config.json` and loads sample data into a new or empty database
Existing data stays saved

The browser opens automatically at [http://127.0.0.1:5001](http://127.0.0.1:5001)
Stop with **Ctrl+C** and run the same command next time

## Use it

- Select a table to see its data
- Click **Add record**, fill in the fields, then **Insert record**
- Use `YYYY-MM-DD` for dates and existing IDs for related records
- Click **Delete** beside a row and confirm — MySQL blocks deletion when another record depends on it
- Open MySQL Workbench with the same login to run SQL, such as `SELECT * FROM customer;`

## If it fails

- **Access denied:** check the username and password in `db_config.json` — the account needs permission to create and use the project database
- **Connection refused:** start your MySQL server
- **Port 5001 in use:** stop the other running copy with Ctrl+C

Each teammate uses their own MySQL server and login
Keep `db_config.json` and `.venv` on your computer only

## Files

- `start.py` — starts the project
- `db_tools.py` — connects to MySQL and loads the SQL files
- `database/` — table definitions and sample data
- `rental_interface.py` and `table_actions.py` — pages and database actions
- `templates/` and `static/` — HTML and CSS
- `requirements.txt` — Python packages
