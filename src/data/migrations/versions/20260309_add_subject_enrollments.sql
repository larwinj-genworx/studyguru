CREATE TABLE IF NOT EXISTS subject_enrollments (
    student_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (student_id, subject_id)
);

CREATE INDEX IF NOT EXISTS ix_subject_enrollments_subject_id
    ON subject_enrollments (subject_id, enrolled_at DESC);
