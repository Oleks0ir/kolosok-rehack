from concurrent.futures import ThreadPoolExecutor

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


def test_import_source_tool_creates_source():
    node = tools.import_source({"file": "G70 feedback.xlsx"}, "tool:ingestion")
    assert node.type == NodeType.SOURCE


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


def test_double_versioning_marks_both_old_versions_stale():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    v1 = tools.query_data({"row": "v1"}, [src.id], "agent:researcher")
    v2 = add_node(NodeType.EVIDENCE, {"row": "v2"}, [src.id], "agent:researcher", replaces=v1.id)
    v3 = add_node(NodeType.EVIDENCE, {"row": "v3"}, [src.id], "agent:researcher", replaces=v2.id)

    assert v2.version == 2
    assert v3.version == 3
    assert get_node(v1.id).status == "stale"
    assert get_node(v2.id).status == "stale"
    assert get_node(v3.id).status == "ok"


def test_scoring_a_stale_node_is_still_allowed():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    evidence = tools.query_data({"row": "v1"}, [src.id], "agent:researcher")
    claim = tools.add_claim({"text": "unmet need"}, [evidence.id], "agent:researcher")
    requirement = tools.propose_requirement({"text": "fix it"}, [claim.id], "agent:researcher")

    add_node(NodeType.EVIDENCE, {"row": "v2"}, [src.id], "agent:researcher", replaces=evidence.id)
    assert get_node(requirement.id).status == "stale"

    scored = tools.score({"value": 1}, requirement.id, "formula", "formula:v1")
    assert scored.type == NodeType.SCORE
    assert scored.status == "ok"


def test_concurrent_add_node_gets_unique_ids():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")

    def make_claim(i):
        return tools.add_claim({"text": f"claim {i}"}, [src.id], "agent:researcher").id

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(make_claim, range(8)))

    assert len(set(ids)) == 8


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


def test_pm_edit_creates_new_version_with_same_inputs_and_marks_dependents_stale():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    evidence = tools.query_data({"row": "complaint"}, [src.id], "agent:researcher")
    claim = tools.add_claim({"text": "v1"}, [evidence.id], "agent:researcher")
    requirement = tools.propose_requirement({"text": "req"}, [claim.id], "agent:researcher")

    edited = tools.edit({"text": "v2"}, claim.id, "PM:alex", rationale="sharper wording")

    from app.graph import list_edges

    assert edited.type == NodeType.CLAIM
    assert edited.version == 2 and edited.replaces == claim.id
    assert list_edges(edited.id) == [{"from_id": edited.id, "to_id": evidence.id, "relation": "derived_from"}]
    assert get_node(requirement.id).status == "stale"
    assert get_node(edited.id).status == "ok"


def test_connect_adds_input_as_new_version_and_rejects_loops():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    e1 = tools.query_data({"row": "a"}, [src.id], "agent:researcher")
    e2 = tools.query_data({"row": "b"}, [src.id], "agent:researcher")
    claim = tools.add_claim({"text": "c"}, [e1.id], "agent:researcher")

    connected = tools.edit(claim.content, claim.id, "PM:alex", "e2 supports it too", add_inputs=[e2.id])

    from app.graph import list_edges

    assert [e["to_id"] for e in list_edges(connected.id)] == [e1.id, e2.id]
    assert get_node(claim.id).status == "stale"
    with pytest.raises(ValueError, match="loop"):
        tools.edit(e1.content, e1.id, "PM:alex", add_inputs=[connected.id])


def test_pm_create_enforces_pm_types_and_input_rules():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    claim = tools.create(NodeType.CLAIM, {"text": "c"}, [src.id], "PM:alex")
    counter = tools.create(NodeType.EVIDENCE, {"text": "no"}, [claim.id], "PM:alex", relation=Relation.CONTRADICTS)

    from app.graph import list_edges

    assert claim.created_by == "PM:alex"
    assert list_edges(counter.id)[0]["relation"] == "contradicts"
    assert tools.create(NodeType.NOTE, {"text": "workshop"}, [], "PM:alex").type == NodeType.NOTE
    with pytest.raises(PermissionError):
        tools.create(NodeType.CLAIM, {"text": "c"}, [src.id], "agent:x")
    with pytest.raises(ValueError):
        tools.create(NodeType.CLAIM, {"text": "c"}, [], "PM:alex")  # claims need inputs
    with pytest.raises(ValueError):
        tools.create(NodeType.DECISION, {"verdict": "approve"}, [src.id], "PM:alex")


def test_edit_rejects_non_pm_and_already_replaced_nodes():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    with pytest.raises(PermissionError):
        tools.edit({"file": "y.csv"}, src.id, "agent:researcher")
    tools.edit({"file": "y.csv"}, src.id, "PM:alex")
    with pytest.raises(ValueError):
        tools.edit({"file": "z.csv"}, src.id, "PM:alex")


def test_revise_redoes_a_stale_chain_step_by_step_on_the_latest_inputs():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    evidence = tools.query_data({"row": "complaint"}, [src.id], "agent:researcher")
    claim = tools.add_claim({"text": "c"}, [evidence.id], "agent:researcher")
    requirement = tools.propose_requirement({"text": "r"}, [claim.id], "agent:researcher")
    edited = tools.edit({"row": "sharper complaint"}, evidence.id, "PM:alex", rationale="typo")

    from app.graph import list_edges

    # the requirement has to wait: its claim is still stale
    with pytest.raises(ValueError, match="first"):
        tools.revise({"text": "r2"}, requirement.id, "agent:loop")
    claim2 = tools.revise({"text": "c2"}, claim.id, "agent:loop", rationale="evidence changed")
    assert claim2.replaces == claim.id and claim2.status == "ok"
    assert [e["to_id"] for e in list_edges(claim2.id)] == [edited.id]
    req2 = tools.revise({"text": "r2"}, requirement.id, "agent:loop")
    assert [e["to_id"] for e in list_edges(req2.id)] == [claim2.id]
    with pytest.raises(ValueError, match="newer version"):
        tools.revise({"text": "again"}, claim.id, "agent:loop")


def test_revise_refuses_fresh_nodes_and_decisions():
    src = add_node(NodeType.SOURCE, {"file": "x.csv"}, [], "tool:import")
    evidence = tools.query_data({"row": "a"}, [src.id], "agent:researcher")
    with pytest.raises(ValueError, match="not stale"):
        tools.revise({"row": "b"}, evidence.id, "agent:loop")
    decision = tools.decide({"verdict": "approve"}, evidence.id, "PM:alex", "fine")
    tools.edit({"row": "a2"}, evidence.id, "PM:alex", rationale="fix")
    with pytest.raises(ValueError, match="re-reviewed"):
        tools.revise({"verdict": "approve"}, decision.id, "agent:loop")
