from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.settings import database_path


JSON_COLUMNS = {
    "runs": {"config_json", "input_json", "final_json"},
    "evidence": {"extra_json"},
    "signals": {"evidence_ids_json"},
    "requirements": {"signal_ids_json", "score_breakdown_json", "assumptions_json", "uncertainties_json"},
    "audit_events": {"actor_json", "before_json", "after_json", "input_refs_json"},
    "simulations": {"results_json"},
}


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads(value: str | None, default: Any = None) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                parent_run_id TEXT,
                profile_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'complete',
                replay_from TEXT,
                config_json TEXT NOT NULL,
                input_json TEXT NOT NULL,
                final_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evidence (
                run_id TEXT NOT NULL REFERENCES runs(id),
                id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_ref TEXT NOT NULL,
                market TEXT NOT NULL,
                model TEXT NOT NULL,
                date TEXT NOT NULL,
                text_or_value TEXT NOT NULL,
                reliability REAL NOT NULL,
                in_scope INTEGER NOT NULL,
                exclusion_reason TEXT,
                extra_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (run_id, id)
            );
            CREATE TABLE IF NOT EXISTS signals (
                run_id TEXT NOT NULL REFERENCES runs(id),
                id TEXT NOT NULL,
                type TEXT NOT NULL,
                theme TEXT NOT NULL,
                category TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                mention_count INTEGER NOT NULL,
                share_of_feedback REAL NOT NULL,
                evidence_ids_json TEXT NOT NULL,
                confidence REAL NOT NULL,
                satisfaction_index INTEGER NOT NULL DEFAULT 50,
                summary TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (run_id, id)
            );
            CREATE TABLE IF NOT EXISTS requirements (
                run_id TEXT NOT NULL REFERENCES runs(id),
                id TEXT NOT NULL,
                text TEXT NOT NULL,
                category TEXT NOT NULL,
                signal_ids_json TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                score_breakdown_json TEXT NOT NULL DEFAULT '{}',
                rationale TEXT NOT NULL DEFAULT '',
                evidence_level TEXT NOT NULL DEFAULT 'weak',
                assumptions_json TEXT NOT NULL DEFAULT '[]',
                uncertainties_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'proposed',
                version INTEGER NOT NULL DEFAULT 1,
                parent_id TEXT,
                target_spec TEXT,
                specification_status TEXT NOT NULL DEFAULT 'not_started',
                PRIMARY KEY (run_id, id)
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id),
                ts TEXT NOT NULL,
                actor_json TEXT NOT NULL,
                action TEXT NOT NULL,
                target_id TEXT NOT NULL,
                before_json TEXT,
                after_json TEXT,
                rationale TEXT NOT NULL,
                input_refs_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS vectors (
                run_id TEXT NOT NULL,
                evidence_id TEXT NOT NULL,
                vector_json TEXT NOT NULL,
                vector_kind TEXT NOT NULL,
                PRIMARY KEY (run_id, evidence_id)
            );
            CREATE TABLE IF NOT EXISTS simulations (
                id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES runs(id),
                results_json TEXT NOT NULL,
                include_in_score INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_evidence_run ON evidence(run_id, source_type, in_scope);
            CREATE INDEX IF NOT EXISTS idx_signals_run ON signals(run_id, category, theme);
            CREATE INDEX IF NOT EXISTS idx_requirements_run ON requirements(run_id, category, score DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_events(run_id, ts);
            CREATE TRIGGER IF NOT EXISTS audit_no_update
            BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS audit_no_delete
            BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
            """
        )
        signal_columns = {row["name"] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
        if "satisfaction_index" not in signal_columns:
            conn.execute("ALTER TABLE signals ADD COLUMN satisfaction_index INTEGER NOT NULL DEFAULT 50")
        requirement_columns = {row["name"] for row in conn.execute("PRAGMA table_info(requirements)").fetchall()}
        if "specification_status" not in requirement_columns:
            conn.execute("ALTER TABLE requirements ADD COLUMN specification_status TEXT NOT NULL DEFAULT 'not_started'")


def decode_row(table: str, row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    item = dict(row)
    for column in JSON_COLUMNS.get(table, set()):
        if column in item:
            item[column.removesuffix("_json")] = loads(item.pop(column), {})
    if table == "evidence":
        item["in_scope"] = bool(item["in_scope"])
        item["extra"] = item.pop("extra", {})
    if table == "simulations":
        item["include_in_score"] = bool(item["include_in_score"])
    return item


def list_rows(table: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [decode_row(table, row) or {} for row in rows]


def get_row(table: str, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return decode_row(table, row)
