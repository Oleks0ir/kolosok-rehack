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
