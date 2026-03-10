ALTER TABLE concepts
    ADD COLUMN IF NOT EXISTS topic_order INTEGER;

ALTER TABLE concepts
    ADD COLUMN IF NOT EXISTS pass_percentage INTEGER NOT NULL DEFAULT 70;

WITH ranked_concepts AS (
    SELECT
        id,
        ROW_NUMBER() OVER (
            PARTITION BY subject_id
            ORDER BY COALESCE(topic_order, 2147483647), created_at, id
        ) AS next_topic_order
    FROM concepts
)
UPDATE concepts
SET topic_order = ranked_concepts.next_topic_order
FROM ranked_concepts
WHERE concepts.id = ranked_concepts.id;

ALTER TABLE concepts
    ALTER COLUMN topic_order SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_concepts_subject_topic_order
    ON concepts (subject_id, topic_order);

CREATE TABLE IF NOT EXISTS student_concept_progress (
    student_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    learning_completed_at TIMESTAMPTZ,
    assessment_attempts INTEGER NOT NULL DEFAULT 0,
    latest_score_percent DOUBLE PRECISION,
    best_score_percent DOUBLE PRECISION,
    passed_at TIMESTAMPTZ,
    last_assessment_session_id VARCHAR(32) REFERENCES quiz_sessions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (student_id, concept_id)
);

CREATE INDEX IF NOT EXISTS ix_student_concept_progress_subject_id
    ON student_concept_progress (subject_id);

CREATE INDEX IF NOT EXISTS ix_student_concept_progress_subject_student
    ON student_concept_progress (subject_id, student_id);

ALTER TABLE quiz_questions
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(30) NOT NULL DEFAULT 'custom_practice';

CREATE INDEX IF NOT EXISTS ix_quiz_questions_concept_source
    ON quiz_questions (concept_id, source_type);

ALTER TABLE quiz_sessions
    ADD COLUMN IF NOT EXISTS session_type VARCHAR(30) NOT NULL DEFAULT 'custom_practice';

ALTER TABLE quiz_sessions
    ADD COLUMN IF NOT EXISTS gated_concept_id VARCHAR(32) REFERENCES concepts(id) ON DELETE SET NULL;

ALTER TABLE quiz_sessions
    ADD COLUMN IF NOT EXISTS required_pass_percentage INTEGER;

ALTER TABLE quiz_sessions
    ADD COLUMN IF NOT EXISTS passed BOOLEAN;

CREATE INDEX IF NOT EXISTS ix_quiz_sessions_gated_concept_id
    ON quiz_sessions (gated_concept_id);
