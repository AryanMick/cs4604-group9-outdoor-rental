"""Add demo mountain bikes to selected sample businesses without replacing inventory."""
from __future__ import annotations

import db_tools

SHOPS = {
    "Blue Ridge Outfitters": "101 Demonstration Trail, Blacksburg, VA 24060",
    "Trailhead Equipment": "103 Demonstration Trail, Blacksburg, VA 24060",
    "Summit Outdoor Gear": "104 Demonstration Trail, Blacksburg, VA 24060",
    "Roanoke Trail Supply": "109 Demonstration Trail, Blacksburg, VA 24060",
}


def main() -> int:
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            for name, address in SHOPS.items():
                cursor.execute(
                    "SELECT business_id, address FROM business WHERE business_name=%s FOR UPDATE",
                    (name,),
                )
                shops = cursor.fetchall()
                if len(shops) != 1 or shops[0][1] != address:
                    raise RuntimeError(
                        f"Expected exactly one sample business named {name!r} at {address!r}; "
                        "no data was changed. Inspect the business records before continuing."
                    )
            for statement in db_tools.sql_statements("05_mountain_bike_data.sql"):
                cursor.execute(statement)
            inserted = cursor.rowcount
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"Added {inserted} mountain bike(s) to the selected sample shops.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
