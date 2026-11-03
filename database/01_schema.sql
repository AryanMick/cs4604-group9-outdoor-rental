-- CS4604 Group 9 | Outdoor Equipment Rental Management System
-- MySQL 8.4. Run once in an empty outdoor_rental_group9 database.
-- Run order: 01_schema.sql, 02_sample_data.sql, 03_triggers.sql (db_tools.py does this).

CREATE TABLE business (
    business_id INT AUTO_INCREMENT PRIMARY KEY,
    business_name VARCHAR(120) NOT NULL,
    address VARCHAR(255) NOT NULL,
    CONSTRAINT business_name_not_blank CHECK (TRIM(business_name) <> ''),
    CONSTRAINT business_address_not_blank CHECK (TRIM(address) <> '')
) ENGINE=InnoDB;

CREATE TABLE rental_equipment (
    equipment_id INT AUTO_INCREMENT PRIMARY KEY,
    equipment_type VARCHAR(60) NOT NULL,
    description VARCHAR(255) NOT NULL,
    rate DECIMAL(10,2) NOT NULL,
    rate_unit VARCHAR(10) NOT NULL,
    -- Path relative to the static/ folder.
    image_url VARCHAR(255) NOT NULL DEFAULT 'img/placeholder.jpg',
    status VARCHAR(20) NOT NULL,
    business_id INT NOT NULL,
    CONSTRAINT equipment_type_not_blank CHECK (TRIM(equipment_type) <> ''),
    CONSTRAINT equipment_description_not_blank CHECK (TRIM(description) <> ''),
    CONSTRAINT equipment_rate_positive CHECK (rate > 0),
    CONSTRAINT equipment_rate_unit_valid CHECK (rate_unit IN ('HOUR', 'DAY')),
    CONSTRAINT equipment_status_valid CHECK (status IN ('AVAILABLE', 'MAINTENANCE', 'RETIRED')),
    CONSTRAINT equipment_business_fk FOREIGN KEY (business_id) REFERENCES business (business_id)
) ENGINE=InnoDB;

CREATE TABLE customer (
    customer_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    email VARCHAR(254) NOT NULL,
    CONSTRAINT customer_first_name_not_blank CHECK (TRIM(first_name) <> ''),
    CONSTRAINT customer_last_name_not_blank CHECK (TRIM(last_name) <> ''),
    CONSTRAINT customer_email_not_blank CHECK (TRIM(email) <> ''),
    CONSTRAINT customer_email_unique UNIQUE (email)
) ENGINE=InnoDB;

-- One payment can cover several reservations; only the last 4 card digits are kept.
CREATE TABLE payment (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    amount DECIMAL(10,2) NOT NULL,
    payment_date DATETIME NOT NULL,
    card_last4 CHAR(4) NOT NULL,
    CONSTRAINT payment_amount_positive CHECK (amount > 0),
    CONSTRAINT payment_card_last4_digits CHECK (card_last4 REGEXP '^[0-9]{4}$')
) ENGINE=InnoDB;

-- Only RESERVED rows block other bookings; 03_triggers.sql rejects overlaps.
CREATE TABLE reservation (
    reservation_id INT AUTO_INCREMENT PRIMARY KEY,
    equipment_id INT NOT NULL,
    customer_id INT NOT NULL,
    payment_id INT NULL,
    status VARCHAR(20) NOT NULL,
    checkout_date DATETIME NOT NULL,
    due_date DATETIME NOT NULL,
    CONSTRAINT reservation_status_valid CHECK (status IN ('RESERVED', 'RETURNED', 'CANCELLED')),
    CONSTRAINT reservation_date_order CHECK (due_date > checkout_date),
    CONSTRAINT reservation_slot_aligned CHECK (
        MINUTE(checkout_date) IN (0, 30) AND SECOND(checkout_date) = 0
        AND MINUTE(due_date) IN (0, 30) AND SECOND(due_date) = 0),
    CONSTRAINT reservation_equipment_fk FOREIGN KEY (equipment_id) REFERENCES rental_equipment (equipment_id),
    CONSTRAINT reservation_customer_fk FOREIGN KEY (customer_id) REFERENCES customer (customer_id),
    CONSTRAINT reservation_payment_fk FOREIGN KEY (payment_id) REFERENCES payment (payment_id)
) ENGINE=InnoDB;

CREATE TABLE manager (
    manager_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    email VARCHAR(254) NOT NULL,
    business_id INT NOT NULL,
    CONSTRAINT manager_first_name_not_blank CHECK (TRIM(first_name) <> ''),
    CONSTRAINT manager_last_name_not_blank CHECK (TRIM(last_name) <> ''),
    CONSTRAINT manager_email_not_blank CHECK (TRIM(email) <> ''),
    CONSTRAINT manager_email_unique UNIQUE (email),
    CONSTRAINT manager_business_fk FOREIGN KEY (business_id) REFERENCES business (business_id)
) ENGINE=InnoDB;

CREATE TABLE employee (
    employee_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    email VARCHAR(254) NOT NULL,
    manager_id INT NOT NULL,
    CONSTRAINT employee_first_name_not_blank CHECK (TRIM(first_name) <> ''),
    CONSTRAINT employee_last_name_not_blank CHECK (TRIM(last_name) <> ''),
    CONSTRAINT employee_email_not_blank CHECK (TRIM(email) <> ''),
    CONSTRAINT employee_email_unique UNIQUE (email),
    CONSTRAINT employee_manager_fk FOREIGN KEY (manager_id) REFERENCES manager (manager_id)
) ENGINE=InnoDB;

CREATE TABLE admin (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(80) NOT NULL,
    last_name VARCHAR(80) NOT NULL,
    CONSTRAINT admin_first_name_not_blank CHECK (TRIM(first_name) <> ''),
    CONSTRAINT admin_last_name_not_blank CHECK (TRIM(last_name) <> '')
) ENGINE=InnoDB;

-- The manager for an access grant is found through employee.manager_id.
CREATE TABLE defines_access (
    admin_id INT NOT NULL,
    employee_id INT NOT NULL,
    PRIMARY KEY (admin_id, employee_id),
    CONSTRAINT access_admin_fk FOREIGN KEY (admin_id) REFERENCES admin (admin_id),
    CONSTRAINT access_employee_fk FOREIGN KEY (employee_id) REFERENCES employee (employee_id)
) ENGINE=InnoDB;

CREATE TABLE admin_privileges (
    admin_id INT NOT NULL,
    privilege VARCHAR(60) NOT NULL,
    PRIMARY KEY (admin_id, privilege),
    CONSTRAINT privilege_not_blank CHECK (TRIM(privilege) <> ''),
    CONSTRAINT privileges_admin_fk FOREIGN KEY (admin_id) REFERENCES admin (admin_id)
) ENGINE=InnoDB;

-- A customer's cart exists only while logged in: created at login, deleted at logout.
CREATE TABLE cart (
    cart_id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT cart_customer_unique UNIQUE (customer_id),
    CONSTRAINT cart_customer_fk FOREIGN KEY (customer_id) REFERENCES customer (customer_id)
) ENGINE=InnoDB;

-- Cleared when the cart is booked or removed by the customer.
CREATE TABLE cart_item (
    cart_item_id INT AUTO_INCREMENT PRIMARY KEY,
    cart_id INT NOT NULL,
    equipment_id INT NOT NULL,
    start_at DATETIME NOT NULL,
    end_at DATETIME NOT NULL,
    CONSTRAINT cart_item_equipment_unique UNIQUE (cart_id, equipment_id),
    CONSTRAINT cart_item_date_order CHECK (end_at > start_at),
    CONSTRAINT cart_item_slot_aligned CHECK (
        MINUTE(start_at) IN (0, 30) AND SECOND(start_at) = 0
        AND MINUTE(end_at) IN (0, 30) AND SECOND(end_at) = 0),
    CONSTRAINT cart_item_cart_fk FOREIGN KEY (cart_id) REFERENCES cart (cart_id),
    CONSTRAINT cart_item_equipment_fk FOREIGN KEY (equipment_id) REFERENCES rental_equipment (equipment_id)
) ENGINE=InnoDB;

CREATE INDEX equipment_business_idx ON rental_equipment (business_id);
CREATE INDEX reservation_equipment_idx ON reservation (equipment_id);
CREATE INDEX reservation_customer_idx ON reservation (customer_id);
CREATE INDEX reservation_payment_idx ON reservation (payment_id);
CREATE INDEX cart_item_equipment_idx ON cart_item (equipment_id);
CREATE INDEX manager_business_idx ON manager (business_id);
CREATE INDEX employee_manager_idx ON employee (manager_id);
CREATE INDEX access_employee_idx ON defines_access (employee_id);

-- Views show joined information without duplicating it in the base tables.
-- payment_amount is the whole payment, which may cover several reservations.
CREATE VIEW reservation_details AS
SELECT r.reservation_id, CONCAT(c.first_name, ' ', c.last_name) AS customer,
       e.equipment_id, e.equipment_type, b.business_name,
       r.status, r.checkout_date, r.due_date, r.payment_id, p.amount AS payment_amount
FROM reservation AS r
JOIN customer AS c ON c.customer_id = r.customer_id
JOIN rental_equipment AS e ON e.equipment_id = r.equipment_id
JOIN business AS b ON b.business_id = e.business_id
LEFT JOIN payment AS p ON p.payment_id = r.payment_id;

CREATE VIEW employee_details AS
SELECT e.employee_id, e.first_name, e.last_name, e.email,
       m.manager_id, CONCAT(m.first_name, ' ', m.last_name) AS manager,
       b.business_id, b.business_name
FROM employee AS e
JOIN manager AS m ON m.manager_id = e.manager_id
JOIN business AS b ON b.business_id = m.business_id;
