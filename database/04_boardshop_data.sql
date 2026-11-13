-- Demo boardshop and equipment for new and existing databases.
-- Re-running adds only missing equipment types, without changing existing rows.
INSERT INTO business (business_name, address)
SELECT 'John''s Boardshop', '121 Demonstration Trail, Blacksburg, VA 24060'
WHERE NOT EXISTS (SELECT 1 FROM business WHERE business_name = 'John''s Boardshop');

INSERT INTO rental_equipment (equipment_type, description, rate, rate_unit, status, business_id, image_url)
SELECT gear.equipment_type, gear.description, gear.rate, 'DAY', 'AVAILABLE', b.business_id, gear.image_url
FROM business b
JOIN (
    SELECT 'Mountain bike' AS equipment_type, 'Trail-ready mountain bike with front suspension.' AS description, 45.00 AS rate, 'img/mountainBike.jpg' AS image_url
    UNION ALL SELECT 'Rental skis', 'All-mountain rental skis with bindings and poles.', 40.00, 'img/skis.jpg'
    UNION ALL SELECT 'Rental snowboard', 'All-mountain rental snowboard with bindings.', 40.00, 'img/snowboard.jpg'
    UNION ALL SELECT 'Professional demo skis', 'Performance demo skis with bindings for experienced skiers.', 60.00, 'img/skis.jpg'
    UNION ALL SELECT 'Professional demo snowboard', 'Performance demo snowboard with bindings for experienced riders.', 60.00, 'img/snowboard.jpg'
    UNION ALL SELECT 'Ski and snowboard helmet', 'Adjustable snow sports helmet for skiing or snowboarding.', 10.00, 'img/snowHelmet.jpg'
) AS gear
WHERE b.business_name = 'John''s Boardshop'
AND NOT EXISTS (
    SELECT 1 FROM rental_equipment existing
    WHERE existing.business_id = b.business_id AND existing.equipment_type = gear.equipment_type
);
