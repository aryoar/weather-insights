"""Fetch and append the fixed Weather Insights collection set.

Run from any directory with ``python scripts/log_weather.py``. Each run appends
successful OpenWeatherMap city observations and METAR reports to their CSV logs.
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "src"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from weather_app.client import AviationWeatherClient, WeatherClient
from weather_app.config import get_api_key
from weather_app.storage import MetarStore, WeatherStore

# Keep this collection set stable so rows remain comparable over time.
CITIES = ("Madrid", "London", "Paris")
AIRPORTS = ("LEMD", "EGLL", "LFPG")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Append real current weather for Madrid, London and Paris, plus "
            "METAR observations for LEMD, EGLL and LFPG, to data/*.csv."
        )
    )
    return parser


def _collect_openweathermap() -> tuple[int, list[str]]:
    try:
        client = WeatherClient(get_api_key())
    except RuntimeError as exc:
        return 0, [f"OpenWeatherMap setup: {exc}"]

    snapshots, errors = client.current_many(list(CITIES))
    store = WeatherStore()
    saved = 0
    for snapshot in snapshots:
        try:
            store.append(snapshot)
            saved += 1
        except (OSError, ValueError) as exc:
            errors[snapshot.location] = f"Fetched but could not save: {exc}"
    return saved, [f"OpenWeatherMap {city}: {message}" for city, message in errors.items()]


def _collect_metars() -> tuple[int, list[str]]:
    client = AviationWeatherClient()
    try:
        reports, errors = client.metars(list(AIRPORTS))
    except (ConnectionError, LookupError, PermissionError, RuntimeError, ValueError) as exc:
        return 0, [f"aviationweather.gov: {exc}"]

    store = MetarStore()
    saved = 0
    for report in reports:
        try:
            store.append(report)
            saved += 1
        except (OSError, ValueError) as exc:
            errors[report.icao] = f"Fetched but could not save: {exc}"
    return saved, [f"METAR {code}: {message}" for code, message in errors.items()]


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    weather_saved, weather_errors = _collect_openweathermap()
    metars_saved, metar_errors = _collect_metars()

    print(f"OpenWeatherMap: appended {weather_saved} row(s) to data/weather_history.csv.")
    print(f"METAR: appended {metars_saved} row(s) to data/metar_history.csv.")
    errors = weather_errors + metar_errors
    for message in errors:
        print(f"Warning: {message}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
