"""Write the generated facility into the five Firestore databases.

Run once before the demo:
    python -m seed.generate_seed_data                    # seed 42, 2pm, summer
    python -m seed.generate_seed_data --dry-run          # show, write nothing
    python -m seed.generate_seed_data --hour 3           # quiet 3am facility

This is the ONLY place randomness enters the system. After it runs, the
databases hold fixed values and the agents are fully deterministic: same
question, same answer, every time. To move the simulated clock forward, re-run
with a different --hour; every dependent value shifts together because they all
derive from the same master term.

The leak check runs FIRST and aborts the write if it fails. Seeding a database
with another domain's facts would silently defeat the multi-agent design while
leaving every IAM isolation check green, so it is not something to discover
later.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone

from google.cloud import firestore

from agents.common.auth import get_credentials
from agents.common.config import PROJECT_ID

from .facility_model import SEED, derive_facility
from .leak_check import run as run_leak_check
from .projections import PROJECTIONS, provenance

DOMAIN_DB = {"power": "power-db", "cooling": "cooling-db",
             "facilities": "facilities-db", "cost": "cost-db"}


# ---------------------------------------------------------------------------
# Workload requests
# ---------------------------------------------------------------------------

# The scripted demo request. Pinned, never randomized: this exact ask is what
# produces the four-way deadlock the whole demo is built on.
DEMO_WORKLOAD = {
    "workload_id": "wl-2026-0842",
    "tenant": "internal-research",
    "description": "Frontier model training cluster expansion",
    "gpu_model": "GB200",
    "rack_type": "GB200 NVL72",
    "gpu_count": 432,
    "racks_required": 6,
    "power_per_rack_kw": 132.0,
    "total_power_kw": 792.0,
    "rack_weight_kg": 1360.0,
    "cooling_requirement": "direct_to_chip_liquid",
    "duration_weeks": 8,
    "priority": "high",
    "requester": "ml-platform-team",
    "export_control_status": "verified_domestic",
    "scenario_tag": "four_way_zone_conflict",
    "status": "pending",
}


def build_request_mix(rng_seed: int) -> list[dict]:
    """A deliberately scripted MIX of requests, not a random pile.

    Three shapes, each exercising a different path through the system:
      clean_approve   -- modest air-cooled ask; should sail through round 1
      cooling_conflict-- high density into a facility short on liquid capacity
      deadline_pressure-- tight deadline colliding with an external signal

    Scripting the mix means the demo has a narrative instead of whatever
    randomness happened to produce. `scenario_tag` is for OUR scripting and is
    never shown to the model -- it is stripped before the request reaches an
    agent, so the agents cannot cheat off the label.
    """
    import random
    rng = random.Random(rng_seed)
    now = datetime.now(timezone.utc)
    out: list[dict] = []

    def mk(idx: int, gpu: str, racks: int, kw: float, weight: float,
           cooling: str, tag: str, deadline_hours: int) -> dict:
        return {
            "workload_id": f"wl-2026-{900 + idx:04d}",
            "tenant": rng.choice(["internal-research", "team-vision", "customer-alpha"]),
            "description": f"{gpu} capacity request",
            "gpu_model": gpu,
            "racks_required": racks,
            "power_per_rack_kw": kw,
            "total_power_kw": round(racks * kw, 1),
            "rack_weight_kg": weight,
            "cooling_requirement": cooling,
            "duration_weeks": rng.choice([2, 4, 8, 12]),
            "priority": rng.choices(["low", "medium", "high"], weights=[.3, .4, .3])[0],
            "requested_start": (now + timedelta(hours=6)).isoformat(),
            "deadline": (now + timedelta(hours=deadline_hours)).isoformat(),
            "requester": "ml-platform-team",
            "export_control_status": "verified_domestic",
            "scenario_tag": tag,
            "status": "pending",
        }

    i = 0
    for _ in range(3):      # comfortably feasible
        i += 1
        out.append(mk(i, "H100", rng.choice([2, 3, 4]), round(rng.uniform(28, 36), 1),
                      900.0, "air", "clean_approve", rng.randint(96, 168)))
    for _ in range(2):      # density forces liquid cooling
        i += 1
        out.append(mk(i, "B200", rng.choice([4, 6]), round(rng.uniform(60, 88), 1),
                      1150.0, "direct_to_chip_liquid", "cooling_conflict",
                      rng.randint(48, 120)))
    for _ in range(2):      # tight deadline vs external conditions
        i += 1
        out.append(mk(i, "GB200", rng.choice([4, 6]), round(rng.uniform(118, 132), 1),
                      1360.0, "direct_to_chip_liquid", "deadline_pressure",
                      rng.choice([8, 12])))
    return out


MEMORY_PRECEDENT = {
    "precedent_id": "prec-2026-0311",
    "conflict_type": "power_cooling_zone_mismatch",
    "summary": ("A 4-rack H200 request stalled when Power endorsed one zone and Cooling "
                "required a liquid-capable one. Resolved by a partial split: 3 racks into "
                "an existing liquid zone, 1 rack retrofitted, accepting 16 hours of delay."),
    "resolution": "partial_placement_with_retrofit",
    "delay_hours_accepted": 16,
    "cost_delta_pct": 6.2,
    "outcome": "deployed_successfully",
    "lesson": ("When Power and Cooling endorse different zones, check whether the "
               "cooling-capable zone can be topped up with a retrofit before rejecting "
               "outright or splitting across zones."),
    "recorded_at": "2026-03-11T00:00:00Z",
}


# ---------------------------------------------------------------------------

def _db(database: str) -> firestore.Client:
    return firestore.Client(project=PROJECT_ID, database=database,
                            credentials=get_credentials())


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed GridMind's five Firestore databases.")
    ap.add_argument("--seed", type=int, default=SEED, help="dice seed (default 42)")
    ap.add_argument("--hour", type=int, default=14, help="simulated hour, 0-23 ET (default 14)")
    ap.add_argument("--season", default="summer", choices=["summer", "winter"])
    ap.add_argument("--dry-run", action="store_true", help="print, write nothing")
    args = ap.parse_args()

    # Refuse to seed a leaky dataset.
    print("Running cross-domain leak check first...\n")
    if run_leak_check() != 0:
        print("\nABORTED -- refusing to seed leaked data.")
        return 1

    f = derive_facility(sim_hour=args.hour, season=args.season, seed=args.seed)
    prov = provenance(f)

    print(f"\nFacility {f.zones[0].spec.zone_id[:0] or 'iad-dc-01'} at simulated hour "
          f"{args.hour}:00 ET, {args.season}, seed {args.seed}")
    print(f"  {prov['rack_count']} racks -> {f.total_it_load_kw/1000:.2f} MW IT load, "
          f"{f.total_draw_kw/1000:.2f} MW total draw, PUE {f.facility_pue}")

    requests = build_request_mix(args.seed)

    if args.dry_run:
        print("\n--- DRY RUN: nothing will be written ---")
        for domain, project in PROJECTIONS.items():
            zones, facility = project(f)
            print(f"\n{DOMAIN_DB[domain]}")
            print(f"   zones/           {len(zones)} documents: {', '.join(sorted(zones))}")
            print(f"   facility/current 1 document, {len(facility)} fields")
        print(f"\nshared-db")
        print(f"   workload_queue/  {1 + len(requests)} documents "
              f"(1 scripted demo + {len(requests)} mixed)")
        print(f"   memory_bank/     1 document")
        print(f"\nSample -- power-db/zones/zone-c:")
        zones, _ = PROJECTIONS["power"](f)
        print(json.dumps(zones["zone-c"], indent=4))
        return 0

    # --- write the four domain databases ---
    for domain, project in PROJECTIONS.items():
        zones, facility = project(f)
        db = _db(DOMAIN_DB[domain])
        batch = db.batch()
        for zid, doc in zones.items():
            batch.set(db.collection("zones").document(zid), doc)
        batch.set(db.collection("facility").document("current"), facility)
        batch.commit()
        print(f"  wrote {DOMAIN_DB[domain]:<16} {len(zones)} zones + facility state")

    # --- write shared-db (workload queue + memory bank) ---
    shared = _db("shared-db")
    batch = shared.batch()
    batch.set(shared.collection("workload_queue").document(DEMO_WORKLOAD["workload_id"]),
              {**DEMO_WORKLOAD, "provenance": prov})
    for r in requests:
        batch.set(shared.collection("workload_queue").document(r["workload_id"]), r)
    batch.set(shared.collection("memory_bank").document(MEMORY_PRECEDENT["precedent_id"]),
              MEMORY_PRECEDENT)
    batch.commit()
    print(f"  wrote {'shared-db':<16} {1 + len(requests)} workloads + 1 memory precedent")

    print("\nSeed complete. Verify isolation still holds:")
    print("  bash infra/iam/03_verify_isolation.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
