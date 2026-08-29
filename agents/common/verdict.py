"""The contract every agent speaks.

Nothing crosses an agent boundary as free text. A verdict is either a valid
AgentVerdict or it is a retry -- there is no "mostly parseable" path, because a
half-understood verdict is exactly how a silent wrong approval would happen.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Status = Literal["feasible", "infeasible", "conditional"]
Domain = Literal["power", "cooling", "facilities", "cost"]


class ProposedAlternative(BaseModel):
    """What an agent offers INSTEAD of a flat rejection.

    This is what makes the protocol a negotiation rather than a vote. An agent
    that says "no" without a proposal gives the orchestrator nothing to
    reconcile; an agent that says "no, but zone C works if you accept 12 hours
    of delay" creates a tradeable position.
    """
    description: str = Field(..., description="Concretely, what to do instead.")
    target_zone: Optional[str] = Field(
        None, description="Zone id this alternative would place the workload in, e.g. 'zone-c'.")
    cost_delta_pct: float = Field(
        0.0, description="Cost change vs the original request, percent. Negative means cheaper.")
    delay_hours: float = Field(
        0.0, ge=0, description="Additional delay before the workload could start.")


class AgentVerdict(BaseModel):
    """One domain's answer about one workload request.

    Note that the four specialists are NOT voting on the same question. Power
    feasibility, thermal feasibility, space feasibility and budget feasibility
    are four different questions that happen to share a subject. The
    orchestrator's job is not to tally them.
    """
    agent: Domain
    status: Status
    reasoning: str = Field(
        ..., description="Why, citing the specific constraint and the numbers that drove it.")
    target_zone: Optional[str] = Field(
        None, description="Zone this verdict endorses. Load-bearing: two agents can both "
                          "say 'feasible' about DIFFERENT zones, which is not agreement.")
    proposed_alternative: Optional[ProposedAlternative] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    constraint_snapshot: dict = Field(
        default_factory=dict,
        description="The numbers the agent actually reasoned over, so the verdict can be "
                    "re-checked later against the same ground truth.")

    @field_validator("reasoning")
    @classmethod
    def _reasoning_must_say_something(cls, v: str) -> str:
        if len(v.strip()) < 20:
            raise ValueError("reasoning too thin to audit")
        return v.strip()


class GuardrailResult(BaseModel):
    """Outcome of validating a verdict against ground truth after the fact.

    The model is treated as untrusted. Before a verdict propagates to the
    orchestrator it is re-checked against the SAME constants the agent was
    given -- catching the case where an agent proposes an alternative that
    violates a physical limit it was explicitly told about.
    """
    passed: bool
    violations: list[str] = Field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed


class EscalationVerdict(AgentVerdict):
    """Emitted when the harness exhausts its retries.

    Fail SAFE, never fail open: if the agent could not produce a trustworthy
    answer, the answer is 'infeasible' plus an escalation flag -- not a guess,
    and not a silent success.
    """
    escalated: bool = True
    failure_reason: str = ""
