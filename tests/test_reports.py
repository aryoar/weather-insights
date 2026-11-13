"""Tests for parsing a saved aviationweather.gov METAR example."""

import json
from pathlib import Path

import pytest

from weather_app.reports import KM_PER_MILE, metar_from_api


@pytest.fixture
def saved_metar_example():
    path = Path(__file__).parent / "fixtures" / "metar_example.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_metar_parser_reads_saved_example_response(saved_metar_example):
    report = metar_from_api(saved_metar_example)

    assert report.icao == "LEMD"
    assert report.flight_category == "VFR"
    assert report.observed_at.isoformat() == "2026-11-13T10:00:00+00:00"
    assert report.temperature_c == 14
    assert report.wind_speed_kt == 9
    assert report.wind_gust_kt == 24
    assert report.visibility_km == pytest.approx(6 * KM_PER_MILE)
    assert report.visibility_at_least is True
    assert report.ceiling_ft is None  # SCT layers do not define a ceiling.
    assert "METAR LEMD" in report.raw_text
