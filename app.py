"""Streamlit interface for live weather and accumulated local analytics."""

import streamlit as st

from weather_app.analytics import comfort_ranking, latest_comparison, temperature_trend
from weather_app.client import WeatherClient
from weather_app.config import get_api_key
from weather_app.storage import WeatherStore

st.set_page_config(page_title="Weather Insights", page_icon="🌤️", layout="wide")
st.title("Weather Insights")
st.caption("Live conditions and analytics built from observations collected by this app.")

store = WeatherStore()
page = st.sidebar.radio("View", ["Live Conditions", "Analytics"])

if page == "Live Conditions":
    st.header("Live Conditions")
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

    if st.session_state.cities:
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
    else:
        st.info("Add one or more cities to start collecting weather observations.")

elif page == "Analytics":
    st.header("Analytics")
    history = store.load()
    if history.empty:
        st.info("No observations have been collected yet. Fetch current conditions on the Live Conditions page first.")
    else:
        comparison = latest_comparison(history)
        ranking = comfort_ranking(history)
        cities = sorted(comparison["location"].dropna().unique().tolist())

        st.subheader("Temperature history")
        selected_location = st.selectbox("Location", cities)
        trend = temperature_trend(history, selected_location)
        st.line_chart(trend, x="observed_at", y="temperature_c", y_label="Temperature (°C)")

        left, right = st.columns(2)
        with left:
            st.subheader("Latest temperatures by location")
            st.bar_chart(comparison, x="location", y="temperature_c", y_label="Temperature (°C)")
        with right:
            st.subheader("Latest feels-like difference")
            st.bar_chart(comparison, x="location", y="feels_like_delta_c", y_label="Feels like minus actual (°C)")

        st.subheader("Comfort ranking")
        st.caption("Comparative index = temperature − 0.5 × wind speed − 0.1 × humidity above 60%. Higher scores rank first.")
        st.dataframe(
            ranking[["location", "observed_at", "temperature_c", "humidity_pct", "wind_speed_mps", "comfort_index"]],
            hide_index=True,
            use_container_width=True,
        )
