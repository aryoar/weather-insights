"""Analytics checked on small hand-made histories with known answers (no network needed)."""

import pandas as pd
import pytest

from weather_app.analytics import (
    airport_ifr_lifr_share,
    comfort_ranking,
    daily_temperature_ranges,
    deduplicate_metar_observations,
    deduplicate_weather_observations,
    latest_comparison,
    temperature_trend,
)


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


def test_daily_temperature_range_requires_multiple_observations_per_local_day():
    history = _history([
        ("2026-11-12T08:00Z", "Madrid", "ES", 8.0, 7.0, 50, 2.0),
        ("2026-11-12T20:00Z", "Madrid", "ES", 17.0, 16.0, 50, 2.0),
        ("2026-11-13T08:00Z", "Madrid", "ES", 10.0, 9.0, 50, 2.0),
    ])
    daily = daily_temperature_ranges(history)
    first_day = daily.loc[daily["day"] == pd.Timestamp("2026-11-12").date()].iloc[0]
    second_day = daily.loc[daily["day"] == pd.Timestamp("2026-11-13").date()].iloc[0]
    assert first_day["min_temperature_c"] == 8.0
    assert first_day["max_temperature_c"] == 17.0
    assert first_day["temperature_range_c"] == 9.0
    assert first_day["observation_count"] == 2
    assert second_day["observation_count"] == 1
    assert pd.isna(second_day["temperature_range_c"])


def test_airport_ifr_lifr_share_ranks_reports_with_sample_size_and_local_date_filter():
    history = pd.DataFrame([
        {"observed_at": "2026-11-12T23:30:00Z", "icao": "LEMD", "name": "Madrid",
         "flight_category": "IFR"},  # Nov 13 in Madrid
        {"observed_at": "2026-11-13T09:00:00Z", "icao": "LEMD", "name": "Madrid",
         "flight_category": "VFR"},
        {"observed_at": "2026-11-13T09:00:00Z", "icao": "EGLL", "name": "London",
         "flight_category": "LIFR"},
        {"observed_at": "2026-11-14T00:30:00Z", "icao": "EGLL", "name": "London",
         "flight_category": "VFR"},
    ])
    ranked = airport_ifr_lifr_share(
        history, pd.Timestamp("2026-11-13").date(), pd.Timestamp("2026-11-13").date()
    )
    assert ranked["icao"].tolist() == ["EGLL", "LEMD"]
    assert ranked["ifr_lifr_share_pct"].tolist() == [100.0, 50.0]
    assert ranked["observation_count"].tolist() == [1, 2]
    assert airport_ifr_lifr_share(
        history, pd.Timestamp("2026-11-13").date(), pd.Timestamp("2026-11-13").date(), ["LEMD"]
    )["icao"].tolist() == ["LEMD"]


def test_airport_ifr_lifr_share_handles_invalid_range_and_empty_data():
    empty = pd.DataFrame(columns=["observed_at", "icao", "flight_category"])
    day = pd.Timestamp("2026-11-13").date()
    assert airport_ifr_lifr_share(empty, day, day).empty
    assert airport_ifr_lifr_share(HISTORY, day, day - pd.Timedelta(days=1)).empty


def test_weather_analytics_drops_matching_payloads_fetched_within_two_minutes():
    history = pd.DataFrame([
        {"observed_at": "2026-11-13T09:15:42Z", "city": "London", "country": "GB",
         "temperature_c": 6.22, "feels_like_c": 3.59, "humidity_pct": 94,
         "wind_speed_mps": 3.6, "description": "Mist"},
        {"observed_at": "2026-11-13T09:16:01Z", "city": "London", "country": "GB",
         "temperature_c": 6.22, "feels_like_c": 3.59, "humidity_pct": 94,
         "wind_speed_mps": 3.6, "description": "Mist"},
        {"observed_at": "2026-11-13T09:30:00Z", "city": "London", "country": "GB",
         "temperature_c": 6.22, "feels_like_c": 3.59, "humidity_pct": 94,
         "wind_speed_mps": 3.6, "description": "Mist"},
    ])
    unique = deduplicate_weather_observations(history)
    assert len(unique) == 2
    assert unique["observed_at"].tolist() == [
        pd.Timestamp("2026-11-13T09:15:42Z"),
        pd.Timestamp("2026-11-13T09:30:00Z"),
    ]


def test_metar_analytics_keeps_latest_fetch_per_airport_observation():
    history = pd.DataFrame([
        {"icao": "lemd", "observed_at": "2026-11-13T10:00:00Z",
         "fetched_at": "2026-11-13T10:02:00Z", "flight_category": "VFR"},
        {"icao": "LEMD", "observed_at": "2026-11-13T10:00:00+00:00",
         "fetched_at": "2026-11-13T10:22:00Z", "flight_category": "MVFR"},
        {"icao": "LEMD", "observed_at": "2026-11-13T10:30:00Z",
         "fetched_at": "2026-11-13T10:32:00Z", "flight_category": "VFR"},
    ])
    unique = deduplicate_metar_observations(history)
    assert len(unique) == 2
    assert unique.iloc[0]["icao"] == "LEMD"
    assert unique.iloc[0]["flight_category"] == "MVFR"
    assert unique.iloc[0]["fetched_at"] == pd.Timestamp("2026-11-13T10:22:00Z")
