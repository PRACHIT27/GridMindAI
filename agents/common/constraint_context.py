"""The constraint harness: assembles all four context parts, identically, for
every agent.

WHY THIS IS A MODULE AND NOT PROMPT TEXT
----------------------------------------
If each agent's constraints lived in its own prompt string, four things go
wrong: the constants drift apart between agents, nobody can diff what an agent
was actually told, the guardrail has no ground truth to re-check against, and
a verdict cannot be reproduced later because the inputs weren't recorded.

Assembling context as DATA fixes all four. The same dict that goes into the
prompt is the dict the guardrail validates against and the dict stored in the
verdict's constraint_snapshot -- so "what did the agent know when it decided
this?" always has an exact answer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import obs
from .constants import constants_for
from .data_access import read_live_data
from .external_signals import get_external_signal
from .policy import policy_for


# Fields worth putting in front of a human auditor, per domain. The full zone
# record is too wide for a report; these are the values the agents actually
# reason over and cite, so they are what a reader needs in order to check the
# prose against the data.
#
# Module scope, not a class attribute: inside a @dataclass a plain dict is
# treated as a field with a mutable default and raises at import.
EVIDENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "power": ("breaker_capacity_kw", "allocated_kw", "headroom_kw",
              "spare_30a_208v_circuits", "planned_outage"),
    "cooling": ("cooling_type", "max_kw_per_rack", "thermal_headroom_kw",
                "free_cdu_ports", "current_pue"),
    "facilities": ("available_racks", "liquid_ready_racks", "retrofittable_racks",
                   "floor_load_limit_kg_per_rack"),
    "cost": ("cost_per_kw_month_usd", "liquid_retrofit_cost_usd_per_rack",
             "install_labor_rate_usd_per_hour"),
}


@dataclass(slots=True)
class ConstraintContext:
    """Everything one agent knows, in one auditable object."""
    domain: str
    workload: dict[str, Any]
    internal_constants: dict[str, Any]
    live_data: dict[str, Any]
    external_signal: dict[str, Any]
    policy_context: dict[str, Any]
    correlation_id: str
    # Populated on rounds 2+ with the other agents' positions. Empty on round 1
    # BY DESIGN: round 1 must be an independent judgment, or the agents just
    # anchor on whoever answered first.
    peer_positions: list[dict[str, Any]] = field(default_factory=list)
    round_number: int = 1

    def to_prompt_block(self) -> str:
        """Render as stable, sorted JSON.

        sort_keys is not cosmetic: stable ordering keeps the prompt prefix
        identical across calls, which is what makes context caching effective
        and keeps the credit burn down.
        """
        payload = {
            "workload_request": self.workload,
            "internal_constants": self.internal_constants,
            "live_facility_data": self.live_data,
            "external_signal": self.external_signal,
            "policy_context": self.policy_context,
        }
        if self.peer_positions:
            payload["peer_agent_positions"] = self.peer_positions
        return json.dumps(payload, indent=2, sort_keys=True, default=str)

    def snapshot(self) -> dict[str, Any]:
        """What this agent was GIVEN, recorded by the harness.

        Deliberately captured here rather than asked of the model. The point of
        a snapshot is to let a human check the agent's prose against the data it
        actually saw -- and a model that will invent a headroom figure will just
        as happily invent the snapshot that appears to support it. Self-reported
        evidence is not evidence.

        In practice the agents left this field empty anyway: an unstructured
        dict in the response schema gives a model nothing to fill in, so
        verdicts arrived carrying reasoning with no numbers behind it.
        """
        fields = EVIDENCE_FIELDS.get(self.domain, ())
        zones = self.live_data.get("zones", {})
        evidence = {
            zid: {f: z.get(f) for f in fields if f in z}
            for zid, z in sorted(zones.items())
        }
        return {
            "round": self.round_number,
            "scenario": self.external_signal.get("scenario"),
            "observed_at": self.external_signal.get("observed_at"),
            "zone_ids": sorted(zones.keys()),
            # The auditable half: the figures behind whatever the agent claimed.
            "evidence_seen": evidence,
            "external_signal_seen": {
                k: v for k, v in self.external_signal.items()
                if k not in ("observed_at", "scenario", "source")
            },
        }


def build_constraint_context(
    domain: str,
    workload: dict[str, Any],
    *,
    correlation_id: str,
    scenario: str = "normal",
    peer_positions: list[dict[str, Any]] | None = None,
    round_number: int = 1,
) -> ConstraintContext:
    """Assemble the four-part context for one agent, one request, one round.

    Note the ordering: every deterministic input is gathered BEFORE the model
    is called. The LLM never decides what data it gets -- it only reasons over
    what the harness handed it. That is the whole point of the harness, and it
    is why a verdict is reproducible.
    """
    ctx = ConstraintContext(
        domain=domain,
        workload=workload,
        internal_constants=constants_for(domain),
        live_data=read_live_data(domain, correlation_id=correlation_id),
        external_signal=get_external_signal(domain, scenario=scenario),
        policy_context=policy_for(domain),
        correlation_id=correlation_id,
        peer_positions=peer_positions or [],
        round_number=round_number,
    )

    obs.log(
        "constraint_context_built",
        agent=domain,
        correlation_id=correlation_id,
        round=round_number,
        scenario=scenario,
        zone_count=len(ctx.live_data.get("zones", {})),
        peer_position_count=len(ctx.peer_positions),
        policy_citations=(len(ctx.policy_context["federal"]) + len(ctx.policy_context["state"])),
    )
    return ctx
