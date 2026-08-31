"""GridMind — hackathon submission deck.

Built against the published rubric rather than as a general project tour:

    Innovation & Operational Utility        40%
    Architectural Discipline & Tech Stack   30%
    Demo & Production Readiness             30%

Slide order follows those weights, and the two questions the rubric asks
verbatim about this track — "is the task complex enough to warrant a
multi-agent system" and "how does the system recover if a worker agent loops or
returns a hallucination" — each get their own slide rather than a bullet buried
somewhere.

    python docs/make_deck.py
"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

OUT = Path(__file__).resolve().parent / "GridMind_Submission_Deck.pptx"

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


def text(s, x, y, w, h, runs, *, size=13, color="dim", font=B, bold=False,
         italic=False, align=PP_ALIGN.LEFT, spacing=None, anchor=MSO_ANCHOR.TOP):
    """runs: a string, or a list of (text, {overrides}) for mixed formatting."""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

    lines = runs.split("\n") if isinstance(runs, str) else runs
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.line_spacing = Pt(spacing)
        body, over = (line, {}) if isinstance(line, str) else line
        r = p.add_run()
        r.text = body
        f = r.font
        f.name = over.get("font", font)
        f.size = Pt(over.get("size", size))
        f.bold = over.get("bold", bold)
        f.italic = over.get("italic", italic)
        f.color.rgb = C[over.get("color", color)]
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
    if sh.has_text_frame:
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


def notes(s, txt):
    s.notes_slide.notes_text_frame.text = txt


# ------------------------------------------------------------------ 1 title
s = slide()
text(s, 0.75, 1.95, 8.4, 1.15, "GridMind", size=60, bold=True, color="ink", font=H)
text(s, 0.78, 3.10, 8.6, 0.5, "Four agents that disagree, into one workable plan.",
     size=21, color="cy")
text(s, 0.78, 3.76, 8.3, 1.1,
     "A data center capacity request has to clear power, cooling, floor space and budget at "
     "the same time. Four teams check four things, in four inboxes, over several days — and "
     "nobody checks them together.", size=14, spacing=21)
card(s, 9.55, 1.90, 3.1, 3.55)
for i, (k, v, col) in enumerate([
        ("Track", "The Fortified\nEnterprise Fleet", "ink"),
        ("Live", "gridmind-wuvfpvopoq\n-uk.a.run.app", "cy"),
        ("Built on", "Gemini 3.5 · Vertex AI\nCloud Run · Firestore", "dim")]):
    y = 2.18 + i * 1.10
    text(s, 9.85, y, 2.6, 0.26, k, size=10.5, color="faint")
    text(s, 9.85, y + 0.25, 2.6, 0.68, v, size=13 if i == 0 else 11.5,
         bold=(i == 0), color=col, font=H if i == 0 else B, spacing=16)
notes(s, "Open on the problem, not the tech. The card on the right lets judges see the "
         "mandatory stack without me reciting it.")

# -------------------------------------------------------------- 2 friction
s = slide()
title(s, "The friction we set out to remove",
      "Innovation & Operational Utility — 40% of the score")
for i, (name, what, col) in enumerate([
        ("Power engineering", "breaker capacity, spare circuits, grid events", "cy"),
        ("Cooling / thermal ops", "heat removal, efficiency, water permits", "grn"),
        ("Facilities / DCOps", "rack space, floor loading, install crews", "amb"),
        ("Finance / procurement", "budget, cost per GPU-hour, capex", "vio")]):
    y = 1.72 + i * 0.83
    card(s, 0.6, y, 6.5, 0.72)
    dot(s, 0.86, y + 0.22, 0.28, col)
    text(s, 1.3, y + 0.10, 2.8, 0.28, name, size=13.5, bold=True, color="ink")
    text(s, 1.3, y + 0.38, 5.4, 0.28, what, size=11.5)
card(s, 7.5, 1.72, 5.2, 3.55, "panel2")
text(s, 7.85, 2.02, 4.5, 0.85, "Each one is right.\nNobody owns the joint check.",
     size=19, bold=True, color="ink", font=H, spacing=25)
text(s, 7.85, 3.00, 4.5, 2.1,
     "Requests are routed sequentially — email, Slack, spreadsheets. Every approval is correct "
     "on its own axis, and no one checks whether they describe the same plan.\n\n"
     "What that leaves behind has a name in the industry: stranded capacity. Megawatts you have "
     "paid for and cannot use.", size=12.5, spacing=19)
for i, (n, l, col) in enumerate([("days", "to place one workload", "amb"),
                                 ("0", "teams checking jointly", "red")]):
    text(s, 0.6 + i * 3.3, 5.55, 3.0, 0.7, n, size=38, bold=True, color=col, font=H)
    text(s, 0.6 + i * 3.3, 6.24, 3.0, 0.3, l, size=12)
text(s, 7.5, 5.55, 5.2, 0.7, "~90 sec", size=38, bold=True, color="grn", font=H)
text(s, 7.5, 6.24, 5.2, 0.4, "with GridMind — and the reasoning is written down", size=12)
notes(s, "40% criterion. Keep it short; the next slide is the one that lands.")

# ----------------------------------------------------------- 3 money slide
s = slide()
title(s, "Four correct answers. Zero valid plans.",
      "Round one of a real run — 6 racks of GB200 NVL72, 792 kW, liquid cooled")
for i, (who, zone, why, col) in enumerate([
        ("Power", "zone-a", "most electrical headroom", "red"),
        ("Cooling", "zone-c", "only zone that can remove the heat", "grn"),
        ("Facilities", "zone-b", "only zone with 6 free liquid racks", "amb"),
        ("Cost", "zone-b", "avoids $48k/rack retrofit", "amb")]):
    x = 0.6 + i * 3.06          # 4 cards of 2.92 land the last edge exactly on 12.70
    card(s, x, 1.78, 2.92, 1.9)
    text(s, x + 0.26, 1.96, 2.4, 0.3, who, size=13, bold=True, color="dim")
    text(s, x + 0.26, 2.30, 2.4, 0.5, zone, size=25, bold=True, color=col, font=M)
    text(s, x + 0.26, 2.88, 2.42, 0.7, why, size=11, color="faint", spacing=15)
card(s, 0.6, 4.00, 12.1, 1.3, "panel2")
text(s, 0.95, 4.20, 11.4, 0.42,
     "Three different rooms. Every verdict correct on its own axis — together, nothing buildable.",
     size=16, bold=True, color="ink", font=H)
text(s, 0.95, 4.66, 11.4, 0.42,
     "A system that counted votes would see four approvals and ship it. Then the racks arrive "
     "and the room cannot cool them.", size=13)
text(s, 0.6, 5.62, 12.1, 0.42,
     "This is the failure mode we built for — not agents contradicting each other, but agents "
     "all being right and still adding up to garbage.", size=13.5, italic=True, color="cy")
notes(s, "The slide the pitch rests on. Say the numbers, then pause.")

# -------------------------------------------------- 4 warrants multi-agent
s = slide()
title(s, "Why this genuinely needs four agents",
      "The rubric asks: is the task complex enough to warrant a multi-agent system?")
rows = [("Agent", "A different question", "Evidence only it can see", "Its store"),
        ("Power", "Is there electricity?", "breaker headroom, circuits, outages", "power-db"),
        ("Cooling", "Can we remove the heat?", "per-rack ceiling, CDU ports, PUE", "cooling-db"),
        ("Facilities", "Does it physically fit?", "free racks, floor rating, crew", "facilities-db"),
        ("Cost", "Can we afford it?", "budget, $/GPU-hour, payback", "cost-db")]
tbl = s.shapes.add_table(5, 4, Inches(0.6), Inches(1.8), Inches(12.1), Inches(2.3)).table
for w, col in zip((1.8, 3.2, 4.8, 2.3), range(4)):
    tbl.columns[col].width = Inches(w)
for r, row in enumerate(rows):
    tbl.rows[r].height = Inches(0.46)
    for c, val in enumerate(row):
        cell = tbl.cell(r, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = C["panel2"] if r == 0 else C["panel"]
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = Inches(0.14)
        p = cell.text_frame.paragraphs[0]
        run = p.add_run()
        run.text = val
        run.font.size = Pt(12.5)
        run.font.name = M if (c == 3 and r) else B
        run.font.bold = (r == 0) or (c == 0 and r > 0)
        run.font.color.rgb = (C["faint"] if r == 0 else
                              C["ink"] if c == 0 else
                              C["cy"] if c == 1 else
                              C["grn"] if c == 3 else C["dim"])
for i, (head, body) in enumerate([
        ("Not four copies of one opinion",
         "Four different questions, answered from four disjoint datasets. Cooling cannot see "
         "rack inventory. Facilities cannot see cooling capacity. That is why four answers "
         "carry more information than one."),
        ("Delegation is structural, not prompted",
         "Each agent runs as its own Cloud Run service under its own identity and can open "
         "exactly one database. An agent cannot answer outside its axis because it cannot see "
         "outside its axis.")]):
    x = 0.6 + i * 6.2
    card(s, x, 4.4, 5.9, 1.9, "panel2")
    text(s, x + 0.35, 4.62, 5.2, 0.32, head, size=15, bold=True, color="ink", font=H)
    text(s, x + 0.35, 5.00, 5.2, 1.2, body, size=12, spacing=17)
notes(s, "Answers a rubric question head-on: the split is enforced by infrastructure, not by "
         "asking the model to stay in its lane.")

# ------------------------------------------------------- 5 intersection
s = slide()
title(s, "The answer no single agent could compute",
      "Every agent also reports what its axis rules OUT — the intersection is the plan")
for i, (who, zones) in enumerate([("Cooling rules out", "zone-a   zone-b   zone-d"),
                                  ("Power rules out", "zone-b   zone-d"),
                                  ("Facilities rules out", "zone-a   zone-d"),
                                  ("Cost rules out", "zone-a   zone-d")]):
    y = 1.88 + i * 0.62
    text(s, 0.6, y, 2.5, 0.36, who, size=13, align=PP_ALIGN.RIGHT)
    text(s, 3.25, y, 3.5, 0.36, zones, size=13, color="red", font=M)
ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(3.25), Inches(4.42), Inches(3.3), Pt(1.2))
ln.fill.solid(); ln.fill.fore_color.rgb = C["edge"]; ln.line.fill.background()
ln.shadow.inherit = False
text(s, 0.6, 4.60, 2.5, 0.36, "survives everything", size=13, bold=True, color="ink",
     align=PP_ALIGN.RIGHT)
text(s, 3.25, 4.54, 3.5, 0.5, "zone-c", size=20, bold=True, color="grn", font=M)
card(s, 7.2, 1.8, 5.5, 4.0, "panel2")
text(s, 7.55, 2.06, 4.8, 0.8, "And in round one, not one agent had picked it.",
     size=19, bold=True, color="grn", font=H, spacing=25)
text(s, 7.55, 2.98, 4.8, 2.7,
     "Power wanted zone-a. Facilities and Cost wanted zone-b. The zone that actually works was "
     "nobody's first choice.\n\n"
     "It only appears when you intersect four independent exclusion lists — exactly what no team "
     "can do from inside its own silo.\n\n"
     "Final plan: zone-c, five liquid-ready racks plus one retrofitted, 14 hours' delay, $48,000 "
     "one-off. Facilities knew the retrofit existed; Cost had priced it at $288,000 assuming all "
     "six racks needed one.", size=12, spacing=18)
notes(s, "The negotiation turns four opinions into one plan. Stress that the orchestrator does "
         "not count votes.")

# ------------------------------------------------------- 6 architecture
s = slide()
title(s, "Architecture", "Architectural Discipline & Tech Stack — 30% of the score")


def lane(y, h, label, col):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                            Inches(0.6), Inches(y), Inches(12.1), Inches(h))
    sh.adjustments[0] = 0.04
    sh.fill.solid(); sh.fill.fore_color.rgb = RGBColor(0x14, 0x1B, 0x25)
    sh.line.color.rgb = C[col]; sh.line.width = Pt(1)
    sh.shadow.inherit = False
    sh.text_frame.text = ""
    text(s, 8.6, y + 0.08, 4.0, 0.26, label, size=10, bold=True, color=col,
         align=PP_ALIGN.RIGHT)


lane(1.68, 0.98, "PUBLIC", "faint")
card(s, 0.85, 1.88, 3.1, 0.62)
text(s, 1.05, 1.95, 2.8, 0.26, "gridmind · web tier", size=12.5, bold=True, color="cy")
text(s, 1.05, 2.20, 2.8, 0.26, "read-only · no model access", size=10, color="faint")
text(s, 4.25, 2.00, 6.2, 0.45,
     "the only service reachable from the internet — and the least privileged in the system",
     size=11.5)
lane(2.82, 2.42, "PRIVATE VPC · ingress=internal · 404 from the internet", "vio")
for i, (n, d, col) in enumerate([("Orchestrator", "shared store only", "cy"),
                                 ("Gateway", "identity · routing · Model Armor", "amb"),
                                 ("4 assessors", "one store each", "grn")]):
    x = 0.85 + i * 3.95
    card(s, x, 3.10, 3.7, 0.78)
    text(s, x + 0.2, 3.19, 3.3, 0.28, n, size=13, bold=True, color=col)
    text(s, x + 0.2, 3.47, 3.3, 0.28, d, size=10.5, color="faint")
text(s, 0.85, 4.06, 11.6, 0.32,
     "HARNESS around every assessor — scoped read · schema-validated I/O · guardrail re-check · "
     "retry with correction · fail safe", size=11.5, bold=True, color="amb")
text(s, 0.85, 4.42, 11.6, 0.6,
     "Gemini 3.5 on Vertex AI (global endpoint) — flash-lite per assessor, flash with a "
     "4,096-token thinking budget for reconciliation", size=11.5, color="vio")
lane(5.36, 0.96, "DATA", "grn")
for i, d in enumerate(["power-db", "cooling-db", "facilities-db", "cost-db", "shared-db"]):
    x = 0.85 + i * 2.36
    card(s, x, 5.54, 2.16, 0.6)
    text(s, x, 5.62, 2.16, 0.26, d, size=11, bold=True, color="grn", font=M,
         align=PP_ALIGN.CENTER)
    text(s, x, 5.86, 2.16, 0.24, "all others → 403", size=9.5, color="red",
         align=PP_ALIGN.CENTER)
text(s, 0.6, 6.55, 12.1, 0.32,
     "7 Cloud Run services · 7 service accounts · 5 isolated Firestore databases · 1 VPC · "
     "full diagram and reproducible setup scripts in the repo", size=12)
notes(s, "Don't read the boxes. Say the shape: the most exposed service holds the least "
         "privilege, and everything else is off the internet entirely.")

# --------------------------------------------------- 7 separation enforced
s = slide()
title(s, "Separation of concerns, enforced by the platform",
      "Not a convention in our code — an IAM condition Firestore itself applies")
text(s, 0.6, 1.70, 12.1, 0.6,
     "Firestore Security Rules are not evaluated for server-side Admin SDK access. A design that "
     "scoped agents with per-collection rules would have enforced nothing at all — and looked "
     "correct in a diagram.", size=13.5, color="amb", spacing=20)
sec = [("Identity", "Its own store", "The other stores", "From the internet"),
       ("power / cooling / facilities / cost", "200", "403", "404"),
       ("orchestrator", "shared only", "403 — all four", "404"),
       ("public web tier", "shared, read-only", "403", "200 — the only door")]
tbl = s.shapes.add_table(4, 4, Inches(0.6), Inches(2.5), Inches(12.1), Inches(2.1)).table
for w, col in zip((4.4, 2.5, 2.7, 2.5), range(4)):
    tbl.columns[col].width = Inches(w)
for r, row in enumerate(sec):
    tbl.rows[r].height = Inches(0.5)
    for c, val in enumerate(row):
        cell = tbl.cell(r, c)
        cell.fill.solid()
        cell.fill.fore_color.rgb = C["panel2"] if r == 0 else C["panel"]
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = Inches(0.14)
        run = cell.text_frame.paragraphs[0].add_run()
        run.text = val
        run.font.size = Pt(13)
        run.font.name = B
        run.font.bold = (r == 0) or (c > 0 and val.startswith(("200", "403", "404")))
        run.font.color.rgb = (C["faint"] if r == 0 else C["ink"] if c == 0 else
                              C["red"] if val.startswith(("403", "404")) else
                              C["cy"] if "only door" in val else C["grn"])
for i, (head, body, mono) in enumerate([
        ("The orchestrator cannot read facility data",
         "So \"it only sees the agents' verdicts\" is a property of the platform, not a promise "
         "in a README. It is bound to one store and cannot open the others.", None),
        ("21 checks, run live in the demo", None,
         "bash infra/iam/03_verify_isolation.sh\nbash scripts/demo_denial.sh")]):
    x = 0.6 + i * 6.2
    card(s, x, 4.95, 5.9, 1.55, "panel2")
    text(s, x + 0.35, 5.15, 5.2, 0.3, head, size=14.5, bold=True, color="ink", font=H)
    if body:
        text(s, x + 0.35, 5.50, 5.2, 0.9, body, size=12, spacing=17)
    else:
        text(s, x + 0.35, 5.50, 5.2, 0.6, mono, size=11.5, color="grn", font=M, spacing=17)
        text(s, x + 0.35, 6.08, 5.2, 0.3,
             "Every denial comes from Google Cloud, not from our code.",
             size=11, color="faint")
notes(s, "The Security Rules point is the strongest technical finding here. Say it plainly — "
         "most teams get this wrong.")

# -------------------------------------------------- 8 failure tolerance
s = slide()
title(s, "What happens when an agent hallucinates",
      "The rubric asks this directly: how does the system recover if a worker agent loops or "
      "returns a hallucination?")
card(s, 0.6, 1.90, 5.9, 2.2, "panel2")
text(s, 0.95, 2.08, 5.2, 0.28, "A real verdict the model produced", size=12, color="faint")
text(s, 0.95, 2.40, 5.2, 1.1,
     '"status": "feasible",\n"target_zone": "zone-b",\n"reasoning": "Zone B has ample\n'
     '  headroom for this deployment."', size=11.5, color="ink", font=M, spacing=17)
text(s, 0.95, 3.50, 5.2, 0.3, "zone-b has 561 kW. The request needs 792 kW.",
     size=13, bold=True, color="red")
text(s, 0.95, 3.78, 5.2, 0.28, "Confident, well-formed, and wrong by 231 kW.", size=11.5)
for i, (n, d, col) in enumerate([
        ("Guardrail", "Re-checks every verdict against the same figures the agent was given. "
                      "Not the model checking itself — deterministic code.", "grn"),
        ("Retry with correction", "The violation text goes back in: \"zone-b has 561 kW against "
                                  "a 792 kW request.\" It usually self-corrects on attempt two.", "cy"),
        ("Fail safe, never open", "Retries exhausted → return INFEASIBLE and escalate. A broken "
                                  "agent stops the line rather than approving and hoping.", "amb")]):
    y = 1.90 + i * 1.45
    card(s, 6.8, y, 5.9, 1.28)
    dot(s, 7.05, y + 0.26, 0.34, col)
    text(s, 7.05, y + 0.30, 0.34, 0.28, str(i + 1), size=13, bold=True, color="bg",
         font=H, align=PP_ALIGN.CENTER)
    text(s, 7.55, y + 0.20, 4.9, 0.3, n, size=14, bold=True, color=col)
    text(s, 7.55, y + 0.52, 4.95, 0.7, d, size=11.5, spacing=16)
card(s, 0.6, 4.30, 5.9, 2.0)
text(s, 0.95, 4.50, 5.2, 0.3, "It caught a failure we never anticipated",
     size=14.5, bold=True, color="ink", font=H)
text(s, 0.95, 4.86, 5.2, 1.4,
     "Twice during the build, a gateway bug broke every request in production. Every agent hit "
     "its retry limit, refused, and the system returned \"escalated — needs a human.\"\n\n"
     "It did not crash and it did not approve anything. The fail-safe held against a bug that "
     "was not in the agents at all.", size=12, spacing=17)
notes(s, "Maps one-to-one onto a rubric question. Guardrails block 6 of 6 bad verdicts, "
         "including one hiding an impossible zone in its proposed alternative.")

# ------------------------------------------------ 9 production readiness
s = slide()
title(s, "Deployed, verifiable, and auditable",
      "Demo & Production Readiness — 30% of the score")
for i, (n, d, col) in enumerate([
        ("Live on Google Cloud", "7 Cloud Run services, each under its own service account, "
                                 "scale-to-zero, max-instances capped", "cy"),
        ("Reproducible from scratch", "Every resource has a script — APIs, databases, IAM roles "
                                      "and conditions, VPC, deploy, seed", "grn"),
        ("Auditable by design", "One correlation id threads every model call, guardrail check, "
                                "screening result and routing decision", "vio"),
        ("Signed decision report", "Per-decision PDF showing what each agent SAID beside what it "
                                   "was SHOWN — evidence, not just prose", "amb")]):
    x = 0.6 + (i % 2) * 6.2
    y = 1.78 + (i // 2) * 1.56
    card(s, x, y, 5.9, 1.36)
    dot(s, x + 0.28, y + 0.30, 0.36, col)
    text(s, x + 0.84, y + 0.24, 4.8, 0.3, n, size=14, bold=True, color="ink")
    text(s, x + 0.84, y + 0.56, 4.9, 0.72, d, size=11.5, spacing=16)
card(s, 0.6, 4.95, 12.1, 1.55, "panel2")
text(s, 0.95, 5.12, 5.0, 0.3, "Run these yourself", size=12.5, bold=True, color="ink")
text(s, 0.95, 5.46, 8.6, 0.9,
     "bash infra/iam/03_verify_isolation.sh    14 database isolation checks\n"
     "bash scripts/demo_denial.sh              every layer, live denials\n"
     "python -m scripts.demo_guardrails        6 guardrail assertions, no model calls",
     size=11, color="grn", font=M, spacing=17)
text(s, 9.85, 5.24, 2.6, 0.5, "60 / day", size=27, bold=True, color="cy", font=H)
text(s, 9.85, 5.78, 2.7, 0.5,
     "hard cap on the public demo — about $1.50/day worst case", size=11, spacing=15)
notes(s, "The video shows all three running unedited — that is the 'proof of action' the rubric "
         "asks for.")

# ---------------------------------------------------- 10 GEAP coverage
s = slide()
title(s, "Gemini Enterprise Agent Platform coverage",
      "Six of the seven recommended capabilities, one partial — stated honestly")
for i, (n, d, st, col) in enumerate([
        ("Agent Identity", "7 service accounts, 3 custom least-privilege roles, IAM conditions", "BUILT", "grn"),
        ("Agent Gateway", "routing table, identity checks, audience-scoped tokens, audit log", "BUILT", "grn"),
        ("Model Armor", "screens inter-agent traffic in and out — fails closed", "BUILT", "grn"),
        ("Agent Registry", "contract, version, owner, guardrails and data scope per agent", "BUILT", "grn"),
        ("Memory Bank", "precedent recalled before reconciling, written back after", "BUILT", "grn"),
        ("Agent Observability", "correlation id through every agent, full reasoning chain kept", "BUILT", "grn"),
        ("Agent Runtime", "Cloud Run with per-agent identity — but delivery is synchronous", "PARTIAL", "amb")]):
    y = 1.76 + i * 0.66
    card(s, 0.6, y, 12.1, 0.56, "panel2" if i == 6 else "panel")
    text(s, 0.9, y + 0.15, 2.8, 0.28, n, size=13, bold=True, color="ink")
    text(s, 3.75, y + 0.16, 7.1, 0.28, d, size=11.5)
    text(s, 10.9, y + 0.16, 1.5, 0.28, st, size=11.5, bold=True, color=col,
         align=PP_ALIGN.RIGHT)
text(s, 0.6, 6.44, 12.1, 0.44,
     "Where a capability exists it was built on Google Cloud primitives rather than by adopting "
     "a managed product. The behaviour is real and verifiable — but it is our implementation, "
     "and this deck says so.", size=12, italic=True, color="faint")
notes(s, "Being straight about the partial one buys credibility for the other six.")

# --------------------------------------------------- 11 gaps and next
s = slide()
title(s, "What we would do next", "And what we are not claiming")
card(s, 0.6, 1.8, 5.9, 4.45)
text(s, 0.95, 2.00, 5.2, 0.3, "Next", size=12, color="faint")
for i, (n, d) in enumerate([
        ("Read-only capacity audit",
         "Point it at a DCIM export and report the megawatts an operator has paid for and cannot "
         "use. No integration risk, no trust barrier."),
        ("Durable async execution",
         "Results are already durable; delivery is still synchronous. Cloud Tasks closes the "
         "last GEAP gap."),
        ("A solver under the reasoning",
         "Comparing 792 kW against 3,053 kW is arithmetic. The model earns its place on "
         "interpretation and negotiation, not on the maths.")]):
    y = 2.40 + i * 1.26
    text(s, 0.95, y, 5.2, 0.3, n, size=13.5, bold=True, color="cy")
    text(s, 0.95, y + 0.32, 5.2, 0.86, d, size=11.5, spacing=16)
card(s, 6.8, 1.8, 5.9, 4.45, "panel2")
text(s, 7.15, 2.00, 5.2, 0.3, "Stated plainly", size=12, color="faint")
text(s, 7.15, 2.40, 5.2, 0.3, "The facility is simulated.", size=14, bold=True, color="amb")
text(s, 7.15, 2.80, 5.2, 2.3,
     "The agents, the infrastructure, the isolation and every denial shown are real. The data "
     "center is not — it is generated from published engineering figures, physically consistent, "
     "and reproducible from a fixed seed.\n\n"
     "How these decisions actually get made inside an operations team is something we would need "
     "to learn by shadowing one, not by writing a seed file. That is the honest boundary of what "
     "we built in four weeks.", size=12, spacing=18)
text(s, 7.15, 5.45, 5.2, 0.6,
     "What is real: 21 security checks, 7 deployed services, every decision auditable.",
     size=12, bold=True, color="grn", spacing=17)
notes(s, "Judges trust a team more when it draws its own boundary before they have to.")

# ------------------------------------------------------------- 12 close
s = slide()
text(s, 0.9, 2.25, 11.5, 1.5,
     "Four correct answers still add up to nothing\nunless something checks them together.",
     size=29, bold=True, color="ink", font=H, spacing=42)
text(s, 0.95, 3.95, 11.4, 0.4,
     "GridMind — capacity assurance for high-density data centers", size=16, color="cy")
for i, (k, v) in enumerate([("Live", "gridmind-wuvfpvopoq-uk.a.run.app"),
                            ("Code", "github.com/PRACHIT27/GridMindAI"),
                            ("Track", "The Fortified Enterprise Fleet")]):
    x = 0.9 + i * 4.0
    text(s, x, 4.95, 3.7, 0.28, k, size=11, color="faint")
    text(s, x, 5.22, 3.8, 0.32, v, size=13, bold=True, color="ink")
notes(s, "Close on the one-liner, not a thank-you slide.")

prs.save(OUT)
print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes, {len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
