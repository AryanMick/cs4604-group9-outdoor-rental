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
- **Log in as Customer** opens a demo login screen. **Continue as Demo Customer** uses the sample account with ID 31 (looked up by its demo email), not real authentication. Choose a business, browse equipment, add items to the cart for a chosen time, then pay (a demonstration payment; only the last 4 card digits are saved)
- **My Rentals** shows only the session customer's saved reservations, grouped by payment/order. Future `RESERVED` items appear in **Pending Pickup**; started `RESERVED` items, including overdue ones, appear in **Active Rentals**. **Rental History** contains `RETURNED` and `CANCELLED` items. Pickup is not tracked separately.
- The saved payment total is for the whole order. Per-item costs are estimates calculated using current rates because the schema does not store the original item price.
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
My Rentals checks whether each local image exists, then uses `placeholder.jpg` if present or the bundled `placeholder.svg` fallback. No schema changes or database reset are required for My Rentals or demo login.

### Test customer rentals

1. Run `python start.py`, open the dashboard, click **Log in as Customer**, then **Continue as Demo Customer**.
2. Open **My Rentals**. Customer 31 initially has no sample reservations, so all three sections should show empty messages.
3. Add two available items with future, non-overlapping booking times (day-rate items need whole 24-hour days) and complete the simulated checkout.
4. Click **My Rentals** on the confirmation screen. Both items should appear under one payment in **Pending Pickup**, with business, dates, status, cost, and image fallback.
5. Log out and back in: reservations persist although the cart is reset.
6. To exercise Active Rentals and History, use existing staff/admin controls or Workbench on your local test database. A `RESERVED` row whose start has passed is active; a passed due date shows an overdue warning. Set a demo reservation to `RETURNED` or `CANCELLED` to move it to history. Do not create a new status.
7. Other customers' reservations must not appear. Automated tests also cover session scoping, mixed-status multi-item orders, missing data, image fallback, and database errors: `python -m unittest discover tests`.

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
