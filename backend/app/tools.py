"""The 8 agent tools from VISION.md, plus the PM-only `decide`.

Each tool is a thin wrapper over add_node(): it fixes the node type and edge
relation the tool is allowed to write, nothing else. query_data/web_search
only record a result that was already produced elsewhere (the BMW file
search and the web search call itself are the ingestion/agent-loop teams'
job, out of scope here) — callers pass the result in as `content`.
"""

from typing import Any, Optional

from .graph import add_node, downstream_ids, get_node, list_edges, list_nodes
from .models import Node, NodeType, Relation


def import_source(content: dict[str, Any], created_by: str, method: Optional[str] = None, rationale: Optional[str] = None) -> Node:
    """Record one input data file/document as a Source node (used by ingestion)."""
    return add_node(NodeType.SOURCE, content, [], created_by, method, rationale)


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


def edit(content: dict[str, Any], target_id: str, created_by: str, rationale: Optional[str] = None,
         add_inputs: Optional[list[str]] = None) -> Node:
    """PM-only: write a new version of target_id (same type, inputs and relation, new content).
    add_inputs connects extra input nodes — edges are append-only, so connecting is a new
    version too. add_node's `replaces` marks the old version and everything built on it stale."""
    if not created_by.startswith("PM:"):
        raise PermissionError("only the PM can edit nodes")
    target = get_node(target_id)
    if target is None:
        raise ValueError(f"no such node: {target_id}")
    if any(n.replaces == target_id for n in list_nodes(target.type)):
        raise ValueError(f"{target_id} already has a newer version; edit that one")
    edges = list_edges(target_id)
    inputs = [e["to_id"] for e in edges]
    if add_inputs:
        loop = set(add_inputs) & downstream_ids(target_id)
        if loop:
            raise ValueError(f"{', '.join(sorted(loop))} is built on {target_id}; connecting would create a loop")
        inputs += [i for i in add_inputs if i not in inputs]
    relation = Relation(edges[0]["relation"]) if edges else Relation.DERIVED_FROM
    return add_node(target.type, content, inputs, created_by,
                    target.method, rationale, relation=relation, replaces=target_id)


PM_CREATABLE = {NodeType.SOURCE, NodeType.EVIDENCE, NodeType.CLAIM, NodeType.ASSUMPTION,
                NodeType.REQUIREMENT, NodeType.QUESTION, NodeType.NOTE}


def create(type: NodeType, content: dict[str, Any], inputs: list[str], created_by: str,
           rationale: Optional[str] = None, relation: Relation = Relation.DERIVED_FROM) -> Node:
    """PM-only: add a node by hand (GUI). Scores need the formula (`score`), Decisions `decide`."""
    if not created_by.startswith("PM:"):
        raise PermissionError("only the PM can create nodes by hand")
    if NodeType(type) not in PM_CREATABLE:
        raise ValueError(f"{NodeType(type).value} nodes can't be created by hand")
    if Relation(relation) not in (Relation.DERIVED_FROM, Relation.SUPPORTS, Relation.CONTRADICTS):
        raise ValueError(f"relation {Relation(relation).value} can't be set by hand")
    return add_node(type, content, inputs, created_by, None, rationale, relation=Relation(relation))
