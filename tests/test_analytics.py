"""Analytics checked on small hand-made histories with known answers (no network needed)."""

import pandas as pd
import pytest

from weather_app.analytics import comfort_ranking, latest_comparison, temperature_trend


def _history(rows: list[tuple]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=["observed_at", "city", "country", "temperature_c",
                                        "feels_like_c", "humidity_pct", "wind_speed_mps"])
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True)
    return frame


HISTORY = _history([
    # observed_at,          city,     country, temp, feels, humidity, wind
    ("2026-11-10T09:00Z", "Madrid", "ES", 10.0, 9.0, 50, 2.0),
    ("2026-11-12T09:00Z", "Madrid", "ES", 20.0, 19.0, 50, 2.0),   # latest Madrid
    ("2026-11-11T09:00Z", "Madrid", "ES", 15.0, 14.0, 50, 2.0),   # out of order on purpose
    ("2026-11-12T09:00Z", "London", "GB", 6.0, 3.0, 90, 4.0),     # only London row
])


def test_trend_returns_one_location_in_time_order():
    trend = temperature_trend(HISTORY, "madrid, es")  # case does not matter
    assert trend["temperature_c"].tolist() == [10.0, 15.0, 20.0]


def test_trend_for_unknown_location_is_empty():
    assert temperature_trend(HISTORY, "Oslo, NO").empty


def test_latest_comparison_keeps_newest_row_per_location_warmest_first():
    latest = latest_comparison(HISTORY)
    assert latest["location"].tolist() == ["Madrid, ES", "London, GB"]
    assert latest["temperature_c"].tolist() == [20.0, 6.0]
    # feels-like delta = feels like − actual
    assert latest["feels_like_delta_c"].tolist() == pytest.approx([-1.0, -3.0])


def test_comfort_ranking_uses_the_documented_formula():
    ranking = comfort_ranking(HISTORY)
    # Madrid: 20 − 0.5 × 2 − 0 = 19.   London: 6 − 0.5 × 4 − (90 − 60) × 0.1 = 1
    assert ranking["location"].tolist() == ["Madrid, ES", "London, GB"]
    assert ranking["comfort_index"].tolist() == pytest.approx([19.0, 1.0])


def test_comfort_ranking_can_differ_from_temperature_order():
    # Warmer but very windy and humid Seville ranks below cooler, calm Lisbon.
    history = _history([
        ("2026-11-12T09:00Z", "Seville", "ES", 22.0, 22.0, 100, 10.0),  # 22 − 5 − 4 = 13
        ("2026-11-12T09:00Z", "Lisbon", "PT", 18.0, 18.0, 50, 0.0),     # 18
    ])
    assert comfort_ranking(history)["location"].tolist() == ["Lisbon, PT", "Seville, ES"]
    assert latest_comparison(history)["location"].tolist() == ["Seville, ES", "Lisbon, PT"]


def test_empty_history_gives_empty_results():
    empty = HISTORY.iloc[0:0]
    assert latest_comparison(empty).empty
    assert comfort_ranking(empty).empty
    assert temperature_trend(empty, "Madrid, ES").empty
