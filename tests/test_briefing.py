"""Briefing sheet text, on hand-made reports (no network)."""

from datetime import datetime, timezone

import pytest

from weather_app.briefing import NOTICE, BriefingSheet
from weather_app.decision import STUDENT_LIMITS, evaluate_go_no_go
from weather_app.reports import MetarReport

FLIGHT = {"departure": "LEMD", "destination": "EGLL", "alternate": "LFPG"}
WHEN = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)


def make_report(icao: str, clouds) -> MetarReport:
    return MetarReport(
        icao=icao, name=icao, observed_at=WHEN, raw_text=f"METAR {icao} 160900Z 27005KT 9999 15/05 Q1020",
        flight_category="VFR", temperature_c=15.0, dewpoint_c=5.0, wind_direction_deg=270.0,
        wind_variable=False, wind_speed_kt=5.0, wind_gust_kt=None, visibility_km=9.66,
        visibility_at_least=True, pressure_hpa=1020.0, weather_codes=None, clouds=clouds,
        latitude=40.0, longitude=-3.0,
    )


def test_sheet_lists_three_airports_and_marks_the_missing_one():
    reports = {"LEMD": make_report("LEMD", []), "EGLL": make_report("EGLL", [("BKN", 1200)])}
    decision = evaluate_go_no_go(reports["LEMD"], [], STUDENT_LIMITS)
    sheet = BriefingSheet(FLIGHT, reports, decision, 671.0, created_at=WHEN)
    rows = sheet.airport_rows()
    assert [row["Role"] for row in rows] == ["Departure", "Destination", "Alternate"]
    assert rows[1]["Ceiling"] == "1,200 ft (366 m)"
    assert sheet.missing_airports == ["LFPG"]
    text = sheet.to_markdown()
    assert text.count(NOTICE) == 2
    assert "METAR LEMD" in text and "LFPG: no report available" in text
    assert f"Verdict: {decision.verdict}" in text
    assert sheet.file_name == "briefing_LEMD_EGLL_20261116_0900Z.md"


def test_sheet_validates_its_input():
    with pytest.raises(ValueError):
        BriefingSheet({"departure": "LEMD"}, {}, None, None)
    with pytest.raises(ValueError):
        BriefingSheet(FLIGHT, {}, None, 0)
    assert BriefingSheet(FLIGHT, {}, None, None).verdict is None
