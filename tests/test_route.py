"""Route geometry checked against hand-checkable answers."""

import pytest

from weather_app.route import Route, great_circle_nm

MADRID = (40.4936, -3.5668)   # LEMD
LONDON = (51.4775, -0.4614)   # EGLL


def test_madrid_london_is_about_670_nm():
    assert great_circle_nm(*MADRID, *LONDON) == pytest.approx(670, abs=10)


def test_one_degree_along_the_equator_is_60_nm():
    assert great_circle_nm(0, 0, 0, 1) == pytest.approx(60, abs=0.1)


def test_points_start_and_end_at_the_airports_and_are_evenly_spaced():
    route = Route("LEMD", "EGLL", MADRID, LONDON)
    points = route.points(5)
    assert len(points) == 5
    assert points[0] == pytest.approx(MADRID)
    assert points[-1] == pytest.approx(LONDON)
    gaps = [great_circle_nm(*a, *b) for a, b in zip(points, points[1:])]
    for gap in gaps:
        assert gap == pytest.approx(route.distance_nm / 4, rel=1e-6)


def test_distance_from_route():
    route = Route("LEMD", "EGLL", MADRID, LONDON)
    middle = route.points(3)[1]
    # 100 samples: at most half the gap between two samples away from the true answer (0).
    half_gap = route.distance_nm / 99 / 2
    assert route.distance_from_route_nm(*middle) <= half_gap
    # Paris (LFPG) is east of the Madrid-London line: roughly 100-200 nm off it.
    assert 100 < route.distance_from_route_nm(49.01, 2.55) < 200
    assert route.distance_from_route_nm(*MADRID) == pytest.approx(0, abs=0.01)


def test_bounding_box_contains_route_with_margin():
    route = Route("LEMD", "EGLL", MADRID, LONDON)
    min_lat, min_lon, max_lat, max_lon = route.bounding_box(margin_nm=60)
    assert min_lat == pytest.approx(MADRID[0] - 1, abs=0.01)   # 60 nm = 1 degree of latitude
    assert max_lat == pytest.approx(LONDON[0] + 1, abs=0.01)
    assert min_lon < MADRID[1] and max_lon > LONDON[1]
    assert not route.crosses_antimeridian


def test_pacific_route_crosses_antimeridian():
    tokyo, los_angeles = (35.55, 139.78), (33.94, -118.41)
    assert Route("RJTT", "KLAX", tokyo, los_angeles).crosses_antimeridian


def test_invalid_routes_are_refused():
    with pytest.raises(ValueError):
        Route("LEMD", "LEMD", MADRID, MADRID)
    with pytest.raises(ValueError):
        Route("XXXX", "EGLL", (95, 0), LONDON)
    with pytest.raises(ValueError):
        Route("LEMD", "EGLL", MADRID, LONDON).points(1)
