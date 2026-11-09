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
    latitude: float
    longitude: float
    pressure_hpa: float
    # Optional fields: OpenWeatherMap leaves these out of some responses
    # (e.g. no gust key when the wind is steady), so None means "not reported".
    wind_direction_deg: float | None = None
    wind_gust_mps: float | None = None
    visibility_m: int | None = None
    clouds_pct: int | None = None

    def __post_init__(self) -> None:
        if not self.city.strip():
            raise ValueError("City cannot be empty")
        if not 0 <= self.humidity_pct <= 100:
            raise ValueError("Humidity must be between 0 and 100 percent")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("Coordinates are outside the valid range")
        if self.clouds_pct is not None and not 0 <= self.clouds_pct <= 100:
            raise ValueError("Cloud cover must be between 0 and 100 percent")

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


def _optional_number(value, convert):
    """Convert a value that may be missing: None stays None, anything else is converted."""
    return None if value is None else convert(value)


def snapshot_from_api(city: str, payload: dict, observed_at: datetime | None = None) -> LocationSnapshot:
    """Validate and convert an OpenWeatherMap current-weather response."""
    try:
        wind = payload.get("wind", {})
        return LocationSnapshot(
            city=payload["name"] or city,
            country=payload.get("sys", {}).get("country", ""),
            observed_at=observed_at or datetime.now(timezone.utc),
            temperature_c=float(payload["main"]["temp"]),
            feels_like_c=float(payload["main"]["feels_like"]),
            humidity_pct=int(payload["main"]["humidity"]),
            wind_speed_mps=float(wind.get("speed", 0)),
            description=payload.get("weather", [{}])[0].get("description", "Unknown conditions").capitalize(),
            latitude=float(payload["coord"]["lat"]),
            longitude=float(payload["coord"]["lon"]),
            pressure_hpa=float(payload["main"]["pressure"]),
            wind_direction_deg=_optional_number(wind.get("deg"), float),
            wind_gust_mps=_optional_number(wind.get("gust"), float),
            visibility_m=_optional_number(payload.get("visibility"), int),
            clouds_pct=_optional_number(payload.get("clouds", {}).get("all"), int),
        )
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError("OpenWeatherMap returned an incomplete weather response") from exc
