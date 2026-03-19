CREATE TABLE IF NOT EXISTS organizations (
    id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS organization_id VARCHAR(32);

ALTER TABLE subjects
    ADD COLUMN IF NOT EXISTS organization_id VARCHAR(32);

INSERT INTO organizations (id, name, is_active, created_at, updated_at)
SELECT
    SUBSTRING(MD5('org:' || users.id) FROM 1 FOR 32),
    CONCAT(
        COALESCE(NULLIF(SPLIT_PART(users.email, '@', 1), ''), CONCAT('organization-', LEFT(users.id, 8))),
        ' Organization'
    ),
    TRUE,
    COALESCE(users.created_at, NOW()),
    COALESCE(users.updated_at, NOW())
FROM users
WHERE LOWER(users.role) = 'admin'
  AND NOT EXISTS (
      SELECT 1
      FROM organizations
      WHERE organizations.id = SUBSTRING(MD5('org:' || users.id) FROM 1 FOR 32)
  );

UPDATE users
SET organization_id = SUBSTRING(MD5('org:' || users.id) FROM 1 FOR 32)
WHERE LOWER(users.role) = 'admin'
  AND organization_id IS NULL;

UPDATE subjects
SET organization_id = owners.organization_id
FROM users AS owners
WHERE subjects.owner_id = owners.id
  AND subjects.organization_id IS NULL;

UPDATE users
SET organization_id = enrollment_orgs.organization_id
FROM (
    SELECT
        subject_enrollments.student_id,
        MIN(subjects.organization_id) AS organization_id,
        COUNT(DISTINCT subjects.organization_id) AS organization_count
    FROM subject_enrollments
    INNER JOIN subjects ON subjects.id = subject_enrollments.subject_id
    GROUP BY subject_enrollments.student_id
) AS enrollment_orgs
WHERE users.id = enrollment_orgs.student_id
  AND users.organization_id IS NULL
  AND enrollment_orgs.organization_count = 1;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM (
            SELECT subject_enrollments.student_id
            FROM subject_enrollments
            INNER JOIN subjects ON subjects.id = subject_enrollments.subject_id
            GROUP BY subject_enrollments.student_id
            HAVING COUNT(DISTINCT subjects.organization_id) > 1
        ) AS conflicting_students
    ) THEN
        RAISE EXCEPTION 'Cannot migrate students enrolled in multiple organizations.';
    END IF;
END
$$;

INSERT INTO organizations (id, name, is_active, created_at, updated_at)
SELECT
    SUBSTRING(MD5('legacy:' || users.id) FROM 1 FOR 32),
    CONCAT(
        COALESCE(NULLIF(SPLIT_PART(users.email, '@', 1), ''), CONCAT('workspace-', LEFT(users.id, 8))),
        ' Workspace'
    ),
    TRUE,
    COALESCE(users.created_at, NOW()),
    COALESCE(users.updated_at, NOW())
FROM users
WHERE users.organization_id IS NULL
  AND NOT EXISTS (
      SELECT 1
      FROM organizations
      WHERE organizations.id = SUBSTRING(MD5('legacy:' || users.id) FROM 1 FOR 32)
  );

UPDATE users
SET organization_id = SUBSTRING(MD5('legacy:' || users.id) FROM 1 FOR 32)
WHERE organization_id IS NULL;

UPDATE subjects
SET organization_id = owners.organization_id
FROM users AS owners
WHERE subjects.owner_id = owners.id
  AND subjects.organization_id IS NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM users WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'User organization backfill failed.';
    END IF;

    IF EXISTS (SELECT 1 FROM subjects WHERE organization_id IS NULL) THEN
        RAISE EXCEPTION 'Subject organization backfill failed.';
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_users_organization_id'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT fk_users_organization_id
            FOREIGN KEY (organization_id)
            REFERENCES organizations(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_subjects_organization_id'
    ) THEN
        ALTER TABLE subjects
            ADD CONSTRAINT fk_subjects_organization_id
            FOREIGN KEY (organization_id)
            REFERENCES organizations(id);
    END IF;
END
$$;

ALTER TABLE users
    ALTER COLUMN organization_id SET NOT NULL;

ALTER TABLE subjects
    ALTER COLUMN organization_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_users_organization_id ON users (organization_id);
CREATE INDEX IF NOT EXISTS ix_subjects_organization_id ON subjects (organization_id);
