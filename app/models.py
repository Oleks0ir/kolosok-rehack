from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


SourceType = Literal["feedback", "sales", "equipment", "study", "web"]
EvidenceLevel = Literal["strong", "moderate", "weak", "assumption_based"]
RequirementStatus = Literal["proposed", "approved", "rejected", "edited", "challenged"]
SpecificationStatus = Literal["not_started", "proposed", "approved"]


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10].upper()}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("EVD"))
    source_type: SourceType = "feedback"
    source_ref: str = ""
    market: str = "Germany"
    model: str = "BMW 5 Series"
    date: str = Field(default_factory=lambda: date.today().isoformat())
    text_or_value: str
    reliability: float = Field(default=0.7, ge=0.0, le=1.0)
    in_scope: bool = True
    exclusion_reason: str | None = None


class Signal(BaseModel):
    id: str = Field(default_factory=lambda: new_id("SIG"))
    type: Literal["complaint", "unmet_need", "competitor_edge", "trend", "praise"]
    theme: str
    category: str
    sentiment: Literal["positive", "negative", "mixed", "neutral"]
    mention_count: int = Field(ge=1)
    share_of_feedback: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    satisfaction_index: int = Field(default=50, ge=0, le=100)
    summary: str = ""


class Requirement(BaseModel):
    id: str = Field(default_factory=lambda: new_id("REQ"))
    text: str
    category: str
    signal_ids: list[str] = Field(default_factory=list)
    score: int = Field(default=0, ge=0, le=100)
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    evidence_level: EvidenceLevel = "weak"
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    status: RequirementStatus = "proposed"
    version: int = 1
    parent_id: str | None = None
    target_spec: str | None = None
    specification_status: SpecificationStatus = "not_started"


class AuditEvent(BaseModel):
    id: str = Field(default_factory=lambda: new_id("AUD"))
    ts: str = Field(default_factory=utc_now)
    actor: dict[str, str] = Field(default_factory=lambda: {"type": "ai", "name": "workbench"})
    action: str
    target_id: str
    before: Any = None
    after: Any = None
    rationale: str = ""
    input_refs: list[str] = Field(default_factory=list)


class EvidenceInput(BaseModel):
    source_type: SourceType = "feedback"
    source_ref: str = ""
    market: str | None = None
    model: str | None = None
    date: str | None = None
    text_or_value: str
    reliability: float = Field(default=0.7, ge=0.0, le=1.0)


class RunRequest(BaseModel):
    profile_id: str = "bmw_5_series_germany"
    evidence: list[EvidenceInput] = Field(default_factory=list)
    raw_text: str | None = None
    file_name: str | None = None
    source_type: SourceType = "feedback"
    include_web: bool = False


class ReplayRequest(BaseModel):
    start_at: Literal["M1", "M2", "M3", "M4", "M5"] = "M3"
    config_overrides: dict[str, Any] = Field(default_factory=dict)


class DecisionRequest(BaseModel):
    action: Literal["approve", "reject", "edit", "challenge"]
    comment: str = Field(min_length=2, max_length=2000)
    edited_text: str | None = None
    actor_name: str = Field(default="Product Manager", min_length=1, max_length=120)


class SpecificationRequest(BaseModel):
    target_spec: str | None = None
    approve: bool = False
    comment: str = Field(min_length=2, max_length=2000)
    actor_name: str = Field(default="Product Manager", min_length=1, max_length=120)


class SimulationRequest(BaseModel):
    options: dict[str, str] = Field(default_factory=dict)
    include_in_score: bool = False
    actor_name: str = Field(default="Product Manager", min_length=1, max_length=120)


class FinalizeRequest(BaseModel):
    requirement_ids: list[str] = Field(default_factory=list)
    comment: str = Field(min_length=2, max_length=2000)
    actor_name: str = Field(default="Product Manager", min_length=1, max_length=120)
