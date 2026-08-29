"""Power Agent guardrail: re-check the model's verdict against the electrical facts.

The per-agent safety net. The shared harness knows HOW to retry; only this file
knows WHAT counts as an impossible electrical answer.

Runs after every model call, before the verdict is allowed to leave the agent.
The model is untrusted until its answer survives the same numbers it was given
-- which catches the failure that would be most damaging in production: an
agent confidently approving a zone that cannot carry the load, using data that
was sitting right there in its own context.

On a violation the harness re-prompts with the violation text attached, so
attempt 2 sees exactly what it got wrong. It usually self-corrects.
"""
from __future__ import annotations

from ..common.constants import DOMAIN_CONSTANTS
from ..common.constraint_context import ConstraintContext
from ..common.verdict import AgentVerdict, GuardrailResult


def power_guardrail(verdict: AgentVerdict, ctx: ConstraintContext) -> GuardrailResult:
    violations: list[str] = []
    zones: dict = ctx.live_data.get("zones", {})
    facility: dict = ctx.live_data.get("facility_state", {})
    consts = DOMAIN_CONSTANTS["power"]

    workload = ctx.workload
    required_kw = float(workload.get("total_power_kw")
                        or workload.get("racks_required", 0) * workload.get("power_per_rack_kw", 0))

    def check_zone(zone_id: str | None, label: str) -> None:
        if not zone_id:
            return
        if zone_id not in zones:
            violations.append(
                f"{label} names zone '{zone_id}', which does not exist. "
                f"Known zones: {sorted(zones)}.")
            return

        z = zones[zone_id]
        headroom = float(z.get("headroom_kw", 0.0))
        if required_kw > headroom:
            violations.append(
                f"{label} endorses {zone_id}, but it has {headroom:,.0f} kW of headroom "
                f"against a {required_kw:,.0f} kW request -- short by "
                f"{required_kw - headroom:,.0f} kW.")

        circuits_needed = required_kw / consts["kw_per_30a_208v_circuit"]
        spare = float(z.get("spare_30a_208v_circuits", 0))
        if circuits_needed > spare:
            violations.append(
                f"{label} endorses {zone_id}, which has {spare:.0f} spare circuits but the "
                f"request needs about {circuits_needed:.0f}.")

        outage = z.get("planned_outage")
        if outage and verdict.status == "feasible":
            violations.append(
                f"{label} reports {zone_id} feasible, but {outage.get('switchgear')} has a "
                f"planned outage starting in {outage.get('starts_in_hours')} h. That is at "
                f"best conditional, not feasible.")

    # Only zones the agent ENDORSED are checked. An 'infeasible' verdict naming
    # a zone is explaining why it failed, not approving it.
    if verdict.status in ("feasible", "conditional"):
        check_zone(verdict.target_zone, "Verdict")

    # Alternatives are checked too. An agent can pass its main verdict and
    # smuggle an impossible fallback into proposed_alternative, which the
    # orchestrator would then treat as a real option during negotiation.
    if verdict.proposed_alternative is not None:
        check_zone(verdict.proposed_alternative.target_zone, "Proposed alternative")

    # Without a zone id the orchestrator cannot check cross-agent physical
    # consistency at all -- "everyone said feasible" would look like agreement.
    if verdict.status == "feasible" and not verdict.target_zone:
        violations.append("Status is 'feasible' but no target_zone was given.")

    # Facility-wide ceiling: never plan above 85% of firm capacity. The margin
    # absorbs a utility transient without tripping into load shed.
    firm_mw = float(facility.get("substation_firm_capacity_mw", 0.0))
    current_mw = float(facility.get("substation_current_load_mw", 0.0))
    if firm_mw and verdict.status == "feasible":
        projected = current_mw + (required_kw / 1000.0)
        ceiling = firm_mw * consts["max_sustained_utilization_pct"] / 100.0
        if projected > ceiling:
            violations.append(
                f"Approving this pushes the substation to {projected:.1f} MW, above the "
                f"{ceiling:.1f} MW ceiling ({consts['max_sustained_utilization_pct']}% of "
                f"{firm_mw:.1f} MW firm capacity).")

    # Curtailment is an obligation with a penalty attached, not a preference.
    signal = ctx.external_signal
    if signal.get("demand_response_event_active") and verdict.status == "feasible":
        violations.append(
            f"A demand-response event is active with a "
            f"{signal.get('curtailment_obligation_mw')} MW curtailment obligation. "
            f"New load cannot be approved as unconditionally feasible during an event.")

    return GuardrailResult(passed=not violations, violations=violations)
