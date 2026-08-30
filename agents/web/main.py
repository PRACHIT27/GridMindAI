"""Public web tier: serves the dashboard and fronts the orchestrator.

THE ONLY INTERNET-FACING SERVICE. Everything else -- the four specialists, the
gateway, and now the orchestrator -- is --ingress=internal and unreachable from
outside the VPC.

TWO PATHS, TWO DIFFERENT PROTECTIONS
The dashboard does two very different things, and treating them identically
would be a mistake:

  READ  past decisions from shared-db   -- effectively free, low risk
  RUN   a new negotiation               -- 5 agents, multi-round, ~2-3 cents
                                           and 60-90 seconds

So reads are open, and runs are rate limited. An unmetered public trigger is
not a security hole in the usual sense -- it is a BILLING hole. At roughly
2.5 cents a negotiation, a scraper hitting it in a loop drains a $300 credit
overnight. The limiter below is the thing standing between a portfolio demo and
an empty account.

A demo key bypasses the limits so a live walkthrough is never blocked by a
visitor who ran a negotiation thirty seconds earlier.
"""
from __future__ import annotations

import os
import time
from collections import deque
from pathlib import Path
from typing import Any

import google.auth.transport.requests
import google.oauth2.id_token
import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from google.cloud import firestore
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..common import obs
from ..common.auth import get_credentials
from ..common.config import PROJECT_ID, SHARED_DATABASE

ORCHESTRATOR_URL = os.environ.get("GRIDMIND_ORCHESTRATOR_URL", "").rstrip("/")
DEMO_KEY = os.environ.get("GRIDMIND_DEMO_KEY", "")

# Anonymous visitors may run a negotiation, but not many and not fast.
COOLDOWN_SECONDS = 90          # per IP
GLOBAL_DAILY_LIMIT = 60        # ~$1.50/day worst case
_last_run_by_ip: dict[str, float] = {}
_recent_runs: deque[float] = deque()

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="GridMind Dashboard", version="1.0.0")


def _db() -> firestore.Client:
    return firestore.Client(project=PROJECT_ID, database=SHARED_DATABASE,
                            credentials=get_credentials())


def _client_ip(request: Request) -> str:
    # Cloud Run puts the real client first in X-Forwarded-For.
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _check_rate_limit(ip: str, key: str | None) -> None:
    """Raise 429 unless this caller may start a negotiation."""
    if DEMO_KEY and key == DEMO_KEY:
        return                                   # presenter bypass

    now = time.time()
    while _recent_runs and now - _recent_runs[0] > 86400:
        _recent_runs.popleft()
    if len(_recent_runs) >= GLOBAL_DAILY_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=("GridMind has hit its daily demo limit. Every run costs real "
                    "Gemini calls, so the public demo is capped. Browse the saved "
                    "decisions below -- they are real negotiations, not fixtures."))

    last = _last_run_by_ip.get(ip, 0.0)
    if now - last < COOLDOWN_SECONDS:
        wait = int(COOLDOWN_SECONDS - (now - last))
        raise HTTPException(status_code=429,
                            detail=f"One negotiation per {COOLDOWN_SECONDS}s. "
                                   f"Try again in {wait}s.")

    _last_run_by_ip[ip] = now
    _recent_runs.append(now)


def _id_token() -> str:
    """Audience-scoped token for the orchestrator, which is now VPC-internal."""
    return google.oauth2.id_token.fetch_id_token(
        google.auth.transport.requests.Request(), ORCHESTRATOR_URL)


# ---------------------------------------------------------------- routes

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "web",
            "orchestrator_configured": bool(ORCHESTRATOR_URL),
            "demo_key_set": bool(DEMO_KEY),
            "runs_today": len(_recent_runs), "daily_limit": GLOBAL_DAILY_LIMIT}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/workloads")
def workloads() -> list[dict]:
    """The pending request queue."""
    out = []
    for d in _db().collection("workload_queue").stream():
        w = d.to_dict() or {}
        w.pop("provenance", None)
        out.append(w)
    # The scripted demo request first, then the rest.
    out.sort(key=lambda w: (w.get("workload_id") != "wl-2026-0842",
                            w.get("workload_id", "")))
    return out


@app.get("/api/decisions")
def decisions(limit: int = 25) -> list[dict]:
    """Past negotiations -- summary only, so the list stays small."""
    out = []
    for d in _db().collection("negotiation_log").limit(limit).stream():
        n = d.to_dict() or {}
        dec = n.get("decision") or {}
        out.append({
            "correlation_id": n.get("correlation_id"),
            "workload_id": n.get("workload_id"),
            "scenario": n.get("scenario"),
            "outcome": n.get("outcome"),
            "chosen_zone": n.get("chosen_zone"),
            "rounds_used": n.get("rounds_used"),
            "delay_hours": dec.get("delay_hours"),
            "economics": dec.get("economics"),
        })
    out.sort(key=lambda x: x.get("correlation_id") or "", reverse=True)
    return out


@app.get("/api/decisions/{correlation_id}")
def decision(correlation_id: str) -> dict:
    doc = _db().collection("negotiation_log").document(correlation_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="negotiation not found")
    return doc.to_dict() or {}


@app.get("/api/registry")
def registry() -> list[dict]:
    """Agent discovery: what agents exist, what they judge, what they can reach.

    The point of publishing `data_scope` is that it makes the isolation claim
    checkable rather than assertable. Each entry names the one database that
    agent can read and the four it cannot, and the same values drive the IAM
    conditions -- so an entry that lied would be caught by
    infra/iam/03_verify_isolation.sh.
    """
    out = [d.to_dict() or {} for d in _db().collection("agent_registry").stream()]
    order = {"gridmind-orchestrator": 0}
    out.sort(key=lambda r: (order.get(r.get("agent_id", ""), 1), r.get("agent_id", "")))
    return out


@app.get("/api/memory")
def memory() -> list[dict]:
    """Memory Bank precedents the orchestrator can draw on."""
    return [d.to_dict() or {} for d in _db().collection("memory_bank").limit(20).stream()]


@app.get("/api/decisions/{correlation_id}/report.pdf")
def decision_pdf(correlation_id: str) -> Response:
    """The decision report as a downloadable PDF.

    Rendered on demand from the stored negotiation rather than written at
    decision time: it costs nothing until someone asks, keeps Cloud Storage
    write access off the orchestrator, and means a layout change applies to
    every past decision instead of only future ones.
    """
    doc = _db().collection("negotiation_log").document(correlation_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="negotiation not found")

    from .report_pdf import render_pdf
    n = doc.to_dict() or {}
    pdf = render_pdf(n)
    name = f"gridmind-{n.get('workload_id', 'decision')}-{correlation_id}.pdf"
    obs.log("report_pdf_rendered", agent="web", correlation_id=correlation_id,
            bytes=len(pdf))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


GPU_CHOICES = {
    "GB200": "GB200 NVL72", "B200": "B200 rack",
    "H200": "H200 rack", "H100": "H100 rack",
}
COOLING_CHOICES = {"air", "direct_to_chip_liquid"}
PRIORITY_CHOICES = {"low", "medium", "high"}


class CustomWorkload(BaseModel):
    """A workload composed in the browser, from an untrusted public caller.

    NO FREE TEXT REACHES THE MODEL FROM HERE. Every field is either a bounded
    number or a value from a fixed allowlist, and the human-readable description
    is GENERATED server-side from those numbers rather than accepted from the
    request.

    That is not incidental hardening. The workload dict is serialised straight
    into the constraint context and therefore into the prompt, so a free-text
    field on a public form is a direct prompt-injection channel -- verified:
    text placed in `description` appeared verbatim in the model prompt.

    The output guardrails do not cover this. They check whether a verdict is
    physically possible, so a verdict an attacker steered toward a genuinely
    feasible zone would sail through. The architecture still resists it -- no
    single agent can approve a placement, and the other three read different
    databases -- but resisting an attack is not the same as refusing to carry
    it, so the channel is closed at the door.

    The numeric bounds are the milder concern: they stop a 900-rack request
    inflating the prompt and the token bill to no purpose.
    """
    # extra="forbid": an unknown field is a 422, not a silent drop. If someone
    # posts `description`, they should be told it is refused rather than left
    # believing their text reached the agents.
    model_config = ConfigDict(extra="forbid")

    racks_required: int = Field(6, ge=1, le=24)
    power_per_rack_kw: float = Field(132.0, ge=5, le=200)
    rack_weight_kg: float = Field(1360.0, ge=200, le=2000)
    gpu_model: str = Field("GB200")
    cooling_requirement: str = Field("direct_to_chip_liquid")
    duration_weeks: int = Field(8, ge=1, le=52)
    priority: str = Field("high")

    @field_validator("gpu_model")
    @classmethod
    def _gpu(cls, v: str) -> str:
        if v not in GPU_CHOICES:
            raise ValueError(f"gpu_model must be one of {sorted(GPU_CHOICES)}")
        return v

    @field_validator("cooling_requirement")
    @classmethod
    def _cool(cls, v: str) -> str:
        if v not in COOLING_CHOICES:
            raise ValueError(f"cooling_requirement must be one of {sorted(COOLING_CHOICES)}")
        return v

    @field_validator("priority")
    @classmethod
    def _prio(cls, v: str) -> str:
        if v not in PRIORITY_CHOICES:
            raise ValueError(f"priority must be one of {sorted(PRIORITY_CHOICES)}")
        return v

    def to_workload(self) -> dict[str, Any]:
        total = round(self.racks_required * self.power_per_rack_kw, 1)
        return {
            "workload_id": "wl-custom",
            "tenant": "dashboard-user",
            # Generated, never echoed from the request.
            "description": (f"{self.racks_required}x {GPU_CHOICES[self.gpu_model]} "
                            f"at {self.power_per_rack_kw} kW/rack ({total} kW total)"),
            "gpu_model": self.gpu_model,
            "rack_type": GPU_CHOICES[self.gpu_model],
            "racks_required": self.racks_required,
            "power_per_rack_kw": self.power_per_rack_kw,
            "total_power_kw": round(self.racks_required * self.power_per_rack_kw, 1),
            "rack_weight_kg": self.rack_weight_kg,
            "cooling_requirement": self.cooling_requirement,
            "duration_weeks": self.duration_weeks,
            "priority": self.priority,
            "requester": "dashboard",
            "export_control_status": "verified_domestic",
            "status": "pending",
        }


class RunRequest(BaseModel):
    workload_id: str = "wl-2026-0842"
    scenario: str = "normal"
    custom: CustomWorkload | None = None


@app.post("/api/negotiate")
def negotiate(req: RunRequest, request: Request,
              x_demo_key: str | None = Header(default=None)) -> Any:
    """Start a real negotiation. Rate limited -- this one costs money."""
    if not ORCHESTRATOR_URL:
        raise HTTPException(status_code=503, detail="orchestrator URL not configured")

    ip = _client_ip(request)
    _check_rate_limit(ip, x_demo_key)

    obs.log("web_negotiate_requested", agent="web", workload_id=req.workload_id,
            scenario=req.scenario, client_ip=ip,
            keyed=bool(DEMO_KEY and x_demo_key == DEMO_KEY))

    # A custom workload is passed through as a body, never written to Firestore.
    # The web tier's identity is read-only, so it could not persist one even if
    # this code tried -- a visitor cannot pollute the real workload queue.
    body: dict[str, Any] = {"scenario": req.scenario, "format": "json"}
    if req.custom is not None:
        body["workload"] = req.custom.to_workload()
    else:
        body["workload_id"] = req.workload_id

    try:
        with httpx.Client(timeout=600.0) as client:
            resp = client.post(
                f"{ORCHESTRATOR_URL}/negotiate", json=body,
                headers={"Authorization": f"Bearer {_id_token()}"})
    except httpx.HTTPError as exc:
        obs.log("web_orchestrator_unreachable", level="error", agent="web",
                error=str(exc)[:300])
        raise HTTPException(status_code=502, detail="orchestrator unreachable") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"orchestrator returned {resp.status_code}")
    return JSONResponse(resp.json())
