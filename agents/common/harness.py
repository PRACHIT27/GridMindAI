"""The agent harness.

The model call is ONE STEP inside this class, not the agent itself. Around it:

  1. structured I/O      -- schema-validated in and out, never free text
  2. scoped tool access  -- Firestore reads confined to one database by IAM
  3. retry + fail-safe   -- bounded retries, then refuse rather than guess
  4. structured logging  -- emitted from the harness, so it cannot be forgotten
  5. guardrail           -- verdicts re-checked against the same ground truth
                            the agent was given, before anyone trusts them

That list is the difference between "harness engineering" and "prompting
Gemini". Swap the model out and all five properties survive.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Protocol

from google import genai
from google.genai import types as genai_types
from pydantic import ValidationError
from tenacity import (RetryCallState, retry, retry_if_exception_type,
                      stop_after_attempt, wait_exponential)

from . import obs
from .auth import get_credentials
from .config import (BACKOFF_MAX_SECONDS, BACKOFF_MULTIPLIER, MAX_ATTEMPTS,
                     MAX_OUTPUT_TOKENS_SPECIALIST, MODEL_SPECIALIST,
                     PROJECT_ID, VERTEX_LOCATION)
from .constraint_context import ConstraintContext, build_constraint_context
from .verdict import AgentVerdict, EscalationVerdict, GuardrailResult


class GuardrailFn(Protocol):
    """Re-checks a verdict against ground truth. Domain-specific."""
    def __call__(self, verdict: AgentVerdict, ctx: ConstraintContext) -> GuardrailResult: ...


class GuardrailViolation(Exception):
    """A verdict contradicted the constants the agent was handed.

    Retried rather than raised to the caller: the violation text is fed back to
    the model as correction, which in practice fixes it on attempt two. An
    agent that proposes a 132 kW workload into an air-cooled zone was told the
    40 kW ceiling and ignored it -- that is a model error, and it must not
    reach the orchestrator.
    """
    def __init__(self, result: GuardrailResult):
        self.result = result
        super().__init__("; ".join(result.violations))


class ModelOutputError(Exception):
    """Model returned nothing parseable -- empty candidate, or invalid JSON."""


_TRANSIENT = (ModelOutputError, GuardrailViolation, ValidationError, json.JSONDecodeError)

_client: genai.Client | None = None
_client_lock = threading.Lock()


def get_client() -> genai.Client:
    """Vertex AI client, pinned to the `global` location.

    Gemini 3.5 is served only from the global endpoint -- regional endpoints
    404 for these model ids. Getting this wrong silently drops the project to a
    model that does not satisfy the hackathon's "Gemini 3.5 or newer" rule.

    DOUBLE-CHECKED LOCKING IS LOAD-BEARING HERE. The orchestrator runs all four
    specialists concurrently, so without the lock every thread sees
    `_client is None`, each builds its own genai.Client, and the losers get
    garbage collected -- whose finalizers close the shared HTTP transport out
    from under the surviving client. Every subsequent call then dies with
    "Cannot send a request, as the client has been closed", the harness fails
    the agents safe, and an entire negotiation round is lost to what looks like
    three agents inexplicably refusing the request.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:      # re-check: another thread may have won
                _client = genai.Client(vertexai=True, project=PROJECT_ID,
                                       location=VERTEX_LOCATION,
                                       credentials=get_credentials())
    return _client


def _build_config(
    *,
    system_instruction: str,
    max_output_tokens: int,
    thinking_budget: int | None,
) -> genai_types.GenerateContentConfig:
    """Force JSON output matching AgentVerdict, and budget thinking tokens.

    response_schema is what makes the I/O contract structural rather than
    hopeful -- the model is constrained to the shape, and pydantic still
    validates afterwards because "matches the schema" and "is semantically
    valid" are different claims.
    """
    kwargs: dict[str, Any] = {
        "system_instruction": system_instruction,
        "response_mime_type": "application/json",
        "response_schema": AgentVerdict,
        "max_output_tokens": max_output_tokens,
        # Low but nonzero: we want consistent engineering judgment, with just
        # enough variation that a re-prompt in round 2 can actually move.
        "temperature": 0.2,
    }
    if thinking_budget is not None:
        try:
            kwargs["thinking_config"] = genai_types.ThinkingConfig(
                thinking_budget=thinking_budget)
        except Exception:  # pragma: no cover - SDK surface varies by version
            # Not fatal: without an explicit budget the model picks its own.
            obs.log("thinking_config_unsupported", level="warn",
                    message="SDK rejected ThinkingConfig; using model default")
    return genai_types.GenerateContentConfig(**kwargs)


class AgentHarness:
    """Wraps one specialist agent. Construct once per service, reuse per request."""

    def __init__(
        self,
        domain: str,
        system_instruction: str,
        *,
        guardrail: GuardrailFn | None = None,
        model: str = MODEL_SPECIALIST,
        max_output_tokens: int = MAX_OUTPUT_TOKENS_SPECIALIST,
        thinking_budget: int | None = 512,
    ) -> None:
        self.domain = domain
        self.system_instruction = system_instruction
        self.guardrail = guardrail
        self.model = model
        self.max_output_tokens = max_output_tokens
        self.thinking_budget = thinking_budget

    # ---------------- public API ----------------

    def decide(
        self,
        workload: dict[str, Any],
        *,
        correlation_id: str,
        scenario: str = "normal",
        peer_positions: list[dict[str, Any]] | None = None,
        round_number: int = 1,
    ) -> AgentVerdict:
        """Produce one schema-valid, guardrail-checked verdict.

        Never raises for model failure. If every attempt fails, returns an
        EscalationVerdict marked infeasible -- fail SAFE, so a broken agent
        stalls a placement instead of rubber-stamping one.
        """
        ctx = build_constraint_context(
            self.domain, workload,
            correlation_id=correlation_id,
            scenario=scenario,
            peer_positions=peer_positions,
            round_number=round_number,
        )

        # Records how the verdict was arrived at, not just what it says. A
        # verdict the guardrail had to reject and re-prompt is materially less
        # trustworthy than one that was right first time, and an auditor cannot
        # see that difference from the reasoning text alone.
        audit: dict[str, Any] = {"attempts": 0, "corrections": []}

        try:
            verdict = self._decide_with_retry(ctx, audit)
        except Exception as exc:
            return self._fail_safe(ctx, exc)

        verdict.constraint_snapshot = {
            **ctx.snapshot(),
            **verdict.constraint_snapshot,
            "harness": {
                "attempts_used": audit["attempts"],
                "corrected_by_guardrail": bool(audit["corrections"]),
                "guardrail_corrections": audit["corrections"],
                "model": self.model,
            },
        }
        obs.log("verdict_returned", agent=self.domain, correlation_id=correlation_id,
                round=round_number, status=verdict.status, zone=verdict.target_zone,
                confidence=verdict.confidence,
                has_alternative=verdict.proposed_alternative is not None)
        return verdict

    # ---------------- internals ----------------

    def _decide_with_retry(self, ctx: ConstraintContext,
                           audit: dict[str, Any]) -> AgentVerdict:
        corrections: list[str] = []

        def _log_retry(state: RetryCallState) -> None:
            exc = state.outcome.exception() if state.outcome else None
            if exc is not None:
                text = self._correction_for(exc)
                corrections.append(text)
                audit["corrections"].append(text[:300])
            obs.log("agent_attempt_failed", level="warn", agent=self.domain,
                    correlation_id=ctx.correlation_id, attempt=state.attempt_number,
                    error_type=type(exc).__name__, error=str(exc)[:400])

        @retry(
            retry=retry_if_exception_type(_TRANSIENT),
            stop=stop_after_attempt(MAX_ATTEMPTS),
            wait=wait_exponential(multiplier=BACKOFF_MULTIPLIER, max=BACKOFF_MAX_SECONDS),
            before_sleep=_log_retry,
            reraise=True,
        )
        def _attempt() -> AgentVerdict:
            audit["attempts"] += 1
            return self._one_attempt(ctx, corrections)

        return _attempt()

    def _one_attempt(self, ctx: ConstraintContext, corrections: list[str]) -> AgentVerdict:
        prompt = self._render_prompt(ctx, corrections)

        with obs.timed("model_call", agent=self.domain, correlation_id=ctx.correlation_id,
                       model=self.model, round=ctx.round_number) as extra:
            response = get_client().models.generate_content(
                model=self.model,
                contents=prompt,
                config=_build_config(
                    system_instruction=self.system_instruction,
                    max_output_tokens=self.max_output_tokens,
                    thinking_budget=self.thinking_budget,
                ),
            )
            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                extra["prompt_tokens"] = getattr(usage, "prompt_token_count", None)
                extra["output_tokens"] = getattr(usage, "candidates_token_count", None)
                extra["thought_tokens"] = getattr(usage, "thoughts_token_count", None)

        verdict = self._parse(response)

        # The model is untrusted until its answer survives the same constants
        # it was given. This is where hallucinated headroom gets caught.
        if self.guardrail is not None:
            result = self.guardrail(verdict, ctx)
            if not result.passed:
                obs.log("guardrail_violation", level="warn", agent=self.domain,
                        correlation_id=ctx.correlation_id,
                        violations=result.violations, proposed_zone=verdict.target_zone)
                raise GuardrailViolation(result)

        return verdict

    def _parse(self, response: Any) -> AgentVerdict:
        """Turn a raw model response into a validated verdict."""
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, AgentVerdict):
            return parsed

        text = getattr(response, "text", None)
        if not text or not text.strip():
            # The characteristic Gemini 3.5 failure: the whole output budget
            # was consumed by internal reasoning, leaving an empty candidate.
            finish = None
            try:
                finish = str(response.candidates[0].finish_reason)
            except Exception:
                pass
            raise ModelOutputError(f"empty model output (finish_reason={finish})")

        return AgentVerdict.model_validate_json(text)

    def _render_prompt(self, ctx: ConstraintContext, corrections: list[str]) -> str:
        parts = [
            f"You are the {self.domain.upper()} agent for facility "
            f"{ctx.internal_constants['facility']['facility_id']}.",
            "",
            f"NEGOTIATION ROUND: {ctx.round_number}",
            "",
            "CONSTRAINT CONTEXT (authoritative -- do not invent values not present here):",
            ctx.to_prompt_block(),
            "",
        ]

        if ctx.peer_positions:
            parts += [
                "The other agents have taken the positions listed under "
                "peer_agent_positions above.",
                "Reconsider YOUR OWN axis in light of them. You are not being asked to "
                "defer, and you must not approve something your domain cannot support. "
                "You ARE being asked whether a different zone or a different timing makes "
                "the joint plan work while still satisfying your constraint.",
                "",
                # Without this, an agent keeps re-endorsing a zone that is fine on ITS
                # axis but already dead on someone else's -- Facilities re-proposing a
                # zone with free racks that Power has shown cannot be fed. Each round
                # then restates the same deadlock instead of narrowing it, and the
                # negotiation burns its round budget going nowhere.
                "A ZONE RULED OUT ON A HARD PHYSICAL LIMIT IS DEAD. If a peer reports "
                "that a zone lacks the electrical headroom, lacks the cooling ports, is "
                "the wrong cooling type, or has a floor rating below the rack weight, "
                "that zone cannot host this workload no matter how good it looks on your "
                "axis. Stop endorsing it, and say which peer finding ruled it out.",
                "",
                # Without this an agent keeps optimising its own axis while its peers
                # have already converged: Power holding out for the roomiest zone when
                # the zone everyone else agreed on cleared its limits comfortably. The
                # result is a false escalation -- a workable plan refused because no
                # single zone was every agent's favourite.
                "YOU ARE ASSESSING FEASIBILITY, NOT CHOOSING A FAVOURITE. If a zone your "
                "peers have endorsed SATISFIES your own constraints, endorse it too, even "
                "when another zone would suit your axis better. A zone that clears every "
                "team's limits beats one that is merely optimal for yours. Hold out only "
                "when the peers' zone genuinely fails a limit you own -- and then say "
                "which limit, with the numbers.",
                "",
                "Timing and money are negotiable. Physics and law are not. If the only "
                "workable zone needs a delay or a one-off cost, say so with numbers "
                "rather than reaching for a zone a peer has already excluded.",
                "",
            ]

        if corrections:
            parts += [
                "YOUR PREVIOUS ANSWER WAS REJECTED. Correct these problems:",
                *(f"  - {c}" for c in corrections),
                "",
            ]

        parts += [
            "Decide feasibility ON YOUR AXIS ONLY. Do not speculate about other domains.",
            "If you cannot approve as requested, propose a concrete alternative "
            "(zone, timing, or configuration) rather than a bare rejection.",
            "Cite the specific numbers and any policy citation that drove your decision "
            "in `reasoning`, and record those numbers in `constraint_snapshot`.",
        ]
        return "\n".join(parts)

    @staticmethod
    def _correction_for(exc: Exception) -> str:
        if isinstance(exc, GuardrailViolation):
            return ("Your answer violated a hard constraint you were given: "
                    + "; ".join(exc.result.violations))
        if isinstance(exc, (ValidationError, json.JSONDecodeError)):
            return f"Your output did not match the required schema: {str(exc)[:300]}"
        if isinstance(exc, ModelOutputError):
            return "You returned no output. Answer concisely and emit the JSON verdict."
        return f"Previous attempt failed: {str(exc)[:200]}"

    def _fail_safe(self, ctx: ConstraintContext, exc: Exception) -> EscalationVerdict:
        """All retries exhausted. Refuse, loudly, and hand it to a human.

        Deliberately NOT a fallback guess. An agent that cannot reason reliably
        about a 90 MW electrical envelope should stop the line, not approve
        and hope.
        """
        obs.log("agent_failed_safe", level="error", agent=self.domain,
                correlation_id=ctx.correlation_id, round=ctx.round_number,
                error_type=type(exc).__name__, error=str(exc)[:500],
                message=f"{self.domain} agent exhausted {MAX_ATTEMPTS} attempts; escalating")

        return EscalationVerdict(
            agent=self.domain,  # type: ignore[arg-type]
            status="infeasible",
            reasoning=(
                f"The {self.domain} agent could not produce a trustworthy verdict after "
                f"{MAX_ATTEMPTS} attempts ({type(exc).__name__}). Failing safe to infeasible "
                f"and escalating for human review rather than guessing."
            ),
            target_zone=None,
            proposed_alternative=None,
            confidence=0.0,
            constraint_snapshot=ctx.snapshot(),
            failure_reason=f"{type(exc).__name__}: {str(exc)[:300]}",
        )
