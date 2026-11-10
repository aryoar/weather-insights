"""Winds aloft: wind and temperature at cruise heights, and the headwind they give.

This is a model-based view built from Open-Meteo forecast data, NOT an official
SIGWX chart. All calculations live here; views/winds_aloft.py only displays them.

Pressure levels and the flight levels they roughly match (standard atmosphere):
850 hPa ≈ FL050, 700 ≈ FL100, 500 ≈ FL180, 300 ≈ FL300, 250 ≈ FL340, 200 ≈ FL390.
"""

import math
from typing import Any

# Pressure level (hPa) -> approximate flight level (hundreds of feet)
FLIGHT_LEVELS: dict[int, int] = {850: 50, 700: 100, 500: 180, 300: 300, 250: 340, 200: 390}

KMH_PER_KT = 1.852
M_PER_FT = 0.3048


def headwind_component(wind_speed_kt: float, wind_direction_deg: float, route_direction_deg: float) -> float:
    """Part of the wind blowing against the aircraft, in knots.

    Wind direction is where the wind comes FROM (as in METARs and weather models);
    route direction is where the aircraft is GOING. Positive = headwind (slower,
    more fuel), negative = tailwind (faster, less fuel), 0 = pure crosswind.

    headwind = wind speed × cos(wind direction − route direction)
    """
    angle = math.radians(wind_direction_deg - route_direction_deg)
    return round(wind_speed_kt * math.cos(angle), 1)


class WindLevel:
    """Model wind and temperature at one pressure level above one point."""

    def __init__(self, pressure_hpa: int, wind_speed_kt: float, wind_direction_deg: float, temperature_c: float) -> None:
        if pressure_hpa not in FLIGHT_LEVELS:
            raise ValueError(f"Unsupported pressure level: {pressure_hpa} hPa")
        if wind_speed_kt < 0:
            raise ValueError("Wind speed cannot be negative")
        self.pressure_hpa = pressure_hpa
        self.wind_speed_kt = wind_speed_kt
        self.wind_direction_deg = wind_direction_deg % 360
        self.temperature_c = temperature_c

    @property
    def flight_level(self) -> int:
        """Approximate flight level, e.g. 340 for 250 hPa."""
        return FLIGHT_LEVELS[self.pressure_hpa]

    @property
    def altitude_ft(self) -> int:
        """Approximate altitude in feet (FL340 ≈ 34,000 ft)."""
        return self.flight_level * 100

    @property
    def altitude_m(self) -> int:
        """Approximate altitude in metres, for readers who don't think in feet."""
        return round(self.altitude_ft * M_PER_FT)

    @property
    def wind_speed_kmh(self) -> float:
        return round(self.wind_speed_kt * KMH_PER_KT, 1)

    def headwind_kt(self, route_direction_deg: float) -> float:
        """Headwind (+) or tailwind (−) this level gives an aircraft flying the given direction."""
        return headwind_component(self.wind_speed_kt, self.wind_direction_deg, route_direction_deg)

    def __str__(self) -> str:
        return (
            f"FL{self.flight_level:03d} (~{self.altitude_ft:,} ft / {self.altitude_m:,} m): "
            f"wind from {self.wind_direction_deg:.0f}° at {self.wind_speed_kt:.0f} kt, {self.temperature_c:.0f} °C"
        )

    def __repr__(self) -> str:
        return (
            f"WindLevel({self.pressure_hpa}, wind_speed_kt={self.wind_speed_kt}, "
            f"wind_direction_deg={self.wind_direction_deg}, temperature_c={self.temperature_c})"
        )

    def __lt__(self, other: "WindLevel") -> bool:
        """Lower altitude first, so sorted(levels) goes from the ground up."""
        return self.altitude_ft < other.altitude_ft


def wind_levels_from_api(payload: dict[str, Any]) -> list[WindLevel]:
    """Turn an Open-Meteo `current` response into WindLevel objects, lowest first.

    A level the model did not report (missing or null values) is left out rather
    than filled in with a made-up number.
    """
    current = payload.get("current") if isinstance(payload, dict) else None
    if not isinstance(current, dict):
        raise ValueError("Open-Meteo response has no current weather data.")
    levels: list[WindLevel] = []
    for hpa in FLIGHT_LEVELS:
        speed = current.get(f"wind_speed_{hpa}hPa")
        direction = current.get(f"wind_direction_{hpa}hPa")
        temperature = current.get(f"temperature_{hpa}hPa")
        if speed is None or direction is None or temperature is None:
            continue
        levels.append(WindLevel(hpa, float(speed), float(direction), float(temperature)))
    return sorted(levels)
