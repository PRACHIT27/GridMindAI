"""Render a negotiation as a human-readable decision report.

The report is a deliverable, not debug output. A capacity decision that cannot
be explained to the team it affects is not much better than the spreadsheet it
replaced, and "no auditable reasoning trail" is one of the four failures this
system exists to fix.

So it shows every agent's verdict in every round, what changed between rounds
and why, the trade-offs that were accepted, and the cost and efficiency
consequences -- with every figure attributed to the agent that reported it.
"""
from __future__ import annotations

import shutil

from ..common.verdict import AgentVerdict, EscalationVerdict
from .orchestrator import NegotiationResult

WIDTH = min(shutil.get_terminal_size((100, 24)).columns, 100)

_STATUS = {"feasible": "FEASIBLE", "conditional": "CONDITIONAL", "infeasible": "INFEASIBLE"}
_OUTCOME = {
    "approved": "APPROVED",
    "approved_with_conditions": "APPROVED WITH CONDITIONS",
    "rejected": "REJECTED",
    "escalated": "ESCALATED TO HUMAN",
}


def _rule(ch: str = "=") -> str:
    return ch * WIDTH


def _head(title: str, ch: str = "=") -> str:
    return f"\n{_rule(ch)}\n{title}\n{_rule(ch)}"


def _wrap(text: str, indent: int = 6) -> str:
    import textwrap
    return textwrap.fill(" ".join(text.split()), width=WIDTH - 2,
                         initial_indent=" " * indent, subsequent_indent=" " * indent)


def _money(v: float | None) -> str:
    return "not reported" if v is None else f"${v:,.0f}"


def _verdict_block(v: AgentVerdict) -> list[str]:
    lines = [f"  [{v.agent.upper()}]  {_STATUS.get(v.status, v.status.upper())}"
             f"   zone: {v.target_zone or '-'}   confidence: {v.confidence:.2f}"]

    if isinstance(v, EscalationVerdict) or getattr(v, "escalated", False):
        lines.append("      !! HARNESS FAILED SAFE -- this agent could not produce a "
                     "trustworthy verdict and refused rather than guessing.")

    lines.append(_wrap(v.reasoning))

    if v.proposed_alternative:
        a = v.proposed_alternative
        bits = []
        if a.target_zone:
            bits.append(f"zone {a.target_zone}")
        if a.delay_hours:
            bits.append(f"+{a.delay_hours:.0f} h")
        if a.cost_delta_pct:
            bits.append(f"{a.cost_delta_pct:+.1f}% cost")
        suffix = f"   ({', '.join(bits)})" if bits else ""
        lines.append(_wrap(f"PROPOSES: {a.description}{suffix}", indent=6))
    return lines


def render(result: NegotiationResult) -> str:
    wl = result.workload
    d = result.decision
    out: list[str] = []

    # ---------------- header ----------------
    out.append(_head("GRIDMIND  --  CAPACITY ALLOCATION DECISION REPORT"))
    out.append(f"  Workload      {wl.get('workload_id')}  --  {wl.get('description','')}")
    out.append(f"  Request       {wl.get('racks_required')} x {wl.get('rack_type') or wl.get('gpu_model')}"
               f"  @ {wl.get('power_per_rack_kw')} kW/rack  =  {wl.get('total_power_kw')} kW")
    out.append(f"  Cooling       {wl.get('cooling_requirement')}"
               f"     Rack weight  {wl.get('rack_weight_kg')} kg")
    out.append(f"  Priority      {wl.get('priority')}     Duration {wl.get('duration_weeks')} weeks")
    out.append(f"  Conditions    scenario '{result.scenario}'")
    out.append(f"  Trace         {result.correlation_id}")

    # ---------------- rounds ----------------
    for r in result.rounds:
        title = f"ROUND {r.number}" + (
            "  --  independent assessment, no agent sees another's answer"
            if r.number == 1 else
            "  --  each agent re-prompted with the others' positions attached")
        out.append(_head(title, "-"))
        for v in sorted(r.verdicts, key=lambda x: x.agent):
            out += _verdict_block(v)
            out.append("")

        out.append(f"  JOINT FEASIBILITY CHECK -> {r.report.conflict_type.upper()}")
        if r.report.endorsed_zones:
            zones = ", ".join(f"{a}={z}" for a, z in sorted(r.report.endorsed_zones.items()))
            out.append(f"      zones endorsed: {zones}")
        if r.report.ruled_out_by:
            for a, zs in sorted(r.report.ruled_out_by.items()):
                if zs:
                    out.append(f"      {a} rules out: {', '.join(zs)}")
        if r.report.surviving_zones:
            out.append(f"      ZONES SURVIVING EVERY AGENT'S EXCLUSIONS: "
                       f"{', '.join(r.report.surviving_zones)}")
            out.append(_wrap("No single agent could compute this -- it is the intersection "
                             "of four independent exclusion lists, and it is frequently a "
                             "zone that not one agent endorsed on its own.", indent=6))
        for c in r.report.conflicts:
            out.append(_wrap(f"- {c}", indent=6))
        if r.report.consistent:
            out.append("      RESULT: verdicts describe one physically consistent plan.")
        else:
            out.append("      RESULT: no single deployable plan yet -- opening another round.")

    # ---------------- what changed ----------------
    if len(result.rounds) > 1:
        out.append(_head("WHAT THE NEGOTIATION CHANGED", "-"))
        first = {v.agent: v for v in result.rounds[0].verdicts}
        last = {v.agent: v for v in result.rounds[-1].verdicts}
        moved = False
        for agent in sorted(first):
            a, b = first[agent], last[agent]
            if a.status != b.status or a.target_zone != b.target_zone:
                moved = True
                out.append(f"  {agent.upper():<11} {a.status}/{a.target_zone or '-'}"
                           f"   ->   {b.status}/{b.target_zone or '-'}")
                out.append(_wrap(f"why: {b.reasoning}", indent=6))
        if not moved:
            out.append("  No agent changed position; the conflict was structural, not "
                       "a matter of information.")

    # ---------------- precedent ----------------
    if result.precedent:
        p = result.precedent
        out.append(_head("MEMORY BANK  --  PRIOR CASE CONSULTED", "-"))
        out.append(f"  {p.get('precedent_id')}   ({p.get('conflict_type')})")
        out.append(_wrap(p.get("summary", ""), indent=6))
        if p.get("lesson"):
            out.append(_wrap(f"LESSON: {p['lesson']}", indent=6))

    if d is None:
        out.append(_head("NO DECISION PRODUCED"))
        return "\n".join(out)

    # ---------------- decision ----------------
    out.append(_head(f"DECISION:  {_OUTCOME.get(d.outcome, d.outcome.upper())}"))
    out.append(f"  Zone          {d.chosen_zone or '-- none --'}")
    out.append(f"  Delay         {d.delay_hours:.0f} hours")
    out.append(f"  Rounds used   {len(result.rounds)}")
    if d.precedent_applied:
        out.append(f"  Precedent     {d.precedent_applied}")
    out.append("")
    out.append("  PLAN")
    out.append(_wrap(d.plan))

    if d.conditions:
        out.append("\n  CONDITIONS")
        for c in d.conditions:
            out.append(_wrap(f"- {c}"))

    out.append("\n  HOW THE CONFLICT WAS RECONCILED")
    out.append(_wrap(d.reasoning))

    # ---------------- trade-offs ----------------
    if d.tradeoffs:
        out.append(_head("NEGOTIATION TRADE-OFFS", "-"))
        for t in d.tradeoffs:
            out.append(_wrap(f"- {t}", indent=4))

    # ---------------- economics ----------------
    e = d.economics
    out.append(_head("COST", "-"))
    out.append(f"  Recurring monthly cost      {_money(e.estimated_monthly_cost_usd)}")
    out.append(f"  Change vs original request  {e.cost_delta_pct:+.1f}%")
    out.append(f"  One-time capex              {_money(e.one_time_capex_usd)}")
    if e.monthly_saving_vs_next_best_usd:
        out.append(f"  Saving vs next-best zone    {_money(e.monthly_saving_vs_next_best_usd)}"
                   f" per month")
    if e.payback_months is not None:
        out.append(f"  Payback on the capex        {e.payback_months:.1f} months")
        dur = wl.get("duration_weeks")
        if dur:
            weeks = e.payback_months * 4.35
            verdict = ("pays for itself within the workload's life"
                       if weeks <= float(dur) else
                       "does NOT pay back within the workload's life")
            out.append(f"                              -> {verdict} "
                       f"({weeks:.0f} wks vs {dur} wks)")

    out.append(_head("EFFICIENCY", "-"))
    if e.pue_at_chosen_zone:
        out.append(f"  PUE at chosen zone          {e.pue_at_chosen_zone:.3f}")
    if e.pue_at_next_best_zone:
        out.append(f"  PUE at next-best zone       {e.pue_at_next_best_zone:.3f}")
    if e.pue_at_chosen_zone and e.pue_at_next_best_zone:
        delta = e.pue_at_next_best_zone - e.pue_at_chosen_zone
        it_kw = float(wl.get("total_power_kw") or 0)
        # Overhead power is (PUE - 1) x IT load, so the PUE gap converts
        # directly into avoided kW of cooling and distribution draw.
        out.append(f"  PUE advantage               {delta:+.3f}"
                   f"  ->  {delta * it_kw:,.0f} kW less overhead on {it_kw:,.0f} kW of IT load")
    if e.efficiency_note:
        out.append(_wrap(e.efficiency_note, indent=4))
    if e.stranded_capacity_avoided:
        out.append("\n  STRANDED CAPACITY AVOIDED")
        out.append(_wrap(e.stranded_capacity_avoided, indent=4))

    # ---------------- escalation ----------------
    if d.unresolved_conflicts:
        out.append(_head("UNRESOLVED  --  REQUIRES HUMAN DECISION", "!"))
        for c in d.unresolved_conflicts:
            out.append(_wrap(f"- {c}", indent=4))
        out.append(_wrap("The orchestrator did not choose a side. All trade-offs above are "
                         "presented for a human to weigh.", indent=4))

    # ---------------- provenance ----------------
    out.append(_head("AUDIT", "-"))
    out.append(f"  Written to shared-db/negotiation_log/{result.correlation_id}")
    out.append("  The orchestrator holds no access to power, cooling, facilities or cost")
    out.append("  databases. Every figure above was reported by a specialist agent and is")
    out.append("  attributable to its verdict. Verify with infra/iam/03_verify_isolation.sh")
    out.append(_rule())
    return "\n".join(out)
