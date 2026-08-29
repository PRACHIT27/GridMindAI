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
        """The compact subset stored on the verdict for later re-checking."""
        return {
            "round": self.round_number,
            "scenario": self.external_signal.get("scenario"),
            "observed_at": self.external_signal.get("observed_at"),
            "zone_ids": sorted(self.live_data.get("zones", {}).keys()),
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
