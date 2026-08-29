"""Structured logging, baked into the harness rather than bolted on.

Cloud Run captures anything written to stdout and ships it to Cloud Logging.
If the line is valid JSON with a `severity` field, Cloud Logging parses it into
a structured entry -- so `jsonPayload.event="verdict_returned"` becomes a
queryable filter with no logging agent or SDK required. That is what feeds
Agent Observability.

AWS analogy: stdout -> Cloud Logging is the same deal as stdout -> CloudWatch
Logs, and emitting JSON gets you the equivalent of CloudWatch Logs Insights
field extraction for free.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

_SEVERITY = {"debug": "DEBUG", "info": "INFO", "warn": "WARNING",
             "error": "ERROR", "critical": "CRITICAL"}


def new_correlation_id() -> str:
    """One id per workload request, threaded through every agent that touches it.

    This is what makes a negotiation reconstructable after the fact: filter
    Cloud Logging on a single correlation_id and the whole multi-agent decision
    trail comes back in order.
    """
    return f"gm-{uuid.uuid4().hex[:12]}"


def log(event: str, *, level: str = "info", agent: str | None = None,
        correlation_id: str | None = None, **fields: Any) -> None:
    """Emit one structured JSON log line to stdout."""
    entry: dict[str, Any] = {
        "severity": _SEVERITY.get(level, "INFO"),
        "event": event,
        "message": fields.pop("message", event),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if agent:
        entry["agent"] = agent
    if correlation_id:
        entry["correlation_id"] = correlation_id
    entry.update(_sanitize(fields))

    # default=str so a stray datetime or pydantic object can never turn an
    # observability call into a crash inside the agent it is observing.
    sys.stdout.write(json.dumps(entry, default=str) + "\n")
    sys.stdout.flush()


@contextmanager
def timed(event: str, **kw: Any) -> Iterator[dict[str, Any]]:
    """Log an event with its wall-clock duration, whether or not it succeeds."""
    start = time.perf_counter()
    extra: dict[str, Any] = {}
    try:
        yield extra
    except Exception as exc:
        log(event, level="error", duration_ms=round((time.perf_counter() - start) * 1000, 1),
            outcome="error", error_type=type(exc).__name__, error=str(exc)[:500], **kw, **extra)
        raise
    else:
        log(event, duration_ms=round((time.perf_counter() - start) * 1000, 1),
            outcome="ok", **kw, **extra)


# Matched as whole-ish credential names rather than the bare substring "token".
# A blanket "token" match also swallows prompt_tokens / output_tokens /
# thought_tokens -- the per-call usage counts we rely on to watch spend against
# the GCP credit. Redacting those hides cost data while protecting nothing.
_REDACT = ("access_token", "id_token", "refresh_token", "bearer",
           "secret", "password", "passwd", "authorization",
           "api_key", "apikey", "credential", "private_key")


def _sanitize(fields: dict[str, Any]) -> dict[str, Any]:
    """Never let a credential reach the log sink."""
    out = {}
    for k, v in fields.items():
        out[k] = "[REDACTED]" if any(s in k.lower() for s in _REDACT) else v
    return out
