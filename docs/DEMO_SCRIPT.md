# Demo video script — 4 minutes

**Live:** https://gridmind-wuvfpvopoq-uk.a.run.app
**Access key** (skips the rate limit — have it pasted in before recording): `611d3791b072090476d04a81`

## Before you hit record

```bash
# 1. Wake the services so nothing cold-starts on camera (each takes ~10s otherwise)
curl -s -o /dev/null https://gridmind-wuvfpvopoq-uk.a.run.app/api/decisions

# 2. Confirm the whole chain is alive — do NOT skip this
bash infra/iam/03_verify_isolation.sh          # expect: ISOLATION VERIFIED
python -m scripts.demo_guardrails              # expect: 6/6
```

Have these open in tabs, in this order:

1. The dashboard, on **New assessment**
2. A terminal, cleared, in the repo root
3. Cloud Run console — the services list
4. Cloud Logging, with a correlation id already filtered

**Record at 1920×1080.** The zone map and the round cards are the two things that
must be legible; everything else can be small.

---

## 0:00 – 0:35 · The problem

> *"A data centre operator gets a request: six racks of GB200s. Before anyone can
> say yes, four separate teams have to check four different things — is there
> power, can we cool it, is there floor space, can we afford it."*
>
> *"Today that happens in four inboxes over several days. And here's the failure
> nobody catches: all four teams can say yes, correctly, and still describe a plan
> that cannot be built — because each was looking at a different room."*

**On screen:** the landing page. Let the headline sit for a beat.

> *"GridMind checks all four together, in about a minute, and writes down why."*

---

## 0:35 – 1:50 · The assessment, live

**Do:** paste the access key, leave the queued 6× GB200 request selected, hit
**Check feasibility.**

While it runs (60–90 s), talk over it:

> *"Four agents are running right now, in parallel, on separate Cloud Run
> services. Each one can read exactly one database — the power agent physically
> cannot open the cooling data. That's not a policy we wrote in code, it's an IAM
> condition on the store itself."*

**When round 1 lands — this is the moment. Stop talking and point at it:**

| Agent | Zone |
|---|---|
| Power | `zone-a` |
| Cooling | `zone-c` |
| Facilities | `zone-b` |
| Cost | `zone-b` |

> *"Four answers. Every one correct on its own axis. Together they describe
> nothing — three different rooms."*

**Then point at the exclusion line under the round:**

> *"But look at what they each rule OUT. Cooling kills A, B and D. Power kills B
> and D. Intersect the four lists and exactly one room survives — zone C. And in
> round one, not a single agent had picked it."*

**Watch the zone map dim** as the eliminated zones grey out.

> *"That's the whole idea. No individual team could compute that, because no
> individual team can see the other three."*

---

## 1:50 – 2:35 · The decision and the audit trail

**On screen:** the decision panel.

> *"Zone C, five liquid-ready racks plus one retrofitted, fourteen hours' delay,
> forty-eight thousand in capex. And it names which agent unlocked it —
> Facilities knew about the retrofit; Cost had assumed all six racks needed one
> and priced it at two hundred and eighty-eight thousand."*

**Do:** click **Download report (PDF)**. Scroll to the **evidence** section.

> *"This is the part an operator actually needs. Everything above is what the
> agents said. This is what they were shown — the exact figures each one was
> handed, recorded by the system, not self-reported by the model. So you can
> check the reasoning against the data."*

Point at one row: *"Zone B, 560 kW of headroom against a 792 kW request. The
agent's sentence and the number it was given, side by side."*

---

## 2:35 – 3:20 · Security, in a terminal

**Do:** run it live.

```bash
bash scripts/demo_denial.sh
```

> *"Three layers, and none of these refusals come from our code."*

- **Data:** `power-agent-sa` → `cost-db` = **403**. Firestore itself refuses.
- **Network:** every agent = **404** from the internet. Not rejected — unreachable.
- **Content:** Model Armor blocks prompt injection, jailbreak and PII on the way in
  *and* the way out.

> *"The orchestrator is bound to one store and cannot read any facility data at
> all. So 'it only sees the agents' verdicts' isn't a promise in a README — it's
> a property of the platform. Delete our checks and these still hold."*

**Worth saying if you have the second:**

> *"And the most exposed service holds the least. The public web tier is
> read-only, one store, and has no permission to call a model at all."*

---

## 3:20 – 4:00 · Proof it's really on GCP

**Do:** Cloud Run console → the seven services, each with its own service account.

> *"Seven services, seven identities, five isolated databases."*

**Do:** Cloud Logging, filtered on the correlation id from the run you just did.

```
jsonPayload.correlation_id="gm-..."
```

> *"And one id threads the whole decision — every model call, every guardrail
> check, every screening result, every allow and deny. A capacity decision you
> can reconstruct months later."*

**Close:**

> *"Built on Gemini 3.5, Cloud Run and Firestore. Six of the seven Gemini
> Enterprise Agent Platform capabilities, with the security enforced by the
> platform rather than described in a slide."*

---

## Things to avoid

- **Don't apologise for the simulated facility.** State it once, plainly, if it
  comes up: the facility is simulated, the agents and the infrastructure are real.
- **Don't read the agent reasoning aloud** — it's long. Point at the verdict
  chips and the zone map instead.
- **Don't run an assessment without the key.** The rate limiter will refuse a
  second run within 90 seconds and it looks like a fault.
- **Don't demo the 2-rack request.** Two zones are genuinely viable there and it
  escalates rather than picking — defensible, but it needs explaining and you
  don't have the seconds.

## If something fails on camera

The system fails *safe*, so a broken dependency shows up as **`ESCALATED`**
rather than a crash or a wrong answer. If that happens, use it:

> *"That's the fail-safe. When an agent can't produce a trustworthy answer, the
> system refuses and escalates rather than guessing — which is exactly what you
> want from something deciding where megawatts go."*

Then cut to a saved decision from the **History** tab, which reads from the
stored record and needs nothing live.
