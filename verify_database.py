"""Verify the live MySQL database; every trial mutation is rolled back."""
from __future__ import annotations

from datetime import datetime
import json

import pymysql

import db_tools


def scalar(cursor, statement: str, parameters=None):
    cursor.execute(statement, parameters)
    return cursor.fetchone()[0]


def verify() -> dict:
    checks = []
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION(), DATABASE()")
            version, database = cursor.fetchone()

            counts = {}
            for table in db_tools.TABLES:
                counts[table] = scalar(cursor, f"SELECT COUNT(*) FROM `{table}`")
            assert counts == db_tools.EXPECTED_COUNTS
            assert sum(counts.values()) == 301
            checks.append("All 12 base tables have their expected counts (301 total rows)")

            primary_keys = scalar(
                cursor,
                """SELECT COUNT(*) FROM information_schema.table_constraints
                   WHERE constraint_schema=%s AND constraint_type='PRIMARY KEY'""",
                (database,),
            )
            assert primary_keys == 12
            checks.append("Every base table has a primary key")

            foreign_keys = scalar(
                cursor,
                """SELECT COUNT(*) FROM information_schema.table_constraints
                   WHERE constraint_schema=%s AND constraint_type='FOREIGN KEY'""",
                (database,),
            )
            assert foreign_keys == 12
            checks.append("All 12 intended foreign keys exist")

            unique_constraints = scalar(
                cursor,
                """SELECT COUNT(*) FROM information_schema.table_constraints
                   WHERE constraint_schema=%s AND constraint_type='UNIQUE'""",
                (database,),
            )
            assert unique_constraints == 5
            checks.append("All 5 intended unique constraints exist")

            check_constraints = scalar(
                cursor,
                """SELECT COUNT(*) FROM information_schema.table_constraints
                   WHERE constraint_schema=%s AND constraint_type='CHECK'
                     AND enforced='YES'""",
                (database,),
            )
            assert check_constraints == 26
            checks.append("All 26 CHECK constraints exist and are enforced")

            triggers = scalar(
                cursor,
                "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=%s AND event_object_table='reservation'",
                (database,),
            )
            assert triggers == 2
            checks.append("Both reservation overlap triggers exist")

            orphan_queries = (
                "SELECT COUNT(*) FROM rental_equipment c LEFT JOIN business p ON p.business_id=c.business_id WHERE p.business_id IS NULL",
                "SELECT COUNT(*) FROM reservation c LEFT JOIN rental_equipment p ON p.equipment_id=c.equipment_id WHERE p.equipment_id IS NULL",
                "SELECT COUNT(*) FROM reservation c LEFT JOIN customer p ON p.customer_id=c.customer_id WHERE p.customer_id IS NULL",
                "SELECT COUNT(*) FROM reservation c LEFT JOIN payment p ON p.payment_id=c.payment_id WHERE c.payment_id IS NOT NULL AND p.payment_id IS NULL",
                "SELECT COUNT(*) FROM cart c LEFT JOIN customer p ON p.customer_id=c.customer_id WHERE p.customer_id IS NULL",
                "SELECT COUNT(*) FROM cart_item c LEFT JOIN cart p ON p.cart_id=c.cart_id WHERE p.cart_id IS NULL",
                "SELECT COUNT(*) FROM cart_item c LEFT JOIN rental_equipment p ON p.equipment_id=c.equipment_id WHERE p.equipment_id IS NULL",
                "SELECT COUNT(*) FROM manager c LEFT JOIN business p ON p.business_id=c.business_id WHERE p.business_id IS NULL",
                "SELECT COUNT(*) FROM employee c LEFT JOIN manager p ON p.manager_id=c.manager_id WHERE p.manager_id IS NULL",
                "SELECT COUNT(*) FROM defines_access c LEFT JOIN admin p ON p.admin_id=c.admin_id WHERE p.admin_id IS NULL",
                "SELECT COUNT(*) FROM defines_access c LEFT JOIN employee p ON p.employee_id=c.employee_id WHERE p.employee_id IS NULL",
                "SELECT COUNT(*) FROM admin_privileges c LEFT JOIN admin p ON p.admin_id=c.admin_id WHERE p.admin_id IS NULL",
            )
            assert all(scalar(cursor, query) == 0 for query in orphan_queries)
            checks.append("All 12 foreign-key relationships are free of orphan rows")

            unpaid = scalar(
                cursor,
                "SELECT COUNT(*) FROM reservation WHERE payment_id IS NULL",
            )
            assert unpaid > 0
            checks.append("Reservations can exist without a payment")

            repeated_equipment = scalar(
                cursor,
                """SELECT COUNT(*) FROM (
                       SELECT equipment_id FROM reservation
                       GROUP BY equipment_id HAVING COUNT(*) > 1
                   ) AS repeated""",
            )
            assert repeated_equipment > 0
            checks.append("Equipment can retain multiple historical reservations")

            overlaps = scalar(
                cursor,
                """SELECT COUNT(*) FROM reservation a
                   JOIN reservation b
                     ON a.equipment_id=b.equipment_id
                    AND a.reservation_id < b.reservation_id
                    AND a.status = 'RESERVED'
                    AND b.status = 'RESERVED'
                    AND a.checkout_date < b.due_date
                    AND b.checkout_date < a.due_date""",
            )
            assert overlaps == 0
            checks.append("Sample reservations do not overlap for the same equipment")

            assert scalar(cursor, "SELECT COUNT(*) FROM payment WHERE payment_date >= '2026-10-22'") == 0
            checks.append("Sample payments respect the 2026-10-21 snapshot date")

            sample_emails = scalar(
                cursor,
                """SELECT
                     (SELECT COUNT(*) FROM customer WHERE BINARY email <> BINARY CONCAT(first_name,last_name,'@gmail.com')) +
                     (SELECT COUNT(*) FROM manager WHERE BINARY email <> BINARY CONCAT(first_name,last_name,'@gmail.com')) +
                     (SELECT COUNT(*) FROM employee WHERE BINARY email <> BINARY CONCAT(first_name,last_name,'@gmail.com'))""",
            )
            assert sample_emails == 0
            checks.append("Every sample email uses the person’s name and gmail.com")
        connection.rollback()

        equipment_columns = "equipment_id,equipment_type,description,rate,rate_unit,status,business_id"
        reservation_columns = "reservation_id,equipment_id,customer_id,status,checkout_date,due_date"
        trials = (
            ("Duplicate primary key rejected", 1062,
             "INSERT INTO business (business_id,business_name,address) VALUES (1,'Duplicate','Test address')"),
            ("Orphan foreign key rejected", 1452,
             f"INSERT INTO rental_equipment ({equipment_columns}) VALUES (9001,'Test tent','A tent',10.00,'DAY','AVAILABLE',9999)"),
            ("Due date before checkout rejected", 3819,
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,1,1,'RESERVED','2026-12-04 09:00:00','2026-12-01 09:00:00')"),
            ("Reservation times off the 30-minute grid rejected", 3819,
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,1,1,'RESERVED','2027-01-04 09:15:00','2027-01-05 09:15:00')"),
            ("Overlapping reservation rejected by trigger", 1644,
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,1,1,'RESERVED','2026-11-02 09:00:00','2026-11-03 09:00:00')"),
            ("Reservation of equipment under maintenance rejected by trigger", 1644,
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,35,1,'RESERVED','2027-01-04 09:00:00','2027-01-04 10:00:00')"),
            ("Partial-day rental of a day-rate item rejected by trigger", 1644,
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,1,1,'RESERVED','2027-01-04 09:00:00','2027-01-04 21:00:00')"),
            ("Reinstating a cancelled reservation over a booked time rejected by trigger", 1644,
             (f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,1,1,'CANCELLED','2026-11-02 09:00:00','2026-11-03 09:00:00')",
              "UPDATE reservation SET status='RESERVED' WHERE reservation_id=9001")),
            ("Negative payment rejected", 3819,
             "INSERT INTO payment (payment_id,amount,payment_date,card_last4) VALUES (9001,-10.00,'2026-10-21 08:00:00','4242')"),
            ("Non-numeric card digits rejected", 3819,
             "INSERT INTO payment (payment_id,amount,payment_date,card_last4) VALUES (9001,10.00,'2026-10-21 08:00:00','42A2')"),
            ("Reservation with an unknown payment rejected", 1452,
             "INSERT INTO reservation (reservation_id,equipment_id,customer_id,payment_id,status,checkout_date,due_date) VALUES (9001,1,1,9999,'RESERVED','2027-01-04 09:00:00','2027-01-05 09:00:00')"),
            ("Zero equipment rate rejected", 3819,
             f"INSERT INTO rental_equipment ({equipment_columns}) VALUES (9001,'Test tent','A tent',0,'DAY','AVAILABLE',1)"),
            ("Invalid equipment rate unit rejected", 3819,
             f"INSERT INTO rental_equipment ({equipment_columns}) VALUES (9001,'Test tent','A tent',10.00,'WEEK','AVAILABLE',1)"),
            ("Equipment without a description rejected", 1364,
             "INSERT INTO rental_equipment (equipment_id,equipment_type,rate,rate_unit,status,business_id) VALUES (9001,'Test tent',10.00,'DAY','AVAILABLE',1)"),
            ("Second cart for one customer rejected", 1062,
             ("INSERT INTO cart (cart_id,customer_id) VALUES (9001,31)",
              "INSERT INTO cart (cart_id,customer_id) VALUES (9002,31)")),
            ("Same equipment twice in one cart rejected", 1062,
             ("INSERT INTO cart (cart_id,customer_id) VALUES (9001,31)",
              "INSERT INTO cart_item (cart_id,equipment_id,start_at,end_at) VALUES (9001,1,'2027-01-04 09:00:00','2027-01-05 09:00:00')",
              "INSERT INTO cart_item (cart_id,equipment_id,start_at,end_at) VALUES (9001,1,'2027-02-04 09:00:00','2027-02-05 09:00:00')")),
            ("Duplicate customer email rejected", 1062,
             "INSERT INTO customer (customer_id,first_name,last_name,email) VALUES (9001,'Test','Person','AlexCarter@gmail.com')"),
            ("Missing required manager rejected", 1048,
             "INSERT INTO employee (employee_id,first_name,last_name,email,manager_id) VALUES (9001,'Test','Person','TestPerson@gmail.com',NULL)"),
            ("Invalid equipment status rejected", 3819,
             f"INSERT INTO rental_equipment ({equipment_columns}) VALUES (9001,'Test tent','A tent',10.00,'DAY','UNKNOWN',1)"),
            ("Invalid reservation status rejected", 3819,
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,1,1,'UNKNOWN','2026-12-01 09:00:00','2026-12-04 09:00:00')"),
            ("Removed reservation status CHECKED_OUT rejected", 3819,
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,1,1,'CHECKED_OUT','2026-12-01 09:00:00','2026-12-04 09:00:00')"),
            ("Duplicate access assignment rejected", 1062,
             "INSERT INTO defines_access (admin_id,employee_id) VALUES (1,1)"),
            ("Duplicate privilege assignment rejected", 1062,
             "INSERT INTO admin_privileges (admin_id,privilege) VALUES (1,'VIEW_RESERVATIONS')"),
            ("Blank privilege rejected", 3819,
             "INSERT INTO admin_privileges (admin_id,privilege) VALUES (1,'   ')"),
            ("Deletion of referenced rental history rejected", 1451,
             "DELETE FROM rental_equipment WHERE equipment_id=1"),
        )
        for label, expected_code, statements in trials:
            if isinstance(statements, str):
                statements = (statements,)
            try:
                with connection.cursor() as cursor:
                    for statement in statements:
                        cursor.execute(statement)
            except pymysql.MySQLError as exc:
                assert exc.args[0] == expected_code, (
                    f"{label}: expected MySQL error {expected_code}, got {exc.args[0]}"
                )
                checks.append(label)
            else:
                raise AssertionError(f"{label}: invalid data was accepted")
            finally:
                connection.rollback()

        accepted = (
            ("Reservation of a free hourly time slot accepted",
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,5,1,'RESERVED','2027-01-04 09:00:00','2027-01-04 09:30:00')"),
            ("Back-to-back reservations accepted",
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,1,1,'RESERVED','2026-11-04 09:00:00','2026-11-05 09:00:00')"),
            ("Cancelled reservations do not block a time slot",
             f"INSERT INTO reservation ({reservation_columns}) VALUES (9001,16,1,'RESERVED','2026-10-28 09:00:00','2026-10-31 09:00:00')"),
        )
        for label, statement in accepted:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(statement)
                checks.append(label)
            finally:
                connection.rollback()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO rental_equipment ({equipment_columns}) VALUES (9001,'Test tent','A tent',10.00,'DAY','AVAILABLE',1)"
                )
                assert scalar(cursor, "SELECT image_url FROM rental_equipment WHERE equipment_id=9001") == "img/placeholder.jpg"
            checks.append("Equipment inserted without an image uses img/placeholder.jpg")
        finally:
            connection.rollback()

        with connection.cursor() as cursor:
            for table, expected in counts.items():
                assert scalar(cursor, f"SELECT COUNT(*) FROM `{table}`") == expected
        checks.append("All sample rows were preserved after verification")
        connection.rollback()

        report = {
            "verified_at": datetime.now().astimezone().isoformat(),
            "database": database,
            "dbms": f"MySQL {version}",
            "interface_language": "Python 3 / Flask",
            "total_rows": sum(counts.values()),
            "table_counts": counts,
            "checks_passed": len(checks),
            "checks": checks,
            "limits": [
                "Reservation overlap is enforced by database triggers (database/03_triggers.sql); the browser interface re-checks it before booking.",
                "The browser interface is local and read-only; use MySQL Workbench for authorized edits.",
            ],
        }
        destination = db_tools.PACKAGE / "submission" / "verification_results.json"
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return report
    finally:
        connection.close()


if __name__ == "__main__":
    verify()
