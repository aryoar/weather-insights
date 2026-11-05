"""Domain objects for current and historical weather observations."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class LocationSnapshot:
    city: str
    country: str
    observed_at: datetime
    temperature_c: float
    feels_like_c: float
    humidity_pct: int
    wind_speed_mps: float
    description: str

    def __post_init__(self) -> None:
        if not self.city.strip():
            raise ValueError("City cannot be empty")
        if not 0 <= self.humidity_pct <= 100:
            raise ValueError("Humidity must be between 0 and 100 percent")

    @property
    def location(self) -> str:
        return f"{self.city}, {self.country}" if self.country else self.city

    @property
    def feels_like_delta_c(self) -> float:
        return self.feels_like_c - self.temperature_c

    @property
    def comfort_index(self) -> float:
        """Simple comparative score; higher means milder, less humid/windy weather."""
        humidity_penalty = max(0, self.humidity_pct - 60) * 0.1
        return self.temperature_c - self.wind_speed_mps * 0.5 - humidity_penalty

    def __repr__(self) -> str:
        return f"LocationSnapshot({self.location!r}, {self.temperature_c:.1f}°C)"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, LocationSnapshot):
            return NotImplemented
        return self.temperature_c < other.temperature_c


def snapshot_from_api(city: str, payload: dict, observed_at: datetime | None = None) -> LocationSnapshot:
    """Validate and convert an OpenWeatherMap current-weather response."""
    try:
        return LocationSnapshot(
            city=payload["name"] or city,
            country=payload.get("sys", {}).get("country", ""),
            observed_at=observed_at or datetime.now(timezone.utc),
            temperature_c=float(payload["main"]["temp"]),
            feels_like_c=float(payload["main"]["feels_like"]),
            humidity_pct=int(payload["main"]["humidity"]),
            wind_speed_mps=float(payload.get("wind", {}).get("speed", 0)),
            description=payload.get("weather", [{}])[0].get("description", "Unknown conditions").capitalize(),
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError("OpenWeatherMap returned an incomplete weather response") from exc
