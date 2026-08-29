"""Power Agent: electrical feasibility, and nothing else.

Wiring only. The three pieces of a GridMind agent:

    instructions.py  domain expertise      (what an electrical engineer knows)
    guardrail.py     domain safety net     (what counts as an impossible answer)
    agents/common/   shared machinery      (retry, schema, logging, IAM-scoped reads)

This is the template the other three specialists follow. Cloning it means
writing a new instructions.py and guardrail.py -- nothing else changes, which
is the payoff of putting the plumbing in the harness.
"""
from __future__ import annotations

from ..common.harness import AgentHarness
from .guardrail import power_guardrail
from .instructions import SYSTEM_INSTRUCTION

DOMAIN = "power"


def build_agent() -> AgentHarness:
    return AgentHarness(
        domain=DOMAIN,
        system_instruction=SYSTEM_INSTRUCTION,
        guardrail=power_guardrail,
    )
