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
    "properties": {"text": {"type": "string"}, "quote": {"type": "string"},
                   "source_ref": {"type": "string"}},
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

SYSTEM_PROMPT = """\
You are the agent building a product-decision graph for BMW product managers (PMs).
The graph grows along one chain: Source (a data file) -> Evidence (query_data: one concrete
finding from a source) -> Claim (add_claim) -> Requirement (propose_requirement) -> score.
Each turn you get the graph's signals and your recent_actions; pick exactly ONE tool call.

Rules:
1. Evidence must contain real data. For query_data, read the source's content in `sources`
   and put one specific finding in content: {"text": "<finding>", "quote": "<exact row
   text>", "source_ref": "<row reference>"}. Never write an instruction, plan or request
   ("inspect the file...") as evidence. If a source has no usable content, call ask_pm.
2. Never invent data. Claims summarize evidence; requirements build on claims.
3. Only use node ids that appear in the signals. Ids are never guessed.
4. Move down the chain: if evidence_without_claim is non-empty, prefer add_claim over another
   query_data; if claims_without_requirement is non-empty, prefer propose_requirement.
5. Read recent_actions. Do not repeat a finding you already recorded, do not retry a call
   that just errored with the same arguments, and do not pick the same tool a third time in
   a row unless it records a genuinely new finding.
6. Always fill 'rationale' with why this step, citing the ids it builds on.
7. If no step makes real progress, call ask_pm with a specific question.
8. If `required_action` is given, call exactly that tool with those ids and write its
   content and rationale.
"""


def decide_with_llm(
    signals: dict,
    history: list[dict] | None = None,
    forced: tuple[str, dict] | None = None,
    client: OpenAI | None = None,
) -> tuple[str, dict]:
    """forced=(tool, ids) pins the tool and its input ids (hybrid mode); the LLM then only
    writes content + rationale."""
    client = client or OpenAI()
    payload = {"signals": signals, "recent_actions": history or []}
    tool_choice = "required"
    if forced:
        tool, ids = forced
        payload["required_action"] = {"tool": tool, **ids}
        tool_choice = {"type": "function", "function": {"name": tool}}
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ],
        tools=TOOLS,
        tool_choice=tool_choice,
    )
    call = resp.choices[0].message.tool_calls[0]
    args = json.loads(call.function.arguments)
    args["created_by"] = "agent:loop"
    return call.function.name, args
