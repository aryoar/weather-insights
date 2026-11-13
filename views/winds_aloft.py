"""Winds aloft page. Owner: Jeevan.

A model-based winds aloft view (NOT an official SIGWX chart): wind and temperature at several
cruise heights along the route, and whether each height gives a headwind or a tailwind.

Data (all real, all free, no key):
- Airport coordinates: METARs from aviationweather.gov (AviationWeatherClient).
- Winds and temperatures at altitude: Open-Meteo forecast model (OpenMeteoClient.winds_many),
  one request for all points along the route.
All calculations (headwind, averages, best height) live in weather_app.winds; this file only shows them.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from weather_app.client import AviationWeatherClient, OpenMeteoClient
from weather_app.glossary import GLOSSARY
from weather_app.reports import clean_icao_code
from weather_app.route import KM_PER_NM, Route
from weather_app.winds import RouteWinds, best_level_hint

from .common import metric_with_note, show_glossary

API_ERRORS = (ConnectionError, PermissionError, LookupError, RuntimeError, ValueError)


# ---------------------------------------------------------------- data (cached) ----
# Failures raise instead of being returned, so Streamlit never caches an error.

@st.cache_data(ttl=300, show_spinner="Finding the airports…")
def _fetch_airports(codes: tuple[str, ...]):
    return AviationWeatherClient().metars(list(codes))


@st.cache_data(ttl=300, show_spinner="Fetching winds at altitude from Open-Meteo…")
def _fetch_winds(points: tuple[tuple[float, float], ...]):
    return OpenMeteoClient().winds_many(list(points))


# ---------------------------------------------------------------- input ----

def _read_request() -> dict | None:
    """Form for the route. Starts from the route chosen on the other pages."""
    shared = st.session_state.get("selected_airports", {})
    route_page = st.session_state.get("route_request", {})
    last = st.session_state.get("winds_request", {})
    defaults = {
        "winds_departure": last.get("departure", route_page.get("departure", shared.get("Departure", "LEMD"))),
        "winds_destination": last.get("destination", route_page.get("destination", shared.get("Destination", "EGLL"))),
        "winds_point_count": last.get("point_count", 8),
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    with st.form("winds_form"):
        left, mid, right = st.columns([1, 1, 1.4])
        departure = left.text_input("Departure airport (ICAO code)", key="winds_departure",
                                    max_chars=4, help=GLOSSARY["ICAO code"])
        destination = mid.text_input("Destination airport (ICAO code)", key="winds_destination",
                                     max_chars=4, help=GLOSSARY["ICAO code"])
        point_count = right.slider("Points along the route", 4, 12, key="winds_point_count",
                                   help="Including departure and destination. All points are fetched in one request.")
        submitted = st.form_submit_button("Show winds aloft", type="primary")

    if submitted:
        problems = []
        try:
            departure = clean_icao_code(departure)
        except ValueError as exc:
            problems.append(f"Departure: {exc}")
        try:
            destination = clean_icao_code(destination)
        except ValueError as exc:
            problems.append(f"Destination: {exc}")
        if not problems and departure == destination:
            problems.append("Departure and destination must be two different airports.")
        for problem in problems:
            st.error(problem)
        if problems:
            return None
        st.session_state.winds_request = {"departure": departure, "destination": destination,
                                          "point_count": point_count}
        st.session_state.selected_airports = {**shared, "Departure": departure, "Destination": destination}
    return st.session_state.get("winds_request")


# ---------------------------------------------------------------- charts ----

def _level_label(fl: int) -> str:
    return f"FL{fl:03d} (~{fl * 100 * 0.3048 / 1000:.1f} km)"


def _heatmap(winds: RouteWinds) -> go.Figure:
    levels = list(reversed(winds.flight_levels))  # highest at the top, like the sky
    z = [winds.headwinds_at(fl) for fl in levels]
    limit = max((abs(v) for row in z for v in row if v is not None), default=1) or 1
    fig = go.Figure(go.Heatmap(
        x=winds.distances_nm, y=[_level_label(fl) for fl in levels], z=z,
        zmin=-limit, zmax=limit, colorscale="RdBu_r",
        text=[[("n/a" if v is None else f"{v:+.0f}") for v in row] for row in z], texttemplate="%{text}",
        colorbar={"title": {"text": "Headwind (kt)<br>+ against, − behind"}},
        hovertemplate="%{y}<br>%{x} nm from departure<br>Headwind: %{z:+.0f} kt<extra></extra>",
    ))
    fig.update_layout(
        title="Headwind (red) or tailwind (blue) along the route",
        xaxis_title="Distance from departure (nm)", yaxis_title="Cruise height (flight level)",
        margin={"t": 50, "b": 10}, height=420,
    )
    return fig


def _bar_chart(table: pd.DataFrame) -> go.Figure:
    colours = ["#d62728" if v > 0 else "#1f77b4" for v in table["headwind_kt"]]
    fig = go.Figure(go.Bar(
        x=table["headwind_kt"], y=[_level_label(fl) for fl in table["flight_level"]], orientation="h",
        marker_color=colours, text=[f"{v:+.0f} kt" for v in table["headwind_kt"]], textposition="outside",
        hovertemplate="%{y}<br>Average headwind: %{x:+.1f} kt<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="grey")
    fig.update_layout(
        title="Average headwind per height (negative = tailwind)",
        xaxis_title="Average headwind along the route (kt)", yaxis_title="Cruise height (flight level)",
        margin={"t": 50, "b": 10}, height=360,
    )
    return fig


def _effect(headwind_kt: float) -> str:
    if headwind_kt > 2:
        return "🔴 headwind: slower, more fuel"
    if headwind_kt < -2:
        return "🔵 tailwind: faster, less fuel"
    return "⚪ about neutral"


# ---------------------------------------------------------------- page ----

def render() -> None:
    st.header("Winds aloft (model-based estimate)")
    st.write(
        "How strong the wind is at the heights airliners cruise, and whether each height pushes the "
        "aircraft along (**tailwind**) or holds it back (**headwind**). Winds come from the free "
        "**Open-Meteo** weather model; airport positions from aviationweather.gov."
    )
    st.caption("⚠️ Our own approximation from weather-model data. Not an official SIGWX chart and "
               "not for real flight planning.")

    request = _read_request()
    if not request:
        return
    dep_code, dest_code = request["departure"], request["destination"]

    # 1. Where are the two airports? (their METARs include coordinates)
    try:
        metars, errors = _fetch_airports((dep_code, dest_code))
    except API_ERRORS as exc:
        st.error(f"Could not look up the airports: {exc}")
        return
    by_code = {m.icao: m for m in metars}
    missing = [code for code in (dep_code, dest_code) if code not in by_code]
    for code in missing:
        st.error(f"{code}: {errors.get(code, 'not found')} The page needs a current METAR to know where it is.")
    if missing:
        return
    dep, dest = by_code[dep_code], by_code[dest_code]
    route = Route(dep_code, dest_code, (dep.latitude, dep.longitude), (dest.latitude, dest.longitude))

    # 2. Winds at every height above points along the route (one Open-Meteo request)
    points = tuple((round(lat, 3), round(lon, 3)) for lat, lon in route.points(request["point_count"]))
    try:
        levels_per_point = _fetch_winds(points)
    except API_ERRORS as exc:
        st.error(f"Winds aloft are not available right now: {exc}")
        return
    winds = RouteWinds(str(route), route.distance_nm, list(points), levels_per_point)
    if not winds.flight_levels:
        st.warning("Open-Meteo did not report any upper winds for this route. Try again later.")
        return

    # 3. Summary
    best = winds.best_flight_level
    best_value = winds.average_headwind_kt(best)
    st.success(f"✈️ {best_level_hint(winds)}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Route", f"{dep_code} → {dest_code}")
    metric_with_note(c2, "Distance", f"{route.distance_nm:,.0f} nm", f"{route.distance_nm * KM_PER_NM:,.0f} km",
                     help=GLOSSARY["Nautical mile (nm)"])
    metric_with_note(c3, f"Best height: FL{best:03d}",
                     f"{abs(best_value):.0f} kt {'tailwind' if best_value < 0 else 'headwind'}",
                     f"{abs(best_value) * 1.852:.0f} km/h", help=GLOSSARY["Flight level (FL)"])

    # 4. Charts
    table = pd.DataFrame(winds.summary_rows())
    st.plotly_chart(_heatmap(winds), width="stretch")
    st.plotly_chart(_bar_chart(table), width="stretch")
    st.caption("Headwind = wind speed × cos(wind direction − direction of flight), at each point, "
               "using the direction of the route at that point. Positive = headwind, negative = tailwind.")

    # 5. Table with everyday units next to aviation ones
    shown = pd.DataFrame({
        "Height": [f"FL{fl:03d}" for fl in table["flight_level"]],
        "Feet": [f"{ft:,}" for ft in table["altitude_ft"]],
        "Metres": [f"{m:,}" for m in table["altitude_m"]],
        "Avg wind (kt)": table["wind_speed_kt"],
        "Avg wind (km/h)": (table["wind_speed_kt"] * 1.852).round().astype(int),
        "Avg temperature (°C)": table["temperature_c"],
        "Avg headwind (kt)": table["headwind_kt"],
        "Avg headwind (km/h)": table["headwind_kmh"],
        "Effect": [_effect(v) for v in table["headwind_kt"]],
    })
    st.subheader("Each cruise height, averaged along the route")
    st.dataframe(shown, hide_index=True, width="stretch")

    with st.expander("Why does wind at altitude matter?"):
        st.markdown(
            "- Aircraft cruise high (FL300–FL390 for airliners), where winds are often 50–150 kt in the "
            "**jet stream**, much stronger than at the airport.\n"
            "- With a headwind the aircraft covers less ground per hour, so the flight takes longer and "
            "burns more fuel. A tailwind does the opposite.\n"
            "- That is why flights from America to Europe are usually faster than the other way: the jet "
            "stream blows from the west.\n"
            "- The **Fuel planner** page uses the average headwind from this page."
        )

    show_glossary(["Winds aloft", "Flight level (FL)", "Pressure level (hPa)", "Headwind / tailwind",
                   "Knots (kt)", "Nautical mile (nm)", "ICAO code"])
