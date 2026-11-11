"""Pure tests: no API key or internet needed."""

import pytest
from weather_app.airports import RunwayEnd, assess_airport, choose_runway, crosswind_kt


def test_crosswind_perpendicular():
    assert crosswind_kt(90, 20, 0) == pytest.approx(20)


def test_crosswind_parallel():
    assert crosswind_kt(0, 20, 0) == pytest.approx(0, abs=1e-10)
    assert crosswind_kt(180, 20, 0) == pytest.approx(0, abs=1e-10)


def test_choose_lowest_crosswind():
    result = choose_runway(90, 20, [RunwayEnd("18", 180), RunwayEnd("09", 90)])
    assert result is not None
    assert result[0].name == "09"
    assert result[1] == pytest.approx(0, abs=1e-10)


def test_scenario_strike_turns_red():
    observation = {"fltCat": "VFR", "wdir": 90, "wspd": 12, "lat": 40, "lon": -3}
    runways = [RunwayEnd("09", 90)]
    normal = assess_airport("TEST", observation, runways)
    strike = assess_airport("TEST", observation, runways, strike_scenario=True)
    assert normal.status == "Usable"
    assert strike.status == "Not usable"


def test_missing_data_is_not_green():
    result = assess_airport("ZZZZ", None, [])
    assert result.status == "Unknown"
