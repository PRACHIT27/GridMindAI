"""Do four verdicts describe ONE physically consistent plan?

THE CENTRAL IDEA OF THE WHOLE SYSTEM
------------------------------------
This is NOT "do the agents agree". The four specialists are not answering the
same question -- power feasibility, thermal feasibility, physical feasibility
and budget feasibility are four different questions that merely share a
subject. Tallying them is the exact failure GridMind exists to prevent.

The real question is whether the four verdicts, taken together, describe a
single deployable plan. They can all say "feasible" and still describe nothing:

    Power      feasible, zone-a
    Cooling    feasible, zone-c
    Facilities feasible, zone-b
    Cost       feasible, zone-d

Four approvals, zero valid plans. A voting system approves this and the racks
arrive to a room that cannot cool them. Here, it is a ZONE_MISMATCH conflict
that opens a negotiation round.

Deliberately deterministic. Whether two zone ids differ is not a judgement
call, and making a language model decide it would add cost, latency and a
failure mode for no benefit. The model is used for RECONCILING conflicts --
which needs judgement -- not for detecting them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..common.verdict import AgentVerdict


@dataclass(slots=True)
class ConsistencyReport:
    consistent: bool
    endorsed_zones: dict[str, str] = field(default_factory=dict)   # agent -> zone
    blocking_agents: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    candidate_zones: list[str] = field(default_factory=list)
    conflict_type: str = "none"

    @property
    def unanimous_zone(self) -> str | None:
        zones = set(self.endorsed_zones.values())
        return zones.pop() if len(zones) == 1 else None


def check(verdicts: list[AgentVerdict]) -> ConsistencyReport:
    """Assess whether these verdicts describe one plan."""
    rep = ConsistencyReport(consistent=False)

    feasible = [v for v in verdicts if v.status == "feasible"]
    conditional = [v for v in verdicts if v.status == "conditional"]
    infeasible = [v for v in verdicts if v.status == "infeasible"]

    for v in feasible + conditional:
        if v.target_zone:
            rep.endorsed_zones[v.agent] = v.target_zone

    # Zones any agent is willing to work with, including via an alternative.
    proposed: set[str] = set()
    for v in verdicts:
        if v.proposed_alternative and v.proposed_alternative.target_zone:
            proposed.add(v.proposed_alternative.target_zone)
    rep.candidate_zones = sorted(set(rep.endorsed_zones.values()) | proposed)

    # A hard refusal blocks everything until it is renegotiated.
    if infeasible:
        rep.blocking_agents = [v.agent for v in infeasible]
        rep.conflict_type = "hard_refusal"
        for v in infeasible:
            alt = (f" Proposes instead: {v.proposed_alternative.description}"
                   if v.proposed_alternative else " No alternative offered.")
            rep.conflicts.append(
                f"{v.agent} refuses outright: {v.reasoning.strip()[:180]}{alt}")
        return rep

    distinct = set(rep.endorsed_zones.values())

    if len(distinct) > 1:
        # The signature failure: everyone approved, nobody approved the same thing.
        rep.conflict_type = "zone_mismatch"
        detail = ", ".join(f"{a}->{z}" for a, z in sorted(rep.endorsed_zones.items()))
        rep.conflicts.append(
            f"Agents endorse different zones ({detail}). Every verdict is individually "
            f"correct, but together they describe no single deployable plan.")
        return rep

    if not distinct:
        rep.conflict_type = "no_zone_endorsed"
        rep.conflicts.append("No agent endorsed a specific zone, so there is nothing to place.")
        return rep

    if conditional:
        # One zone, but conditions attached: a real plan, not an unconditional yes.
        rep.conflict_type = "conditions_pending"
        for v in conditional:
            cond = (v.proposed_alternative.description
                    if v.proposed_alternative else v.reasoning.strip()[:160])
            rep.conflicts.append(f"{v.agent} is conditional on: {cond}")
        rep.consistent = True      # consistent, but approval carries conditions
        return rep

    rep.consistent = True
    rep.conflict_type = "none"
    return rep


def peer_positions(verdicts: list[AgentVerdict], exclude: str) -> list[dict]:
    """Summarise the OTHER agents' positions for a re-prompt.

    Trimmed to what another domain can act on: the stance, the zone, and any
    concrete alternative. Full reasoning is omitted deliberately -- it is long,
    it is another domain's internal detail, and passing it wholesale invites an
    agent to defer to a neighbour's judgement instead of applying its own.
    """
    out = []
    for v in verdicts:
        if v.agent == exclude:
            continue
        entry: dict = {
            "agent": v.agent,
            "status": v.status,
            "endorses_zone": v.target_zone,
            "position": v.reasoning.strip()[:260],
        }
        if v.proposed_alternative:
            a = v.proposed_alternative
            entry["proposes"] = {
                "description": a.description,
                "zone": a.target_zone,
                "delay_hours": a.delay_hours,
                "cost_delta_pct": a.cost_delta_pct,
            }
        out.append(entry)
    return out
