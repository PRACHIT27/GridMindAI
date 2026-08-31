"""Generate the GridMind architecture and workflow diagram as SVG.

Drawn in the conventional cloud-architecture style: official product icons as
the primary visual, labels beneath them, every arrow carrying the action it
performs, grouping rectangles for trust boundaries, and a diamond at the branch
point. A reader should be able to trace one request from top to bottom without
reading any prose.

Generated from a script rather than drawn by hand so it cannot drift: the
service, store and identity names here are the same strings the infra scripts
use, so a rename shows up as a diff instead of as a diagram that quietly
describes last week's system.

    python docs/make_architecture_svg.py
"""
from __future__ import annotations

from pathlib import Path

import gcp_icons

OUT = Path(__file__).resolve().parent / "gridmind_architecture.svg"
W, H = 1720, 2150

# Dark canvas, matching the product. Google's product icons are designed on
# light backgrounds but their blues hold up well here, and dark keeps the
# coloured edges legible where a diagram this dense would otherwise grey out.
BG = "#12161c"
INK = "#eef2f7"
DIM = "#98a6b8"
FAINT = "#6b7a8d"
EDGE = "#8595a8"
CHIP = "#1b212a"

CY = "#5b9dff"      # request / control flow
GRN = "#34d399"     # permitted read
RED = "#f87171"     # denied
AMB = "#fbbf24"     # policy decision
VIO = "#a78bfa"     # model inference
TEAL = "#22d3ee"    # telemetry

MARKER = {EDGE: "mEdge", CY: "mCy", GRN: "mGrn", RED: "mRed", AMB: "mAmb",
          VIO: "mVio", TEAL: "mTeal"}

parts: list[str] = []
A = parts.append


def esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def txt(x, y, t, *, size=13, fill=INK, weight="400", anchor="middle",
        family="Inter, Segoe UI, Helvetica, Arial, sans-serif", spacing=None):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    A(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" fill="{fill}" '
      f'font-weight="{weight}" text-anchor="{anchor}"{ls}>{esc(t)}</text>')


def mono(x, y, t, **kw):
    kw.setdefault("size", 10.5)
    kw.setdefault("fill", FAINT)
    kw.setdefault("anchor", "middle")
    txt(x, y, t, family="JetBrains Mono, Consolas, monospace", **kw)


def container(x, y, w, h, label, sub="", *, color=EDGE, dash="8 6", fill="none"):
    A(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" '
      f'stroke="{color}" stroke-width="1.6" stroke-dasharray="{dash}"/>')
    # Labels sit on the RIGHT edge: the request enters top-left, and a label
    # there gets a control-flow arrow drawn straight through it.
    txt(x + w - 22, y + 27, label, size=12, fill=color, weight="700", anchor="end",
        spacing="1.3")
    if sub:
        txt(x + w - 22, y + 46, sub, size=11, fill=FAINT, anchor="end")


def label_chip(cx, ty, lines, *, w, color):
    h = 20 + 14 * (len(lines) - 1)
    A(f'<rect x="{cx - w/2}" y="{ty - 14}" width="{w}" height="{h}" rx="5" '
      f'fill="{CHIP}" opacity="0.94"/>')
    txt(cx, ty, lines[0], size=12.5, weight="700", fill=color)
    for i, s in enumerate(lines[1:]):
        txt(cx, ty + 15 + i * 14, s, size=10.5, fill=DIM)


def node(cx, cy, icon, name, *subs, size=52, color=CY, w=250):
    """An icon with its label beneath — the unit this diagram is built from."""
    A(gcp_icons.use(icon, cx - size / 2, cy - size / 2, size))
    label_chip(cx, cy + size / 2 + 22, [name, *subs], w=w, color=color)
    return cy + size / 2 + 22 + 14 * len(subs)


def edge(pts, label="", label2="", *, color=EDGE, dash=None, lx=None, ly=None, sw=1.7):
    d = " ".join(("M" if i == 0 else "L") + f" {x} {y}" for i, (x, y) in enumerate(pts))
    da = f' stroke-dasharray="{dash}"' if dash else ""
    A(f'<path d="{d}" stroke="{color}" stroke-width="{sw}" fill="none" '
      f'marker-end="url(#{MARKER[color]})" stroke-linejoin="round"{da}/>')
    if label:
        mi = max(1, len(pts) // 2)
        lx = lx if lx is not None else (pts[mi - 1][0] + pts[mi][0]) / 2
        ly = ly if ly is not None else (pts[mi - 1][1] + pts[mi][1]) / 2 - 9
        wid = max(len(label), len(label2)) * 6.05 + 18
        hgt = 19 if not label2 else 32
        A(f'<rect x="{lx - wid/2}" y="{ly - 13}" width="{wid}" height="{hgt}" rx="4" '
          f'fill="{BG}" opacity="0.96"/>')
        txt(lx, ly, label, size=10.5, fill=color)
        if label2:
            txt(lx, ly + 13, label2, size=10.5, fill=color)


def diamond(cx, cy, w, h, l1, l2="", *, color=AMB):
    A(f'<path d="M {cx} {cy-h/2} L {cx+w/2} {cy} L {cx} {cy+h/2} L {cx-w/2} {cy} Z" '
      f'fill="#241d0a" stroke="{color}" stroke-width="1.8"/>')
    txt(cx, cy + (-3 if l2 else 4), l1, size=11.5, fill=color, weight="700")
    if l2:
        txt(cx, cy + 14, l2, size=11.5, fill=color, weight="700")


def terminal(cx, cy, w, h, title, sub, *, color=GRN, fill="#10201a"):
    A(f'<rect x="{cx-w/2}" y="{cy-h/2}" width="{w}" height="{h}" rx="10" '
      f'fill="{fill}" stroke="{color}" stroke-width="1.8"/>')
    txt(cx, cy - 2, title, size=13.5, fill=color, weight="700")
    txt(cx, cy + 18, sub, size=10.5, fill=DIM)


# ----------------------------------------------------------------- document
A(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
  f'viewBox="0 0 {W} {H}" font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif">')
A(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
A('<defs>')
for col, mid in MARKER.items():
    A(f'<marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" '
      f'markerHeight="6.5" orient="auto-start-reverse">'
      f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{col}"/></marker>')
A(gcp_icons.symbols())
A('</defs>')

# ----------------------------------------------------------------- header
txt(46, 46, "GridMind — Capacity Allocation Orchestrator", size=27, weight="700",
    anchor="start")
txt(46, 72, "Request workflow and trust boundaries  ·  project gridmindai-507000  ·  "
            "region us-east4", size=13, fill=DIM, anchor="start")
for i, (col, lab) in enumerate(((CY, "request / control"), (GRN, "permitted read"),
                                (RED, "denied by policy"), (AMB, "policy decision"),
                                (VIO, "model inference"), (TEAL, "telemetry"))):
    x = 1180 + (i // 3) * 250
    y = 38 + (i % 3) * 19
    A(f'<line x1="{x}" y1="{y}" x2="{x+24}" y2="{y}" stroke="{col}" stroke-width="2.6"/>')
    txt(x + 32, y + 4, lab, size=11, fill=DIM, anchor="start")

# ----------------------------------------------------------------- operator
A(f'<circle cx="150" cy="150" r="9" fill="none" stroke="{CY}" stroke-width="2"/>')
A(f'<path d="M 134 178 a 16 16 0 0 1 32 0" fill="none" stroke="{CY}" stroke-width="2"/>')
label_chip(150, 205, ["Operator", "submits a placement request"], w=220, color=CY)

# ----------------------------------------------------------------- cloud
container(40, 258, W - 80, H - 360, "GOOGLE CLOUD",
          "gridmindai-507000  ·  us-east4", color="#4a5768", dash="none")

# public tier
node(330, 350, "cloud-run", "gridmind · web tier",
     "ingress=all — the only public door",
     "web-bff-sa · read-only · no model access", w=340)
edge([(150, 232), (150, 350), (285, 350)], "POST /api/negotiate", color=CY, lx=150, ly=300)
edge([(330, 425), (330, 505)], "allowlist validated — no free text",
     "reaches a model  ·  rate limited", color=CY, lx=560, ly=458)

# ----------------------------------------------------------------- VPC
container(90, 530, W - 180, 1180,
          "gridmind-vpc  ·  10.20.0.0/24  ·  PRIVATE GOOGLE ACCESS  ·  CLOUD NAT",
          "every service below is ingress=internal — from the internet they answer 404, "
          "not 403: unreachable rather than merely refused", color=VIO)

node(330, 640, "cloud-run", "Orchestrator", "orchestrator-agent-sa",
     "gemini-3.5-flash · 4096 thinking", w=270)
node(1430, 640, "firestore", "shared-db", "queue · precedent · audit log",
     "the ONLY store it can open", color=GRN, w=280)
edge([(440, 628), (1300, 628)], "reads the queue  ·  recalls a matching precedent",
     color=GRN, lx=870, ly=616)
edge([(1300, 660), (440, 660)], "writes the full negotiation record", color=GRN,
     lx=870, ly=692)

# gateway + model armor
node(330, 880, "cloud-run", "Agent Gateway", "gateway-agent-sa",
     "the only path to the assessors", w=270)
edge([(330, 720), (330, 838)], "one round — ask all four", color=CY, lx=330, ly=784)
node(700, 880, "armor", "Model Armor", "screens the payload in,",
     "the verdict out · FAILS CLOSED", color=AMB, w=270)
edge([(400, 868), (570, 868)], "screen", color=AMB, lx=485, ly=856)
edge([(570, 896), (400, 896)], "clean", color=AMB, lx=485, ly=928)
node(1430, 880, "iam", "Identity + routing table",
     "verify the signed caller token", "log every allow and deny", color=AMB, w=300)
edge([(1180, 880), (1300, 880)], "", color=AMB)

# assessors
COLS = [(340, "Power", "power-agent-sa", "breaker capacity · circuits", "switchgear outages"),
        (660, "Cooling", "cooling-agent-sa", "per-rack ceiling · CDU ports", "PUE · water permit"),
        (980, "Facilities", "facilities-agent-sa", "free & liquid-ready racks", "floor loading · crew"),
        (1300, "Cost", "cost-agent-sa", "budget · cost per GPU-hour", "retrofit payback · tariff")]
AY = 1150
for i, (cx, name, sa, l1, l2) in enumerate(COLS):
    node(cx, AY, "cloud-run", f"{name} assessor", sa, l1, l2, size=48, w=280)
    edge([(330, 985), (330, 1060), (cx, 1060), (cx, AY - 28)],
         "route to each assessor — four run in parallel, none sees another's answer"
         if i == 0 else "", color=CY, lx=830, ly=1046, sw=1.5)

# stores
DY = 1450
for i, (cx, name, *_) in enumerate(COLS):
    node(cx, DY, "firestore", f"{name.lower()}-db", "this assessor only",
         "every other identity → 403", size=44, color=GRN, w=260)
    # The label goes on the first edge only; repeating it four times would
    # crowd the row without saying anything new.
    edge([(cx, AY + 96), (cx, DY - 26)],
         "Firestore checks the caller's" if i == 0 else "",
         "identity on every request" if i == 0 else "",
         color=GRN, sw=1.5, lx=cx - 118, ly=DY - 96)

# A denied read, drawn rather than described. Without this the "denied by
# policy" key has nothing to point at, and the isolation reads as an assertion.
edge([(408, DY - 44), (520, DY - 12), (556, DY - 4)],
     "403 — refused by the database itself,", "not by any check we wrote",
     color=RED, dash="6 4", sw=1.7, lx=530, ly=DY - 78)
txt(408, DY - 56, "power assessor → cooling-db", size=10, fill=RED, anchor="start")

# Where the identity decision actually happens.
A(gcp_icons.use("iam", 340, DY + 104, 24))
txt(372, DY + 121, "The identity check happens AT THE STORE. Each service account is bound "
                   "by an IAM condition on resource.name, so a cross-domain read is "
                   "refused by Firestore —",
    size=11.5, fill=INK, anchor="start")
txt(372, DY + 139, "before it reaches any of our code. Deleting the application entirely "
                   "would not open it.", size=11.5, fill=GRN, anchor="start")

# model inference
node(1590, 1150, "vertex-ai", "Vertex AI · Gemini 3.5",
     "location=global — regional 404s",
     "used by all four assessors", "and by the orchestrator", color=VIO, w=250)
edge([(1445, AY - 14), (1520, AY - 14)], "inference", color=VIO, dash="5 4", sw=1.3,
     lx=1483, ly=AY - 26)

# ----------------------------------------------------------------- decision
DEC = 1800
diamond(430, DEC, 350, 100, "do the four verdicts describe",
        "ONE deployable plan?")
edge([(340, AY + 96), (200, AY + 96), (200, DEC), (255, DEC)],
     "verdicts, plus the zones", "each assessor rules out", color=CY, lx=200, ly=1600)

edge([(605, DEC - 18), (820, DEC - 18), (820, 1668), (330, 1668), (330, 945)],
     "NO, rounds remain — re-ask each assessor",
     "with the others' positions attached", color=AMB, lx=1035, ly=1782)

terminal(430, 2035, 350, 76, "APPROVED WITH CONDITIONS",
         "one zone · costed trade-off · signed report")
edge([(430, DEC + 50), (430, 1997)], "YES", color=GRN, lx=465, ly=1950)

terminal(1010, 2035, 360, 76, "ESCALATED TO A HUMAN",
         "no zone survives · every option presented", color=AMB, fill="#241d0a")
edge([(605, DEC + 16), (1010, DEC + 16), (1010, 1997)],
     "NO, round limit reached — never a silent choice", color=RED, lx=1045, ly=1900)

# ----------------------------------------------------------------- telemetry
node(1420, 1830, "logging", "Cloud Logging", "one correlation id per decision",
     "every step reconstructable", color=TEAL, w=280)
edge([(1630, 1500), (1660, 1500), (1660, 1790), (1470, 1790)],
     "structured JSON", "from every service", color=TEAL, dash="5 4", sw=1.3,
     lx=1660, ly=1640)

# ----------------------------------------------------------------- footer
A(f'<line x1="46" y1="{H-74}" x2="{W-46}" y2="{H-74}" stroke="#2a323d" stroke-width="1"/>')
txt(46, H - 48, "Every refusal in this diagram is enforced by Google Cloud — an IAM "
                "condition on each store, Cloud Run invoker policy, and VPC ingress — "
                "not by application code that could be edited away.",
    size=12.5, fill=INK, anchor="start")
mono(46, H - 24, "verify:   bash infra/iam/03_verify_isolation.sh       "
                 "bash scripts/demo_denial.sh       python -m scripts.demo_guardrails",
     size=11, anchor="start")

A('</svg>')
OUT.write_text("\n".join(parts), encoding="utf-8")
print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes)")
