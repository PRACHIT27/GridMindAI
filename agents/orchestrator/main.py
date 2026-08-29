"""HTTP surface for the orchestrator on Cloud Run."""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ..common import obs
from ..common.config import MAX_NEGOTIATION_ROUNDS, MODEL_ORCHESTRATOR, PROJECT_ID
from ..common.data_access import shared_client
from .orchestrator import Orchestrator
from .report import render

app = FastAPI(title="GridMind Orchestrator", version="1.0.0")
_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    # Built on first request, not at import. Cloud Run counts container startup
    # against the request timeout, and constructing four remote clients during
    # module import slows every cold start on a scale-to-zero service.
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


class NegotiateRequest(BaseModel):
    workload_id: str | None = None
    workload: dict[str, Any] | None = None
    scenario: str = "normal"
    format: str = "json"          # json | text


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "service": "orchestrator", "project": PROJECT_ID,
            "model": MODEL_ORCHESTRATOR, "round_limit": MAX_NEGOTIATION_ROUNDS,
            "gateway": os.environ.get("GRIDMIND_GATEWAY_URL", "(in-process)")}


@app.post("/negotiate")
def negotiate(req: NegotiateRequest) -> dict:
    workload = req.workload
    if workload is None:
        if not req.workload_id:
            raise HTTPException(status_code=400, detail="provide workload or workload_id")
        # shared-db is the only database this service can open -- by IAM, not
        # by convention. Reading the queue here is legitimate; reading power-db
        # would be denied outright.
        doc = (shared_client().collection("workload_queue")
               .document(req.workload_id).get())
        if not doc.exists:
            raise HTTPException(status_code=404, detail=f"workload {req.workload_id} not found")
        workload = doc.to_dict() or {}

    # Demo scripting, never shown to an agent.
    workload.pop("scenario_tag", None)
    workload.pop("provenance", None)

    cid = obs.new_correlation_id()
    result = get_orchestrator().negotiate(workload, scenario=req.scenario, correlation_id=cid)

    if req.format == "text":
        return {"correlation_id": cid, "report": render(result)}

    return {
        "correlation_id": cid,
        "decision": result.decision.model_dump() if result.decision else None,
        "rounds": [
            {
                "round": r.number,
                "conflict_type": r.report.conflict_type,
                "consistent": r.report.consistent,
                "conflicts": r.report.conflicts,
                "endorsed_zones": r.report.endorsed_zones,
                "verdicts": [v.model_dump() for v in r.verdicts],
            }
            for r in result.rounds
        ],
        "precedent": result.precedent,
        "report": render(result),
    }
