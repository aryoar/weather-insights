"""Route overview page (planned). Owner: (add your name)

Goal: the user enters departure and destination airports, and the map zooms to just that
part of the world, with the route drawn as a black line, coloured weather dots along it,
and smaller markers for nearby airports that could serve as alternates.

Data (all real, all free):
- Airport coordinates: the METAR from AviationWeatherClient (latitude/longitude).
- Weather along the route: OpenWeatherMap current weather at evenly spaced points.
- Nearby airports: aviationweather.gov METARs for the map area.
Map: pydeck (already installed with Streamlit): PathLayer for the line, ScatterplotLayer for dots.

First small step: a function in src/weather_app/ that returns N evenly spaced points
between two coordinates along the great circle, with a test (Madrid-London is about 670 nm).
"""

import streamlit as st


def render() -> None:
    st.header("Route overview")
    st.info(
        "🚧 Coming soon: a map zoomed to your route, the route as a line, the weather along it, "
        "and nearby airports you could divert to."
    )
