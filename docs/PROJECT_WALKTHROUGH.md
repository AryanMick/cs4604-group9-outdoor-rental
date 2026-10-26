# Understanding and presenting the Group 9 project

Read this alongside the [normalization report](Normalized_Schema_Report.md) and [schema diagram](Corrected_Relational_Schema.svg). The database already contains sample data; normal use does **not** require setup again.

## What the tools do

MySQL 8.4 is the database management system (DBMS): it stores records, executes SQL, and enforces constraints. SQL defines tables and reads or changes records. Python is the language for setup, verification, and interface scripts.

Flask is the Python framework receiving browser requests. PyMySQL is the driver connecting Python to MySQL. Jinja combines HTML templates with query results; CSS styles pages. Chrome displays them. VS Code edits project files; saving a file does not execute SQL or start MySQL.

## How the project was implemented

First, the relational design was corrected around explicit business assumptions: one equipment item per reservation, one assigned manager per employee, and zero or one payment per reservation. The corrected tables satisfy third normal form (3NF) under those assumptions.

Next, MySQL 8.4 was installed and the connection settings were provided privately. `db_tools.py setup` connects to the server, creates the configured database if absent, and checks that it contains no table or view objects. It then executes [01_schema.sql](../database/01_schema.sql) to create tables, constraints, indexes, and views. Finally, it executes [02_sample_data.sql](../database/02_sample_data.sql) to insert the 300 sample records and commits the data transaction.

MySQL automatically commits these schema-definition operations, called DDL. A rollback cannot undo already-created tables. If schema setup fails, partial objects can remain; if sample loading fails, its inserts are rolled back but the schema remains. Setup refuses an already-populated database instead of resetting it. Use `status` for the existing installation.

The browser interface and verification scripts were then connected to MySQL. SQL files contain instructions; MySQL holds the database. Editing an SQL file requires executing the appropriate SQL to apply changes. Closing Chrome does not delete committed records.

## The ten tables and their relationships

A row represents a record; a column describes an attribute. Expected sample counts:

| Table | Purpose | Rows |
|---|---|---:|
| `business` | Rental business name and address | 20 |
| `rental_equipment` | Individual equipment items and their owning business | 40 |
| `customer` | Customer names and email addresses | 30 |
| `reservation` | A customer's booking of one equipment item, dates, and status | 40 |
| `payment` | An amount and payment date for a reservation | 30 |
| `manager` | Managers and their assigned businesses | 20 |
| `employee` | Employees and their assigned managers | 20 |
| `admin` | Administrator records | 20 |
| `defines_access` | Administrator-to-employee access assignments | 40 |
| `admin_privileges` | Individual privileges assigned to administrators | 40 |
| **Total** | **Ten base tables** | **300** |

A primary key (PK) uniquely identifies a row. Eight entity tables use an `INT AUTO_INCREMENT` ID, which MySQL generates when an insert omits the ID. `defines_access` instead uses `(admin_id, employee_id)` as its composite PK, preventing duplicate pairs. `admin_privileges` uses `(admin_id, privilege)`, allowing several distinct privileges per administrator.

A foreign key (FK) requires an existing parent, such as a reservation’s customer. These relationships also prevent deleting a parent record while other rows reference it. There are ten PKs, nine FKs, four additional unique constraints, and nineteen enforced CHECK constraints. Customer, manager, and employee emails are unique within their respective tables; the fourth unique constraint prevents two payments for one reservation.

`INT` stores whole-number IDs; `VARCHAR` stores text up to a stated length; `DATE` stores calendar dates. `DECIMAL(10,2)` stores payment amounts exactly with up to ten digits total, including two decimal places. `NOT NULL` prevents missing values, while `CHECK (TRIM(...) <> '')` also prevents empty or spaces-only text. Other checks restrict statuses, require positive payments, and require due dates after checkout dates.

## Why the design is normalized

First normal form (1NF) means each field holds one value: privileges occupy separate rows instead of a comma-separated list. The address is one display value under this project's requirements. Second normal form (2NF) removes dependencies on only part of a composite key; the two composite-key tables have no non-key attributes.

For 3NF, facts should depend on a candidate key without an extra dependency between non-key fields. Reservation no longer stores a redundant business ID: reservation → equipment → business supplies it. Employee no longer repeats its manager's business ID: employee → manager → business supplies it. Access assignments similarly derive the supervisor through the employee instead of repeating a manager ID. This reduces conflicting copies when information changes.

Equipment IDs in reservation allow repeated historical bookings. Payment’s unique reservation reference allows zero or one payment. Multiple items per booking would require a reservation-item table.

## Reading actual SQL

Actual schema excerpt; do not recreate the existing table.

```sql
CREATE TABLE business (
    business_id INT AUTO_INCREMENT PRIMARY KEY,
    business_name VARCHAR(120) NOT NULL,
    address VARCHAR(255) NOT NULL,
    CONSTRAINT business_name_not_blank CHECK (TRIM(business_name) <> ''),
    CONSTRAINT business_address_not_blank CHECK (TRIM(address) <> '')
) ENGINE=InnoDB;
```

The first line names the table. The second creates its automatic integer identifier. The next two require a name (maximum 120 characters) and address (maximum 255). The named checks reject blank values after trimming spaces. The final line selects InnoDB, supporting transactions and foreign keys. The semicolon ends the statement.

This insert illustrates the first already-loaded business record. **Do not run it again against the existing database:** ID 1 already exists.

```sql
INSERT INTO business (business_id, business_name, address)
VALUES (1, 'Blue Ridge Outfitters',
        '101 Demonstration Trail, Blacksburg, VA 24060');
```

`INSERT INTO` names the table and columns; `VALUES` supplies values. Parent records load before dependent records.

Run these read-only examples in a **MySQL client SQL tab**, selecting `outdoor_rental_group9`:

```sql
SELECT customer_id, first_name, last_name
FROM customer
WHERE customer_id = 1;

SELECT r.reservation_id, c.first_name, c.last_name, r.due_date
FROM reservation AS r
JOIN customer AS c ON c.customer_id = r.customer_id
ORDER BY r.reservation_id;

SELECT r.reservation_id
FROM reservation AS r
LEFT JOIN payment AS p ON p.reservation_id = r.reservation_id
WHERE p.payment_id IS NULL;
```

`SELECT` chooses columns; `WHERE` filters rows. `JOIN` matches related rows using their keys. An inner join returns matching pairs; the left join retains reservations even when payment is missing. Filtering those missing matches finds unpaid reservations.

`reservation_details` and `employee_details` are views, not additional base tables. They are saved queries presenting joined information without storing another copy. The reservation view uses a left join so unpaid bookings remain visible.

## What happens when a browser page opens

For `/table/customer?page=2`, Flask first checks `customer` against the fixed allowed table/view names. The connection helper reads private configuration and opens PyMySQL's connection. The app queries real server metadata and counts all ten tables, then counts customers to calculate pagination.

It executes `SELECT *` with `ORDER BY 1, 2`, a parameterized `LIMIT` of 20, and an offset of 20 for page two. Because there are 30 customers, that page contains the remaining ten. Jinja renders the results into HTML, CSS supplies the appearance, and Chrome displays it. The connection closes in a `finally` block. Invalid names return 404; connection failures display an error with HTTP 503. The allowlist limits table selection; it is not a claim that every security concern is solved.

## Commands and files to recognize

Run these Python commands in a **terminal**, from the project folder. Use `python3` if required. Activate your environment separately in every new terminal. The `.venv` commands below describe creating and using an environment for a fresh installation; an existing environment can be reused from its own location.

| Terminal command | Meaning |
|---|---|
| `python -m venv .venv` | Create a local Python environment once |
| `source .venv/bin/activate` | Activate it on macOS/Linux |
| `.venv\Scripts\Activate.ps1` | Activate it in Windows PowerShell |
| `python -m pip install -r requirements.txt` | Install Flask and PyMySQL dependencies |
| `python db_tools.py status` | Inspect live connection and counts |
| `python db_tools.py setup` | First-time setup on an absent/empty database only |
| `python rental_interface.py` | Start the local interface if it is stopped |
| `python verify_database.py` | Run live verification and save results |
| `python -m unittest discover -s tests -v` | Run four mocked interface tests |

Once started, the interface runs on port 5001; open `http://127.0.0.1:5001`. MySQL normally listens on port 3306. A private `db_config.json` supplies host, port, database, user, and password. `GROUP9_DB_CONFIG` can select another configuration path. Keep credentials private.

`database/` contains executable SQL; `docs/` explains the design. `templates/` contains Jinja pages; `static/` contains CSS. The three root Python scripts handle setup/status, the interface, and verification. `tests/` contains mocked route checks. `submission/` contains the PDF, screenshots, and `verification_results.json`.

Live verification has 25 checks covering counts, constraints, relationships, sample overlaps, and rejected invalid operations. Trial changes are rolled back. The four unit tests mock database access and check dashboard output, pagination, unknown names, and error display; they do not prove live MySQL behavior.

## Presenting the project

Adapt this 60–90 second explanation to your understanding and contributions:

> Our project models an outdoor equipment rental business using ten related MySQL tables. The design separates customers, equipment, bookings, payments, and staff. We corrected repeated business and manager references so those facts can be obtained through relationships, which supports third normal form under our assumptions. Primary keys identify records, foreign keys keep relationships valid, and checks reject invalid dates, statuses, and amounts. The database contains 300 synthetic sample records. A Python Flask interface connects through PyMySQL and displays live counts and paginated tables. Joined views make related information easier to read. Verification checks the live database and rolls back trial changes, while separate mocked tests check the browser routes. The current interface is read-only, and the model assumes one item per reservation and at most one payment.

Demo order: show dashboard counts, customer pagination, the SQL schema, `reservation_details`, then verification results.

Five likely questions:

1. **Can users edit in Chrome?** No. Use an authorized SQL client, then refresh the page.
2. **Does `admin` provide login security?** No. These are modeled records; authentication and permission enforcement are outside this implementation.
3. **Does MySQL prevent overlapping bookings?** This schema does not. Verification confirms only that the sample bookings do not overlap.
4. **Can one booking contain several items or payments?** Currently one item and zero or one payment; broader requirements need schema changes.
5. **Why remove employee's business ID?** Its assigned manager determines the business, so a join supplies it without a conflicting duplicate.
