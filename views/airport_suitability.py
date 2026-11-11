"""Tab 4: airport suitability (educational only)."""

from __future__ import annotations

from pathlib import Path

import streamlit as st
import pydeck as pdk
from weather_app.airports import assess_airport, get_daylight, get_metars, load_runways

RUNWAY_FILE = Path("data/runways.csv")


def _code(value):
    """Extract an ICAO string from common shared-route representations."""
    if isinstance(value, str):
        value = value.strip().upper()
        return value if len(value) == 4 and value.isalpha() else None
    if isinstance(value, dict):
        for key in ("icao", "code", "airport_code", "icao_code"):
            candidate = _code(value.get(key))
            if candidate:
                return candidate
    for key in ("icao", "code", "airport_code", "icao_code"):
        candidate = _code(getattr(value, key, None)) if value is not None else None
        if candidate:
            return candidate
    return None


def _route_codes():
    """Prefer Rebeca's get_route(); fall back if its interface isn't ready yet."""
    try:
        from views.common import get_route
    except ImportError:
        get_route = None

    if get_route is not None:
        route = get_route()
        if isinstance(route, dict):
            codes = [
                _code(route.get("departure") or route.get("origin")),
                _code(route.get("destination") or route.get("arrival")),
                _code(route.get("alternate") or route.get("alternative")),
            ]
            if codes[0] and codes[1]:
                return list(dict.fromkeys(code for code in codes if code))
        if isinstance(route, (tuple, list)) and len(route) >= 2:
            codes = [_code(item) for item in route[:3]]
            if codes[0] and codes[1]:
                return list(dict.fromkeys(code for code in codes if code))

    st.sidebar.caption("Route input (temporary fallback until the shared sidebar is integrated)")
    departure = st.sidebar.text_input("Departure ICAO", "LEMD", key="suit_departure")
    destination = st.sidebar.text_input("Destination ICAO", "EGLL", key="suit_destination")
    alternate = st.sidebar.text_input("Alternate ICAO", "EGKK", key="suit_alternate")
    codes = [x.strip().upper() for x in (departure, destination, alternate) if x.strip()]
    if not all(len(code) == 4 and code.isalpha() for code in codes):
        st.error("Each airport needs a four-letter ICAO code, such as LEMD.")
        return []
    return list(dict.fromkeys(codes))


def _scenario_banner(message):
    try:
        from views.common import scenario_banner
        scenario_banner(message)
    except ImportError:
        st.warning(f"SCENARIO — {message}")


def _glossary():
    try:
        from weather_app.glossary import GLOSSARY
        from views.common import show_glossary
    except ImportError:
        return
    # Never request keys absent from the group's glossary.
    names = [name for name in ("ICAO", "METAR", "crosswind", "VFR", "IFR", "runway") if name in GLOSSARY]
    if names:
        show_glossary(names)


@st.cache_data(ttl=300, show_spinner=False)
def _live_metars(codes: tuple[str, ...]):
    return get_metars(list(codes))


@st.cache_data(ttl=300, show_spinner=False)
def _live_sun(lat: float, lon: float):
    return get_daylight(lat, lon)


def _fallback_coords(code, raw_runways):
    """Use genuine runway-end coordinates when METAR lacks a position."""
    for row in raw_runways:
        if row.get("airport_ident", "").upper() != code:
            continue
        for prefix in ("le", "he"):
            try:
                return float(row[f"{prefix}_latitude_deg"]), float(row[f"{prefix}_longitude_deg"])
            except (ValueError, TypeError, KeyError):
                continue
    return None


def _raw_runways():
    import csv
    if not RUNWAY_FILE.exists():
        return []
    with RUNWAY_FILE.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def render():
    st.title("Airport Suitability — Tab 4")
    st.write(
        "This educational view compares airport weather using live METAR observations, "
        "runway headings from OurAirports, and sunrise/sunset from OpenWeatherMap. "
        "It is not official flight-planning advice."
    )
    codes = _route_codes()
    if not codes:
        st.info("Choose valid airport codes to continue.")
        return

    _scenario_banner("The switches and crosswind limit below are hypothetical, not real NOTAM closures.")
    target = st.sidebar.selectbox("Apply scenarios to airport", codes, key="suit_scenario_airport")
    runway_closed = st.sidebar.checkbox("All runways closed for maintenance", key="suit_closed")
    night_closed = st.sidebar.checkbox("Airport closed at night", key="suit_night")
    strike = st.sidebar.checkbox("Airport strike", key="suit_strike")
    limit = st.sidebar.number_input(
        "Example aircraft crosswind limit (knots)",
        min_value=1, max_value=80, value=30, step=1,
        help="Illustrative aircraft limit, not a certified limit for any real aircraft.",
    )

    try:
        runways_by_airport = load_runways(RUNWAY_FILE)
    except FileNotFoundError as exc:
        st.error(str(exc))
        st.code("uv run python scripts/prepare_runways.py LEMD EGLL EGKK")
        return

    try:
        metars = _live_metars(tuple(codes))
    except (ConnectionError, ValueError) as exc:
        st.error(f"Live METAR data unavailable: {exc}")
        metars = {}

    raw_runways = _raw_runways()
    assessments = []
    for code in codes:
        metar = metars.get(code)
        lat, lon = None, None
        if metar is not None:
            try:
                lat = float(metar.get("lat"))
                lon = float(metar.get("lon"))
            except (TypeError, ValueError):
                pass
        if lat is None or lon is None:
            coordinates = _fallback_coords(code, raw_runways)
            if coordinates:
                lat, lon = coordinates

        daylight = None
        if lat is not None and lon is not None:
            try:
                daylight = _live_sun(lat, lon)
            except (ValueError, ConnectionError) as exc:
                st.caption(f"{code}: sunrise/sunset unavailable — {exc}")

        assessment = assess_airport(
            code, metar, runways_by_airport.get(code, []), daylight,
            crosswind_limit_kt=float(limit),
            runway_closed_scenario=(code == target and runway_closed),
            night_closed_scenario=(code == target and night_closed),
            strike_scenario=(code == target and strike),
        )
        if lat is not None and lon is not None:
            assessment.latitude, assessment.longitude = lat, lon
        assessments.append(assessment)

    points = [
        {
            "icao": a.code, "lat": a.latitude, "lon": a.longitude,
            "color": a.color, "status": a.status,
        }
        for a in assessments if a.latitude is not None and a.longitude is not None
    ]
    if points:
        lat_avg = sum(p["lat"] for p in points) / len(points)
        lon_avg = sum(p["lon"] for p in points) / len(points)
        st.pydeck_chart(pdk.Deck(
            map_style=None,
            initial_view_state=pdk.ViewState(latitude=lat_avg, longitude=lon_avg, zoom=4, pitch=0),
            layers=[pdk.Layer(
                "ScatterplotLayer", data=points, get_position="[lon, lat]",
                get_fill_color="color", get_radius=25000, radius_min_pixels=8,
                pickable=True,
            )],
            tooltip={"html": "<b>{icao}</b><br>{status}"},
        ), width="stretch")
    else:
        st.warning("No airport coordinates available for the map.")

    st.caption("Green = meets our checked conditions; yellow = caution; red = blocked in this model/scenario; grey = unknown.")
    for airport in assessments:
        with st.container(border=True):
            st.subheader(f"{airport.code} — {airport.status}")
            if airport.flight_category:
                st.write(f"METAR flight category: {airport.flight_category}")
            if airport.crosswind_kt is not None:
                st.write(
                    f"Best runway: {airport.runway}; crosswind: "
                    f"{airport.crosswind_kt:.1f} knots ({airport.crosswind_kt * 1.852:.1f} km/h)."
                )
            for reason in airport.reasons:
                st.write(f"• {reason}")
    st.caption("Crosswind estimate = |wind speed × sin(wind direction − runway heading)|. Uses true runway headings.")
    _glossary()


# Compatible with apps calling either render() or main().
def main():
    render()


if __name__ == "__main__":
    render()
