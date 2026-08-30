"""Publish the agent registry. Run by the deploy script after services roll out.

    python -m scripts.publish_registry

Uses the DEPLOYER's credentials, not an agent's. That is the point: a
specialist agent cannot write to shared-db, and giving it the ability to
would contradict the very isolation its registry entry advertises.
"""
from __future__ import annotations

import sys

from google.cloud import firestore

from agents.common import obs, registry
from agents.common.auth import get_credentials
from agents.common.config import PROJECT_ID, SHARED_DATABASE


def main() -> int:
    db = firestore.Client(project=PROJECT_ID, database=SHARED_DATABASE,
                          credentials=get_credentials())
    ids = registry.publish(db)

    print(f"\nPublished {len(ids)} agents to shared-db/agent_registry "
          f"(version {registry.AGENT_VERSION}):\n")
    for aid in ids:
        rec = db.collection("agent_registry").document(aid).get().to_dict() or {}
        scope = rec.get("data_scope", {})
        print(f"  {aid:<26} reads {str(scope.get('readable_database')):<16}"
              f" denied {len(scope.get('denied_databases') or [])} others")
    print("\nDiscover them at  GET /api/registry  on the dashboard.")
    return 0


if __name__ == "__main__":
    obs.log = lambda *a, **k: None      # type: ignore[assignment]
    sys.exit(main())
