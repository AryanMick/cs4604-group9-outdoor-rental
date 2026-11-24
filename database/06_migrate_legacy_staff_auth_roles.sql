-- One-time migration for databases that used STAFF for both employees and managers.
-- Back up the database before applying. Run only if the legacy auth_role_valid and
-- auth_role_link_valid checks are present.

ALTER TABLE auth_account
    DROP CHECK auth_role_link_valid,
    DROP CHECK auth_role_valid;

UPDATE auth_account
SET role = CASE
    WHEN employee_id IS NOT NULL AND manager_id IS NULL THEN 'EMPLOYEE'
    WHEN manager_id IS NOT NULL AND employee_id IS NULL THEN 'MANAGER'
    ELSE role
END
WHERE role = 'STAFF';

ALTER TABLE auth_account
    ADD CONSTRAINT auth_role_valid
        CHECK (role IN ('CUSTOMER', 'EMPLOYEE', 'MANAGER', 'ADMIN')),
    ADD CONSTRAINT auth_role_link_valid CHECK (
        (role = 'CUSTOMER' AND customer_id IS NOT NULL AND employee_id IS NULL AND manager_id IS NULL AND admin_id IS NULL)
        OR (role = 'EMPLOYEE' AND customer_id IS NULL AND employee_id IS NOT NULL AND manager_id IS NULL AND admin_id IS NULL)
        OR (role = 'MANAGER' AND customer_id IS NULL AND employee_id IS NULL AND manager_id IS NOT NULL AND admin_id IS NULL)
        OR (role = 'ADMIN' AND customer_id IS NULL AND employee_id IS NULL AND manager_id IS NULL AND admin_id IS NOT NULL)
    );
