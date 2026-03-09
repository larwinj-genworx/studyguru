CREATE TABLE IF NOT EXISTS concept_image_assets (
    id VARCHAR(32) PRIMARY KEY,
    subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    concept_material_id VARCHAR(32) NOT NULL REFERENCES concept_materials(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    title VARCHAR(240) NOT NULL,
    caption TEXT,
    alt_text TEXT,
    intent_label VARCHAR(160),
    source_page_url TEXT,
    source_image_url TEXT,
    source_domain VARCHAR(120),
    local_image_path VARCHAR(320) NOT NULL,
    thumbnail_path VARCHAR(320) NOT NULL,
    mime_type VARCHAR(80),
    width INTEGER,
    height INTEGER,
    file_size_bytes INTEGER,
    fingerprint VARCHAR(64),
    relevance_score DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_concept_image_assets_subject_id ON concept_image_assets (subject_id);
CREATE INDEX IF NOT EXISTS ix_concept_image_assets_concept_id ON concept_image_assets (concept_id);
CREATE INDEX IF NOT EXISTS ix_concept_image_assets_concept_material_id ON concept_image_assets (concept_material_id);

CREATE INDEX IF NOT EXISTS ix_concept_image_assets_material_status
ON concept_image_assets (concept_material_id, status);

CREATE INDEX IF NOT EXISTS ix_concept_image_assets_concept_created
ON concept_image_assets (concept_id, created_at);
