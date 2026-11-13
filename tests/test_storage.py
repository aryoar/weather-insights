"""CSV store round-trip and observation de-duplication tests."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from weather_app.models import LocationSnapshot
from weather_app.reports import metar_from_api
from weather_app.storage import MetarStore, WeatherStore

FIXTURE = Path(__file__).parent / "fixtures" / "metar_example.json"


def _report():
    return metar_from_api(json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_weather_store_writes_and_reads_from_temporary_directory(tmp_path):
    store = WeatherStore(tmp_path / "weather.csv")
    snapshot = LocationSnapshot(
        city="Madrid", country="ES", observed_at=datetime(2026, 11, 13, 10, tzinfo=timezone.utc),
        temperature_c=14.0, feels_like_c=13.0, humidity_pct=70, wind_speed_mps=3.5,
        description="Clear sky", latitude=40.4, longitude=-3.7, pressure_hpa=1011.0,
        wind_direction_deg=200.0, visibility_m=10_000, clouds_pct=20,
    )

    store.append(snapshot)
    loaded = store.load()

    assert len(loaded) == 1
    assert loaded.iloc[0]["city"] == "Madrid"
    assert loaded.iloc[0]["observed_at"] == pd.Timestamp("2026-11-13T10:00:00Z")
    assert loaded.iloc[0]["temperature_c"] == 14.0
    assert loaded.iloc[0]["wind_speed_mps"] == 3.5


def test_metar_store_writes_reads_and_skips_same_observation_on_later_fetch(tmp_path):
    store = MetarStore(tmp_path / "metars.csv")
    report = _report()
    first_fetch = datetime(2026, 11, 13, 10, 2, tzinfo=timezone.utc)
    later_fetch = datetime(2026, 11, 13, 10, 22, tzinfo=timezone.utc)

    assert store.append_if_new(report, first_fetch) is True
    assert store.append_if_new(report, later_fetch) is False

    other_airport = _report()
    other_airport.icao = "EGLL"
    assert store.append_if_new(other_airport, later_fetch) is True
    loaded = store.load()

    assert len(loaded) == 2
    lemd = loaded.loc[loaded["icao"] == "LEMD"].iloc[0]
    assert lemd["flight_category"] == "VFR"
    assert lemd["observed_at"] == pd.Timestamp("2026-11-13T10:00:00Z")
    assert lemd["fetched_at"] == pd.Timestamp("2026-11-13T10:02:00Z")

    later_observation = _report()
    later_observation.observed_at = datetime(2026, 11, 13, 10, 30, tzinfo=timezone.utc)
    assert store.append_if_new(later_observation, later_fetch) is True
    assert len(store.load()) == 3
