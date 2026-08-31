# Demo video script — 4 minutes

Follows `GridMind_Submission_Deck.pptx` slide for slide, then one live demo at
the end. Deck for 0:00–2:50, screen share for 2:50–3:45, back to the deck to close.

**Live:** https://gridmind-wuvfpvopoq-uk.a.run.app
**Access key** (skips the rate limit — paste it in *before* you record):
`611d3791b072090476d04a81`

## Before you hit record

```bash
curl -s -o /dev/null https://gridmind-wuvfpvopoq-uk.a.run.app/api/decisions
```

That wakes the services so nothing cold-starts on camera. Then confirm the chain
is alive — do not skip this:

```bash
bash infra/iam/03_verify_isolation.sh
```

```bash
python -m scripts.demo_guardrails
```

Expect `ISOLATION VERIFIED` and `6/6`.

Have exactly three things open, in this order, and nothing else:

1. The deck, full screen, on slide 1
2. The dashboard, on **New assessment**, key already pasted, 6× GB200 selected
3. A terminal, cleared, in the repo root

**Record at 1920×1080.** The round-one verdict chips and the zone map are the
two things that must be legible.

---

## The deck · 0:00 – 2:52

Timings are per slide. The words below are what to say, not a paragraph to read
— each slide's speaker notes carry the same beat if you lose your place.

### Slide 1 · Title · 0:00 – 0:10

> *"This is GridMind. It decides where a new high-density workload can go inside
> a data center, by checking power, cooling, floor space and budget at the same
> time."*

### Slide 2 · The problem · 0:10 – 0:38

> *"Right now four teams own those four answers, and the request moves from one
> inbox to the next over several days."*
>
> *"The failure nobody catches isn't that a team gets it wrong. It's that all
> four can be right and still describe a plan that cannot be built, because each
> was looking at a different room. The industry calls what's left behind stranded
> capacity — megawatts you've paid for and can't use."*

### Slide 3 · What it's worth · 0:38 – 1:00

> *"For the operations team placing that workload, GridMind returns one plan
> clearing all four constraints at once, in about ninety seconds instead of days,
> with a report showing what each assessor was shown beside what it concluded."*
>
> *"Nobody in the current process computes that joint check, because no team can
> see outside its own data."*

### Slide 4 · What it does · 1:00 – 1:14

> *"A request goes in as a form. Four assessors run in parallel, each reading
> only its own database. The orchestrator checks whether their four answers
> describe a single buildable plan. Out comes a decision and a report."*

### Slide 5 · The conflict · 1:14 – 1:40

> *"Here's a real run. Six racks of GB200s — 792 kilowatts, liquid cooled."*
>
> *"Power says zone A. Cooling says zone C. Facilities and cost both say zone
> B."*

**Pause here for a beat. Let the three different zones land.**

> *"Every one of those is correct on its own axis. Together they're three
> different rooms and no plan at all. A system that counted votes would see four
> approvals and place the order."*

### Slide 6 · How it resolves · 1:40 – 2:16

> *"So the orchestrator doesn't count votes. It detects the conflict in ordinary
> code — whether two zone ids differ is not a judgement call — then opens a
> negotiation round with each assessor's position attached to the others'."*
>
> *"In round two, facilities volunteers a retrofit it hadn't mentioned. Cost
> re-prices one rack instead of six. Three rounds maximum, then it escalates
> rather than picking a winner."*
>
> *"Every assessor also reports what its axis rules out. Intersect those four
> lists and one zone survives — zone C. In round one, nobody had picked it."*

### Slide 7 · Under the hood · 2:16 – 2:42

> *"Underneath: seven Cloud Run services, seven identities, five separate
> databases. The power assessor physically cannot open the cooling data — that's
> an IAM condition on the store, not a check in our code."*
>
> *"The rest is a line each. Guardrails re-check every verdict against the figures
> it was handed. Three retries with the violation fed back, then it refuses.
> Model Armor screens agent traffic both ways."*

### Slide 8 · Deployed · 2:42 – 2:52

> *"Twenty-one security checks, seven services, six of the seven platform
> capabilities. And the facility is simulated — the agents, the infrastructure
> and every denial are real."*

---

## The demo · 2:52 – 3:43

Switch to the dashboard. **One take, no cuts.**

### Start it · 2:52 – 3:01

**Do:** hit **Check feasibility** on the queued 6× GB200 request.

> *"Let me run it. Four agents starting in parallel, on four separate
> services."*

### Fill the wait with the security proof · 3:01 – 3:25

**This is the tight part of the video.** The assessment takes 60–90 seconds and
you have about 40 before you need the result on screen, so the terminal has to
carry the gap. **Switch to it and run:**

```bash
bash scripts/demo_denial.sh
```

> *"While that runs — none of these refusals come from our code. The power agent
> asking for cost data gets a 403 straight from Firestore. Every agent from the
> internet gets a 404: not rejected, unreachable."*
>
> *"Delete every check we wrote and these still hold."*

That's about 17 seconds of talking over a script that takes longer than that to
finish. **Let it scroll in silence.** Twenty-one checks going green unattended is
better television than filler narration, and it is the unedited live execution
the rubric asks for.

**Do not switch back until the dashboard has a decision.** Cutting to a spinner
costs you more than the extra seconds do.

> **Safer alternative if you'd rather not race the clock:** hit **Check
> feasibility** just before slide 7 instead, leave the tab in the background, and
> the result is waiting when you reach the demo. You lose nothing — the run is
> still live and unedited, it just starts forty seconds earlier.

### Back to the result · 3:25 – 3:43

**Switch back to the dashboard.** Round one should be on screen.

> *"There's the conflict, live. Three different rooms."*

**Point at the exclusion line, then the zone map dimming.**

> *"And the decision: zone C. Five liquid-ready racks plus one retrofit, fourteen
> hours of delay, forty-eight thousand instead of two hundred and eighty-eight."*

**Do:** click **Download report (PDF)**, scroll to the **evidence** section.

> *"And this is what an operator needs. Not what the agents said — what they were
> shown. The figures each one was handed, recorded by the system rather than
> reported by the model."*

---

## Slide 9 · Close · 3:43 – 3:50

Switch back to the deck.

> *"Four correct answers still add up to nothing unless something checks them
> together. That's GridMind."*

---

## Things to avoid

- **Don't run the assessment without the key pasted.** The limiter refuses a
  second run inside 90 seconds and it looks like a fault.
- **Don't demo the 2-rack request.** Two zones are genuinely viable there, so it
  escalates rather than deciding. Defensible, but it needs explaining and you do
  not have the seconds.
- **Don't read the agent reasoning aloud.** It's long. Point at the verdict chips
  and the zone map instead.
- **Don't apologise for the simulated facility.** Slide 8 states it once. Leave
  it there.
- **Don't narrate the deck's six under-the-hood boxes.** Say the shape, let the
  slide carry the detail.

## If something fails on camera

The system fails safe, so a broken dependency shows up as **`ESCALATED`** rather
than a crash or a wrong answer. Use it:

> *"That's the fail-safe. When an assessor can't produce an answer it trusts, the
> system refuses and escalates instead of guessing — which is what you want from
> something deciding where megawatts go."*

Then open the **History** tab and walk a stored decision. It reads from the
recorded result and needs nothing live.

If the run is still spinning at 3:30, stop waiting and go to **History** — the
stored 6× GB200 decision shows the identical round-one conflict and the same
final plan.
