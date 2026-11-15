"""Go/No-Go checks on hand-made reports with known answers (no network)."""

from datetime import datetime, timezone

import pytest

from weather_app.airports import RunwayEnd
from weather_app.decision import (
    STUDENT_LIMITS,
    PilotLimits,
    apply_scenario,
    evaluate_go_no_go,
    flight_category_for,
    grade_choice,
)
from weather_app.reports import MetarReport

# One runway pointing east/west: wind from 090° is straight down it, from 360° straight across.
RUNWAYS = [RunwayEnd("09", 90.0), RunwayEnd("27", 270.0)]


def make_report(**changes) -> MetarReport:
    """A clear VFR day: wind 090/06, 10 km+, no ceiling."""
    fields = dict(
        icao="LEMD", name="Madrid", observed_at=datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc),
        raw_text="METAR LEMD 151200Z 09006KT 9999 FEW040 15/05 Q1020", flight_category="VFR",
        temperature_c=15.0, dewpoint_c=5.0, wind_direction_deg=90.0, wind_variable=False,
        wind_speed_kt=6.0, wind_gust_kt=None, visibility_km=9.66, visibility_at_least=True,
        pressure_hpa=1020.0, weather_codes=None, clouds=[("FEW", 4000)], latitude=40.47, longitude=-3.56,
    )
    fields.update(changes)
    return MetarReport(**fields)


def statuses(decision) -> dict[str, str]:
    return {check.name: check.status for check in decision.checks}


def test_clear_day_is_go():
    decision = evaluate_go_no_go(make_report(), RUNWAYS, STUDENT_LIMITS)
    assert decision.verdict == "GO"
    assert decision.runway in ("09", "27")
    assert set(statuses(decision).values()) == {"Pass"}


def test_strong_crosswind_is_no_go():
    decision = evaluate_go_no_go(make_report(wind_direction_deg=360.0, wind_speed_kt=15.0), RUNWAYS, STUDENT_LIMITS)
    assert decision.verdict == "NO-GO"
    assert statuses(decision)["Crosswind"] == "Fail"
    assert "15 kt" in decision.reasons[0]


def test_crosswind_uses_the_gust():
    # 8 kt straight across passes, but the 14 kt gust does not.
    report = make_report(wind_direction_deg=360.0, wind_speed_kt=8.0, wind_gust_kt=14.0)
    assert statuses(evaluate_go_no_go(report, RUNWAYS, STUDENT_LIMITS))["Crosswind"] == "Fail"


def test_low_ceiling_and_poor_visibility_fail():
    report = make_report(clouds=[("BKN", 1000)], visibility_km=3.0, visibility_at_least=False,
                         flight_category="IFR")
    result = statuses(evaluate_go_no_go(report, RUNWAYS, STUDENT_LIMITS))
    assert result["Ceiling"] == "Fail" and result["Visibility"] == "Fail" and result["Flight category"] == "Fail"


def test_close_to_a_limit_is_caution():
    report = make_report(clouds=[("BKN", 1600)])  # 1,600 ft vs 1,500 ft minimum
    decision = evaluate_go_no_go(report, RUNWAYS, STUDENT_LIMITS)
    assert decision.verdict == "CAUTION"
    assert statuses(decision)["Ceiling"] == "Pass (close to limit)"


def test_gust_spread():
    report = make_report(wind_speed_kt=5.0, wind_gust_kt=18.0)  # spread 13 kt > 10 kt
    assert statuses(evaluate_go_no_go(report, RUNWAYS, STUDENT_LIMITS))["Gust spread"] == "Fail"


def test_without_runway_data_uses_worst_case():
    light = evaluate_go_no_go(make_report(wind_speed_kt=4.0), [], STUDENT_LIMITS)
    assert statuses(light)["Crosswind"] == "Pass"  # even straight across it is inside the limit
    strong = evaluate_go_no_go(make_report(wind_speed_kt=14.0), [], STUDENT_LIMITS)
    assert statuses(strong)["Crosswind"] == "Unknown"
    assert strong.verdict == "CAUTION"


def test_vfr_check_only_when_required():
    relaxed = PilotLimits(15, 3, 1000, 15, vfr_required=False)
    names = [check.name for check in evaluate_go_no_go(make_report(), RUNWAYS, relaxed).checks]
    assert "Flight category" not in names


def test_limits_are_validated():
    with pytest.raises(ValueError):
        PilotLimits(0, 5, 1500, 10)
    with pytest.raises(ValueError):
        PilotLimits(10, 5, -1, 10)
    assert "VFR only" in STUDENT_LIMITS.summary


def test_grading_the_students_choice():
    go = evaluate_go_no_go(make_report(), RUNWAYS, STUDENT_LIMITS)
    no_go = evaluate_go_no_go(make_report(clouds=[("OVC", 500)], flight_category="LIFR"), RUNWAYS, STUDENT_LIMITS)
    caution = evaluate_go_no_go(make_report(clouds=[("BKN", 1600)]), RUNWAYS, STUDENT_LIMITS)
    assert grade_choice("GO", go)[0] is True
    assert grade_choice("NO-GO", go)[0] is False
    assert grade_choice("GO", no_go)[0] is False
    assert grade_choice("NO-GO", no_go)[0] is True
    assert grade_choice("GO", caution)[0] and grade_choice("NO-GO", caution)[0]
    with pytest.raises(ValueError):
        grade_choice("MAYBE", go)


@pytest.mark.parametrize("visibility_km, ceiling_ft, expected", [
    (10, None, "VFR"), (10, 3000, "MVFR"), (6, None, "MVFR"), (10, 800, "IFR"),
    (3, None, "IFR"), (10, 400, "LIFR"), (1, None, "LIFR"),
])
def test_flight_category_rules(visibility_km, ceiling_ft, expected):
    assert flight_category_for(visibility_km, ceiling_ft) == expected


def test_scenario_changes_only_what_is_asked_and_recomputes_category():
    real = make_report()
    scenario = apply_scenario(real, wind_speed_kt=20.0, ceiling_ft=900)
    assert scenario.wind_speed_kt == 20.0 and scenario.wind_direction_deg == 90.0
    assert scenario.ceiling_ft == 900 and scenario.flight_category == "IFR"
    assert real.ceiling_ft is None and real.wind_speed_kt == 6.0  # the real report is untouched
    cleared = apply_scenario(make_report(clouds=[("BKN", 700)]), clear_ceiling=True)
    assert cleared.ceiling_ft is None
    with pytest.raises(ValueError):
        apply_scenario(real, visibility_km=0)
