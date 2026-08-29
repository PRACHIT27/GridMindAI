"""Run a full negotiation and print the decision report.

    python -m scripts.negotiate
    python -m scripts.negotiate --scenario heatwave
    python -m scripts.negotiate --workload wl-2026-0901
"""
from __future__ import annotations

import argparse
import sys

from google.cloud import firestore

from agents.common import obs
from agents.common.auth import get_credentials
from agents.common.config import PROJECT_ID
from agents.orchestrator.orchestrator import Orchestrator
from agents.orchestrator.report import render


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workload", default="wl-2026-0842")
    ap.add_argument("--scenario", default="normal",
                    choices=["normal", "heatwave", "grid_stress", "crew_shortage",
                             "freight_delay"])
    ap.add_argument("--quiet", action="store_true", help="suppress per-agent log lines")
    args = ap.parse_args()

    db = firestore.Client(project=PROJECT_ID, database="shared-db",
                          credentials=get_credentials())
    doc = db.collection("workload_queue").document(args.workload).get()
    if not doc.exists:
        print(f"workload {args.workload} not found in shared-db/workload_queue")
        return 1

    workload = doc.to_dict()
    # scenario_tag is demo scripting for US. Strip it so no agent can read the
    # label off the request instead of reasoning about it.
    workload.pop("scenario_tag", None)
    workload.pop("provenance", None)

    if args.quiet:
        obs.log = lambda *a, **k: None      # type: ignore[assignment]

    result = Orchestrator().negotiate(workload, scenario=args.scenario,
                                      correlation_id=obs.new_correlation_id())
    print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
