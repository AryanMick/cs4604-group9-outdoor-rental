-- CS4604 Group 9 | Outdoor Equipment Rental Management System
-- MySQL 8.4. Run once in an empty outdoor_rental_group9 database.

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
    status VARCHAR(20) NOT NULL,
    business_id INT NOT NULL,
    CONSTRAINT equipment_type_not_blank CHECK (TRIM(equipment_type) <> ''),
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

CREATE TABLE reservation (
    reservation_id INT AUTO_INCREMENT PRIMARY KEY,
    equipment_id INT NOT NULL,
    customer_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    checkout_date DATE NOT NULL,
    due_date DATE NOT NULL,
    CONSTRAINT reservation_status_valid CHECK (status IN ('RESERVED', 'CHECKED_OUT', 'RETURNED', 'CANCELLED')),
    CONSTRAINT reservation_date_order CHECK (due_date > checkout_date),
    CONSTRAINT reservation_equipment_fk FOREIGN KEY (equipment_id) REFERENCES rental_equipment (equipment_id),
    CONSTRAINT reservation_customer_fk FOREIGN KEY (customer_id) REFERENCES customer (customer_id)
) ENGINE=InnoDB;

CREATE TABLE payment (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    reservation_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    payment_date DATE NOT NULL,
    CONSTRAINT payment_reservation_unique UNIQUE (reservation_id),
    CONSTRAINT payment_amount_positive CHECK (amount > 0),
    CONSTRAINT payment_reservation_fk FOREIGN KEY (reservation_id) REFERENCES reservation (reservation_id)
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

CREATE INDEX equipment_business_idx ON rental_equipment (business_id);
CREATE INDEX reservation_equipment_idx ON reservation (equipment_id);
CREATE INDEX reservation_customer_idx ON reservation (customer_id);
CREATE INDEX manager_business_idx ON manager (business_id);
CREATE INDEX employee_manager_idx ON employee (manager_id);
CREATE INDEX access_employee_idx ON defines_access (employee_id);

-- Views show joined information without duplicating it in the base tables.
CREATE VIEW reservation_details AS
SELECT r.reservation_id, CONCAT(c.first_name, ' ', c.last_name) AS customer,
       e.equipment_id, e.equipment_type, b.business_name,
       r.status, r.checkout_date, r.due_date, p.amount AS payment_amount
FROM reservation AS r
JOIN customer AS c ON c.customer_id = r.customer_id
JOIN rental_equipment AS e ON e.equipment_id = r.equipment_id
JOIN business AS b ON b.business_id = e.business_id
LEFT JOIN payment AS p ON p.reservation_id = r.reservation_id;

CREATE VIEW employee_details AS
SELECT e.employee_id, e.first_name, e.last_name, e.email,
       m.manager_id, CONCAT(m.first_name, ' ', m.last_name) AS manager,
       b.business_id, b.business_name
FROM employee AS e
JOIN manager AS m ON m.manager_id = e.manager_id
JOIN business AS b ON b.business_id = m.business_id;
