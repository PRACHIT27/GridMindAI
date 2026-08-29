# GridMind — Capacity Allocation Orchestrator

A multi-agent system that decides whether a high-density GPU workload can
actually be placed in a data center — checking power, cooling, physical space
and cost **jointly**, in real time, and producing an auditable decision.

Built for Google's *All Things Agentic* hackathon, Track 3: **The Fortified
Enterprise Fleet**.

---

## The problem

A new GPU workload needs a home. Today that request is routed **sequentially and
manually** — email, Slack, spreadsheets — through four teams who each approve
against their own constraint in isolation:

| Team | Cares about |
|---|---|
| Power engineering | breaker capacity, circuits, grid conditions |
| Cooling / thermal ops | heat removal, efficiency, water permits |
| Facilities / DCOps | rack space, floor loading, install crews |
| Finance / procurement | budget, cost per GPU-hour, capex |

Nobody checks *joint* feasibility before commitments are made. Four teams can
each say "yes" and still describe **no valid plan** — power approves one zone,
cooling approves another, and the racks arrive to a room that cannot cool them.

The result is stranded capacity, provisioning that takes days instead of
minutes, and no record of *why* anything was decided.

## What GridMind does

Five agents. Four specialists, each seeing only its own slice of the facility,
plus an orchestrator that reconciles their verdicts into one physically
consistent plan — or escalates to a human when it cannot.

**The key move: the orchestrator is not a vote counter.** The four specialists
answer four *different* questions. Tallying them is precisely the failure this
system prevents.

### A real negotiation from this repo

Request: **6 × GB200 NVL72 racks — 132 kW and 1,360 kg each, 792 kW total,
liquid cooling required.**

**Round 1** — each agent decides independently:

| Agent | Verdict | Reason |
|---|---|---|
| Power | `zone-a` | 3,887 kW headroom, 388 spare circuits |
| Cooling | `zone-c` | only liquid zone with enough CDU ports |
| Facilities | `zone-b` | only zone with 6 free liquid-ready racks |
| Cost | `zone-b` | avoids $48k/rack retrofit capex |

Every verdict is **correct on its own axis**. Together they describe nothing.
→ `ZONE_MISMATCH`

**Round 2** — each agent is re-prompted with the others' positions attached.
Facilities volunteers something it had no reason to mention before: *zone-c has
5 liquid-ready racks plus 3 that can be retrofitted in ~14 hours each.*

Power then rules out zone-b (only 560 kW headroom vs 792 kW needed). Cooling
rules out zone-b (2 CDU ports vs 6 needed). Cost recalculates: retrofitting
**one** rack costs $48,000, not the $288,000 it had assumed for six.

**Decision: `zone-c`, 5 ready racks + 1 retrofit, 14-hour delay, $48k capex.**

No single agent could have found that plan.

---

## Architecture

```
   request
      │
      ▼
 ┌──────────┐     ┌──────────────┐     ┌───────────────────────────┐
 │ ORCHEST- │────▶│   GATEWAY    │────▶│  power / cooling /        │
 │  RATOR   │     │ routing +    │     │  facilities / cost agents │
 └────┬─────┘     │ audit log    │     └────────────┬──────────────┘
      │           └──────────────┘                  │
      ▼                                             ▼
  shared-db                            power-db  cooling-db
  (queue, negotiation log,             facilities-db  cost-db
   memory bank)                        (one per agent, IAM-isolated)
```

Six Cloud Run services, six service accounts, five Firestore databases.

### Security is enforced, not described

**Firestore Security Rules do not apply to server-side Admin SDK access.** A
design that relied on them would be silently wrong. GridMind instead uses
**one database per domain** plus **IAM Conditions** scoping each service
account to exactly one `resource.name` — which *is* enforced for client-library
access.

Three independent layers, each demonstrated by a real denial:

1. **Database** — `power-agent-sa` reading `cost-db` → **403 from Firestore**
2. **Network** — the four specialists and the gateway are `--ingress=internal`,
   inside `gridmind-vpc`. From the internet they return **404**: not refused,
   *unreachable*. Google will not even confirm they exist.
3. **Routing** — the gateway checks a routing table and logs every allow/deny

### Network posture

| Service | Ingress | Egress | Reachable from internet |
|---|---|---|---|
| `orchestrator` | `all` | Direct VPC | yes, **with a valid token** (403 without) |
| `gateway` | `internal` | Direct VPC | **no — 404** |
| 4 specialists | `internal` | — | **no — 404** |

Two halves are required and **both** must be in place. `ingress=internal` on
the callee refuses anything not originating in the VPC; **Direct VPC egress**
on the caller routes its outbound traffic through the VPC so it qualifies.
Setting only the first breaks every call with a 403 that looks exactly like an
IAM misconfiguration and is not one.

We use Direct VPC egress rather than a Serverless VPC Access connector: a
connector runs 2+ VMs continuously, roughly $10/month of idle burn against a
$300 credit. The subnet has **Private Google Access** enabled, which is what
lets agents reach Firestore and Vertex AI without Cloud NAT — another running
resource we would otherwise have to pay for.

Out of scope: **VPC Service Controls**. It requires org-level Access Context
Manager rights, which a university-owned project does not delegate to students.

The orchestrator is bound to `shared-db` **only**. It is architecturally
incapable of reading raw power, cooling, facilities or cost data — so "the
orchestrator only sees verdicts" is a property of the platform, not a promise.

```bash
bash infra/iam/03_verify_isolation.sh
```

### Harness engineering, not prompting

Every agent call goes through a structural layer. The model call is **one step
inside** it:

1. **Structured I/O** — schema-validated JSON in and out, never free text
2. **Scoped tools** — Firestore access confined to one database by IAM
3. **Retry + fail-safe** — 3 attempts with backoff, then refuse and escalate.
   Never a guess.
4. **Logging** — structured JSON from the harness, so it cannot be forgotten
5. **Guardrails** — every verdict re-checked against the *same* ground truth
   the agent was given

The guardrails catch real model errors: endorsing a zone 231 kW short,
approving a zone whose switchgear is out, inventing a zone that doesn't exist,
or smuggling an impossible fallback into `proposed_alternative`.

Each agent supplies its own `instructions.py` and `guardrail.py`. Everything
else is shared — `common/` holds no domain knowledge, and an agent folder holds
no plumbing.

### Four-part constraint context

Assembled identically for every agent, **before** the model is called:

| Part | Source |
|---|---|
| `internal_constants` | physics and engineering limits, each tagged `[SOURCED]` or `[MODELED]` |
| `live_data` | the agent's own Firestore database |
| `external_signal` | PJM grid pricing, NOAA weather, crew availability, freight ETA |
| `policy_context` | EAR export controls, EPA/AIM Act, OSHA, Virginia GS-5 rate class, water permits |

Policy is not only restrictive — Virginia's sales-and-use tax exemption is a
*positive* signal the Cost agent uses.

---

## The simulated facility

`iad-dc-01` — Ashburn, Virginia. 600 racks across 4 zones, 32.9 MW IT load,
42.5 MW total draw, PUE 1.29.

Generated **once**, under a fixed seed, in three layers:

1. **Authored constraints** — the blockers (floor ratings, CDU ports,
   liquid-ready counts, switchgear outages). Never randomized, so the demo
   conflict survives any reseed.
2. **Seeded population** — 464 racks dealt with weighted GPU mix and
   triangular density, *constrained by* each zone's cooling type, so an
   air-cooled zone can never be dealt a 132 kW rack.
3. **Derived values** — loads, thermals, PUE and costs computed from those
   racks.

Derivation is not optional: essentially all IT power becomes heat, so a zone's
electrical draw and thermal load are **one fact seen twice**. Authoring them
separately produces a facility that violates conservation of energy. Here,
`Σ(rack kW) × PUE` equals the reported substation load exactly.

Two tests protect the design:

```bash
bash infra/iam/03_verify_isolation.sh   # can an agent REACH another database?
python -m seed.leak_check               # did we COPY another domain's facts in?
```

Both are needed. The second caught a real bug: a shared `notes` field had
copied *"5 liquid-ready racks against 6 needed"* into all four databases,
letting every agent solve the problem alone — while all 14 isolation checks
still passed.

---

## Spin-up instructions

**Prerequisites:** a GCP project with billing enabled, `gcloud` CLI, Python
3.11+, and Git Bash or WSL on Windows.

```bash
# 1. Configure
export PROJECT_ID=your-project-id
# edit infra/env.sh to match

# 2. Enable APIs
bash infra/00_project_and_apis.sh

# 3. Create the five Firestore databases
bash infra/firestore/01_create_databases.sh

# 4. Create six service accounts, two custom roles, conditional bindings
bash infra/iam/01_create_service_accounts.sh
bash infra/iam/02_create_role_and_bind.sh

# 5. Install dependencies
python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt
gcloud auth application-default login

# 6. Seed the facility (runs the leak check first and aborts if it fails)
python -m seed.generate_seed_data

# 7. Deploy six Cloud Run services and wire the invoker chain
bash infra/network/01_create_vpc.sh
bash infra/cloudrun/deploy.sh
```

**Run a negotiation locally:**

```bash
python -m scripts.negotiate --quiet
```

**Run one agent on its own, as its real service account:**

```bash
python -m scripts.try_agent power --impersonate --scenario grid_stress
```

**Call the deployed orchestrator:**

```bash
curl -X POST "$(gcloud run services describe orchestrator --region=us-east4 --format='value(status.url)')/negotiate" -H "Authorization: Bearer $(gcloud auth print-identity-token)" -H "Content-Type: application/json" -d '{"workload_id":"wl-2026-0842","format":"text"}'
```

**Demonstrate the security model:**

```bash
bash scripts/demo_denial.sh
```

---

## Scenarios

External conditions are a dial, so the same request can be shown reaching
different answers for stated reasons:

| Scenario | Effect |
|---|---|
| `normal` | baseline |
| `grid_stress` | PJM emergency event — curtailment becomes a contractual obligation, so Power turns `feasible` → `conditional` |
| `heatwave` | 35–40 °C ambient — no free cooling, PUE climbs, air zones degrade twice as fast as liquid |
| `crew_shortage` | few certified technicians — Facilities adds delay |
| `freight_delay` | port congestion, long lead times — Cost pushes back |

```bash
python -m scripts.negotiate --scenario grid_stress --quiet
```

---

## Stack

- **Gemini 3.5** via Vertex AI — `gemini-3.5-flash-lite` for specialists,
  `gemini-3.5-flash` with a 4,096-token thinking budget for the orchestrator's
  reconciliation. *Note: Gemini 3.5 is served only from Vertex's `global`
  endpoint; regional endpoints 404 for these model ids.*
- **Google GenAI SDK** — structured output with pydantic response schemas
- **Cloud Run** — six services, scale-to-zero, `max-instances=2`
- **Firestore** — five databases, native mode, IAM-Condition isolated
- **Cloud Logging** — structured JSON, correlation-id threaded through every
  agent in a decision

A full 5-agent, multi-round negotiation costs roughly **2–3 cents**.

---

## Repository layout

```
agents/
  common/          shared harness — no domain knowledge lives here
    harness.py         retry, model call, parse, guardrail, fail-safe
    verdict.py         the AgentVerdict contract
    constraint_context.py / constants.py / data_access.py
    external_signals.py / policy.py / obs.py / auth.py
  power/ cooling/ facilities/ cost/
    instructions.py    domain expertise
    guardrail.py       domain safety net
    agent.py           wiring
  orchestrator/
    consistency.py     deterministic joint-feasibility check
    orchestrator.py    the negotiation loop
    decision.py        the decision contract
    report.py          the decision report
  gateway/main.py      routing, identity, audit
seed/
  facility_model.py    the simulated facility
  projections.py       four domain views of it
  leak_check.py        cross-domain leak test
infra/                 all GCP setup, reproducible from scratch
scripts/               local runners and the security demo
```
