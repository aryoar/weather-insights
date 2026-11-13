"""Fuel planner page. Owner: Samuel.

An educational fuel estimate, NOT for real flight planning.
- Real inputs: airport positions (METARs from aviationweather.gov), the great-circle distance,
  and the average headwind at the chosen cruise height (Open-Meteo, same data as Winds aloft).
- Scenario inputs (hypothetical, marked with a SCENARIO banner): aircraft class, passengers,
  bags, cargo and extra fuel.
All calculations live in weather_app.fuel (FuelPlan); this file only collects inputs and shows them.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from weather_app.client import AviationWeatherClient, OpenMeteoClient
from weather_app.fuel import AIRCRAFT_PROFILES, FuelPlan
from weather_app.glossary import GLOSSARY
from weather_app.reports import clean_icao_code
from weather_app.route import Route, great_circle_nm
from weather_app.winds import FLIGHT_LEVELS, RouteWinds

from .common import metric_with_note, scenario_banner, show_glossary

API_ERRORS = (ConnectionError, PermissionError, LookupError, RuntimeError, ValueError)
WIND_POINTS = 8  # points along the route where winds are sampled (one request for all)


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
    """Form for the flight. Starts from the airports chosen on the other pages."""
    shared = st.session_state.get("selected_airports", {})
    last = st.session_state.get("fuel_request", {})
    defaults = {
        "fuel_departure": last.get("departure", shared.get("Departure", "LEMD")),
        "fuel_destination": last.get("destination", shared.get("Destination", "EGLL")),
        "fuel_alternate": last.get("alternate", shared.get("Alternate", "LFPG")),
        "fuel_aircraft": last.get("aircraft", "Narrow-body jet"),
        "fuel_flight_level": last.get("flight_level", 340),
        "fuel_passengers": last.get("passengers", 150),
        "fuel_bags": last.get("bags", 100),
        "fuel_cargo": last.get("cargo_kg", 1_000),
        "fuel_extra": last.get("extra_kg", 0),
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    with st.form("fuel_form"):
        st.markdown("**Real flight**: airports and cruise height")
        c1, c2, c3, c4 = st.columns(4)
        departure = c1.text_input("Departure (ICAO)", key="fuel_departure", max_chars=4,
                                  help=GLOSSARY["ICAO code"])
        destination = c2.text_input("Destination (ICAO)", key="fuel_destination", max_chars=4,
                                    help=GLOSSARY["ICAO code"])
        alternate = c3.text_input("Alternate (ICAO)", key="fuel_alternate", max_chars=4,
                                  help=GLOSSARY["Alternate airport"])
        flight_level = c4.selectbox("Cruise height", sorted(FLIGHT_LEVELS.values()), key="fuel_flight_level",
                                    format_func=lambda fl: f"FL{fl:03d} (~{fl * 30.48 / 1000:.1f} km)",
                                    help=GLOSSARY["Flight level (FL)"] + " Each aircraft class has its own "
                                         "cruise range, shown next to its name below.")

        st.markdown("**Scenario**: hypothetical aircraft and load")
        c1, c2, c3, c4, c5 = st.columns([1.6, 1, 1, 1, 1])
        aircraft = c1.selectbox("Aircraft class", list(AIRCRAFT_PROFILES), key="fuel_aircraft",
                                format_func=lambda name: str(AIRCRAFT_PROFILES[name]))
        passengers = c2.number_input("Passengers", min_value=0, max_value=400, step=1, key="fuel_passengers")
        bags = c3.number_input("Checked bags", min_value=0, max_value=800, step=1, key="fuel_bags")
        cargo_kg = c4.number_input("Cargo (kg)", min_value=0, max_value=60_000, step=100, key="fuel_cargo",
                                   help=GLOSSARY["Payload"])
        extra_kg = c5.number_input("Extra fuel (kg)", min_value=0, max_value=20_000, step=100, key="fuel_extra",
                                   help="Fuel the captain adds on top of the minimum, e.g. for expected delays.")
        submitted = st.form_submit_button("Estimate fuel", type="primary")

    if submitted:
        problems, codes = [], {}
        for role, code in (("Departure", departure), ("Destination", destination), ("Alternate", alternate)):
            try:
                codes[role] = clean_icao_code(code)
            except ValueError as exc:
                problems.append(f"{role}: {exc}")
        if not problems and len(set(codes.values())) < 3:
            problems.append("Departure, destination and alternate must be three different airports.")
        if passengers > AIRCRAFT_PROFILES[aircraft].seats:
            problems.append(f"A {aircraft} has {AIRCRAFT_PROFILES[aircraft].seats} seats; "
                            f"you entered {passengers} passengers.")
        if not AIRCRAFT_PROFILES[aircraft].can_cruise_at(flight_level):
            problems.append(f"A {aircraft} cruises at {AIRCRAFT_PROFILES[aircraft].cruise_range} in this planner, "
                            f"not FL{flight_level:03d}. Pick a cruise height in that range.")
        for problem in problems:
            st.error(problem)
        if problems:
            return None
        st.session_state.fuel_request = {
            "departure": codes["Departure"], "destination": codes["Destination"],
            "alternate": codes["Alternate"], "aircraft": aircraft, "flight_level": flight_level,
            "passengers": int(passengers), "bags": int(bags), "cargo_kg": float(cargo_kg),
            "extra_kg": float(extra_kg),
        }
        st.session_state.selected_airports = {**shared, **codes}
    return st.session_state.get("fuel_request")


# ---------------------------------------------------------------- charts ----

def _breakdown_chart(plan: FuelPlan) -> go.Figure:
    parts = [(name, kg) for name, kg in plan.breakdown() if kg > 0]
    fig = go.Figure(go.Bar(
        x=[kg for _, kg in parts], y=[name for name, _ in parts], orientation="h",
        text=[f"{kg:,.0f} kg" for _, kg in parts], textposition="auto",
        hovertemplate="%{y}: %{x:,.0f} kg<extra></extra>",
    ))
    fig.update_layout(
        title=f"Where the {plan.block_fuel_kg:,.0f} kg of block fuel goes",
        xaxis_title="Fuel (kg)", yaxis_title="Fuel part", yaxis={"autorange": "reversed"},
        margin={"t": 50, "b": 10}, height=340,
    )
    return fig


def _heights_chart(rows: pd.DataFrame, chosen_fl: int) -> go.Figure:
    """Fuel at each height compared with the chosen one, as bars from zero.

    Plotting the totals would need an axis that does not start at zero (they differ by
    only 1-3%), which makes small differences look huge. The difference is honest and
    answers the real question: how much more or less fuel would another height need?
    """
    chosen = rows.loc[rows["flight_level"] == chosen_fl, "block_fuel_kg"].iloc[0]
    difference = rows["block_fuel_kg"] - chosen
    colours = ["#9aa5b1" if fl == chosen_fl else ("#d62728" if d > 0 else "#2ca02c")
               for fl, d in zip(rows["flight_level"], difference)]
    labels = ["your choice" if fl == chosen_fl else f"{d:+,.0f} kg"
              for fl, d in zip(rows["flight_level"], difference)]
    fig = go.Figure(go.Bar(
        x=[f"FL{fl:03d}" for fl in rows["flight_level"]], y=difference, marker_color=colours,
        text=labels, textposition="outside", cliponaxis=False,
        customdata=list(zip(rows["block_fuel_kg"], rows["headwind_kt"])),
        hovertemplate=("%{x}<br>%{y:+,.0f} kg compared with your choice<br>Block fuel: %{customdata[0]:,.0f} kg"
                       "<br>Average headwind: %{customdata[1]:+.0f} kt<extra></extra>"),
    ))
    fig.add_hline(y=0, line_color="grey")
    limit = max(difference.abs().max(), 1) * 1.3  # same room above and below zero, plus space for labels
    fig.update_layout(
        title=f"Fuel at other cruise heights compared with FL{chosen_fl:03d} (live winds)",
        xaxis_title="Cruise height (flight level)",
        yaxis_title=f"Block fuel compared with FL{chosen_fl:03d} (kg)",
        yaxis={"range": [-limit, limit], "zeroline": False},
        margin={"t": 50, "b": 10}, height=340,
    )
    return fig


# ---------------------------------------------------------------- page ----

def render() -> None:
    st.header("Fuel planner (educational estimate)")
    st.write(
        "How much fuel a flight needs, using the **real distance** between two airports and the **real "
        "wind** at cruise height, with an aircraft and load you choose."
    )
    st.caption("⚠️ Simplified textbook method with rounded aircraft numbers. Not for real flight planning.")

    request = _read_request()
    if not request:
        return
    dep_code, dest_code, alt_code = request["departure"], request["destination"], request["alternate"]
    scenario_banner(
        f"{request['aircraft']} with {request['passengers']} passengers, {request['bags']} bags and "
        f"{request['cargo_kg']:,.0f} kg cargo is hypothetical. Distances and winds are real."
    )

    # 1. Where are the three airports? (their METARs include coordinates)
    try:
        metars, errors = _fetch_airports((dep_code, dest_code, alt_code))
    except API_ERRORS as exc:
        st.error(f"Could not look up the airports: {exc}")
        return
    by_code = {m.icao: m for m in metars}
    missing = [code for code in (dep_code, dest_code, alt_code) if code not in by_code]
    for code in missing:
        st.error(f"{code}: {errors.get(code, 'not found')} The page needs a current METAR to know where it is.")
    if missing:
        return
    dep, dest, alt = by_code[dep_code], by_code[dest_code], by_code[alt_code]
    route = Route(dep_code, dest_code, (dep.latitude, dep.longitude), (dest.latitude, dest.longitude))
    alternate_nm = great_circle_nm(dest.latitude, dest.longitude, alt.latitude, alt.longitude)

    # 2. Average headwind at every cruise height (one Open-Meteo request)
    points = tuple((round(lat, 3), round(lon, 3)) for lat, lon in route.points(WIND_POINTS))
    try:
        levels_per_point = _fetch_winds(points)
    except API_ERRORS as exc:
        st.error(f"Winds aloft are not available right now, so fuel cannot be estimated: {exc}")
        return
    winds = RouteWinds(str(route), route.distance_nm, list(points), levels_per_point)
    if request["flight_level"] not in winds.flight_levels:
        st.warning(f"Open-Meteo has no wind data at FL{request['flight_level']:03d} on this route. "
                   "Pick another cruise height.")
        return

    # 3. The plan
    profile = AIRCRAFT_PROFILES[request["aircraft"]]
    try:
        plan = FuelPlan(profile, route.distance_nm, winds.average_headwind_kt(request["flight_level"]),
                        alternate_nm, request["passengers"], request["bags"], request["cargo_kg"],
                        request["extra_kg"])
    except ValueError as exc:
        st.error(f"This flight cannot be estimated: {exc}")
        return

    wind = plan.headwind_kt
    hours, minutes = divmod(round(plan.trip_time_h * 60), 60)
    if abs(wind) < 0.5:
        wind_note = f"no headwind or tailwind at FL{request['flight_level']:03d}"
    else:
        wind_note = f"{abs(wind):.0f} kt {'headwind' if wind > 0 else 'tailwind'} at FL{request['flight_level']:03d}"
    c1, c2, c3, c4 = st.columns(4)
    metric_with_note(c1, "Block fuel", f"{plan.block_fuel_kg:,.0f} kg",
                     f"≈ {plan.block_fuel_kg / 0.8:,.0f} litres", help=GLOSSARY["Block fuel"])
    metric_with_note(c2, "Flight time", f"{hours} h {minutes:02d} min",
                     f"{route.distance_nm:,.0f} nm {dep_code} → {dest_code}")
    metric_with_note(c3, "Ground speed", f"{plan.ground_speed_kt:.0f} kt", wind_note, help=GLOSSARY["Ground speed"])
    metric_with_note(c4, "Payload", f"{plan.payload_kg:,.0f} kg", f"fuel burn {plan.burn_kg_per_h:,.0f} kg/h",
                     help=GLOSSARY["Payload"])
    for problem in plan.problems:
        st.error(f"⛔ {problem}")

    # 4. Charts: the parts of this plan, and the same plan at every other height
    heights = []
    for fl in winds.flight_levels:
        if not profile.can_cruise_at(fl):
            continue  # only compare heights this aircraft could really fly at
        headwind = winds.average_headwind_kt(fl)
        try:
            heights.append({"flight_level": fl, "headwind_kt": headwind,
                            "block_fuel_kg": plan.with_headwind(headwind).block_fuel_kg})
        except ValueError:
            continue  # headwind faster than the aircraft: leave that height out
    heights = pd.DataFrame(heights)

    left, right = st.columns(2)
    left.plotly_chart(_breakdown_chart(plan), width="stretch")
    right.plotly_chart(_heights_chart(heights, request["flight_level"]), width="stretch")
    best = heights.loc[heights["block_fuel_kg"].idxmin()]
    saving = plan.block_fuel_kg - best["block_fuel_kg"]
    if saving > 1:
        st.info(f"💡 FL{int(best['flight_level']):03d} would need about {saving:,.0f} kg less fuel today "
                f"(average headwind {best['headwind_kt']:+.0f} kt). Only heights in the {profile.name}'s "
                f"cruise range ({profile.cruise_range}) are compared, and the hourly burn is treated as the "
                "same across that range, so only the wind makes the difference.")
    else:
        st.success(f"✅ FL{request['flight_level']:03d} needs the least fuel of the heights a "
                   f"{profile.name} can use ({profile.cruise_range}) today.")

    # 5. Table: how each part is worked out
    st.subheader("How each part is worked out")
    st.dataframe(pd.DataFrame({
        "Part": [name for name, _ in plan.breakdown()],
        "Fuel (kg)": [round(kg) for _, kg in plan.breakdown()],
        "How": [
            f"Fixed for a {profile.name}",
            f"{route.distance_nm:,.0f} nm ÷ {plan.ground_speed_kt:.0f} kt = {plan.trip_time_h:.2f} h × "
            f"{plan.burn_kg_per_h:,.0f} kg/h",
            "5% of trip fuel",
            f"{alternate_nm:,.0f} nm {dest_code} → {alt_code} at {profile.cruise_speed_kt:.0f} kt (no wind data)",
            f"30 min × {plan.burn_kg_per_h:,.0f} kg/h",
            "Chosen by you",
        ],
    }), hide_index=True, width="stretch")
    st.caption(f"Hourly burn = {profile.burn_kg_per_h:,.0f} kg/h + {profile.burn_per_tonne_kg_h:.0f} kg/h "
               f"per tonne of payload. Litres use jet fuel at about 0.8 kg per litre.")

    show_glossary(["Block fuel", "Trip fuel", "Contingency fuel", "Final reserve", "Alternate airport",
                   "Payload", "Ground speed", "Headwind / tailwind", "Flight level (FL)", "Nautical mile (nm)"])
