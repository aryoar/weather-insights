"""Streamlit entry point: shared page shell, navigation, and view dispatch."""

import streamlit as st

from views import (
    airport_suitability,
    airport_weather,
    analytics,
    fuel_planner,
    live_conditions,
    route_overview,
    winds_aloft,
)

st.set_page_config(page_title="Weather Insights: aviation briefing", page_icon="✈️", layout="wide")
st.title("✈️ Weather Insights: aviation weather briefing")
st.caption(
    "Real weather for a flight, explained in plain language. "
    "For learning and demonstration only: not for real flight planning."
)

page = st.sidebar.radio(
    "View",
    [
        "Airport weather",
        "Route overview",
        "Winds aloft",
        "Airport suitability",
        "Fuel planner",
        "Live Conditions",
        "Analytics",
    ],
)

if page == "Live Conditions":
    live_conditions.render()
elif page == "Analytics":
    analytics.render()
elif page == "Airport weather":
    airport_weather.render()
elif page == "Route overview":
    route_overview.render()
elif page == "Winds aloft":
    winds_aloft.render()
elif page == "Airport suitability":
    airport_suitability.render()
elif page == "Fuel planner":
    fuel_planner.render()
