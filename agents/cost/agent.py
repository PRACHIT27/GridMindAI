"""Cost Agent: wiring only.

Same three-part shape as every GridMind agent:
    instructions.py  domain expertise
    guardrail.py     domain safety net
    agents/common/   shared machinery (retry, schema, logging, IAM-scoped reads)
"""
from __future__ import annotations

from ..common.harness import AgentHarness
from .guardrail import cost_guardrail
from .instructions import SYSTEM_INSTRUCTION

DOMAIN = "cost"


def build_agent() -> AgentHarness:
    return AgentHarness(
        domain=DOMAIN,
        system_instruction=SYSTEM_INSTRUCTION,
        guardrail=cost_guardrail,
    )
