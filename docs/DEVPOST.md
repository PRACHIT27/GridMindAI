# Devpost form — paste-ready

**Track:** The Fortified Enterprise Fleet
**Live:** https://gridmind-wuvfpvopoq-uk.a.run.app
**Repo:** https://github.com/PRACHIT27/GridMindAI

---

## Elevator pitch (200 char limit)

Four correct answers can still add up to a plan nobody can build. GridMind checks
power, cooling, space and budget together, and returns one that holds.

---

## Inspiration

Modern AI data centers run at 100 to 750 MW, and every GPU generation pushes rack
density higher. When a new high-density workload needs a home, four teams have to
sign off: power engineering, cooling, facilities and finance. Today that happens
one team at a time, over email and spreadsheets, over several days.

The failure mode that got our attention is not that a team gets it wrong. It is
that all four can be right and still describe a plan that cannot be built. Power
approves the room with the most electrical headroom. Cooling approves the only
room that can remove the heat. Facilities approves the room with free racks.
Three correct answers, three different rooms, no valid plan, and nobody owns the
joint check.

The industry has a name for what that leaves behind: stranded capacity, meaning
megawatts a site has paid for and cannot use.

## What it does

A request arrives: six racks of GB200 NVL72, 132 kW and 1,360 kg each.

Four specialist agents assess it in parallel, each reading only its own database.

- **Power** — breaker headroom, spare circuits, switchgear outages, grid events
- **Cooling** — per-rack thermal ceiling, CDU ports, PUE, water discharge permit
- **Facilities** — free and liquid-ready racks, floor load rating, crew and retrofit time
- **Cost** — operating budget, cost per GPU-hour, retrofit payback, tariff rules

In our demo facility, round one produces exactly the failure above: power says
zone A, cooling says zone C, facilities and cost say zone B.

The orchestrator does not count votes. It asks whether the four verdicts describe
one physically deployable plan. They do not, so it opens a negotiation round and
re-prompts each agent with the others' positions attached. Facilities then
volunteers something it had no reason to mention before: zone C has five
liquid-ready racks and more that can be plumbed in about fourteen hours each.
Cost recalculates, because retrofitting one rack costs $48,000, not the $288,000
it had assumed for six.

**Decision: zone C, five ready racks plus one retrofit, fourteen hours of delay.**

Each agent also reports the zones its own axis excludes. Intersecting those four
lists leaves exactly one surviving zone, and in round one not a single agent had
endorsed it. That intersection is the thing no individual team can compute from
inside its silo, and computing it is the point of the system.

You get back a target zone or a refusal, the plan to get there, every agent's
verdict beside the evidence it was actually shown, and a PDF decision report.

## How we built it

**Gemini 3.5** on Vertex AI, with `flash-lite` for the four specialists and
`flash` with a 4,096-token thinking budget for reconciliation. The **Google GenAI
SDK** with Pydantic response schemas for structured output. **Cloud Run** for
seven services under seven service accounts, and **Firestore** for five separate
databases.

### Security that is enforced, not described

The load-bearing finding: **Firestore Security Rules are not evaluated for
server-side Admin SDK access.** They apply only to client SDK and Firebase Auth
traffic. A design that scoped agents with per-collection rules would have enforced
nothing at all, while looking correct in a diagram.

So each domain gets its own database, and each service account is bound through an
**IAM Condition** on `resource.name`, which is enforced for client-library access.
Verified by live API calls with real agent credentials:

| Identity | Own store | Other stores | From the internet |
|---|---|---|---|
| four specialists | 200 | **403** | **404** |
| orchestrator | shared only | **403** (all four) | **404** |
| public web tier | shared, read-only | **403** | 200 |

The orchestrator is incapable of reading facility data, so "it only sees the
agents' verdicts" is a property of the platform rather than a promise.

Note the shape of that last row: the only internet-facing service holds the least
privilege. Read-only, one store, and no permission to call a model at all. Someone
who fully owns the public container gets a request queue and a decision log, not
the facility, and no way to spend the inference budget.

**Model Armor** screens inter-agent traffic at the gateway in both directions and
fails closed. **Cloud Logging** threads one correlation id through every model
call, guardrail check, screening result and routing decision, so a whole
multi-agent decision is reconstructable from a single filter.

### Harness engineering

The model call is one step inside a structural layer, not the agent itself.
Schema-validated I/O, IAM-scoped tool access, retry that feeds the violation text
back as correction, and guardrails that re-check every verdict against the same
figures the agent was handed, including the alternatives it proposes.

Both loops are bounded and neither can spin. Each agent call retries at most three
times, and negotiation runs at most three rounds. When either is exhausted the
system refuses. **It fails safe, never open.** An agent that cannot reason reliably
about a 90 MW electrical envelope stops the line rather than approving and hoping.

Conflict detection itself is deterministic. Whether two zone ids differ is not a
judgement call, so no model decides it. The model reconciles conflicts. It never
detects them.

## Challenges we ran into

**Gemini 3.5 is only served from Vertex's `global` endpoint.** Regional endpoints
404 for those model ids, and `gemini-2.0-flash` is retired. Pointing at a region
would have silently dropped us to a non-compliant model.

**Thinking tokens share the output budget.** A 4,096 thinking budget inside a
4,096 ceiling returns JSON truncated mid-string.

**A lazy-singleton race.** Four concurrent agents each built their own client, and
the garbage-collected losers closed the shared HTTP transport. Three of four agents
failed in round one for no visible reason.

**A data leak that all our security tests passed.** A single shared `notes` field
had copied the sentence "5 liquid-ready racks against 6 needed" into all four
databases. Every agent could solve the problem alone, so the multi-agent premise
had quietly collapsed while all 14 isolation checks stayed green. Airtight
permissions plus a leaky payload is not isolation. A second test now scans every
value written to each store.

**A prompt injection channel we had left open.** Free text from the request
description reached the model verbatim. It is now an allowlist of fixed choices
and numbers, with `extra="forbid"` on the schema, and the description the model
sees is generated server-side.

**Our own eval suite lied to us.** It ran in-process and bypassed the gateway, so
it reported 12/12 green while production was completely broken, twice. We removed
it rather than keep a suite that manufactures confidence during an outage.

## Accomplishments that we're proud of

**The isolation is real and you can check it in thirty seconds.** Twenty-one live
checks, and every denial comes from Google Cloud rather than from our code. Delete
every check we wrote and they all still hold.

**We caught the Security Rules gap before it made the whole design decorative.**
It would have been very easy to ship per-collection rules, demo them, and have
enforced nothing.

**Our own leak test caught us breaking our own premise.** The multi-agent argument
had collapsed into four agents that could each solve the problem alone, and none of
the permission tests could see it, because permissions were not the thing that was
wrong.

**The fail-safe held against bugs that were not in the agents.** Two gateway
outages during the build, and both times the system returned "escalated, needs a
human" instead of crashing or approving something. It protected us from a failure
we had not thought of.

**The negotiation produces answers no single agent proposed.** Zone C was nobody's
first choice in round one. It only exists as an answer because four independent
exclusion lists get intersected, which is exactly what no team can do from inside
its own silo.

## What we learned

That the most dangerous failures were the ones our tests were structurally unable
to see. Both production outages presented identically, as `ESCALATED`, because the
fail-safe worked perfectly. Correct behaviour made a missing network route look
like an agent decision.

That a passing test suite during an outage is worse than no suite, because you
trust it.

And that an LLM is the wrong tool for part of this. Comparing 792 kW against
3,053 kW of headroom is arithmetic, and a constraint solver would be faster,
cheaper and provably optimal. Where the model genuinely earns its place is
interpreting constraints that vary between facilities, negotiating trade-offs, and
explaining a decision to the team it affects. Our guardrails are already a small
deterministic solver checking the model's work, and that split is the right shape
for a real product.

## What's next for GridMind

**A read-only stranded-capacity audit as the entry point.** Point it at a DCIM
export and report the megawatts an operator has paid for and cannot use. No
integration risk, no trust barrier, and it earns the right to be in the decision
loop later.

**Durable async execution**, the last partial GEAP capability. Results are already
durable; delivery is still synchronous. Cloud Tasks closes it.

**A constraint solver underneath the reasoning**, so the model does the judgement
and the arithmetic is provable.

**Real facility data.** The physics here is sourced from published figures, but how
these decisions actually get made inside an operations team is something we would
need to learn by shadowing one, not by writing a seed file.

---

## Built with (25 tags)

Every tag below is something the project actually uses, checked against
`requirements.txt`, the `gcloud services enable` list in `infra/`, and the
imports in `agents/`.

```
google-cloud, gemini, vertex-ai, google-genai, cloud-run, firestore, model-armor,
cloud-iam, cloud-logging, cloud-monitoring, cloud-build, artifact-registry,
cloud-nat, vpc, python, fastapi, pydantic, uvicorn, tenacity, httpx, reportlab,
docker, javascript, html5, bash
```

Deliberately not tagged: **google-adk**. It is in `requirements.txt` but nothing
in `agents/` imports it, so claiming it would be inaccurate.

---

*The facility `iad-dc-01` is simulated. The agents, the infrastructure and every
denial shown are real.*
