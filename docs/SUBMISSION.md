# Devpost submission

**Track:** The Fortified Enterprise Fleet
**Live:** https://gridmind-wuvfpvopoq-uk.a.run.app
**Repo:** https://github.com/PRACHIT27/GridMindAI

---

## Elevator pitch (one line)

Four AI agents that each check one constraint on a data center capacity request,
and a fifth that reconciles their conflicting answers into a plan that actually
holds — with the isolation between them enforced by Google Cloud IAM rather than
by application code.

---

## Inspiration

Modern AI data centers run at 100–750 MW, and every GPU generation pushes rack
density higher. When a new high-density workload needs a home, four teams have
to sign off — power engineering, cooling, facilities, and finance — and today
that happens sequentially, over email and spreadsheets, over days.

The failure mode that got our attention is not that any team gets it wrong. It's
that **all four can be right and still describe a plan that cannot be built.**
Power approves the room with the most electrical headroom; cooling approves the
only room with liquid capacity; facilities approves the room with free racks.
Three correct answers, three different rooms, no valid plan — and nobody owns
the joint check. The industry term for what this leaves behind is *stranded
capacity*: megawatts you have paid for and cannot use.

## What it does

A request arrives — say six racks of GB200 NVL72, 132 kW and 1,360 kg each.

Four specialist agents assess it in parallel, each reading only its own data:

- **Power** — breaker headroom, spare circuits, switchgear outages, grid events
- **Cooling** — per-rack thermal ceiling, CDU ports, PUE, water discharge permit
- **Facilities** — free and liquid-ready racks, floor load rating, crew and retrofit time
- **Cost** — operating budget, cost per GPU-hour, retrofit payback, tariff rules

In our demo facility, round one produces exactly the failure described above:
power says zone A, cooling says zone C, facilities and cost say zone B.

The orchestrator does **not** count votes. It asks whether the four verdicts
describe one physically deployable plan. They don't — so it re-prompts each
agent with the others' positions attached. Facilities then volunteers something
it had no reason to mention before: zone C has five liquid-ready racks and three
more that can be plumbed in about fourteen hours each. Cost recalculates —
retrofitting *one* rack costs $48,000, not the $288,000 it had assumed for six.

**Decision: zone C, five ready racks plus one retrofit, fourteen hours' delay.**
No single agent could have found it.

Each agent also reports the zones its own axis **excludes**. Intersecting those
four lists leaves exactly one surviving zone — one that, in round one, not a
single agent had endorsed. That intersection is the thing no individual team can
compute from inside its silo, and computing it is the point of the system.

## How we built it

**Gemini 3.5** on Vertex AI (`flash-lite` for the four specialists, `flash` with
a 4,096-token thinking budget for reconciliation), the **Google GenAI SDK**,
**Cloud Run** (seven services, seven service accounts), and **Firestore** (five
databases).

### Security enforced, not described

The load-bearing finding: **Firestore Security Rules are not evaluated for
server-side Admin SDK access.** They apply only to client SDK and Firebase Auth
traffic. A design that scoped agents with per-collection rules would have
enforced *nothing at all* while looking correct in a diagram.

So each domain gets its own database, and each service account is bound through
an **IAM Condition** on `resource.name` — which *is* enforced for client-library
access. Verified by live API calls with real agent credentials:

| Identity | Own store | Other stores | From the internet |
|---|---|---|---|
| four specialists | 200 | **403** | **404** |
| orchestrator | shared only | **403** (all four) | **404** |
| public web tier | shared, read-only | **403** | 200 |

The orchestrator is *incapable* of reading facility data, so "it only sees the
agents' verdicts" is a property of the platform rather than a promise.

Note the shape of that last row: **the only internet-facing service holds the
least privilege** — read-only, one store, and no permission to call a model at
all. Someone who fully owns the public container gets a request queue and a
decision log, not the facility, and no way to spend the inference budget.

**Model Armor** screens inter-agent traffic at the gateway, inbound and outbound,
and fails closed. **Cloud Logging** threads one correlation id through every
model call, guardrail check, screening result and routing decision, so an entire
multi-agent decision is reconstructable from a single filter.

### Harness engineering

The model call is one step inside a structural layer, not the agent itself:
schema-validated I/O, IAM-scoped tool access, retry that feeds the violation
text back as correction, guardrails that re-check every verdict against the same
figures the agent was handed, and — when retries are exhausted — a refusal.
**It fails safe, never open.** An agent that cannot reason reliably about a 90 MW
electrical envelope stops the line rather than approving and hoping.

## Challenges we ran into

**Gemini 3.5 is only served from Vertex's `global` endpoint.** Regional endpoints
404 for those model ids, and `gemini-2.0-flash` is retired. Pointing at a region
would have silently dropped us to a non-compliant model.

**Thinking tokens share the output budget.** A 4,096 thinking budget inside a
4,096 ceiling returns JSON truncated mid-string.

**A lazy-singleton race.** Four concurrent agents each built their own client;
the garbage-collected losers closed the shared HTTP transport, and three of four
agents failed in round one for no visible reason.

**A data leak that all our security tests passed.** A single shared `notes` field
had copied the sentence *"5 liquid-ready racks against 6 needed"* into all four
databases. Every agent could solve the problem alone — the multi-agent premise
had quietly collapsed while all 14 isolation checks stayed green. Airtight
permissions plus a leaky payload is not isolation. A second test now scans every
value written to each store.

**Our own eval suite lied to us.** It ran in-process and bypassed the gateway, so
it reported 12/12 green while production was completely broken — twice. We
removed it rather than keep a suite that manufactures confidence during an
outage.

## What we learned

That the most dangerous failures were the ones our tests were structurally unable
to see. Both production outages presented identically — the system returned
`ESCALATED` — because the fail-safe worked perfectly. Correct behaviour made a
missing network route look like an agent decision.

And that an LLM is the wrong tool for part of this. Comparing 792 kW against
3,053 kW of headroom is arithmetic; a constraint solver would be faster, cheaper
and provably optimal. Where the model genuinely earns its place is interpreting
constraints that vary between facilities, negotiating trade-offs, and explaining
a decision to the team it affects. Our guardrails are, in effect, already a small
deterministic solver checking the model's work — and that split is the right
shape for a real product.

## What's next

- **Read-only stranded-capacity audit** as the entry point: point it at a DCIM
  export and report the megawatts an operator has paid for and cannot use. No
  integration risk, no trust barrier, and it earns the right to be in the
  decision loop later.
- **Durable async execution** — the last partial GEAP capability. Results are
  already durable; delivery is still synchronous.
- **Real facility data.** The physics here is sourced from published figures, but
  how these decisions actually get made is something we would need to learn by
  shadowing an operations team, not by inventing a seed file.

## Try it

```bash
bash infra/iam/03_verify_isolation.sh   # 14 database isolation checks
bash scripts/demo_denial.sh             # all layers, live denials
python -m scripts.demo_guardrails       # 6 guardrail assertions, no model calls
```

*The facility `iad-dc-01` is simulated. The agents, the infrastructure and every
denial shown are real.*
