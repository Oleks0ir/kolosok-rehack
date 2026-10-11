PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assets (
    sha256 TEXT PRIMARY KEY,
    extension TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size >= 0),
    content BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    dataset_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset_versions (
    version_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    asset_sha256 TEXT NOT NULL REFERENCES assets(sha256),
    original_filename TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    importer_version TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE (dataset_id, version_number),
    UNIQUE (dataset_id, asset_sha256, importer_version)
);
CREATE TABLE IF NOT EXISTS sheets (
    version_id TEXT NOT NULL REFERENCES dataset_versions(version_id),
    sheet_name TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    column_count INTEGER NOT NULL,
    metadata_json TEXT NOT NULL,
    PRIMARY KEY (version_id, sheet_name)
);
CREATE TABLE IF NOT EXISTS source_rows (
    version_id TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number > 0),
    values_json TEXT NOT NULL,
    cell_metadata_json TEXT NOT NULL,
    PRIMARY KEY (version_id, sheet_name, row_number),
    FOREIGN KEY (version_id, sheet_name) REFERENCES sheets(version_id, sheet_name)
);
CREATE TABLE IF NOT EXISTS reviews (
    version_id TEXT NOT NULL REFERENCES dataset_versions(version_id),
    review_key TEXT NOT NULL,
    source_review_id TEXT NOT NULL,
    review_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    PRIMARY KEY (version_id, review_key),
    UNIQUE (version_id, source_review_id)
);
CREATE TABLE IF NOT EXISTS review_rows (
    version_id TEXT NOT NULL,
    review_key TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    PRIMARY KEY (version_id, review_key, sheet_name, row_number),
    FOREIGN KEY (version_id, review_key) REFERENCES reviews(version_id, review_key),
    FOREIGN KEY (version_id, sheet_name, row_number) REFERENCES source_rows(version_id, sheet_name, row_number)
);
CREATE TABLE IF NOT EXISTS sales_observations (
    observation_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    cell_address TEXT NOT NULL,
    model_group TEXT NOT NULL,
    market TEXT NOT NULL,
    market_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    volume INTEGER NOT NULL CHECK (volume >= 0),
    scenario TEXT NOT NULL DEFAULT 'unspecified',
    FOREIGN KEY (version_id, sheet_name, row_number) REFERENCES source_rows(version_id, sheet_name, row_number),
    UNIQUE (version_id, model_group, market_code, year)
);
CREATE TABLE IF NOT EXISTS study_observations (
    observation_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL,
    sheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL,
    cell_address TEXT NOT NULL,
    metric TEXT NOT NULL,
    response_label TEXT NOT NULL,
    model_code TEXT NOT NULL,
    model_label TEXT NOT NULL,
    region_code TEXT NOT NULL,
    year INTEGER NOT NULL,
    statistic TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    sample_size INTEGER,
    FOREIGN KEY (version_id, sheet_name, row_number) REFERENCES source_rows(version_id, sheet_name, row_number),
    UNIQUE (version_id, sheet_name, cell_address)
);
CREATE TABLE IF NOT EXISTS document_pages (
    version_id TEXT NOT NULL REFERENCES dataset_versions(version_id),
    page_number INTEGER NOT NULL CHECK (page_number > 0),
    extracted_text TEXT NOT NULL,
    extraction_status TEXT NOT NULL,
    PRIMARY KEY (version_id, page_number)
);
CREATE TABLE IF NOT EXISTS import_issues (
    issue_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES dataset_versions(version_id),
    severity TEXT NOT NULL,
    code TEXT NOT NULL,
    location TEXT,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id TEXT PRIMARY KEY,
    version_id TEXT NOT NULL REFERENCES dataset_versions(version_id),
    topics_asset_sha256 TEXT NOT NULL REFERENCES assets(sha256),
    summary_asset_sha256 TEXT NOT NULL REFERENCES assets(sha256),
    attached_at TEXT NOT NULL,
    summary_status TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE (version_id, topics_asset_sha256, summary_asset_sha256),
    UNIQUE (run_id, version_id)
);
CREATE TABLE IF NOT EXISTS analysis_topics (
    run_id TEXT NOT NULL REFERENCES analysis_runs(run_id),
    topic_id TEXT NOT NULL,
    title TEXT NOT NULL,
    review_count INTEGER NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, topic_id)
);
CREATE TABLE IF NOT EXISTS topic_reviews (
    run_id TEXT NOT NULL,
    topic_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    review_key TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    PRIMARY KEY (run_id, topic_id, review_key),
    FOREIGN KEY (run_id, topic_id) REFERENCES analysis_topics(run_id, topic_id),
    FOREIGN KEY (run_id, version_id) REFERENCES analysis_runs(run_id, version_id),
    FOREIGN KEY (version_id, review_key) REFERENCES reviews(version_id, review_key)
);
CREATE TABLE IF NOT EXISTS fragments (
    run_id TEXT NOT NULL,
    fragment_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    review_key TEXT NOT NULL,
    data_json TEXT NOT NULL,
    PRIMARY KEY (run_id, fragment_id),
    FOREIGN KEY (run_id, version_id) REFERENCES analysis_runs(run_id, version_id),
    FOREIGN KEY (version_id, review_key) REFERENCES reviews(version_id, review_key)
);
CREATE INDEX IF NOT EXISTS sales_lookup ON sales_observations(model_group, market_code, year);
CREATE INDEX IF NOT EXISTS studies_lookup ON study_observations(model_code, region_code, year, metric);
CREATE INDEX IF NOT EXISTS reviews_source_id ON reviews(source_review_id);
CREATE VIEW IF NOT EXISTS current_versions AS
SELECT v.* FROM dataset_versions v WHERE v.version_number =
 (SELECT MAX(other.version_number) FROM dataset_versions other WHERE other.dataset_id = v.dataset_id);
CREATE VIEW IF NOT EXISTS current_reviews AS
SELECT r.* FROM reviews r JOIN current_versions v ON r.version_id = v.version_id;
CREATE VIEW IF NOT EXISTS current_sales AS
SELECT r.* FROM sales_observations r JOIN current_versions v ON r.version_id = v.version_id;
CREATE VIEW IF NOT EXISTS current_studies AS
SELECT r.* FROM study_observations r JOIN current_versions v ON r.version_id = v.version_id;
PRAGMA user_version = 1;
