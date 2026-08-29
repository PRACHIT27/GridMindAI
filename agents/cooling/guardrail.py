"""Cooling Agent guardrail: re-check the verdict against the thermal facts."""
from __future__ import annotations

from ..common.constants import DOMAIN_CONSTANTS
from ..common.constraint_context import ConstraintContext
from ..common.verdict import AgentVerdict, GuardrailResult

HEAT_FRACTION = 0.98


def cooling_guardrail(verdict: AgentVerdict, ctx: ConstraintContext) -> GuardrailResult:
    violations: list[str] = []
    zones: dict = ctx.live_data.get("zones", {})
    facility: dict = ctx.live_data.get("facility_state", {})
    consts = DOMAIN_CONSTANTS["cooling"]

    wl = ctx.workload
    racks = int(wl.get("racks_required", 0) or 0)
    per_rack_kw = float(wl.get("power_per_rack_kw", 0.0) or 0.0)
    total_kw = float(wl.get("total_power_kw") or racks * per_rack_kw)
    heat_kw = total_kw * HEAT_FRACTION
    needs_liquid = "liquid" in str(wl.get("cooling_requirement", "")).lower()

    def check_zone(zone_id: str | None, label: str) -> None:
        if not zone_id:
            return
        if zone_id not in zones:
            violations.append(
                f"{label} names zone '{zone_id}', which does not exist. "
                f"Known zones: {sorted(zones)}.")
            return

        z = zones[zone_id]

        # The per-rack ceiling is the single most important check. Total
        # headroom does not rescue it: a 132 kW rack cannot be air-cooled no
        # matter how much spare capacity the zone reports.
        ceiling = float(z.get("max_kw_per_rack", 0.0))
        if per_rack_kw > ceiling:
            violations.append(
                f"{label} endorses {zone_id}, which is {z.get('cooling_type')} with a "
                f"{ceiling:.0f} kW/rack ceiling, but each rack draws {per_rack_kw:.0f} kW. "
                f"Total thermal headroom is irrelevant to a per-rack violation.")

        headroom = float(z.get("thermal_headroom_kw", 0.0))
        if heat_kw > headroom:
            violations.append(
                f"{label} endorses {zone_id}, which has {headroom:,.0f} kW of thermal "
                f"headroom against {heat_kw:,.0f} kW of new heat -- short by "
                f"{heat_kw - headroom:,.0f} kW.")

        if needs_liquid:
            if z.get("cooling_type") != "liquid_dlc":
                violations.append(
                    f"{label} endorses {zone_id}, which is {z.get('cooling_type')}, for a "
                    f"workload requiring direct-to-chip liquid cooling.")
            ports = int(z.get("free_cdu_ports", 0) or 0)
            if racks > ports:
                violations.append(
                    f"{label} endorses {zone_id}, which has {ports} free CDU ports but the "
                    f"request needs {racks}.")

    if verdict.status in ("feasible", "conditional"):
        check_zone(verdict.target_zone, "Verdict")
    if verdict.proposed_alternative is not None:
        check_zone(verdict.proposed_alternative.target_zone, "Proposed alternative")

    if verdict.status == "feasible" and not verdict.target_zone:
        violations.append("Status is 'feasible' but no target_zone was given.")

    # Water is a legal ceiling under Virginia's withdrawal permitting, not just
    # a physical one -- exceeding it is a permit violation, not inefficiency.
    makeup = float(facility.get("cooling_tower_makeup_water_gpm", 0.0))
    limit = float(facility.get("water_permit_limit_gpm", 0.0))
    if limit and verdict.status == "feasible":
        projected = makeup + heat_kw * 0.0125
        if projected > limit:
            violations.append(
                f"Approving this raises cooling tower makeup water to {projected:.0f} gpm, "
                f"above the {limit:.0f} gpm permit limit (9VAC25-210).")

    # Efficiency ceiling.
    if verdict.status == "feasible" and verdict.target_zone in zones:
        pue = float(zones[verdict.target_zone].get("current_pue", 0.0))
        if pue > consts["max_acceptable_pue"]:
            violations.append(
                f"{verdict.target_zone} is already running at PUE {pue:.2f}, above the "
                f"{consts['max_acceptable_pue']:.2f} ceiling; adding load cannot be "
                f"unconditionally feasible.")

    return GuardrailResult(passed=not violations, violations=violations)
