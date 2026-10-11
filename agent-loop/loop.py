"""Thin Look -> Decide -> Act -> Pause loop against the decision graph API.

See README.md in this directory for the design. Talks to the backend only
over HTTP (never imports backend/app/), so it runs as an independent module.
"""

import os
import sys

import requests

from llm import decide_with_llm

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
    # Each evidence carries its input ids, so Decide can see which source it came from
    # instead of guessing ids once the source has dropped out of sources_without_evidence.
    evidence_without_claim = [
        {**e, "inputs": [i["id"] for i in requests.get(f"{API_BASE}/nodes/{e['id']}/inputs").json()]}
        for e in by_type.get("Evidence", [])
        if not any(
            d["type"] == "Claim"
            for d in requests.get(f"{API_BASE}/nodes/{e['id']}/dependents").json()
        )
    ]

    return {
        # shortcut: every source's full content goes into every prompt; chunk or summarize
        # once real files exceed a few hundred rows.
        "sources": by_type.get("Source", []),
        "sources_without_evidence": sources_without_evidence,
        "evidence_without_claim": evidence_without_claim,
        "claims_without_requirement": claims_without_requirement,
        "stale": [n for n in nodes if n["status"] == "stale"],
        "open_questions": by_type.get("Question", []),
    }


def decide(signals: dict, history: list[dict] | None = None) -> tuple[str, dict]:
    """Pick the next tool call and its arguments.

    Without OPENAI_API_KEY: decide_rule_based() alone (tests, offline runs).
    DECIDE_MODE=llm (default): the LLM picks the tool and writes everything.
    DECIDE_MODE=hybrid: decide_rule_based() picks the tool and input ids, so the
    loop always progresses; the LLM only writes content + rationale.
    """
    if not os.environ.get("OPENAI_API_KEY"):
        return decide_rule_based(signals)
    if os.environ.get("DECIDE_MODE", "llm") != "hybrid":
        return decide_with_llm(signals, history)
    tool, args = decide_rule_based(signals)
    ids = {k: v for k, v in args.items() if k not in ("content", "rationale", "created_by")}
    _, written = decide_with_llm(signals, history, forced=(tool, ids))
    return tool, {**args, "content": written["content"],
                  "rationale": written.get("rationale", args["rationale"])}


def decide_rule_based(signals: dict) -> tuple[str, dict]:
    """Deterministic placeholder Decide step: fixed priority rule instead of
    an LLM choosing the action. Used as a fallback and in tests."""
    if signals["sources_without_evidence"]:
        src = signals["sources_without_evidence"][0]
        return "query_data", {
            "content": {"note": f"TODO: real query against source {src['id']}"},
            "source_ids": [src["id"]],
            "created_by": "agent:loop",
            "rationale": "source has no evidence yet",
        }
    if signals["evidence_without_claim"]:
        evidence = signals["evidence_without_claim"][0]
        return "add_claim", {
            "content": {"text": f"TODO: claim derived from {evidence['id']}"},
            "evidence_ids": [evidence["id"]],
            "created_by": "agent:loop",
            "rationale": "evidence has no claim built on it yet",
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
    """Call the chosen tool. A 400 means Decide's choice was invalid (e.g. a
    dangling input id) — return it as an error result instead of raising, so
    run() can let Decide try something else next iteration instead of dying."""
    resp = requests.post(f"{API_BASE}/tools/{tool}", json=args)
    if resp.status_code == 400:
        return {"error": resp.json().get("detail", resp.text), "tool": tool}
    resp.raise_for_status()
    return resp.json()


def run(max_actions: int = 5) -> list[dict]:
    """Look -> Decide -> Act up to max_actions times, or until ask_pm succeeds."""
    summary = []
    history = []  # what Decide did this run, so it can see repeats and its own errors
    for _ in range(max_actions):
        tool, args = decide(look(), history[-5:])
        result = act(tool, args)
        summary.append(result)
        history.append({"tool": tool, "content": args.get("content"),
                        "result": result.get("error") or result.get("id")})
        # one line per action as it happens: the live log the GUI shows (GET /agent/status)
        print(result.get("id", "ERROR"), tool, result.get("rationale") or result.get("error"), flush=True)
        if tool == "ask_pm" and "error" not in result:
            break
    return summary


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
