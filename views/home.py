"""Start here: what the app is for, who it is for, and the four-step briefing flow.

Progress comes from st.session_state["visited_pages"] (filled in by app.py) and the
two practice scores, so a student can see where they are in the session.
"""

import streamlit as st

from .common import get_route
from .theme import APP_NAME, ACCENT, card, hero

# The briefing flow a student follows, and the pages (url paths in app.py) that complete each step.
STEPS = [
    ("Weather", "🌦️", "Read the METAR and TAF for your three airports.", ["airport-weather"]),
    ("Route & winds", "🧭", "The route, the weather along it and the winds at altitude.", ["route-overview", "winds-aloft"]),
    ("Airport check", "🛬", "Runways, crosswind and daylight at each airport.", ["airport-suitability"]),
    ("Fuel", "⛽", "A fuel estimate with today's real winds.", ["fuel-planner"]),
]


def _link(url_path: str, label: str) -> None:
    """Link to a page registered in app.py (skipped when the page runs on its own, e.g. in a test)."""
    page = st.session_state.get("pages_by_path", {}).get(url_path)
    if page is not None:
        st.page_link(page, label=label, icon=":material/arrow_forward:")


def render() -> None:
    hero("Learn aviation weather on today's real data",
         "Decode live METARs, brief a flight step by step and practise the go/no-go call. "
         "Built for student pilots and their instructors.", kicker=f"{APP_NAME} · Start here")

    visited = st.session_state.get("visited_pages", set())
    done = [any(page in visited for page in pages) for *_, pages in STEPS]
    route = get_route()
    trainer = st.session_state.get("trainer_score")
    gng = st.session_state.get("gng_score")
    practised = (trainer.answered if trainer else 0) + (gng.answered if gng else 0)
    correct = (trainer.correct if trainer else 0) + (gng.correct if gng else 0)

    cols = st.columns(3)
    cols[0].metric("Your flight", f"{route['departure']} → {route['destination']}" if route else "not set",
                   help="Departure → destination. Change it in 'Your flight' in the sidebar.")
    cols[1].metric("Briefing steps done", f"{sum(done)} of {len(STEPS)}")
    cols[2].metric("Practice answers", f"{correct} of {practised} correct" if practised else "none yet",
                   help="METAR trainer answers plus Go/No-Go decisions this session.")

    st.subheader("Who it is for")
    left, right = st.columns(2)
    with left:
        card("Student pilots", "Read real METARs with instant feedback, then check every flight against "
             "example personal limits before you ask your instructor.", "🧑‍✈️")
    with right:
        card("Instructors", "Set the limits, change wind, visibility or ceiling as a marked scenario, and "
             "use the briefing sheet in the pre-flight discussion. EASA units: metric next to kt and ft.", "🎓")

    st.subheader("Brief a flight in four steps")
    st.progress(sum(done) / len(STEPS), text=f"{sum(done)} of {len(STEPS)} steps visited this session")
    columns = st.columns(len(STEPS))
    for number, (column, (title, icon, text, pages), finished) in enumerate(zip(columns, STEPS, done), start=1):
        with column:
            card(f"{number}. {title}{'  ✓' if finished else ''}", text, icon, accent="#0ca30c" if finished else ACCENT)
            _link(pages[0], "Open")

    st.subheader("Then practise")
    left, right = st.columns(2)
    with left:
        card("METAR trainer", "Five questions on a real METAR, each with an explanation.", "📖")
        _link("metar-trainer", "Start the trainer")
    with right:
        card("Go / No-Go", "Make the call for your departure first, then see every check.", "🎯")
        _link("go-no-go", "Make a decision")
