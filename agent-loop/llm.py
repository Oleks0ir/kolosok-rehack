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
                   "{\"text\": \"...\", \"quote\": \"...\", \"source_ref\": \"...\"} — never a plain string.",
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
    # shortcut: no web_search tool — the loop has no real search behind it, so the LLM could only
    # invent results and URLs. Add it back (backend /tools/web_search exists) with a real search call.
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
        "name": "challenge",
        "description": "Record counter-evidence against an existing node: a source row that says the "
                       "OPPOSITE of it or limits it. content.quote must be that row's exact text. A row "
                       "that supports, repeats or is unrelated to the target is NOT counter-evidence — "
                       "if no row contradicts it, call ask_pm instead and say none was found.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "target_id": {"type": "string"}, "rationale": _RATIONALE},
                        "required": ["content", "target_id", "rationale"]}}},
    {"type": "function", "function": {
        "name": "revise",
        "description": "Redo a node from `stale_ready` after the PM edited something it is built on. "
                       "Read its inputs_now (the current inputs; `was` is the old id) and write the "
                       "node's content again so it matches them. If it still holds unchanged, keep the "
                       "content and say so in the rationale. Only ids from stale_ready.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "target_id": {"type": "string"}, "rationale": _RATIONALE},
                        "required": ["content", "target_id", "rationale"]}}},
    {"type": "function", "function": {
        "name": "ask_pm", "description": "Stop and ask the PM a question when no good next step exists.",
        "parameters": {"type": "object",
                        "properties": {"content": _CONTENT, "inputs": _IDS, "rationale": _RATIONALE},
                        "required": ["content", "rationale"]}}},
]

# Self-check the loop gates on (loop.check): seen live, models picked an off-topic row for
# "dig deeper" or a non-contradicting row for "challenge" while their own rationale said so.
_FULFILLS = {"type": "boolean", "description":
             "Only while handling a pm_input request (challenge / dig_deeper): true only if this call "
             "really does what the PM asked — a row that truly contradicts the target, or a finding on "
             "the SAME topic as the target. If not, don't make this call: call ask_pm instead."}
for _tool in TOOLS:
    if _tool["function"]["name"] != "ask_pm":
        _tool["function"]["parameters"]["properties"]["fulfills_pm_request"] = _FULFILLS

SYSTEM_PROMPT = """\
You are the agent building a product-decision graph for BMW product managers (PMs).
The graph grows along one chain: Source (a data file) -> Evidence (query_data: one concrete
finding from a source) -> Claim (add_claim) -> Requirement (propose_requirement) -> score.
Each turn you get the graph's signals and your recent_actions; pick exactly ONE tool call.

Rules:
0. `pm_input` comes first — the PM steers. Your call must handle its FIRST item; the loop links
   the node you write to that item (so it counts as done), so don't do unrelated work now.
   - request "challenge": look in the sources for evidence against its target and call
     challenge on the target. If the sources hold none, call ask_pm (item id in inputs) and
     say so — never invent counter-evidence.
   - request "dig_deeper": find another source row about the SAME topic as its target
     (query_data), or a claim that refines it. Rows on other topics don't count; if there are
     none, call ask_pm and say so.
   - a PM Note built on one of your Questions is the PM's answer. It is the PM's judgement, not
     evidence: record it with add_assumption (the note among the inputs), or add the note to
     evidence_ids only NEXT TO real Evidence ids. Never make a claim that rests on the note alone.
   - anything else is an instruction: follow it. If you can't, call ask_pm with the item id in
     inputs and explain why.
0b. `stale_ready` comes next: the PM edited something these nodes are built on. Redo the first
   one with revise before any new work, so the chain the PM changed is whole again.
0c. `brief` is the PM's goal (vehicle, market, what they want to decide). Prefer findings,
   claims and requirements that serve it; skip rows that don't.
0d. Never build on ids in `rejected_by_pm`: the PM rejected them.
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
        # gpt-6 models reject tool calls on chat.completions unless reasoning is off
        **({"reasoning_effort": "none"} if MODEL.startswith("gpt-6") else {}),
    )
    call = resp.choices[0].message.tool_calls[0]
    args = json.loads(call.function.arguments)
    args["created_by"] = "agent:loop"
    return call.function.name, args
