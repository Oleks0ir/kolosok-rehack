"""Thin Look -> Decide -> Act -> Pause loop against the decision graph API.

See README.md in this directory for the design. Talks to the backend only
over HTTP (never imports backend/app/), so it runs as an independent module.
"""

import os
import sys
from datetime import datetime

import requests

from llm import decide_with_llm

API_BASE = "http://localhost:8000"


def handled(pm: dict, dependents: list[dict], target_dependents: list[dict]) -> bool:
    """Is a PM input (a PM's Question/Note) done? Yes once the agent built a node on it, or —
    for "challenge" requests, whose tool takes only the target id — once the agent built on
    the target after the request was made."""
    by_agent = [d for d in dependents + target_dependents if d["created_by"].startswith("agent:")]
    if any(d in dependents for d in by_agent):
        return True
    asked = datetime.fromisoformat(pm["timestamp"])
    return pm["content"].get("request") == "challenge" and any(
        datetime.fromisoformat(d["timestamp"]) > asked for d in by_agent)


def is_brief(n: dict) -> bool:
    """The PM's brief (start screen): a Note with content.kind = "brief", the goal of the graph."""
    return n["type"] == "Note" and n["content"].get("kind") == "brief"


def graph_state(nodes: list[dict], edges: list[dict]) -> dict:
    """What the chain signals must respect besides the raw graph: the latest version of each
    node, the PM's verdicts, the brief, and which stale nodes are ready to be redone."""
    by_id = {n["id"]: n for n in nodes}
    newer = {n["replaces"]: n["id"] for n in nodes if n["replaces"]}

    def latest(node_id: str) -> str:
        while node_id in newer:
            node_id = newer[node_id]
        return node_id

    decisions = sorted((e for e in edges if e["relation"] == "decides"),
                       key=lambda e: by_id[e["from_id"]]["timestamp"])
    verdict = {e["to_id"]: by_id[e["from_id"]]["content"].get("verdict") for e in decisions}
    inputs: dict[str, list[str]] = {}
    for e in edges:
        if e["relation"] != "decides":
            inputs.setdefault(e["from_id"], []).append(e["to_id"])

    # A stale node can be redone once every input's latest version is fine again: redo the
    # chain from the edit downwards, one step per action.
    stale_ready = []
    for n in nodes:
        if n["status"] != "stale" or n["id"] in newer or n["type"] in ("Decision", "Source", "Question", "Note"):
            continue
        now = [latest(i) for i in inputs.get(n["id"], [])]
        if all(by_id[i]["status"] != "stale" for i in now):
            stale_ready.append({**n, "inputs_now": [
                {"id": i, "was": old, "content": by_id[i]["content"]} for old, i in zip(inputs.get(n["id"], []), now)]})

    briefs = [n for n in nodes if is_brief(n) and n["id"] not in newer]
    return {
        "superseded": set(newer),
        "rejected": {i for i, v in verdict.items() if v == "reject"},
        "verdict": verdict,
        "brief": briefs[-1] if briefs else None,
        "stale_ready": stale_ready,
    }


def look() -> dict:
    """Read the graph and compute the signals Decide needs."""
    all_nodes = requests.get(f"{API_BASE}/nodes").json()
    state = graph_state(all_nodes, requests.get(f"{API_BASE}/edges").json())
    # Build only on live ground: not an old version, not rejected by the PM, not stale (stale
    # nodes are redone via stale_ready instead), and not what a pending redo will build on.
    pending = {i["id"] for n in state["stale_ready"] for i in n["inputs_now"]}
    skip = state["superseded"] | state["rejected"] | pending
    nodes = [n for n in all_nodes if n["id"] not in skip and n["status"] != "stale"]
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

    dependents = lambda node_id: requests.get(f"{API_BASE}/nodes/{node_id}/dependents").json()
    # PM requests (Question, content.request = challenge | dig_deeper), PM answers (Note on
    # an agent Question) and other PM instructions that the agent hasn't acted on yet.
    pm_input = []
    for n in by_type.get("Question", []) + by_type.get("Note", []):
        if not n["created_by"].startswith("PM:") or is_brief(n):
            continue
        targets = requests.get(f"{API_BASE}/nodes/{n['id']}/inputs").json()
        if not handled(n, dependents(n["id"]), [d for t in targets for d in dependents(t["id"])]):
            pm_input.append({**n, "targets": targets})
    pm_input.sort(key=lambda n: datetime.fromisoformat(n["timestamp"]))  # oldest PM input first

    return {
        # the PM's goal for the whole graph: every step should serve it
        "brief": state["brief"] and state["brief"]["content"],
        "pm_input": pm_input,
        # stale after a PM edit, inputs fine again: redo with revise (after pm_input)
        "stale_ready": state["stale_ready"],
        "rejected_by_pm": sorted(state["rejected"]),
        # shortcut: every source's full content goes into every prompt; chunk or summarize
        # once real files exceed a few hundred rows.
        "sources": by_type.get("Source", []),
        "sources_without_evidence": sources_without_evidence,
        "evidence_without_claim": evidence_without_claim,
        "claims_without_requirement": claims_without_requirement,
        # the agent's own questions the PM hasn't answered yet
        "open_questions": [q for q in by_type.get("Question", [])
                           if not q["created_by"].startswith("PM:") and not dependents(q["id"])],
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
    for item in signals.get("pm_input", [])[:1]:  # PM input first (VISION.md: "the PM steers")
        # requests and free-text input need judgement (e.g. finding real counter-evidence)
        # the rules don't have: hand it back to the PM, linked to the item so it's handled
        return "ask_pm", {
            "content": {"text": f"The rule-based loop can't act on {item['id']}; run with the LLM or follow up by hand."},
            "inputs": [item["id"]],
            "created_by": "agent:loop",
            "rationale": f"PM input {item['id']} needs judgement",
        }
    for node in signals.get("stale_ready", [])[:1]:  # then repair what a PM edit broke
        return "revise", {
            "content": node["content"],
            "target_id": node["id"],
            "created_by": "agent:loop",
            "rationale": f"rebuilt on {', '.join(i['id'] for i in node['inputs_now'])} after an edit; content unchanged (rule-based)",
        }
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


# the id list each tool writes its input edges from (challenge/score take a single target id)
LIST_ARG = {"query_data": "source_ids", "web_search": "inputs", "add_claim": "evidence_ids",
            "add_assumption": "inputs", "propose_requirement": "claim_ids", "ask_pm": "inputs"}


def link_pm_input(tool: str, args: dict, pm_input: list[dict]) -> dict:
    """Decide must handle the first PM input (prompt rule 0). Link the new node to it here
    instead of trusting the LLM to: that makes the work traceable to the PM's request and
    marks the request handled. challenge has no id list; handled() covers it by target."""
    key = LIST_ARG.get(tool)
    if pm_input and key and pm_input[0]["id"] not in (args.get(key) or []):
        args = {**args, key: (args.get(key) or []) + [pm_input[0]["id"]]}
    return args


def check_challenge(args: dict, signals: dict) -> str | None:
    """Counter-evidence must quote a real source row that isn't what the target itself says —
    otherwise the graph shows a 'contradicts' arrow nothing backs. Seen live: models recorded
    the claim's own row, or "none found", as counter-evidence."""
    quote = (args.get("content") or {}).get("quote")
    rows = {str(v) for s in signals.get("sources", []) for r in s["content"].get("rows") or [] for v in r.values()}
    target = {str(v) for item in signals.get("pm_input", []) for t in item["targets"]
              if t["id"] == args.get("target_id") for v in t["content"].values()}
    if not quote or quote not in rows:
        return ("challenge rejected: content.quote must be the exact text of a source row that "
                "contradicts the target. If no row does, call ask_pm and say none was found.")
    if quote in target:
        return ("challenge rejected: that row is what the target itself says, so it supports it. "
                "If no other row contradicts it, call ask_pm and say so.")
    return None


def check(tool: str, args: dict, signals: dict) -> str | None:
    """Gate the calls LLMs got wrong in live runs before they become misleading nodes."""
    item = (signals.get("pm_input") or [None])[0]
    if item and item["content"].get("request") and tool != "ask_pm" and args.get("fulfills_pm_request") is not True:
        return (f"rejected: you didn't confirm this call does what {item['id']} asks "
                "(fulfills_pm_request). Call ask_pm and tell the PM what you found instead.")
    return check_challenge(args, signals) if tool == "challenge" else None


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
        signals = look()
        tool, args = decide(signals, history[-5:])
        problem = check(tool, args, signals)
        # a rejected call goes into history like an API 400, so Decide sees why next turn
        result = {"error": problem, "tool": tool} if problem else act(tool, link_pm_input(tool, args, signals["pm_input"]))
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
