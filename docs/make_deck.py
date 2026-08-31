"""GridMind — hackathon submission deck.

Cut to nine slides because the deck is the spine of the four-minute demo video,
so roughly twenty-five seconds per slide. Story first: problem, value, what it
does, the conflict, how it resolves. Everything engineering (isolation,
guardrails, retry, negotiation bounds, Model Armor, memory, audit) collapses to
one line each beside the architecture on slide 7, and the evidence that it runs
is slide 8.

    python docs/make_deck.py
    python docs/qa_deck.py [path]
"""
from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    Path(__file__).resolve().parent / "GridMind_Submission_Deck.pptx"

C = dict(
    bg=RGBColor(0x0E, 0x13, 0x19), panel=RGBColor(0x18, 0x20, 0x2C),
    panel2=RGBColor(0x1E, 0x27, 0x35), edge=RGBColor(0x2A, 0x35, 0x43),
    ink=RGBColor(0xEE, 0xF2, 0xF7), dim=RGBColor(0x9A, 0xA8, 0xBA),
    faint=RGBColor(0x6B, 0x7A, 0x8D), cy=RGBColor(0x4D, 0xD6, 0xFF),
    grn=RGBColor(0x34, 0xD3, 0x99), amb=RGBColor(0xFB, 0xBF, 0x24),
    red=RGBColor(0xF8, 0x71, 0x71), vio=RGBColor(0xA7, 0x8B, 0xFA),
)
H, B, M = "Arial", "Calibri", "Courier New"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide():
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = C["bg"]
    return s


def text(s, x, y, w, h, body, *, size=13, color="dim", font=B, bold=False,
         align=PP_ALIGN.LEFT, spacing=None, anchor=MSO_ANCHOR.TOP):
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate(body.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.line_spacing = Pt(spacing)
        r = p.add_run()
        r.text = line
        r.font.name = font
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = C[color]
    return tb


def card(s, x, y, w, h, fill="panel", line="edge"):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                            Inches(x), Inches(y), Inches(w), Inches(h))
    sh.adjustments[0] = 0.06
    sh.fill.solid()
    sh.fill.fore_color.rgb = C[fill]
    sh.line.color.rgb = C[line]
    sh.line.width = Pt(1)
    sh.shadow.inherit = False
    sh.text_frame.text = ""
    return sh


def dot(s, x, y, d, color):
    sh = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    sh.fill.solid()
    sh.fill.fore_color.rgb = C[color]
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def title(s, head, sub=None):
    text(s, 0.6, 0.50, 12.1, 0.64, head, size=29, bold=True, color="ink", font=H)
    if sub:
        text(s, 0.6, 1.16, 12.1, 0.36, sub, size=14, color="dim")


def bullets(s, x, y, w, items, gap=0.48, size=12.5, color="dim", bullet="grn"):
    for i, it in enumerate(items):
        yy = y + i * gap
        dot(s, x, yy + 0.09, 0.11, bullet)
        text(s, x + 0.28, yy, w - 0.28, gap, it, size=size, color=color)


def notes(s, txt):
    s.notes_slide.notes_text_frame.text = txt


# ====================================================== 1. title  (~15s)
s = slide()
text(s, 0.75, 1.90, 8.4, 1.15, "GridMind", size=60, bold=True, color="ink", font=H)
text(s, 0.78, 3.06, 8.6, 0.5, "Capacity planning for high-density data centers",
     size=21, color="cy")
text(s, 0.78, 3.74, 8.3, 1.2,
     "Every new workload has to clear power, cooling, floor space and budget before it can be "
     "placed. Today four teams check those four things separately, over several days. GridMind "
     "checks them together and returns a plan the site can actually build.", size=14, spacing=21)
card(s, 9.55, 1.90, 3.1, 3.55)
for i, (k, v, col, big) in enumerate([
        ("Track", "The Fortified\nEnterprise Fleet", "ink", True),
        ("Live", "gridmind-wuvfpvopoq\n-uk.a.run.app", "cy", False),
        ("Built on", "Gemini 3.5 on Vertex AI\nCloud Run, Firestore", "dim", False)]):
    y = 2.18 + i * 1.10
    text(s, 9.85, y, 2.6, 0.26, k, size=10.5, color="faint")
    text(s, 9.85, y + 0.25, 2.6, 0.68, v, size=13 if big else 11.5, bold=big,
         color=col, font=H if big else B, spacing=16)
notes(s, "15 seconds. Name it, say the one line, move on.")

# ==================================================== 2. problem  (~30s)
s = slide()
title(s, "The problem",
      "Four teams, four inboxes, and nobody who checks the four answers together")
for i, (name, what, col) in enumerate([
        ("Power engineering", "breaker capacity, spare circuits, grid events", "cy"),
        ("Cooling and thermal ops", "heat removal, efficiency, water permits", "grn"),
        ("Facilities and DCOps", "rack space, floor loading, install crews", "amb"),
        ("Finance and procurement", "budget, cost per GPU-hour, capex", "vio")]):
    y = 1.75 + i * 0.84
    card(s, 0.6, y, 6.5, 0.72)
    dot(s, 0.88, y + 0.22, 0.28, col)
    text(s, 1.32, y + 0.10, 2.9, 0.28, name, size=13.5, bold=True, color="ink")
    text(s, 1.32, y + 0.38, 5.3, 0.28, what, size=11.5)
card(s, 7.5, 1.75, 5.2, 3.50, "panel2")
text(s, 7.85, 2.02, 4.5, 0.85, "Each one is right.\nNobody owns the joint check.",
     size=19, bold=True, color="ink", font=H, spacing=25)
text(s, 7.85, 3.00, 4.5, 2.20,
     "Requests move from team to team by email and spreadsheet. Every approval is correct on its "
     "own axis, and no one asks whether the four approvals describe the same plan.\n\n"
     "What that leaves behind has a name in the industry: stranded capacity. Megawatts a site has "
     "paid for and cannot use.", size=12.5, spacing=19)
for i, (n, l, col) in enumerate([("days", "for four sequential approvals", "amb"),
                                 ("0", "teams who check them together", "red")]):
    text(s, 0.6 + i * 3.3, 5.45, 3.0, 0.7, n, size=38, bold=True, color=col, font=H)
    text(s, 0.6 + i * 3.3, 6.14, 3.0, 0.3, l, size=12)
text(s, 7.5, 5.45, 5.2, 0.7, "~90 sec", size=38, bold=True, color="grn", font=H)
text(s, 7.5, 6.14, 5.2, 0.4, "for the same four checks, run together", size=12)
notes(s, "30 seconds. The failure is not that a team gets it wrong. All four can be right and "
         "still describe a plan nobody can build.")

# ========================================== 3. value proposition  (~25s)
s = slide()
title(s, "What GridMind is worth")
card(s, 0.6, 1.72, 12.1, 1.25, "panel2")
text(s, 0.95, 1.94, 11.4, 0.9,
     "For the operations team that has to place a workload, GridMind returns one plan that clears "
     "power, cooling, space and budget at the same time, in about ninety seconds instead of "
     "several days, with a report showing what every assessor was shown beside what it concluded.",
     size=15, color="ink", spacing=22)
card(s, 0.6, 3.15, 5.9, 3.15)
text(s, 0.95, 3.36, 5.2, 0.3, "Today", size=14, bold=True, color="red")
bullets(s, 0.95, 3.82, 5.2, [
    "Four approvals, one team at a time",
    "Each team sees only its own data",
    "Nobody computes the joint check",
    "Conflicts surface after the racks arrive",
    "The reasoning lives in someone's inbox",
], bullet="red")
card(s, 6.8, 3.15, 5.9, 3.15)
text(s, 7.15, 3.36, 5.2, 0.3, "With GridMind", size=14, bold=True, color="grn")
bullets(s, 7.15, 3.82, 5.2, [
    "Four checks run together, in parallel",
    "The orchestrator sees all four verdicts",
    "It computes what all four constraints allow",
    "Conflicts surface before anything is ordered",
    "Every decision ships with its evidence",
], bullet="grn")
notes(s, "25 seconds. The defensibility line: nobody in the current process can compute the "
         "intersection of all four constraints, because no team can see outside its own data.")

# =============================================== 4. what it does  (~30s)
s = slide()
title(s, "What GridMind does", "A capacity request goes in. A plan the site can build comes out.")
for i, (n, d, col) in enumerate([
        ("Submit a request", "Rack count, power draw per rack, cooling type, weight, budget "
                             "ceiling. A form, not free text.", "cy"),
        ("Four assessors run in parallel", "Power, cooling, facilities and cost. Each one reads "
                                           "only its own data and answers one question.", "grn"),
        ("The orchestrator reconciles", "It checks whether the four answers describe one buildable "
                                        "plan. When they do not, it opens a negotiation round.", "amb"),
        ("You get a decision and a report", "Target zone, the plan to get there, and what every "
                                            "assessor said beside the numbers it was shown.", "vio")]):
    y = 1.75 + i * 1.18
    card(s, 0.6, y, 12.1, 1.02)
    dot(s, 0.92, y + 0.30, 0.42, col)
    text(s, 0.92, y + 0.36, 0.42, 0.32, str(i + 1), size=16, bold=True, color="bg",
         font=H, align=PP_ALIGN.CENTER)
    text(s, 1.58, y + 0.20, 3.5, 0.32, n, size=15, bold=True, color="ink")
    text(s, 5.25, y + 0.22, 7.2, 0.62, d, size=12.5, spacing=17)
text(s, 0.6, 6.55, 12.1, 0.36,
     "About ninety seconds end to end. The same four checks take a site several days today.",
     size=13, color="cy")
notes(s, "30 seconds. This is the whole product in one slide. Cue the live run here.")

# ================================================= 5. the conflict (~30s)
s = slide()
title(s, "A real run, round one",
      "Six racks of GB200 NVL72. 792 kW, liquid cooled, 1,360 kg per rack.")
for i, (who, zone, why, col) in enumerate([
        ("Power", "zone-a", "most electrical headroom", "red"),
        ("Cooling", "zone-c", "only zone that can remove the heat", "grn"),
        ("Facilities", "zone-b", "only zone with 6 free liquid racks", "amb"),
        ("Cost", "zone-b", "avoids a $48k per rack retrofit", "amb")]):
    x = 0.6 + i * 3.06
    card(s, x, 1.78, 2.92, 1.9)
    text(s, x + 0.26, 1.96, 2.4, 0.3, who, size=13, bold=True, color="dim")
    text(s, x + 0.26, 2.30, 2.4, 0.5, zone, size=25, bold=True, color=col, font=M)
    text(s, x + 0.26, 2.88, 2.42, 0.7, why, size=11, color="faint", spacing=15)
card(s, 0.6, 4.00, 12.1, 1.3, "panel2")
text(s, 0.95, 4.20, 11.4, 0.42,
     "Four correct answers. Three different rooms. No plan.",
     size=18, bold=True, color="ink", font=H)
text(s, 0.95, 4.68, 11.4, 0.42,
     "A system that counted votes would see four approvals and place the order. Then the racks "
     "arrive and the room cannot cool them.", size=13)
text(s, 0.6, 5.62, 12.1, 0.42,
     "This is the failure we built for. Not assessors contradicting each other, but assessors all "
     "being right and still adding up to nothing.", size=13.5, color="cy")
notes(s, "30 seconds. Say the four zones out loud, then pause before the next slide.")

# ============================================ 6. how it resolves  (~45s)
s = slide()
title(s, "How the disagreement gets resolved",
      "Bounded negotiation, and an intersection no single assessor could compute")
for i, (n, sub, body, flag, col) in enumerate([
        ("Round 1", "Four independent verdicts",
         "Each assessor reads only its own data and cannot see what the others said.",
         "conflict: zone_mismatch", "red"),
        ("Round 2", "Positions attached",
         "Each assessor is asked again with the others' positions attached. Facilities volunteers "
         "a retrofit it had not mentioned. Cost re-prices one rack, not six.",
         "consistent, ends here", "grn"),
        ("Round 3", "The hard limit",
         "If the verdicts still do not describe one plan, it stops and escalates with the whole "
         "disagreement attached. It never picks a winner.",
         "3 rounds, then a human", "amb")]):
    y = 1.72 + i * 1.38
    card(s, 0.6, y, 6.3, 1.24)
    text(s, 0.9, y + 0.15, 1.3, 0.28, n, size=14, bold=True, color=col)
    text(s, 2.25, y + 0.16, 2.6, 0.26, sub, size=12, bold=True, color="ink")
    text(s, 4.95, y + 0.16, 1.7, 0.26, flag, size=10, bold=True, color=col,
         align=PP_ALIGN.RIGHT)
    text(s, 0.9, y + 0.50, 5.75, 0.70, body, size=11, spacing=15)
text(s, 0.6, 5.98, 6.3, 0.7,
     "Conflict detection is ordinary code, not a model and not a vote. Whether two zone ids "
     "differ is not a judgement call.", size=11.5, color="cy", spacing=16)
card(s, 7.2, 1.72, 5.5, 4.95, "panel2")
text(s, 7.55, 1.95, 4.8, 0.3, "Each assessor also reports what it rules out",
     size=13, bold=True, color="ink")
for i, (who, zones) in enumerate([("Cooling", "zone-a  zone-b  zone-d"),
                                  ("Power", "zone-b  zone-d"),
                                  ("Facilities", "zone-a  zone-d"),
                                  ("Cost", "zone-a  zone-d")]):
    y = 2.42 + i * 0.44
    text(s, 7.55, y, 1.5, 0.3, who, size=12)
    text(s, 9.25, y, 3.2, 0.3, zones, size=12, color="red", font=M)
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(9.25), Inches(4.26), Inches(2.6), Pt(1.2))
ln.fill.solid()
ln.fill.fore_color.rgb = C["edge"]
ln.line.fill.background()
ln.shadow.inherit = False
text(s, 7.55, 4.44, 1.6, 0.3, "survives", size=12, bold=True, color="ink")
text(s, 9.25, 4.38, 3.2, 0.4, "zone-c", size=18, bold=True, color="grn", font=M)
text(s, 7.55, 5.02, 4.8, 1.5,
     "In round one, not one assessor had picked zone-c. It only appears when you intersect four "
     "independent exclusion lists, which is exactly what no team can do from inside its own "
     "silo.\n\n"
     "Final plan: zone-c, five liquid-ready racks plus one retrofit, fourteen hours of delay, "
     "$48,000 rather than $288,000.", size=11.5, spacing=16)
notes(s, "45 seconds, the most important slide. Left side is the protocol, right side is the "
         "result. The point to land: the answer was nobody's first choice.")

# ================================================ 7. under the hood (~45s)
s = slide()
title(s, "Under the hood", "Seven Cloud Run services, seven identities, five databases")


def lane(y, h, label, col):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                            Inches(0.6), Inches(y), Inches(12.1), Inches(h))
    sh.adjustments[0] = 0.04
    sh.fill.solid()
    sh.fill.fore_color.rgb = RGBColor(0x14, 0x1B, 0x25)
    sh.line.color.rgb = C[col]
    sh.line.width = Pt(1)
    sh.shadow.inherit = False
    sh.text_frame.text = ""
    text(s, 8.9, y + 0.06, 3.7, 0.24, label, size=9.5, bold=True, color=col,
         align=PP_ALIGN.RIGHT)


lane(1.62, 0.72, "PUBLIC", "faint")
card(s, 0.85, 1.74, 3.1, 0.48)
text(s, 1.05, 1.83, 2.8, 0.26, "gridmind, web tier", size=11.5, bold=True, color="cy")
text(s, 4.25, 1.86, 4.4, 0.3, "read only, no model access", size=11, color="faint")
lane(2.46, 1.30, "PRIVATE VPC, ingress=internal, 404 from the internet", "vio")
for i, (n, d, col) in enumerate([("Orchestrator", "shared store only", "cy"),
                                 ("Gateway", "identity, routing, Model Armor", "amb"),
                                 ("Four assessors", "one store each", "grn")]):
    x = 0.85 + i * 3.95
    card(s, x, 2.62, 3.7, 0.62)
    text(s, x + 0.2, 2.69, 3.3, 0.26, n, size=12, bold=True, color=col)
    text(s, x + 0.2, 2.94, 3.3, 0.24, d, size=10, color="faint")
text(s, 0.85, 3.34, 11.6, 0.3,
     "Gemini 3.5 on Vertex AI. flash-lite per assessor, flash with a 4,096-token thinking budget "
     "for reconciliation.", size=10.5, color="vio")
lane(3.88, 0.70, "DATA", "grn")
for i, d in enumerate(["power-db", "cooling-db", "facilities-db", "cost-db", "shared-db"]):
    x = 0.85 + i * 2.36
    card(s, x, 4.00, 2.16, 0.46)
    text(s, x, 4.09, 2.16, 0.26, d, size=10.5, bold=True, color="grn", font=M,
         align=PP_ALIGN.CENTER)
for i, (n, d, col) in enumerate([
        ("Data isolation", "IAM conditions on resource.name. A cross-domain read gets 403 from "
                           "Firestore, before our code runs.", "grn"),
        ("Guardrails", "Every verdict re-checked against the figures it was given. Ordinary "
                       "code. Six of six bad verdicts blocked.", "amb"),
        ("Retry, then refuse", "Three attempts with the violation fed back, then infeasible and "
                               "escalate. Never a guess.", "cy"),
        ("Model Armor", "Screens traffic between agents on the way in and out. Fails closed.", "red"),
        ("Memory Bank", "Precedent for this conflict type is recalled before reconciling, and "
                        "written back after.", "vio"),
        ("Audit", "One correlation id threads every model call, guardrail and routing decision.",
         "faint")]):
    x = 0.6 + (i % 3) * 4.05
    y = 4.78 + (i // 3) * 0.95
    card(s, x, y, 3.9, 0.85)
    dot(s, x + 0.24, y + 0.16, 0.16, col)
    text(s, x + 0.52, y + 0.11, 3.2, 0.26, n, size=11.5, bold=True, color="ink")
    text(s, x + 0.24, y + 0.40, 3.45, 0.4, d, size=9.5, spacing=13)
notes(s, "45 seconds. Do not read the six boxes. Say the shape: the most exposed service holds "
         "the least privilege, everything else is off the internet, and each of those six is one "
         "sentence because the repo has the detail. The load-bearing one is data isolation: "
         "Firestore Security Rules are not evaluated for server-side Admin SDK access, so we "
         "used IAM conditions instead.")

# =============================================== 8. proof it runs  (~25s)
s = slide()
title(s, "It is deployed, and you can check it yourself",
      "Every denial below is produced by Google Cloud, not by our application code")
card(s, 0.6, 1.75, 7.6, 2.45, "panel2")
text(s, 0.95, 1.96, 6.9, 0.3, "Run these against the live system", size=13, bold=True,
     color="ink")
text(s, 0.95, 2.40, 6.9, 1.4,
     "bash infra/iam/03_verify_isolation.sh    14 isolation checks\n"
     "bash scripts/demo_denial.sh              7 live denials, every layer\n"
     "python -m scripts.demo_guardrails        6 guardrail assertions",
     size=11.5, color="grn", font=M, spacing=22)
text(s, 0.95, 3.82, 6.9, 0.3,
     "The orchestrator is incapable of reading facility data. That is a platform property.",
     size=11, color="faint")
for i, (n, v, col) in enumerate([("Cloud Run services", "7", "cy"),
                                 ("Security checks passing", "21", "grn"),
                                 ("GEAP capabilities built", "6 of 7", "vio")]):
    y = 1.75 + i * 0.84
    card(s, 8.5, y, 4.2, 0.72)
    text(s, 8.8, y + 0.20, 2.0, 0.32, n, size=11.5, color="dim")
    text(s, 11.0, y + 0.14, 1.4, 0.42, v, size=19, bold=True, color=col, font=H,
         align=PP_ALIGN.RIGHT)
card(s, 0.6, 4.45, 12.1, 2.05)
text(s, 0.95, 4.66, 11.4, 0.3, "Stated plainly", size=12, color="faint")
text(s, 0.95, 5.02, 5.6, 1.3,
     "The facility is simulated. The agents, the infrastructure, the isolation and every denial "
     "shown are real. The data center is generated from published engineering figures, physically "
     "consistent, reproducible from a fixed seed.", size=12, spacing=17)
text(s, 6.9, 5.02, 5.5, 1.3,
     "How these decisions actually get made inside an operations team is something we would need "
     "to learn by shadowing one, not by writing a seed file. That is the honest boundary of what "
     "we built.", size=12, spacing=17)
notes(s, "25 seconds. Run at least one of the three commands live and unedited. Drawing the "
         "boundary ourselves buys credibility for everything else.")

# ===================================================== 9. close  (~15s)
s = slide()
text(s, 0.9, 2.30, 11.5, 1.4,
     "Four correct answers still add up to nothing\nunless something checks them together.",
     size=29, bold=True, color="ink", font=H, spacing=42)
text(s, 0.95, 3.95, 11.4, 0.4,
     "GridMind, capacity planning for high-density data centers", size=16, color="cy")
for i, (k, v) in enumerate([("Live", "gridmind-wuvfpvopoq-uk.a.run.app"),
                            ("Code", "github.com/PRACHIT27/GridMindAI"),
                            ("Track", "The Fortified Enterprise Fleet")]):
    x = 0.9 + i * 4.0
    text(s, x, 4.95, 3.7, 0.28, k, size=11, color="faint")
    text(s, x, 5.22, 3.8, 0.32, v, size=13, bold=True, color="ink")
notes(s, "15 seconds. Close on the one line.")

prs.save(OUT)
print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes, {len(prs.slides._sldIdLst)} slides)")
