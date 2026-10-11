"""The 8 agent tools from VISION.md, plus the PM-only `decide`.

Each tool is a thin wrapper over add_node(): it fixes the node type and edge
relation the tool is allowed to write, nothing else. query_data/web_search
only record a result that was already produced elsewhere (the BMW file
search and the web search call itself are the ingestion/agent-loop teams'
job, out of scope here) — callers pass the result in as `content`.
"""

from typing import Any, Optional

from .graph import add_node
from .models import Node, NodeType, Relation


def query_data(content: dict[str, Any], source_ids: list[str], created_by: str, method: Optional[str] = None, rationale: Optional[str] = None) -> Node:
    return add_node(NodeType.EVIDENCE, content, source_ids, created_by, method, rationale)


def web_search(content: dict[str, Any], inputs: list[str], created_by: str, method: Optional[str] = None, rationale: Optional[str] = None) -> Node:
    return add_node(NodeType.EVIDENCE, content, inputs, created_by, method, rationale)


def add_claim(content: dict[str, Any], evidence_ids: list[str], created_by: str, method: Optional[str] = None, rationale: Optional[str] = None) -> Node:
    return add_node(NodeType.CLAIM, content, evidence_ids, created_by, method, rationale)


def add_assumption(content: dict[str, Any], inputs: list[str], created_by: str, method: Optional[str] = None, rationale: Optional[str] = None) -> Node:
    return add_node(NodeType.ASSUMPTION, content, inputs, created_by, method, rationale)


def propose_requirement(content: dict[str, Any], claim_ids: list[str], created_by: str, method: Optional[str] = None, rationale: Optional[str] = None) -> Node:
    return add_node(NodeType.REQUIREMENT, content, claim_ids, created_by, method, rationale)


def score(content: dict[str, Any], target_id: str, formula: str, created_by: str, rationale: Optional[str] = None) -> Node:
    return add_node(NodeType.SCORE, content, [target_id], created_by, formula, rationale, relation=Relation.SCORES)


def challenge(content: dict[str, Any], target_id: str, created_by: str, method: Optional[str] = None, rationale: Optional[str] = None) -> Node:
    return add_node(NodeType.EVIDENCE, content, [target_id], created_by, method, rationale, relation=Relation.CONTRADICTS)


def ask_pm(content: dict[str, Any], inputs: Optional[list[str]], created_by: str, method: Optional[str] = None, rationale: Optional[str] = None) -> Node:
    return add_node(NodeType.QUESTION, content, inputs or [], created_by, method, rationale)


def decide(content: dict[str, Any], target_id: str, created_by: str, rationale: Optional[str] = None) -> Node:
    """PM-only: approve/reject/postpone/edit a node, with reason."""
    return add_node(NodeType.DECISION, content, [target_id], created_by, None, rationale, relation=Relation.DECIDES)
