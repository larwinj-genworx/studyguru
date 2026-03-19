CREATE TABLE IF NOT EXISTS learning_bot_sessions (
    id VARCHAR(32) PRIMARY KEY,
    user_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    title VARCHAR(200),
    session_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_learning_bot_sessions_user_id ON learning_bot_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_learning_bot_sessions_subject_id ON learning_bot_sessions (subject_id);
CREATE INDEX IF NOT EXISTS ix_learning_bot_sessions_concept_id ON learning_bot_sessions (concept_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_learning_bot_sessions_active_user_concept
ON learning_bot_sessions (user_id, concept_id)
WHERE status = 'active';

CREATE TABLE IF NOT EXISTS learning_bot_messages (
    id VARCHAR(32) PRIMARY KEY,
    session_id VARCHAR(32) NOT NULL REFERENCES learning_bot_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    follow_up_suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
    message_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_learning_bot_messages_session_id ON learning_bot_messages (session_id);

CREATE INDEX IF NOT EXISTS ix_learning_bot_messages_session_created
ON learning_bot_messages (session_id, created_at);
