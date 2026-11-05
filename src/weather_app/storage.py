"""Append-only CSV storage for successfully fetched observations."""

import csv
from pathlib import Path

import pandas as pd

from .models import LocationSnapshot

FIELDS = [
    "observed_at", "city", "country", "temperature_c", "feels_like_c",
    "humidity_pct", "wind_speed_mps", "description",
]


class WeatherStore:
    def __init__(self, path: str | Path = "data/weather_history.csv") -> None:
        self.path = Path(path)

    def append(self, snapshot: LocationSnapshot) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not self.path.exists() or self.path.stat().st_size == 0
        with self.path.open("a", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=FIELDS)
            if needs_header:
                writer.writeheader()
            writer.writerow({
                "observed_at": snapshot.observed_at.isoformat(),
                "city": snapshot.city,
                "country": snapshot.country,
                "temperature_c": snapshot.temperature_c,
                "feels_like_c": snapshot.feels_like_c,
                "humidity_pct": snapshot.humidity_pct,
                "wind_speed_mps": snapshot.wind_speed_mps,
                "description": snapshot.description,
            })

    def load(self) -> pd.DataFrame:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return pd.DataFrame(columns=FIELDS)
        frame = pd.read_csv(self.path)
        if "observed_at" in frame:
            frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True, errors="coerce")
        return frame.dropna(subset=["observed_at"])
