"""The real Decide step (VISION.md: "it picks its next action and stores
why"). Needs OPENAI_API_KEY in the environment (see repo root .env.example).
"""

import json
import os

from openai import OpenAI

MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

_CONTENT = {
    "type": "object",
    "description": "the node's content. Always a JSON object, e.g. {\"text\": \"...\"} or "
                   "{\"quote\": \"...\", \"url\": \"...\"} — never a plain string.",
    "properties": {"text": {"type": "string"}},
}
_IDS = {"type": "array", "items": {"type": "string"}}
_RATIONALE = {"type": "string", "description": "why this action, for the node's rationale field"}

TOOLS = [
    {"type": "function", "function": {
        "name": "query_data", "description": "Look into the BMW files for evidence.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "source_ids": _IDS, "rationale": _RATIONALE},
                        "required": ["content", "source_ids", "rationale"]}}},
    {"type": "function", "function": {
        "name": "web_search", "description": "Find competitor info/trends; content must include a url.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "inputs": _IDS, "rationale": _RATIONALE},
                        "required": ["content", "inputs", "rationale"]}}},
    {"type": "function", "function": {
        "name": "add_claim", "description": "State a finding, linked to its evidence.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "evidence_ids": _IDS, "rationale": _RATIONALE},
                        "required": ["content", "evidence_ids", "rationale"]}}},
    {"type": "function", "function": {
        "name": "add_assumption", "description": "State a forward-looking guess, clearly marked as not evidence.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "inputs": _IDS, "rationale": _RATIONALE},
                        "required": ["content", "inputs", "rationale"]}}},
    {"type": "function", "function": {
        "name": "propose_requirement", "description": "Turn one or more claims into a requirement.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "claim_ids": _IDS, "rationale": _RATIONALE},
                        "required": ["content", "claim_ids", "rationale"]}}},
    {"type": "function", "function": {
        "name": "score", "description": "Run the fixed scoring formula on a requirement.",
        "parameters": {"type": "object", "properties": {
            "content": _CONTENT, "target_id": {"type": "string"}, "formula": {"type": "string"},
            "rationale": _RATIONALE},
            "required": ["content", "target_id", "formula", "rationale"]}}},
    {"type": "function", "function": {
        "name": "challenge", "description": "Look for counter-evidence to an existing node.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "target_id": {"type": "string"}, "rationale": _RATIONALE},
                        "required": ["content", "target_id", "rationale"]}}},
    {"type": "function", "function": {
        "name": "ask_pm", "description": "Stop and ask the PM a question when no good next step exists.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "inputs": _IDS, "rationale": _RATIONALE},
                        "required": ["content", "rationale"]}}},
]

SYSTEM_PROMPT = (
    "You are the agent building a product-decision graph (VISION.md). You are given the "
    "current graph's signals (sources without evidence, evidence without a claim, claims "
    "without a requirement, stale nodes, open questions). Pick exactly one tool call that "
    "makes the most progress right "
    "now, and fill in its 'rationale' argument explaining why. If nothing useful can be done, "
    "call ask_pm."
)


def decide_with_llm(signals: dict, client: OpenAI | None = None) -> tuple[str, dict]:
    client = client or OpenAI()
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(signals, default=str)},
        ],
        tools=TOOLS,
        tool_choice="required",
    )
    call = resp.choices[0].message.tool_calls[0]
    args = json.loads(call.function.arguments)
    args["created_by"] = "agent:loop"
    return call.function.name, args
