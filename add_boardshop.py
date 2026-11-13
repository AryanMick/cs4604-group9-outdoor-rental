"""Add the demo boardshop to an existing project database without replacing data."""
from __future__ import annotations

import db_tools

SHOP_NAME = "John's Boardshop"
SHOP_ADDRESS = "121 Demonstration Trail, Blacksburg, VA 24060"


def main() -> int:
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT business_id, address FROM business WHERE business_name=%s FOR UPDATE",
                (SHOP_NAME,),
            )
            shops = cursor.fetchall()
            if len(shops) > 1 or (shops and shops[0][1] != SHOP_ADDRESS):
                raise RuntimeError(
                    "A different or duplicate John's Boardshop already exists; "
                    "no data was changed. Inspect the business records before continuing."
                )
            for statement in db_tools.sql_statements("04_boardshop_data.sql"):
                cursor.execute(statement)
            inserted = cursor.rowcount
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"John's Boardshop is ready; added {inserted} equipment item(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
