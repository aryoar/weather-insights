"""Fuel plan checked against round numbers you can work out by hand (no network needed)."""

import pytest

from weather_app.fuel import AIRCRAFT_PROFILES, AircraftProfile, FuelPlan, total_payload_kg

# Easy numbers: 400 kt cruise, 2,000 kg/h empty, +100 kg/h per tonne of payload, 200 kg taxi.
SIMPLE = AircraftProfile("Test jet", seats=100, cruise_speed_kt=400, burn_kg_per_h=2_000,
                         burn_per_tonne_kg_h=100, taxi_kg=200, max_payload_kg=10_000, max_fuel_kg=8_000,
                         min_flight_level=300, max_flight_level=390)


def test_payload_uses_standard_masses():
    # 10 × 84 + 4 × 15 + 100 = 840 + 60 + 100
    assert total_payload_kg(passengers=10, bags=4, cargo_kg=100) == 1_000


def test_cruise_range_includes_both_ends():
    assert SIMPLE.can_cruise_at(300) and SIMPLE.can_cruise_at(390)
    assert not SIMPLE.can_cruise_at(180)
    assert SIMPLE.cruise_range == "FL300–FL390"


def test_every_part_in_still_air():
    # 800 nm at 400 kt = 2 h. Empty aircraft burns 2,000 kg/h.
    plan = FuelPlan(SIMPLE, distance_nm=800, headwind_kt=0, alternate_distance_nm=200)
    assert plan.ground_speed_kt == 400
    assert plan.trip_time_h == pytest.approx(2)
    assert plan.taxi_kg == 200
    assert plan.trip_kg == pytest.approx(4_000)
    assert plan.contingency_kg == pytest.approx(200)    # 5% of 4,000
    assert plan.alternate_kg == pytest.approx(1_000)    # 200 nm / 400 kt = 0.5 h × 2,000
    assert plan.final_reserve_kg == pytest.approx(1_000)  # 30 min × 2,000
    assert plan.block_fuel_kg == pytest.approx(6_400)
    assert plan.problems == []


def test_headwind_makes_the_trip_longer_and_tailwind_shorter():
    # 600 nm against 100 kt: ground speed 300 kt, 2 h, 4,000 kg trip fuel
    headwind = FuelPlan(SIMPLE, distance_nm=600, headwind_kt=100, alternate_distance_nm=0)
    assert headwind.ground_speed_kt == 300
    assert headwind.trip_kg == pytest.approx(4_000)
    # Same distance with 100 kt behind: 500 kt, 1.2 h, 2,400 kg
    tailwind = headwind.with_headwind(-100)
    assert tailwind.trip_kg == pytest.approx(2_400)
    assert sorted([headwind, tailwind]) == [tailwind, headwind]  # less fuel first


def test_payload_increases_hourly_burn():
    # 2 tonnes of cargo: 2,000 + 2 × 100 = 2,200 kg/h
    plan = FuelPlan(SIMPLE, distance_nm=400, headwind_kt=0, alternate_distance_nm=0, cargo_kg=2_000)
    assert plan.burn_kg_per_h == pytest.approx(2_200)
    assert plan.trip_kg == pytest.approx(2_200)


def test_extra_fuel_is_added_to_the_total():
    base = FuelPlan(SIMPLE, distance_nm=800, headwind_kt=0, alternate_distance_nm=200)
    extra = FuelPlan(SIMPLE, distance_nm=800, headwind_kt=0, alternate_distance_nm=200, extra_kg=500)
    assert extra.block_fuel_kg - base.block_fuel_kg == pytest.approx(500)


def test_problems_report_overload_and_tanks_too_small():
    # 1,600 nm = 4 h × 2,000 = 8,000 kg trip alone: more than the 8,000 kg tanks once reserves are added
    plan = FuelPlan(SIMPLE, distance_nm=1_600, headwind_kt=0, alternate_distance_nm=0, cargo_kg=12_000)
    assert len(plan.problems) == 2


@pytest.mark.parametrize("kwargs", [
    {"distance_nm": 0},
    {"alternate_distance_nm": -1},
    {"extra_kg": -10},
    {"passengers": 101},          # more than the 100 seats
    {"passengers": -1},
    {"headwind_kt": 400},         # aircraft would never arrive
])
def test_invalid_inputs_are_refused(kwargs):
    values = {"distance_nm": 800, "headwind_kt": 0, "alternate_distance_nm": 200, **kwargs}
    with pytest.raises(ValueError):
        FuelPlan(SIMPLE, **values)


def test_built_in_profiles_are_consistent():
    for name, profile in AIRCRAFT_PROFILES.items():
        assert profile.name == name
        assert profile.cruise_speed_kt > 0 and profile.burn_kg_per_h > 0
        assert profile.min_flight_level < profile.max_flight_level


def test_turboprop_cannot_cruise_at_jet_heights():
    turboprop = AIRCRAFT_PROFILES["Regional turboprop"]
    jet = AIRCRAFT_PROFILES["Narrow-body jet"]
    assert turboprop.can_cruise_at(180) and not turboprop.can_cruise_at(390)
    assert jet.can_cruise_at(340) and not jet.can_cruise_at(50)
