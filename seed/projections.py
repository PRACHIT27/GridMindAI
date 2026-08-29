"""Project the single derived facility into four incompatible domain views.

Each function returns (zones, facility) destined for ONE database. The four
views share zone ids and reconcile to the same physics, but expose disjoint
fields: power sees breakers, cooling sees CDUs, facilities sees rack
inventory, cost sees dollars.

That disjointness is the product thesis. Cooling can compute that zone-c has
thermal room and still have no idea it is one liquid-ready rack short, because
rack inventory simply is not in cooling-db -- and IAM guarantees it cannot go
look.
"""
from __future__ import annotations

from typing import Any

from .facility_model import (AIR_COOLING_CEILING_KW, FACILITY,
                             LIQUID_COOLING_CEILING_KW, DerivedFacility)


def provenance(f: DerivedFacility) -> dict[str, Any]:
    """Recipe card stamped into every facility document.

    Anyone reading the database -- including a judge -- can see exactly which
    inputs produced these numbers and rebuild them byte-for-byte. That turns
    "we didn't cherry-pick these figures to make our demo work" from a claim
    into something checkable in one command.

    Deliberately carries no domain facts, so it is safe to copy into all four
    databases without leaking anything across the isolation boundary.
    """
    return {
        "generator": "seed/facility_model.py",
        "seed": f.seed,
        "sim_hour_et": f.sim_hour,
        "season": f.season,
        "rack_count": sum(len(z.racks) for z in f.zones),
        "reproduce_with": (f"python -m seed.generate_seed_data "
                           f"--seed {f.seed} --hour {f.sim_hour} --season {f.season}"),
    }


def project_power(f: DerivedFacility) -> tuple[dict, dict]:
    zones = {
        z.spec.zone_id: {
            "zone_id": z.spec.zone_id,
            "upstream_switchgear": z.spec.upstream_switchgear,
            "breaker_capacity_kw": z.breaker_capacity_kw,
            "allocated_kw": z.it_load_kw,
            "headroom_kw": round(z.breaker_capacity_kw - z.it_load_kw, 1),
            "utilization_pct": z.power_utilization_pct,
            "spare_30a_208v_circuits": z.spare_circuits,
            "installed_racks": len(z.racks),
            "feed_redundancy": "N+1" if z.spec.upstream_switchgear == "SG-3" else "2N",
            "planned_outage": z.spec.planned_outage,
            "notes": z.spec.notes["power"],
        }
        for z in f.zones
    }
    facility = {
        "substation_current_load_mw": f.substation_load_mw,
        "substation_firm_capacity_mw": FACILITY["substation_firm_capacity_mw"],
        "utility_feed_mw": FACILITY["utility_feed_mw"],
        "contracted_demand_mw": FACILITY["contracted_demand_mw"],
        "firm_capacity_utilization_pct": round(
            100.0 * f.substation_load_mw / FACILITY["substation_firm_capacity_mw"], 1),
        "ups_strings_online": FACILITY["ups_strings_online"],
        "ups_strings_total": FACILITY["ups_strings_total"],
        "generator_fuel_hours": FACILITY["generator_fuel_hours"],
        "sim_hour_et": f.sim_hour,
        "provenance": provenance(f),
    }
    return zones, facility


def project_cooling(f: DerivedFacility) -> tuple[dict, dict]:
    zones = {
        z.spec.zone_id: {
            "zone_id": z.spec.zone_id,
            "cooling_type": z.spec.cooling_type,
            "max_kw_per_rack": (AIR_COOLING_CEILING_KW
                                if z.spec.cooling_type == "air_crah"
                                else LIQUID_COOLING_CEILING_KW),
            "thermal_capacity_kw": z.thermal_capacity_kw,
            "current_thermal_load_kw": z.thermal_load_kw,
            "thermal_headroom_kw": round(z.thermal_capacity_kw - z.thermal_load_kw, 1),
            "thermal_utilization_pct": z.thermal_utilization_pct,
            "current_pue": z.pue,
            "free_cdu_ports": z.spec.free_cdu_ports,
            # Air zones run hotter at the inlet for the same outside air.
            "inlet_temp_c": round(19.0 + 0.18 * (f.ambient_c - 18.0)
                                  + (2.5 if z.spec.cooling_type == "air_crah" else 0.0), 1),
            "notes": z.spec.notes["cooling"],
        }
        for z in f.zones
    }
    facility = {
        "chillers_online": FACILITY["chillers_online"],
        "chillers_total": FACILITY["chillers_total"],
        "chiller_capacity_mw_thermal": FACILITY["chiller_capacity_mw_thermal"],
        "chiller_in_maintenance": FACILITY["chiller_in_maintenance"],
        "total_thermal_load_kw": f.total_thermal_load_kw,
        "chiller_utilization_pct": round(
            100.0 * f.total_thermal_load_kw
            / (FACILITY["chiller_capacity_mw_thermal"] * 1000.0), 1),
        "facility_pue": f.facility_pue,
        "ambient_dry_bulb_c": f.ambient_c,
        "relative_humidity_pct": f.humidity_pct,
        "free_cooling_active": f.ambient_c < 18.0,
        # Makeup water scales with the heat actually being rejected, so it
        # moves with load rather than sitting as a static literal.
        "cooling_tower_makeup_water_gpm": round(f.total_thermal_load_kw * 0.0125, 1),
        "water_permit_limit_gpm": FACILITY["water_permit_limit_gpm"],
        "sim_hour_et": f.sim_hour,
        "provenance": provenance(f),
    }
    return zones, facility


def project_facilities(f: DerivedFacility) -> tuple[dict, dict]:
    zones = {
        z.spec.zone_id: {
            "zone_id": z.spec.zone_id,
            "total_racks": z.spec.total_racks,
            "occupied_racks": z.spec.occupied_racks,
            "available_racks": z.spec.available_racks,
            "liquid_ready_racks": z.spec.liquid_ready_racks,
            "retrofittable_racks": z.spec.retrofittable_racks,
            "floor_load_limit_kg_per_rack": z.spec.floor_load_limit_kg_per_rack,
            "avg_kw_per_occupied_rack": round(z.nameplate_kw / max(1, len(z.racks)), 1),
            "heaviest_installed_rack_kg": max((r.weight_kg for r in z.racks), default=0.0),
            "gpu_mix": z.gpu_mix,
            "aisle_type": ("hot_aisle_containment" if z.spec.cooling_type == "air_crah"
                           else "rear_door_hx"),
            "notes": z.spec.notes["facilities"],
        }
        for z in f.zones
    }
    facility = {
        "dcim_system": "Nlyte (simulated)",
        "total_racks": sum(z.spec.total_racks for z in f.zones),
        "total_occupied_racks": sum(z.spec.occupied_racks for z in f.zones),
        "total_available_racks": sum(z.spec.available_racks for z in f.zones),
        "open_work_orders": 14,
        "loading_dock_slots_free": 2,
        "staging_area_racks": 6,
        "last_audit": "2026-08-15",
        "sim_hour_et": f.sim_hour,
        "provenance": provenance(f),
    }
    return zones, facility


def project_cost(f: DerivedFacility) -> tuple[dict, dict]:
    zones = {
        z.spec.zone_id: {
            "zone_id": z.spec.zone_id,
            "cost_per_kw_month_usd": z.spec.cost_per_kw_month_usd,
            "monthly_energy_usd": z.monthly_energy_usd,
            "monthly_demand_charge_usd": z.monthly_demand_usd,
            "monthly_capex_amortization_usd": z.monthly_capex_amort_usd,
            "liquid_retrofit_cost_usd_per_rack": z.spec.liquid_retrofit_cost_usd_per_rack,
            "install_labor_rate_usd_per_hour": z.spec.install_labor_rate_usd_per_hour,
            "current_draw_kw": z.total_draw_kw,
            "notes": z.spec.notes["cost"],
        }
        for z in f.zones
    }
    facility = {
        "monthly_opex_budget_usd": FACILITY["monthly_opex_budget_usd"],
        "month_to_date_spend_usd": f.month_to_date_spend_usd,
        "budget_remaining_usd": round(
            FACILITY["monthly_opex_budget_usd"] - f.month_to_date_spend_usd, 2),
        "budget_utilization_pct": round(
            100.0 * f.month_to_date_spend_usd / FACILITY["monthly_opex_budget_usd"], 1),
        "monthly_energy_usd": f.monthly_energy_usd,
        "monthly_demand_charge_usd": f.monthly_demand_usd,
        "monthly_capex_amortization_usd": f.monthly_capex_amort_usd,
        "cost_per_gpu_hour_usd": f.cost_per_gpu_hour_usd,
        "installed_gpus": f.installed_gpus,
        "contracted_demand_mw": FACILITY["contracted_demand_mw"],
        # Above the 25 MW threshold, so GS-5 minimum-take obligations bind:
        # contracted headroom becomes a durable cost floor, not a free option.
        "gs5_rate_class_applies": FACILITY["contracted_demand_mw"] > 25.0,
        "blended_energy_rate_usd_per_kwh": 0.094,
        "overtime_multiplier": 1.5,
        "sim_hour_et": f.sim_hour,
        "provenance": provenance(f),
    }
    return zones, facility


PROJECTIONS: dict[str, Any] = {
    "power": project_power,
    "cooling": project_cooling,
    "facilities": project_facilities,
    "cost": project_cost,
}
