"""Append-only CSV storage for successfully fetched observations."""

import csv
from pathlib import Path

import pandas as pd

from .models import LocationSnapshot

# Always <project root>/data/weather_history.csv, no matter which folder the app is
# started from. Same idea as ENV_FILE in config.py: this file lives in
# src/weather_app/, so parents[2] is the project root.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "weather_history.csv"

FIELDS = [
    "observed_at", "city", "country", "latitude", "longitude",
    "temperature_c", "feels_like_c", "humidity_pct", "pressure_hpa",
    "wind_speed_mps", "wind_direction_deg", "wind_gust_mps",
    "visibility_m", "clouds_pct", "description",
]


class WeatherStore:
    def __init__(self, path: str | Path = DEFAULT_PATH) -> None:
        self.path = Path(path)

    def _has_rows(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def _check_header(self) -> None:
        """Refuse to append to a file written with a different column layout."""
        with self.path.open(newline="", encoding="utf-8") as file:
            header = next(csv.reader(file), [])
        if header != FIELDS:
            raise ValueError(
                f"{self.path.name} uses an older column format, so new rows were not saved. "
                "Convert or rename the old file before fetching again."
            )

    def append(self, snapshot: LocationSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not self._has_rows()
        if not needs_header:
            self._check_header()
        with self.path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            if needs_header:
                writer.writeheader()
            # Missing optional values (None) are written as empty cells,
            # which pandas reads back as NaN ("no value").
            writer.writerow({
                "observed_at": snapshot.observed_at.isoformat(),
                "city": snapshot.city,
                "country": snapshot.country,
                "latitude": snapshot.latitude,
                "longitude": snapshot.longitude,
                "temperature_c": snapshot.temperature_c,
                "feels_like_c": snapshot.feels_like_c,
                "humidity_pct": snapshot.humidity_pct,
                "pressure_hpa": snapshot.pressure_hpa,
                "wind_speed_mps": snapshot.wind_speed_mps,
                "wind_direction_deg": snapshot.wind_direction_deg,
                "wind_gust_mps": snapshot.wind_gust_mps,
                "visibility_m": snapshot.visibility_m,
                "clouds_pct": snapshot.clouds_pct,
                "description": snapshot.description,
            })

    def load(self) -> pd.DataFrame:
        if not self._has_rows():
            return pd.DataFrame(columns=FIELDS)
        frame = pd.read_csv(self.path)
        if "observed_at" in frame:
            frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True, errors="coerce")
        return frame.dropna(subset=["observed_at"])
