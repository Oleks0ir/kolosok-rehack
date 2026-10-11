from unittest.mock import MagicMock, patch

import loop
from loop import act, decide_rule_based as decide, handled

EMPTY_SIGNALS = {
    "pm_input": [],
    "sources_without_evidence": [],
    "evidence_without_claim": [],
    "claims_without_requirement": [],
    "stale": [],
    "open_questions": [],
}


def _node(id, created_by, ts, request=None):
    return {"id": id, "created_by": created_by, "timestamp": ts,
            "content": {"text": "x", **({"request": request} if request else {})}}


def test_pm_input_is_handled_once_the_agent_builds_on_it():
    pm = _node("QST-001", "PM:alex", "2026-10-11T10:00:00Z")
    assert not handled(pm, [], [])
    assert not handled(pm, [_node("NOTE-001", "PM:alex", "2026-10-11T10:01:00Z")], [])
    assert handled(pm, [_node("CLM-002", "agent:loop", "2026-10-11T10:01:00Z")], [])


def test_challenge_request_is_handled_by_later_agent_work_on_its_target():
    pm = _node("QST-001", "PM:alex", "2026-10-11T10:00:00.5Z", request="challenge")
    earlier = _node("EVD-001", "agent:loop", "2026-10-11T09:00:00Z")
    later = _node("EVD-002", "agent:loop", "2026-10-11T10:00:01Z")
    assert not handled(pm, [], [earlier])
    assert handled(pm, [], [later])
    assert not handled({**pm, "content": {"text": "dig", "request": "dig_deeper"}}, [], [later])


def test_rule_based_hands_pm_input_back_before_anything_else():
    challenge = {**_node("QST-001", "PM:alex", "t", request="challenge"), "targets": [{"id": "CLM-001"}]}
    signals = {**EMPTY_SIGNALS, "pm_input": [challenge], "sources_without_evidence": [{"id": "SRC-001"}]}
    tool, args = decide(signals)
    assert (tool, args["inputs"]) == ("ask_pm", ["QST-001"])


def test_check_rejects_pm_request_calls_the_model_did_not_confirm():
    dig = {**_node("QST-002", "PM:alex", "t", request="dig_deeper"), "targets": []}
    signals = {"pm_input": [dig]}
    assert "QST-002" in loop.check("query_data", {"source_ids": ["SRC-001"]}, signals)
    assert "QST-002" in loop.check("query_data", {"fulfills_pm_request": False}, signals)
    assert loop.check("query_data", {"fulfills_pm_request": True}, signals) is None
    assert loop.check("ask_pm", {}, signals) is None  # handing it back is always allowed
    plain_note = {**_node("NOTE-001", "PM:alex", "t"), "targets": []}
    assert loop.check("add_claim", {}, {"pm_input": [plain_note]}) is None  # not a request


def test_check_challenge_needs_a_real_row_that_isnt_the_targets_own():
    signals = {
        "sources": [{"content": {"rows": [{"text": "seats too narrow"}, {"text": "seats are roomy"}]}}],
        "pm_input": [{"targets": [{"id": "CLM-001", "content": {"text": "x", "quote": "seats too narrow"}}]}],
    }
    check = lambda quote: loop.check_challenge({"target_id": "CLM-001", "content": {"quote": quote}}, signals)
    assert check("seats are roomy") is None
    assert "exact text" in check(None)  # "none found" recorded as counter-evidence
    assert "exact text" in check("seats feel cramped")  # invented row
    assert "supports it" in check("seats too narrow")  # the claim's own row


def test_link_pm_input_adds_the_first_item_to_the_tools_id_list():
    pm = [{"id": "QST-002"}, {"id": "QST-003"}]
    args = loop.link_pm_input("query_data", {"source_ids": ["SRC-001"]}, pm)
    assert args["source_ids"] == ["SRC-001", "QST-002"]
    assert loop.link_pm_input("ask_pm", {"inputs": None}, pm)["inputs"] == ["QST-002"]
    assert loop.link_pm_input("challenge", {"target_id": "CLM-001"}, pm) == {"target_id": "CLM-001"}
    assert loop.link_pm_input("add_claim", {"evidence_ids": ["EVD-1"]}, []) == {"evidence_ids": ["EVD-1"]}


def test_decide_prioritizes_sources_without_evidence():
    signals = {**EMPTY_SIGNALS, "sources_without_evidence": [{"id": "SRC-001"}]}
    tool, args = decide(signals)
    assert tool == "query_data"
    assert args["source_ids"] == ["SRC-001"]


def test_decide_prefers_evidence_without_claim_over_requirement():
    signals = {
        **EMPTY_SIGNALS,
        "evidence_without_claim": [{"id": "EVD-001"}],
        "claims_without_requirement": [{"id": "CLM-001"}],
    }
    tool, args = decide(signals)
    assert tool == "add_claim"
    assert args["evidence_ids"] == ["EVD-001"]


def test_decide_falls_back_to_propose_requirement():
    signals = {**EMPTY_SIGNALS, "claims_without_requirement": [{"id": "CLM-001"}]}
    tool, args = decide(signals)
    assert tool == "propose_requirement"
    assert args["claim_ids"] == ["CLM-001"]


def test_decide_falls_back_to_ask_pm():
    tool, args = decide(EMPTY_SIGNALS)
    assert tool == "ask_pm"


def test_act_returns_error_on_400_instead_of_raising():
    resp = MagicMock(status_code=400)
    resp.json.return_value = {"detail": "input node EVD-999 does not exist"}
    with patch("loop.requests.post", return_value=resp):
        result = act("add_claim", {"evidence_ids": ["EVD-999"]})
    assert result == {"error": "input node EVD-999 does not exist", "tool": "add_claim"}


def test_hybrid_keeps_rule_based_tool_and_ids_but_llm_content(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("DECIDE_MODE", "hybrid")
    signals = {**EMPTY_SIGNALS, "evidence_without_claim": [{"id": "EVD-001"}]}
    written = ("add_claim", {"content": {"text": "real claim"}, "rationale": "because EVD-001"})
    with patch("loop.decide_with_llm", return_value=written) as llm:
        tool, args = loop.decide(signals, [])
    assert llm.call_args.kwargs["forced"] == ("add_claim", {"evidence_ids": ["EVD-001"]})
    assert tool == "add_claim"
    assert args["evidence_ids"] == ["EVD-001"]
    assert args["content"] == {"text": "real claim"}
    assert args["rationale"] == "because EVD-001"
