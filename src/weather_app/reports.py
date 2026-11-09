"""Aviation weather reports (METAR and TAF) from aviationweather.gov, in plain language.

A METAR is the weather an airport observed (usually every 30 or 60 minutes).
A TAF is the airport's official forecast (usually for the next 24-30 hours).
The API already decodes most of the coded text; this module turns the rest into
words a non-pilot can read, and converts units (knots, miles, feet) for display.
"""

import re
from datetime import datetime, timezone

KM_PER_MILE = 1.609344
KMH_PER_KNOT = 1.852
M_PER_FOOT = 0.3048

# Official FAA flight categories, from best to worst. "rank" lets us sort airports.
FLIGHT_CATEGORIES = {
    "VFR": {
        "rank": 0, "label": "Good", "emoji": "🟢",
        "explanation": "Visual flight rules: clouds above 3,000 ft and visibility over 5 miles "
                       "(8 km). Pilots can fly by looking outside.",
    },
    "MVFR": {
        "rank": 1, "label": "Moderate", "emoji": "🔵",
        "explanation": "Marginal visual flight rules: clouds 1,000-3,000 ft or visibility 3-5 miles "
                       "(5-8 km). Still visual, but needs extra care.",
    },
    "IFR": {
        "rank": 2, "label": "Poor", "emoji": "🔴",
        "explanation": "Instrument flight rules: clouds 500-1,000 ft or visibility 1-3 miles "
                       "(1.6-5 km). Pilots must fly using instruments.",
    },
    "LIFR": {
        "rank": 3, "label": "Very poor", "emoji": "🟣",
        "explanation": "Low instrument flight rules: clouds below 500 ft or visibility under 1 mile "
                       "(1.6 km). Only well-equipped aircraft and crews can land.",
    },
}
UNKNOWN_CATEGORY = {
    "rank": -1, "label": "Unknown", "emoji": "⚪",
    "explanation": "The report did not include enough information to work out a category.",
}

CLOUD_COVER = {
    "FEW": "few clouds", "SCT": "scattered clouds", "BKN": "broken clouds",
    "OVC": "overcast", "OVX": "sky hidden (fog or precipitation)", "VV": "sky hidden (fog or precipitation)",
    "CLR": "no clouds detected", "SKC": "clear sky", "NSC": "no significant clouds",
    "NCD": "no clouds detected", "CAVOK": "no significant clouds, good visibility",
}
# A "ceiling" is the lowest layer covering more than half the sky.
CEILING_COVERS = {"BKN", "OVC", "OVX", "VV"}

TAF_CHANGE_TYPES = {
    None: "Main forecast",
    "FM": "From this time",
    "BECMG": "Gradually becoming",
    "TEMPO": "Temporarily",
    "PROB": "Possibly",
}

# Weather codes (e.g. "-SHRA" = light showers of rain). Descriptors come before phenomena.
_INTENSITY = {"-": "light", "+": "heavy"}
_DESCRIPTORS = {
    "MI": "shallow", "BC": "patches of", "PR": "partial", "DR": "low drifting",
    "BL": "blowing", "SH": "showers of", "TS": "thunderstorm with", "FZ": "freezing",
}
_PHENOMENA = {
    "DZ": "drizzle", "RA": "rain", "SN": "snow", "SG": "snow grains", "IC": "ice crystals",
    "PL": "ice pellets", "GR": "hail", "GS": "small hail", "UP": "unknown precipitation",
    "BR": "mist", "FG": "fog", "FU": "smoke", "VA": "volcanic ash", "DU": "dust",
    "SA": "sand", "HZ": "haze", "PY": "spray", "PO": "dust whirls", "SQ": "squalls",
    "FC": "funnel cloud", "SS": "sandstorm", "DS": "duststorm",
}

_ICAO_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{3}$")


def clean_icao_code(code: str) -> str:
    """Validate an airport code before calling the API. Returns it in capitals."""
    cleaned = code.strip().upper()
    if not _ICAO_PATTERN.match(cleaned):
        raise ValueError(
            f"'{code.strip()}' is not a valid ICAO airport code. Use 4 characters, e.g. LEMD for Madrid."
        )
    return cleaned


def explain_weather_codes(codes: str | None) -> str:
    """Translate a weather string such as '-SHRA BR' into 'light showers of rain, mist'."""
    if not codes:
        return "no significant weather"
    phrases = []
    for token in codes.split():
        words = []
        nearby = token.startswith("VC")
        rest = token[2:] if nearby else token
        if rest[:1] in _INTENSITY:
            words.append(_INTENSITY[rest[0]])
            rest = rest[1:]
        parts = [rest[i:i + 2] for i in range(0, len(rest), 2)]
        if not parts or any(p not in _DESCRIPTORS and p not in _PHENOMENA for p in parts):
            phrases.append(f"'{token}'")  # unknown code: show it as-is rather than guess
            continue
        words += [_DESCRIPTORS.get(p) or _PHENOMENA[p] for p in parts]
        phrase = " ".join(words).removesuffix(" of").removesuffix(" with")
        phrases.append(f"{phrase} nearby" if nearby else phrase)
    return ", ".join(phrases)


def describe_clouds(clouds: list[tuple[str, int | None]]) -> str:
    """Turn [('SCT', 1300), ('BKN', 4000)] into 'scattered clouds at 1,300 ft, broken clouds at 4,000 ft'."""
    if not clouds:
        return "no cloud information"
    parts = []
    for cover, base_ft in clouds:
        words = CLOUD_COVER.get(cover, cover)
        parts.append(f"{words} at {base_ft:,} ft" if base_ft is not None else words)
    return ", ".join(parts)


def _number(value) -> float | None:
    """API numbers can be None, '' (missing), or text like '6+' ('6 or more')."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return float(value.rstrip("+"))
    return float(value)


def _to_datetime(value) -> datetime:
    """The API sends times either as Unix seconds or as ISO text ending in 'Z' (UTC)."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _parse_clouds(items: list[dict] | None) -> list[tuple[str, int | None]]:
    return [(c.get("cover", "?"), c.get("base")) for c in (items or [])]


def _wind_text(direction_deg, variable: bool, speed_kt, gust_kt) -> str:
    if speed_kt is None:
        return "not reported"
    if speed_kt == 0:
        return "calm"
    source = "variable direction" if variable else f"from {direction_deg:.0f}°"
    text = f"{source}, {speed_kt:.0f} kt ({speed_kt * KMH_PER_KNOT:.0f} km/h)"
    if gust_kt:
        text += f", gusts {gust_kt:.0f} kt ({gust_kt * KMH_PER_KNOT:.0f} km/h)"
    return text


def _visibility_text(visibility_km, at_least: bool) -> str:
    if visibility_km is None:
        return "not reported"
    return f"{visibility_km:.0f}+ km" if at_least else f"{visibility_km:.1f} km"


class MetarReport:
    """One METAR: the weather an airport observed at a given time."""

    def __init__(self, icao, name, observed_at, raw_text, flight_category, temperature_c,
                 dewpoint_c, wind_direction_deg, wind_variable, wind_speed_kt, wind_gust_kt,
                 visibility_km, visibility_at_least, pressure_hpa, weather_codes, clouds,
                 latitude, longitude):
        self.icao = icao
        self.name = name
        self.observed_at = observed_at
        self.raw_text = raw_text
        self.flight_category = flight_category
        self.temperature_c = temperature_c
        self.dewpoint_c = dewpoint_c
        self.wind_direction_deg = wind_direction_deg
        self.wind_variable = wind_variable
        self.wind_speed_kt = wind_speed_kt
        self.wind_gust_kt = wind_gust_kt
        self.visibility_km = visibility_km
        self.visibility_at_least = visibility_at_least
        self.pressure_hpa = pressure_hpa
        self.weather_codes = weather_codes
        self.clouds = clouds
        self.latitude = latitude
        self.longitude = longitude

    @property
    def category_info(self) -> dict:
        """Label, emoji and plain explanation for this report's flight category."""
        return FLIGHT_CATEGORIES.get(self.flight_category, UNKNOWN_CATEGORY)

    @property
    def ceiling_ft(self) -> int | None:
        """Lowest cloud layer covering more than half the sky (None if there isn't one)."""
        bases = [base for cover, base in self.clouds if cover in CEILING_COVERS and base is not None]
        return min(bases) if bases else None

    @property
    def wind_text(self) -> str:
        return _wind_text(self.wind_direction_deg, self.wind_variable, self.wind_speed_kt, self.wind_gust_kt)

    @property
    def visibility_text(self) -> str:
        return _visibility_text(self.visibility_km, self.visibility_at_least)

    @property
    def weather_text(self) -> str:
        return explain_weather_codes(self.weather_codes)

    @property
    def clouds_text(self) -> str:
        return describe_clouds(self.clouds)

    def __str__(self) -> str:
        return f"{self.icao} ({self.flight_category}): {self.raw_text}"

    def __repr__(self) -> str:
        return f"MetarReport({self.icao!r}, {self.flight_category!r})"

    def __lt__(self, other: object) -> bool:
        """Better conditions sort first, so sorted(reports, reverse=True) puts the worst airport first."""
        if not isinstance(other, MetarReport):
            return NotImplemented
        return self.category_info["rank"] < other.category_info["rank"]


class TafPeriod:
    """One line of a TAF forecast, e.g. 'TEMPO 18:00-21:00: visibility 3 km in mist'."""

    def __init__(self, starts_at, ends_at, change_type, probability, wind_direction_deg,
                 wind_variable, wind_speed_kt, wind_gust_kt, visibility_km, visibility_at_least,
                 weather_codes, clouds):
        self.starts_at = starts_at
        self.ends_at = ends_at
        self.change_type = change_type
        self.probability = probability
        self.wind_direction_deg = wind_direction_deg
        self.wind_variable = wind_variable
        self.wind_speed_kt = wind_speed_kt
        self.wind_gust_kt = wind_gust_kt
        self.visibility_km = visibility_km
        self.visibility_at_least = visibility_at_least
        self.weather_codes = weather_codes
        self.clouds = clouds

    @property
    def change_text(self) -> str:
        text = TAF_CHANGE_TYPES.get(self.change_type, self.change_type)
        return f"{text} ({self.probability}% chance)" if self.probability else text

    def to_row(self) -> dict:
        """One table row in plain language. Empty cells mean 'no change from the main forecast'."""
        return {
            "When (UTC)": f"{self.starts_at:%a %H:%M} - {self.ends_at:%a %H:%M}",
            "Type": self.change_text,
            "Wind": "" if self.wind_speed_kt is None else _wind_text(
                self.wind_direction_deg, self.wind_variable, self.wind_speed_kt, self.wind_gust_kt),
            "Visibility": "" if self.visibility_km is None else _visibility_text(
                self.visibility_km, self.visibility_at_least),
            "Weather": explain_weather_codes(self.weather_codes) if self.weather_codes else "",
            "Clouds": describe_clouds(self.clouds) if self.clouds else "",
        }


class TafReport:
    """One TAF: an airport's official forecast for a period of time."""

    def __init__(self, icao, name, issued_at, valid_from, valid_to, raw_text, periods):
        self.icao = icao
        self.name = name
        self.issued_at = issued_at
        self.valid_from = valid_from
        self.valid_to = valid_to
        self.raw_text = raw_text
        self.periods = periods

    @property
    def hours_covered(self) -> float:
        return (self.valid_to - self.valid_from).total_seconds() / 3600

    def __repr__(self) -> str:
        return f"TafReport({self.icao!r}, {len(self.periods)} periods, {self.hours_covered:.0f} h)"


def metar_from_api(item: dict) -> MetarReport:
    """Validate and convert one METAR from the aviationweather.gov JSON response."""
    try:
        visibility = item.get("visib")
        return MetarReport(
            icao=item["icaoId"],
            name=item.get("name") or item["icaoId"],
            observed_at=_to_datetime(item["obsTime"]),
            raw_text=item["rawOb"],
            flight_category=item.get("fltCat") or "UNKNOWN",
            temperature_c=_number(item.get("temp")),
            dewpoint_c=_number(item.get("dewp")),
            wind_direction_deg=None if item.get("wdir") == "VRB" else _number(item.get("wdir")),
            wind_variable=item.get("wdir") == "VRB",
            wind_speed_kt=_number(item.get("wspd")),
            wind_gust_kt=_number(item.get("wgst")),
            visibility_km=None if _number(visibility) is None else _number(visibility) * KM_PER_MILE,
            visibility_at_least=isinstance(visibility, str) and visibility.endswith("+"),
            pressure_hpa=_number(item.get("altim")),
            weather_codes=item.get("wxString"),
            # With no cloud layers (e.g. CAVOK or CLR) the list is empty and the code is in "cover".
            clouds=_parse_clouds(item.get("clouds")) or ([(item["cover"], None)] if item.get("cover") else []),
            latitude=float(item["lat"]),
            longitude=float(item["lon"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"The METAR for {item.get('icaoId', '?')} could not be read") from exc


def taf_from_api(item: dict) -> TafReport:
    """Validate and convert one TAF from the aviationweather.gov JSON response."""
    try:
        periods = []
        for f in item.get("fcsts", []):
            visibility = f.get("visib")
            periods.append(TafPeriod(
                starts_at=_to_datetime(f["timeFrom"]),
                ends_at=_to_datetime(f["timeTo"]),
                change_type=f.get("fcstChange"),
                probability=f.get("probability"),
                wind_direction_deg=None if f.get("wdir") == "VRB" else _number(f.get("wdir")),
                wind_variable=f.get("wdir") == "VRB",
                wind_speed_kt=_number(f.get("wspd")),
                wind_gust_kt=_number(f.get("wgst")),
                visibility_km=None if _number(visibility) is None else _number(visibility) * KM_PER_MILE,
                visibility_at_least=isinstance(visibility, str) and visibility.endswith("+"),
                weather_codes=f.get("wxString"),
                clouds=_parse_clouds(f.get("clouds")),
            ))
        return TafReport(
            icao=item["icaoId"],
            name=item.get("name") or item["icaoId"],
            issued_at=_to_datetime(item["issueTime"]),
            valid_from=_to_datetime(item["validTimeFrom"]),
            valid_to=_to_datetime(item["validTimeTo"]),
            raw_text=item["rawTAF"],
            periods=periods,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"The TAF for {item.get('icaoId', '?')} could not be read") from exc
