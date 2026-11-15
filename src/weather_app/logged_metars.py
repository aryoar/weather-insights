"""Read logged METARs back as MetarReport objects (offline fallback).

When aviationweather.gov cannot be reached, the METAR trainer and the Go/No-Go page
use the latest REAL METAR we logged for each airport in data/metar_history.csv
(MetarStore.load()). Nothing is invented: a row that cannot be read is skipped and
reported, and an airport with no logged row simply has no report.
"""

import json
import math
from collections.abc import Iterable, Mapping
from datetime import datetime

import pandas as pd

from .reports import MetarReport


def _missing(value) -> bool:
    """True for None, NaN and NaT (how pandas shows an empty CSV cell)."""
    if value is None:
        return True
    if isinstance(value, float):
        return math.isnan(value)
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _number(value) -> float | None:
    return None if _missing(value) else float(value)


def _flag(value) -> bool:
    """CSV booleans come back as True/False, or as the text 'True'/'False'."""
    if _missing(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "1", "yes"}


def _text(value) -> str | None:
    return None if _missing(value) else str(value)


def _clouds(value) -> list[tuple[str, int | None]]:
    """The log stores cloud layers as JSON: [{"cover": "BKN", "base_ft": 800}, ...]."""
    if _missing(value) or not str(value).strip():
        return []
    layers = json.loads(value)
    return [
        (str(layer["cover"]), None if layer.get("base_ft") is None else int(layer["base_ft"]))
        for layer in layers
    ]


def _moment(value) -> datetime:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    return stamp.to_pydatetime()


def report_from_row(row: Mapping) -> MetarReport:
    """Rebuild one MetarReport from one row of the METAR history."""
    try:
        if _missing(row["icao"]) or _missing(row["raw_text"]) or _missing(row["observed_at"]):
            raise ValueError("missing airport, time or raw text")
        icao = str(row["icao"]).strip().upper()
        return MetarReport(
            icao=icao,
            name=_text(row.get("name")) or icao,
            observed_at=_moment(row["observed_at"]),
            raw_text=str(row["raw_text"]),
            flight_category=_text(row.get("flight_category")) or "UNKNOWN",
            temperature_c=_number(row.get("temperature_c")),
            dewpoint_c=_number(row.get("dewpoint_c")),
            wind_direction_deg=_number(row.get("wind_direction_deg")),
            wind_variable=_flag(row.get("wind_variable")),
            wind_speed_kt=_number(row.get("wind_speed_kt")),
            wind_gust_kt=_number(row.get("wind_gust_kt")),
            visibility_km=_number(row.get("visibility_km")),
            visibility_at_least=_flag(row.get("visibility_at_least")),
            pressure_hpa=_number(row.get("pressure_hpa")),
            weather_codes=_text(row.get("weather_codes")),
            clouds=_clouds(row.get("clouds")),
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
        )
    except (KeyError, TypeError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
        raise ValueError(f"A logged METAR for {row.get('icao', '?')} could not be read") from exc


def latest_logged_reports(
    history: pd.DataFrame, codes: Iterable[str] | None = None,
) -> tuple[list[MetarReport], dict[str, str]]:
    """Latest logged METAR per airport, plus a message for each airport without one.

    `codes` keeps the requested order; with no codes, every logged airport is returned.
    """
    wanted = None if codes is None else [str(code).strip().upper() for code in codes]
    errors: dict[str, str] = {}
    if history.empty or "icao" not in history or "observed_at" not in history:
        return [], {code: "No logged METAR history is available." for code in wanted or []}

    frame = history.copy()
    frame["icao"] = frame["icao"].astype(str).str.strip().str.upper()
    frame["observed_at"] = pd.to_datetime(frame["observed_at"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["observed_at"]).sort_values("observed_at", ascending=False)

    reports: list[MetarReport] = []
    for code in wanted if wanted is not None else list(dict.fromkeys(frame["icao"])):
        rows = frame.loc[frame["icao"] == code]
        if rows.empty:
            errors[code] = "No logged METAR for this airport yet."
            continue
        for _, row in rows.iterrows():  # newest first; skip unreadable rows
            try:
                reports.append(report_from_row(row))
                break
            except ValueError as exc:
                errors[code] = str(exc)
        else:
            continue
        errors.pop(code, None)
    return reports, errors
