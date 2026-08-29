"""Facilities Agent guardrail: re-check the verdict against the physical facts."""
from __future__ import annotations

from ..common.constants import DOMAIN_CONSTANTS
from ..common.constraint_context import ConstraintContext
from ..common.verdict import AgentVerdict, GuardrailResult


def facilities_guardrail(verdict: AgentVerdict, ctx: ConstraintContext) -> GuardrailResult:
    violations: list[str] = []
    zones: dict = ctx.live_data.get("zones", {})
    consts = DOMAIN_CONSTANTS["facilities"]
    signal = ctx.external_signal

    wl = ctx.workload
    racks = int(wl.get("racks_required", 0) or 0)
    weight = float(wl.get("rack_weight_kg", 0.0) or 0.0)
    needs_liquid = "liquid" in str(wl.get("cooling_requirement", "")).lower()

    def check_zone(zone_id: str | None, label: str, alt=None) -> None:
        if not zone_id:
            return
        if zone_id not in zones:
            violations.append(
                f"{label} names zone '{zone_id}', which does not exist. "
                f"Known zones: {sorted(zones)}.")
            return

        z = zones[zone_id]

        available = int(z.get("available_racks", 0) or 0)
        if racks > available:
            violations.append(
                f"{label} endorses {zone_id}, which has {available} free racks against a "
                f"{racks}-rack request.")

        # Floor loading is a hard physical limit and the one most often missed.
        limit = float(z.get("floor_load_limit_kg_per_rack", 0.0))
        if weight and limit and weight > limit:
            violations.append(
                f"{label} endorses {zone_id}, whose floor is rated {limit:,.0f} kg/rack, "
                f"but each rack weighs {weight:,.0f} kg -- over by {weight - limit:,.0f} kg.")

        if needs_liquid:
            ready = int(z.get("liquid_ready_racks", 0) or 0)
            retrofittable = int(z.get("retrofittable_racks", 0) or 0)
            shortfall = racks - ready

            if shortfall > 0:
                # A shortfall is only acceptable if this verdict actually
                # proposes retrofitting enough racks AND allows time for it.
                # Otherwise the agent is quietly approving racks that are not
                # plumbed and cannot carry the workload.
                if alt is None:
                    violations.append(
                        f"{label} endorses {zone_id}, which has {ready} liquid-ready racks "
                        f"against {racks} needed, with no retrofit proposed to cover the "
                        f"{shortfall}-rack shortfall.")
                elif shortfall > retrofittable:
                    violations.append(
                        f"{label} would need {shortfall} racks retrofitted in {zone_id}, but "
                        f"only {retrofittable} are retrofittable.")
                else:
                    needed_hours = shortfall * consts["liquid_retrofit_hours_per_rack"]
                    if alt.delay_hours < needed_hours:
                        violations.append(
                            f"{label} proposes retrofitting {shortfall} rack(s) in {zone_id} "
                            f"but allows only {alt.delay_hours:.0f} h; that needs at least "
                            f"{needed_hours:.0f} h at "
                            f"{consts['liquid_retrofit_hours_per_rack']:.0f} h per rack.")

    alt = verdict.proposed_alternative
    if verdict.status in ("feasible", "conditional"):
        # A 'conditional' verdict paired with a retrofit proposal for the SAME
        # zone is the intended resolution path, so evaluate them together.
        same_zone_alt = alt if (alt and alt.target_zone == verdict.target_zone) else None
        check_zone(verdict.target_zone, "Verdict", same_zone_alt)
    if alt is not None and alt.target_zone != verdict.target_zone:
        check_zone(alt.target_zone, "Proposed alternative", alt)

    if verdict.status == "feasible" and not verdict.target_zone:
        violations.append("Status is 'feasible' but no target_zone was given.")

    # Crew reality: you cannot install with nobody on site.
    if verdict.status == "feasible":
        if needs_liquid and int(signal.get("liquid_cooling_certified_techs", 0)) < 1:
            violations.append(
                "No liquid-cooling-certified technicians are available, so a liquid "
                "install cannot be unconditionally feasible.")
        if int(signal.get("certified_technicians_on_shift", 0)) < consts[
                "crew_size_required_per_rack"]:
            violations.append(
                f"Only {signal.get('certified_technicians_on_shift')} technicians are on "
                f"shift; {consts['crew_size_required_per_rack']} are required per rack.")

    return GuardrailResult(passed=not violations, violations=violations)
