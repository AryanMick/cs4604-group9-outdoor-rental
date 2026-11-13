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

- **Login** uses the email and password in `auth_account`; registration is not available yet
- Sample customer login: `alexcarter@gmail.com` with password `password`
- Customers choose a business, add equipment to their own cart, and complete the practice checkout
- On the business selection page, search by equipment type, description, or business name. Equipment matches link to the matching items at that business; availability is checked when choosing rental dates.
- Staff can view tables; admins can also add and delete records
- To add a row as an admin, click **Add record**, fill in the required fields, then **Insert record**
- Use `YYYY-MM-DD HH:MM:SS` for date and time fields and existing IDs for related records
- Click **Delete** beside a row and confirm — MySQL blocks deletion when another record depends on it
- Checkout is a demonstration payment; only the last 4 card digits are saved
- **My Rentals** shows only the session customer's saved reservations, grouped by payment/order. Future `RESERVED` items appear in **Pending Pickup**; started `RESERVED` items, including overdue ones, appear in **Active Rentals**. **Rental History** contains `RETURNED` and `CANCELLED` items. Pickup is not tracked separately.
- The saved payment total is for the whole order. Per-item costs are estimates calculated using current rates because the schema does not store the original item price.
- The customer's cart is deleted when they log out
- Open MySQL Workbench with the same login to run SQL, such as `SELECT * FROM customer;`

## Older database copies

The new login needs the `auth_account` table
If your database was created before that change, set a new database name in `db_config.json` and run `python start.py`
Setup fills the new database and keeps the old one
The MySQL account needs permission to create the database, triggers, and routines

Equipment images for customer browsing and cart review live in `static/img/`; `image_url` stores a path relative to that folder. If an image file is missing, those pages use the bundled `img/placeholder.svg` fallback. My Rentals keeps its existing local-image check and placeholder fallback.

For an existing database, run `python update_equipment_images.py` from the project folder after pulling the image update. The script uses the connection settings in `db_config.json`, changes only equipment still using the default `img/placeholder.jpg` path, and preserves all other data and custom image paths. It is safe to run more than once; database reinitialization is not needed.

John's Boardshop is included in new sample databases. For an existing database, run `python add_boardshop.py` once to add it and its mountain bike, rental and demo skis and snowboards, and snow helmet. The script uses `db_config.json`, adds only missing equipment types, and does not replace existing rows; it can be run again safely. Rates and the address are illustrative.

New sample databases also have mountain bikes at Blue Ridge Outfitters, Trailhead Equipment, Summit Outdoor Gear, and Roanoke Trail Supply. For an existing sample database, run `python add_mountain_bikes.py` to add missing bikes at those four shops. It verifies the sample businesses before making changes and can be run again safely without replacing existing inventory.

The boardshop equipment photos are from Pexels: [mountain bike](https://www.pexels.com/photo/blue-mountain-bike-with-dual-suspension-outdoors-36450314/), [skis](https://www.pexels.com/photo/pair-of-skis-on-snowy-surface-in-winter-setting-30417375/), [snowboard](https://www.pexels.com/photo/a-snowboard-on-a-snow-10933679/), and [snow helmet](https://www.pexels.com/photo/profile-of-a-ski-enthusiast-in-winter-gear-29767332/), used under the [Pexels license](https://www.pexels.com/license/). Images are illustrative and do not identify the actual rental equipment.

### Test customer rentals

1. Run `python start.py`, click **Login**, and sign in with `alexcarter@gmail.com` / `password`.
2. Open **My Rentals** to see that customer's reservations.
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
- `add_boardshop.py` — adds the demo boardshop to an existing database
- `add_mountain_bikes.py` — adds demo mountain bikes to selected existing sample shops
- `database/` — table definitions, sample data, and reservation triggers
- `rental_interface.py` and `table_actions.py` — admin pages and database actions
- `customer_routes.py` and `customer_service.py` — customer pages and their database logic
- `templates/` and `static/` — HTML, CSS, and JavaScript (`static/vendor/flatpickr` is the calendar library)
- `tests/` — unit tests: `python -m unittest discover tests`
- `requirements.txt` — Python packages
