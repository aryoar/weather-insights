"""Airport weather page: real METAR (observed now) and TAF (forecast) reports for the
departure, destination and alternate airports, from aviationweather.gov."""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from weather_app.client import AviationWeatherClient
from weather_app.glossary import GLOSSARY
from weather_app.reports import M_PER_FOOT, clean_icao_code
from weather_app.storage import MetarStore

from .common import age_text, show_glossary

ROLES = ["Departure", "Destination", "Alternate"]
DEFAULT_CODES = {"Departure": "LEMD", "Destination": "EGLL", "Alternate": "LFPG"}


# Cache answers for 5 minutes: METARs change at most every 30 min, and the API asks
# clients to keep requests low. Same codes within 5 min = no new request.
@st.cache_data(ttl=300, show_spinner="Fetching airport reports…")
def _fetch_reports(codes: tuple[str, ...]):
    client = AviationWeatherClient()
    try:
        metars, metar_errors = client.metars(list(codes))
    except (ConnectionError, PermissionError, LookupError, RuntimeError, ValueError) as exc:
        metars = []
        metar_errors = {code: str(exc) for code in codes}
    fetched_at = datetime.now(timezone.utc)
    try:
        tafs, taf_errors = client.tafs(list(codes))
    except (ConnectionError, PermissionError, LookupError, RuntimeError, ValueError) as exc:
        tafs = []
        taf_errors = {code: str(exc) for code in codes}
    return metars, metar_errors, tafs, taf_errors, fetched_at


def _read_codes() -> dict[str, str] | None:
    """Form with one code per role. Returns {role: code} once the user submits valid codes."""
    with st.form("airport_codes"):
        columns = st.columns(3)
        typed = {
            role: column.text_input(
                f"{role} airport (ICAO code)",
                value=st.session_state.get("selected_airports", DEFAULT_CODES)[role],
                max_chars=4,
                help=GLOSSARY["ICAO code"] if role != "Alternate" else GLOSSARY["Alternate airport"],
            )
            for role, column in zip(ROLES, columns)
        }
        submitted = st.form_submit_button("Show airport weather", type="primary")

    if submitted:
        cleaned, problems = {}, []
        for role, code in typed.items():
            try:
                cleaned[role] = clean_icao_code(code)
            except ValueError as exc:
                problems.append(f"{role}: {exc}")
        if problems:
            for problem in problems:
                st.error(problem)
            return None
        st.session_state.selected_airports = cleaned
    return st.session_state.get("selected_airports")


def _show_summary(metars) -> None:
    """Worst airport first. sorted() works on MetarReport because it defines __lt__."""
    ranked = sorted(metars, reverse=True)
    parts = [f"{m.category_info['emoji']} **{m.icao}** {m.flight_category}" for m in ranked]
    st.markdown("**Flying conditions, worst first:** " + " → ".join(parts))


def _show_metar(metar) -> None:
    info = metar.category_info
    st.markdown(f"#### {info['emoji']} {info['label']} flying conditions ({metar.flight_category})")
    st.caption(info["explanation"])

    cols = st.columns(4)
    cols[0].metric("Wind", f"{metar.wind_speed_kt or 0:.0f} kt", help=f"{metar.wind_text}. {GLOSSARY['Knots (kt)']}")
    cols[1].metric("Visibility", metar.visibility_text, help=GLOSSARY["Visibility"])
    ceiling = metar.ceiling_ft
    cols[2].metric(
        "Cloud ceiling",
        "none" if ceiling is None else f"{ceiling:,} ft",
        help=GLOSSARY["Ceiling"] + ("" if ceiling is None else f" ({ceiling * M_PER_FOOT:,.0f} m)"),
    )
    cols[3].metric(
        "Temperature",
        "n/a" if metar.temperature_c is None else f"{metar.temperature_c:.0f} °C",
        help=None if metar.pressure_hpa is None else f"Pressure (QNH): {metar.pressure_hpa:.0f} hPa. {GLOSSARY['QNH (pressure)']}",
    )
    st.write(f"**Wind:** {metar.wind_text}. **Weather:** {metar.weather_text}. **Clouds:** {metar.clouds_text}.")
    st.caption(f"Observed {age_text(metar.observed_at)}")
    with st.expander("Raw METAR (the coded text pilots read)"):
        st.code(metar.raw_text, language=None)


def _show_taf(taf) -> None:
    st.markdown("#### Forecast (TAF)")
    st.caption(
        f"Valid {taf.valid_from:%a %H:%M} – {taf.valid_to:%a %H:%M} UTC "
        f"({taf.hours_covered:.0f} hours). Empty cells mean no change from the main forecast."
    )
    table = pd.DataFrame([period.to_row() for period in taf.periods])
    st.dataframe(table, hide_index=True, width="stretch")
    with st.expander("Raw TAF"):
        st.code(taf.raw_text, language=None)


def render() -> None:
    st.header("Airport weather")
    st.write(
        "Current weather (**METAR**) and official forecast (**TAF**) for the airports of your flight. "
        "Real reports from aviationweather.gov, translated into plain language."
    )
    codes = _read_codes()
    if not codes:
        return

    try:
        metars, metar_errors, tafs, taf_errors, fetched_at = _fetch_reports(
            tuple(dict.fromkeys(codes.values()))
        )
    except (ConnectionError, PermissionError, LookupError, RuntimeError) as exc:
        st.error(str(exc))
        return

    metar_store = MetarStore()
    storage_errors = []
    saved_count = 0
    for metar in metars:
        try:
            if metar_store.append_if_new(metar, fetched_at):
                saved_count += 1
        except (OSError, ValueError) as exc:
            storage_errors.append(f"{metar.icao}: {exc}")
    if saved_count:
        st.caption(f"Saved {saved_count} new METAR observation(s) to the project history.")
    for message in storage_errors:
        st.error(f"Could not save METAR history for {message}")

    if metars:
        _show_summary(metars)
    metar_by_code = {m.icao: m for m in metars}
    taf_by_code = {t.icao: t for t in tafs}

    for role, code in codes.items():
        with st.container(border=True):
            report = metar_by_code.get(code) or taf_by_code.get(code)
            name = report.name if report else code
            st.subheader(f"{role}: {name} ({code})")
            if code in metar_by_code:
                _show_metar(metar_by_code[code])
            else:
                st.warning(f"Current weather: {metar_errors.get(code, 'not available')}")
            if code in taf_by_code:
                _show_taf(taf_by_code[code])
            else:
                st.info(f"Forecast: {taf_errors.get(code, 'not available')} Smaller airports often have no TAF.")

    show_glossary(["METAR", "TAF", "ICAO code", "UTC (Z)", "Flight category", "Ceiling",
                   "Visibility", "Knots (kt)", "Gust", "QNH (pressure)", "Alternate airport",
                   "TEMPO", "BECMG", "PROB30 / PROB40", "FM"])
