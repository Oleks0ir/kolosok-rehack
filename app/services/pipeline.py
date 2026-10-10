from __future__ import annotations

from typing import Any

from app import db
from app.models import (
    AuditEvent,
    EvidenceItem,
    Requirement,
    ReplayRequest,
    RunRequest,
    Signal,
    new_id,
    utc_now,
)
from app.profiles import apply_overrides, load_profile
from app.services.embeddings import vectors_for
from app.services.ingestion import demo_items, parse_inputs
from app.services.requirements import draft_requirements
from app.services.scoring import score_requirements
from app.services.signals import extract_signals
from app.services.llm import configured as llm_configured
from app.services.web_enrichment import search_web
from app.settings import env


STAGES = ("M1", "M2", "M3", "M4", "M5")


def _audit(
    run_id: str,
    action: str,
    target_id: str,
    rationale: str,
    actor: dict[str, str] | None = None,
    before: Any = None,
    after: Any = None,
    input_refs: list[str] | None = None,
) -> None:
    event = AuditEvent(
        actor=actor or {
            "type": "ai",
            "name": "workbench",
            "model_version": env("OPENAI_MODEL", "gpt-6-luna") if llm_configured() else "rules-v1",
        },
        action=action,
        target_id=target_id,
        before=before,
        after=after,
        rationale=rationale,
        input_refs=input_refs or [],
    )
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO audit_events(id,run_id,ts,actor_json,action,target_id,before_json,after_json,rationale,input_refs_json) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                event.id,
                run_id,
                event.ts,
                db.dumps(event.actor),
                event.action,
                event.target_id,
                db.dumps(event.before) if event.before is not None else None,
                db.dumps(event.after) if event.after is not None else None,
                event.rationale,
                db.dumps(event.input_refs),
            ),
        )


def _store_evidence(run_id: str, evidence: list[EvidenceItem]) -> None:
    if not evidence:
        return
    with db.connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO evidence(run_id,id,source_type,source_ref,market,model,date,text_or_value,"
            "reliability,in_scope,exclusion_reason,extra_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    run_id, item.id, item.source_type, item.source_ref, item.market, item.model, item.date,
                    item.text_or_value, item.reliability, int(item.in_scope), item.exclusion_reason, "{}",
                )
                for item in evidence
            ],
        )


def _index_evidence(run_id: str, evidence: list[EvidenceItem]) -> str:
    items = [item for item in evidence if item.in_scope]
    if not items:
        return "No in-scope evidence to index."
    vectors, kind = vectors_for([item.text_or_value for item in items])
    with db.connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO vectors(run_id,evidence_id,vector_json,vector_kind) VALUES(?,?,?,?)",
            [(run_id, item.id, db.dumps(vector), kind) for item, vector in zip(items, vectors)],
        )
    return kind


def _store_signals(run_id: str, signals: list[Signal]) -> None:
    with db.connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO signals(run_id,id,type,theme,category,sentiment,mention_count,share_of_feedback,"
            "evidence_ids_json,confidence,satisfaction_index,summary) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    run_id, item.id, item.type, item.theme, item.category, item.sentiment, item.mention_count,
                    item.share_of_feedback, db.dumps(item.evidence_ids), item.confidence,
                    item.satisfaction_index, item.summary,
                )
                for item in signals
            ],
        )


def _store_requirements(run_id: str, requirements: list[Requirement]) -> None:
    with db.connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO requirements(run_id,id,text,category,signal_ids_json,score,score_breakdown_json,"
            "rationale,evidence_level,assumptions_json,uncertainties_json,status,version,parent_id,target_spec,specification_status) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    run_id, item.id, item.text, item.category, db.dumps(item.signal_ids), item.score,
                    db.dumps(item.score_breakdown), item.rationale, item.evidence_level, db.dumps(item.assumptions),
                    db.dumps(item.uncertainties), item.status, item.version, item.parent_id, item.target_spec,
                    item.specification_status,
                )
                for item in requirements
            ],
        )


def _stage_event(run_id: str, stage: str, result: list[Any], reason: str, refs: list[str]) -> None:
    _audit(
        run_id,
        f"{stage}.completed",
        run_id,
        reason,
        after={"count": len(result)},
        input_refs=refs,
    )


def _run_module(run_id: str, stage: str, profile: dict[str, Any], include_web: bool) -> None:
    if stage == "M2":
        items: list[EvidenceItem] = []
        reason = "Web enrichment is disabled for this run."
        if include_web:
            items, reason = search_web(profile.get("search_queries", []), profile)
            for item in items:
                lowered = item.text_or_value.lower()
                excluded = next((term for term in profile.get("scope_exclusions", []) if term.lower() in lowered), None)
                if excluded:
                    item.in_scope = False
                    item.exclusion_reason = f"Out of customer-requirements scope: {excluded}"
            _store_evidence(run_id, items)
            vector_kind = _index_evidence(run_id, items)
            if items:
                reason = f"{reason} Vector index: {vector_kind}."
        _stage_event(run_id, stage, items, reason, [item.id for item in items])
        return

    evidence = [
        EvidenceItem(**row)
        for row in db.list_rows("evidence", "SELECT * FROM evidence WHERE run_id=? ORDER BY rowid", (run_id,))
    ]
    if stage == "M3":
        signals = extract_signals(evidence, profile)
        _store_signals(run_id, signals)
        _stage_event(run_id, stage, signals, "Evidence classified and clustered into traceable customer signals; satisfaction index includes positive and negative mentions.", [item.id for item in evidence if item.in_scope])
    elif stage == "M4":
        signals = [Signal(**row) for row in db.list_rows("signals", "SELECT * FROM signals WHERE run_id=? ORDER BY rowid", (run_id,))]
        requirements = draft_requirements(signals, evidence, profile)
        _store_requirements(run_id, requirements)
        _stage_event(run_id, stage, requirements, "Customer-facing draft requirements created with assumptions and uncertainty separated.", [item.id for item in signals])
    elif stage == "M5":
        signals = [Signal(**row) for row in db.list_rows("signals", "SELECT * FROM signals WHERE run_id=? ORDER BY rowid", (run_id,))]
        requirements = [Requirement(**row) for row in db.list_rows("requirements", "SELECT * FROM requirements WHERE run_id=? ORDER BY rowid", (run_id,))]
        scored = score_requirements(requirements, signals, evidence, profile)
        _store_requirements(run_id, scored)
        _stage_event(run_id, stage, scored, "Explainable profile weights applied; evidence level remains independent of score.", [item.id for item in requirements])


def _create_run_record(
    run_id: str,
    profile: dict[str, Any],
    source_input: dict[str, Any],
    parent_run_id: str | None = None,
    replay_from: str | None = None,
) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO runs(id,parent_run_id,profile_id,status,replay_from,config_json,input_json,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                run_id, parent_run_id, profile["id"], "running", replay_from,
                db.dumps(profile), db.dumps(source_input), utc_now(),
            ),
        )


def _finish_run(run_id: str) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE runs SET status='complete' WHERE id=?", (run_id,))


def create_run(request: RunRequest) -> dict[str, Any]:
    profile = load_profile(request.profile_id)
    rows = parse_inputs(request.evidence, request.raw_text, request.file_name, request.source_type, profile)
    if not rows and not request.raw_text and not request.evidence:
        rows = demo_items(profile)
    if not rows:
        raise ValueError("Add evidence or use the included demo dataset.")
    run_id = new_id("RUN")
    source_input = request.model_dump(mode="json")
    _create_run_record(run_id, profile, source_input)
    _audit(run_id, "run.created", run_id, "Pipeline run started.", after={"profile_id": profile["id"]})
    _store_evidence(run_id, rows)
    vector_kind = _index_evidence(run_id, rows)
    _stage_event(run_id, "M1", rows, f"Normalized {len(rows)} input evidence item(s); excluded out-of-scope items remain visible. Vector index: {vector_kind}.", [row.id for row in rows])
    include_web = request.include_web
    _run_module(run_id, "M2", profile, include_web)
    _run_module(run_id, "M3", profile, include_web)
    _run_module(run_id, "M4", profile, include_web)
    _run_module(run_id, "M5", profile, include_web)
    _finish_run(run_id)
    return get_run(run_id) or {}


def replay_run(run_id: str, request: ReplayRequest) -> dict[str, Any]:
    parent = db.get_row("runs", "SELECT * FROM runs WHERE id=?", (run_id,))
    if not parent:
        raise ValueError("Run not found")
    start_at = request.start_at
    parent_config = parent.get("config", {})
    profile = apply_overrides(load_profile(parent["profile_id"]), request.config_overrides)
    if "weights" not in request.config_overrides:
        profile["weights"] = parent_config.get("weights", profile["weights"])
    profile = {**parent_config, **profile}
    new_run_id = new_id("RUN")
    _create_run_record(new_run_id, profile, parent.get("input", {}), run_id, start_at)
    _audit(
        new_run_id,
        "run.replayed",
        new_run_id,
        f"Replayed from {start_at}; parent branch {run_id} is retained.",
        after={"parent_run_id": run_id, "start_at": start_at, "config_overrides": request.config_overrides},
    )
    start_index = STAGES.index(start_at)
    if start_at == "M1":
        original = RunRequest(**parent.get("input", {}))
        rows = parse_inputs(original.evidence, original.raw_text, original.file_name, original.source_type, profile)
        if not rows:
            rows = demo_items(profile)
        _store_evidence(new_run_id, rows)
        vector_kind = _index_evidence(new_run_id, rows)
        _stage_event(new_run_id, "M1", rows, f"Replay normalized input data. Vector index: {vector_kind}.", [row.id for row in rows])
    else:
        evidence_rows = db.list_rows("evidence", "SELECT * FROM evidence WHERE run_id=? ORDER BY rowid", (run_id,))
        if start_at == "M2":
            evidence_rows = [row for row in evidence_rows if row["source_type"] != "web"]
        copied = [EvidenceItem(**row) for row in evidence_rows]
        _store_evidence(new_run_id, copied)
        with db.connect() as conn:
            if start_at == "M2":
                conn.execute(
                    "INSERT OR REPLACE INTO vectors(run_id,evidence_id,vector_json,vector_kind) "
                    "SELECT ?,v.evidence_id,v.vector_json,v.vector_kind FROM vectors v "
                    "JOIN evidence e ON e.run_id=v.run_id AND e.id=v.evidence_id "
                    "WHERE v.run_id=? AND e.source_type!='web'",
                    (new_run_id, run_id),
                )
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO vectors(run_id,evidence_id,vector_json,vector_kind) "
                    "SELECT ?,evidence_id,vector_json,vector_kind FROM vectors WHERE run_id=?",
                    (new_run_id, run_id),
                )
        if start_index > STAGES.index("M3"):
            signals = db.list_rows("signals", "SELECT * FROM signals WHERE run_id=? ORDER BY rowid", (run_id,))
            _store_signals(new_run_id, [Signal(**row) for row in signals])
        if start_at == "M5":
            requirements = db.list_rows("requirements", "SELECT * FROM requirements WHERE run_id=? ORDER BY rowid", (run_id,))
            branch_requirements = []
            for row in requirements:
                item = Requirement(**row)
                previous_id = item.id
                item.id = new_id("REQ")
                item.parent_id = previous_id
                item.version += 1
                item.status = "proposed"
                branch_requirements.append(item)
            _store_requirements(new_run_id, branch_requirements)
    include_web = bool(parent.get("input", {}).get("include_web", False))
    if "include_web" in request.config_overrides:
        include_web = bool(request.config_overrides["include_web"])
    for stage in STAGES[start_index:]:
        _run_module(new_run_id, stage, profile, include_web)
    _finish_run(new_run_id)
    return get_run(new_run_id) or {}


def get_run(run_id: str) -> dict[str, Any] | None:
    run = db.get_row("runs", "SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        return None
    run["evidence"] = db.list_rows("evidence", "SELECT * FROM evidence WHERE run_id=? ORDER BY rowid", (run_id,))
    run["signals"] = db.list_rows("signals", "SELECT * FROM signals WHERE run_id=? ORDER BY rowid", (run_id,))
    run["requirements"] = db.list_rows("requirements", "SELECT * FROM requirements WHERE run_id=? ORDER BY score DESC, rowid", (run_id,))
    run["audit_events"] = db.list_rows("audit_events", "SELECT * FROM audit_events WHERE run_id=? ORDER BY rowid", (run_id,))
    run["simulations"] = db.list_rows("simulations", "SELECT * FROM simulations WHERE run_id=? ORDER BY created_at", (run_id,))
    return run


def latest_run_id() -> str | None:
    row = db.get_row("runs", "SELECT id FROM runs ORDER BY created_at DESC LIMIT 1")
    return row["id"] if row else None


def list_runs() -> list[dict[str, Any]]:
    rows = db.list_rows("runs", "SELECT * FROM runs ORDER BY created_at DESC")
    for run in rows:
        run["evidence_count"] = db.get_row("runs", "SELECT COUNT(*) AS count FROM evidence WHERE run_id=?", (run["id"],))["count"]
        run["requirement_count"] = db.get_row("runs", "SELECT COUNT(*) AS count FROM requirements WHERE run_id=?", (run["id"],))["count"]
    return rows
