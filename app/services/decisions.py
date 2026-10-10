from __future__ import annotations

import copy
from typing import Any

from app import db
from app.models import (
    DecisionRequest,
    FinalizeRequest,
    Requirement,
    SimulationRequest,
    SpecificationRequest,
    new_id,
    utc_now,
)
from app.services.llm import complete_json
from app.services.personas import simulate
from app.services.pipeline import _audit, _store_requirements


def _requirement(requirement_id: str) -> tuple[str, Requirement]:
    found = db.get_row(
        "requirements",
        "SELECT * FROM requirements WHERE id=? ORDER BY rowid DESC LIMIT 1",
        (requirement_id,),
    )
    if not found:
        raise ValueError("Requirement not found")
    return found["run_id"], Requirement(**found)


def decide(requirement_id: str, request: DecisionRequest) -> dict[str, Any]:
    run_id, current = _requirement(requirement_id)
    before = current.model_dump(mode="json")
    actor = {"type": "human", "name": request.actor_name}
    if request.action == "edit":
        if not request.edited_text or len(request.edited_text.strip()) < 8:
            raise ValueError("Add the edited requirement text before saving an edit.")
        current.status = "edited"
        edited = current.model_copy(deep=True)
        edited.id = new_id("REQ")
        edited.text = request.edited_text.strip()
        edited.status = "proposed"
        edited.version = current.version + 1
        edited.parent_id = current.id
        edited.target_spec = None
        edited.specification_status = "not_started"
        _store_requirements(run_id, [current, edited])
        after: dict[str, Any] = {"original": current.model_dump(mode="json"), "new_version": edited.model_dump(mode="json")}
        target = edited.id
    else:
        current.status = {
            "approve": "approved",
            "reject": "rejected",
            "challenge": "challenged",
        }.get(request.action, request.action)
        _store_requirements(run_id, [current])
        after = current.model_dump(mode="json")
        target = current.id
    challenge_response = None
    if request.action == "challenge":
        evidence_rows = [
            row for row in db.list_rows("evidence", "SELECT * FROM evidence WHERE run_id=?", (run_id,))
        ]
        linked_signals = [
            signal for signal in db.list_rows("signals", "SELECT * FROM signals WHERE run_id=?", (run_id,))
            if signal["id"] in current.signal_ids
        ]
        evidence_ids = {eid for signal in linked_signals for eid in signal["evidence_ids"]}
        relevant = [row for row in evidence_rows if row["id"] in evidence_ids]
        review = complete_json(
            "A product manager challenged this customer requirement. Reassess only the provided evidence and return JSON "
            '{"response":"short review","evidence_gaps":["..."],"suggested_action":"..."}; do not invent sources.',
            {"requirement": current.model_dump(mode="json"), "challenge": request.comment, "evidence": relevant[:12]},
        )
        challenge_response = review or {
            "response": "Challenge recorded. Revisit the linked evidence and rationale before approving this requirement.",
            "evidence_gaps": ["Local rule-based review cannot verify external sources."],
            "suggested_action": "Review the linked evidence and update the requirement if needed.",
        }
        after = {**after, "challenge_response": challenge_response}
    _audit(
        run_id,
        f"M6.{request.action}",
        target,
        request.comment,
        actor=actor,
        before=before,
        after=after,
        input_refs=[current.id, *current.signal_ids],
    )
    return {"run_id": run_id, "requirement": after, "challenge_response": challenge_response}


def specify(requirement_id: str, request: SpecificationRequest) -> dict[str, Any]:
    run_id, requirement = _requirement(requirement_id)
    if requirement.status != "approved":
        raise ValueError("Complete the M6 PM approval before moving this requirement through M7.")
    before = requirement.model_dump(mode="json")
    suggestion = request.target_spec
    if not suggestion:
        draft = complete_json(
            "Suggest one measurable, customer-facing target for this requirement. Flag any invented number as a proposed "
            "assumption. Return JSON {target_spec: string}.",
            {"requirement": requirement.model_dump(mode="json"), "evidence_level": requirement.evidence_level},
        )
        suggestion = str((draft or {}).get("target_spec") or (
            "Proposed target: establish a current customer baseline, then improve the measured task-success rate by "
            "at least 10 percentage points in successor-model validation. The baseline and target are assumptions "
            "for PM review."
        ))
    requirement.target_spec = suggestion[:1000]
    requirement.specification_status = "approved" if request.approve else "proposed"
    _store_requirements(run_id, [requirement])
    _audit(
        run_id,
        "M7.specification.approved" if request.approve else "M7.specification.proposed",
        requirement.id,
        request.comment,
        actor={"type": "human", "name": request.actor_name},
        before=before,
        after=requirement.model_dump(mode="json"),
        input_refs=[requirement.id, *requirement.signal_ids],
    )
    return {"run_id": run_id, "requirement": requirement.model_dump(mode="json")}


def simulate_run(run_id: str, request: SimulationRequest) -> dict[str, Any]:
    run = db.get_row("runs", "SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        raise ValueError("Run not found")
    primary = simulate(request.options)
    requirements = [
        Requirement(**row)
        for row in db.list_rows("requirements", "SELECT * FROM requirements WHERE run_id=? ORDER BY score DESC", (run_id,))
    ]
    requirement_inputs = {item.id: item.text for item in requirements}
    requirement_simulation = simulate(requirement_inputs)
    rating_by_id = requirement_simulation["option_averages"]
    before = []
    score_changed = False
    for requirement in requirements:
        breakdown = requirement.score_breakdown
        if request.include_in_score:
            before.append(requirement.model_dump(mode="json"))
            base_score = breakdown.get("simulation_base_score", requirement.score)
            base_factors = breakdown.get("simulation_base_factors", copy.deepcopy(breakdown.get("factors", {})))
            value = float(rating_by_id.get(requirement.id, 50))
            factors = copy.deepcopy(base_factors)
            for factor in factors.values():
                factor["weight"] = round(float(factor.get("weight", 0)) * 0.9, 3)
                factor["points"] = round(float(factor.get("points", 0)) * 0.9, 1)
            factors["persona_simulation"] = {
                "value": round(value / 100, 2),
                "weight": 0.1,
                "points": round(value * 0.1, 1),
                "evidence_level": "weak",
                "simulated": True,
            }
            requirement.score = round(float(base_score) * 0.9 + value * 0.1)
            breakdown["simulation_base_score"] = base_score
            breakdown["simulation_base_factors"] = base_factors
            breakdown["simulation_enabled"] = True
            breakdown["factors"] = factors
            breakdown["total"] = requirement.score
            score_changed = True
        elif breakdown.get("simulation_enabled"):
            before.append(requirement.model_dump(mode="json"))
            requirement.score = int(breakdown.get("simulation_base_score", requirement.score))
            breakdown["factors"] = copy.deepcopy(breakdown.get("simulation_base_factors", {}))
            breakdown["total"] = requirement.score
            breakdown.pop("simulation_base_score", None)
            breakdown.pop("simulation_base_factors", None)
            breakdown.pop("simulation_enabled", None)
            score_changed = True
    if score_changed:
        by_category: dict[str, list[Requirement]] = {}
        for requirement in requirements:
            by_category.setdefault(requirement.category, []).append(requirement)
        for group in by_category.values():
            for rank, requirement in enumerate(sorted(group, key=lambda item: item.score, reverse=True), start=1):
                requirement.score_breakdown["category_rank"] = rank
        _store_requirements(run_id, requirements)
        _audit(
            run_id,
            "M8.simulation.included_in_score" if request.include_in_score else "M8.simulation.removed_from_score",
            run_id,
            "PM enabled a reversible 10% low-evidence persona factor." if request.include_in_score
            else "PM removed the persona factor and restored the saved base scores.",
            actor={"type": "human", "name": request.actor_name},
            before=before,
            after=[item.model_dump(mode="json") for item in requirements],
            input_refs=[item.id for item in requirements],
        )
    result = {
        **primary,
        "requirement_simulation": requirement_simulation,
        "include_in_score": request.include_in_score,
        "evidence_level": "weak",
    }
    simulation_id = new_id("SIM")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO simulations(id,run_id,results_json,include_in_score,created_at) VALUES(?,?,?,?,?)",
            (simulation_id, run_id, db.dumps(result), int(request.include_in_score), utc_now()),
        )
    _audit(
        run_id,
        "M8.simulation.completed",
        simulation_id,
        result["note"],
        actor={"type": "ai", "name": "synthetic-personas", "model_version": "rules-v1"},
        after=result,
        input_refs=[run_id],
    )
    return {"id": simulation_id, **result}


def finalize(run_id: str, request: FinalizeRequest) -> dict[str, Any]:
    run = db.get_row("runs", "SELECT * FROM runs WHERE id=?", (run_id,))
    if not run:
        raise ValueError("Run not found")
    requirements = db.list_rows(
        "requirements",
        "SELECT * FROM requirements WHERE run_id=?",
        (run_id,),
    )
    by_id = {item["id"]: item for item in requirements}
    selected = request.requirement_ids or [
        item["id"] for item in requirements
        if item["status"] == "approved" and item["specification_status"] == "approved"
    ]
    if not selected:
        raise ValueError("Approve at least one requirement before the final sign-off.")
    missing = [item for item in selected if item not in by_id]
    if missing:
        raise ValueError("One or more selected requirements do not belong to this run.")
    unapproved = [
        item for item in selected
        if by_id[item]["status"] != "approved" or by_id[item]["specification_status"] != "approved"
    ]
    if unapproved:
        raise ValueError("Gate 2 accepts only requirements approved at M6 and with an approved specification at M7.")
    final = {
        "signed_off": True,
        "requirement_ids": selected,
        "requirement_count": len(selected),
        "comment": request.comment,
        "actor": request.actor_name,
        "signed_at": utc_now(),
    }
    before = run.get("final")
    with db.connect() as conn:
        conn.execute("UPDATE runs SET final_json=? WHERE id=?", (db.dumps(final), run_id))
    _audit(
        run_id,
        "M9.final_decision.signed_off",
        run_id,
        request.comment,
        actor={"type": "human", "name": request.actor_name},
        before=before,
        after=final,
        input_refs=selected,
    )
    return final
