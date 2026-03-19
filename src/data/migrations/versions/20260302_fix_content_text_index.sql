DROP INDEX IF EXISTS ix_concept_materials_content_text;

CREATE INDEX IF NOT EXISTS ix_concept_materials_content_text_fts
ON concept_materials
USING GIN (to_tsvector('english', content_text));
