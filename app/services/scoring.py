from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from app.models import EvidenceItem, Requirement, Signal


def score_requirements(
    requirements: list[Requirement],
    signals: list[Signal],
    evidence: list[EvidenceItem],
    profile: dict[str, Any],
) -> list[Requirement]:
    signal_map = {signal.id: signal for signal in signals}
    evidence_map = {item.id: item for item in evidence}
    raw_mentions = {
        req.id: sum(signal_map[sid].mention_count for sid in req.signal_ids if sid in signal_map)
        for req in requirements
    }
    max_mentions = max(raw_mentions.values(), default=1)
    weights = profile.get("weights", {})
    for requirement in requirements:
        linked = [signal_map[sid] for sid in requirement.signal_ids if sid in signal_map]
        unique_items = {
            eid: evidence_map[eid]
            for signal in linked for eid in signal.evidence_ids if eid in evidence_map
        }
        linked_items = list(unique_items.values())
        mentions = raw_mentions.get(requirement.id, 0)
        reach = min(1.0, math.log1p(mentions) / math.log1p(max_mentions or 1))
        negative_share = sum(
            signal.mention_count for signal in linked if signal.sentiment in {"negative", "mixed"}
        ) / max(1, mentions)
        severity = min(1.0, 0.35 + negative_share * 0.65)
        quality = sum(item.reliability for item in linked_items) / max(1, len(linked_items))
        independent = len({item.source_ref for item in linked_items})
        evidence_quality = min(1.0, quality * min(1.0, 0.62 + 0.12 * max(0, independent - 1)))
        strategic = min(
            1.0,
            0.45
            + 0.28 * sum(signal.type == "competitor_edge" for signal in linked)
            + 0.18 * sum(signal.type == "trend" for signal in linked),
        )
        text = requirement.text.lower()
        effort_hints = ("app", "software", "navigation", "voice", "information", "controls")
        feasibility = 0.68 if any(word in text for word in effort_hints) else 0.58
        context_notes = []
        context = " ".join((requirement.text, str(profile.get("model", "")), str(profile.get("market", "")))).lower()
        for rule in profile.get("context_rules", []):
            if not isinstance(rule, dict):
                continue
            triggers = rule.get("trigger_terms", [])
            contexts = rule.get("context_terms", [])
            if triggers and any(str(term).lower() in text for term in triggers):
                if contexts and not any(str(term).lower() in context for term in contexts):
                    context_notes.append(str(rule.get("description", rule.get("id", "Context rule"))) + " · matching context not found.")
                elif rule.get("pm_confirmed") and rule.get("factor") == "feasibility":
                    feasibility = min(1.0, feasibility + float(rule.get("adjustment", 0)))
                    context_notes.append(str(rule.get("description", rule.get("id", "Context rule"))) + " · PM confirmed.")
                elif rule.get("pm_confirmed") and rule.get("factor") == "evidence_quality":
                    quality = min(1.0, quality + float(rule.get("adjustment", 0)))
                    evidence_quality = min(1.0, quality * min(1.0, 0.62 + 0.12 * max(0, independent - 1)))
                    context_notes.append(str(rule.get("description", rule.get("id", "Context rule"))) + " · PM confirmed.")
                else:
                    context_notes.append(str(rule.get("description", rule.get("id", "Context rule"))) + " · awaiting PM confirmation.")
        values = {
            "reach": reach,
            "severity": severity,
            "evidence_quality": evidence_quality,
            "strategic_fit": strategic,
            "feasibility": feasibility,
        }
        points = {name: round(values[name] * float(weights.get(name, 0)) * 100, 1) for name in values}
        requirement.score = max(0, min(100, round(sum(points.values()))))
        requirement.score_breakdown = {
            "factors": {
                name: {
                    "value": round(values[name], 2),
                    "weight": round(float(weights.get(name, 0)), 3),
                    "points": points[name],
                }
                for name in values
            },
            "total": requirement.score,
            "formula": "sum(normalized factor value x profile weight) x 100",
            "mentions": mentions,
            "independent_sources": independent,
            "context_notes": context_notes,
        }
        all_web = bool(linked_items) and all(item.source_type == "web" for item in linked_items)
        if all_web:
            requirement.evidence_level = "assumption_based"
        elif len(linked_items) >= 5 and quality >= 0.78 and independent >= 3:
            requirement.evidence_level = "strong"
        elif len(linked_items) >= 2 and quality >= 0.6:
            requirement.evidence_level = "moderate"
        else:
            requirement.evidence_level = "weak"
        if requirement.evidence_level in {"weak", "assumption_based"} and not requirement.assumptions:
            requirement.assumptions.append(
                "Additional customer validation is needed before treating this as a stable priority."
            )
        if not requirement.rationale:
            requirement.rationale = (
                f"Prioritized from {mentions} linked mention(s); factor values and weights are shown in the breakdown."
            )
    by_category: dict[str, list[Requirement]] = defaultdict(list)
    for requirement in requirements:
        by_category[requirement.category].append(requirement)
    for group in by_category.values():
        group.sort(key=lambda item: item.score, reverse=True)
        for rank, requirement in enumerate(group, start=1):
            requirement.score_breakdown["category_rank"] = rank
    return requirements
