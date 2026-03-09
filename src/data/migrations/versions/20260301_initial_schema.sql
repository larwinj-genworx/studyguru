CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(32) PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(30) NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    last_login_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS subjects (
    id VARCHAR(32) PRIMARY KEY,
    owner_id VARCHAR(32) NOT NULL REFERENCES users(id),
    name VARCHAR(200) NOT NULL,
    grade_level VARCHAR(50) NOT NULL,
    description TEXT,
    published BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_subjects_owner_id ON subjects (owner_id);

CREATE TABLE IF NOT EXISTS concepts (
    id VARCHAR(32) PRIMARY KEY,
    subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    material_status VARCHAR(11) NOT NULL,
    material_version INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_concepts_subject_id ON concepts (subject_id);

CREATE TABLE IF NOT EXISTS material_jobs (
    id VARCHAR(32) PRIMARY KEY,
    subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id),
    learner_profile TEXT,
    revision_note TEXT,
    status VARCHAR(9) NOT NULL,
    review_status VARCHAR(14) NOT NULL,
    progress INTEGER NOT NULL,
    artifact_index JSONB NOT NULL,
    errors JSONB NOT NULL,
    reviewer_note TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    reviewed_at TIMESTAMPTZ,
    output_dir VARCHAR(200)
);

CREATE INDEX IF NOT EXISTS ix_material_jobs_subject_id ON material_jobs (subject_id);

CREATE TABLE IF NOT EXISTS material_job_concepts (
    job_id VARCHAR(32) NOT NULL REFERENCES material_jobs(id),
    concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id),
    status VARCHAR(120) NOT NULL,
    artifact_index JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (job_id, concept_id)
);

CREATE TABLE IF NOT EXISTS concept_materials (
    id VARCHAR(32) PRIMARY KEY,
    subject_id VARCHAR(32) NOT NULL REFERENCES subjects(id),
    concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id),
    lifecycle_status VARCHAR(11) NOT NULL,
    version INTEGER NOT NULL,
    source_job_id VARCHAR(32) NOT NULL REFERENCES material_jobs(id),
    artifact_index JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    approved_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    CONSTRAINT uq_concept_version UNIQUE (concept_id, version)
);

CREATE INDEX IF NOT EXISTS ix_concept_materials_subject_id ON concept_materials (subject_id);
CREATE INDEX IF NOT EXISTS ix_concept_materials_concept_id ON concept_materials (concept_id);
CREATE INDEX IF NOT EXISTS ix_concept_materials_source_job_id ON concept_materials (source_job_id);
