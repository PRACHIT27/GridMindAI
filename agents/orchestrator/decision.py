"""What the orchestrator produces: one auditable decision.

Note what is NOT here: raw power, thermal, rack or cost data. The orchestrator
is bound by IAM to shared-db only, so every figure below is something a
specialist agent REPORTED, never something the orchestrator looked up. That is
the provable version of "the orchestrator only sees verdicts", and it is why
the economics live in a nested model -- they are second-hand by construction
and should look it.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Outcome = Literal["approved", "approved_with_conditions", "rejected", "escalated"]


class DecisionEconomics(BaseModel):
    """Money and efficiency, as reported by the Cost and Cooling agents."""
    estimated_monthly_cost_usd: Optional[float] = Field(
        None, description="Recurring monthly cost of the chosen plan.")
    cost_delta_pct: float = Field(
        0.0, description="Change vs the original request. Negative means cheaper.")
    one_time_capex_usd: Optional[float] = Field(
        None, description="One-off spend the plan requires, e.g. a liquid retrofit.")
    payback_months: Optional[float] = Field(
        None, description="Months for recurring savings to repay one_time_capex_usd.")
    monthly_saving_vs_next_best_usd: Optional[float] = Field(
        None, description="Recurring saving against the next-best zone considered.")
    pue_at_chosen_zone: Optional[float] = Field(
        None, description="Power Usage Effectiveness of the chosen zone.")
    pue_at_next_best_zone: Optional[float] = Field(
        None, description="PUE of the next-best zone, for comparison.")
    efficiency_note: str = Field(
        "", description="Why this placement is more or less efficient, in one or two "
                        "sentences, citing the PUE figures.")
    stranded_capacity_avoided: str = Field(
        "", description="Capacity that would have been stranded had a single team decided "
                        "alone -- e.g. power headroom in a zone that cannot be cooled.")


class OrchestratorDecision(BaseModel):
    """The final, reconciled placement decision."""
    workload_id: str
    outcome: Outcome
    chosen_zone: Optional[str] = Field(
        None, description="The single zone all agents can support. Null if escalated.")
    plan: str = Field(
        ..., description="The physically consistent plan, concretely stated.")
    conditions: list[str] = Field(
        default_factory=list,
        description="What must be true for this to proceed, e.g. 'retrofit 1 rack'.")
    delay_hours: float = Field(
        0.0, ge=0, description="Delay before the workload can start.")
    tradeoffs: list[str] = Field(
        default_factory=list,
        description="What was given up and what was gained, one line per trade.")
    economics: DecisionEconomics
    unresolved_conflicts: list[str] = Field(
        default_factory=list,
        description="Conflicts still open. Must be non-empty when escalating.")
    precedent_applied: Optional[str] = Field(
        None, description="Memory Bank precedent id that informed this decision.")
    reasoning: str = Field(
        ..., description="How the conflicting verdicts were reconciled into one plan, "
                         "naming which agent's proposal unlocked it.")
