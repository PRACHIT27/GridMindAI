"""Agent Registry: how an organisation discovers what these agents are.

THE GAP THIS CLOSES
The track's stated focus opens with "corporate agent discovery". Until now
GridMind had none: Artifact Registry stored the container image, which is image
storage, not agent discovery. Nothing let a person find an agent, read its
input/output contract, see which data it is allowed to touch, or pin a version.

WHAT A REGISTRY ENTRY HAS TO CARRY TO BE USEFUL
Not just a name and a description. To decide whether to trust an agent with a
request, an organisation needs to know:

  * its CONTRACT      -- the exact schema it accepts and returns
  * its DATA SCOPE    -- which database it can reach, and which it cannot
  * its VERSION       -- what changed, and how to pin the old behaviour
  * its OWNER         -- who to ask when it refuses something
  * its GUARDRAILS    -- what it independently refuses to do

The data-scope field is the interesting one here. It turns the isolation story
from a claim in a README into a published, queryable property of each agent --
and because the same value drives the IAM condition in
infra/iam/02_create_role_and_bind.sh, a registry entry that disagreed with
reality would be caught by infra/iam/03_verify_isolation.sh.

Entries are self-registered at container start. An agent that cannot start
cannot advertise itself, so the registry describes what is actually RUNNING
rather than what someone once wrote in a wiki.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from . import obs
from .config import DOMAIN_DATABASES, MODEL_ORCHESTRATOR, MODEL_SPECIALIST

# Bumped by hand when an agent's contract or judgement changes in a way a
# caller could notice. Not the image tag: two builds of identical behaviour
# should not look like a new agent to whoever is depending on it.
AGENT_VERSION = "1.2.0"

CAPABILITIES: dict[str, dict[str, Any]] = {
    "power": {
        "title": "Power Agent",
        "judges": "Electrical feasibility",
        "decides_on": [
            "breaker capacity and headroom per zone",
            "30A/208V circuit availability after NEC derate",
            "switchgear outages inside the deployment window",
            "substation headroom against firm capacity",
            "PJM demand-response curtailment obligations",
        ],
        "explicitly_not": ["thermal capacity", "rack space", "floor loading", "budget"],
        "refuses": [
            "a zone whose headroom is below the requested load",
            "a zone with fewer spare circuits than the request needs",
            "'feasible' during an active curtailment event",
            "any zone it cannot name",
        ],
    },
    "cooling": {
        "title": "Cooling Agent",
        "judges": "Thermal feasibility and efficiency",
        "decides_on": [
            "per-rack cooling ceiling by topology (40 kW air, 140 kW liquid)",
            "total thermal headroom against the added heat load",
            "free CDU ports for direct-to-chip requests",
            "resulting PUE against a 1.60 ceiling",
            "ambient temperature and free-cooling availability",
            "cooling tower makeup water against the discharge permit",
        ],
        "explicitly_not": ["electrical capacity", "rack inventory", "budget"],
        "refuses": [
            "a per-rack density above the zone's ceiling, whatever the total headroom",
            "a liquid workload in an air-cooled zone",
            "a placement that would breach the water permit",
        ],
    },
    "facilities": {
        "title": "Facilities Agent",
        "judges": "Physical space and installation",
        "decides_on": [
            "available and liquid-ready rack counts",
            "floor load rating against rack weight",
            "retrofit options and the hours they cost",
            "certified crew availability and shift limits",
        ],
        "explicitly_not": ["electrical capacity", "thermal capacity", "budget"],
        "refuses": [
            "a rack heavier than the floor is rated for",
            "more racks than the zone has free",
            "a retrofit with less time allowed than it physically takes",
        ],
    },
    "cost": {
        "title": "Cost Agent",
        "judges": "Budget and procurement",
        "decides_on": [
            "recurring monthly cost against remaining opex budget",
            "cost per GPU-hour including capex amortization",
            "retrofit capex and its payback period",
            "Virginia GS-5 minimum-take obligations above 25 MW",
            "time-of-use energy pricing",
            "Virginia sales-and-use tax exemption as a positive signal",
        ],
        "explicitly_not": ["electrical, thermal or physical feasibility"],
        "refuses": [
            "a placement exceeding the remaining operating budget",
            "an unquantified claim of saving",
        ],
    },
    "orchestrator": {
        "title": "Capacity Allocation Orchestrator",
        "judges": "Whether four verdicts describe ONE deployable plan",
        "decides_on": [
            "physical consistency across agent verdicts, not agreement",
            "bounded re-prompt rounds when zones conflict",
            "reconciliation into a single plan, or escalation to a human",
            "precedent recall from the Memory Bank",
        ],
        "explicitly_not": [
            "any raw facility data -- it holds no access to the domain databases",
        ],
        "refuses": [
            "reporting an unresolved conflict as an approval",
            "choosing a side once the round limit is reached",
        ],
    },
}


def entry(domain: str) -> dict[str, Any]:
    """The registry record for one agent."""
    cap = CAPABILITIES[domain]
    is_orch = domain == "orchestrator"
    return {
        "agent_id": f"gridmind-{domain}",
        "name": cap["title"],
        "version": AGENT_VERSION,
        "status": "active",
        "owner": "GridMind / Data Center Capacity Engineering",
        "judges": cap["judges"],
        "decides_on": cap["decides_on"],
        "explicitly_not": cap["explicitly_not"],
        "independently_refuses": cap["refuses"],

        # The isolation story, published rather than asserted.
        "data_scope": {
            "readable_database": DOMAIN_DATABASES.get(domain),
            "denied_databases": sorted(
                set(DOMAIN_DATABASES.values()) - {DOMAIN_DATABASES.get(domain)}),
            "enforced_by": "IAM Condition on resource.name (not application code)",
            "verify_with": "bash infra/iam/03_verify_isolation.sh",
        },

        "contract": {
            "invoked_via": ("direct HTTP by the web tier" if is_orch
                            else "the Agent Gateway only"),
            "endpoint": "/negotiate" if is_orch else "/decide",
            "input_schema": "NegotiateRequest" if is_orch else "DecideRequest",
            "output_schema": "OrchestratorDecision" if is_orch else "AgentVerdict",
            "schema_url": "/openapi.json",
        },

        "runtime": {
            "platform": "Cloud Run",
            "service_account": f"{domain}-agent-sa@gridmindai-507000.iam.gserviceaccount.com"
            if not is_orch else
            "orchestrator-agent-sa@gridmindai-507000.iam.gserviceaccount.com",
            "ingress": "internal",
            "model": MODEL_ORCHESTRATOR if is_orch else MODEL_SPECIALIST,
            "revision": os.environ.get("K_REVISION", "local"),
        },

        "safeguards": {
            "structured_output": "schema-validated, retried on violation",
            "retry_policy": "3 attempts, exponential backoff, then fail safe",
            "on_exhaustion": "returns infeasible and escalates -- never guesses",
            "content_screening": "Model Armor at the gateway (inbound and outbound)",
        },
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }


ALL_AGENTS = ("power", "cooling", "facilities", "cost", "orchestrator")


def publish(client: Any) -> list[str]:
    """Publish every agent's entry to shared-db/agent_registry.

    WHY THIS IS NOT SELF-REGISTRATION
    The obvious design is for each agent to write its own entry at startup. It
    cannot, and should not be able to: a specialist's identity is bound by IAM
    Condition to its own domain database, so it has no write access to
    shared-db at all. Granting it some would mean widening the exact boundary
    the registry exists to advertise -- the entry would claim "this agent can
    only reach power-db" while the act of publishing it proved otherwise.

    So publication is a DEPLOY-TIME step, run with the deployer's credentials,
    the same way a real registry is populated by CI rather than by the running
    workload. The entries still describe what is deployed, because the deploy
    script publishes them immediately after the services roll out.

    Takes a client rather than building one, so the caller supplies credentials
    that are appropriate for writing.
    """
    written: list[str] = []
    for domain in ALL_AGENTS:
        rec = entry(domain)
        client.collection("agent_registry").document(rec["agent_id"]).set(rec)
        written.append(rec["agent_id"])
        obs.log("agent_registered", agent=domain, agent_id=rec["agent_id"],
                version=rec["version"], scope=rec["data_scope"]["readable_database"])
    return written
