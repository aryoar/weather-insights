"""Small display helpers shared by several pages."""

from datetime import datetime, timezone

import streamlit as st

from weather_app.client import AviationWeatherClient
from weather_app.glossary import GLOSSARY
from weather_app.logged_metars import latest_logged_reports
from weather_app.reports import clean_icao_code
from weather_app.storage import MetarStore

# ---------------------------------------------------------------- shared flight ----
# One flight for the whole app, chosen once in the sidebar ("Your flight").
DEFAULT_FLIGHT = {"departure": "LEMD", "destination": "EGLL", "alternate": "LFPG"}
_FLIGHT_KEY = "flight"              # last valid flight: {"departure", "destination", "alternate"}
_FLIGHT_ERROR_KEY = "flight_error"  # True while the last submitted flight was invalid
_ROLES = {"departure": "Departure", "destination": "Destination", "alternate": "Alternate"}


def _validate_flight(typed: dict[str, str]) -> tuple[dict[str, str] | None, list[str]]:
    """Clean three ICAO codes. Returns (flight, []) or (None, problems)."""
    cleaned, problems = {}, []
    for role, code in typed.items():
        try:
            cleaned[role] = clean_icao_code(code)
        except ValueError as exc:
            problems.append(f"{_ROLES[role]}: {exc}")
    if not problems and len(set(cleaned.values())) < 3:
        problems.append("Departure, destination and alternate must be three different airports.")
    return (None, problems) if problems else (cleaned, [])


def _store_flight(flight: dict[str, str]) -> None:
    st.session_state[_FLIGHT_KEY] = dict(flight)
    st.session_state[_FLIGHT_ERROR_KEY] = False
    # Older pages read this shape, so keep writing it.
    st.session_state["selected_airports"] = {_ROLES[role]: code for role, code in flight.items()}


def get_route() -> dict[str, str] | None:
    """The flight chosen in the sidebar: {"departure", "destination", "alternate"}.

    Returns None while the last submitted flight is invalid (the sidebar shows why).
    Before anything is submitted it returns the defaults LEMD → EGLL (alternate LFPG).
    """
    if st.session_state.get(_FLIGHT_ERROR_KEY):
        return None
    if _FLIGHT_KEY not in st.session_state:
        _store_flight(DEFAULT_FLIGHT)
    return dict(st.session_state[_FLIGHT_KEY])


def sidebar_flight() -> dict[str, str] | None:
    """'Your flight' box in the sidebar: departure, destination and alternate (validated)."""
    current = get_route() or st.session_state.get(_FLIGHT_KEY, DEFAULT_FLIGHT)
    for role in _ROLES:
        st.session_state.setdefault(f"flight_{role}", current[role])
    with st.sidebar:
        st.markdown("##### ✈️ Your flight")
        with st.form("your_flight", border=False):
            typed = {
                role: st.text_input(
                    f"{label} (ICAO)", key=f"flight_{role}", max_chars=4,
                    help=GLOSSARY["Alternate airport"] if role == "alternate" else GLOSSARY["ICAO code"],
                )
                for role, label in _ROLES.items()
            }
            submitted = st.form_submit_button("Update flight", width="stretch")
        if submitted:
            flight, problems = _validate_flight(typed)
            if flight:
                _store_flight(flight)
            else:
                st.session_state[_FLIGHT_ERROR_KEY] = True
                for problem in problems:
                    st.error(problem)
        route = get_route()
        if route:
            st.caption(f"{route['departure']} → {route['destination']} · alternate {route['alternate']}")
    return route


def route_missing_notice() -> None:
    """What a page shows when the sidebar flight is not valid yet."""
    st.info("👈 Enter a valid flight in **Your flight** in the sidebar (three different 4-letter ICAO codes).")


def show_glossary(terms: list[str] | None = None) -> None:
    """Collapsed 'Glossary' section. Pass a list of terms to show only those."""
    with st.expander("📖 Glossary: aviation terms on this page"):
        for term in terms or GLOSSARY:
            st.markdown(f"**{term}**: {GLOSSARY[term]}")


def scenario_banner(text: str) -> None:
    """Mark anything simulated or hypothetical, so it is never confused with real data."""
    st.warning(f"🧪 **SCENARIO**: {text}")


def age_text(moment: datetime) -> str:
    """'12:30 UTC (25 min ago)' for a timezone-aware UTC datetime."""
    minutes = int((datetime.now(timezone.utc) - moment).total_seconds() // 60)
    ago = f"{minutes} min ago" if minutes < 120 else f"{minutes // 60} h ago"
    return f"{moment:%d %b %H:%M} UTC ({ago})"


def metric_with_note(column, label: str, value: str, note: str, help: str | None = None) -> None:
    """A metric with a small grey note under it.

    Streamlit's `delta` would add an ↑/↓ arrow, which reads as "increased"; this is for
    plain extra information such as the same value in other units.
    """
    column.metric(label, value, help=help)
    column.caption(note)


# ---------------------------------------------------------------- METARs with fallback ----
API_ERRORS = (ConnectionError, PermissionError, LookupError, RuntimeError, ValueError)


@st.cache_data(ttl=300, show_spinner="Fetching live METARs…")
def _fetch_live_metars(codes: tuple[str, ...]):
    """Live METARs. Raises when the service is down, so Streamlit never caches a failure."""
    return AviationWeatherClient().metars(list(codes))


def load_reports(codes: tuple[str, ...]) -> tuple[list, dict[str, str], str | None]:
    """(reports, skipped airports with reasons, fallback note or None). Shared with Go/No-Go."""
    try:
        reports, errors = _fetch_live_metars(codes)
        if reports:
            return reports, errors, None
        reason = "aviationweather.gov returned no reports"
    except API_ERRORS as exc:
        reason = str(exc).rstrip(".")
    try:
        reports, errors = latest_logged_reports(MetarStore().load(), codes)
    except (OSError, ValueError) as exc:
        return [], {code: f"Live and logged METARs are both unavailable ({exc})." for code in codes}, None
    note = (f"Live METARs are unavailable right now ({reason}). Showing the latest **real** METARs "
            "logged in data/metar_history.csv instead; check the observation time of each one.")
    return reports, errors, note
