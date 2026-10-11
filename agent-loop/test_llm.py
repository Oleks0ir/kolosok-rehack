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
