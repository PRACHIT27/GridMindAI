"""Cost Agent guardrail: re-check the verdict against the financial facts."""
from __future__ import annotations

from ..common.constants import DOMAIN_CONSTANTS
from ..common.constraint_context import ConstraintContext
from ..common.verdict import AgentVerdict, GuardrailResult

HOURS_PER_MONTH = 730.0


def cost_guardrail(verdict: AgentVerdict, ctx: ConstraintContext) -> GuardrailResult:
    violations: list[str] = []
    zones: dict = ctx.live_data.get("zones", {})
    facility: dict = ctx.live_data.get("facility_state", {})
    consts = DOMAIN_CONSTANTS["cost"]

    wl = ctx.workload
    racks = int(wl.get("racks_required", 0) or 0)
    total_kw = float(wl.get("total_power_kw")
                     or racks * float(wl.get("power_per_rack_kw", 0.0) or 0.0))

    def check_zone(zone_id: str | None, label: str) -> None:
        if not zone_id:
            return
        if zone_id not in zones:
            violations.append(
                f"{label} names zone '{zone_id}', which does not exist. "
                f"Known zones: {sorted(zones)}.")
            return

        z = zones[zone_id]
        added_monthly = total_kw * float(z.get("cost_per_kw_month_usd", 0.0))
        remaining = float(facility.get("budget_remaining_usd", 0.0))
        if added_monthly > remaining:
            violations.append(
                f"{label} endorses {zone_id} at ${added_monthly:,.0f}/month, exceeding the "
                f"${remaining:,.0f} remaining in the operating budget.")

    if verdict.status in ("feasible", "conditional"):
        check_zone(verdict.target_zone, "Verdict")
    if verdict.proposed_alternative is not None:
        check_zone(verdict.proposed_alternative.target_zone, "Proposed alternative")

    if verdict.status == "feasible" and not verdict.target_zone:
        violations.append("Status is 'feasible' but no target_zone was given.")

    # Unit-economics ceiling.
    current = float(facility.get("cost_per_gpu_hour_usd", 0.0))
    if current and current > consts["max_cost_per_gpu_hour_usd"] and verdict.status == "feasible":
        violations.append(
            f"Cost per GPU-hour is already ${current:.2f}, above the "
            f"${consts['max_cost_per_gpu_hour_usd']:.2f} ceiling.")

    # A cost saving claimed without a number cannot be audited, and an
    # unquantified saving is exactly the kind of thing that ends up in a
    # report and then in a budget nobody can reconcile.
    alt = verdict.proposed_alternative
    if alt is not None and alt.cost_delta_pct == 0.0 and "sav" in alt.description.lower():
        violations.append(
            "The proposed alternative claims a saving but reports cost_delta_pct of 0. "
            "Quantify the saving as a percentage against the original request.")

    return GuardrailResult(passed=not violations, violations=violations)
