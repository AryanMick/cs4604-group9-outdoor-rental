# Outdoor Equipment Rental Management System

CS4604 — Group 9. MySQL 8.4, a Python/Flask browser interface, ten normalized
tables, two joined views, and 300 synthetic sample records.

## Start on your computer

1. [Download the latest GitHub ZIP](https://github.com/AryanMick/cs4604-group9-outdoor-rental/archive/refs/heads/main.zip) and extract it into a **new folder**. An older copy used PostgreSQL; use this MySQL version with `start.py`.
2. Install [Python 3.10 or newer](https://www.python.org/downloads/) and [MySQL Community 8.4](https://dev.mysql.com/downloads/mysql/8.4.html). On Windows, enable Python's **Add Python to PATH** option. Start the MySQL server and keep the username and password you chose during installation.
3. Open Command Prompt, PowerShell, or Terminal in the extracted folder containing `start.py`. Run:

```sh
python start.py
```

On macOS/Linux, use `python3 start.py` if needed. The launcher creates its own
`.venv`, installs the Python packages, and asks for your MySQL connection settings
on first launch. Press Enter to accept a default; enter your own MySQL password
when asked (it stays hidden). Settings are saved locally in private
`db_config.json`.

The launcher creates the database and loads the sample records if the database
is absent or empty. It preserves an existing complete database and refuses a
partial schema. It does not install MySQL or change MySQL accounts/passwords.

Open [http://127.0.0.1:5001](http://127.0.0.1:5001). The dashboard shows the actual
MySQL connection and live table counts. Select a table or view to browse 20 rows
per page. The browser interface is read-only.

Stop with **Ctrl+C**. Next time, start MySQL and run the same `python start.py`
command from the same folder. Your database data stays saved.

## If startup fails

- **Windows cannot find `python`:** reopen the terminal after installing Python with PATH enabled, or try `py start.py`. You do not need `python3`, `source`, or a manual environment activation command on Windows.
- **Errors mention PostgreSQL or `psycopg2`:** you have the older project. Download the latest ZIP into a fresh folder.
- **Package installation fails:** check your internet connection and rerun the launcher.
- **MySQL connection refused:** install/start MySQL Community 8.4. On Windows, check its service in the Services app; on macOS/Linux, start it using your installation's server controls.
- **Access denied:** edit your local `db_config.json` to use your own MySQL credentials. The account must be allowed to create the project database and its tables. The launcher cannot guess or reset your MySQL password.
- **Port 5001 is occupied:** stop the other copy of the interface before starting again.

Do not share `db_config.json` or `.venv`; each teammate runs the launcher on their
own computer.

## Check or edit the database

The dashboard's connection panel and counts are live queries. For a SQL shell,
open MySQL Workbench with the settings in your local `db_config.json`, or run
this command if the MySQL command-line client is on your PATH:

```sh
mysql -h 127.0.0.1 -P 3306 -u root -p outdoor_rental_group9
```

Use your configured host, port, username, and database if different. Enter your
own password when prompted. For example:

```sql
SELECT COUNT(*) FROM customer;
INSERT INTO customer (first_name, last_name, email)
VALUES ('Sam', 'Lee', 'SamLee@gmail.com');
DELETE FROM customer WHERE email = 'SamLee@gmail.com';
```

Refresh the browser after changes. MySQL rejects deleting a customer linked to
a reservation.

## Project materials

- [Schema SQL](database/01_schema.sql) and [sample data](database/02_sample_data.sql)
- [Relational diagram](docs/Corrected_Relational_Schema.svg) and [normalization report](docs/Normalized_Schema_Report.md)
- [Submission PDF](submission/Deliverables.pdf), [verification results](submission/verification_results.json), and [17 screenshots](submission/screenshots/)
- Interface: `rental_interface.py`, `templates/`, and `static/`

For development checks after the launcher has installed dependencies, use
`.venv\Scripts\python.exe` on Windows or `.venv/bin/python` on macOS/Linux:

```text
<venv-python> -m unittest discover -s tests -v
<venv-python> db_tools.py status
<venv-python> verify_database.py
```

Replace `<venv-python>` with the path above. Tests need no MySQL. The verification
script checks the original sample counts and constraints against MySQL, rolls
back trial changes, and saves `submission/verification_results.json`.
