import pytest

from app import tools
from app.db import get_conn, init_db
from app.graph import add_node, get_node
from app.models import NodeType, Relation


@pytest.fixture(autouse=True)
def clean_db():
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE edges, nodes CASCADE")
            cur.execute("UPDATE node_counters SET next = 1")
    yield


def test_source_needs_no_inputs():
    node = add_node(NodeType.SOURCE, {"file": "G70 feedback.xlsx"}, [], "tool:import")
    assert node.id == "SRC-001"
    assert node.status == "ok"


def test_claim_requires_inputs():
    with pytest.raises(ValueError):
        add_node(NodeType.CLAIM, {"text": "unmet need"}, [], "agent:researcher")


def test_decision_requires_pm():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    with pytest.raises(PermissionError):
        add_node(NodeType.DECISION, {"verdict": "approve"}, [src.id], "agent:researcher")

    decided = add_node(NodeType.DECISION, {"verdict": "approve"}, [src.id], "PM:alex", relation=Relation.DECIDES)
    assert decided.created_by == "PM:alex"


def test_nodes_are_append_only():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    with get_conn() as conn:
        with conn.cursor() as cur:
            with pytest.raises(Exception):
                cur.execute("UPDATE nodes SET content = '{}' WHERE id = %s", (src.id,))
                conn.commit()


def test_stale_propagates_to_dependents():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    evidence = tools.query_data({"row": "complaint"}, [src.id], "agent:researcher")
    claim = tools.add_claim({"text": "unmet need"}, [evidence.id], "agent:researcher")

    add_node(
        NodeType.EVIDENCE,
        {"row": "corrected complaint"},
        [src.id],
        "agent:researcher",
        replaces=evidence.id,
    )

    assert get_node(evidence.id).status == "stale"
    assert get_node(claim.id).status == "stale"


def test_add_claim_rejects_missing_input():
    with pytest.raises(ValueError):
        tools.add_claim({"text": "x"}, ["EVD-999"], "agent:researcher")


def test_web_search_creates_evidence_with_url():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    found = tools.web_search({"url": "https://example.com", "quote": "trend"}, [src.id], "agent:researcher")
    assert found.type == NodeType.EVIDENCE
    assert found.content["url"] == "https://example.com"


def test_add_assumption_requires_inputs():
    with pytest.raises(ValueError):
        tools.add_assumption({"text": "guess"}, [], "agent:researcher")


def test_propose_requirement_links_to_claim():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    evidence = tools.query_data({"row": "complaint"}, [src.id], "agent:researcher")
    claim = tools.add_claim({"text": "unmet need"}, [evidence.id], "agent:researcher")
    requirement = tools.propose_requirement({"text": "fix it"}, [claim.id], "agent:researcher")
    assert requirement.type == NodeType.REQUIREMENT


def test_challenge_creates_contradicting_evidence():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    claim = add_node(NodeType.CLAIM, {"text": "unmet need"}, [src.id], "agent:researcher")
    counter = tools.challenge({"row": "actually fine"}, claim.id, "agent:researcher")
    assert counter.type == NodeType.EVIDENCE
    from app.graph import get_dependents
    assert any(d.id == counter.id for d in get_dependents(claim.id))


def test_ask_pm_allows_no_inputs():
    question = tools.ask_pm({"text": "which market first?"}, None, "agent:researcher")
    assert question.type == NodeType.QUESTION


def test_end_to_end_requirement_traces_to_source():
    src = add_node(NodeType.SOURCE, {"file": "G70 feedback.xlsx"}, [], "tool:import")
    evidence = tools.query_data({"row": "seat too narrow"}, [src.id], "agent:researcher")
    claim = tools.add_claim({"text": "seats too narrow for tall drivers"}, [evidence.id], "agent:researcher")
    requirement = tools.propose_requirement({"text": "widen seat by 2cm"}, [claim.id], "agent:researcher")

    scored = tools.score({"value": 7.5, "breakdown": {}}, requirement.id, "impact*reach", "formula:scoring_v1")
    decision = tools.decide({"verdict": "approve"}, requirement.id, "PM:alex", rationale="matches strategy")

    from app.graph import get_inputs

    assert get_inputs(requirement.id)[0].id == claim.id
    assert get_inputs(claim.id)[0].id == evidence.id
    assert get_inputs(evidence.id)[0].id == src.id
    assert scored.type == NodeType.SCORE
    assert decision.created_by.startswith("PM:")
