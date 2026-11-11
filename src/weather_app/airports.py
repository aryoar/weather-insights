"""Airport suitability calculations and live-data adapters for Weather Insights.

The labels are EDUCATIONAL indicators, not operational flight clearance.
METAR information and sunrise/sunset must come from real API responses.
"""

from __future__ import annotations

import csv
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

METAR_ENDPOINT = "https://aviationweather.gov/api/data/metar"
WEATHER_ENDPOINT = "https://api.openweathermap.org/data/2.5/weather"


@dataclass(frozen=True)
class RunwayEnd:
    """One usable direction of a runway (heading is true degrees)."""

    name: str
    heading_deg: float


@dataclass
class AirportAssessment:
    """Explanation of one airport's educational suitability result."""

    code: str
    status: str
    reasons: list[str] = field(default_factory=list)
    flight_category: str | None = None
    wind_speed_kt: float | None = None
    wind_direction_deg: float | None = None
    runway: str | None = None
    crosswind_kt: float | None = None
    is_daylight: bool | None = None
    sunset_local: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @property
    def color(self) -> list[int]:
        """Marker colour suitable for the PyDeck ScatterplotLayer."""
        return {
            "Usable": [34, 139, 34, 220],
            "Caution": [239, 170, 26, 220],
            "Not usable": [206, 54, 59, 220],
            "Unknown": [120, 120, 120, 220],
        }[self.status]

    def __str__(self) -> str:
        return f"{self.code}: {self.status} — {'; '.join(self.reasons)}"


def crosswind_kt(wind_dir: float, wind_speed: float, runway_heading: float) -> float:
    """Absolute crosswind component in knots.

    The wind direction and runway heading are in degrees. A 90-degree
    difference yields the full wind speed; 0/180 degrees yields zero.
    """
    for name, value in (
        ("wind_dir", wind_dir),
        ("wind_speed", wind_speed),
        ("runway_heading", runway_heading),
    ):
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f"{name} must be numeric")
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")
    if wind_speed < 0:
        raise ValueError("wind_speed must not be negative")
    diff = math.radians((wind_dir - runway_heading) % 360)
    return abs(wind_speed * math.sin(diff))


def _optional_number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        answer = float(value)
        return answer if math.isfinite(answer) else None
    except (TypeError, ValueError):
        return None


def _field(record, *names):
    """Support both raw API dictionaries and the group's model objects."""
    if record is None:
        return None
    for name in names:
        value = record.get(name) if isinstance(record, dict) else getattr(record, name, None)
        if value is not None:
            return value
    return None


def load_runways(path: str | Path) -> dict[str, list[RunwayEnd]]:
    """Read filtered OurAirports runways CSV; ignore ends without true headings."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}. Run scripts/prepare_runways.py first.")
    result: dict[str, list[RunwayEnd]] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            airport = (row.get("airport_ident") or "").strip().upper()
            if not airport or row.get("closed") == "1":
                continue
            for prefix in ("le", "he"):
                heading = _optional_number(row.get(f"{prefix}_heading_degT"))
                ident = (row.get(f"{prefix}_ident") or "").strip()
                if heading is not None and ident:
                    result.setdefault(airport, []).append(RunwayEnd(ident, heading))
    return result


def choose_runway(
    wind_dir: float, wind_speed: float, runways: list[RunwayEnd]
) -> tuple[RunwayEnd, float] | None:
    """Return the runway end with the smallest absolute crosswind."""
    if not runways:
        return None
    return min(
        ((runway, crosswind_kt(wind_dir, wind_speed, runway.heading_deg)) for runway in runways),
        key=lambda pair: pair[1],
    )


def get_metars(codes: list[str]) -> dict[str, dict]:
    """Retrieve real current METAR data for several ICAO codes in one call.

    When integrating with the group, this HTTP call can be replaced by
    AviationWeatherClient().metars(codes) in client.py.
    """
    import requests

    unique = list(dict.fromkeys(c.strip().upper() for c in codes if c.strip()))
    if not unique or any(len(c) != 4 or not c.isalpha() for c in unique):
        raise ValueError("Airport codes must contain exactly four letters (ICAO).")
    try:
        r = requests.get(
            METAR_ENDPOINT,
            params={"ids": ",".join(unique), "format": "json"},
            headers={"User-Agent": "WeatherInsightsClassProject/1.0"},
            timeout=20,
        )
        if r.status_code == 204:
            return {}
        r.raise_for_status()
        payload = r.json()
    except requests.Timeout as exc:
        raise ConnectionError("METAR request timed out.") from exc
    except requests.RequestException as exc:
        raise ConnectionError(f"METAR service failed: {exc}") from exc
    except ValueError as exc:
        raise ValueError("METAR service returned invalid JSON.") from exc
    if not isinstance(payload, list):
        raise ValueError("Unexpected METAR response format.")
    return {
        str(_field(row, "icaoId", "icao_id", "station") or "").upper(): row
        for row in payload
        if _field(row, "icaoId", "icao_id", "station")
    }


def get_daylight(lat: float, lon: float) -> dict | None:
    """Request real sunrise/sunset. Return None if no key configured.

    Coordinates are airport coordinates, not values typed as weather.
    The group can swap this adapter for WeatherClient.current_at().
    """
    import requests

    try:
        from dotenv import load_dotenv
        load_dotenv("variables.env")
    except ImportError:
        pass
    key = os.getenv("OPENWEATHER_API_KEY") or os.getenv("OPENWEATHERMAP_API_KEY")
    if not key:
        return None
    try:
        r = requests.get(
            WEATHER_ENDPOINT,
            params={"lat": lat, "lon": lon, "appid": key, "units": "metric"},
            timeout=20,
        )
        if r.status_code == 401:
            raise ValueError("OpenWeatherMap API key is missing, inactive or invalid.")
        r.raise_for_status()
        data = r.json()
        sunrise, sunset = data.get("sys", {}).get("sunrise"), data.get("sys", {}).get("sunset")
        if sunrise is None or sunset is None:
            return None
        offset = int(data.get("timezone", 0))
        local_tz = timezone(timedelta(seconds=offset))
        local_sunset = datetime.fromtimestamp(sunset, tz=local_tz).strftime("%H:%M UTC%z")
        return {
            "is_daylight": int(sunrise) <= datetime.now(timezone.utc).timestamp() < int(sunset),
            "sunset_local": local_sunset,
        }
    except requests.Timeout as exc:
        raise ConnectionError("Sunrise/sunset request timed out.") from exc
    except requests.RequestException as exc:
        raise ConnectionError("OpenWeatherMap is temporarily unavailable; check your connection or API access.") from exc
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError(f"Invalid sunrise/sunset response: {exc}") from exc


def assess_airport(
    code: str,
    metar: dict | object | None,
    runways: list[RunwayEnd],
    daylight: dict | None = None,
    *,
    crosswind_limit_kt: float = 30,
    runway_closed_scenario: bool = False,
    night_closed_scenario: bool = False,
    strike_scenario: bool = False,
) -> AirportAssessment:
    """Combine REAL observations with plainly marked HYPOTHETICAL restrictions."""
    if crosswind_limit_kt <= 0:
        raise ValueError("Example crosswind limit must be above zero.")
    reasons: list[str] = []
    wind_dir = _optional_number(_field(metar, "wdir", "wind_dir", "wind_direction_deg"))
    wind_speed = _optional_number(_field(metar, "wspd", "wind_speed_kt", "wind_speed"))
    category = _field(metar, "fltCat", "flight_category", "flight_cat")
    category = str(category).upper() if category else None
    latitude = _optional_number(_field(metar, "lat", "latitude"))
    longitude = _optional_number(_field(metar, "lon", "longitude"))

    if metar is None:
        status = "Unknown"
        reasons.append("No recent METAR reported; weather suitability unknown")
    else:
        status = "Usable"
        if category is None:
            status = "Caution"
            reasons.append("Flight category not reported")
        elif category in {"MVFR", "IFR", "LIFR"}:
            status = "Caution"
            reasons.append(f"{category} conditions require additional flight assessment")
        else:
            reasons.append(f"Reported flight category: {category}")

    selected_runway = None
    crosswind = None
    if not runways:
        reasons.append("Runway heading data not available")
        if status == "Usable":
            status = "Caution"
    elif wind_dir is None or wind_speed is None:
        reasons.append("Wind direction/speed not reported; crosswind cannot be calculated")
        if status == "Usable":
            status = "Caution"
    else:
        best = choose_runway(wind_dir, wind_speed, runways)
        if best:
            selected_runway, crosswind = best[0].name, best[1]
            reasons.append(f"Lowest crosswind: {crosswind:.1f} kt on runway {selected_runway}")
            if crosswind > crosswind_limit_kt:
                status = "Not usable"
                reasons.append(f"Above example crosswind limit of {crosswind_limit_kt:.0f} kt")

    is_daylight = daylight.get("is_daylight") if daylight else None
    sunset_local = daylight.get("sunset_local") if daylight else None
    if is_daylight is True:
        reasons.append(f"Daylight; sunset {sunset_local or 'not reported'}")
    elif is_daylight is False:
        reasons.append("Nighttime according to sunrise/sunset API")
    else:
        reasons.append("Sunrise/sunset data not available")

    if runway_closed_scenario:
        status = "Not usable"
        reasons.append("SCENARIO: assume all usable runways closed for maintenance")
    if strike_scenario:
        status = "Not usable"
        reasons.append("SCENARIO: airport unavailable due to strike")
    if night_closed_scenario:
        if is_daylight is False:
            status = "Not usable"
            reasons.append("SCENARIO: airport closed at night")
        elif is_daylight is None:
            if status != "Not usable":
                status = "Caution"
            reasons.append("SCENARIO: night closure cannot be checked without sunrise/sunset data")
        else:
            reasons.append("SCENARIO: night closure enabled, currently daylight")

    return AirportAssessment(
        code=code.upper(), status=status, reasons=reasons,
        flight_category=category, wind_speed_kt=wind_speed,
        wind_direction_deg=wind_dir, runway=selected_runway,
        crosswind_kt=crosswind, is_daylight=is_daylight,
        sunset_local=sunset_local, latitude=latitude, longitude=longitude,
    )
