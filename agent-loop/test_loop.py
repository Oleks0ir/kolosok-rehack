from loop import decide

EMPTY_SIGNALS = {
    "sources_without_evidence": [],
    "claims_without_requirement": [],
    "stale": [],
    "open_questions": [],
}


def test_decide_prioritizes_sources_without_evidence():
    signals = {**EMPTY_SIGNALS, "sources_without_evidence": [{"id": "SRC-001"}]}
    tool, args = decide(signals)
    assert tool == "query_data"
    assert args["source_ids"] == ["SRC-001"]


def test_decide_falls_back_to_propose_requirement():
    signals = {**EMPTY_SIGNALS, "claims_without_requirement": [{"id": "CLM-001"}]}
    tool, args = decide(signals)
    assert tool == "propose_requirement"
    assert args["claim_ids"] == ["CLM-001"]


def test_decide_falls_back_to_ask_pm():
    tool, args = decide(EMPTY_SIGNALS)
    assert tool == "ask_pm"
