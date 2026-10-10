from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.models import EvidenceItem, Requirement, Signal
from app.services.llm import complete_json


OUTCOMES = {
    "voice_assistant": "The in-car voice assistant should reliably understand natural requests and place names in the driver's market language.",
    "navigation": "Navigation should make it easy for drivers to plan confident journeys with relevant routes and stops.",
    "connected_app": "The connected app should give drivers timely, dependable confirmation and control of remote vehicle functions.",
    "charging": "Drivers should be able to plan charging and understand the electric range with confidence across their regular journeys.",
    "seating": "Drivers should be able to set up a comfortable seating position quickly and consistently.",
    "cabin_quietness": "The cabin should help occupants enjoy a calm, comfortable experience during everyday and motorway journeys.",
    "passenger_comfort": "Passengers should have convenient access to the comfort and connectivity features they use during a journey.",
    "parking": "Drivers should be able to understand the vehicle's surroundings and park with confidence in tight spaces.",
    "driver_assistance": "Driver assistance should communicate its availability and actions clearly so drivers can remain confident and in control.",
    "ride_and_handling": "The vehicle should provide a composed, confident ride across the road conditions customers encounter.",
    "storage": "The vehicle should make it straightforward to carry the items customers need on everyday and longer journeys.",
    "ownership": "Customers should be able to resolve ownership and service needs with clear, dependable support.",
    "overall_experience": "The successor should address the recurring customer need while preserving the experiences customers value.",
}


def draft_requirements(signals: list[Signal], evidence: list[EvidenceItem], profile: dict[str, Any]) -> list[Requirement]:
    by_theme: dict[tuple[str, str], list[Signal]] = defaultdict(list)
    evidence_by_id = {item.id: item for item in evidence}
    for signal in signals:
        by_theme[(signal.theme, signal.category)].append(signal)
    themes = []
    for (theme, category), linked in by_theme.items():
        examples = [
            {"source_type": evidence_by_id[eid].source_type, "text": evidence_by_id[eid].text_or_value[:400]}
            for signal in linked for eid in signal.evidence_ids if eid in evidence_by_id
        ]
        themes.append({
            "key": f"{theme}|{category}",
            "theme": theme,
            "category": category,
            "signals": [signal.model_dump() for signal in linked],
            "evidence": examples[:12],
        })
    generated: dict[str, dict[str, Any]] = {}
    ai_result = complete_json(
        "Draft one customer-facing requirement per input group. Do not prescribe implementation or invent evidence. "
        "Keep evidence-backed conclusions separate from assumptions. Return only JSON as "
        '{"requirements":[{"key":"exact input key","text":"...","rationale":"...","assumptions":["..."],'
        '"uncertainties":["..."]}]}',
        themes,
    ) if themes else None
    if ai_result:
        for item in ai_result.get("requirements", []):
            if isinstance(item, dict) and item.get("key"):
                generated[str(item["key"])] = item

    requirements: list[Requirement] = []
    for group in themes:
        linked = by_theme[(group["theme"], group["category"])]
        draft = generated.get(group["key"], {})
        source_types = {
            evidence_by_id[eid].source_type
            for signal in linked for eid in signal.evidence_ids if eid in evidence_by_id
        }
        count = sum(signal.mention_count for signal in linked)
        text = str(draft.get("text") or OUTCOMES.get(group["theme"], OUTCOMES["overall_experience"]))
        assumptions = draft.get("assumptions") if isinstance(draft.get("assumptions"), list) else []
        uncertainties = draft.get("uncertainties") if isinstance(draft.get("uncertainties"), list) else []
        if not assumptions:
            assumptions = ["Current evidence is representative of customers for the successor vehicle."]
        if not uncertainties:
            uncertainties = ["Preferences may differ by customer segment and market."]
        rationale = str(draft.get("rationale") or (
            f"Linked to {count} evidence-backed mention(s) across {len(source_types)} source type(s). "
            f"Signals include {', '.join(sorted({signal.type for signal in linked}))}."
        ))
        requirements.append(Requirement(
            text=text[:700],
            category=group["category"],
            signal_ids=[signal.id for signal in linked],
            rationale=rationale[:1000],
            assumptions=[str(value)[:300] for value in assumptions[:5]],
            uncertainties=[str(value)[:300] for value in uncertainties[:5]],
        ))
    return requirements
