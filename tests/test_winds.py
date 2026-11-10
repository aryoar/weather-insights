"""Known-answer tests for the winds aloft logic (no network needed)."""

import pytest

from weather_app.winds import (
    RouteWinds,
    WindLevel,
    bearing_deg,
    best_level_hint,
    headwind_component,
    tracks_along,
    wind_levels_from_api,
)


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


# ---------------------------------------------------------------- along a route ----

def test_bearing_due_north_and_due_east():
    assert bearing_deg(0, 0, 10, 0) == pytest.approx(0)
    assert bearing_deg(0, 0, 0, 10) == pytest.approx(90)
    assert bearing_deg(10, 0, 0, 0) == pytest.approx(180)


def test_tracks_along_has_one_direction_per_point():
    points = [(0, 0), (0, 5), (0, 10)]  # flying east along the equator
    assert tracks_along(points) == pytest.approx([90, 90, 90])


def _levels(direction_by_fl: dict[int, float], speed: float = 40) -> list[WindLevel]:
    hpa_for = {50: 850, 100: 700, 180: 500, 300: 300, 340: 250, 390: 200}
    return [WindLevel(hpa_for[fl], speed, direction, -40) for fl, direction in direction_by_fl.items()]


def test_route_winds_average_and_best_height():
    # Flying east along the equator. At FL340 the wind comes from the west (behind: −40 kt);
    # at FL300 it comes from the east (on the nose: +40 kt).
    points = [(0, 0), (0, 5), (0, 10)]
    per_point = [_levels({300: 90, 340: 270}) for _ in points]
    winds = RouteWinds("TEST", 600, points, per_point)
    assert winds.flight_levels == [300, 340]
    assert winds.average_headwind_kt(300) == pytest.approx(40)
    assert winds.average_headwind_kt(340) == pytest.approx(-40)
    assert winds.best_flight_level == 340
    assert winds.distances_nm == [0, 300, 600]
    assert best_level_hint(winds) == "FL340 has the strongest tailwind on this route (+40 kt behind you)."


def test_route_winds_skips_a_height_missing_at_one_point():
    points = [(0, 0), (0, 10)]
    per_point = [_levels({340: 270}), []]  # second point: model reported nothing
    winds = RouteWinds("TEST", 600, points, per_point)
    assert winds.headwinds_at(340) == [pytest.approx(-40), None]
    assert winds.average_headwind_kt(340) == pytest.approx(-40)
    with pytest.raises(LookupError):
        winds.average_headwind_kt(300)
