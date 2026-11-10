"""Route overview page: a map zoomed to the flight, with the great-circle route as a black line,
the current weather at evenly spaced points along it, and the reporting airports near the route
that could serve as alternates.

Data (all real, all free):
- Airport coordinates and conditions: METARs from aviationweather.gov (AviationWeatherClient).
- Weather along the route: OpenWeatherMap current weather at each point (WeatherClient.current_at).
- Nearby airports: aviationweather.gov METARs for the map area (AviationWeatherClient.metars_in_area).
Geometry (distance, points, map area) lives in weather_app.route, so it can be tested without Streamlit.
"""

import html
import math
from datetime import datetime, timezone

import pandas as pd
import pydeck as pdk
import streamlit as st

from weather_app.client import AviationWeatherClient, WeatherClient
from weather_app.config import get_api_key
from weather_app.glossary import GLOSSARY
from weather_app.reports import FLIGHT_CATEGORIES, UNKNOWN_CATEGORY, clean_icao_code
from weather_app.route import Route, great_circle_nm
from weather_app.storage import MetarStore

from .common import age_text, show_glossary

KT_PER_MPS = 1 / 0.514444
API_ERRORS = (ConnectionError, PermissionError, LookupError, RuntimeError, ValueError)

# Map colours (RGB). Airports use the same traffic-light colours as the 🟢🔵🔴🟣 emojis.
CATEGORY_COLOURS = {"VFR": [46, 160, 67], "MVFR": [31, 119, 180], "IFR": [214, 39, 40], "LIFR": [170, 0, 170]}
UNKNOWN_COLOUR = [150, 150, 150]
# Colour scales for the weather dots: (value, colour) stops, blended in between.
DOT_SCALES = {
    "Temperature": {"column": "temperature_c", "unit": "°C", "stops": [
        (-10, (49, 54, 149)), (0, (116, 173, 209)), (10, (171, 217, 233)),
        (20, (253, 174, 97)), (30, (215, 48, 39))]},
    "Wind": {"column": "wind_kt", "unit": "kt", "stops": [
        (0, (26, 152, 80)), (15, (254, 224, 139)), (30, (215, 48, 39))]},
    "Cloud cover": {"column": "clouds_pct", "unit": "%", "stops": [
        (0, (135, 206, 250)), (100, (90, 90, 90))]},
}


# ---------------------------------------------------------------- data (cached) ----
# Failures raise instead of being returned, so Streamlit never caches an error.

@st.cache_data(ttl=300, show_spinner="Finding the airports…")
def _fetch_endpoints(codes: tuple[str, ...]):
    metars, errors = AviationWeatherClient().metars(list(codes))
    return metars, errors, datetime.now(timezone.utc)


@st.cache_data(ttl=600, show_spinner="Fetching the weather along the route…")
def _fetch_route_weather(points: tuple[tuple[float, float, str], ...]):
    """Current weather at each (lat, lon, label). One failing point is skipped, not fatal."""
    client = WeatherClient(get_api_key())
    snapshots, errors = {}, {}
    for lat, lon, label in points:
        try:
            snapshots[label] = client.current_at(lat, lon, label)
        except PermissionError:
            raise  # a bad key fails every point, so stop and report it once
        except (ValueError, LookupError, ConnectionError, RuntimeError) as exc:
            errors[label] = str(exc)
    return snapshots, errors


@st.cache_data(ttl=600, show_spinner="Finding airports near the route…")
def _fetch_area(box: tuple[float, float, float, float]):
    return AviationWeatherClient().metars_in_area(*box)


# ---------------------------------------------------------------- helpers ----

def _blend(stops, value) -> list[int]:
    """Colour for a value on a scale of (value, rgb) stops. Missing values are grey."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return UNKNOWN_COLOUR
    if value <= stops[0][0]:
        return list(stops[0][1])
    for (low, low_rgb), (high, high_rgb) in zip(stops, stops[1:]):
        if value <= high:
            share = (value - low) / (high - low)
            return [round(a + (b - a) * share) for a, b in zip(low_rgb, high_rgb)]
    return list(stops[-1][1])


def _view_state(box, width_px: int = 900, height_px: int = 520) -> pdk.ViewState:
    """Centre and zoom so the box fills the map (Web Mercator: each zoom level doubles the scale)."""
    min_lat, min_lon, max_lat, max_lon = box

    def mercator_y(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    lon_zoom = math.log2(width_px / 256 * 360 / max(max_lon - min_lon, 0.01))
    lat_zoom = math.log2(height_px / 256 * 2 * math.pi / max(mercator_y(max_lat) - mercator_y(min_lat), 0.0001))
    return pdk.ViewState(
        latitude=(min_lat + max_lat) / 2,
        longitude=(min_lon + max_lon) / 2,
        zoom=max(min(lon_zoom, lat_zoom) - 0.3, 0.5),
    )


def _category_colour(metar) -> list[int]:
    return CATEGORY_COLOURS.get(metar.flight_category, UNKNOWN_COLOUR)


def _airport_tooltip(metar, extra: str = "") -> str:
    info = metar.category_info
    ceiling = "none" if metar.ceiling_ft is None else f"{metar.ceiling_ft:,} ft"
    return (
        f"<b>{html.escape(metar.icao)}</b> {html.escape(metar.name)}<br/>"
        f"{info['emoji']} {info['label']} ({html.escape(metar.flight_category)})<br/>"
        f"Wind: {html.escape(metar.wind_text)}<br/>Visibility: {html.escape(metar.visibility_text)}"
        f" · Ceiling: {ceiling}{extra}"
    )


def _read_request() -> dict | None:
    """Form for the route. Remembers the last valid request; shares codes with the Airport weather page."""
    shared = st.session_state.get("selected_airports", {})
    last = st.session_state.get("route_request", {})
    # Widgets get fixed keys with starting values set once. (Passing a changing value= instead
    # makes Streamlit treat it as a new widget, which can throw away what the user typed.)
    defaults = {
        "route_departure": last.get("departure", shared.get("Departure", "LEMD")),
        "route_destination": last.get("destination", shared.get("Destination", "EGLL")),
        "route_point_count": last.get("point_count", 6),
        "route_corridor_nm": last.get("corridor_nm", 50),
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    with st.form("route_form"):
        left, right = st.columns(2)
        departure = left.text_input("Departure airport (ICAO code)", key="route_departure",
                                    max_chars=4, help=GLOSSARY["ICAO code"])
        destination = right.text_input("Destination airport (ICAO code)", key="route_destination",
                                       max_chars=4, help=GLOSSARY["ICAO code"])
        left, right = st.columns(2)
        point_count = left.slider("Weather points along the route", 3, 12, key="route_point_count",
                                  help="Including departure and destination. Each point is one OpenWeatherMap request.")
        corridor_nm = right.slider("Show airports within this distance of the route (nm)", 10, 150, step=10,
                                   key="route_corridor_nm", help=GLOSSARY["Nautical mile (nm)"])
        submitted = st.form_submit_button("Show route", type="primary")

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
        st.session_state.route_request = {"departure": departure, "destination": destination,
                                          "point_count": point_count, "corridor_nm": corridor_nm}
        # Keep the Airport weather page in step with the route the user is looking at.
        st.session_state.selected_airports = {**shared, "Departure": departure, "Destination": destination}
        st.session_state.selected_airports.setdefault("Alternate", "LFPG")
    return st.session_state.get("route_request")


def _save_endpoint_metars(metars, fetched_at) -> None:
    """Add the departure/destination METARs to the project history (same rule as Airport weather)."""
    store = MetarStore()
    for metar in metars:
        try:
            store.append_if_new(metar, fetched_at)
        except (OSError, ValueError) as exc:
            st.error(f"Could not save METAR history for {metar.icao}: {exc}")


# ---------------------------------------------------------------- page ----

def render() -> None:
    st.header("Route overview")
    st.write(
        "Enter two airports to see the direct (**great circle**) route on a map, the current weather "
        "at points along it, and the airports near the route you could divert to. All data is live."
    )
    request = _read_request()
    if not request:
        return
    dep_code, dest_code = request["departure"], request["destination"]

    # 1. Where are the two airports? (their METARs include coordinates)
    try:
        metars, errors, fetched_at = _fetch_endpoints((dep_code, dest_code))
    except API_ERRORS as exc:
        st.error(f"Could not look up the airports: {exc}")
        return
    by_code = {m.icao: m for m in metars}
    missing = [code for code in (dep_code, dest_code) if code not in by_code]
    for code in missing:
        st.error(f"{code}: {errors.get(code, 'not found')} The route needs a current METAR for both airports.")
    if missing:
        return
    _save_endpoint_metars(metars, fetched_at)
    dep, dest = by_code[dep_code], by_code[dest_code]
    route = Route(dep_code, dest_code, (dep.latitude, dep.longitude), (dest.latitude, dest.longitude))

    # 2. Weather along the route (OpenWeatherMap)
    points = route.points(request["point_count"])
    step_nm = route.distance_nm / (len(points) - 1)
    labels = [f"{i * step_nm:,.0f} nm" for i in range(len(points))]
    weather, weather_errors = {}, {}
    try:
        weather, weather_errors = _fetch_route_weather(
            tuple((round(lat, 3), round(lon, 3), label) for (lat, lon), label in zip(points, labels))
        )
    except (RuntimeError, PermissionError) as exc:
        st.warning(f"Weather along the route is not available: {exc}")

    rows = []
    for i, ((lat, lon), label) in enumerate(zip(points, labels)):
        snap = weather.get(label)
        if snap is None:
            continue
        near = "" if snap.city == label else f" (near {snap.city})"
        row = {
            "distance_nm": round(i * step_nm), "latitude": lat, "longitude": lon,
            "temperature_c": snap.temperature_c, "wind_kt": snap.wind_speed_mps * KT_PER_MPS,
            "clouds_pct": snap.clouds_pct, "description": snap.description,
        }
        row["tooltip"] = (
            f"<b>{label} from {html.escape(dep_code)}</b>{html.escape(near)}<br/>{html.escape(snap.description)}<br/>"
            f"{snap.temperature_c:.0f} °C · wind {row['wind_kt']:.0f} kt"
            + ("" if snap.clouds_pct is None else f" · clouds {snap.clouds_pct}%")
        )
        rows.append(row)
    profile = pd.DataFrame(rows)

    # 3. Reporting airports near the route (possible alternates)
    nearby = []
    if route.crosses_antimeridian:
        st.info("This route crosses the 180° line, so nearby airports are not shown for it.")
    else:
        box = tuple(round(v, 1) for v in route.bounding_box(margin_nm=request["corridor_nm"]))
        try:
            area_metars, _skipped = _fetch_area(box)
        except API_ERRORS as exc:
            st.warning(f"Nearby airports are not available: {exc}")
            area_metars = []
        for metar in area_metars:
            if metar.icao in (dep_code, dest_code):
                continue
            off_route = route.distance_from_route_nm(metar.latitude, metar.longitude)
            if off_route <= request["corridor_nm"]:
                to_dest = great_circle_nm(metar.latitude, metar.longitude, dest.latitude, dest.longitude)
                nearby.append((metar, off_route, to_dest))

    # ---- headline numbers
    cols = st.columns(4)
    cols[0].metric("Distance", f"{route.distance_nm:,.0f} nm", help=f"{route.distance_km:,.0f} km. {GLOSSARY['Great circle']}")
    cols[1].metric(f"{dep_code} now", f"{dep.category_info['emoji']} {dep.flight_category}", help=dep.category_info["explanation"])
    cols[2].metric(f"{dest_code} now", f"{dest.category_info['emoji']} {dest.flight_category}", help=dest.category_info["explanation"])
    cols[3].metric("Airports near the route", len(nearby), help=f"Reporting airports within {request['corridor_nm']} nm of the route.")

    # ---- map
    colour_by = st.radio("Colour the weather dots by", list(DOT_SCALES), horizontal=True)
    scale = DOT_SCALES[colour_by]
    if not profile.empty:
        profile["color"] = [_blend(scale["stops"], value) for value in profile[scale["column"]]]

    path = [[lon, lat] for lat, lon in route.points(100)]
    layers = [
        pdk.Layer("PathLayer", [{"path": path, "tooltip": html.escape(str(route))}], get_path="path",
                  get_color=[0, 0, 0], width_min_pixels=3, wrap_longitude=True, pickable=True),
        pdk.Layer("ScatterplotLayer", [
            {"position": [m.longitude, m.latitude], "color": _category_colour(m),
             "tooltip": _airport_tooltip(m, f"<br/>{off:.0f} nm from route · {to_dest:.0f} nm from {html.escape(dest_code)}")}
            for m, off, to_dest in nearby
        ], get_position="position", get_fill_color="color", get_line_color=[255, 255, 255],
            stroked=True, line_width_min_pixels=1, radius_units="pixels", get_radius=5, pickable=True),
        # NaN (e.g. no cloud report) is not valid JSON for the map, so turn it into None first.
        pdk.Layer("ScatterplotLayer", profile.astype(object).where(profile.notna(), None).to_dict("records"),
                  get_position="[longitude, latitude]", get_fill_color="color", get_line_color=[0, 0, 0],
                  stroked=True, line_width_min_pixels=2, radius_units="pixels", get_radius=11, pickable=True),
        pdk.Layer("ScatterplotLayer", [
            {"position": [m.longitude, m.latitude], "color": _category_colour(m), "label": m.icao,
             "tooltip": _airport_tooltip(m, f"<br/>{role}")}
            for m, role in ((dep, "Departure"), (dest, "Destination"))
        ], get_position="position", get_fill_color="color", get_line_color=[0, 0, 0], stroked=True,
            line_width_min_pixels=3, radius_units="pixels", get_radius=8, pickable=True),
        pdk.Layer("TextLayer", [{"position": [m.longitude, m.latitude], "label": m.icao} for m in (dep, dest)],
                  get_position="position", get_text="label", get_size=15, get_color=[0, 0, 0],
                  get_pixel_offset=[0, -22], font_weight=700),
    ]
    view = (pdk.ViewState(latitude=(dep.latitude + dest.latitude) / 2, longitude=path[50][0], zoom=1.5)
            if route.crosses_antimeridian else _view_state(route.bounding_box(margin_nm=request["corridor_nm"])))
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, map_style="light",
                             tooltip={"html": "{tooltip}", "style": {"fontSize": "13px"}}))
    legend = " · ".join(f"{FLIGHT_CATEGORIES[c]['emoji']} {c}" for c in CATEGORY_COLOURS)
    low, high = scale["stops"][0][0], scale["stops"][-1][0]
    st.caption(
        f"**Black line:** direct route. **Large dots with a black ring:** weather now, coloured by "
        f"{colour_by.lower()} (from {low} {scale['unit']} to {high} {scale['unit']} and above). "
        f"**Small dots:** airports near the route, coloured by flying conditions ({legend}). "
        "Hover over anything for details."
    )
    for label, message in weather_errors.items():
        st.warning(f"Weather point at {label}: {message}")

    # ---- weather profile along the route
    if not profile.empty:
        st.subheader("Weather along the route")
        chart = profile.rename(columns={"distance_nm": "Distance from departure (nm)"})
        left, right = st.columns(2)
        with left:
            st.line_chart(chart, x="Distance from departure (nm)", y="temperature_c", y_label="Temperature (°C)")
        with right:
            st.bar_chart(chart, x="Distance from departure (nm)", y="wind_kt", y_label="Wind speed at the surface (kt)")
        st.caption("Current surface conditions from OpenWeatherMap. Winds at cruise altitude are on the Winds aloft page.")

    # ---- alternates
    st.subheader("Possible alternate airports")
    if not nearby:
        st.info(f"No reporting airports found within {request['corridor_nm']} nm of the route. Try a wider distance.")
    else:
        counts = {c: sum(1 for m, _, _ in nearby if m.flight_category == c) for c in CATEGORY_COLOURS}
        st.write("Conditions near the route right now: " + " · ".join(
            f"{FLIGHT_CATEGORIES[c]['emoji']} {n} {c}" for c, n in counts.items() if n))
        good = [item for item in nearby if item[0].flight_category in ("VFR", "MVFR")]
        if good:
            best, _, best_dist = min(good, key=lambda item: item[2])
            st.success(f"Closest airport to {dest_code} with good or moderate conditions: "
                       f"**{best.icao}** ({best.name}), {best_dist:.0f} nm away, {best.flight_category}.")
        else:
            st.warning("None of the airports near the route currently report good or moderate conditions.")
        table = pd.DataFrame([{
            "Airport": f"{m.category_info['emoji']} {m.icao}", "Name": m.name, "Conditions": m.flight_category,
            f"From {dest_code} (nm)": round(to_dest), "From route (nm)": round(off),
            "Wind": m.wind_text, "Visibility": m.visibility_text,
            "Ceiling (ft)": "none" if m.ceiling_ft is None else f"{m.ceiling_ft:,}",
            "Observed": age_text(m.observed_at),
        } for m, off, to_dest in sorted(nearby, key=lambda item: item[2])])
        st.dataframe(table.head(15), hide_index=True, width="stretch")
        st.caption(f"Closest to {dest_code} first. A real alternate also needs a suitable runway, "
                   "opening hours and services: see the Airport suitability page.")

    show_glossary(["Great circle", "Nautical mile (nm)", "ICAO code", "METAR", "Flight category",
                   "Alternate airport", "Knots (kt)", "Ceiling", "Visibility"])
