"""Run one agent locally against the seeded databases.

    python -m scripts.try_agent power
    python -m scripts.try_agent power --scenario grid_stress
    python -m scripts.try_agent power --impersonate    # run AS power-agent-sa

--impersonate is the honest test: it forces the call to use the agent's own
service account, so the Firestore read is subject to the same IAM conditions it
will face in Cloud Run. Without it you are reading as yourself, which proves
the code works but proves nothing about the isolation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from agents.common import obs
from agents.common.config import PROJECT_ID


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("domain", choices=["power", "cooling", "facilities", "cost"])
    ap.add_argument("--scenario", default="normal",
                    choices=["normal", "heatwave", "grid_stress", "crew_shortage",
                             "freight_delay"])
    ap.add_argument("--workload", default="wl-2026-0842")
    ap.add_argument("--impersonate", action="store_true",
                    help="run as the agent's own service account")
    args = ap.parse_args()

    from google.cloud import firestore

    from agents.common.auth import get_credentials

    # Fetch the workload FIRST, as the developer -- before any impersonation is
    # switched on. shared-db is off-limits to every specialist agent, so trying
    # to read it as power-agent-sa correctly fails with a 403. In production the
    # request body arrives from the gateway; the agent never reads the queue.
    shared = firestore.Client(project=PROJECT_ID, database="shared-db",
                              credentials=get_credentials())
    doc = shared.collection("workload_queue").document(args.workload).get()
    if not doc.exists:
        print(f"workload {args.workload} not found in shared-db")
        return 1
    workload = doc.to_dict()

    # scenario_tag is OUR demo scripting. Strip it so the agent cannot read the
    # label off the request and shortcut the reasoning we are trying to test.
    workload.pop("scenario_tag", None)
    workload.pop("provenance", None)

    # Only now switch identity, so the agent's OWN Firestore read is subject to
    # the same IAM conditions it will face running in Cloud Run.
    if args.impersonate:
        os.environ["GRIDMIND_IMPERSONATE_SA"] = (
            f"{args.domain}-agent-sa@{PROJECT_ID}.iam.gserviceaccount.com")

    if args.domain == "power":
        from agents.power.agent import build_agent
    else:
        print(f"{args.domain} agent not built yet")
        return 1

    correlation_id = obs.new_correlation_id()
    print(f"\n=== {args.domain.upper()} AGENT | workload {args.workload} "
          f"| scenario {args.scenario} | {correlation_id} ===\n")
    print(f"REQUEST: {workload.get('racks_required')} x {workload.get('rack_type')} "
          f"@ {workload.get('power_per_rack_kw')} kW = {workload.get('total_power_kw')} kW\n")

    verdict = build_agent().decide(
        workload, correlation_id=correlation_id, scenario=args.scenario)

    print("\n--- VERDICT ---")
    print(json.dumps(verdict.model_dump(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
