"""Go/No-Go practice page: decide first, then see the checks.

The student looks at the REAL METAR for the departure airport of their flight (sidebar),
commits to GO or NO-GO, and only then sees every check against their personal limits
and whether their call was right. Instructor mode (sidebar) can edit the limits and
override wind, visibility and ceiling as a clearly marked SCENARIO.
All checks live in weather_app.decision; this file only collects choices and shows results.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from weather_app.airports import load_runways
from weather_app.decision import STUDENT_LIMITS, PilotLimits, apply_scenario, evaluate_go_no_go, grade_choice
from weather_app.glossary import GLOSSARY
from weather_app.training import Scoreboard

from .common import age_text, get_route, load_reports, route_missing_notice, scenario_banner, show_glossary
from .theme import card, hero, raw_report, status_badge

RUNWAY_FILE = Path(__file__).resolve().parents[1] / "data" / "runways.csv"
CHECK_ICONS = {"Pass": "✅", "Pass (close to limit)": "⚠️", "Fail": "⛔", "Unknown": "❔"}


@st.cache_data(show_spinner=False)
def _runways() -> dict:
    try:
        return load_runways(RUNWAY_FILE)
    except FileNotFoundError:
        return {}


def _scoreboard() -> Scoreboard:
    return st.session_state.setdefault("gng_score", Scoreboard())


def _instructor_panel(report) -> tuple[PilotLimits, dict | None]:
    """Sidebar: limits (example preset by default) and an optional SCENARIO override."""
    with st.sidebar:
        st.divider()
        instructor = st.toggle("🎓 Instructor mode", key="gng_instructor",
                               help="Edit the limits or set up a practice scenario.")
        if not instructor:
            return STUDENT_LIMITS, None
        st.markdown("**Personal limits**")
        limits = PilotLimits(
            max_crosswind_kt=st.number_input("Max crosswind (kt)", 1, 40, int(STUDENT_LIMITS.max_crosswind_kt), key="gng_xwind"),
            min_visibility_km=st.number_input("Min visibility (km)", 0.5, 10.0, float(STUDENT_LIMITS.min_visibility_km), 0.5, key="gng_vis"),
            min_ceiling_ft=st.number_input("Min ceiling (ft)", 0, 5000, int(STUDENT_LIMITS.min_ceiling_ft), 100, key="gng_ceiling"),
            max_gust_spread_kt=st.number_input("Max gust spread (kt)", 0, 30, int(STUDENT_LIMITS.max_gust_spread_kt), key="gng_gust"),
            vfr_required=st.checkbox("VFR only", value=STUDENT_LIMITS.vfr_required, key="gng_vfr"),
            name="Instructor limits",
        )
        if not st.toggle("🧪 Scenario: override the weather", key="gng_scenario_on"):
            return limits, None
        direction = report.wind_direction_deg if report.wind_direction_deg is not None else 0
        scenario = {
            "wind_direction_deg": st.slider("Wind from (°)", 0, 350, int(round(direction / 10) * 10), 10, key="gng_s_dir"),
            "wind_speed_kt": st.slider("Wind speed (kt)", 0, 40, int(report.wind_speed_kt or 0), key="gng_s_speed"),
            "wind_gust_kt": st.slider("Gusts (kt, 0 = none)", 0, 50, int(report.wind_gust_kt or 0), key="gng_s_gust"),
            "visibility_km": st.slider("Visibility (km)", 0.5, 10.0, float(min(report.visibility_km or 10.0, 10.0)), 0.5, key="gng_s_vis"),
        }
        if st.checkbox("No ceiling", value=report.ceiling_ft is None, key="gng_s_noceil"):
            scenario["clear_ceiling"] = True
        else:
            scenario["ceiling_ft"] = st.slider("Ceiling (ft)", 200, 5000, int(report.ceiling_ft or 2000), 100, key="gng_s_ceil")
        return limits, scenario


def render() -> None:
    hero("Go / No-Go practice", "Read the real weather at your departure airport, make your call first, "
         "then see every check against your personal limits.", kicker="Practise · Decide")

    route = get_route()
    if route is None:
        route_missing_notice()
        return
    code = route["departure"]
    reports, errors, fallback_note = load_reports((code,))
    if fallback_note:
        st.info(f"📼 {fallback_note}")
    if not reports:
        st.error(f"{code}: {errors.get(code, 'no METAR available')} Pick another departure in the sidebar.")
        return
    real = reports[0]

    limits, scenario = _instructor_panel(real)
    report = real
    if scenario:
        try:
            report = apply_scenario(real, **scenario)
        except ValueError as exc:
            st.error(f"Scenario not valid: {exc}")
            return
        scenario_banner("The instructor changed the wind, visibility or ceiling below. The raw METAR is the "
                        "real one; the checks use the scenario values.")

    st.markdown(f"**{real.name} ({code})** · observed {age_text(real.observed_at)}")
    raw_report(real.raw_text)
    cols = st.columns(4)
    cols[0].metric("Wind", "calm" if not report.wind_speed_kt else f"{report.wind_speed_kt:.0f} kt",
                   help=report.wind_text)
    cols[1].metric("Visibility", report.visibility_text, help=GLOSSARY["Visibility"])
    cols[2].metric("Ceiling", "none" if report.ceiling_ft is None else f"{report.ceiling_ft:,} ft",
                   help=GLOSSARY["Ceiling"])
    cols[3].metric("Category", report.flight_category, help=GLOSSARY["Flight category"])
    card(limits.name, limits.summary + ". "
         + ("These are EXAMPLE school limits for practice, not regulations." if limits is STUDENT_LIMITS
            else "Set by the instructor for this practice session."), "📏")

    decision = evaluate_go_no_go(report, _runways().get(code, []), limits)
    situation = f"gng|{code}|{real.observed_at:%Y%m%d%H%M}|{limits}|{sorted((scenario or {}).items())}"
    choice_key = f"choice::{situation}"

    # Step 1: commit to a decision before seeing the checks.
    if choice_key not in st.session_state:
        st.subheader("1 · Your decision")
        pick = st.radio("Would you take off?", ["GO", "NO-GO"], index=None, horizontal=True, key=f"pick::{situation}")
        if st.button("Lock in my decision", type="primary", disabled=pick is None):
            correct, _ = grade_choice(pick, decision)
            _scoreboard().record(correct)
            st.session_state[choice_key] = pick
            st.rerun()
        st.caption("The checks appear after you lock in your choice.")
    else:
        choice = st.session_state[choice_key]
        correct, explanation = grade_choice(choice, decision)
        st.subheader("2 · The checks")
        st.markdown(f"Verdict with these limits: {status_badge(decision.verdict)}", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame([{
            "Check": check.name, "Observed": check.value, "Your limit": check.limit,
            "Result": f"{CHECK_ICONS[check.status]} {check.status}",
        } for check in decision.checks]), hide_index=True, width="stretch")
        st.subheader("3 · Your call")
        message = f"You chose **{choice}**. {explanation}"
        (st.success if correct else st.error)(("✅ " if correct else "❌ ") + message)
        with st.expander("Why each check passed or failed"):
            for check in decision.checks:
                st.markdown(f"- {CHECK_ICONS[check.status]} **{check.name}**: {check.explanation}")
        if st.button("Decide again"):
            del st.session_state[choice_key]
            st.rerun()

    board = _scoreboard()
    st.caption(f"Go/No-Go score this session: {board}"
               + ("" if board.accuracy_pct is None else f" ({board.accuracy_pct:.0f}%)"))
    show_glossary(["Flight category", "Ceiling", "Visibility", "Gust", "Knots (kt)", "METAR"])
