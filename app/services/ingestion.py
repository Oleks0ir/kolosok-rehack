from __future__ import annotations

import csv
import io
import json
import re
from datetime import date
from typing import Any

from app.models import EvidenceInput, EvidenceItem


TEXT_FIELDS = ("text_or_value", "text", "feedback", "comment", "quote", "statement", "review", "value")


def _reliability(value: Any) -> float:
    try:
        parsed = float(value)
        if parsed > 1:
            parsed /= 100
        return min(1.0, max(0.0, parsed))
    except (TypeError, ValueError):
        return 0.7


def _mark_scope(item: EvidenceItem, profile: dict[str, Any]) -> EvidenceItem:
    text = item.text_or_value.lower()
    exclusions = profile.get("scope_exclusions", [])
    reason = next((word for word in exclusions if word.lower() in text), None)
    if reason:
        item.in_scope = False
        item.exclusion_reason = f"Out of customer-requirements scope: {reason}"
    return item


def _from_record(record: dict[str, Any], fallback_type: str, index: int, profile: dict[str, Any]) -> EvidenceItem | None:
    lower = {str(k).strip().lower(): v for k, v in record.items() if k is not None}
    text = next((lower.get(key) for key in TEXT_FIELDS if lower.get(key) not in (None, "")), None)
    if text is None:
        text = " | ".join(f"{k}: {v}" for k, v in lower.items() if v not in (None, ""))
    text = str(text).strip()
    if not text:
        return None
    raw_type = str(lower.get("source_type") or fallback_type).lower().strip()
    if raw_type not in {"feedback", "sales", "equipment", "study", "web"}:
        raw_type = fallback_type
    item = EvidenceItem(
        source_type=raw_type,
        source_ref=str(lower.get("source_ref") or lower.get("source") or lower.get("id") or f"Imported item {index}"),
        market=str(lower.get("market") or profile.get("market", "Germany")),
        model=str(lower.get("model") or profile.get("model", "BMW 5 Series")),
        date=str(lower.get("date") or lower.get("timestamp") or date.today().isoformat())[:32],
        text_or_value=text,
        reliability=_reliability(lower.get("reliability", 0.7)),
    )
    return _mark_scope(item, profile)


def parse_inputs(
    evidence: list[EvidenceInput],
    raw_text: str | None,
    file_name: str | None,
    fallback_type: str,
    profile: dict[str, Any],
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for index, row in enumerate(evidence, start=1):
        item = EvidenceItem(
            source_type=row.source_type,
            source_ref=row.source_ref or f"Manual input {index}",
            market=row.market or profile.get("market", "Germany"),
            model=row.model or profile.get("model", "BMW 5 Series"),
            date=row.date or date.today().isoformat(),
            text_or_value=row.text_or_value,
            reliability=row.reliability,
        )
        items.append(_mark_scope(item, profile))

    if raw_text:
        suffix = (file_name or "").lower()
        lines = raw_text.splitlines()
        first_line = lines[0] if lines else ""
        parsed_records: list[dict[str, Any]] = []
        try:
            if suffix.endswith(".json") or raw_text.lstrip().startswith(("[", "{")):
                loaded = json.loads(raw_text)
                parsed_records = loaded if isinstance(loaded, list) else loaded.get("items", [loaded])
            elif suffix.endswith(".csv") or "," in first_line:
                parsed_records = list(csv.DictReader(io.StringIO(raw_text.lstrip("\ufeff"))))
        except (json.JSONDecodeError, AttributeError, csv.Error):
            parsed_records = []
        if parsed_records:
            items.extend(
                item for i, record in enumerate(parsed_records, start=len(items) + 1)
                if isinstance(record, dict) and (item := _from_record(record, fallback_type, i, profile)) is not None
            )
        else:
            text_lines = [re.sub(r"^\s*[-*•]\s*", "", line).strip() for line in lines]
            text_lines = [line for line in text_lines if len(line) >= 12]
            if not text_lines and raw_text.strip():
                text_lines = [raw_text.strip()]
            items.extend(
                item for i, line in enumerate(text_lines, start=len(items) + 1)
                if (item := _from_record(
                    {"text": line, "source_ref": f"{file_name or 'Pasted text'} · {i}"},
                    fallback_type,
                    i,
                    profile,
                ))
            )
    return items


def demo_items(profile: dict[str, Any]) -> list[EvidenceItem]:
    from app.settings import PROJECT_ROOT

    text = (PROJECT_ROOT / "data" / "demo_feedback.csv").read_text(encoding="utf-8")
    return [
        item for index, record in enumerate(csv.DictReader(io.StringIO(text)), start=1)
        if (item := _from_record(record, "feedback", index, profile)) is not None
    ]
