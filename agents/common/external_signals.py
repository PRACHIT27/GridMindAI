"""Part 3 of the constraint context: external, real-world signals.

These stand in for third-party APIs an operator would genuinely subscribe to
(PJM pricing, NOAA forecasts, a workforce system, a freight tracker). They are
mocked, but they are shaped like the real feeds and -- more importantly -- they
are the thing that makes agents DISAGREE. Without a live external axis, four
agents reading static Firestore rows will reach the same conclusion forever and
the negotiation has nothing to negotiate.

Determinism: signals are seeded from (domain, scenario, hour) so a demo replays
identically, while still drifting hour to hour like a real feed.

`scenario` lets the demo force a specific world state. This is the difference
between hoping a conflict appears on camera and staging one deliberately.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone
from typing import Any

SCENARIOS = ("normal", "heatwave", "grid_stress", "crew_shortage", "freight_delay")


def _rng(domain: str, scenario: str, hour: int) -> random.Random:
    seed = int(hashlib.sha256(f"{domain}|{scenario}|{hour}".encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _power_signal(r: random.Random, scenario: str, hour_et: int) -> dict[str, Any]:
    """PJM wholesale pricing and demand-response posture.

    On-peak in PJM is roughly 07:00-23:00 ET weekdays. Locational marginal
    price spikes are what make "run it tonight instead" a real cost argument.
    """
    on_peak = 7 <= hour_et < 23
    base_lmp = r.uniform(38, 55) if not on_peak else r.uniform(62, 95)

    dr_event = False
    dr_notice_hours = None
    if scenario == "grid_stress":
        base_lmp = r.uniform(180, 340)          # scarcity pricing
        dr_event = True
        dr_notice_hours = r.choice([2, 4, 6])
    elif scenario == "heatwave" and on_peak:
        base_lmp = r.uniform(110, 190)
        dr_event = r.random() < 0.6
        dr_notice_hours = r.choice([4, 8]) if dr_event else None

    return {
        "source": "PJM Interconnection (simulated)",
        "zone": "DOM",
        "locational_marginal_price_usd_per_mwh": round(base_lmp, 2),
        "period": "on-peak" if on_peak else "off-peak",
        "demand_response_event_active": dr_event,
        "demand_response_notice_hours": dr_notice_hours,
        # Under PJM Emergency Load Response, a curtailment instruction is not
        # advisory -- non-performance carries a penalty, so the Power agent must
        # treat this as a hard constraint rather than a price signal.
        "curtailment_obligation_mw": round(r.uniform(4, 12), 1) if dr_event else 0.0,
        "grid_frequency_hz": round(r.uniform(59.97, 60.03), 3),
    }


def _cooling_signal(r: random.Random, scenario: str, hour_et: int) -> dict[str, Any]:
    """NOAA-style forecast for Ashburn, VA.

    Ambient dry bulb and especially WET BULB decide whether evaporative/free
    cooling assist is available. Above the free-cooling ceiling the chillers
    carry the whole load, PUE climbs, and thermal headroom evaporates -- which
    is precisely when the Cooling agent should start refusing placements the
    Power agent sees no problem with.
    """
    diurnal = 6.0 * (1 if 11 <= hour_et <= 18 else -1)
    if scenario == "heatwave":
        dry_bulb = r.uniform(35, 40) + diurnal * 0.4
        humidity = r.uniform(55, 75)
    else:
        dry_bulb = r.uniform(19, 27) + diurnal * 0.3
        humidity = r.uniform(40, 70)

    # Stull approximation for wet bulb from dry bulb + relative humidity.
    wet_bulb = (dry_bulb * 0.151977 * ((humidity + 8.313659) ** 0.5)
                + 0.00391838 * (humidity ** 1.5) * 0.023101
                - 4.686035 + 0.00391838 * humidity)
    wet_bulb = max(min(wet_bulb, dry_bulb), dry_bulb - 12)

    return {
        "source": "NOAA/NWS Sterling VA forecast office (simulated)",
        "station": "KIAD",
        "ambient_dry_bulb_c": round(dry_bulb, 1),
        "relative_humidity_pct": round(humidity, 1),
        "wet_bulb_c": round(wet_bulb, 1),
        "forecast_high_next_24h_c": round(dry_bulb + r.uniform(1.5, 4.0), 1),
        "heat_advisory": scenario == "heatwave",
    }


def _facilities_signal(r: random.Random, scenario: str, hour_et: int) -> dict[str, Any]:
    """Workforce management feed: who can actually turn a wrench, and when."""
    if scenario == "crew_shortage":
        available = r.randint(0, 2)
        next_window = r.choice([18, 24, 36])
    else:
        available = r.randint(4, 9)
        next_window = 0

    return {
        "source": "Workforce management system (simulated)",
        "certified_technicians_on_shift": available,
        "electricians_available": max(0, available - r.randint(1, 2)),
        "liquid_cooling_certified_techs": max(0, available - r.randint(2, 4)),
        "next_availability_window_hours": next_window,
        "site_access_restricted": scenario in ("heatwave", "crew_shortage") and r.random() < 0.3,
        "shift_ends_in_hours": round(max(0.5, 8 - (hour_et % 8)), 1),
    }


def _cost_signal(r: random.Random, scenario: str, hour_et: int) -> dict[str, Any]:
    """Procurement feed: vendor lead times and inbound freight."""
    if scenario == "freight_delay":
        lead_weeks = r.randint(14, 26)
        eta_days = r.randint(21, 45)
        congestion = r.choice(["severe", "high"])
    else:
        lead_weeks = r.randint(6, 12)
        eta_days = r.randint(4, 14)
        congestion = r.choice(["none", "moderate"])

    return {
        "source": "Vendor/logistics portal (simulated)",
        "gpu_lead_time_weeks": lead_weeks,
        "cdu_lead_time_weeks": r.randint(8, 20),
        "inbound_freight_eta_days": eta_days,
        "port_congestion": congestion,
        "customs_hold_risk_pct": r.randint(25, 60) if scenario == "freight_delay" else r.randint(2, 12),
        "spot_gpu_premium_pct": round(r.uniform(12, 30) if scenario == "freight_delay"
                                      else r.uniform(-3, 8), 1),
    }


_BUILDERS = {
    "power": _power_signal,
    "cooling": _cooling_signal,
    "facilities": _facilities_signal,
    "cost": _cost_signal,
}


def get_external_signal(domain: str, scenario: str = "normal",
                        at: datetime | None = None) -> dict[str, Any]:
    """Fetch the external signal for one domain.

    In production this would be four real HTTP clients behind a timeout and a
    circuit breaker. The interface is deliberately the same shape so swapping
    the mock for a live feed touches only this module.
    """
    if domain not in _BUILDERS:
        raise KeyError(f"no external signal defined for domain {domain!r}")
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; expected one of {SCENARIOS}")

    now = at or _now()
    hour_et = (now.hour - 4) % 24          # UTC -> approximate US/Eastern
    r = _rng(domain, scenario, now.hour)

    signal = _BUILDERS[domain](r, scenario, hour_et)
    signal["observed_at"] = now.isoformat()
    signal["scenario"] = scenario
    signal["local_hour_et"] = hour_et
    return signal
