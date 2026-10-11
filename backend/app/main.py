"""HTTP contract for the decision graph — the data-transit layer between the
Python core and the GUI / agent-loop / ingestion modules (each built
independently against this API, see VISION.md).
"""

from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import tools
from .db import init_db
from .graph import get_dependents, get_inputs, get_node, list_nodes
from .models import Node, NodeType

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
    return _handle(tools.web_search, **req.model_dump())


@app.post("/tools/add_claim", response_model=Node)
def api_add_claim(req: AddClaimRequest):
    return _handle(tools.add_claim, **req.model_dump())


@app.post("/tools/add_assumption", response_model=Node)
def api_add_assumption(req: AddAssumptionRequest):
    return _handle(tools.add_assumption, **req.model_dump())


@app.post("/tools/propose_requirement", response_model=Node)
def api_propose_requirement(req: ProposeRequirementRequest):
    return _handle(tools.propose_requirement, **req.model_dump())


@app.post("/tools/score", response_model=Node)
def api_score(req: ScoreRequest):
    return _handle(tools.score, **req.model_dump())


@app.post("/tools/challenge", response_model=Node)
def api_challenge(req: ChallengeRequest):
    return _handle(tools.challenge, **req.model_dump())


@app.post("/tools/ask_pm", response_model=Node)
def api_ask_pm(req: AskPmRequest):
    return _handle(tools.ask_pm, **req.model_dump())


@app.post("/decide", response_model=Node)
def api_decide(req: DecideRequest):
    return _handle(tools.decide, **req.model_dump())
