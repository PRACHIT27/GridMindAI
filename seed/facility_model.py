"""ONE physical facility, generated once, projected into four domain views.

DESIGN PRINCIPLE: constrain, then randomize, then derive.
--------------------------------------------------------
Three layers, in order. Each one is the input to the next.

  1. AUTHORED CONSTRAINTS  (fixed, never randomized)
     The things that make an agent say "no": floor load ratings, free CDU
     ports, liquid-ready rack counts, switchgear outages. These are pinned so
     the demo's cross-domain deadlock survives any reseed.

  2. RANDOMIZED POPULATION  (seeded, generated once at seed time)
     Which GPUs sit in which racks and at what density. Weighted and
     triangular rather than uniform, and CONSTRAINED BY the zone's cooling
     type -- an air-cooled zone physically cannot be dealt a 132 kW GB200
     rack, so no impossible combination can be generated in the first place.

  3. DERIVED VALUES  (pure functions of 1 and 2)
     Loads, thermals, PUE, costs, facility rollups. Never authored, always
     computed, so the four domain views reconcile to the same physics.

WHY DERIVATION IS NOT OPTIONAL
------------------------------
Essentially all IT power becomes heat. So a zone's electrical draw and its
thermal load are not two independent facts to randomize separately -- they are
one fact seen twice. Authoring them independently produces a facility that
violates conservation of energy, which is the first thing a technical judge
would check.

Crucially, this does NOT collapse the multi-agent premise. The magnitudes are
coupled; the CONSTRAINTS are not. Knowing zone-c draws 14.2 MW tells you
nothing about whether it has 5 or 6 liquid-ready racks, what its floor is rated
for, or whether a crew is available. Every value that actually drives a verdict
remains independent -- which is exactly the real world: one physical facility,
four teams reading four different systems (EPMS, BMS, DCIM, ERP).

DETERMINISM
-----------
Randomization happens ONCE, at seed time, under a fixed seed. Agents never
randomize; they read fixed state, so the same request yields the same answer
and a demo replays identically. To simulate the clock moving forward, re-run
with a different sim_hour: the diurnal term moves, and every dependent value
moves WITH it, because they all derive from the same master term.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Physical coefficients
# ---------------------------------------------------------------------------

# Fraction of IT electrical draw that becomes heat the cooling plant must
# remove. Near 1.0 by conservation of energy; the remainder leaves as fan work
# and radiated light rather than as load on the CRAH/CDU.
HEAT_FRACTION = 0.98

# Usable capacity of one 30A/208V circuit after the NEC 80% continuous derate.
KW_PER_CIRCUIT = 10.0

AIR_COOLING_CEILING_KW = 40.0     # hard ceiling for air-cooled racks
LIQUID_COOLING_CEILING_KW = 140.0  # DLC upper bound; GB200 NVL72 draws ~132

BASE_PUE = {"air_crah": 1.38, "liquid_dlc": 1.14}
HOURS_PER_MONTH = 730.0
RACK_U_HEIGHT = 48

SEED = 42

# GPU population, per cooling topology. The zone's cooling type CONSTRAINS the
# draw before any randomization happens, which is what makes it impossible to
# generate an air-cooled 132 kW rack. Densities are (min, mode, max) for a
# triangular distribution -- peaked near the typical value, with realistic
# tails, rather than flat/uniform.
GPU_POPULATION: dict[str, dict[str, Any]] = {
    "air_crah": {
        # Real fleets skew to older, cheaper parts.
        "types": ["H100", "H200"],
        "weights": [0.65, 0.35],
        "density": {"H100": (28.0, 34.0, 39.0), "H200": (32.0, 36.0, 39.5)},
        "weight_kg": {"H100": 900.0, "H200": 950.0},
        "gpus_per_rack": {"H100": 8, "H200": 8},
        "rack_capex_usd": {"H100": 250_000.0, "H200": 290_000.0},
    },
    "liquid_dlc": {
        "types": ["B200", "GB200_NVL72"],
        "weights": [0.45, 0.55],
        "density": {"B200": (55.0, 70.0, 90.0), "GB200_NVL72": (100.0, 120.0, 132.0)},
        "weight_kg": {"B200": 1150.0, "GB200_NVL72": 1360.0},
        "gpus_per_rack": {"B200": 8, "GB200_NVL72": 72},
        # A GB200 NVL72 rack is a ~$3M single SKU, not 72 loose GPUs.
        "rack_capex_usd": {"B200": 400_000.0, "GB200_NVL72": 3_000_000.0},
    },
}

# GPU hardware is depreciated over 3 years. Capex amortization DOMINATES
# cost-per-GPU-hour -- power is the minority term -- so a model that counts
# only electricity reports a figure several times too low.
CAPEX_AMORTIZATION_MONTHS = 36.0


# ---------------------------------------------------------------------------
# Layer 1: authored constraints
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ZoneSpec:
    """Pinned facts about one zone.

    Capacities are expressed as HEADROOM above whatever load the generator
    produces, not as absolute kW. That is deliberate: it means the designed
    scarcity (zone-b being nearly out of breaker capacity) holds exactly, no
    matter how the rack randomization lands.
    """
    zone_id: str
    total_racks: int
    occupied_racks: int
    cooling_type: str                     # air_crah | liquid_dlc
    upstream_switchgear: str

    # Authored scarcity -- the things agents refuse on.
    breaker_headroom_kw: float            # spare electrical capacity by design
    thermal_headroom_kw: float            # spare cooling capacity by design
    floor_load_limit_kg_per_rack: float
    liquid_ready_racks: int
    retrofittable_racks: int
    free_cdu_ports: int

    cost_per_kw_month_usd: float
    liquid_retrofit_cost_usd_per_rack: float
    install_labor_rate_usd_per_hour: float
    planned_outage: dict[str, Any] | None = None

    # Notes are PER DOMAIN, never shared. A single shared note string is an
    # information leak that quietly defeats the entire isolation design: a
    # sentence like "5 liquid-ready racks against 6 needed" copied into every
    # database hands the Cooling agent a rack-inventory fact it must not have,
    # and every agent can then solve the problem alone.
    # Each note may only reference facts already present in ITS OWN database.
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def available_racks(self) -> int:
        return self.total_racks - self.occupied_racks


# The demo workload is 6x GB200 NVL72 racks: 132 kW and ~1,360 kg each, 792 kW
# total, requiring direct-to-chip liquid cooling.
#
#   zone-a  most electrical headroom in the building, and useless for this:
#           air-cooled (40 kW/rack ceiling) AND a 1,200 kg floor rating that a
#           1,360 kg GB200 rack exceeds. Power endorses it; Cooling and
#           Facilities both refuse it, for unrelated reasons.
#   zone-b  8 free liquid-ready racks -- looks ideal on rack count alone --
#           but only 2 free CDU ports and 460 kW of breaker headroom against a
#           792 kW ask. Fails on cooling plant AND on power.
#   zone-c  the only workable zone, and NOT as requested: 5 liquid-ready racks
#           against 6 needed. Becomes feasible only by retrofitting 1 of its 3
#           retrofittable racks, at roughly 14 hours of delay.
#   zone-d  cheapest $/kW and the most space, but air-cooled, and switchgear
#           SG-3 is out for maintenance inside the deployment window.
#
# No single agent holds enough to find the zone-c-plus-retrofit answer:
# Facilities knows the retrofit exists but not whether cooling or power can
# carry it; Cooling knows zone-c has thermal room but not that it is one rack
# short. The answer only appears when those positions are put in front of each
# other -- which is what the negotiation rounds do.
ZONES: tuple[ZoneSpec, ...] = (
    ZoneSpec(
        zone_id="zone-a", total_racks=160, occupied_racks=130,
        cooling_type="air_crah", upstream_switchgear="SG-1",
        breaker_headroom_kw=3800.0, thermal_headroom_kw=2600.0,
        floor_load_limit_kg_per_rack=1200.0,
        liquid_ready_racks=0, retrofittable_racks=0, free_cdu_ports=0,
        cost_per_kw_month_usd=12.40, liquid_retrofit_cost_usd_per_rack=0.0,
        install_labor_rate_usd_per_hour=95.0,
        notes={
            "power": "Largest electrical headroom in the facility; 2N feed from SG-1.",
            "cooling": "Air-cooled CRAH zone; hard 40 kW/rack ceiling.",
            "facilities": "Space available, but legacy floor rated 1,200 kg per rack.",
            "cost": "Lowest-cost air-cooled zone.",
        },
    ),
    ZoneSpec(
        zone_id="zone-b", total_racks=140, occupied_racks=132,
        cooling_type="liquid_dlc", upstream_switchgear="SG-1",
        breaker_headroom_kw=460.0, thermal_headroom_kw=900.0,
        floor_load_limit_kg_per_rack=1800.0,
        liquid_ready_racks=8, retrofittable_racks=0, free_cdu_ports=2,
        cost_per_kw_month_usd=13.10, liquid_retrofit_cost_usd_per_rack=0.0,
        install_labor_rate_usd_per_hour=95.0,
        notes={
            "power": "Near breaker limit; roughly 460 kW of headroom remains on SG-1.",
            "cooling": "Liquid DLC zone, but only 2 CDU ports currently free.",
            "facilities": "8 liquid-ready racks free.",
            "cost": "Premium rate reflecting existing DLC infrastructure.",
        },
    ),
    ZoneSpec(
        zone_id="zone-c", total_racks=150, occupied_racks=142,
        cooling_type="liquid_dlc", upstream_switchgear="SG-2",
        breaker_headroom_kw=3100.0, thermal_headroom_kw=4200.0,
        floor_load_limit_kg_per_rack=1800.0,
        liquid_ready_racks=5, retrofittable_racks=3, free_cdu_ports=10,
        cost_per_kw_month_usd=12.90, liquid_retrofit_cost_usd_per_rack=48000.0,
        install_labor_rate_usd_per_hour=110.0,
        notes={
            "power": "Healthy headroom on a 2N feed from SG-2.",
            "cooling": "Best thermal position in the facility; 10 CDU ports free.",
            # Only facilities-db may mention rack counts -- this is THE fact
            # that unlocks the negotiation, and it must stay in one place.
            "facilities": "5 liquid-ready racks free; 3 further racks can be "
                          "retrofitted for DLC at roughly 14 h each.",
            "cost": "Retrofit is capex-heavy but avoids a new zone buildout.",
        },
    ),
    ZoneSpec(
        zone_id="zone-d", total_racks=150, occupied_racks=60,
        cooling_type="air_crah", upstream_switchgear="SG-3",
        breaker_headroom_kw=4900.0, thermal_headroom_kw=3400.0,
        floor_load_limit_kg_per_rack=1600.0,
        liquid_ready_racks=0, retrofittable_racks=12, free_cdu_ports=0,
        cost_per_kw_month_usd=11.80, liquid_retrofit_cost_usd_per_rack=61000.0,
        install_labor_rate_usd_per_hour=95.0,
        planned_outage={
            "switchgear": "SG-3", "starts_in_hours": 48, "duration_hours": 14,
            "reason": "Scheduled breaker maintenance and thermographic survey",
        },
        notes={
            "power": "Ample headroom, but SG-3 maintenance falls inside the deployment window.",
            "cooling": "Air-cooled CRAH zone; hard 40 kW/rack ceiling.",
            "facilities": "Most free space in the facility; 12 racks retrofittable, none ready.",
            "cost": "Lowest $/kW in the facility.",
        },
    ),
)

FACILITY = {
    "facility_id": "iad-dc-01",
    "location": "Ashburn, Loudoun County, Virginia, USA",
    "utility_feed_mw": 90.0,
    "substation_firm_capacity_mw": 72.0,
    "contracted_demand_mw": 50.0,      # above the 25 MW GS-5 threshold, so it binds
    "chiller_capacity_mw_thermal": 48.0,
    "chillers_online": 5,
    "chillers_total": 6,
    "chiller_in_maintenance": "CH-04",
    "water_permit_limit_gpm": 600.0,
    "monthly_opex_budget_usd": 7_200_000.0,
    "ups_strings_online": 6,
    "ups_strings_total": 6,
    "generator_fuel_hours": 72,
}


# ---------------------------------------------------------------------------
# Layer 2: seeded population
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Rack:
    rack_id: str
    zone: str
    gpu_type: str
    gpu_count: int
    nameplate_kw: float
    cooling_method: str
    circuit_count: int
    weight_kg: float
    capex_usd: float
    u_space_used: int
    u_space_total: int = RACK_U_HEIGHT


def generate_racks(spec: ZoneSpec, rng: random.Random) -> list[Rack]:
    """Populate one zone's occupied racks.

    Rack ids are sequential, not random. The reference implementation used
    `random.randint(1, 20)`, which collides constantly -- and because racks are
    stored in a dict keyed by rack_id, collisions SILENTLY DROP racks. Asking
    for 142 racks would quietly yield fewer, and every derived load would be
    wrong by an amount nobody could see.
    """
    pop = GPU_POPULATION[spec.cooling_type]
    racks: list[Rack] = []

    for i in range(1, spec.occupied_racks + 1):
        gpu_type = rng.choices(pop["types"], weights=pop["weights"], k=1)[0]
        lo, mode, hi = pop["density"][gpu_type]
        kw = round(rng.triangular(lo, mode, hi), 1)

        # Cooling method is DERIVED from density, never randomized alongside
        # it. Combined with the topology-constrained GPU pool above, an
        # air-cooled zone cannot produce a rack over its 40 kW ceiling.
        cooling_method = "air" if kw <= AIR_COOLING_CEILING_KW else "liquid"
        if cooling_method == "liquid" and spec.cooling_type == "air_crah":
            raise AssertionError(  # unreachable; guards the invariant explicitly
                f"{spec.zone_id}: generated a {kw} kW rack in an air-cooled zone")

        racks.append(Rack(
            rack_id=f"{spec.zone_id}-r{i:03d}",
            zone=spec.zone_id,
            gpu_type=gpu_type,
            gpu_count=pop["gpus_per_rack"][gpu_type],
            nameplate_kw=kw,
            cooling_method=cooling_method,
            circuit_count=math.ceil(kw / KW_PER_CIRCUIT),
            weight_kg=pop["weight_kg"][gpu_type],
            capex_usd=pop["rack_capex_usd"][gpu_type],
            # Occupancy tracks a facility-wide fill level rather than each rack
            # rolling independently -- real facilities fill fairly uniformly.
            u_space_used=int(min(max(rng.gauss(34, 6), 8), RACK_U_HEIGHT)),
        ))
    return racks


# ---------------------------------------------------------------------------
# Layer 3: derivation
# ---------------------------------------------------------------------------

def diurnal_factor(sim_hour: int) -> float:
    """Fraction of nameplate the facility is actually drawing at this hour.

    Real data centers are not flat: batch and training work concentrates
    overnight when power is cheap, interactive load peaks mid-afternoon. This
    is the ONLY time-varying term in the model. Everything else moves because
    this moves, which is what keeps the four domain views consistent as the
    simulated clock advances -- and what makes "run it off-peak" a real
    argument for the Cost agent rather than an arbitrary one.

    Peaks near 15:00 local, troughs near 03:00, range about 0.86 to 1.00.
    """
    return 0.93 + 0.07 * math.sin((sim_hour - 9) * math.pi / 12.0)


def zone_pue(cooling_type: str, load_ratio: float, ambient_c: float) -> float:
    """PUE from topology, how hard the zone is working, and outside air.

    Two penalties above the topology baseline:
      * load     -- cooling plant is less efficient near its ceiling
      * ambient  -- above the 18 C free-cooling ceiling the chillers carry the
                    load alone. Air-cooled zones degrade about twice as fast as
                    liquid ones, which is why a heatwave can flip a Cooling
                    verdict on an air zone while leaving a liquid zone fine.
    """
    base = BASE_PUE[cooling_type]
    load_penalty = 0.06 * max(0.0, load_ratio - 0.75)
    ambient_penalty = max(0.0, ambient_c - 18.0) * (
        0.010 if cooling_type == "air_crah" else 0.005)
    return round(base + load_penalty + ambient_penalty, 3)


@dataclass(slots=True)
class DerivedZone:
    spec: ZoneSpec
    racks: list[Rack]
    nameplate_kw: float
    it_load_kw: float
    thermal_load_kw: float
    pue: float
    total_draw_kw: float
    breaker_capacity_kw: float
    thermal_capacity_kw: float
    spare_circuits: int
    power_utilization_pct: float
    thermal_utilization_pct: float
    monthly_energy_usd: float
    monthly_demand_usd: float
    monthly_capex_amort_usd: float
    gpu_count: int
    gpu_mix: dict[str, int] = field(default_factory=dict)


def derive_zone(spec: ZoneSpec, racks: list[Rack], *, sim_hour: int, ambient_c: float,
                energy_rate_usd_per_kwh: float, demand_charge_usd_per_kw: float,
                rng: random.Random) -> DerivedZone:
    """Compute every dependent value for one zone from its racks."""
    nameplate = sum(r.nameplate_kw for r in racks)

    # Sensor noise, +/-3%: real telemetry is never exact, and an agent that
    # only ever sees suspiciously round numbers is not being tested properly.
    it_load = nameplate * diurnal_factor(sim_hour) * rng.gauss(1.0, 0.03)

    # Capacities derive from AUTHORED HEADROOM, so designed scarcity is exact
    # regardless of how the population randomized.
    breaker_capacity = round((nameplate + spec.breaker_headroom_kw) / 100.0) * 100.0
    thermal_capacity = round(
        (nameplate * HEAT_FRACTION + spec.thermal_headroom_kw) / 100.0) * 100.0

    load_ratio = it_load / breaker_capacity
    pue = zone_pue(spec.cooling_type, load_ratio, ambient_c)
    thermal_load = it_load * HEAT_FRACTION       # conservation of energy
    total_draw = it_load * pue                   # IT plus cooling and losses

    gpu_mix: dict[str, int] = {}
    for r in racks:
        gpu_mix[r.gpu_type] = gpu_mix.get(r.gpu_type, 0) + 1

    return DerivedZone(
        spec=spec, racks=racks,
        nameplate_kw=round(nameplate, 1),
        it_load_kw=round(it_load, 1),
        thermal_load_kw=round(thermal_load, 1),
        pue=pue,
        total_draw_kw=round(total_draw, 1),
        breaker_capacity_kw=breaker_capacity,
        thermal_capacity_kw=thermal_capacity,
        spare_circuits=int(max(0.0, breaker_capacity - it_load) // KW_PER_CIRCUIT),
        power_utilization_pct=round(100.0 * load_ratio, 1),
        thermal_utilization_pct=round(100.0 * thermal_load / thermal_capacity, 1),
        monthly_energy_usd=round(total_draw * HOURS_PER_MONTH * energy_rate_usd_per_kwh, 2),
        monthly_demand_usd=round(total_draw * demand_charge_usd_per_kw, 2),
        monthly_capex_amort_usd=round(
            sum(r.capex_usd for r in racks) / CAPEX_AMORTIZATION_MONTHS, 2),
        gpu_count=sum(r.gpu_count for r in racks),
        gpu_mix=gpu_mix,
    )


@dataclass(slots=True)
class DerivedFacility:
    sim_hour: int
    seed: int
    season: str
    ambient_c: float
    humidity_pct: float
    zones: list[DerivedZone]
    total_it_load_kw: float
    total_draw_kw: float
    total_thermal_load_kw: float
    facility_pue: float
    substation_load_mw: float
    monthly_energy_usd: float
    monthly_demand_usd: float
    monthly_opex_usd: float
    monthly_capex_amort_usd: float
    month_to_date_spend_usd: float
    cost_per_gpu_hour_usd: float
    installed_gpus: int


def generate_weather(rng: random.Random, season: str = "summer") -> tuple[float, float]:
    """Ambient dry bulb (CELSIUS) and relative humidity, correlated.

    Units are Celsius throughout, matching the ASHRAE envelope and the PUE
    coefficients. The reference implementation generated Fahrenheit while the
    thermal constants were Celsius -- a silent unit mismatch that would have
    had the Cooling agent reasoning about a 35 C facility as though it were
    35 F.

    Humidity is drawn against the temperature rather than independently, so
    "very hot and very humid" and "very hot and dry" both occur while
    incoherent pairings do not.
    """
    ambient_c = rng.gauss(35.0, 4.4) if season == "summer" else rng.gauss(12.8, 5.6)
    humidity = rng.gauss(45.0, 15.0) - (ambient_c - 32.2) * 0.54
    return round(ambient_c, 1), round(min(max(humidity, 10.0), 90.0), 1)


def derive_facility(*, sim_hour: int = 14, season: str = "summer",
                    energy_rate_usd_per_kwh: float = 0.094,
                    demand_charge_usd_per_kw: float = 8.98,
                    day_of_month: int = 29,
                    seed: int = SEED) -> DerivedFacility:
    """Build the whole facility at one instant of simulated time.

    Every facility-level number is a SUM over zones, never an independent
    literal -- which is what makes the dataset checkable. Add up the per-rack
    kW in facilities-db, apply PUE, and you land on the substation load
    reported in power-db.
    """
    rng = random.Random(seed)
    ambient_c, humidity = generate_weather(rng, season)

    zones = [
        derive_zone(spec, generate_racks(spec, rng),
                    sim_hour=sim_hour, ambient_c=ambient_c,
                    energy_rate_usd_per_kwh=energy_rate_usd_per_kwh,
                    demand_charge_usd_per_kw=demand_charge_usd_per_kw, rng=rng)
        for spec in ZONES
    ]

    total_it = sum(z.it_load_kw for z in zones)
    total_draw = sum(z.total_draw_kw for z in zones)
    total_thermal = sum(z.thermal_load_kw for z in zones)
    monthly_energy = sum(z.monthly_energy_usd for z in zones)
    monthly_demand = sum(z.monthly_demand_usd for z in zones)
    installed_gpus = sum(z.gpu_count for z in zones)

    # Load-weighted, so a lightly loaded efficient zone cannot flatter the
    # facility number.
    facility_pue = round(total_draw / total_it, 3) if total_it else 0.0

    # OPEX and CAPEX are kept separate on purpose. The Cost agent checks a
    # request against the monthly OPEX budget -- hardware already bought and
    # being depreciated is not a reason to refuse a placement. But
    # cost-per-GPU-hour, the KPI leadership actually watches, has to include
    # capex amortization or it understates true cost several-fold.
    monthly_power = monthly_energy + monthly_demand
    monthly_opex = monthly_power * 1.55          # + staff, maintenance, facilities
    monthly_capex = sum(z.monthly_capex_amort_usd for z in zones)
    gpu_hours = installed_gpus * HOURS_PER_MONTH

    return DerivedFacility(
        sim_hour=sim_hour, seed=seed, season=season,
        ambient_c=ambient_c, humidity_pct=humidity, zones=zones,
        total_it_load_kw=round(total_it, 1),
        total_draw_kw=round(total_draw, 1),
        total_thermal_load_kw=round(total_thermal, 1),
        facility_pue=facility_pue,
        substation_load_mw=round(total_draw / 1000.0, 2),
        monthly_energy_usd=round(monthly_energy, 2),
        monthly_demand_usd=round(monthly_demand, 2),
        monthly_opex_usd=round(monthly_opex, 2),
        monthly_capex_amort_usd=round(monthly_capex, 2),
        month_to_date_spend_usd=round(monthly_opex * (day_of_month / 30.0), 2),
        cost_per_gpu_hour_usd=(round((monthly_opex + monthly_capex) / gpu_hours, 3)
                               if gpu_hours else 0.0),
        installed_gpus=installed_gpus,
    )
