"""Agent Gateway: the only path between the orchestrator and the specialists.

WHAT IT ADDS OVER CALLING AGENTS DIRECTLY
Cloud Run's --no-allow-unauthenticated already enforces WHO may invoke a
service. The gateway adds the things IAM cannot express:

  * a routing table -- which caller may reach which agent, checked per request
  * an allow/deny record for every call, shipped to Cloud Logging, which is
    what makes the whole system auditable rather than merely secure
  * one seam to add Model Armor style screening of inter-agent traffic later

Defence in depth, deliberately. If the gateway's own logic were bypassed, IAM
still denies the call; if IAM were misconfigured, the routing table still
refuses it. Neither layer is load-bearing alone.
"""
from __future__ import annotations

import json
import os
from typing import Any

import google.auth.transport.requests
import google.oauth2.id_token
import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from ..common import obs
from ..common.config import PROJECT_ID
from ..common.model_armor import MAX_CHARS, screen_prompt, screen_response

# Which callers may reach which agents. Deliberately explicit: a new agent has
# to be added here on purpose, so nothing becomes reachable by accident.
ROUTING_TABLE: dict[str, set[str]] = {
    "orchestrator-agent-sa": {"power", "cooling", "facilities", "cost"},
}

AGENT_URLS = {
    d: os.environ.get(f"GRIDMIND_{d.upper()}_URL", "") for d in
    ("power", "cooling", "facilities", "cost")
}

app = FastAPI(title="GridMind Agent Gateway", version="1.0.0")


class RouteRequest(BaseModel):
    agent: str
    workload: dict[str, Any]
    correlation_id: str
    scenario: str = "normal"
    round_number: int = 1
    peer_positions: list[dict[str, Any]] | None = None


def _caller_identity(auth_header: str | None) -> str:
    """Identify the caller from its Google-signed ID token.

    Cloud Run has already verified this token before the request arrives -- an
    unauthenticated caller never reaches this code. We decode it to learn WHICH
    service account is calling, so the routing table can be applied and the
    decision logged against a real identity.
    """
    if not auth_header or not auth_header.lower().startswith("bearer "):
        return "anonymous"
    token = auth_header.split(None, 1)[1]
    try:
        claims = google.oauth2.id_token.verify_oauth2_token(
            token, google.auth.transport.requests.Request())
        email = claims.get("email", "")
        return email.split("@")[0] if email else "unknown"
    except Exception:
        return "unverified"


def _id_token_for(url: str) -> str:
    """Mint an ID token for the downstream agent, audience-scoped to its URL.

    Audience scoping matters: a token minted for the power agent is not valid
    at the cost agent, so a leaked token cannot be replayed across services.
    """
    return google.oauth2.id_token.fetch_id_token(
        google.auth.transport.requests.Request(), url)


# NOTE: the path is /health, not /healthz. Cloud Run's frontend intercepts
# /healthz and returns its own 404 before the request ever reaches the
# container -- the route exists in the app's OpenAPI schema and still 404s,
# which is a confusing hour to lose.
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "gateway", "project": PROJECT_ID,
            "routes": {k: sorted(v) for k, v in ROUTING_TABLE.items()},
            "agents_configured": {k: bool(v) for k, v in AGENT_URLS.items()}}


@app.post("/route")
def route(req: RouteRequest, authorization: str | None = Header(default=None)) -> dict:
    caller = _caller_identity(authorization)
    allowed = ROUTING_TABLE.get(caller, set())

    if req.agent not in allowed:
        # The deliberate-denial demo lands here. Logged at WARNING with both
        # identities so the denial is visible in Cloud Logging, not just a 403
        # the caller sees and nobody else ever knows about.
        obs.log("gateway_denied", level="warn", agent="gateway",
                correlation_id=req.correlation_id, caller=caller,
                requested_agent=req.agent, permitted=sorted(allowed),
                message=f"DENIED {caller} -> {req.agent}: not in routing table")
        raise HTTPException(
            status_code=403,
            detail=f"gateway: {caller} is not permitted to invoke the {req.agent} agent")

    url = AGENT_URLS.get(req.agent, "")
    if not url:
        raise HTTPException(status_code=503, detail=f"no URL configured for {req.agent}")

    # MODEL ARMOR -- content screening, after the identity and routing checks
    # have decided the caller is allowed at all. Order matters: there is no
    # point paying for a screening call on a request we are about to refuse.
    #
    # This covers the gap the per-agent guardrails cannot. Those verify that a
    # verdict is physically possible; they say nothing about whether the input
    # that produced it was trying to hijack the agent.
    inbound = json.dumps(req.workload, sort_keys=True, default=str)
    armor = screen_prompt(inbound, what=f"workload->{req.agent}",
                          correlation_id=req.correlation_id)
    if armor.blocked:
        obs.log("gateway_armor_block", level="warn", agent="gateway",
                correlation_id=req.correlation_id, caller=caller,
                requested_agent=req.agent, triggered=armor.triggered,
                match_state=armor.match_state,
                message=f"BLOCKED inbound payload to {req.agent}: {armor.summary}")
        raise HTTPException(
            status_code=422,
            detail=f"Model Armor refused this payload ({armor.summary}). "
                   f"The request never reached the {req.agent} agent.")

    obs.log("gateway_allowed", agent="gateway", correlation_id=req.correlation_id,
            caller=caller, requested_agent=req.agent, round=req.round_number,
            armor=armor.match_state)

    payload = req.model_dump(exclude={"agent"})
    try:
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(
                f"{url}/decide", json=payload,
                headers={"Authorization": f"Bearer {_id_token_for(url)}"})
    except httpx.HTTPError as exc:
        obs.log("gateway_upstream_error", level="error", agent="gateway",
                correlation_id=req.correlation_id, requested_agent=req.agent,
                error=str(exc)[:300])
        raise HTTPException(status_code=502, detail=f"upstream {req.agent} unreachable") from exc

    if resp.status_code != 200:
        obs.log("gateway_upstream_status", level="error", agent="gateway",
                correlation_id=req.correlation_id, requested_agent=req.agent,
                status=resp.status_code, body=resp.text[:300])
        raise HTTPException(status_code=502,
                            detail=f"{req.agent} returned {resp.status_code}")

    verdict = resp.json()

    # Screen the way OUT as well. An agent given clean input can still emit
    # something it should not -- echoing a value out of its own database, or
    # hallucinating one. The reasoning text is what gets surfaced to humans and
    # written to the audit log, so it is the field worth checking.
    out_armor = screen_response(str(verdict.get("reasoning", ""))[:MAX_CHARS],
                                what=f"verdict<-{req.agent}",
                                correlation_id=req.correlation_id)
    if out_armor.blocked:
        obs.log("gateway_armor_block_outbound", level="warn", agent="gateway",
                correlation_id=req.correlation_id, requested_agent=req.agent,
                triggered=out_armor.triggered,
                message=f"BLOCKED {req.agent} verdict: {out_armor.summary}")
        raise HTTPException(
            status_code=422,
            detail=f"Model Armor refused the {req.agent} agent's response "
                   f"({out_armor.summary}).")

    return verdict
