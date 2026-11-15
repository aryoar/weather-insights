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
from weather_app.route import KM_PER_NM, Route
from weather_app.winds import RouteWinds, best_level_hint

from .common import get_route, metric_with_note, route_missing_notice, show_glossary
from .theme import AXIS, HEAD_COLOUR, HEADWIND_SCALE, TAIL_COLOUR, chart, hero

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
    """Airports from the sidebar ('Your flight', validated there) plus this page's point slider."""
    route = get_route()
    if route is None:
        route_missing_notice()
        return None
    last = st.session_state.get("winds_request", {})
    st.session_state.setdefault("winds_point_count", last.get("point_count", 8))
    point_count = st.slider("Points along the route", 4, 12, key="winds_point_count",
                            help="Including departure and destination. All points are fetched in one request.")
    st.session_state.winds_request = {"departure": route["departure"], "destination": route["destination"],
                                      "point_count": point_count}
    return st.session_state.winds_request


# ---------------------------------------------------------------- charts ----

def _level_label(fl: int) -> str:
    return f"FL{fl:03d} (~{fl * 100 * 0.3048 / 1000:.1f} km)"


def _heatmap(winds: RouteWinds) -> go.Figure:
    levels = list(reversed(winds.flight_levels))  # highest at the top, like the sky
    z = [winds.headwinds_at(fl) for fl in levels]
    limit = max((abs(v) for row in z for v in row if v is not None), default=1) or 1
    cells = [(v, fl, x) for fl, row in zip(levels, z) for x, v in zip(winds.distances_nm, row) if v is not None]
    worst = max(cells, default=None)
    title = ("Headwind (red) or tailwind (blue) along the route" if worst is None or worst[0] <= 0 else
             f"Strongest headwind: {worst[0]:.0f} kt at FL{worst[1]:03d}, {worst[2]:,.0f} nm along the route")
    fig = go.Figure(go.Heatmap(
        x=winds.distances_nm, y=[_level_label(fl) for fl in levels], z=z,
        zmin=-limit, zmax=limit, colorscale=HEADWIND_SCALE, xgap=2, ygap=2,
        text=[[("n/a" if v is None else f"{v:+.0f}") for v in row] for row in z], texttemplate="%{text}",
        colorbar={"title": {"text": "Headwind (kt)<br>+ against, − behind"}, "tickfont": {"color": AXIS}},
        hovertemplate="%{y}<br>%{x:,.0f} nm from departure<br>Headwind: %{z:+.0f} kt<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title="Distance from departure (nm; 1 nm = 1.852 km)", yaxis_title="Cruise height (flight level)",
        height=420,
    )
    return fig


def _bar_chart(table: pd.DataFrame) -> go.Figure:
    colours = [HEAD_COLOUR if v > 0 else TAIL_COLOUR for v in table["headwind_kt"]]
    best = table.loc[table["headwind_kt"].idxmin()]
    kind = "tailwind" if best["headwind_kt"] < 0 else "headwind"
    fig = go.Figure(go.Bar(
        x=table["headwind_kt"], y=[_level_label(fl) for fl in table["flight_level"]], orientation="h",
        marker_color=colours, text=[f"{v:+.0f} kt" for v in table["headwind_kt"]], textposition="outside",
        cliponaxis=False, customdata=table["headwind_kmh"],
        hovertemplate="%{y}<br>Average headwind: %{x:+.1f} kt (%{customdata:+.0f} km/h)<extra></extra>",
    ))
    fig.add_vline(x=0, line_color=AXIS)
    fig.update_layout(
        title=f"FL{int(best['flight_level']):03d} is best today: {abs(best['headwind_kt']):.0f} kt average {kind}",
        xaxis_title="Average headwind along the route (kt; − = tailwind, 1 kt = 1.852 km/h)",
        yaxis_title="Cruise height (flight level)", height=360,
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
    hero("Winds aloft (model-based estimate)", "How strong the wind is at cruise heights, and whether each "
         "height pushes the aircraft along (tailwind) or holds it back (headwind). Winds from the Open-Meteo "
         "model; airport positions from aviationweather.gov.", kicker="Brief · Step 2")
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
    grid = pd.DataFrame({_level_label(fl): winds.headwinds_at(fl) for fl in winds.flight_levels})
    grid.insert(0, "Distance from departure (nm)", [round(d) for d in winds.distances_nm])
    chart(_heatmap(winds), grid, key="winds_heatmap")
    chart(_bar_chart(table), table, key="winds_bars")
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
