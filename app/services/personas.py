from __future__ import annotations

from typing import Any


PERSONAS = [
    {"name": "Long-distance commuter", "needs": {"charging": 1.0, "navigation": 0.8, "cabin": 0.55, "comfort": 0.55}},
    {"name": "Connected technology user", "needs": {"voice": 0.9, "app": 0.9, "digital": 0.8, "navigation": 0.6}},
    {"name": "Family passenger", "needs": {"rear": 0.9, "comfort": 0.85, "storage": 0.7, "safety": 0.6}},
]

KEYWORDS = {
    "charging": ("charge", "range", "battery", "electric"),
    "navigation": ("navigation", "route", "map", "journey"),
    "cabin": ("quiet", "noise", "cabin"),
    "comfort": ("comfort", "seat", "climate", "ride"),
    "voice": ("voice", "assistant", "speech"),
    "app": ("app", "remote", "connected"),
    "digital": ("digital", "screen", "infotainment", "software"),
    "rear": ("rear", "passenger", "back seat"),
    "storage": ("storage", "boot", "trunk", "luggage"),
    "safety": ("safety", "assist", "parking", "lane"),
}


def simulate(options: dict[str, str]) -> dict[str, Any]:
    if not options:
        options = {
            "A": "Improve connected services and natural voice interaction.",
            "B": "Improve cabin comfort, seating and passenger controls.",
            "C": "Improve journey planning, charging and driver assistance.",
        }
    results = []
    option_scores: dict[str, list[float]] = {key: [] for key in options}
    for persona in PERSONAS:
        persona_ratings = []
        for key, description in options.items():
            text = description.lower()
            matches = 0
            weighted = 0.0
            for need, weight in persona["needs"].items():
                terms = KEYWORDS.get(need, (need,))
                if any(term in text for term in terms) or need in text:
                    matches += 1
                    weighted += weight
            rating = round(min(96, max(42, 55 + weighted * 15 + matches * 2)))
            option_scores[key].append(float(rating))
            persona_ratings.append({
                "option": key,
                "rating": rating,
                "reason": f"Matched {matches} stated persona preference(s).",
            })
        results.append({
            "persona": persona["name"],
            "ratings": persona_ratings,
            "simulated": True,
            "evidence_level": "weak",
        })
    averages = {
        key: round(sum(values) / max(1, len(values)), 1)
        for key, values in option_scores.items()
    }
    return {
        "simulated": True,
        "label": "Synthetic customer simulation · low evidence",
        "personas": results,
        "option_averages": averages,
        "note": "Simulation is excluded from requirement scores unless the PM explicitly enables it.",
    }
