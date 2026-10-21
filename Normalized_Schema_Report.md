# Outdoor Equipment Rental Management System

CS4604 — Introduction to Database Systems  
Group 9  
Aryan Bhowmick, Tanner Fitzgerald, John Hewitt II, Timothy Peace  
Contact: johnh95@vt.edu  
Schema revision: October 21, 2026

## Project

The database keeps track of outdoor rental businesses, equipment, customers, reservations, payments, and staff. It uses PostgreSQL 15.14. The interface is written in Python 3 with Tkinter and connects through psycopg2.

## Changes to the original schema

- Move the equipment reference into RESERVATION. One equipment item can then have several reservations over time.
- Remove BusinessID from RESERVATION. The business is already identified by the equipment being rented.
- Store reservation_id in PAYMENT and make it unique. A reservation can have no payment or one payment.
- Remove BusinessID from EMPLOYEE. Each employee works for the business assigned to their manager.
- Remove Man_ID from DEFINES_ACCESS. In this version, the manager means the employee's supervisor, so it is found through EMPLOYEE.
- Give ADMIN_PRIVILEGES a composite primary key of admin_id and privilege. Each privilege goes in its own row.

The model assumes one equipment item per reservation and one assigned manager per employee. Managers and employees remain separate entity sets, following the original design. If a reservation must contain several items, it would need an extra reservation-item table. If the manager in DEFINES_ACCESS is meant to be someone other than the employee's supervisor, that access relationship would need to be changed.

## Relational schema

PK means primary key, FK means foreign key, and UQ means unique.

```text
BUSINESS(
  business_id PK, business_name, address
)

RENTAL_EQUIPMENT(
  equipment_id PK, equipment_type, status,
  business_id FK -> BUSINESS
)

CUSTOMER(
  customer_id PK, first_name, last_name, email UQ
)

RESERVATION(
  reservation_id PK, equipment_id FK -> RENTAL_EQUIPMENT,
  customer_id FK -> CUSTOMER, status, checkout_date, due_date
)

PAYMENT(
  payment_id PK, reservation_id FK/UQ -> RESERVATION,
  amount, payment_date
)

MANAGER(
  manager_id PK, first_name, last_name, email UQ,
  business_id FK -> BUSINESS
)

EMPLOYEE(
  employee_id PK, first_name, last_name, email UQ,
  manager_id FK -> MANAGER
)

ADMIN(
  admin_id PK, first_name, last_name
)

DEFINES_ACCESS(
  admin_id FK -> ADMIN, employee_id FK -> EMPLOYEE,
  PK(admin_id, employee_id)
)

ADMIN_PRIVILEGES(
  admin_id FK -> ADMIN, privilege,
  PK(admin_id, privilege)
)
```

## Data types and constraints

| Attributes | PostgreSQL type |
|---|---|
| Entity primary keys | INTEGER, generated identity |
| Foreign keys | INTEGER |
| First and last names | VARCHAR(80) |
| Business name | VARCHAR(120) |
| Address | VARCHAR(255) |
| Email | VARCHAR(254) |
| Equipment type and privilege | VARCHAR(60) |
| Status | VARCHAR(20) |
| Checkout, due, and payment dates | DATE |
| Payment amount | NUMERIC(10,2) |

All columns are required. Names, addresses, emails, equipment types, and privileges cannot be blank. Email is unique within each customer, manager, or employee table. A due date must be later than its checkout date, and a payment amount must be positive. Foreign keys reject records that refer to missing parents and prevent deleting a referenced parent.

Equipment status is AVAILABLE, MAINTENANCE, or RETIRED. AVAILABLE means the equipment is serviceable; its current booking is recorded separately in RESERVATION. Reservation status is RESERVED, CHECKED_OUT, RETURNED, or CANCELLED. The checkout date is the scheduled start of the rental.

## Normalization

**1NF:** Every column stores one value. Checkout and due dates are separate. Privileges are stored as individual rows rather than lists. The address is stored as one display value because this project does not search its individual parts.

**2NF:** The eight entity tables have single-column primary keys. The two relationship tables have composite keys and no non-key attributes that could depend on only part of a key.

**3NF:** The non-key attributes depend on a candidate key without an extra dependency between non-key attributes in the same table. The duplicated business IDs have been removed from RESERVATION and EMPLOYEE. The duplicated manager ID has been removed from DEFINES_ACCESS. These values can be found with joins. Under the business rules above, the ten tables satisfy 3NF.

Two views, reservation_details and employee_details, show those joined values without storing them again.

## Sample data

The dataset represents October 21, 2026. The names and addresses are fictional, and email addresses use example.com.

| Table | Records |
|---|---:|
| business | 20 |
| rental_equipment | 40 |
| customer | 30 |
| reservation | 40 |
| payment | 30 |
| manager | 20 |
| employee | 20 |
| admin | 20 |
| defines_access | 40 |
| admin_privileges | 40 |
| Total | 300 |

The database was tested for duplicate keys, missing foreign-key references, duplicate payments, invalid dates and statuses, negative amounts, and duplicate access and privilege assignments. The tests also confirmed that an unpaid reservation is allowed and that equipment can have more than one reservation over time.

The sample dates do not overlap for the same equipment item. Preventing future overlapping bookings is not enforced by this schema. Payment amounts are sample values because the original model does not include rental prices. The interface displays records and checks the connection; editing records and enforcing administrator permissions are outside this implementation.

## Screenshots

Add real screenshots of each populated table and the successful database connection before submitting. The README explains how to open the interface and select the tables.
