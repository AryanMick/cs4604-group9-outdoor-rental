-- CS4604 Group 9 | Reservation rules enforced by the database.
-- Run after 02_sample_data.sql. Statements end with $$ because trigger bodies contain semicolons.

-- Rejects a RESERVED row for unavailable equipment, a partial-day rental of a DAY-rate item,
-- or a time range overlapping another RESERVED row for the same equipment.
-- The equipment row is locked first so concurrent bookings of one item are serialized.
CREATE PROCEDURE validate_reservation(
    IN p_reservation_id INT,
    IN p_equipment_id INT,
    IN p_status VARCHAR(20),
    IN p_start DATETIME,
    IN p_end DATETIME
)
BEGIN
    DECLARE v_equipment_status VARCHAR(20) DEFAULT NULL;
    DECLARE v_rate_unit VARCHAR(10) DEFAULT NULL;
    DECLARE v_conflicts INT DEFAULT 0;

    -- Date order is left to the reservation_date_order CHECK constraint.
    IF p_status = 'RESERVED' AND p_end > p_start THEN
        SELECT status, rate_unit INTO v_equipment_status, v_rate_unit
        FROM rental_equipment
        WHERE equipment_id = p_equipment_id
        FOR UPDATE;

        -- A missing equipment row is reported by the foreign key instead.
        IF v_equipment_status IS NOT NULL THEN
            IF v_equipment_status <> 'AVAILABLE' THEN
                SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Reservation rejected: the equipment is not available.';
            END IF;

            IF v_rate_unit = 'DAY' AND MOD(TIMESTAMPDIFF(MINUTE, p_start, p_end), 1440) <> 0 THEN
                SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Reservation rejected: day-rate equipment must be rented in whole 24-hour days.';
            END IF;

            SELECT COUNT(*) INTO v_conflicts
            FROM reservation
            WHERE equipment_id = p_equipment_id
              AND status = 'RESERVED'
              AND reservation_id <> COALESCE(p_reservation_id, 0)
              AND checkout_date < p_end
              AND due_date > p_start
            FOR SHARE;

            IF v_conflicts > 0 THEN
                SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'Reservation rejected: the equipment is already reserved for part of that time.';
            END IF;
        END IF;
    END IF;
END$$

CREATE TRIGGER reservation_validate_insert
BEFORE INSERT ON reservation
FOR EACH ROW
BEGIN
    CALL validate_reservation(NEW.reservation_id, NEW.equipment_id, NEW.status, NEW.checkout_date, NEW.due_date);
END$$

-- Unchanged rows (for example a status-only edit) are not re-validated.
CREATE TRIGGER reservation_validate_update
BEFORE UPDATE ON reservation
FOR EACH ROW
BEGIN
    IF NOT (NEW.equipment_id <=> OLD.equipment_id
            AND NEW.status <=> OLD.status
            AND NEW.checkout_date <=> OLD.checkout_date
            AND NEW.due_date <=> OLD.due_date) THEN
        CALL validate_reservation(NEW.reservation_id, NEW.equipment_id, NEW.status, NEW.checkout_date, NEW.due_date);
    END IF;
END$$
