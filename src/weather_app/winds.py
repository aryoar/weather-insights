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


# ---------------------------------------------------------------- along a route ----

def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle direction from point 1 to point 2, in degrees (0 = north, 90 = east)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    x = math.sin(d_lambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    return math.degrees(math.atan2(x, y)) % 360


def tracks_along(points: list[tuple[float, float]]) -> list[float]:
    """Direction of flight at each point of a route.

    A great circle changes direction as it goes (Madrid–London turns from about 10° to 12°;
    long routes turn much more), so each point uses the direction towards the next point; the last point
    keeps the direction it arrived with.
    """
    if len(points) < 2:
        raise ValueError("A route needs at least 2 points.")
    tracks = [bearing_deg(*a, *b) for a, b in zip(points, points[1:])]
    tracks.append(bearing_deg(*points[-2], *points[-1]) if len(points) == 2 else tracks[-1])
    return tracks


class RouteWinds:
    """Model winds at every cruise height, sampled at evenly spaced points along a route.

    `levels_per_point[i]` is the list of WindLevel objects above `points[i]`. A height that
    the model did not report at some point is simply averaged over the points that have it.
    """

    def __init__(self, route_name: str, distance_nm: float, points: list[tuple[float, float]],
                 levels_per_point: list[list[WindLevel]]) -> None:
        if len(points) != len(levels_per_point):
            raise ValueError("Need one list of wind levels per route point.")
        self.route_name = route_name
        self.distance_nm = distance_nm
        self.points = points
        self.levels_per_point = levels_per_point
        self._tracks = tracks_along(points)

    @property
    def distances_nm(self) -> list[float]:
        """Distance of each sample point from departure."""
        step = self.distance_nm / (len(self.points) - 1)
        return [round(i * step) for i in range(len(self.points))]

    @property
    def flight_levels(self) -> list[int]:
        """Flight levels reported at one or more points, lowest first."""
        return sorted({lvl.flight_level for levels in self.levels_per_point for lvl in levels})

    def headwinds_at(self, flight_level: int) -> list[float | None]:
        """Headwind (+) or tailwind (−) in kt at each point for one height (None = not reported)."""
        result: list[float | None] = []
        for levels, track in zip(self.levels_per_point, self._tracks):
            match = next((lvl for lvl in levels if lvl.flight_level == flight_level), None)
            result.append(None if match is None else match.headwind_kt(track))
        return result

    def average_headwind_kt(self, flight_level: int) -> float:
        """Mean headwind along the route at one height. Negative = tailwind on average."""
        values = [v for v in self.headwinds_at(flight_level) if v is not None]
        if not values:
            raise LookupError(f"No wind data for FL{flight_level:03d} on this route.")
        return round(sum(values) / len(values), 1)

    @property
    def best_flight_level(self) -> int:
        """The height with the least headwind (or strongest tailwind) on average."""
        if not self.flight_levels:
            raise LookupError("No wind data on this route.")
        return min(self.flight_levels, key=self.average_headwind_kt)

    def summary_rows(self) -> list[dict[str, Any]]:
        """One row per height, for a table: averages along the route."""
        rows = []
        for fl in self.flight_levels:
            found = [lvl for levels in self.levels_per_point for lvl in levels if lvl.flight_level == fl]
            headwind = self.average_headwind_kt(fl)
            rows.append({
                "flight_level": fl,
                "altitude_ft": found[0].altitude_ft,
                "altitude_m": found[0].altitude_m,
                "wind_speed_kt": round(sum(lvl.wind_speed_kt for lvl in found) / len(found)),
                "temperature_c": round(sum(lvl.temperature_c for lvl in found) / len(found)),
                "headwind_kt": headwind,
                "headwind_kmh": round(headwind * KMH_PER_KT),
            })
        return rows

    def __str__(self) -> str:
        best = self.best_flight_level
        return f"Winds aloft {self.route_name}: best FL{best:03d} (average headwind {self.average_headwind_kt(best):+.0f} kt)"

    def __repr__(self) -> str:
        return f"RouteWinds({self.route_name!r}, {len(self.points)} points, levels={self.flight_levels})"


def best_level_hint(route_winds: RouteWinds) -> str:
    """Plain-language hint, e.g. 'FL340 has the strongest tailwind on this route (+45 kt).'"""
    best = route_winds.best_flight_level
    value = route_winds.average_headwind_kt(best)
    if value < 0:
        return f"FL{best:03d} has the strongest tailwind on this route (+{-value:.0f} kt behind you)."
    if value == 0:
        return f"FL{best:03d} has no average headwind or tailwind on this route."
    return f"Every height has a headwind on this route; FL{best:03d} has the weakest ({value:.0f} kt)."


def average_headwind_kt(route: Any, flight_level: int, point_count: int = 8) -> float:
    """Hand-off for the Fuel planner: mean headwind (kt, negative = tailwind) at one cruise
    height along a weather_app.route.Route, from live Open-Meteo data.

    Raises the same errors as the API client (ConnectionError, RuntimeError, ...) if
    Open-Meteo cannot be reached, and LookupError if that height has no data.
    """
    from .client import OpenMeteoClient  # imported here: client.py already imports this module

    return OpenMeteoClient().route_winds(route, point_count).average_headwind_kt(flight_level)
