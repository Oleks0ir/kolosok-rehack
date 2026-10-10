from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.models import EvidenceItem, Signal
from app.services.llm import complete_json


THEMES: dict[str, tuple[str, list[str]]] = {
    "voice_assistant": ("Infotainment & digital services", ["voice", "assistant", "speech", "command", "language"]),
    "navigation": ("Infotainment & digital services", ["navigation", "route", "map", "destination"]),
    "connected_app": ("Infotainment & digital services", ["app", "remote", "connected", "climate setting", "locked"]),
    "charging": ("Charging & energy", ["charge", "charging", "range", "electric", "battery", "charging stop"]),
    "seating": ("Comfort & convenience", ["seat", "seating", "adjustment", "profile"]),
    "cabin_quietness": ("Comfort & convenience", ["noise", "quiet", "cabin", "road noise"]),
    "passenger_comfort": ("Comfort & convenience", ["rear passenger", "climate", "charging port", "legroom"]),
    "parking": ("Driver assistance", ["parking", "camera", "garage", "visibility"]),
    "driver_assistance": ("Driver assistance", ["lane", "assistance", "assist", "warning", "unavailable"]),
    "ride_and_handling": ("Vehicle dynamics", ["ride", "handling", "wet road", "smooth", "confident"]),
    "storage": ("Practicality & storage", ["storage", "boot", "trunk", "luggage", "practical"]),
    "ownership": ("Ownership experience", ["service", "dealer", "repair", "ownership", "maintenance"]),
}
NEGATIVE = ("not", "too", "hard", "stressful", "poor", "difficult", "miss", "slow", "long", "issue", "uncomfortable", "fail", "lack", "inconvenient", "misunderstand")
POSITIVE = ("like", "love", "smooth", "comfortable", "great", "confident", "satisfied", "easy", "reliable", "enjoy")


def _classify(text: str) -> dict[str, str]:
    lower = text.lower()
    theme, category = "overall_experience", "Ownership experience"
    for candidate, (label, keywords) in THEMES.items():
        if any(keyword in lower for keyword in keywords):
            theme, category = candidate, label
            break
    negative = any(word in lower for word in NEGATIVE)
    positive = any(word in lower for word in POSITIVE)
    sentiment = "mixed" if positive and negative else "negative" if negative else "positive" if positive else "neutral"
    if any(word in lower for word in ("competitor", "competitors", "rival", "compared with")):
        signal_type = "competitor_edge"
    elif any(word in lower for word in ("expect", "trend", "increasing", "more customers", "future")):
        signal_type = "trend"
    elif sentiment == "negative":
        signal_type = "complaint"
    elif sentiment == "positive":
        signal_type = "praise"
    else:
        signal_type = "unmet_need"
    return {"theme": theme, "category": category, "sentiment": sentiment, "type": signal_type}


def extract_signals(evidence: list[EvidenceItem], profile: dict[str, Any]) -> list[Signal]:
    in_scope = [row for row in evidence if row.in_scope]
    if not in_scope:
        return []
    classified: dict[str, dict[str, str]] = {}
    ai_rows = complete_json(
        "Classify customer evidence for a vehicle product manager. Return only JSON: "
        '{"items":[{"evidence_id":"...","type":"complaint|unmet_need|competitor_edge|trend|praise",'
        '"theme":"short_snake_case","category":"one suitable category","sentiment":"positive|negative|mixed|neutral",'
        '"summary":"short factual summary"}]}. Do not invent facts. Keep each evidence_id unchanged.',
        [{"evidence_id": row.id, "source_type": row.source_type, "text": row.text_or_value[:1200]} for row in in_scope[:80]],
    )
    if ai_rows:
        for row in ai_rows.get("items", []):
            if not isinstance(row, dict) or not row.get("evidence_id"):
                continue
            classified[str(row["evidence_id"])] = {
                "theme": str(row.get("theme") or "overall_experience")[:80],
                "category": str(row.get("category") or "Ownership experience")[:100],
                "sentiment": str(row.get("sentiment") or "neutral").lower(),
                "type": str(row.get("type") or "unmet_need").lower(),
                "summary": str(row.get("summary") or "")[:300],
            }
    feedback_total = max(1, sum(row.source_type in {"feedback", "study"} for row in in_scope))
    grouped: dict[tuple[str, str, str], list[tuple[EvidenceItem, dict[str, str]]]] = defaultdict(list)
    allowed_types = {"complaint", "unmet_need", "competitor_edge", "trend", "praise"}
    allowed_sentiments = {"positive", "negative", "mixed", "neutral"}
    for row in in_scope:
        item = classified.get(row.id) or _classify(row.text_or_value)
        if item.get("type") not in allowed_types or item.get("sentiment") not in allowed_sentiments:
            item = _classify(row.text_or_value)
        item.setdefault("summary", "")
        grouped[(item["theme"], item["category"], item["type"])].append((row, item))

    sentiment_by_theme: dict[str, list[str]] = defaultdict(list)
    for grouped_rows in grouped.values():
        for _, item in grouped_rows:
            sentiment_by_theme[item["theme"]].append(item["sentiment"])
    satisfaction_by_theme = {}
    for theme, values in sentiment_by_theme.items():
        positive_count = sum(value in {"positive", "mixed"} for value in values)
        negative_count = sum(value in {"negative", "mixed"} for value in values)
        satisfaction_by_theme[theme] = max(
            0,
            min(100, round(50 + 50 * (positive_count - negative_count) / max(1, len(values)))),
        )

    signals: list[Signal] = []
    for (theme, category, signal_type), rows in grouped.items():
        reliability = sum(row.reliability for row, _ in rows) / len(rows)
        source_diversity = len({row.source_type for row, _ in rows})
        sentiments = [item["sentiment"] for _, item in rows]
        sentiment = (
            "mixed" if "positive" in sentiments and "negative" in sentiments
            else "negative" if "negative" in sentiments
            else "positive" if "positive" in sentiments
            else "neutral"
        )
        summaries = [item.get("summary", "") for _, item in rows if item.get("summary")]
        signals.append(Signal(
            type=signal_type,
            theme=theme,
            category=category,
            sentiment=sentiment,
            mention_count=len(rows),
            share_of_feedback=min(1.0, sum(row.source_type in {"feedback", "study"} for row, _ in rows) / feedback_total),
            evidence_ids=[row.id for row, _ in rows],
            confidence=round(min(0.99, reliability * (0.78 + 0.07 * min(3, source_diversity))), 2),
            satisfaction_index=satisfaction_by_theme.get(theme, 50),
            summary=summaries[0] if summaries else f"{len(rows)} evidence item(s) indicate {theme.replace('_', ' ')}.",
        ))
    return signals
