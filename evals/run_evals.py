"""Run the evaluation suite and print a scorecard.

    python -m evals.run_evals              # everything
    python -m evals.run_evals --case escalate-too-many-racks
    python -m evals.run_evals --guardrails-only   # no model calls, free

Runs against the agents in-process, so it exercises the real harness, the real
Firestore reads and the real Gemini calls -- roughly 2-3 cents per case.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from agents.common import obs
from agents.orchestrator.orchestrator import Orchestrator

from .cases import CASES, EvalCase

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"


def _tick(ok: bool) -> str:
    return f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"


def run_case(orch: Orchestrator, case: EvalCase) -> dict[str, Any]:
    t0 = time.perf_counter()
    failures: list[str] = []
    try:
        result = orch.negotiate(dict(case.workload), scenario=case.scenario,
                                correlation_id=obs.new_correlation_id())
    except Exception as exc:
        return {"name": case.name, "error": f"{type(exc).__name__}: {exc}",
                "passed": False, "seconds": time.perf_counter() - t0,
                "failures": ["negotiation raised"], "rounds": 0}

    d = result.decision
    rounds = len(result.rounds)

    if d is None:
        failures.append("no decision produced")
    else:
        if d.outcome not in case.expect_outcomes:
            failures.append(f"outcome {d.outcome!r} not in {case.expect_outcomes}")
        if case.expect_zone and d.chosen_zone != case.expect_zone:
            failures.append(f"zone {d.chosen_zone!r} != expected {case.expect_zone!r}")
    if case.max_rounds is not None and rounds > case.max_rounds:
        failures.append(f"took {rounds} rounds, expected <= {case.max_rounds}")

    for label, fn in case.checks:
        try:
            if not fn(result):
                failures.append(f"check failed: {label}")
        except Exception as exc:
            failures.append(f"check errored ({label}): {type(exc).__name__}")

    return {
        "name": case.name, "passed": not failures, "failures": failures,
        "rounds": rounds, "seconds": time.perf_counter() - t0,
        "outcome": d.outcome if d else None,
        "zone": d.chosen_zone if d else None,
        "error": None,
    }


def run_guardrails() -> list[dict[str, Any]]:
    """Guardrail checks -- pure functions, no model calls, so effectively free."""
    from agents.common.constraint_context import build_constraint_context
    from agents.common.verdict import AgentVerdict, ProposedAlternative
    from agents.power.guardrail import power_guardrail

    wl = {"workload_id": "eval-guard", "racks_required": 6,
          "power_per_rack_kw": 132.0, "total_power_kw": 792.0}
    ctx = build_constraint_context("power", wl, correlation_id=obs.new_correlation_id())

    def v(**kw: Any) -> AgentVerdict:
        base = dict(agent="power", status="feasible", confidence=0.9,
                    reasoning="Zone endorsed with adequate capacity for this request.")
        base.update(kw)
        return AgentVerdict(**base)

    cases = [
        ("blocks a zone short on headroom", v(target_zone="zone-b"), False),
        ("blocks a zone with a switchgear outage", v(target_zone="zone-d"), False),
        ("blocks an invented zone", v(target_zone="zone-f"), False),
        ("blocks feasible with no zone named", v(target_zone=None), False),
        ("blocks a bad proposed_alternative",
         v(status="conditional", target_zone="zone-a",
           proposed_alternative=ProposedAlternative(
               description="fall back to zone-b", target_zone="zone-b")), False),
        ("allows a correct verdict", v(target_zone="zone-a"), True),
    ]
    out = []
    for label, verdict, should_pass in cases:
        res = power_guardrail(verdict, ctx)
        out.append({"name": label, "passed": res.passed == should_pass,
                    "detail": (res.violations[0][:90] if res.violations else "clean")})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", help="run a single case by name")
    ap.add_argument("--guardrails-only", action="store_true",
                    help="guardrail checks only; makes no model calls")
    args = ap.parse_args()

    obs.log = lambda *a, **k: None      # type: ignore[assignment]

    print(f"\n{'='*74}\nGRIDMIND EVALUATION SUITE\n{'='*74}")

    print(f"\n{DIM}Guardrails (no model calls){RESET}")
    g = run_guardrails()
    for r in g:
        print(f"  {_tick(r['passed'])}  {r['name']:<42} {DIM}{r['detail']}{RESET}")
    g_pass = sum(1 for r in g if r["passed"])

    if args.guardrails_only:
        print(f"\nGuardrails: {g_pass}/{len(g)} passed\n")
        return 0 if g_pass == len(g) else 1

    cases = [c for c in CASES if not args.case or c.name == args.case]
    if not cases:
        print(f"no case named {args.case!r}")
        return 1

    print(f"\n{DIM}Negotiations (live Gemini calls, ~2-3c each){RESET}")
    results = []
    for c in cases:
        print(f"  {YELLOW}running{RESET} {c.name} ...", end=" ", flush=True)
        r = run_case(Orchestrator(), c)
        results.append(r)
        print(f"{_tick(r['passed'])}  "
              f"{r.get('outcome') or 'ERROR'} / {r.get('zone') or '-'}  "
              f"{DIM}{r['rounds']} rounds, {r['seconds']:.0f}s{RESET}")
        for f in r["failures"]:
            print(f"          {RED}- {f}{RESET}")
        if r["error"]:
            print(f"          {RED}- {r['error'][:110]}{RESET}")

    n_pass = sum(1 for r in results if r["passed"])
    total_s = sum(r["seconds"] for r in results)
    avg_rounds = (sum(r["rounds"] for r in results) / len(results)) if results else 0

    print(f"\n{'='*74}")
    print(f"Guardrails    {g_pass}/{len(g)} passed")
    print(f"Negotiations  {n_pass}/{len(results)} passed")
    print(f"Mean rounds   {avg_rounds:.1f}")
    print(f"Wall clock    {total_s:.0f}s   "
          f"Approx cost   ${0.025 * len(results):.2f}")
    print(f"{'='*74}\n")

    return 0 if (n_pass == len(results) and g_pass == len(g)) else 1


if __name__ == "__main__":
    sys.exit(main())
