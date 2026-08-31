"""Generate the GridMind architecture and workflow diagram as SVG.

Written as a script rather than drawn by hand so it stays correct: the service
names, database names and IAM conditions here are the same strings the infra
scripts use, so a rename shows up as a diff rather than as a diagram that
quietly describes last week's system.

Outputs docs/gridmind_architecture.svg (and a PNG if cairosvg is available).
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "gridmind_architecture.svg"

W, H = 1840, 1760

# Light theme: architecture diagrams end up in documents and slides far more
# often than on a dark dashboard, and thin strokes survive printing better.
INK = "#101720"
DIM = "#5f6f80"
FAINT = "#8b9aab"
LINE = "#c9d4e0"
PAPER = "#ffffff"
BAND = "#f4f7fb"
BAND2 = "#eef3f9"

CY = "#1a73e8"     # control / request flow
GRN = "#0f9d58"    # allowed / data reads
RED = "#d93025"    # denied
AMB = "#f29900"    # policy / screening
VIO = "#7b3ff2"    # model calls
TEAL = "#00838f"   # observability

parts: list[str] = []
A = parts.append


def esc(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def box(x, y, w, h, *, fill=PAPER, stroke=LINE, rx=10, sw=1.4, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    A(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" '
      f'stroke="{stroke}" stroke-width="{sw}"{d}/>')


def txt(x, y, t, *, size=14, fill=INK, weight="400", anchor="start",
        family="Inter, Segoe UI, Helvetica, Arial, sans-serif", spacing=None):
    ls = f' letter-spacing="{spacing}"' if spacing else ""
    A(f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
      f'fill="{fill}" font-weight="{weight}" text-anchor="{anchor}"{ls}>{esc(t)}</text>')


def mono(x, y, t, *, size=12, fill=DIM, weight="400", anchor="start"):
    txt(x, y, t, size=size, fill=fill, weight=weight, anchor=anchor,
        family="JetBrains Mono, Consolas, monospace")


def arrow(x1, y1, x2, y2, *, color=CY, sw=2.0, dash=None, marker="arrow"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    A(f'<path d="M {x1} {y1} L {x2} {y2}" stroke="{color}" stroke-width="{sw}" '
      f'fill="none" marker-end="url(#{marker})"{d}/>')


def elbow(x1, y1, x2, y2, *, color=CY, sw=2.0, dash=None, marker="arrow", mid=None):
    """Right-angled connector; mid is the x (or y) of the bend."""
    m = mid if mid is not None else (y1 + y2) / 2
    d = f' stroke-dasharray="{dash}"' if dash else ""
    A(f'<path d="M {x1} {y1} V {m} H {x2} V {y2}" stroke="{color}" stroke-width="{sw}" '
      f'fill="none" marker-end="url(#{marker})"{d}/>')


def step(x, y, n, *, color=CY, r=13):
    A(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')
    txt(x, y + 4.5, str(n), size=13, fill="#fff", weight="700", anchor="middle")


def cylinder(x, y, w, h, *, fill=PAPER, stroke=LINE):
    ry = 9
    A(f'<path d="M {x} {y+ry} A {w/2} {ry} 0 0 1 {x+w} {y+ry} V {y+h-ry} '
      f'A {w/2} {ry} 0 0 1 {x} {y+h-ry} Z" fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
    A(f'<path d="M {x} {y+ry} A {w/2} {ry} 0 0 0 {x+w} {y+ry}" fill="none" '
      f'stroke="{stroke}" stroke-width="1.4"/>')


# ---------------------------------------------------------------- defs
A(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
  f'viewBox="0 0 {W} {H}" font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif">')
A(f'<rect width="{W}" height="{H}" fill="{PAPER}"/>')
A('<defs>')
for name, col in (("arrow", CY), ("arrowGrn", GRN), ("arrowRed", RED),
                  ("arrowAmb", AMB), ("arrowVio", VIO), ("arrowTeal", TEAL),
                  ("arrowDim", FAINT)):
    A(f'<marker id="{name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
      f'markerHeight="7" orient="auto-start-reverse">'
      f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{col}"/></marker>')
A('</defs>')

# ---------------------------------------------------------------- title
txt(50, 52, "GridMind — Capacity Allocation Orchestrator", size=30, weight="700")
txt(50, 78, "Architecture and request workflow  ·  Google Cloud project gridmindai-507000  ·  "
            "region us-east4", size=14, fill=DIM)

# legend
lx = 1180
for i, (col, label) in enumerate((
        (CY, "request / control flow"), (GRN, "permitted data read"),
        (RED, "denied by policy"), (AMB, "content screening"),
        (VIO, "model inference"), (TEAL, "telemetry"))):
    y = 40 + (i % 3) * 20
    x = lx + (i // 3) * 230
    A(f'<line x1="{x}" y1="{y}" x2="{x+26}" y2="{y}" stroke="{col}" stroke-width="2.6"/>')
    txt(x + 34, y + 4, label, size=12, fill=DIM)

# ================================================================ PUBLIC
PY0 = 108
box(40, PY0, W - 80, 148, fill=BAND, stroke=LINE, rx=12)
txt(60, PY0 + 26, "PUBLIC INTERNET", size=11, fill=FAINT, weight="700", spacing="1.6")

# browser
box(70, PY0 + 42, 210, 84, fill=PAPER)
txt(85, PY0 + 70, "Operator / browser", size=15, weight="600")
txt(85, PY0 + 92, "submits a placement request", size=12, fill=DIM)
txt(85, PY0 + 110, "or reviews past assessments", size=12, fill=DIM)

# web tier
box(360, PY0 + 30, 470, 108, fill=PAPER, stroke=CY, sw=2)
txt(378, PY0 + 56, "gridmind  ·  public web tier", size=15, weight="700", fill=CY)
mono(378, PY0 + 76, "Cloud Run · web-bff-sa · ingress=all")
txt(378, PY0 + 96, "• allowlist validation — no free text reaches a model", size=11.5, fill=DIM)
txt(378, PY0 + 113, "• rate limit 1/90s per IP, 60/day  • max-instances=1", size=11.5, fill=DIM)
txt(378, PY0 + 130, "• read-only identity · no model permission", size=11.5, fill=DIM)

arrow(282, PY0 + 84, 356, PY0 + 84)
step(320, PY0 + 66, 1)

# least-privilege callout
box(870, PY0 + 30, 400, 108, fill="#fff8e6", stroke=AMB, rx=10, sw=1.4)
txt(888, PY0 + 54, "The most exposed service holds the least", size=13, weight="700", fill="#8a5a00")
txt(888, PY0 + 74, "web-bff-sa can read one shared store, read-only.", size=11.5, fill="#6d4c00")
txt(888, PY0 + 91, "No writes anywhere. No facility data. No model", size=11.5, fill="#6d4c00")
txt(888, PY0 + 108, "access — so it cannot be turned into spend.", size=11.5, fill="#6d4c00")
txt(888, PY0 + 128, "Everything below is unreachable from here (404).", size=11.5,
    fill="#8a5a00", weight="600")

# ================================================================ VPC
VY0 = 286
VH = 742
box(40, VY0, W - 80, VH, fill="#fbfdff", stroke=CY, rx=14, sw=2, dash="9 6")
txt(60, VY0 + 26, "PRIVATE NETWORK  —  gridmind-vpc  ·  subnet 10.20.0.0/24  ·  "
                  "Private Google Access  ·  Cloud NAT for egress",
    size=11, fill=CY, weight="700", spacing="1.2")
txt(60, VY0 + 46, "All services below are ingress=internal: not merely refused from the "
                  "internet, but unacknowledged (HTTP 404).", size=12, fill=DIM)

# ---- orchestrator
OY = VY0 + 62
box(70, OY, 700, 210, fill=PAPER, stroke=CY, sw=2)
txt(90, OY + 28, "Orchestrator", size=17, weight="700", fill=CY)
mono(90, OY + 48, "Cloud Run · orchestrator-agent-sa · gemini-3.5-flash (4096 thinking)")

# negotiation loop inside
box(90, OY + 62, 660, 132, fill=BAND2, stroke=LINE, rx=8)
txt(106, OY + 84, "NEGOTIATION LOOP  ·  bounded to 3 rounds", size=11, fill=DIM,
    weight="700", spacing="1.2")
txt(106, OY + 106, "Round 1  ask all four independently — no agent sees another's answer",
    size=12.5)
txt(106, OY + 126, "Joint check  do the four verdicts describe ONE deployable plan? "
                   "(deterministic, not a model call)", size=12.5)
txt(106, OY + 146, "Round 2-3  re-prompt each agent with the others' positions attached",
    size=12.5)
txt(106, OY + 168, "Resolve → approve / approve-with-conditions   ·   no surviving zone → "
                   "ESCALATE to a human", size=12.5, weight="600")

arrow(595, PY0 + 138, 420, OY - 4, color=CY)
step(505, OY - 26, 2)

# ---- gateway
GY = OY + 232
box(70, GY, 700, 150, fill=PAPER, stroke=AMB, sw=2)
txt(90, GY + 28, "Agent Gateway", size=17, weight="700", fill="#8a5a00")
mono(90, GY + 48, "Cloud Run · gateway-agent-sa · the only path to the specialists")
txt(90, GY + 74, "1  verify caller identity from its signed token", size=12.5)
txt(90, GY + 94, "2  check the routing table — which caller may reach which assessor",
    size=12.5)
txt(90, GY + 114, "3  MODEL ARMOR screens the payload in, and the verdict out", size=12.5,
    weight="600", fill="#8a5a00")
txt(90, GY + 134, "4  log every allow and deny  ·  fails CLOSED if screening is unreachable",
    size=12.5)

arrow(300, OY + 210, 300, GY - 4, color=CY)
step(300, GY - 26, 3)
arrow(560, GY - 4, 560, OY + 210, color=GRN)
txt(575, GY - 14, "verdicts back", size=11, fill=GRN)

# Model Armor callout
box(800, GY - 10, 470, 170, fill="#fff8e6", stroke=AMB, rx=10)
txt(818, GY + 14, "Model Armor — content screening", size=14, weight="700", fill="#8a5a00")
txt(818, GY + 36, "Catches what the output guardrails cannot: the", size=11.5, fill="#6d4c00")
txt(818, GY + 53, "guardrails check whether an answer is physically", size=11.5, fill="#6d4c00")
txt(818, GY + 70, "possible, and are blind to how it was reached.", size=11.5, fill="#6d4c00")
txt(818, GY + 94, "prompt injection        blocked", size=12, fill="#6d4c00", weight="600")
txt(818, GY + 112, "instruction override    blocked", size=12, fill="#6d4c00", weight="600")
txt(818, GY + 130, "sensitive data (PII)    blocked", size=12, fill="#6d4c00", weight="600")
txt(818, GY + 150, "benign engineering text passes", size=12, fill="#0f7a52", weight="600")

# ---- specialists
SY = GY + 172
AGENTS = [
    ("Power", "power-agent-sa", "breaker capacity, spare circuits,\nswitchgear outages, grid events"),
    ("Cooling", "cooling-agent-sa", "per-rack ceiling, thermal headroom,\nCDU ports, PUE, water permit"),
    ("Facilities", "facilities-agent-sa", "free racks, liquid-ready racks,\nfloor loading, crew and retrofit"),
    ("Cost", "cost-agent-sa", "budget, cost per GPU-hour,\nretrofit payback, tariff rules"),
]
bw, gap = 288, 18
for i, (name, sa, what) in enumerate(AGENTS):
    x = 70 + i * (bw + gap)
    box(x, SY, bw, 168, fill=PAPER, stroke=GRN, sw=1.8)
    txt(x + 16, SY + 26, f"{name} assessor", size=15, weight="700", fill="#0b6b3a")
    mono(x + 16, SY + 45, sa, size=10.5)
    mono(x + 16, SY + 62, "gemini-3.5-flash-lite", size=10.5)
    for j, ln in enumerate(what.split("\n")):
        txt(x + 16, SY + 86 + j * 17, ln, size=11.5, fill=DIM)
    box(x + 16, SY + 122, bw - 32, 32, fill=BAND2, stroke=LINE, rx=6)
    txt(x + 26, SY + 143, "harness: schema · retry · guardrail · log", size=10.5, fill=DIM)
    arrow(x + bw / 2, GY + 150, x + bw / 2, SY - 4, color=CY, sw=1.6)
step(70 + bw / 2, SY - 26, 4)

# ================================================================ DATA
DY = VY0 + VH + 36
box(40, DY, W - 80, 190, fill=BAND, stroke=LINE, rx=12)
txt(60, DY + 26, "DATA LAYER  —  one store per domain, isolated by IAM condition on "
                 "resource.name", size=11, fill=FAINT, weight="700", spacing="1.4")
txt(60, DY + 46, "Firestore Security Rules do NOT apply to server-side Admin SDK access, so "
                 "per-collection rules would enforce nothing. The database is the smallest "
                 "unit IAM can actually scope.", size=12, fill=DIM)

DBS = [("power-db", "Power assessor only"), ("cooling-db", "Cooling assessor only"),
       ("facilities-db", "Facilities assessor only"), ("cost-db", "Cost assessor only"),
       ("shared-db", "Orchestrator + web (read-only)")]
dw = 300
for i, (db, who) in enumerate(DBS):
    x = 70 + i * (dw + 12)
    cylinder(x, DY + 66, dw - 20, 96, fill=PAPER, stroke=GRN if i < 4 else CY)
    mono(x + 18, DY + 100, db, size=13, fill=INK, weight="700")
    txt(x + 18, DY + 122, who, size=11, fill=DIM)
    txt(x + 18, DY + 142, "all other identities → 403", size=10.5, fill=RED, weight="600")
    if i < 4:
        ax = 70 + i * (bw + gap) + bw / 2
        arrow(ax, SY + 168, x + (dw - 20) / 2, DY + 66, color=GRN, sw=1.6, marker="arrowGrn")
step(70 + bw / 2 - 30, DY + 44, 5, color=GRN)

# shared-db is the orchestrator's only store
shared_cx = 70 + 4 * (dw + 12) + (dw - 20) / 2
elbow(770, OY + 150, shared_cx, DY + 66, color=CY, sw=1.6, dash="6 4", mid=1268)
txt(shared_cx - 130, DY + 46, "queue · precedent · audit log", size=11, fill=CY,
    weight="600")

# ================================================================ RIGHT COLUMN
RX = 1300
# Vertex AI
box(RX, OY, 470, 132, fill=PAPER, stroke=VIO, sw=1.8)
txt(RX + 18, OY + 28, "Vertex AI  ·  Gemini 3.5", size=16, weight="700", fill="#5a2bc0")
mono(RX + 18, OY + 48, "location=global (regional endpoints 404)", size=11)
txt(RX + 18, OY + 72, "flash-lite for the four assessors — one narrow judgement each",
    size=11.5, fill=DIM)
txt(RX + 18, OY + 90, "flash + 4096 thinking for reconciliation, the hard step", size=11.5,
    fill=DIM)
txt(RX + 18, OY + 114, "Callers hold one permission: endpoints.predict", size=11.5,
    fill="#5a2bc0", weight="600")
for i in range(4):
    ax = 70 + i * (bw + gap) + bw - 20
    elbow(ax, SY + 20, RX - 4, OY + 100, color=VIO, sw=1.3, dash="5 4",
          marker="arrowVio", mid=SY - 14)
arrow(770, OY + 60, RX - 4, OY + 60, color=VIO, sw=1.4, dash="5 4", marker="arrowVio")

# Observability
box(RX, GY + 176, 470, 218, fill=PAPER, stroke=TEAL, sw=1.8)
txt(RX + 18, GY + 204, "Cloud Logging  ·  audit trail", size=16, weight="700", fill="#00646e")
txt(RX + 18, GY + 226, "Every service writes structured JSON to stdout. One correlation",
    size=11.5, fill=DIM)
txt(RX + 18, GY + 242, "id threads every step of a single decision:", size=11.5, fill=DIM)
mono(RX + 18, GY + 264, "constraint_context_built", size=11)
mono(RX + 18, GY + 282, "model_call  · tokens, duration", size=11)
mono(RX + 18, GY + 300, "guardrail_violation  · retry", size=11)
mono(RX + 18, GY + 318, "model_armor_screened", size=11)
mono(RX + 18, GY + 336, "gateway_allowed / gateway_denied", size=11)
mono(RX + 18, GY + 354, "verdict_returned · round_complete", size=11)
txt(RX + 18, GY + 378, "A whole multi-agent decision is reconstructable from one filter.",
    size=11.5, fill="#00646e", weight="600")
# One aggregated line: every service emits, and drawing four crossing dashes
# to say so buries the actual request flow underneath them.
# A single short connector in the gap between the assessors and the log panel.
# The earlier version put a labelled box at x=1055 which landed on top of the
# Cost assessor card -- the panel's own first line carries the same point.
arrow(1280, SY + 40, RX - 4, SY + 40, color=TEAL, sw=1.8, dash="5 4", marker="arrowTeal")

# ================================================================ BOTTOM: harness + workflow
BY = DY + 214
box(40, BY, 880, 330, fill=PAPER, stroke=LINE, rx=12)
txt(62, BY + 30, "INSIDE ONE ASSESSOR — the harness", size=12, fill=FAINT, weight="700",
    spacing="1.4")
txt(62, BY + 52, "The model call is one step inside this, not the agent itself. "
                 "Swap the model and all five properties survive.", size=12, fill=DIM)

LAYERS = [
    ("1  Constraint context", "assembled BEFORE any model call: engineering constants · "
                              "the agent's own live data ·", "external signal (grid, weather, "
                              "crew, freight) · applicable federal and state policy"),
    ("2  Structured I/O", "schema-constrained request and reply — never free text; validated "
                          "again after return,", "because 'matches the schema' and 'is "
                          "semantically valid' are different claims"),
    ("3  Guardrail", "the verdict is re-checked against the SAME figures the agent was "
                     "handed — catching a zone", "231 kW short, a switchgear outage ignored, "
                     "or an invented zone"),
    ("4  Retry with correction", "on violation the failure text is fed back, so the next "
                                 "attempt is told exactly what", "it got wrong. Three "
                                 "attempts, exponential backoff"),
    ("5  Fail safe", "retries exhausted → return INFEASIBLE and escalate. Never a guess: a "
                     "broken assessor", "stops the line rather than approving and hoping"),
]
for i, (h, l1, l2) in enumerate(LAYERS):
    y = BY + 74 + i * 48
    box(62, y, 836, 42, fill=BAND2 if i % 2 == 0 else PAPER, stroke=LINE, rx=6, sw=1)
    txt(76, y + 18, h, size=12.5, weight="700")
    txt(280, y + 16, l1, size=11, fill=DIM)
    txt(280, y + 32, l2, size=11, fill=DIM)

# workflow steps
box(946, BY, W - 986, 330, fill=PAPER, stroke=LINE, rx=12)
txt(968, BY + 30, "REQUEST WORKFLOW", size=12, fill=FAINT, weight="700", spacing="1.4")
STEPS = [
    (1, CY, "Request arrives", "Validated against an allowlist and rate limited. No free "
                               "text is forwarded to a model."),
    (2, CY, "Orchestrator opens a round", "Reads the queue from its one permitted store. It "
                                          "holds no facility data at all."),
    (3, AMB, "Gateway screens and routes", "Identity checked, routing table applied, payload "
                                           "screened by Model Armor, decision logged."),
    (4, CY, "Four assessors run in parallel", "Each answers one question, reading only its "
                                              "own store. Independent by construction."),
    (5, GRN, "Each reads its own store only", "Cross-domain reads return 403 from the "
                                              "database itself, not from our code."),
    (6, CY, "Joint feasibility check", "Deterministic: do the four verdicts describe ONE "
                                       "plan? Not 'do they agree'."),
    (7, CY, "Conflict → another round", "Each assessor is re-prompted with the others' "
                                        "positions. Bounded to three rounds."),
    (8, GRN, "Decision, or escalation", "Approve with conditions and a costed trade-off — or "
                                        "hand a human every option, never a silent choice."),
]
for i, (n, col, head, body) in enumerate(STEPS):
    y = BY + 66 + i * 33
    step(978, y, n, color=col, r=11)
    txt(1000, y + 5, head, size=12.5, weight="700")
    txt(1000, y + 21, body, size=10.8, fill=DIM)

# footer
FY = BY + 330 + 34
A(f'<line x1="40" y1="{FY - 18}" x2="{W - 40}" y2="{FY - 18}" stroke="{LINE}" stroke-width="1"/>')
txt(50, FY + 4, "Every refusal in this diagram is enforced by Google Cloud — IAM conditions, "
                "Cloud Run invoker policy and VPC ingress — not by application code that could "
                "be edited away.", size=12.5, fill=INK)
mono(50, FY + 26, "verify:  bash infra/iam/03_verify_isolation.sh    ·    "
                  "bash scripts/demo_denial.sh    ·    python -m scripts.demo_guardrails",
     size=11, fill=FAINT)

A('</svg>')
OUT.write_text("\n".join(parts), encoding="utf-8")
print(f"wrote {OUT}  ({OUT.stat().st_size:,} bytes)")

# Optional PNG for slide decks / Devpost.
try:
    import cairosvg  # type: ignore
    png = OUT.with_suffix(".png")
    cairosvg.svg2png(url=str(OUT), write_to=str(png), scale=2)
    print(f"wrote {png}")
except Exception:
    print("(cairosvg not installed — SVG only; most tools accept SVG directly)")
