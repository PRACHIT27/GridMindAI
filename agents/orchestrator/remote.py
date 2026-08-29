"""Call specialists over HTTP through the gateway.

Interface-compatible with AgentHarness.decide(), so the orchestrator's
negotiation loop is identical whether the specialists are in-process (local
development) or six separate Cloud Run services (deployed). The loop does not
know or care.

Failure is handled the same way too: if a specialist is unreachable or returns
an error, this fails SAFE to an EscalationVerdict rather than dropping the
agent from the round. Silently negotiating with three agents instead of four
would produce a confident decision with a whole constraint axis missing.
"""
from __future__ import annotations

from typing import Any

import google.auth.transport.requests
import google.oauth2.id_token
import httpx

from ..common import obs
from ..common.verdict import AgentVerdict, EscalationVerdict


class RemoteSpecialist:
    def __init__(self, domain: str, gateway_url: str, timeout: float = 180.0) -> None:
        self.domain = domain
        self.gateway_url = gateway_url.rstrip("/")
        self.timeout = timeout

    def _id_token(self) -> str:
        # Audience-scoped to the gateway: this token is not valid anywhere else.
        return google.oauth2.id_token.fetch_id_token(
            google.auth.transport.requests.Request(), self.gateway_url)

    def decide(self, workload: dict[str, Any], *, correlation_id: str,
               scenario: str = "normal",
               peer_positions: list[dict[str, Any]] | None = None,
               round_number: int = 1) -> AgentVerdict:
        payload = {
            "agent": self.domain,
            "workload": workload,
            "correlation_id": correlation_id,
            "scenario": scenario,
            "round_number": round_number,
            "peer_positions": peer_positions,
        }
        try:
            with obs.timed("remote_agent_call", agent="orchestrator",
                           correlation_id=correlation_id, target=self.domain,
                           round=round_number):
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.gateway_url}/route", json=payload,
                        headers={"Authorization": f"Bearer {self._id_token()}"})
            resp.raise_for_status()
            return AgentVerdict.model_validate(resp.json())

        except Exception as exc:
            obs.log("remote_agent_failed", level="error", agent="orchestrator",
                    correlation_id=correlation_id, target=self.domain,
                    error_type=type(exc).__name__, error=str(exc)[:400])
            return EscalationVerdict(
                agent=self.domain,      # type: ignore[arg-type]
                status="infeasible",
                reasoning=(
                    f"The {self.domain} agent could not be reached through the gateway "
                    f"({type(exc).__name__}). Failing safe to infeasible: a negotiation "
                    f"missing an entire constraint axis must not produce a confident "
                    f"approval."),
                target_zone=None,
                confidence=0.0,
                failure_reason=f"{type(exc).__name__}: {str(exc)[:300]}",
            )
