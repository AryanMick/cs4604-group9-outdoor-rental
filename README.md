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

- **Login** or **Register** opens the dashboard; select a table to see its data
- **Make Admin** lets you change data: click **Add record**, fill in the fields (starred fields are required), then **Insert record**
- Use `YYYY-MM-DD HH:MM:SS` for date and time fields and existing IDs for related records
- Click **Delete** beside a row and confirm — MySQL blocks deletion when another record depends on it
- **Log in as Customer** opens the customer view: choose a business, browse its equipment, add items to the cart for a chosen time, then pay (a demonstration payment; only the last 4 card digits are saved)
- The customer's cart is deleted when they log out
- Open MySQL Workbench with the same login to run SQL, such as `SELECT * FROM customer;`

## Reset the database

The setup only fills an empty database. After the SQL files change, drop the database and start again:

```sh
mysql -u <your user> -p -e "DROP DATABASE outdoor_rental_group9;"
python start.py
```

Use your own database name if you changed it in `db_config.json`. The MySQL account needs permission to create triggers and routines.

Rental photos live in `static/img/`; `placeholder.jpg` is the default for equipment without its own `image_url`.

## If it fails

- **Access denied:** check the username and password in `db_config.json` — the account needs permission to create and use the project database
- **Connection refused:** start your MySQL server
- **Port 5001 in use:** stop the other running copy with Ctrl+C

Each teammate uses their own MySQL server and login
Keep `db_config.json` and `.venv` on your computer only

## Files

- `start.py` — starts the project
- `db_tools.py` — connects to MySQL and loads the SQL files
- `database/` — table definitions, sample data, and reservation triggers
- `rental_interface.py` and `table_actions.py` — admin pages and database actions
- `customer_routes.py` and `customer_service.py` — customer pages and their database logic
- `templates/` and `static/` — HTML, CSS, and JavaScript (`static/vendor/flatpickr` is the calendar library)
- `tests/` — unit tests: `python -m unittest discover tests`
- `requirements.txt` — Python packages
