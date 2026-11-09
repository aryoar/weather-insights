"""Airport suitability page (planned). Owner: (add your name)

Goal: can each airport be used right now? Real NOTAM data (closures, works) is not freely
available, so this page combines what IS real and computable with clearly marked scenarios:
- Real: flight category (METAR), crosswind on each runway (METAR wind vs runway headings
  from the OurAirports runways.csv, public domain), day/night (sunrise/sunset).
- Scenario (user-entered, shown with views.common.scenario_banner): closures, strikes,
  maintenance.

First small step: a function crosswind_kt(wind_dir, wind_speed, runway_heading) with a
test (wind 90° off the runway at 20 kt = 20 kt crosswind; along the runway = 0).
"""

import streamlit as st


def render() -> None:
    st.header("Airport suitability")
    st.info(
        "🚧 Coming soon: whether each airport is usable, based on real weather and runway "
        "crosswind, plus scenario switches for closures or strikes."
    )
