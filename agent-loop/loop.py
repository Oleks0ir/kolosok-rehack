"""Thin Look -> Decide -> Act -> Pause loop against the decision graph API.

See README.md in this directory for the design. Talks to the backend only
over HTTP (never imports backend/app/), so it runs as an independent module.
"""

import requests

API_BASE = "http://localhost:8000"


def look() -> dict:
    """Read the graph and compute the signals Decide needs."""
    nodes = requests.get(f"{API_BASE}/nodes").json()
    by_type: dict[str, list] = {}
    for n in nodes:
        by_type.setdefault(n["type"], []).append(n)

    sources_without_evidence = [
        s
        for s in by_type.get("Source", [])
        if not requests.get(f"{API_BASE}/nodes/{s['id']}/dependents").json()
    ]
    claims_without_requirement = [
        c
        for c in by_type.get("Claim", [])
        if not any(
            d["type"] == "Requirement"
            for d in requests.get(f"{API_BASE}/nodes/{c['id']}/dependents").json()
        )
    ]

    return {
        "sources_without_evidence": sources_without_evidence,
        "claims_without_requirement": claims_without_requirement,
        "stale": [n for n in nodes if n["status"] == "stale"],
        "open_questions": by_type.get("Question", []),
    }


def decide(signals: dict) -> tuple[str, dict]:
    """Pick the next tool call and its arguments.

    shortcut: fixed priority rule instead of an LLM choosing the action and
    writing the rationale. Swap this function out for a real model call;
    look()/act()/run() don't need to change when you do.
    """
    if signals["sources_without_evidence"]:
        src = signals["sources_without_evidence"][0]
        return "query_data", {
            "content": {"note": f"TODO: real query against source {src['id']}"},
            "source_ids": [src["id"]],
            "created_by": "agent:loop",
            "rationale": "source has no evidence yet",
        }
    if signals["claims_without_requirement"]:
        claim = signals["claims_without_requirement"][0]
        return "propose_requirement", {
            "content": {"text": f"TODO: requirement derived from {claim['id']}"},
            "claim_ids": [claim["id"]],
            "created_by": "agent:loop",
            "rationale": "claim has no requirement built on it yet",
        }
    return "ask_pm", {
        "content": {"text": "No obvious next step found by the loop."},
        "inputs": None,
        "created_by": "agent:loop",
        "rationale": "ran out of rule-based next steps",
    }


def act(tool: str, args: dict) -> dict:
    resp = requests.post(f"{API_BASE}/tools/{tool}", json=args)
    resp.raise_for_status()
    return resp.json()


def run(max_actions: int = 5) -> list[dict]:
    """Look -> Decide -> Act up to max_actions times, or until ask_pm fires."""
    summary = []
    for _ in range(max_actions):
        tool, args = decide(look())
        summary.append(act(tool, args))
        if tool == "ask_pm":
            break
    return summary


if __name__ == "__main__":
    for node in run():
        print(node["id"], node["type"], node.get("rationale"))
