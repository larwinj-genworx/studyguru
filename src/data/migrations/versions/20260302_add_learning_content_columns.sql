ALTER TABLE concept_materials
    ADD COLUMN IF NOT EXISTS content JSONB;

ALTER TABLE concept_materials
    ADD COLUMN IF NOT EXISTS content_text TEXT;

ALTER TABLE concept_materials
    ADD COLUMN IF NOT EXISTS content_schema_version VARCHAR(24) DEFAULT 'v1';

ALTER TABLE concept_materials
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;

UPDATE concept_materials
SET updated_at = generated_at
WHERE updated_at IS NULL;

ALTER TABLE concept_materials
    ALTER COLUMN updated_at SET DEFAULT NOW();

ALTER TABLE concept_materials
    ALTER COLUMN updated_at SET NOT NULL;

CREATE TABLE IF NOT EXISTS concept_bookmarks (
    user_id VARCHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, concept_id)
);
