"""Fuel planner page (planned). Owner: (add your name)

Goal: an educational fuel estimate, NOT for real flight planning.
- Scenario inputs (hypothetical, mark with views.common.scenario_banner): aircraft profile,
  passengers, bags, extra cargo.
- Real inputs: route distance and the wind component at cruise (from Winds aloft).
Fuel = taxi + trip + contingency (5% of trip) + alternate (to the furthest alternate)
     + final reserve (30 min) + extra. Trip time = distance / (cruise speed ± wind).

First small step: a FuelPlan class in src/weather_app/ with one @property per fuel part,
and a test with round numbers you can check by hand.
"""

import streamlit as st


def render() -> None:
    st.header("Fuel planner")
    st.info(
        "🚧 Coming soon: an educational fuel estimate based on your route, the real winds "
        "and a hypothetical aircraft, passengers and cargo."
    )
