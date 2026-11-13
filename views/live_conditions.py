"""Live city weather collection and display."""

import streamlit as st

from weather_app.client import WeatherClient
from weather_app.config import get_api_key
from weather_app.storage import WeatherStore


def render() -> None:
    st.header("Live Conditions")
    store = WeatherStore()
    if "cities" not in st.session_state:
        st.session_state.cities = []

    with st.form("add_location", clear_on_submit=True):
        city = st.text_input("Add a city", placeholder="Madrid")
        submitted = st.form_submit_button("Add location")
    if submitted:
        cleaned = city.strip()
        if not cleaned or len(cleaned) > 100 or not any(char.isalpha() for char in cleaned):
            st.error("Enter a valid city name (1–100 characters, including a letter).")
        elif cleaned.casefold() not in {item.casefold() for item in st.session_state.cities}:
            st.session_state.cities.append(cleaned)

    if not st.session_state.cities:
        st.info("Add one or more cities to start collecting weather observations.")
        return

    st.write("Tracked locations: " + ", ".join(st.session_state.cities))
    if st.button("Fetch current conditions", type="primary"):
        st.session_state.latest_snapshots = []
        st.session_state.fetch_errors = {}
        st.session_state.storage_errors = {}
        try:
            client = WeatherClient(get_api_key())
            snapshots, failures = client.current_many(st.session_state.cities)
            for snapshot in snapshots:
                try:
                    store.append(snapshot)
                except OSError:
                    st.session_state.storage_errors[snapshot.location] = (
                        "Conditions were fetched but could not be saved to local history."
                    )
                except ValueError as exc:
                    st.session_state.storage_errors[snapshot.location] = str(exc)
            st.session_state.latest_snapshots = snapshots
            st.session_state.fetch_errors = failures
        except RuntimeError as exc:
            st.error(str(exc))

    for failure_city, message in st.session_state.get("fetch_errors", {}).items():
        st.warning(f"{failure_city}: {message}")
    for location, message in st.session_state.get("storage_errors", {}).items():
        st.error(f"{location}: {message}")
    for snapshot in st.session_state.get("latest_snapshots", []):
        with st.container(border=True):
            st.subheader(snapshot.location)
            st.write(snapshot.description)
            cols = st.columns(4)
            cols[0].metric("Temperature", f"{snapshot.temperature_c:.1f} °C")
            cols[1].metric("Feels like", f"{snapshot.feels_like_c:.1f} °C")
            cols[2].metric("Humidity", f"{snapshot.humidity_pct}%")
            cols[3].metric("Wind", f"{snapshot.wind_speed_mps:.1f} m/s")
            st.caption(f"Collected {snapshot.observed_at:%Y-%m-%d %H:%M UTC}")
