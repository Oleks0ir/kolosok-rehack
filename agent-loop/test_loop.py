from unittest.mock import MagicMock, patch

import loop
from loop import act, decide_rule_based as decide

EMPTY_SIGNALS = {
    "sources_without_evidence": [],
    "evidence_without_claim": [],
    "claims_without_requirement": [],
    "stale": [],
    "open_questions": [],
}


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
