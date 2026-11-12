"""Apply the seeded equipment image paths to an existing project database."""
from __future__ import annotations

import db_tools

IMAGE_BY_TYPE = {
    "Two-person tent": "img/twoPersonTent.jpg",
    "Four-person tent": "img/fourPersonTent.jpg",
    "Hiking backpack": "img/hikingBackpack.jpg",
    "Sleeping bag": "img/sleepingBag.jpg",
    "Kayak": "img/kayak.jpg",
    "Canoe": "img/canoe.jpg",
    "Paddleboard": "img/paddleboard.jpg",
    "Climbing helmet": "img/climbingHelmet.jpg",
    "Trekking poles": "img/trekkingPoles.jpg",
    "Camping stove": "img/campingStove.jpg",
}


def main() -> int:
    """Update only default-placeholder paths, preserving any custom image paths."""
    connection = db_tools.connect()
    updated = 0
    try:
        with connection.cursor() as cursor:
            for equipment_type, image_path in IMAGE_BY_TYPE.items():
                cursor.execute(
                    "UPDATE rental_equipment SET image_url=%s "
                    "WHERE equipment_type=%s AND image_url='img/placeholder.jpg'",
                    (image_path, equipment_type),
                )
                updated += cursor.rowcount
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(f"Updated {updated} equipment row(s).")
    if updated == 0:
        print("No default placeholder paths needed updating; the migration may already be applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
