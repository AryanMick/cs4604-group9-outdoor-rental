"""Verify the live MySQL database; every trial mutation is rolled back."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

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
            assert sum(counts.values()) == 300
            checks.append("All 10 base tables have their expected counts (300 total rows)")

            primary_keys = scalar(
                cursor,
                """SELECT COUNT(*) FROM information_schema.table_constraints
                   WHERE constraint_schema=%s AND constraint_type='PRIMARY KEY'""",
                (database,),
            )
            assert primary_keys == 10
            checks.append("Every base table has a primary key")

            foreign_keys = scalar(
                cursor,
                """SELECT COUNT(*) FROM information_schema.table_constraints
                   WHERE constraint_schema=%s AND constraint_type='FOREIGN KEY'""",
                (database,),
            )
            assert foreign_keys == 9
            checks.append("All 9 intended foreign keys exist")

            unique_constraints = scalar(
                cursor,
                """SELECT COUNT(*) FROM information_schema.table_constraints
                   WHERE constraint_schema=%s AND constraint_type='UNIQUE'""",
                (database,),
            )
            assert unique_constraints == 4
            checks.append("All 4 intended single-column unique constraints exist")

            check_constraints = scalar(
                cursor,
                """SELECT COUNT(*) FROM information_schema.table_constraints
                   WHERE constraint_schema=%s AND constraint_type='CHECK'
                     AND enforced='YES'""",
                (database,),
            )
            assert check_constraints == 19
            checks.append("All 19 CHECK constraints exist and are enforced")

            orphan_queries = (
                "SELECT COUNT(*) FROM rental_equipment c LEFT JOIN business p ON p.business_id=c.business_id WHERE p.business_id IS NULL",
                "SELECT COUNT(*) FROM reservation c LEFT JOIN rental_equipment p ON p.equipment_id=c.equipment_id WHERE p.equipment_id IS NULL",
                "SELECT COUNT(*) FROM reservation c LEFT JOIN customer p ON p.customer_id=c.customer_id WHERE p.customer_id IS NULL",
                "SELECT COUNT(*) FROM payment c LEFT JOIN reservation p ON p.reservation_id=c.reservation_id WHERE p.reservation_id IS NULL",
                "SELECT COUNT(*) FROM manager c LEFT JOIN business p ON p.business_id=c.business_id WHERE p.business_id IS NULL",
                "SELECT COUNT(*) FROM employee c LEFT JOIN manager p ON p.manager_id=c.manager_id WHERE p.manager_id IS NULL",
                "SELECT COUNT(*) FROM defines_access c LEFT JOIN admin p ON p.admin_id=c.admin_id WHERE p.admin_id IS NULL",
                "SELECT COUNT(*) FROM defines_access c LEFT JOIN employee p ON p.employee_id=c.employee_id WHERE p.employee_id IS NULL",
                "SELECT COUNT(*) FROM admin_privileges c LEFT JOIN admin p ON p.admin_id=c.admin_id WHERE p.admin_id IS NULL",
            )
            assert all(scalar(cursor, query) == 0 for query in orphan_queries)
            checks.append("All 9 foreign-key relationships are free of orphan rows")

            unpaid = scalar(
                cursor,
                """SELECT COUNT(*) FROM reservation r
                   LEFT JOIN payment p ON p.reservation_id=r.reservation_id
                   WHERE p.payment_id IS NULL""",
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
                    AND a.status <> 'CANCELLED'
                    AND b.status <> 'CANCELLED'
                    AND a.checkout_date < b.due_date
                    AND b.checkout_date < a.due_date""",
            )
            assert overlaps == 0
            checks.append("Sample reservations do not overlap for the same equipment")

            assert scalar(cursor, "SELECT COUNT(*) FROM payment WHERE payment_date > '2026-10-21'") == 0
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

        trials = (
            ("Duplicate primary key rejected", 1062,
             "INSERT INTO business (business_id,business_name,address) VALUES (1,'Duplicate','Test address')"),
            ("Orphan foreign key rejected", 1452,
             "INSERT INTO rental_equipment (equipment_id,equipment_type,status,business_id) VALUES (9001,'Test tent','AVAILABLE',9999)"),
            ("Due date before checkout rejected", 3819,
             "INSERT INTO reservation (reservation_id,equipment_id,customer_id,status,checkout_date,due_date) VALUES (9001,1,1,'RESERVED','2026-12-04','2026-12-01')"),
            ("Second payment for one reservation rejected", 1062,
             "INSERT INTO payment (payment_id,reservation_id,amount,payment_date) VALUES (9001,1,10.00,'2026-10-01')"),
            ("Negative payment rejected", 3819,
             "INSERT INTO payment (payment_id,reservation_id,amount,payment_date) VALUES (9001,31,-10.00,'2026-10-21')"),
            ("Duplicate customer email rejected", 1062,
             "INSERT INTO customer (customer_id,first_name,last_name,email) VALUES (9001,'Test','Person','AlexCarter@gmail.com')"),
            ("Missing required manager rejected", 1048,
             "INSERT INTO employee (employee_id,first_name,last_name,email,manager_id) VALUES (9001,'Test','Person','TestPerson@gmail.com',NULL)"),
            ("Invalid equipment status rejected", 3819,
             "INSERT INTO rental_equipment (equipment_id,equipment_type,status,business_id) VALUES (9001,'Test tent','UNKNOWN',1)"),
            ("Invalid reservation status rejected", 3819,
             "INSERT INTO reservation (reservation_id,equipment_id,customer_id,status,checkout_date,due_date) VALUES (9001,1,1,'UNKNOWN','2026-12-01','2026-12-04')"),
            ("Duplicate access assignment rejected", 1062,
             "INSERT INTO defines_access (admin_id,employee_id) VALUES (1,1)"),
            ("Duplicate privilege assignment rejected", 1062,
             "INSERT INTO admin_privileges (admin_id,privilege) VALUES (1,'VIEW_RESERVATIONS')"),
            ("Blank privilege rejected", 3819,
             "INSERT INTO admin_privileges (admin_id,privilege) VALUES (1,'   ')"),
            ("Deletion of referenced rental history rejected", 1451,
             "DELETE FROM rental_equipment WHERE equipment_id=1"),
        )
        for label, expected_code, statement in trials:
            try:
                with connection.cursor() as cursor:
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
                "The schema does not enforce reservation overlap exclusion; the sample dataset was checked for overlaps.",
                "The browser interface is local and read-only; use MySQL Workbench for authorized edits.",
            ],
        }
        destination = Path(__file__).resolve().with_name("verification_results.json")
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return report
    finally:
        connection.close()


if __name__ == "__main__":
    verify()
