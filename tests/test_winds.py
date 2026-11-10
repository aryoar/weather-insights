"""Known-answer tests for the winds aloft logic (no network needed)."""

import pytest

from weather_app.winds import WindLevel, headwind_component, wind_levels_from_api


def test_wind_on_the_nose_is_full_headwind():
    # Flying north (360°), wind from the north at 30 kt
    assert headwind_component(30, 360, 360) == pytest.approx(30)


def test_wind_from_behind_is_full_tailwind():
    # Flying north, wind from the south at 30 kt
    assert headwind_component(30, 180, 360) == pytest.approx(-30)


def test_wind_from_the_side_gives_no_headwind():
    # Flying north, wind from the east at 30 kt
    assert headwind_component(30, 90, 360) == pytest.approx(0)


def test_wind_at_60_degrees_gives_half_headwind():
    # cos(60°) = 0.5
    assert headwind_component(30, 60, 0) == pytest.approx(15)


def test_wind_level_properties():
    level = WindLevel(250, wind_speed_kt=50, wind_direction_deg=270, temperature_c=-50)
    assert level.flight_level == 340
    assert level.altitude_ft == 34_000
    assert level.altitude_m == 10_363
    assert level.wind_speed_kmh == pytest.approx(92.6)
    assert level.headwind_kt(90) == pytest.approx(-50)  # flying east with a west wind: tailwind


def test_parse_skips_missing_levels_and_sorts_lowest_first():
    payload = {
        "current": {
            "wind_speed_250hPa": 70, "wind_direction_250hPa": 250, "temperature_250hPa": -51,
            "wind_speed_850hPa": 10, "wind_direction_850hPa": 200, "temperature_850hPa": 5,
            "wind_speed_500hPa": None, "wind_direction_500hPa": 240, "temperature_500hPa": -20,
        }
    }
    levels = wind_levels_from_api(payload)
    assert [level.pressure_hpa for level in levels] == [850, 250]


def test_parse_rejects_response_without_current_data():
    with pytest.raises(ValueError):
        wind_levels_from_api({"error": True})
