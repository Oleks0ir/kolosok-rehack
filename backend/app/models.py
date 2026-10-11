from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class NodeType(str, Enum):
    SOURCE = "Source"
    EVIDENCE = "Evidence"
    CLAIM = "Claim"
    ASSUMPTION = "Assumption"
    QUESTION = "Question"
    REQUIREMENT = "Requirement"
    SCORE = "Score"
    DECISION = "Decision"
    NOTE = "Note"


# Node types exempt from VISION.md write rule 3 ("every node except Source,
# Question and Note must have inputs").
NO_INPUT_REQUIRED = {NodeType.SOURCE, NodeType.QUESTION, NodeType.NOTE}

ID_PREFIX = {
    NodeType.SOURCE: "SRC",
    NodeType.EVIDENCE: "EVD",
    NodeType.CLAIM: "CLM",
    NodeType.ASSUMPTION: "ASM",
    NodeType.QUESTION: "QST",
    NodeType.REQUIREMENT: "REQ",
    NodeType.SCORE: "SCR",
    NodeType.DECISION: "DEC",
    NodeType.NOTE: "NOTE",
}


class Relation(str, Enum):
    DERIVED_FROM = "derived_from"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    SCORES = "scores"
    DECIDES = "decides"


class Node(BaseModel):
    id: str
    type: NodeType
    content: dict[str, Any]
    created_by: str
    method: Optional[str] = None
    rationale: Optional[str] = None
    timestamp: datetime
    version: int
    replaces: Optional[str] = None
    status: str


class Edge(BaseModel):
    from_id: str
    to_id: str
    relation: Relation
