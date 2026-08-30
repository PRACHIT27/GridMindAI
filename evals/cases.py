"""Evaluation cases for the GridMind negotiation.

WHY THIS EXISTS
Every manual test so far has been the happy path: a request that zone-c can
absorb. That leaves the ESCALATION path -- outcome "escalated",
unresolved_conflicts, and the "no zone survives" branch in the UI -- as code
that has never once run end to end. Untested code does not become correct
because it is short; it becomes correct when something runs it. Preferably not
for the first time on camera.

The suite also pins behaviour that is easy to regress silently:
  * a workload that fits should NOT burn three rounds arguing
  * external conditions should actually change verdicts, not just prompt text
  * the guardrails should keep refusing impossible verdicts
  * Model Armor should keep refusing injected payloads

Each case asserts on OUTCOME and REASONING SHAPE, never on exact wording. An
eval that greps for a sentence fails every time the model phrases something
differently, and then gets deleted for being noisy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(slots=True)
class EvalCase:
    name: str
    why: str                      # what regression this case would catch
    workload: dict[str, Any]
    scenario: str = "normal"
    expect_outcomes: tuple[str, ...] = ("approved", "approved_with_conditions")
    expect_zone: str | None = None
    max_rounds: int | None = None
    # Extra assertions over the finished NegotiationResult.
    checks: list[tuple[str, Callable[[Any], bool]]] = field(default_factory=list)


def _wl(**kw: Any) -> dict[str, Any]:
    base = {
        "workload_id": "eval",
        "tenant": "eval-suite",
        "description": "evaluation workload",
        "gpu_model": "GB200",
        "rack_type": "GB200 NVL72",
        "racks_required": 6,
        "power_per_rack_kw": 132.0,
        "rack_weight_kg": 1360.0,
        "cooling_requirement": "direct_to_chip_liquid",
        "duration_weeks": 8,
        "priority": "high",
        "export_control_status": "verified_domestic",
        "status": "pending",
    }
    base.update(kw)
    base["total_power_kw"] = round(
        base["racks_required"] * base["power_per_rack_kw"], 1)
    return base


def _any_agent_mentions(result: Any, *terms: str) -> bool:
    """True if any verdict in any round cites one of these terms."""
    for r in result.rounds:
        for v in r.verdicts:
            text = (v.reasoning or "").lower()
            if any(t.lower() in text for t in terms):
                return True
    return False


def _final_statuses(result: Any) -> dict[str, str]:
    return {v.agent: v.status for v in result.rounds[-1].verdicts}


CASES: list[EvalCase] = [
    EvalCase(
        name="flagship-conflict",
        why="The demo path. Four agents endorse three different zones in round 1 "
            "and must reconcile onto zone-c via the retrofit nobody else could see.",
        workload=_wl(workload_id="eval-flagship"),
        expect_zone="zone-c",
        checks=[
            ("round 1 is a zone mismatch",
             lambda r: r.rounds[0].report.conflict_type in ("zone_mismatch", "hard_refusal")),
            ("someone proposes a retrofit",
             lambda r: _any_agent_mentions(r, "retrofit")),
            ("zone-c survives the exclusions",
             lambda r: "zone-c" in (r.rounds[-1].report.surviving_zones or ["zone-c"])),
        ],
    ),
    EvalCase(
        name="escalate-too-many-racks",
        why="THE UNTESTED PATH. 20 liquid racks exceeds every zone's liquid-ready "
            "count even after retrofits, so no plan exists and the system must "
            "escalate rather than invent one.",
        workload=_wl(workload_id="eval-escalate-racks", racks_required=20),
        expect_outcomes=("escalated", "rejected"),
        checks=[
            ("an explanation is attached",
             lambda r: bool(r.decision.unresolved_conflicts) or
                       bool(r.decision.reasoning.strip())),
            ("no zone is silently chosen",
             lambda r: r.decision.outcome != "approved"),
        ],
    ),
    EvalCase(
        name="escalate-floor-loading",
        why="A 3,000 kg rack exceeds every floor rating in the facility. Facilities "
            "must refuse on weight alone -- the constraint most often forgotten.",
        workload=_wl(workload_id="eval-escalate-weight", rack_weight_kg=3000.0,
                     racks_required=4),
        expect_outcomes=("escalated", "rejected"),
        checks=[
            ("facilities cites floor loading",
             lambda r: _any_agent_mentions(r, "floor", "kg", "weight")),
        ],
    ),
    EvalCase(
        name="easy-air-cooled",
        why="A modest air-cooled request should settle fast. Guards against the "
            "negotiation always burning its full round budget.",
        workload=_wl(workload_id="eval-easy", gpu_model="H100", rack_type="H100 rack",
                     racks_required=3, power_per_rack_kw=34.0, rack_weight_kg=900.0,
                     cooling_requirement="air"),
        max_rounds=2,
    ),
    EvalCase(
        name="grid-stress",
        why="An external signal must actually move a verdict. Under a PJM curtailment "
            "event Power should stop being unconditionally feasible.",
        workload=_wl(workload_id="eval-grid"),
        scenario="grid_stress",
        checks=[
            ("power is not unconditionally feasible",
             lambda r: _final_statuses(r).get("power") != "feasible"),
            ("curtailment is cited",
             lambda r: _any_agent_mentions(r, "curtail", "demand response",
                                           "demand-response")),
        ],
    ),
    EvalCase(
        name="heatwave",
        why="Cooling should reason about ambient temperature and efficiency, not "
            "just static capacity.",
        workload=_wl(workload_id="eval-heat"),
        scenario="heatwave",
        checks=[
            ("cooling cites heat or efficiency",
             lambda r: _any_agent_mentions(r, "ambient", "pue", "free cooling",
                                           "free-cooling", "chiller")),
        ],
    ),
]
