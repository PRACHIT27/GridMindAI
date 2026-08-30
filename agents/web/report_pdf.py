"""Render a stored negotiation as a downloadable PDF decision report.

WHY THE WEB TIER RENDERS THIS, NOT THE ORCHESTRATOR
The obvious placement is "the orchestrator produces a PDF when it decides".
Rendering there is worse on three counts:

  * it adds seconds to a request a human is already waiting 60-90 s on
  * the PDF needs somewhere to live, which means giving the orchestrator
    Cloud Storage write access it otherwise has no reason to hold
  * a stored PDF freezes the layout at write time, so improving the report
    would leave every past decision on the old template

Everything the report needs is already persisted in negotiation_log. Rendering
on demand keeps the orchestrator's privileges minimal, costs nothing until
someone asks, and means a layout fix instantly applies to every decision ever
made. The web tier's identity stays read-only either way.
"""
from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

INK = colors.HexColor("#12181f")
DIM = colors.HexColor("#5b6b7d")
LINE = colors.HexColor("#d6dee7")
OK = colors.HexColor("#0f7a52")
WARN = colors.HexColor("#a86a00")
BAD = colors.HexColor("#b3252f")
SOFT = colors.HexColor("#f3f6fa")

_ss = getSampleStyleSheet()
S = {
    "h1": ParagraphStyle("h1", parent=_ss["Title"], fontName="Helvetica-Bold",
                         fontSize=17, leading=21, textColor=INK, alignment=TA_LEFT),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=9, leading=13,
                          textColor=DIM, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, leading=14,
                         textColor=INK, spaceBefore=13, spaceAfter=5),
    "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.2, leading=13,
                        textColor=INK, spaceAfter=5),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.2, leading=11,
                           textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.2,
                            leading=11, textColor=INK),
    "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=8,
                            leading=10.5, textColor=colors.white),
    "mono": ParagraphStyle("mono", fontName="Courier", fontSize=7.8, leading=10.5,
                           textColor=DIM),
}

_STATUS_COLOR = {"feasible": OK, "conditional": WARN, "infeasible": BAD}


def _P(t: str, s: str = "p") -> Paragraph:
    return Paragraph(t, S[s])


def _money(v: Any) -> str:
    try:
        return f"${float(v):,.0f}"
    except (TypeError, ValueError):
        return "not reported"


def _table(rows: list, widths: list, header: bool = True) -> Table:
    t = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
          ("TOPPADDING", (0, 0), (-1, -1), 4),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
          ("LEFTPADDING", (0, 0), (-1, -1), 6),
          ("RIGHTPADDING", (0, 0), (-1, -1), 6)]
    if header:
        st += [("BACKGROUND", (0, 0), (-1, 0), INK)]
    for i in range(1 if header else 0, len(rows)):
        if i % 2 == (0 if header else 1):
            st.append(("BACKGROUND", (0, i), (-1, i), SOFT))
    t.setStyle(TableStyle(st))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(DIM)
    canvas.drawString(16 * mm, 11 * mm, "GridMind capacity allocation decision report")
    canvas.drawRightString(A4[0] - 16 * mm, 11 * mm, f"Page {doc.page}")
    canvas.setStrokeColor(LINE)
    canvas.line(16 * mm, 14 * mm, A4[0] - 16 * mm, 14 * mm)
    canvas.restoreState()


def render_pdf(n: dict[str, Any]) -> bytes:
    """Build the PDF for one negotiation_log document."""
    d = n.get("decision") or {}
    e = d.get("economics") or {}
    rounds = n.get("rounds") or []
    wl = d.get("workload_id") or n.get("workload_id") or "unknown"

    story: list = []
    A = story.append

    A(_P("Capacity Allocation Decision", "h1"))
    A(_P(f"Workload <b>{wl}</b> &nbsp;&middot;&nbsp; facility iad-dc-01, Ashburn VA "
         f"&nbsp;&middot;&nbsp; conditions '{n.get('scenario', 'normal')}' "
         f"&nbsp;&middot;&nbsp; trace {n.get('correlation_id', '')}", "sub"))
    A(HRFlowable(width="100%", thickness=0.6, color=LINE, spaceAfter=8))

    outcome = str(d.get("outcome", "unknown")).replace("_", " ").upper()
    A(_table([[Paragraph(f"<b>{outcome}</b>", S["cellb"]),
               Paragraph(f"Zone <b>{d.get('chosen_zone') or '—'}</b>", S["cell"]),
               Paragraph(f"Delay <b>{d.get('delay_hours', 0)} h</b>", S["cell"]),
               Paragraph(f"Rounds <b>{n.get('rounds_used', len(rounds))}</b>", S["cell"]),
               Paragraph(f"Capex <b>{_money(e.get('one_time_capex_usd'))}</b>", S["cell"])]],
             [42 * mm, 30 * mm, 26 * mm, 24 * mm, 36 * mm], header=False))

    if d.get("plan"):
        A(_P("Plan", "h2"))
        A(_P(str(d["plan"])))

    if d.get("conditions"):
        A(_P("Conditions", "h2"))
        for c in d["conditions"]:
            A(_P(f"&bull; {c}"))

    if d.get("reasoning"):
        A(_P("How the conflicting verdicts were reconciled", "h2"))
        A(_P(str(d["reasoning"])))

    if d.get("tradeoffs"):
        A(_P("Trade-offs accepted", "h2"))
        for t in d["tradeoffs"]:
            A(_P(f"&bull; {t}"))

    # ---- economics ----
    A(_P("Cost and efficiency", "h2"))
    rows = [[Paragraph(h, S["cellh"]) for h in ("Measure", "Value", "Reported by")]]
    econ = [
        ("Recurring monthly cost", _money(e.get("estimated_monthly_cost_usd")), "cost agent"),
        ("Change vs original request", f"{e.get('cost_delta_pct', 0):+.1f}%", "cost agent"),
        ("One-time capex", _money(e.get("one_time_capex_usd")), "cost agent"),
        ("Monthly saving vs next-best",
         _money(e.get("monthly_saving_vs_next_best_usd")), "cost agent"),
        ("Payback period",
         f"{e['payback_months']:.1f} months" if e.get("payback_months") is not None
         else "not reported", "cost agent"),
        ("PUE at chosen zone", str(e.get("pue_at_chosen_zone") or "—"), "cooling agent"),
        ("PUE at next-best zone", str(e.get("pue_at_next_best_zone") or "—"), "cooling agent"),
    ]
    for a, b, c in econ:
        rows.append([Paragraph(a, S["cell"]), Paragraph(f"<b>{b}</b>", S["cellb"]),
                     Paragraph(c, S["cell"])])
    A(_table(rows, [62 * mm, 50 * mm, 46 * mm]))

    if e.get("efficiency_note"):
        A(Spacer(1, 4))
        A(_P(str(e["efficiency_note"])))
    if e.get("stranded_capacity_avoided"):
        A(_P("Stranded capacity avoided", "h2"))
        A(_P(str(e["stranded_capacity_avoided"])))

    # ---- the negotiation ----
    A(_P("The negotiation, round by round", "h2"))
    A(_P("Round 1 is independent: no agent sees another's answer. Later rounds "
         "re-prompt each agent with the others' positions attached.", "p"))

    for r in rounds:
        A(Spacer(1, 3))
        A(_P(f"<b>Round {r.get('round')}</b> &mdash; joint feasibility: "
             f"<b>{r.get('conflict_type', '?')}</b>", "p"))
        rows = [[Paragraph(h, S["cellh"]) for h in
                 ("Agent", "Verdict", "Zone", "Reasoning")]]
        for v in sorted(r.get("verdicts", []), key=lambda x: x.get("agent", "")):
            col = _STATUS_COLOR.get(v.get("status"), INK)
            rows.append([
                Paragraph(f"<b>{v.get('agent', '')}</b>", S["cellb"]),
                Paragraph(f'<font color="{col.hexval()}"><b>'
                          f'{v.get("status", "")}</b></font>', S["cell"]),
                Paragraph(str(v.get("target_zone") or "—"), S["cell"]),
                Paragraph(str(v.get("reasoning", ""))[:600], S["cell"]),
            ])
        A(_table(rows, [20 * mm, 22 * mm, 18 * mm, 98 * mm]))

        surviving = r.get("surviving_zones")
        if surviving:
            A(_P(f"Zones surviving every agent's exclusions: <b>{', '.join(surviving)}</b>. "
                 f"No single agent could compute this &mdash; it is the intersection of "
                 f"four independent exclusion lists.", "p"))

    if d.get("unresolved_conflicts"):
        A(_P("Unresolved — requires a human decision", "h2"))
        for c in d["unresolved_conflicts"]:
            A(_P(f"&bull; {c}"))
        A(_P("The orchestrator did not choose a side. The trade-offs above are "
             "presented for a human to weigh."))

    A(_P("Provenance", "h2"))
    A(_P("The orchestrator holds no access to the power, cooling, facilities or cost "
         "databases &mdash; enforced by IAM Conditions, not convention. Every figure "
         "in this report was reported by a specialist agent and is attributable to its "
         "verdict above.", "p"))
    A(_P(f"gcloud logging read 'jsonPayload.correlation_id=\"{n.get('correlation_id', '')}\"'",
         "mono"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=18 * mm,
        title=f"GridMind decision {wl}", author="GridMind")
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
