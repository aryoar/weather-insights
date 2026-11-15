"""METAR trainer page: decode a REAL METAR and answer five multiple-choice questions.

Reports come live from aviationweather.gov for eight European airports. If that service
cannot be reached, the page falls back to the latest real METARs we logged in
data/metar_history.csv and says so. Questions and explanations are built in
weather_app.training; this file only shows them and keeps the score.
"""

import random

import streamlit as st

from weather_app.glossary import GLOSSARY
from weather_app.training import TRAINER_AIRPORTS, Scoreboard, build_questions

from .common import age_text, load_reports, show_glossary
from .theme import badge, empty_state, hero, raw_report


def _scoreboard() -> Scoreboard:
    return st.session_state.setdefault("trainer_score", Scoreboard())


def render() -> None:
    hero("METAR trainer", "Pick an airport, read its real METAR and decode it: five questions, "
         "each with an explanation.", kicker="Learn · Decode")

    reports, errors, fallback_note = load_reports(tuple(TRAINER_AIRPORTS))
    if fallback_note:
        st.info(f"📼 {fallback_note}")
    if errors:
        st.caption("Skipped: " + "; ".join(f"{code}: {message}" for code, message in errors.items()))
    if not reports:
        empty_state("No METARs are available at the moment, live or logged. Try again in a few minutes.")
        return

    by_code = {report.icao: report for report in reports}
    codes = [code for code in TRAINER_AIRPORTS if code in by_code]
    board = _scoreboard()

    left, middle, right = st.columns([2, 1, 1])
    code = left.selectbox("Airport", codes, key="trainer_airport",
                          format_func=lambda c: f"{c} · {TRAINER_AIRPORTS[c]}")
    middle.metric("Your score", str(board), help="Correct answers this session, across all airports.")
    right.metric("Accuracy", "–" if board.accuracy_pct is None else f"{board.accuracy_pct:.0f}%")

    report = by_code[code]
    round_key = f"trainer_round_{code}"
    st.session_state.setdefault(round_key, 0)
    st.markdown(f"**{report.name}** · observed {age_text(report.observed_at)}")
    raw_report(report.raw_text)
    st.caption("Decode it yourself first: the questions below hide the answers until you check them.")

    seed = f"{report.icao}-{report.observed_at:%Y%m%d%H%M}-{st.session_state[round_key]}"
    questions = build_questions(report, random.Random(seed))
    form_id = f"quiz-{seed}"
    with st.form(form_id):
        answers = [
            st.radio(f"**{number}. {question.prompt}**", question.options, index=None, key=f"{form_id}-{number}")
            for number, question in enumerate(questions, start=1)
        ]
        submitted = st.form_submit_button("Check my answers", type="primary")

    checked_key = f"checked-{form_id}"
    if submitted:
        if any(answer is None for answer in answers):
            st.warning("Answer every question first.")
        elif checked_key not in st.session_state:
            st.session_state[checked_key] = answers  # score each quiz once, even if submitted again
            for question, answer in zip(questions, answers):
                board.record(question.is_correct(answer))
            st.rerun()  # refresh the score metrics above

    if checked_key in st.session_state:
        given = st.session_state[checked_key]
        right_count = sum(q.is_correct(a) for q, a in zip(questions, given))
        st.subheader(f"You got {right_count} of {len(questions)} right")
        badge(report.flight_category, f"This METAR is {report.flight_category}")
        for number, (question, answer) in enumerate(zip(questions, given), start=1):
            ok = question.is_correct(answer)
            with st.container(border=True):
                st.markdown(f"{'✅' if ok else '❌'} **{number}. {question.topic}**"
                            + (f" · look at `{question.code_group}`" if question.code_group else ""))
                if not ok:
                    st.markdown(f"You answered *{answer}*. Correct: **{question.correct}**")
                st.caption(question.explanation)
        if st.button("New questions for this METAR"):
            st.session_state[round_key] += 1
            st.rerun()

    show_glossary(["METAR", "Flight category", "Ceiling", "Visibility", "Knots (kt)", "Gust", "QNH (pressure)"])
    st.caption(f"{GLOSSARY['UTC (Z)']}")
