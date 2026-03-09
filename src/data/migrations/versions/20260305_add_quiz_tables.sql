CREATE TABLE IF NOT EXISTS quiz_questions (
    id VARCHAR(32) PRIMARY KEY,
    subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    material_version INTEGER NOT NULL,
    question TEXT NOT NULL,
    options JSONB NOT NULL DEFAULT '[]'::jsonb,
    correct_option TEXT NOT NULL,
    hints JSONB NOT NULL DEFAULT '[]'::jsonb,
    explanation TEXT,
    difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_quiz_questions_subject_id ON quiz_questions (subject_id);
CREATE INDEX IF NOT EXISTS ix_quiz_questions_concept_id ON quiz_questions (concept_id);
CREATE INDEX IF NOT EXISTS ix_quiz_questions_concept_version ON quiz_questions (concept_id, material_version);

CREATE TABLE IF NOT EXISTS quiz_sessions (
    id VARCHAR(32) PRIMARY KEY,
    user_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
    concept_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    question_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    current_index INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 0,
    correct_count INTEGER NOT NULL DEFAULT 0,
    incorrect_count INTEGER NOT NULL DEFAULT 0,
    score_percent DOUBLE PRECISION,
    session_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    report JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_quiz_sessions_user_id ON quiz_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_quiz_sessions_subject_id ON quiz_sessions (subject_id);

CREATE TABLE IF NOT EXISTS quiz_responses (
    id VARCHAR(32) PRIMARY KEY,
    session_id VARCHAR(32) NOT NULL REFERENCES quiz_sessions(id) ON DELETE CASCADE,
    question_id VARCHAR(32) NOT NULL REFERENCES quiz_questions(id) ON DELETE CASCADE,
    concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    selected_option TEXT,
    is_correct BOOLEAN NOT NULL DEFAULT FALSE,
    attempts INTEGER NOT NULL DEFAULT 0,
    hints_used INTEGER NOT NULL DEFAULT 0,
    attempt_log JSONB NOT NULL DEFAULT '[]'::jsonb,
    answered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_quiz_session_question UNIQUE (session_id, question_id)
);

CREATE INDEX IF NOT EXISTS ix_quiz_responses_session_id ON quiz_responses (session_id);
CREATE INDEX IF NOT EXISTS ix_quiz_responses_concept_id ON quiz_responses (concept_id);
