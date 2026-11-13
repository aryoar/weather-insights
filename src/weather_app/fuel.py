"""Educational fuel estimate for a flight. NOT for real flight planning.

Real inputs: the route distance (great circle between two real airports) and the average
headwind at the chosen cruise height (Open-Meteo, via weather_app.winds).
Scenario inputs (hypothetical, chosen by the user): the aircraft type, passengers, bags,
cargo and any extra fuel.

Fuel parts, in the order a dispatcher would add them up:
    taxi + trip + contingency (5% of trip) + alternate + final reserve (30 min) + extra
Trip time = distance / ground speed, and ground speed = cruise speed − headwind.

All aircraft numbers below are rough, rounded values chosen to be easy to check by hand.
They describe aircraft CLASSES, not any real model or airline.
"""

from dataclasses import dataclass

PASSENGER_KG = 84        # standard mass of an adult passenger with hand luggage
CHECKED_BAG_KG = 15      # standard mass of one checked bag
CONTINGENCY_SHARE = 0.05  # 5% of trip fuel, for anything unexpected on the way
FINAL_RESERVE_H = 0.5    # 30 minutes of flying, kept in the tanks at all times


@dataclass(frozen=True)
class AircraftProfile:
    """A hypothetical aircraft class with simplified, round performance numbers."""

    name: str
    seats: int
    cruise_speed_kt: float     # true airspeed at cruise (speed through the air)
    burn_kg_per_h: float       # fuel burned per hour with no payload on board
    burn_per_tonne_kg_h: float  # extra fuel per hour for each tonne of payload
    taxi_kg: float             # fuel used on the ground before take-off
    max_payload_kg: float
    max_fuel_kg: float
    # Cruise heights this class normally uses. The burn figures above only make sense here:
    # a jet burns far more per hour low down, and a turboprop cannot climb to jet heights.
    min_flight_level: int
    max_flight_level: int

    def can_cruise_at(self, flight_level: int) -> bool:
        return self.min_flight_level <= flight_level <= self.max_flight_level

    @property
    def cruise_range(self) -> str:
        """E.g. 'FL300–FL390'."""
        return f"FL{self.min_flight_level:03d}–FL{self.max_flight_level:03d}"

    def __str__(self) -> str:
        return (f"{self.name} ({self.seats} seats, cruise {self.cruise_speed_kt:.0f} kt "
                f"at {self.cruise_range})")


AIRCRAFT_PROFILES: dict[str, AircraftProfile] = {
    profile.name: profile
    for profile in (
        AircraftProfile("Regional turboprop", 70, 275, 650, 15, 60, 7_000, 5_000, 100, 180),
        AircraftProfile("Narrow-body jet", 180, 450, 2_200, 30, 200, 18_000, 19_000, 300, 390),
        AircraftProfile("Wide-body jet", 300, 490, 5_800, 40, 400, 50_000, 110_000, 300, 390),
    )
}


def total_payload_kg(passengers: int, bags: int, cargo_kg: float) -> float:
    """Everything the aircraft carries for its customers, in kg (standard masses)."""
    if passengers < 0 or bags < 0 or cargo_kg < 0:
        raise ValueError("Passengers, bags and cargo cannot be negative.")
    return passengers * PASSENGER_KG + bags * CHECKED_BAG_KG + cargo_kg


class FuelPlan:
    """Fuel needed for one flight, split into the parts a dispatcher adds up.

    Each part is a @property computed from the stored inputs, so changing nothing but
    (say) the headwind gives a consistent new plan with no stale numbers.
    """

    def __init__(self, profile: AircraftProfile, distance_nm: float, headwind_kt: float,
                 alternate_distance_nm: float, passengers: int = 0, bags: int = 0,
                 cargo_kg: float = 0, extra_kg: float = 0) -> None:
        if distance_nm <= 0:
            raise ValueError("The route distance must be greater than zero.")
        if alternate_distance_nm < 0:
            raise ValueError("The distance to the alternate cannot be negative.")
        if extra_kg < 0:
            raise ValueError("Extra fuel cannot be negative.")
        if passengers > profile.seats:
            raise ValueError(f"A {profile.name} has {profile.seats} seats, not {passengers}.")
        if headwind_kt >= profile.cruise_speed_kt:
            raise ValueError("The headwind is stronger than the aircraft's cruise speed.")
        self.profile = profile
        self.distance_nm = distance_nm
        self.headwind_kt = headwind_kt
        self.alternate_distance_nm = alternate_distance_nm
        self.passengers = passengers
        self.bags = bags
        self.cargo_kg = cargo_kg
        self.extra_kg = extra_kg
        total_payload_kg(passengers, bags, cargo_kg)  # refuse negative numbers now, not on first use

    @property
    def payload_kg(self) -> float:
        return total_payload_kg(self.passengers, self.bags, self.cargo_kg)

    # ---- speed and time

    @property
    def ground_speed_kt(self) -> float:
        """Speed over the ground: cruise speed minus headwind (a tailwind is a negative headwind)."""
        return self.profile.cruise_speed_kt - self.headwind_kt

    @property
    def trip_time_h(self) -> float:
        return self.distance_nm / self.ground_speed_kt

    @property
    def burn_kg_per_h(self) -> float:
        """Hourly burn for this payload: heavier aircraft burn more."""
        return self.profile.burn_kg_per_h + self.profile.burn_per_tonne_kg_h * self.payload_kg / 1000

    # ---- the fuel parts

    @property
    def taxi_kg(self) -> float:
        return self.profile.taxi_kg

    @property
    def trip_kg(self) -> float:
        return self.trip_time_h * self.burn_kg_per_h

    @property
    def contingency_kg(self) -> float:
        return self.trip_kg * CONTINGENCY_SHARE

    @property
    def alternate_kg(self) -> float:
        """Destination to alternate in still air: we have no wind data for that leg."""
        return self.alternate_distance_nm / self.profile.cruise_speed_kt * self.burn_kg_per_h

    @property
    def final_reserve_kg(self) -> float:
        return FINAL_RESERVE_H * self.burn_kg_per_h

    @property
    def block_fuel_kg(self) -> float:
        """Total fuel to load before engine start."""
        return sum(kg for _, kg in self.breakdown())

    # ---- checks and output

    @property
    def problems(self) -> list[str]:
        """Plain-language reasons this plan would not work with this aircraft (empty = fits)."""
        found = []
        if self.payload_kg > self.profile.max_payload_kg:
            found.append(f"Payload {self.payload_kg:,.0f} kg is over the {self.profile.max_payload_kg:,.0f} kg "
                         f"a {self.profile.name} can carry.")
        if self.block_fuel_kg > self.profile.max_fuel_kg:
            found.append(f"Fuel needed {self.block_fuel_kg:,.0f} kg is more than the "
                         f"{self.profile.max_fuel_kg:,.0f} kg the tanks hold.")
        return found

    def breakdown(self) -> list[tuple[str, float]]:
        """(part name, kg) in the order they are added up."""
        return [
            ("Taxi", self.taxi_kg),
            ("Trip", self.trip_kg),
            ("Contingency (5%)", self.contingency_kg),
            ("Alternate", self.alternate_kg),
            ("Final reserve (30 min)", self.final_reserve_kg),
            ("Extra", self.extra_kg),
        ]

    def with_headwind(self, headwind_kt: float) -> "FuelPlan":
        """The same flight at another headwind, e.g. to compare cruise heights."""
        return FuelPlan(self.profile, self.distance_nm, headwind_kt, self.alternate_distance_nm,
                        self.passengers, self.bags, self.cargo_kg, self.extra_kg)

    def __str__(self) -> str:
        return (f"{self.profile.name}, {self.distance_nm:,.0f} nm: {self.block_fuel_kg:,.0f} kg block fuel, "
                f"{self.trip_time_h * 60:.0f} min flight")

    def __repr__(self) -> str:
        return (f"FuelPlan({self.profile.name!r}, distance_nm={self.distance_nm:.0f}, "
                f"headwind_kt={self.headwind_kt:+.0f}, payload_kg={self.payload_kg:.0f})")

    def __lt__(self, other: object) -> bool:
        """Less fuel first, so sorted(plans) puts the cheapest option first."""
        if not isinstance(other, FuelPlan):
            return NotImplemented
        return self.block_fuel_kg < other.block_fuel_kg
