ALTER TABLE concept_image_assets
ADD COLUMN IF NOT EXISTS prompt_text TEXT;

ALTER TABLE concept_image_assets
ADD COLUMN IF NOT EXISTS focus_area VARCHAR(200);

ALTER TABLE concept_image_assets
ADD COLUMN IF NOT EXISTS complexity_level VARCHAR(32);

ALTER TABLE concept_image_assets
ADD COLUMN IF NOT EXISTS visual_style VARCHAR(80);

ALTER TABLE concept_image_assets
ADD COLUMN IF NOT EXISTS generator_name VARCHAR(120);

ALTER TABLE concept_image_assets
ADD COLUMN IF NOT EXISTS explanation TEXT;

ALTER TABLE concept_image_assets
ADD COLUMN IF NOT EXISTS learning_points JSONB NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE concept_image_assets
ADD COLUMN IF NOT EXISTS render_spec JSONB NOT NULL DEFAULT '{}'::jsonb;
