-- Add one demo mountain bike to selected sample shops if they do not have one.
INSERT INTO rental_equipment (equipment_type, description, rate, rate_unit, status, business_id, image_url)
SELECT 'Mountain bike', 'Trail-ready mountain bike with front suspension.',
       45.00, 'DAY', 'AVAILABLE', b.business_id, 'img/mountainBike.jpg'
FROM business b
WHERE (
    (b.business_name = 'Blue Ridge Outfitters' AND b.address = '101 Demonstration Trail, Blacksburg, VA 24060')
    OR (b.business_name = 'Trailhead Equipment' AND b.address = '103 Demonstration Trail, Blacksburg, VA 24060')
    OR (b.business_name = 'Summit Outdoor Gear' AND b.address = '104 Demonstration Trail, Blacksburg, VA 24060')
    OR (b.business_name = 'Roanoke Trail Supply' AND b.address = '109 Demonstration Trail, Blacksburg, VA 24060')
)
AND NOT EXISTS (
    SELECT 1 FROM rental_equipment existing
    WHERE existing.business_id = b.business_id AND existing.equipment_type = 'Mountain bike'
);
