"""Container entrypoint. One image, six services, selected by GRIDMIND_ROLE.

    GRIDMIND_ROLE=power|cooling|facilities|cost   -> that specialist agent
    GRIDMIND_ROLE=orchestrator                    -> the negotiation service
    GRIDMIND_ROLE=gateway                         -> the routing/audit gateway

A single image means one build and one push for the whole system, which on a
$300 credit is the difference between a few minutes of Cloud Build and six
times that. It also guarantees all six services run identical harness code.
"""
from __future__ import annotations

import os

ROLE = os.environ.get("GRIDMIND_ROLE", "").strip().lower()

if ROLE in ("power", "cooling", "facilities", "cost"):
    os.environ.setdefault("GRIDMIND_DOMAIN", ROLE)
    from agents.service import create_app
    app = create_app(ROLE)

elif ROLE == "orchestrator":
    from agents.orchestrator.main import app

elif ROLE == "gateway":
    from agents.gateway.main import app

elif ROLE == "web":
    # The only publicly reachable role. Serves the dashboard, reads shared-db
    # read-only, and fronts the orchestrator behind a rate limit.
    from agents.web.main import app

else:
    raise RuntimeError(
        f"GRIDMIND_ROLE must be one of power, cooling, facilities, cost, "
        f"orchestrator, gateway, web -- got {ROLE!r}")


if __name__ == "__main__":
    import uvicorn
    # Cloud Run injects PORT and expects the container to listen on it.
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
