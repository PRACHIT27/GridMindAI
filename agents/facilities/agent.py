"""Facilities Agent: wiring only.

Same three-part shape as every GridMind agent:
    instructions.py  domain expertise
    guardrail.py     domain safety net
    agents/common/   shared machinery (retry, schema, logging, IAM-scoped reads)
"""
from __future__ import annotations

from ..common.harness import AgentHarness
from .guardrail import facilities_guardrail
from .instructions import SYSTEM_INSTRUCTION

DOMAIN = "facilities"


def build_agent() -> AgentHarness:
    return AgentHarness(
        domain=DOMAIN,
        system_instruction=SYSTEM_INSTRUCTION,
        guardrail=facilities_guardrail,
    )
