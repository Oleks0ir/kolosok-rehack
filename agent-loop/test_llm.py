import json
from unittest.mock import MagicMock

from llm import decide_with_llm


def test_decide_with_llm_parses_tool_call_and_stamps_created_by():
    call = MagicMock()
    call.function.name = "ask_pm"
    call.function.arguments = json.dumps({"content": {"text": "why?", "rationale": "nothing to do"}})

    resp = MagicMock()
    resp.choices[0].message.tool_calls = [call]

    client = MagicMock()
    client.chat.completions.create.return_value = resp

    tool, args = decide_with_llm({"stale": []}, client=client)

    assert tool == "ask_pm"
    assert args["created_by"] == "agent:loop"
    assert args["content"]["text"] == "why?"


def test_forced_tool_pins_tool_choice_and_sends_history():
    call = MagicMock()
    call.function.name = "add_claim"
    call.function.arguments = json.dumps({"content": {"text": "c"}, "rationale": "r"})
    client = MagicMock()
    client.chat.completions.create.return_value.choices[0].message.tool_calls = [call]
    history = [{"tool": "query_data", "content": {"text": "x"}, "result": "EVD-001"}]

    decide_with_llm({}, history, forced=("add_claim", {"evidence_ids": ["EVD-001"]}), client=client)

    kwargs = client.chat.completions.create.call_args.kwargs
    assert kwargs["tool_choice"] == {"type": "function", "function": {"name": "add_claim"}}
    payload = json.loads(kwargs["messages"][1]["content"])
    assert payload["recent_actions"] == history
    assert payload["required_action"] == {"tool": "add_claim", "evidence_ids": ["EVD-001"]}
