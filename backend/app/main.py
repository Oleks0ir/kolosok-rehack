"""HTTP contract for the decision graph — the data-transit layer between the
Python core and the GUI / agent-loop / ingestion modules (each built
independently against this API, see VISION.md).
"""

import csv
import io
import mimetypes
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent_runner, tools
from .db import init_db
from .graph import get_dependents, get_inputs, get_node, list_edges, list_nodes
from .models import Node, NodeType, Relation

app = FastAPI(title="Decision Graph API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def on_startup():
    init_db()


# ---- reads -----------------------------------------------------------

@app.get("/nodes", response_model=list[Node])
def api_list_nodes(type: Optional[NodeType] = None):
    return list_nodes(type)


@app.get("/nodes/{node_id}", response_model=Node)
def api_get_node(node_id: str):
    node = get_node(node_id)
    if node is None:
        raise HTTPException(404, f"no such node: {node_id}")
    return node


@app.get("/nodes/{node_id}/inputs", response_model=list[Node])
def api_get_inputs(node_id: str):
    return get_inputs(node_id)


@app.get("/nodes/{node_id}/dependents", response_model=list[Node])
def api_get_dependents(node_id: str):
    return get_dependents(node_id)


@app.get("/edges")
def api_list_edges():
    """All edges as {from_id, to_id, relation}; from_id is the newer node, to_id its input."""
    return list_edges()


# ---- writes: the 8 agent tools + PM decide ----------------------------

class QueryDataRequest(BaseModel):
    content: dict[str, Any]
    source_ids: list[str]
    created_by: str
    method: Optional[str] = None
    rationale: Optional[str] = None


class WebSearchRequest(BaseModel):
    content: dict[str, Any]
    inputs: list[str]
    created_by: str
    method: Optional[str] = None
    rationale: Optional[str] = None


class AddClaimRequest(BaseModel):
    content: dict[str, Any]
    evidence_ids: list[str]
    created_by: str
    method: Optional[str] = None
    rationale: Optional[str] = None


class AddAssumptionRequest(BaseModel):
    content: dict[str, Any]
    inputs: list[str]
    created_by: str
    method: Optional[str] = None
    rationale: Optional[str] = None


class ProposeRequirementRequest(BaseModel):
    content: dict[str, Any]
    claim_ids: list[str]
    created_by: str
    method: Optional[str] = None
    rationale: Optional[str] = None


class ScoreRequest(BaseModel):
    content: dict[str, Any]
    target_id: str
    formula: str
    created_by: str
    rationale: Optional[str] = None


class ChallengeRequest(BaseModel):
    content: dict[str, Any]
    target_id: str
    created_by: str
    method: Optional[str] = None
    rationale: Optional[str] = None


class AskPmRequest(BaseModel):
    content: dict[str, Any]
    inputs: Optional[list[str]] = None
    created_by: str
    method: Optional[str] = None
    rationale: Optional[str] = None


class ImportSourceRequest(BaseModel):
    content: dict[str, Any]
    created_by: str
    method: Optional[str] = None
    rationale: Optional[str] = None


class DecideRequest(BaseModel):
    content: dict[str, Any]
    target_id: str
    created_by: str
    rationale: Optional[str] = None


def _handle(fn, **kwargs) -> Node:
    try:
        return fn(**kwargs)
    except (ValueError, PermissionError) as e:
        raise HTTPException(400, str(e))


@app.post("/tools/query_data", response_model=Node)
def api_query_data(req: QueryDataRequest):
    return _handle(tools.query_data, **req.model_dump())


@app.post("/tools/web_search", response_model=Node)
def api_web_search(req: WebSearchRequest):
    """Record a web search result (content must include its source url) as Evidence."""
    return _handle(tools.web_search, **req.model_dump())


@app.post("/tools/add_claim", response_model=Node)
def api_add_claim(req: AddClaimRequest):
    return _handle(tools.add_claim, **req.model_dump())


@app.post("/tools/add_assumption", response_model=Node)
def api_add_assumption(req: AddAssumptionRequest):
    """Record a forward-looking guess, explicitly marked as not evidence."""
    return _handle(tools.add_assumption, **req.model_dump())


@app.post("/tools/propose_requirement", response_model=Node)
def api_propose_requirement(req: ProposeRequirementRequest):
    """Turn one or more claims into a customer requirement proposal."""
    return _handle(tools.propose_requirement, **req.model_dump())


@app.post("/tools/score", response_model=Node)
def api_score(req: ScoreRequest):
    return _handle(tools.score, **req.model_dump())


@app.post("/tools/challenge", response_model=Node)
def api_challenge(req: ChallengeRequest):
    """Look for counter-evidence to an existing node; writes Evidence that contradicts it."""
    return _handle(tools.challenge, **req.model_dump())


@app.post("/tools/ask_pm", response_model=Node)
def api_ask_pm(req: AskPmRequest):
    """Stop and ask the PM a question; writes a Question node (no inputs required)."""
    return _handle(tools.ask_pm, **req.model_dump())


@app.post("/tools/import_source", response_model=Node)
def api_import_source(req: ImportSourceRequest):
    return _handle(tools.import_source, **req.model_dump())


@app.post("/decide", response_model=Node)
def api_decide(req: DecideRequest):
    return _handle(tools.decide, **req.model_dump())


class EditRequest(DecideRequest):
    add_inputs: list[str] = []


@app.post("/edit", response_model=Node)
def api_edit(req: EditRequest):
    """PM only: new version of target_id with new content and optionally extra inputs
    (connecting nodes); marks everything built on the old version stale."""
    return _handle(tools.edit, **req.model_dump())


class CreateRequest(BaseModel):
    type: NodeType
    content: dict[str, Any]
    inputs: list[str] = []
    created_by: str
    rationale: Optional[str] = None
    relation: Relation = Relation.DERIVED_FROM


@app.post("/nodes", response_model=Node)
def api_create(req: CreateRequest):
    """PM only: create a Source/Evidence/Claim/Assumption/Requirement/Question/Note by hand."""
    return _handle(tools.create, **req.model_dump())


# ---- GUI helpers: CSV import + starting the agent -----------------------

class ImportCsvRequest(BaseModel):
    filename: str
    text: str
    created_by: str


@app.post("/import/csv", response_model=Node)
def api_import_csv(req: ImportCsvRequest):
    """Record an uploaded CSV as one Source node with its rows (VISION.md: one Source per file)."""
    rows = list(csv.DictReader(io.StringIO(req.text.lstrip("﻿"))))  # Excel adds a BOM
    if not rows:
        raise HTTPException(400, "the CSV has no data rows")
    return _handle(tools.import_source, content={"file": req.filename, "rows": rows},
                   created_by=req.created_by, rationale="imported from the GUI")


class AgentRunRequest(BaseModel):
    max_actions: int = Field(5, ge=1, le=20)


@app.post("/agent/run")
def api_agent_run(req: AgentRunRequest):
    """Start agent-loop/loop.py in the background; 409 if a run is already going."""
    try:
        agent_runner.start(req.max_actions)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return agent_runner.status()


@app.get("/agent/status")
def api_agent_status():
    """{running, exit_code, llm, log}: llm is false when OPENAI_API_KEY isn't set (rule-based run)."""
    return agent_runner.status()


# ---- GUI (gui/ at the repo root), same origin so no CORS needed --------

# Windows' registry can map .js to text/plain, which browsers refuse for module scripts.
mimetypes.add_type("text/javascript", ".js")
app.mount("/ui", StaticFiles(directory=Path(__file__).resolve().parents[2] / "gui", html=True), name="ui")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/ui/")
