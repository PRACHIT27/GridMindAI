"""Part 4 of the constraint context: applicable federal and state law.

Injected structurally, the same way for every agent, rather than sprinkled
through prompt prose. A capacity decision that is physically fine and
financially fine can still be illegal, and the agent should be able to say so
in its reasoning with a citation attached.

SCOPE NOTE: these are simplified working summaries for a simulated Virginia
facility, written to be directionally accurate and citable. They are not legal
advice and a real deployment would source them from counsel, not a constant.
"""
from __future__ import annotations

from typing import Any

FEDERAL: dict[str, dict[str, Any]] = {
    "export_controls": {
        "citation": "15 CFR Parts 730-774 (EAR); BIS advanced computing controls, ECCN 3A090/4A090",
        "summary": "Advanced GPUs above defined performance thresholds are export-controlled. "
                   "Deployment for, or remote access by, restricted end users or destinations "
                   "requires a license.",
        "applies_to": ["power", "facilities", "cost"],
        "operational_effect": "A workload whose tenant or end user is not verified cannot be "
                              "placed on controlled accelerators regardless of available capacity.",
    },
    "epa_refrigerants": {
        "citation": "AIM Act (42 U.S.C. 7675); 40 CFR Part 84",
        "summary": "HFC production and consumption are being phased down, restricting high-GWP "
                   "refrigerants in new cooling equipment and governing leak repair and recovery.",
        "applies_to": ["cooling"],
        "operational_effect": "Adding chiller capacity may not simply replicate existing "
                              "high-GWP equipment; retrofits carry compliance lead time.",
    },
    "epa_water_discharge": {
        "citation": "Clean Water Act NPDES permitting, 40 CFR Part 122",
        "summary": "Cooling tower blowdown discharge is permitted and monitored, including "
                   "thermal and chemical limits.",
        "applies_to": ["cooling"],
        "operational_effect": "Raising evaporative cooling duty increases blowdown volume and "
                              "can approach permitted discharge limits.",
    },
    "osha_electrical": {
        "citation": "29 CFR 1910 Subpart S; NFPA 70E arc-flash practice",
        "summary": "Energized electrical work requires qualified personnel, arc-flash risk "
                   "assessment, and appropriate PPE.",
        "applies_to": ["facilities", "power"],
        "operational_effect": "Live PDU or busbar work cannot be compressed by adding "
                              "uncertified staff; it gates how fast an install can proceed.",
    },
}

VIRGINIA: dict[str, dict[str, Any]] = {
    "sales_use_tax_exemption": {
        "citation": "Va. Code Ann. Sec. 58.1-609.3(18)",
        "summary": "Data center equipment purchases are exempt from Virginia sales and use tax "
                   "where the facility meets job-creation and capital-investment thresholds "
                   "(commonly cited as 50 new jobs and $150M investment, reduced in "
                   "distressed localities).",
        "applies_to": ["cost"],
        # Worth flagging explicitly: policy context is not only restrictive.
        "operational_effect": "POSITIVE signal -- qualifying equipment purchases avoid sales tax, "
                              "materially lowering effective capex for a compliant facility.",
    },
    "gs5_rate_class": {
        "citation": "Virginia SCC, Dominion Energy Virginia rate case (approved Nov 2025), "
                    "Schedule GS-5, effective Jan 2027",
        "summary": "Creates a distinct rate class for customers exceeding 25 MW -- data centers "
                   "specifically -- with minimum-take obligations of 85% of contracted "
                   "transmission/distribution demand and 60% of contracted generation demand.",
        "applies_to": ["cost", "power"],
        "operational_effect": "Contracting headroom for a short-lived workload creates a durable "
                              "cost floor. Over-provisioning is penalized even after the workload ends.",
    },
    "water_withdrawal": {
        "citation": "Virginia Water Protection Permit program, 9VAC25-210; Va. Code Sec. 62.1-44.15",
        "summary": "Surface and groundwater withdrawals above thresholds require permitting, with "
                   "conditions that can tighten during declared drought.",
        "applies_to": ["cooling"],
        "operational_effect": "Evaporative cooling capacity is legally capped, not just physically "
                              "capped -- a drought declaration can shrink available cooling.",
    },
    "demand_response_program": {
        "citation": "PJM Emergency Load Response Program; Dominion curtailable service riders",
        "summary": "Enrolled large loads receive capacity payments in exchange for curtailing on "
                   "instruction. Non-performance during an event carries financial penalty.",
        "applies_to": ["power", "cost"],
        "operational_effect": "During an active event, curtailment is an obligation. New load "
                              "cannot be added against capacity that is contractually committed "
                              "to being shed.",
    },
    "labor_scheduling": {
        "citation": "Va. Code Ann. Sec. 40.1-29 et seq.; Virginia Overtime Wage Act",
        "summary": "Wage, overtime and rest requirements govern how technician shifts may be "
                   "extended or stacked.",
        "applies_to": ["facilities", "cost"],
        "operational_effect": "'Just work the crew longer' has a legal ceiling and an overtime "
                              "cost multiplier; it is not a free way to compress install time.",
    },
}


def policy_for(domain: str) -> dict[str, Any]:
    """Every statute that bears on one domain, federal and state.

    Filtered by domain so an agent is not asked to reason around law that has
    nothing to do with its axis -- keeping the prompt focused and the token
    bill down.
    """
    federal = {k: v for k, v in FEDERAL.items() if domain in v["applies_to"]}
    state = {k: v for k, v in VIRGINIA.items() if domain in v["applies_to"]}
    return {
        "jurisdiction": "United States / Commonwealth of Virginia",
        "federal": federal,
        "state": state,
        "note": "Simplified working summaries for simulation. Not legal advice.",
    }
