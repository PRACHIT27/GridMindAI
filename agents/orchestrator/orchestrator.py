"""The negotiation loop.

Round 1 asks all four specialists independently -- independence matters, or the
agents anchor on whoever answered first. Their verdicts are then checked for
PHYSICAL CONSISTENCY, not agreement. If they do not describe one plan, later
rounds re-prompt each agent with the others' positions attached, which is where
genuine reasoning happens: an agent seeing a peer's retrofit proposal can
revise its own answer in a way no fixed decision tree could produce.

Bounded at MAX_NEGOTIATION_ROUNDS. On exhaustion the orchestrator escalates
with every trade-off laid out. It never silently picks a side.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.cloud.firestore_v1.base_query import FieldFilter
from google.genai import types as genai_types
from pydantic import ValidationError
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

from ..common import obs
from ..common.auth import get_credentials
from ..common.config import (BACKOFF_MAX_SECONDS, BACKOFF_MULTIPLIER, MAX_ATTEMPTS,
                             MAX_NEGOTIATION_ROUNDS, MAX_OUTPUT_TOKENS_ORCHESTRATOR,
                             MODEL_ORCHESTRATOR, PROJECT_ID, VERTEX_LOCATION)
from ..common.data_access import shared_client
from ..common.verdict import AgentVerdict
from . import consistency
from .decision import OrchestratorDecision
from .instructions import RECONCILE_INSTRUCTION

DOMAINS = ("power", "cooling", "facilities", "cost")


def _build_specialists() -> dict[str, Any]:
    """In-process locally; over the gateway when deployed.

    Selected by GRIDMIND_GATEWAY_URL. Both paths expose the same decide()
    signature, so the negotiation loop below is byte-identical either way --
    which is what makes it possible to debug a negotiation on a laptop and
    trust that the deployed behaviour matches.
    """
    gateway = os.environ.get("GRIDMIND_GATEWAY_URL", "").strip()
    if gateway:
        from .remote import RemoteSpecialist
        obs.log("using_remote_specialists", agent="orchestrator", gateway=gateway)
        return {d: RemoteSpecialist(d, gateway) for d in DOMAINS}

    from ..cooling.agent import build_agent as cooling_agent
    from ..cost.agent import build_agent as cost_agent
    from ..facilities.agent import build_agent as facilities_agent
    from ..power.agent import build_agent as power_agent
    return {"power": power_agent(), "cooling": cooling_agent(),
            "facilities": facilities_agent(), "cost": cost_agent()}


@dataclass(slots=True)
class Round:
    number: int
    verdicts: list[AgentVerdict]
    report: consistency.ConsistencyReport


@dataclass(slots=True)
class NegotiationResult:
    workload: dict[str, Any]
    correlation_id: str
    scenario: str
    rounds: list[Round] = field(default_factory=list)
    decision: OrchestratorDecision | None = None
    precedent: dict[str, Any] | None = None

    @property
    def final_verdicts(self) -> list[AgentVerdict]:
        return self.rounds[-1].verdicts if self.rounds else []


class Orchestrator:
    def __init__(self) -> None:
        self.specialists = _build_specialists()
        self._client: genai.Client | None = None

    # ---------------- model ----------------

    def _model(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(vertexai=True, project=PROJECT_ID,
                                        location=VERTEX_LOCATION,
                                        credentials=get_credentials())
        return self._client

    # ---------------- memory bank ----------------

    def _recall_precedent(self, conflict_type: str, cid: str) -> dict | None:
        """Look for a past conflict of the same shape in shared-db.

        shared-db is the ONLY database the orchestrator can open, which is what
        makes the Memory Bank architecturally available to it while raw domain
        data is not.
        """
        try:
            docs = (shared_client().collection("memory_bank")
                    .where(filter=FieldFilter("conflict_type", "==", conflict_type))
                    .limit(1).stream())
            for d in docs:
                p = d.to_dict()
                obs.log("precedent_recalled", agent="orchestrator", correlation_id=cid,
                        precedent_id=p.get("precedent_id"), conflict_type=conflict_type)
                return p
        except Exception as exc:      # never let memory lookup break a decision
            obs.log("precedent_lookup_failed", level="warn", agent="orchestrator",
                    correlation_id=cid, error=str(exc)[:200])
        return None

    def _record(self, result: NegotiationResult) -> None:
        """Write the full negotiation to shared-db: audit trail plus precedent."""
        d = result.decision
        if d is None:
            return
        doc = {
            "workload_id": d.workload_id,
            "correlation_id": result.correlation_id,
            "scenario": result.scenario,
            "outcome": d.outcome,
            "chosen_zone": d.chosen_zone,
            "rounds_used": len(result.rounds),
            "decision": d.model_dump(),
            "rounds": [
                {
                    "round": r.number,
                    "conflict_type": r.report.conflict_type,
                    "conflicts": r.report.conflicts,
                    "verdicts": [v.model_dump() for v in r.verdicts],
                }
                for r in result.rounds
            ],
        }
        try:
            db = shared_client()
            db.collection("negotiation_log").document(result.correlation_id).set(doc)
            # Only multi-round outcomes are worth remembering. A round-1
            # approval teaches nothing and would dilute the precedent store.
            if len(result.rounds) > 1 and d.outcome in ("approved", "approved_with_conditions"):
                db.collection("memory_bank").document(f"prec-{result.correlation_id}").set({
                    "precedent_id": f"prec-{result.correlation_id}",
                    "conflict_type": result.rounds[0].report.conflict_type,
                    "summary": d.reasoning[:600],
                    "resolution": d.plan[:400],
                    "delay_hours_accepted": d.delay_hours,
                    "cost_delta_pct": d.economics.cost_delta_pct,
                    "outcome": d.outcome,
                    "lesson": "; ".join(d.tradeoffs)[:600],
                    "recorded_at": result.correlation_id,
                })
            obs.log("negotiation_recorded", agent="orchestrator",
                    correlation_id=result.correlation_id, outcome=d.outcome)
        except Exception as exc:
            obs.log("negotiation_record_failed", level="error", agent="orchestrator",
                    correlation_id=result.correlation_id, error=str(exc)[:300])

    # ---------------- rounds ----------------

    def _run_round(self, workload: dict, cid: str, scenario: str, number: int,
                   previous: list[AgentVerdict] | None) -> list[AgentVerdict]:
        """Ask all four specialists. Concurrently -- they are independent."""
        def ask(domain: str) -> AgentVerdict:
            peers = (consistency.peer_positions(previous, exclude=domain)
                     if previous else None)
            return self.specialists[domain].decide(
                workload, correlation_id=cid, scenario=scenario,
                peer_positions=peers, round_number=number)

        with ThreadPoolExecutor(max_workers=4) as pool:
            return list(pool.map(ask, DOMAINS))

    # ---------------- decision ----------------

    @retry(retry=retry_if_exception_type((ValueError, ValidationError, json.JSONDecodeError)),
           stop=stop_after_attempt(MAX_ATTEMPTS),
           wait=wait_exponential(multiplier=BACKOFF_MULTIPLIER, max=BACKOFF_MAX_SECONDS),
           reraise=True)
    def _decide(self, result: NegotiationResult) -> OrchestratorDecision:
        """Synthesise the final decision from the verdicts alone.

        Retried like every other model call in the system. The orchestrator is
        the single point where four agents' work becomes one answer, so a
        transient truncation here would waste the entire negotiation.
        """
        last = result.rounds[-1]
        payload = {
            "workload_request": result.workload,
            "negotiation_rounds": [
                {
                    "round": r.number,
                    "consistency": {
                        "consistent": r.report.consistent,
                        "conflict_type": r.report.conflict_type,
                        "conflicts": r.report.conflicts,
                        "endorsed_zones": r.report.endorsed_zones,
                        "ruled_out_by": r.report.ruled_out_by,
                        # The decisive field. Non-empty means a deployable plan
                        # EXISTS -- the remaining disagreement is preference, not
                        # a deadlock, and escalating would be a false negative.
                        "zones_surviving_all_exclusions": r.report.surviving_zones,
                    },
                    "verdicts": [v.model_dump() for v in r.verdicts],
                }
                for r in result.rounds
            ],
            "rounds_used": len(result.rounds),
            "round_limit": MAX_NEGOTIATION_ROUNDS,
            "memory_bank_precedent": result.precedent,
            # Restated at the top level so it cannot be missed inside the rounds.
            "zones_surviving_all_exclusions_final": last.report.surviving_zones,
            "a_deployable_plan_exists": bool(last.report.surviving_zones),
        }

        prompt = (
            "Reconcile these specialist verdicts into ONE decision.\n\n"
            f"{json.dumps(payload, indent=2, default=str)}\n\n"
            "Every number you report must come from a verdict above. If the round limit "
            "was reached without a consistent plan, escalate and populate "
            "unresolved_conflicts rather than choosing a side."
        )

        with obs.timed("orchestrator_reconcile", agent="orchestrator",
                       correlation_id=result.correlation_id,
                       model=MODEL_ORCHESTRATOR, rounds=len(result.rounds)) as extra:
            resp = self._model().models.generate_content(
                model=MODEL_ORCHESTRATOR,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=RECONCILE_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=OrchestratorDecision,
                    max_output_tokens=MAX_OUTPUT_TOKENS_ORCHESTRATOR,
                    temperature=0.15,
                    # The one place we pay for deeper reasoning. Specialists
                    # make a narrow judgement; this step reconciles four of them
                    # into a physically consistent plan, which is the hard part.
                    thinking_config=genai_types.ThinkingConfig(thinking_budget=4096),
                ),
            )
            u = getattr(resp, "usage_metadata", None)
            if u is not None:
                extra["prompt_tokens"] = getattr(u, "prompt_token_count", None)
                extra["output_tokens"] = getattr(u, "candidates_token_count", None)

        parsed = getattr(resp, "parsed", None)
        if isinstance(parsed, OrchestratorDecision):
            decision = parsed
        elif resp.text:
            decision = OrchestratorDecision.model_validate_json(resp.text)
        else:
            finish = None
            try:
                finish = str(resp.candidates[0].finish_reason)
            except Exception:
                pass
            raise ValueError(f"orchestrator produced no parseable decision "
                             f"(finish_reason={finish})")

        # Trust the deterministic check over the model for the escalation flag:
        # an unresolved conflict must never be reported as a clean approval.
        if not last.report.consistent and decision.outcome == "approved":
            decision.outcome = "escalated"
            if not decision.unresolved_conflicts:
                decision.unresolved_conflicts = list(last.report.conflicts)
        return decision

    # ---------------- public ----------------

    def negotiate(self, workload: dict, *, scenario: str = "normal",
                  correlation_id: str | None = None) -> NegotiationResult:
        cid = correlation_id or obs.new_correlation_id()
        result = NegotiationResult(workload=workload, correlation_id=cid, scenario=scenario)

        obs.log("negotiation_started", agent="orchestrator", correlation_id=cid,
                workload_id=workload.get("workload_id"), scenario=scenario,
                round_limit=MAX_NEGOTIATION_ROUNDS)

        previous: list[AgentVerdict] | None = None
        for n in range(1, MAX_NEGOTIATION_ROUNDS + 1):
            verdicts = self._run_round(workload, cid, scenario, n, previous)
            report = consistency.check(verdicts)
            result.rounds.append(Round(number=n, verdicts=verdicts, report=report))

            obs.log("round_complete", agent="orchestrator", correlation_id=cid, round=n,
                    consistent=report.consistent, conflict_type=report.conflict_type,
                    endorsed_zones=report.endorsed_zones,
                    statuses={v.agent: v.status for v in verdicts})

            if report.consistent:
                break

            if result.precedent is None:
                result.precedent = self._recall_precedent(report.conflict_type, cid)

            previous = verdicts

        result.decision = self._decide(result)
        self._record(result)

        obs.log("negotiation_complete", agent="orchestrator", correlation_id=cid,
                outcome=result.decision.outcome, chosen_zone=result.decision.chosen_zone,
                rounds_used=len(result.rounds), delay_hours=result.decision.delay_hours)
        return result
