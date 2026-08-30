"""Demonstrate the output guardrails. No model calls, so it is free and instant.

    python -m scripts.demo_guardrails

Feeds the Power agent's guardrail a set of deliberately wrong verdicts and
shows it refusing each one against the same ground truth the agent was handed.
This is the OUTPUT-correctness layer: it checks whether a verdict is physically
possible, and is deliberately blind to how the answer was reached. Content
screening -- prompt injection, jailbreak, PII -- is Model Armor's job at the
gateway, and the two are not substitutes for each other.
"""
from __future__ import annotations

import sys
from typing import Any

from agents.common import obs
from agents.common.constraint_context import build_constraint_context
from agents.common.verdict import AgentVerdict, ProposedAlternative
from agents.power.guardrail import power_guardrail


def main() -> int:
    obs.log = lambda *a, **k: None      # type: ignore[assignment]

    wl = {"workload_id": "guardrail-demo", "racks_required": 6,
          "power_per_rack_kw": 132.0, "total_power_kw": 792.0}
    ctx = build_constraint_context("power", wl, correlation_id=obs.new_correlation_id())

    def v(**kw: Any) -> AgentVerdict:
        base = dict(agent="power", status="feasible", confidence=0.9,
                    reasoning="Zone endorsed with adequate capacity for this request.")
        base.update(kw)
        return AgentVerdict(**base)

    cases = [
        ("endorses a zone 231 kW short", v(target_zone="zone-b"), False),
        ("calls a zone with a switchgear outage feasible", v(target_zone="zone-d"), False),
        ("invents a zone that does not exist", v(target_zone="zone-f"), False),
        ("says feasible but names no zone", v(target_zone=None), False),
        ("hides an impossible zone in proposed_alternative",
         v(status="conditional", target_zone="zone-a",
           proposed_alternative=ProposedAlternative(
               description="fall back to zone-b", target_zone="zone-b")), False),
        ("a correct verdict", v(target_zone="zone-a"), True),
    ]

    print("\n" + "=" * 78)
    print("POWER AGENT GUARDRAIL — verdicts re-checked against ground truth")
    print("=" * 78 + "\n")

    failures = 0
    for label, verdict, should_pass in cases:
        res = power_guardrail(verdict, ctx)
        ok = res.passed == should_pass
        failures += not ok
        mark = "PASS" if ok else "FAIL"
        action = "allowed" if res.passed else "BLOCKED"
        print(f"  [{mark}] {label}")
        print(f"         -> {action}")
        for viol in res.violations:
            print(f"            {viol}")
        print()

    print("=" * 78)
    print(f"{len(cases) - failures}/{len(cases)} behaved as expected")
    print("Every refusal above cites the same numbers the agent was given, so a")
    print("hallucinated verdict is caught before it can reach the orchestrator.")
    print("=" * 78 + "\n")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
