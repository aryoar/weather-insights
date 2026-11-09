"""Winds aloft page (planned). Owner: (add your name)

Goal: a model-based winds aloft view (NOT an official SIGWX chart): wind and temperature
at several cruise heights along the route, and the headwind/tailwind each height gives.

Data: Open-Meteo forecast API (free, no key, under 10,000 calls/day), pressure-level
variables such as wind_speed_250hPa, wind_direction_250hPa, temperature_250hPa.
Roughly: 850 hPa ≈ FL050, 700 ≈ FL100, 500 ≈ FL180, 300 ≈ FL300, 250 ≈ FL340, 200 ≈ FL390.

Derived metric: headwind component = wind speed × cos(wind direction − route direction).
Positive = headwind (slower, more fuel), negative = tailwind.

First small step: an OpenMeteoClient(APIClient) subclass in client.py with one method
that returns wind and temperature at those levels for one coordinate.
"""

import streamlit as st


def render() -> None:
    st.header("Winds aloft")
    st.info(
        "🚧 Coming soon: model-based wind and temperature at cruise heights along your route, "
        "and whether each height gives you a headwind or a tailwind."
    )
