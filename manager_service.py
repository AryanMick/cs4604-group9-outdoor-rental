"""Business-scoped manager operations for rental equipment."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
import secrets
from tempfile import NamedTemporaryFile

import db_tools

MAX_JPEG_BYTES = 8 * 1024 * 1024
PLACEHOLDER_IMAGE = "img/placeholder.svg"


class ManagerEquipmentError(ValueError):
    """A validation or equipment-availability problem managers can resolve."""


def list_equipment(business_id: int) -> list[dict]:
    """Return this business's editable equipment, excluding retired entries."""
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT equipment_id, equipment_type, description, rate, rate_unit, image_url, status "
                "FROM rental_equipment WHERE business_id=%s AND status <> 'RETIRED' "
                "ORDER BY equipment_type, equipment_id",
                (business_id,),
            )
            return [
                {
                    "equipment_id": row[0], "equipment_type": row[1], "description": row[2],
                    "rate": row[3], "rate_unit": row[4], "image_url": row[5], "status": row[6],
                }
                for row in cursor.fetchall()
            ]
    finally:
        connection.close()


def get_business_name(business_id: int) -> str | None:
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT business_name FROM business WHERE business_id=%s", (business_id,))
            row = cursor.fetchone()
            return row[0] if row else None
    finally:
        connection.close()


def _validated_fields(equipment_type: str, description: str, rate: str, rate_unit: str, status: str) -> tuple[str, str, Decimal, str, str]:
    name = equipment_type.strip()
    detail = description.strip()
    unit = rate_unit.strip().upper()
    state = status.strip().upper()
    if not name or len(name) > 60:
        raise ManagerEquipmentError("Equipment name is required and must be 60 characters or fewer.")
    if not detail or len(detail) > 255:
        raise ManagerEquipmentError("Description is required and must be 255 characters or fewer.")
    try:
        amount = Decimal(rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        raise ManagerEquipmentError("Enter a valid equipment rate.") from None
    if not amount.is_finite() or amount <= 0 or amount > Decimal("99999999.99"):
        raise ManagerEquipmentError("Rate must be greater than zero and no more than 99,999,999.99.")
    if unit not in {"HOUR", "DAY"}:
        raise ManagerEquipmentError("Choose an hourly or daily rate.")
    if state not in {"AVAILABLE", "MAINTENANCE"}:
        raise ManagerEquipmentError("Choose Available or Maintenance status.")
    return name, detail, amount, unit, state


def _validated_jpeg(filename: str, content: bytes | None) -> bytes:
    if not filename.lower().endswith((".jpg", ".jpeg")):
        raise ManagerEquipmentError("Upload a JPG image (.jpg or .jpeg).")
    if not content or len(content) > MAX_JPEG_BYTES:
        raise ManagerEquipmentError("Choose a JPG image smaller than 8 MB.")
    if not content.startswith(b"\xff\xd8\xff"):
        raise ManagerEquipmentError("The uploaded file is not a valid JPG image.")
    return content


def _stage_image(image_dir: Path, equipment_id: int, content: bytes) -> tuple[str, Path, Path]:
    image_dir.mkdir(parents=True, exist_ok=True)
    filename = f"equipment-{equipment_id}-{secrets.token_hex(6)}.jpg"
    destination = image_dir / filename
    with NamedTemporaryFile(prefix=".equipment-upload-", suffix=".tmp", dir=image_dir, delete=False) as staged:
        staged.write(content)
        staged_path = Path(staged.name)
    return f"img/{filename}", staged_path, destination


def _is_managed_image(image_url: str | None, image_dir: Path) -> Path | None:
    if not image_url or not re.fullmatch(r"img/equipment-\d+-[0-9a-f]{12}\.jpg", image_url):
        return None
    root = image_dir.resolve()
    candidate = (root.parent / image_url).resolve()
    return candidate if candidate.is_relative_to(root) else None


def _cleanup_unused_image(image_url: str | None, image_dir: Path) -> None:
    candidate = _is_managed_image(image_url, image_dir)
    if candidate is None:
        return
    connection = db_tools.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM rental_equipment WHERE image_url=%s", (image_url,))
            referenced = cursor.fetchone()[0]
    finally:
        connection.close()
    if not referenced:
        candidate.unlink(missing_ok=True)


def create_equipment(
    business_id: int,
    equipment_type: str,
    description: str,
    rate: str,
    rate_unit: str,
    status: str,
    image_filename: str,
    image_content: bytes | None,
    image_dir: Path,
) -> int:
    """Create equipment and its JPG path in one DB transaction."""
    name, detail, amount, unit, state = _validated_fields(equipment_type, description, rate, rate_unit, status)
    content = _validated_jpeg(image_filename, image_content)
    connection = db_tools.connect()
    staged_path = destination = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO rental_equipment "
                "(equipment_type, description, rate, rate_unit, image_url, status, business_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (name, detail, amount, unit, PLACEHOLDER_IMAGE, state, business_id),
            )
            equipment_id = cursor.lastrowid
            image_url, staged_path, destination = _stage_image(image_dir, equipment_id, content)
            cursor.execute("UPDATE rental_equipment SET image_url=%s WHERE equipment_id=%s", (image_url, equipment_id))
            staged_path.replace(destination)
        connection.commit()
        return equipment_id
    except Exception:
        connection.rollback()
        if staged_path:
            staged_path.unlink(missing_ok=True)
        if destination:
            destination.unlink(missing_ok=True)
        raise
    finally:
        connection.close()


def update_equipment(
    business_id: int,
    equipment_id: int,
    equipment_type: str,
    description: str,
    rate: str,
    rate_unit: str,
    status: str,
    image_filename: str | None,
    image_content: bytes | None,
    image_dir: Path,
) -> None:
    name, detail, amount, unit, state = _validated_fields(equipment_type, description, rate, rate_unit, status)
    content = _validated_jpeg(image_filename, image_content) if image_filename else None
    connection = db_tools.connect()
    staged_path = destination = None
    old_image = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT image_url FROM rental_equipment "
                "WHERE equipment_id=%s AND business_id=%s AND status <> 'RETIRED' FOR UPDATE",
                (equipment_id, business_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise ManagerEquipmentError("That equipment was not found for your business.")
            old_image = row[0]
            image_url = old_image
            if content is not None:
                image_url, staged_path, destination = _stage_image(image_dir, equipment_id, content)
            cursor.execute(
                "UPDATE rental_equipment SET equipment_type=%s, description=%s, rate=%s, "
                "rate_unit=%s, status=%s, image_url=%s WHERE equipment_id=%s AND business_id=%s",
                (name, detail, amount, unit, state, image_url, equipment_id, business_id),
            )
            if staged_path and destination:
                staged_path.replace(destination)
        connection.commit()
    except Exception:
        connection.rollback()
        if staged_path:
            staged_path.unlink(missing_ok=True)
        if destination:
            destination.unlink(missing_ok=True)
        raise
    finally:
        connection.close()
    if content is not None and old_image != image_url:
        _cleanup_unused_image(old_image, image_dir)


def retire_equipment(business_id: int, equipment_id: int, image_dir: Path) -> None:
    """Hide equipment without deleting its row or historical reservations."""
    connection = db_tools.connect()
    old_image = None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT image_url FROM rental_equipment "
                "WHERE equipment_id=%s AND business_id=%s AND status <> 'RETIRED' FOR UPDATE",
                (equipment_id, business_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise ManagerEquipmentError("That equipment was not found for your business.")
            old_image = row[0]
            cursor.execute(
                "SELECT COUNT(*) FROM reservation WHERE equipment_id=%s AND status='RESERVED'",
                (equipment_id,),
            )
            if cursor.fetchone()[0]:
                raise ManagerEquipmentError("This equipment has an active or scheduled rental and cannot be removed.")
            cursor.execute(
                "SELECT COUNT(*) FROM cart_item WHERE equipment_id=%s AND end_at > CURRENT_TIMESTAMP",
                (equipment_id,),
            )
            if cursor.fetchone()[0]:
                raise ManagerEquipmentError("This equipment is in a customer's active or future cart and cannot be removed.")
            cursor.execute(
                "DELETE FROM cart_item WHERE equipment_id=%s AND end_at <= CURRENT_TIMESTAMP",
                (equipment_id,),
            )
            cursor.execute(
                "UPDATE rental_equipment SET status='RETIRED', image_url=%s "
                "WHERE equipment_id=%s AND business_id=%s",
                (PLACEHOLDER_IMAGE, equipment_id, business_id),
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    _cleanup_unused_image(old_image, image_dir)