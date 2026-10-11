-- Decision graph schema (append-only Node/Edge model, see VISION.md).

CREATE TABLE IF NOT EXISTS nodes (
    id         TEXT PRIMARY KEY,
    type       TEXT NOT NULL CHECK (type IN (
        'Source', 'Evidence', 'Claim', 'Assumption', 'Question',
        'Requirement', 'Score', 'Decision', 'Note'
    )),
    content    JSONB NOT NULL,
    created_by TEXT NOT NULL,
    method     TEXT,
    rationale  TEXT,
    timestamp  TIMESTAMPTZ NOT NULL DEFAULT now(),
    version    INTEGER NOT NULL DEFAULT 1,
    replaces   TEXT REFERENCES nodes(id),
    status     TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'stale'))
);

CREATE TABLE IF NOT EXISTS edges (
    id       SERIAL PRIMARY KEY,
    from_id  TEXT NOT NULL REFERENCES nodes(id),
    to_id    TEXT NOT NULL REFERENCES nodes(id),
    relation TEXT NOT NULL CHECK (relation IN (
        'derived_from', 'supports', 'contradicts', 'scores', 'decides'
    ))
);

CREATE INDEX IF NOT EXISTS idx_edges_from ON edges(from_id);
CREATE INDEX IF NOT EXISTS idx_edges_to ON edges(to_id);

-- Append-only enforcement: nodes can never be deleted; the only column an
-- UPDATE may ever touch is `status` (stale propagation, see VISION.md
-- "Going back (propagation)"). Everything else is a new row via add_node.
CREATE OR REPLACE FUNCTION nodes_block_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'nodes are append-only: delete not allowed';
    END IF;
    IF NEW.id <> OLD.id OR NEW.type <> OLD.type
        OR NEW.content IS DISTINCT FROM OLD.content
        OR NEW.created_by <> OLD.created_by
        OR NEW.method IS DISTINCT FROM OLD.method
        OR NEW.rationale IS DISTINCT FROM OLD.rationale
        OR NEW.timestamp <> OLD.timestamp
        OR NEW.version <> OLD.version
        OR NEW.replaces IS DISTINCT FROM OLD.replaces THEN
        RAISE EXCEPTION 'nodes are append-only: only status may change';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS nodes_append_only ON nodes;
CREATE TRIGGER nodes_append_only
    BEFORE UPDATE OR DELETE ON nodes
    FOR EACH ROW EXECUTE FUNCTION nodes_block_mutation();

CREATE OR REPLACE FUNCTION edges_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'edges are append-only: update/delete not allowed';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS edges_append_only ON edges;
CREATE TRIGGER edges_append_only
    BEFORE UPDATE OR DELETE ON edges
    FOR EACH ROW EXECUTE FUNCTION edges_block_mutation();
