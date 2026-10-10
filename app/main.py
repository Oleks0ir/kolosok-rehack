from __future__ import annotations

import csv
import io
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app import db
from app.models import (
    DecisionRequest,
    FinalizeRequest,
    ReplayRequest,
    RunRequest,
    SimulationRequest,
    SpecificationRequest,
)
from app.profiles import load_profile
from app.services import decisions, pipeline
from app.services.embeddings import cosine, query_vector
from app.services.llm import configured as llm_configured
from app.settings import PROJECT_ROOT, env


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    yield


app = FastAPI(
    title="BMW Product Decision Workbench",
    description="Traceable customer evidence, prioritized product requirements and human PM gates.",
    version="1.0.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static")


def _run_or_404(run_id: str) -> dict[str, Any]:
    result = pipeline.get_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Run not found")
    return result


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "app" / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict[str, Any]:
    return {
        "llm_enabled": llm_configured(),
        "web_search_enabled": bool(env("TAVILY_API_KEY")),
        "model": env("OPENAI_MODEL", "gpt-6-luna") if llm_configured() else "local rules",
        "profile_count": len(list((PROJECT_ROOT / "profiles").glob("*.yaml"))),
        "data_mode": "local-first",
    }


@app.get("/api/profiles")
def profiles() -> list[dict[str, Any]]:
    output = []
    for path in sorted((PROJECT_ROOT / "profiles").glob("*.yaml")):
        profile = load_profile(path.stem)
        output.append({
            "id": profile["id"],
            "label": profile["label"],
            "model": profile["model"],
            "market": profile["market"],
            "categories": profile["categories"],
            "weights": profile["weights"],
            "context_rules": profile["context_rules"],
        })
    return output


@app.get("/api/runs")
def runs() -> list[dict[str, Any]]:
    return pipeline.list_runs()


@app.get("/api/runs/latest")
def latest_run() -> dict[str, Any]:
    run_id = pipeline.latest_run_id()
    return {"run": _run_or_404(run_id)} if run_id else {"run": None}


@app.post("/api/runs")
def create_run(request: RunRequest) -> dict[str, Any]:
    try:
        return pipeline.create_run(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/demo")
def create_demo() -> dict[str, Any]:
    try:
        return pipeline.create_run(RunRequest())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    return _run_or_404(run_id)


@app.post("/api/runs/{run_id}/replay")
def replay(run_id: str, request: ReplayRequest) -> dict[str, Any]:
    try:
        result = pipeline.replay_run(run_id, request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result


@app.post("/api/requirements/{requirement_id}/decision")
def decision(requirement_id: str, request: DecisionRequest) -> dict[str, Any]:
    try:
        return decisions.decide(requirement_id, request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/requirements/{requirement_id}/specification")
def specification(requirement_id: str, request: SpecificationRequest) -> dict[str, Any]:
    try:
        return decisions.specify(requirement_id, request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/runs/{run_id}/simulation")
def simulation(run_id: str, request: SimulationRequest) -> dict[str, Any]:
    try:
        return decisions.simulate_run(run_id, request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/api/runs/{run_id}/finalize")
def finalize(run_id: str, request: FinalizeRequest) -> dict[str, Any]:
    try:
        return decisions.finalize(run_id, request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/runs/{run_id}/export.csv")
def export_csv(run_id: str) -> Response:
    run = _run_or_404(run_id)
    stream = io.StringIO()
    def safe_cell(value: Any) -> str:
        text = str(value or "")
        return "'" + text if text[:1] in {"=", "+", "-", "@", "\t", "\r"} else text

    columns = [
        "id", "text", "category", "score", "category_rank", "evidence_level", "status",
        "rationale", "assumptions", "uncertainties", "signal_ids",
    ]
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for requirement in run["requirements"]:
        writer.writerow({
            "id": requirement["id"],
            "text": safe_cell(requirement["text"]),
            "category": safe_cell(requirement["category"]),
            "score": requirement["score"],
            "category_rank": requirement.get("score_breakdown", {}).get("category_rank", ""),
            "evidence_level": requirement["evidence_level"],
            "status": requirement["status"],
            "rationale": safe_cell(requirement["rationale"]),
            "assumptions": safe_cell(" | ".join(requirement["assumptions"])),
            "uncertainties": safe_cell(" | ".join(requirement["uncertainties"])),
            "signal_ids": " | ".join(requirement["signal_ids"]),
        })
    filename = f"requirements-{run_id.lower()}.csv"
    return Response(
        content=stream.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/trace/{requirement_id}")
def trace(requirement_id: str) -> dict[str, Any]:
    found = db.get_row("requirements", "SELECT * FROM requirements WHERE id=? ORDER BY rowid DESC LIMIT 1", (requirement_id,))
    if not found:
        raise HTTPException(status_code=404, detail="Requirement not found")
    run = _run_or_404(found["run_id"])
    signals_by_id = {item["id"]: item for item in run["signals"]}
    evidence_by_id = {item["id"]: item for item in run["evidence"]}
    selected_signals = [signals_by_id[item] for item in found["signal_ids"] if item in signals_by_id]
    evidence_ids = {eid for signal in selected_signals for eid in signal["evidence_ids"]}
    selected_evidence = [evidence_by_id[item] for item in evidence_ids if item in evidence_by_id]
    events = [item for item in run["audit_events"] if item["target_id"] == requirement_id]
    return {
        "requirement": found,
        "signals": selected_signals,
        "evidence": selected_evidence,
        "audit_events": events,
    }


@app.get("/api/evidence/search")
def search_evidence(
    run_id: str = Query(min_length=1),
    q: str = Query(min_length=1, max_length=300),
) -> dict[str, Any]:
    run = _run_or_404(run_id)
    vectors = db.list_rows(
        "vectors",
        "SELECT evidence_id,vector_json,vector_kind FROM vectors WHERE run_id=?",
        (run_id,),
    )
    evidence_by_id = {item["id"]: item for item in run["evidence"]}
    if not vectors:
        return {"results": [item for item in run["evidence"] if q.lower() in item["text_or_value"].lower()]}
    kind = vectors[0]["vector_kind"]
    query_embedding = query_vector(q, kind)
    ranked = []
    for row in vectors:
        item = evidence_by_id.get(row["evidence_id"])
        if not item:
            continue
        vector = db.loads(row["vector_json"], [])
        similarity = cosine(query_embedding, vector) if query_embedding else 0.0
        if q.lower() in item["text_or_value"].lower():
            similarity = max(similarity, 0.7)
        ranked.append((similarity, item))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return {"results": [{"similarity": round(score, 3), **item} for score, item in ranked[:20] if score > 0.05]}
