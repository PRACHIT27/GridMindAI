"""Verify no database leaks another domain's facts.

WHY THIS EXISTS
---------------
The IAM conditions guarantee an agent cannot READ another database. They say
nothing about whether we accidentally COPIED another domain's facts into a
database the agent can read.

That is not hypothetical -- it already happened once. A single shared `notes`
string meant the sentence "5 liquid-ready racks against 6 needed" was written
into power-db, cooling-db AND cost-db. Every agent could then solve the problem
alone, and the entire multi-agent premise silently collapsed while all 14 IAM
isolation checks still passed.

Airtight permissions plus a leaky payload is not isolation. This test closes
that gap: it scans every field name and every string value written to each
database and fails if a domain's data mentions something only another domain
should know.

Run it before every seed:  python -m seed.leak_check
"""
from __future__ import annotations

import json
import sys

from .facility_model import derive_facility
from .projections import PROJECTIONS

# Terms that must NEVER appear in a given database, as a field name or inside
# any string value. Each entry names the domain that rightfully owns it.
FORBIDDEN: dict[str, dict[str, str]] = {
    "power": {
        "liquid_ready": "facilities", "retrofit": "facilities",
        "floor_load": "facilities", "available_rack": "facilities",
        "cdu": "cooling", "thermal": "cooling", "pue": "cooling",
        "inlet_temp": "cooling", "usd": "cost", "budget": "cost",
    },
    "cooling": {
        "liquid_ready": "facilities", "retrofit": "facilities",
        "floor_load": "facilities", "available_rack": "facilities",
        "occupied_rack": "facilities",
        "breaker": "power", "circuit": "power", "switchgear": "power",
        "usd": "cost", "budget": "cost",
    },
    "facilities": {
        "breaker": "power", "circuit": "power", "switchgear": "power",
        "allocated_kw": "power", "headroom_kw": "power",
        "cdu": "cooling", "pue": "cooling", "thermal_capacity": "cooling",
        "inlet_temp": "cooling",
        "usd": "cost", "budget": "cost",
    },
    "cost": {
        # cost-db legitimately knows the PRICE of a retrofit; it must not know
        # how many racks are retrofittable or liquid-ready.
        "liquid_ready": "facilities", "retrofittable": "facilities",
        "floor_load": "facilities", "available_rack": "facilities",
        "occupied_rack": "facilities",
        "breaker": "power", "circuit": "power", "switchgear": "power",
        "cdu": "cooling", "pue": "cooling", "thermal": "cooling",
    },
}

# Field names that contain a forbidden substring but are legitimately owned by
# this domain. Whitelisted explicitly so the check stays strict everywhere else.
ALLOWED: dict[str, set[str]] = {
    "cost": {"liquid_retrofit_cost_usd_per_rack", "monthly_energy_usd",
             "monthly_demand_charge_usd", "monthly_capex_amortization_usd",
             "cost_per_kw_month_usd", "install_labor_rate_usd_per_hour",
             "monthly_opex_budget_usd", "month_to_date_spend_usd",
             "budget_remaining_usd", "budget_utilization_pct",
             "cost_per_gpu_hour_usd", "blended_energy_rate_usd_per_kwh"},
    "power": set(),
    "cooling": set(),
    "facilities": set(),
}


def _scan(domain: str, payload: dict, where: str, out: list[str]) -> None:
    banned = FORBIDDEN[domain]
    allowed = ALLOWED[domain]

    for key, value in payload.items():
        for term, owner in banned.items():
            if term in key.lower() and key not in allowed:
                out.append(f"{where}: field '{key}' contains '{term}' (owned by {owner}-db)")
        if isinstance(value, str):
            for term, owner in banned.items():
                if term in value.lower():
                    out.append(
                        f"{where}: value of '{key}' mentions '{term}' "
                        f"(owned by {owner}-db) -> {value[:90]!r}")
        elif isinstance(value, dict):
            _scan(domain, value, f"{where}.{key}", out)


def run() -> int:
    f = derive_facility(sim_hour=14, seed=42)
    violations: list[str] = []

    for domain, project in PROJECTIONS.items():
        zones, facility = project(f)
        for zid, doc in zones.items():
            _scan(domain, doc, f"{domain}-db/zones/{zid}", violations)
        _scan(domain, facility, f"{domain}-db/facility/current", violations)

    if violations:
        print(f"LEAK CHECK FAILED -- {len(violations)} cross-domain leak(s):\n")
        for v in violations:
            print(f"  {v}")
        print("\nA leaked fact lets one agent solve the problem alone, which defeats "
              "the multi-agent design even though IAM isolation still passes.")
        return 1

    print("LEAK CHECK PASSED -- no database exposes another domain's facts.")
    print("\nThe fact that unlocks the negotiation appears in exactly one place:")
    for domain, project in PROJECTIONS.items():
        zones, _ = project(f)
        blob = json.dumps(zones).lower()
        has = "liquid_ready" in blob
        print(f"  {domain + '-db':<16} knows liquid-ready rack counts: "
              f"{'YES' if has else 'no'}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
