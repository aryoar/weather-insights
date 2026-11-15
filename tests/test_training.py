"""METAR trainer questions, checked on hand-made reports with known answers (no network)."""

import random
from datetime import datetime, timezone

import pandas as pd
import pytest

from weather_app.logged_metars import latest_logged_reports, report_from_row
from weather_app.reports import MetarReport
from weather_app.training import (
    NO_CEILING,
    VISIBILITY_BANDS,
    MetarQuestion,
    Scoreboard,
    build_questions,
)


def make_report(**changes) -> MetarReport:
    """EGLL-like IFR report: 28008KT 9999 -RA BKN008 BKN012 09/08 Q0996."""
    fields = dict(
        icao="EGLL", name="London Heathrow", observed_at=datetime(2026, 11, 15, 19, 50, tzinfo=timezone.utc),
        raw_text="METAR EGLL 151950Z AUTO 28008KT 9999 -RA SCT004 BKN008 BKN012 09/08 Q0996 TEMPO RA",
        flight_category="IFR", temperature_c=9.0, dewpoint_c=8.0, wind_direction_deg=280.0,
        wind_variable=False, wind_speed_kt=8.0, wind_gust_kt=None, visibility_km=9.66,
        visibility_at_least=True, pressure_hpa=996.0, weather_codes="-RA",
        clouds=[("SCT", 400), ("BKN", 800), ("BKN", 1200)], latitude=51.48, longitude=-0.46,
    )
    fields.update(changes)
    return MetarReport(**fields)


def by_topic(report: MetarReport, seed: int = 1, count: int = 6) -> dict[str, MetarQuestion]:
    return {q.topic: q for q in build_questions(report, random.Random(seed), count=count)}


def test_five_questions_with_four_unique_options_by_default():
    questions = build_questions(make_report(), random.Random(7))
    assert len(questions) == 5
    for question in questions:
        assert len(question.options) == 4
        assert len(set(question.options)) == 4
        assert question.correct in question.options


def test_same_seed_gives_same_questions_and_order():
    first = [(q.topic, q.options) for q in build_questions(make_report(), random.Random(42))]
    second = [(q.topic, q.options) for q in build_questions(make_report(), random.Random(42))]
    assert first == second


def test_wind_answer_and_reciprocal_distractor():
    wind = by_topic(make_report())["Wind"]
    assert wind.correct == "From 280° at 8 kt (15 km/h)"
    assert "From 100° at 8 kt (15 km/h)" in wind.options  # "towards" instead of "from"
    assert wind.code_group == "28008KT"


def test_variable_and_calm_wind():
    assert by_topic(make_report(wind_variable=True, wind_direction_deg=None))["Wind"].correct.startswith(
        "Variable direction at 8 kt")
    assert by_topic(make_report(wind_speed_kt=0.0))["Wind"].correct == "Calm (no wind)"


def test_ceiling_is_lowest_broken_layer_not_lowest_cloud():
    ceiling = by_topic(make_report())["Ceiling"]
    assert ceiling.correct == "800 ft (240 m)"
    assert "400 ft (120 m)" in ceiling.options  # the SCT layer: the classic trap
    assert NO_CEILING in ceiling.options


def test_no_ceiling_when_only_scattered_clouds():
    ceiling = by_topic(make_report(clouds=[("SCT", 900), ("SCT", 2200)]))["Ceiling"]
    assert ceiling.correct == NO_CEILING
    assert "900 ft" in ceiling.explanation


def test_visibility_band_flight_category_temperature_and_qnh():
    questions = by_topic(make_report())
    assert questions["Visibility"].correct == VISIBILITY_BANDS[3]  # 9999 = 10 km or more
    assert questions["Flight category"].correct == "IFR"
    assert questions["Temperature / dew point"].correct == "Temperature 9 °C, dew point 8 °C"
    assert "Temperature 8 °C, dew point 9 °C" in questions["Temperature / dew point"].options  # swapped
    assert questions["QNH"].correct == "996 hPa"
    assert questions["QNH"].code_group == "Q0996"
    assert by_topic(make_report(visibility_km=3.0, visibility_at_least=False))["Visibility"].correct == VISIBILITY_BANDS[1]


def test_missing_fields_skip_their_questions():
    report = make_report(wind_speed_kt=None, pressure_hpa=None, flight_category="UNKNOWN")
    topics = {q.topic for q in build_questions(report, random.Random(1), count=6)}
    assert topics == {"Visibility", "Ceiling", "Temperature / dew point"}


def test_question_validates_its_options():
    with pytest.raises(ValueError):
        MetarQuestion("Wind", "?", ["a", "b"], "c", "")
    with pytest.raises(ValueError):
        MetarQuestion("Wind", "?", ["a", "a"], "a", "")
    question = MetarQuestion("Wind", "What?", ["a", "b"], "b", "because")
    assert question.is_correct("b") and not question.is_correct("a")
    assert str(question) == "[Wind] What? -> b"


def test_scoreboard_counts_and_percentage():
    board = Scoreboard()
    assert board.accuracy_pct is None
    for answer in (True, True, False, True):
        board.record(answer)
    assert (board.correct, board.answered, board.accuracy_pct) == (3, 4, 75.0)
    assert str(board) == "3/4 correct"


def test_logged_rows_become_reports_latest_first():
    rows = pd.DataFrame([
        {"observed_at": "2026-11-13T18:00:00+00:00", "icao": "LEMD", "name": "Madrid", "latitude": 40.4,
         "longitude": -3.5, "flight_category": "VFR", "temperature_c": 12.0, "dewpoint_c": 5.0,
         "wind_direction_deg": 220.0, "wind_variable": "False", "wind_speed_kt": 10.0, "wind_gust_kt": None,
         "visibility_km": 9.66, "visibility_at_least": "True", "pressure_hpa": 1021.0, "weather_codes": None,
         "clouds": '[{"cover":"FEW","base_ft":3000}]', "ceiling_ft": None, "raw_text": "METAR LEMD old"},
        {"observed_at": "2026-11-13T19:30:00+00:00", "icao": "lemd", "name": "Madrid", "latitude": 40.4,
         "longitude": -3.5, "flight_category": "MVFR", "temperature_c": 11.0, "dewpoint_c": 9.0,
         "wind_direction_deg": None, "wind_variable": True, "wind_speed_kt": 3.0, "wind_gust_kt": None,
         "visibility_km": 6.0, "visibility_at_least": False, "pressure_hpa": 1020.0, "weather_codes": "BR",
         "clouds": '[{"cover":"BKN","base_ft":2500}]', "ceiling_ft": 2500, "raw_text": "METAR LEMD new"},
    ])
    reports, errors = latest_logged_reports(rows, ["LEMD", "EDDF"])
    assert [r.raw_text for r in reports] == ["METAR LEMD new"]
    assert reports[0].wind_variable is True and reports[0].ceiling_ft == 2500
    assert "EDDF" in errors
    with pytest.raises(ValueError):
        report_from_row({"icao": "LEMD", "observed_at": "2026-11-13T19:30:00Z", "raw_text": "x",
                         "clouds": "not json", "latitude": 1, "longitude": 1})
