CREATE TABLE IF NOT EXISTS concept_video_feedback (
    concept_id VARCHAR(32) NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    video_id VARCHAR(32) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'rejected',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (concept_id, video_id)
);
