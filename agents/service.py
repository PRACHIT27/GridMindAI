"""HTTP surface for a specialist agent running on Cloud Run.

One container image serves every role. GRIDMIND_ROLE selects which app to
mount, which means a single build and a single push produces all six services
-- faster and cheaper than six near-identical images on a $300 credit.

Cloud Run supplies the identity: the service runs AS its bound service account
and Application Default Credentials picks that up from the metadata server. No
keys are packaged, mounted, or rotated. The Firestore access this agent gets is
whatever its IAM condition allows and nothing more.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .common import obs
from .common.config import DOMAIN_DATABASES, MODEL_SPECIALIST

BUILDERS = {
    "power": "agents.power.agent",
    "cooling": "agents.cooling.agent",
    "facilities": "agents.facilities.agent",
    "cost": "agents.cost.agent",
}


class DecideRequest(BaseModel):
    workload: dict[str, Any]
    correlation_id: str = Field(..., description="Threaded through every agent in one decision.")
    scenario: str = "normal"
    round_number: int = 1
    peer_positions: list[dict[str, Any]] | None = None


def create_app(domain: str) -> FastAPI:
    if domain not in BUILDERS:
        raise ValueError(f"unknown agent domain {domain!r}")

    import importlib
    build_agent = importlib.import_module(BUILDERS[domain]).build_agent

    app = FastAPI(title=f"GridMind {domain} agent", version="1.0.0")
    agent = build_agent()

    @app.get("/healthz")
    def healthz() -> dict:
        # Deliberately does NOT touch Firestore or Vertex. Cloud Run probes this
        # on every cold start; making it do real work would add latency and cost
        # to a scale-to-zero service for no diagnostic value.
        return {"status": "ok", "agent": domain,
                "database": DOMAIN_DATABASES[domain], "model": MODEL_SPECIALIST}

    @app.post("/decide")
    def decide(req: DecideRequest) -> dict:
        try:
            verdict = agent.decide(
                req.workload,
                correlation_id=req.correlation_id,
                scenario=req.scenario,
                peer_positions=req.peer_positions,
                round_number=req.round_number,
            )
        except Exception as exc:      # harness already fails safe; this is belt-and-braces
            obs.log("agent_endpoint_error", level="error", agent=domain,
                    correlation_id=req.correlation_id, error=str(exc)[:400])
            raise HTTPException(status_code=500, detail=f"{type(exc).__name__}") from exc
        return verdict.model_dump()

    return app


def build() -> FastAPI:
    domain = os.environ.get("GRIDMIND_DOMAIN", "")
    return create_app(domain)
