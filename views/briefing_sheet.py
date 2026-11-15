"""Briefing sheet page: a one-page summary of the training flight, ready to download.

Uses the flight from the sidebar, the real METARs for its three airports (live, or the
latest logged ones if aviationweather.gov is down) and the go/no-go check with the
example student limits. The text itself is built by weather_app.briefing.BriefingSheet.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from weather_app.airports import load_runways
from weather_app.briefing import BriefingSheet
from weather_app.decision import STUDENT_LIMITS, evaluate_go_no_go
from weather_app.route import great_circle_nm

from .common import get_route, load_reports, metric_with_note, route_missing_notice
from .theme import badge, hero

RUNWAY_FILE = Path(__file__).resolve().parents[1] / "data" / "runways.csv"


def render() -> None:
    hero("Briefing sheet", "Everything about your training flight on one page: download it and take it "
         "to your instructor.", kicker="Brief · Summary")

    route = get_route()
    if route is None:
        route_missing_notice()
        return
    codes = (route["departure"], route["destination"], route["alternate"])
    reports, errors, fallback_note = load_reports(codes)
    if fallback_note:
        st.info(f"📼 {fallback_note}")
    by_code = {report.icao: report for report in reports}

    departure = by_code.get(route["departure"])
    decision = None
    if departure is not None:
        try:
            runways = load_runways(RUNWAY_FILE).get(route["departure"], [])
        except FileNotFoundError:
            runways = []
        decision = evaluate_go_no_go(departure, runways, STUDENT_LIMITS)
    destination = by_code.get(route["destination"])
    distance = None
    if departure is not None and destination is not None:
        distance = great_circle_nm(departure.latitude, departure.longitude,
                                   destination.latitude, destination.longitude)

    sheet = BriefingSheet(route, by_code, decision, distance)
    cols = st.columns(3)
    cols[0].metric("Flight", f"{route['departure']} → {route['destination']}", help=f"Alternate {route['alternate']}")
    metric_with_note(cols[1], "Distance", "n/a" if distance is None else f"{distance:,.0f} nm",
                     "" if distance is None else f"{distance * 1.852:,.0f} km")
    cols[2].metric("Go / No-Go (example limits)", sheet.verdict or "n/a")
    for code in sheet.missing_airports:
        st.warning(f"{code}: {errors.get(code, 'no METAR available')}")

    if sheet.verdict:
        badge(sheet.verdict, f"Departure check: {sheet.verdict} (example student limits)")
    st.dataframe(pd.DataFrame(sheet.airport_rows()), hide_index=True, width="stretch")
    with st.expander("Preview the sheet", expanded=False):
        st.markdown(sheet.to_markdown())
    st.download_button("⬇️ Download briefing (.md)", sheet.to_markdown(), file_name=sheet.file_name,
                       mime="text/markdown", type="primary")
