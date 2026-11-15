"""Streamlit entry point: page set-up, navigation in four sections, and the shared flight sidebar.

Each page lives in views/ (one file per page, with a render() function). The sidebar
"Your flight" box (views/common.py) sets the departure, destination and alternate that
every briefing page uses.
"""

import streamlit as st

from views import (
    airport_suitability,
    airport_weather,
    analytics,
    briefing_sheet,
    fuel_planner,
    go_no_go,
    home,
    live_conditions,
    metar_trainer,
    route_overview,
    winds_aloft,
)
from views.common import sidebar_flight
from views.theme import APP_NAME, NOTICE, apply_theme

st.set_page_config(page_title=f"{APP_NAME}: aviation weather training", page_icon="✈️", layout="wide")
apply_theme()

# url_path is required: every page function is called render(), so Streamlit cannot name them itself.
PAGES = {
    "📚 Learn": [
        st.Page(home.render, title="Start here", icon=":material/flight_takeoff:", url_path="start", default=True),
        st.Page(metar_trainer.render, title="METAR trainer", icon=":material/school:", url_path="metar-trainer"),
    ],
    "🧭 Brief": [
        st.Page(airport_weather.render, title="Airport weather", icon=":material/partly_cloudy_day:", url_path="airport-weather"),
        st.Page(route_overview.render, title="Route overview", icon=":material/route:", url_path="route-overview"),
        st.Page(winds_aloft.render, title="Winds aloft", icon=":material/air:", url_path="winds-aloft"),
        st.Page(airport_suitability.render, title="Airport suitability", icon=":material/flight_land:", url_path="airport-suitability"),
        st.Page(fuel_planner.render, title="Fuel planner", icon=":material/local_gas_station:", url_path="fuel-planner"),
        st.Page(briefing_sheet.render, title="Briefing sheet", icon=":material/description:", url_path="briefing-sheet"),
    ],
    "🎯 Practise": [
        st.Page(go_no_go.render, title="Go / No-Go", icon=":material/rule:", url_path="go-no-go"),
    ],
    "📊 Data": [
        st.Page(live_conditions.render, title="Live Conditions", icon=":material/thermostat:", url_path="live-conditions"),
        st.Page(analytics.render, title="Analytics", icon=":material/monitoring:", url_path="analytics"),
    ],
}
st.session_state["pages_by_path"] = {page.url_path: page for pages in PAGES.values() for page in pages}

page = st.navigation(PAGES, expanded=True)
sidebar_flight()
st.sidebar.caption(f"⚠️ {NOTICE}")
st.session_state.setdefault("visited_pages", set()).add(page.url_path)

page.run()

st.divider()
st.caption(f"⚠️ **{NOTICE}** {APP_NAME} is a training aid for flight schools. Weather data: aviationweather.gov "
           "(METAR/TAF), OpenWeatherMap, Open-Meteo, and our own logs.")
