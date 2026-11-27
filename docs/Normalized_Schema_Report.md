# Outdoor Equipment Rental Management System

CS4604 — Introduction to Database Systems  
Group 9  
Aryan Bhowmick, Tanner Fitzgerald, John Hewitt II, Timothy Peace  
Contact: johnh95@vt.edu  
Schema revision: final submission

## Project

The database keeps track of outdoor rental businesses, equipment, customers, reservations, payments, staff, administrators, login accounts, and shopping carts. It uses MySQL 8.4 with InnoDB tables. The local browser interface is written in Python 3 with Flask and connects through PyMySQL. It has four roles: customers, employees, managers, and administrators.

## Changes from the original schema

- Equipment is referenced from RESERVATION, so one item can have many reservations over time. BusinessID was removed from RESERVATION because the equipment already identifies the business.
- PAYMENT no longer points at a reservation. RESERVATION has a nullable payment_id, so one payment can cover several reservations (a multi-item checkout) and a reservation can exist unpaid.
- Equipment now has a description, a rate and rate unit (HOUR or DAY), and an image path.
- Checkout, due, and payment times are DATETIME values on a 30-minute grid. Payments keep only the last four card digits.
- Reservation status is RESERVED, RETURNED, or CANCELLED.
- Email addresses and passwords moved out of CUSTOMER, MANAGER, and EMPLOYEE into one AUTH_ACCOUNT table that links to exactly one person row according to its role (CUSTOMER, EMPLOYEE, MANAGER, ADMIN).
- CART and CART_ITEM were added for the customer checkout flow. A customer has at most one cart, and an item can appear in a cart once.
- BusinessID was removed from EMPLOYEE (found through the manager) and Man_ID was removed from DEFINES_ACCESS (found through EMPLOYEE).
- ADMIN_PRIVILEGES has a composite key of admin_id and privilege.

Assumptions: one manager per employee, and one manager per business is enough for the interface. A payment's amount is the total charged for its reservations; no per-reservation price is stored.

## Relational schema

PK means primary key, FK means foreign key, and UQ means unique.

```text
BUSINESS(business_id PK, business_name, address)

RENTAL_EQUIPMENT(equipment_id PK, equipment_type, description, rate, rate_unit,
  image_url, status, business_id FK -> BUSINESS)

CUSTOMER(customer_id PK, first_name, last_name)

PAYMENT(payment_id PK, amount, payment_date, card_last4)

RESERVATION(reservation_id PK, equipment_id FK -> RENTAL_EQUIPMENT,
  customer_id FK -> CUSTOMER, payment_id FK -> PAYMENT NULL,
  status, checkout_date, due_date)

MANAGER(manager_id PK, first_name, last_name, business_id FK -> BUSINESS)

EMPLOYEE(employee_id PK, first_name, last_name, manager_id FK -> MANAGER)

ADMIN(admin_id PK, first_name, last_name)

DEFINES_ACCESS(admin_id FK -> ADMIN, employee_id FK -> EMPLOYEE,
  PK(admin_id, employee_id))

ADMIN_PRIVILEGES(admin_id FK -> ADMIN, privilege, PK(admin_id, privilege))

AUTH_ACCOUNT(account_id PK, email UQ, password_hash, role,
  customer_id FK/UQ NULL, employee_id FK/UQ NULL,
  manager_id FK/UQ NULL, admin_id FK/UQ NULL)

CART(cart_id PK, customer_id FK/UQ -> CUSTOMER, created_at)

CART_ITEM(cart_item_id PK, cart_id FK -> CART, equipment_id FK -> RENTAL_EQUIPMENT,
  start_at, end_at, UQ(cart_id, equipment_id))
```

The diagram is in [Corrected_Relational_Schema.svg](Corrected_Relational_Schema.svg) (source: `Corrected_Relational_Schema.mmd`).

## Constraints and rules

The database has 13 base tables, 13 primary keys, 16 foreign keys, 7 unique constraints, and 26 enforced CHECK constraints. The CHECKs forbid blank text, non-positive rates and payments, invalid statuses, rate units and roles, due times not after checkout times, times off the 30-minute grid, non-numeric card digits, and an AUTH_ACCOUNT row linked to anything other than the one person row its role requires. Foreign keys reject missing parents and deletion of referenced rows.

Two triggers on RESERVATION (`database/03_triggers.sql`) enforce rules CHECK constraints cannot express: a RESERVED row may not overlap another RESERVED row for the same equipment, equipment must be AVAILABLE, and day-rate items must be rented in whole 24-hour days. The interface re-checks these rules before booking so users get readable errors.

## Normalization

**1NF:** Every column holds one atomic value. Privileges are one row each, and cart contents are rows in CART_ITEM rather than lists. The address is a single display value because it is never searched by part.

**2NF:** Entity tables have single-column keys. DEFINES_ACCESS and ADMIN_PRIVILEGES have composite keys with no non-key attributes (privilege is part of the key), so no partial dependencies exist. CART_ITEM uses a surrogate key with a unique (cart_id, equipment_id) candidate key; its dates depend on the whole item.

**3NF:** Non-key attributes depend only on the key. Business is derived from equipment (RESERVATION) or manager (EMPLOYEE), and the manager of an access grant is derived from EMPLOYEE, so none of them are duplicated. A payment's amount and date depend on the payment, not on any reservation. Credentials live in AUTH_ACCOUNT rather than being repeated across four person tables. Totals, revenue, and counts shown in the interface are computed by queries (`reports.py`) and never stored.

**Trade-off:** Because no price is stored per reservation, revenue in the aggregate reports is estimated from the equipment's current rate and the reserved duration; the exact amount charged is available per payment. Storing a price per reservation would be the extension if historical accuracy under rate changes mattered.

Views `reservation_details` and `employee_details` expose the joined data without duplicating it.

## Interface and aggregates

- **Customers:** browse equipment, build a cart, check out with a card (last four digits stored), and view their rentals with a personal summary (rental count, estimated spend, status counts).
- **Employees and managers:** see rentals for their own business, business-wide aggregates (rentals by status, estimated revenue, top equipment), and check out a customer for in-store rentals. Managers also manage their equipment and staff.
- **Administrators:** browse every table, add, edit, and delete rows where permitted, and view system-wide aggregates (totals, revenue by business, status counts, top equipment, staff per business).

All write actions are role-checked and protected by a CSRF token.

## Sample data

| Table | Records |
|---|---:|
| business | 21 |
| rental_equipment | 50 |
| customer | 31 |
| reservation | 40 |
| payment | 30 |
| manager | 20 |
| employee | 20 |
| admin | 20 |
| defines_access | 40 |
| admin_privileges | 40 |
| cart | 0 |
| cart_item | 0 |
| auth_account | 91 |
| Total | 403 |

Names, addresses, and gmail.com addresses are synthetic. `verify_database.py` checks exact row counts, key and constraint counts, orphan rows, the triggers, and about two dozen rejected-invalid-data trials; every trial change is rolled back, and results are written to `submission/verification_results.json`.

## Screenshots

The [submission screenshots](../submission/screenshots/) document the browser interface.
