ALTER TABLE quiz_questions
    DROP CONSTRAINT IF EXISTS quiz_questions_subject_id_fkey;

ALTER TABLE quiz_questions
    DROP CONSTRAINT IF EXISTS quiz_questions_concept_id_fkey;

ALTER TABLE quiz_sessions
    DROP CONSTRAINT IF EXISTS quiz_sessions_subject_id_fkey;

ALTER TABLE quiz_responses
    DROP CONSTRAINT IF EXISTS quiz_responses_concept_id_fkey;

ALTER TABLE quiz_questions
    ALTER COLUMN subject_id DROP NOT NULL;

ALTER TABLE quiz_questions
    ALTER COLUMN concept_id DROP NOT NULL;

ALTER TABLE quiz_sessions
    ALTER COLUMN subject_id DROP NOT NULL;

ALTER TABLE quiz_responses
    ALTER COLUMN concept_id DROP NOT NULL;

ALTER TABLE quiz_questions
    ADD CONSTRAINT quiz_questions_subject_id_fkey
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL;

ALTER TABLE quiz_questions
    ADD CONSTRAINT quiz_questions_concept_id_fkey
    FOREIGN KEY (concept_id) REFERENCES concepts(id) ON DELETE SET NULL;

ALTER TABLE quiz_sessions
    ADD CONSTRAINT quiz_sessions_subject_id_fkey
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE SET NULL;

ALTER TABLE quiz_responses
    ADD CONSTRAINT quiz_responses_concept_id_fkey
    FOREIGN KEY (concept_id) REFERENCES concepts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_quiz_questions_subject_id ON quiz_questions (subject_id);
CREATE INDEX IF NOT EXISTS ix_quiz_questions_concept_id ON quiz_questions (concept_id);
CREATE INDEX IF NOT EXISTS ix_quiz_questions_concept_version ON quiz_questions (concept_id, material_version);
CREATE INDEX IF NOT EXISTS ix_quiz_sessions_user_id ON quiz_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_quiz_sessions_subject_id ON quiz_sessions (subject_id);
CREATE INDEX IF NOT EXISTS ix_quiz_responses_session_id ON quiz_responses (session_id);
CREATE INDEX IF NOT EXISTS ix_quiz_responses_concept_id ON quiz_responses (concept_id);
