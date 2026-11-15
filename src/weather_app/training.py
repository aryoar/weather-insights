"""METAR trainer: multiple-choice questions built from one REAL METAR.

Each question asks the student to decode one part of the report (wind, visibility,
ceiling, flight category, temperature/dew point or QNH). The correct answer comes
from the MetarReport fields; the wrong answers ("distractors") are the mistakes
student pilots really make, such as reading the lowest cloud as the ceiling or the
wind direction as where the wind blows TO. No Streamlit code here: the page lives
in views/metar_trainer.py.
"""

import random
import re

from .glossary import GLOSSARY
from .reports import FLIGHT_CATEGORIES, KMH_PER_KNOT, M_PER_FOOT, MetarReport

# The airports the trainer draws real METARs from (EASA region, busy enough to report often).
TRAINER_AIRPORTS: dict[str, str] = {
    "LEMD": "Madrid-Barajas",
    "LEBL": "Barcelona-El Prat",
    "LEPA": "Palma de Mallorca",
    "EGLL": "London Heathrow",
    "LFPG": "Paris Charles de Gaulle",
    "EDDF": "Frankfurt",
    "LIRF": "Rome Fiumicino",
    "EHAM": "Amsterdam Schiphol",
}
QUESTIONS_PER_REPORT = 5
OPTIONS_PER_QUESTION = 4

VISIBILITY_BANDS = ["Under 1.5 km", "1.5 km to under 5 km", "5 km to under 10 km", "10 km or more"]
NO_CEILING = "No ceiling (no BKN or OVC layer)"

# Coded groups inside the raw METAR, so feedback can point at the exact characters.
_WIND_GROUP = re.compile(r"\b(?:\d{3}|VRB)\d{2,3}(?:G\d{2,3})?(?:KT|MPS)\b")
_VISIBILITY_GROUP = re.compile(r"\b(CAVOK|\d{4})\b")
_CLOUD_GROUP = re.compile(r"\b(?:FEW|SCT|BKN|OVC|VV)\d{3}\b|\b(?:NSC|NCD|SKC|CLR|CAVOK)\b")
_TEMPERATURE_GROUP = re.compile(r"\bM?\d{2}/M?\d{2}\b")
_PRESSURE_GROUP = re.compile(r"\b[QA]\d{4}\b")


class MetarQuestion:
    """One multiple-choice question about a METAR, with the explanation shown after answering."""

    def __init__(self, topic: str, prompt: str, options: list[str], correct: str,
                 explanation: str, code_group: str | None = None) -> None:
        if len(options) < 2:
            raise ValueError("A question needs at least two options.")
        if len(set(options)) != len(options):
            raise ValueError("Options must be different from each other.")
        if correct not in options:
            raise ValueError("The correct answer must be one of the options.")
        self._topic = topic
        self._prompt = prompt
        self._options = tuple(options)
        self._correct = correct
        self._explanation = explanation
        self._code_group = code_group

    @property
    def topic(self) -> str:
        """Short name of what is being tested, e.g. 'Wind'."""
        return self._topic

    @property
    def prompt(self) -> str:
        return self._prompt

    @property
    def options(self) -> tuple[str, ...]:
        """The answers to choose from (a tuple, so the order cannot change by accident)."""
        return self._options

    @property
    def correct(self) -> str:
        return self._correct

    @property
    def explanation(self) -> str:
        """Plain-language reason why the correct answer is correct."""
        return self._explanation

    @property
    def code_group(self) -> str | None:
        """The part of the raw METAR this question is about, e.g. '28008KT' (None if not found)."""
        return self._code_group

    def is_correct(self, answer: str | None) -> bool:
        return answer == self._correct

    def __str__(self) -> str:
        return f"[{self._topic}] {self._prompt} -> {self._correct}"

    def __repr__(self) -> str:
        return f"MetarQuestion({self._topic!r}, {len(self._options)} options)"


class Scoreboard:
    """Running score for one student session (kept in st.session_state by the pages)."""

    def __init__(self) -> None:
        self._answered = 0
        self._correct = 0

    def record(self, correct: bool) -> None:
        self._answered += 1
        self._correct += int(correct)

    @property
    def answered(self) -> int:
        return self._answered

    @property
    def correct(self) -> int:
        return self._correct

    @property
    def accuracy_pct(self) -> float | None:
        """Share of correct answers in percent (None before the first answer)."""
        return None if self._answered == 0 else 100 * self._correct / self._answered

    def __str__(self) -> str:
        return f"{self._correct}/{self._answered} correct"


# ---------------------------------------------------------------- formatting ----

def _kt(speed_kt: float) -> str:
    return f"{speed_kt:.0f} kt ({speed_kt * KMH_PER_KNOT:.0f} km/h)"


def _ft(height_ft: float) -> str:
    """Feet with metres next to them (EASA students learn both)."""
    return f"{height_ft:,.0f} ft ({round(height_ft * M_PER_FOOT / 10) * 10:,.0f} m)"


def _wind_answer(direction_deg: float | None, variable: bool, speed_kt: float, gust_kt: float | None) -> str:
    if speed_kt == 0:
        return "Calm (no wind)"
    source = "Variable direction" if variable or direction_deg is None else f"From {direction_deg % 360:03.0f}°"
    text = f"{source} at {_kt(speed_kt)}"
    return f"{text}, gusting {gust_kt:.0f} kt" if gust_kt else text


def _visibility_band(visibility_km: float, at_least: bool) -> str:
    # 9999 ("10 km or more") arrives from the API as 6+ statute miles = 9.66 km, hence 9.5.
    if at_least or visibility_km >= 9.5:
        return VISIBILITY_BANDS[3]
    if visibility_km >= 5:
        return VISIBILITY_BANDS[2]
    if visibility_km >= 1.5:
        return VISIBILITY_BANDS[1]
    return VISIBILITY_BANDS[0]


def _find(pattern: re.Pattern, raw_text: str, start: int = 0) -> re.Match | None:
    return pattern.search(raw_text, start)


def _options(correct: str, distractors: list[str], padding: list[str], rng: random.Random,
             shuffle: bool = True) -> list[str]:
    """Correct answer + up to 3 different distractors (padded if needed), shuffled with rng."""
    chosen = [correct]
    for candidate in distractors + padding:
        if candidate not in chosen:
            chosen.append(candidate)
        if len(chosen) == OPTIONS_PER_QUESTION:
            break
    if shuffle:
        rng.shuffle(chosen)
    return chosen


# ---------------------------------------------------------------- questions ----

def _wind_question(report: MetarReport, rng: random.Random) -> MetarQuestion | None:
    speed, gust = report.wind_speed_kt, report.wind_gust_kt
    if speed is None:
        return None
    direction = report.wind_direction_deg
    variable = report.wind_variable or direction is None
    correct = _wind_answer(direction, report.wind_variable, speed, gust)

    if speed == 0:
        distractors = ["From 000° at 10 kt (19 km/h)", "Variable direction at 3 kt (6 km/h)",
                       "From 360° at 5 kt (9 km/h)"]
    elif variable:
        distractors = [
            _wind_answer(rng.choice([10, 90, 180, 270]), False, speed, gust),
            "Calm (no wind)",
            _wind_answer(None, True, speed + 10, gust),
        ]
    else:
        distractors = [
            _wind_answer(direction + 180, False, speed, gust),  # "towards" instead of "from"
            _wind_answer(direction + rng.choice([-40, 40]), False, speed + 10, gust),
            _wind_answer(direction, False, gust, None) if gust else _wind_answer(direction, False, speed + 10, None),
        ]
    padding = [_wind_answer(d, False, s, None) for d, s in ((90, 12), (200, 6), (310, 15))]

    group = _find(_WIND_GROUP, report.raw_text)
    code = group.group(0) if group else None
    explanation = (
        f"{'The group ' + code + ' means' if code else 'The report gives'} wind {report.wind_text}. "
        "The first three digits are the direction the wind blows FROM (degrees true), the next two "
        "the speed in knots. 'G' adds the gust speed, 'VRB' means the direction keeps changing, and "
        f"00000KT is calm. {GLOSSARY['Knots (kt)']}"
    )
    return MetarQuestion("Wind", "What is the surface wind?",
                         _options(correct, distractors, padding, rng), correct, explanation, code)


def _visibility_question(report: MetarReport, rng: random.Random) -> MetarQuestion | None:
    if report.visibility_km is None:
        return None
    correct = _visibility_band(report.visibility_km, report.visibility_at_least)
    wind = _find(_WIND_GROUP, report.raw_text)
    group = _find(_VISIBILITY_GROUP, report.raw_text, wind.end() if wind else 0)
    code = group.group(1) if group else None
    explanation = (
        f"Reported visibility: {report.visibility_text}. In a European METAR visibility is in metres: "
        "9999 means 10 km or more, 6000 means 6 km, 0800 means 800 m. CAVOK means visibility 10 km "
        f"or more with no cloud below 5,000 ft. {GLOSSARY['Visibility']}"
    )
    return MetarQuestion("Visibility", "What is the prevailing visibility?",
                         list(VISIBILITY_BANDS), correct, explanation, code)


def _ceiling_question(report: MetarReport, rng: random.Random) -> MetarQuestion | None:
    if not report.clouds:
        return None
    ceiling = report.ceiling_ft
    bases = sorted({base for _, base in report.clouds if base is not None})
    other_layers = [base for base in bases if base != ceiling]

    distractors: list[float] = list(other_layers)            # lowest cloud ≠ ceiling: the classic trap
    if ceiling is not None:
        distractors.append(ceiling * 10)                      # "BKN008" read as 8,000 ft
    heights = list(dict.fromkeys(distractors + [500, 1000, 1500, 3000, 5000]))
    choices = [h for h in heights if h != ceiling]
    correct = NO_CEILING if ceiling is None else _ft(ceiling)

    picked = [correct]
    if ceiling is not None:
        picked.append(NO_CEILING)
    for height in choices:
        if len(picked) == OPTIONS_PER_QUESTION:
            break
        picked.append(_ft(height))
    # Lowest height first, "no ceiling" last: easier to read than a random order.
    picked.sort(key=lambda text: float("inf") if text == NO_CEILING else float(text.split(" ft")[0].replace(",", "")))

    codes = [match.group(0) for match in _CLOUD_GROUP.finditer(report.raw_text.split(" TEMPO")[0].split(" BECMG")[0])]
    code = " ".join(codes) if codes else None
    if ceiling is None:
        detail = ("None of the layers is BKN (broken) or OVC (overcast), so there is no ceiling"
                  + (f", even though there are clouds at {_ft(bases[0])}." if bases else "."))
    else:
        detail = f"The lowest BKN or OVC layer is at {_ft(ceiling)}, so that is the ceiling."
    explanation = (
        f"Clouds: {report.clouds_text}. {detail} Cloud heights are in hundreds of feet: "
        f"BKN008 = broken cloud at 800 ft. {GLOSSARY['Ceiling']}"
    )
    return MetarQuestion("Ceiling", "What is the cloud ceiling?", picked, correct, explanation, code)


def _category_question(report: MetarReport, rng: random.Random) -> MetarQuestion | None:
    category = report.flight_category
    if category not in FLIGHT_CATEGORIES:
        return None
    ceiling = "no ceiling" if report.ceiling_ft is None else f"ceiling {_ft(report.ceiling_ft)}"
    explanation = (
        f"{category}: {FLIGHT_CATEGORIES[category]['explanation']} This report has {ceiling} and "
        f"visibility {report.visibility_text}; the worse of the two decides the category. "
        "Categories follow the US (FAA) definition used by aviationweather.gov."
    )
    return MetarQuestion("Flight category", "Which flight category does this METAR give?",
                         list(FLIGHT_CATEGORIES), category, explanation)


def _temperature_question(report: MetarReport, rng: random.Random) -> MetarQuestion | None:
    temp, dew = report.temperature_c, report.dewpoint_c
    if temp is None or dew is None:
        return None

    def answer(t: float, d: float) -> str:
        return f"Temperature {t:.0f} °C, dew point {d:.0f} °C"

    correct = answer(temp, dew)
    distractors = [answer(dew, temp), answer(-temp, -dew), answer(temp, dew - 5), answer(temp + 10, dew + 10)]
    padding = [answer(temp + 3, dew), answer(temp - 3, dew - 3)]
    group = _find(_TEMPERATURE_GROUP, report.raw_text)
    spread = temp - dew
    explanation = (
        f"{'In ' + group.group(0) + ' the' if group else 'The'} number before the slash is the air "
        "temperature and the one after it the dew point, both in °C; 'M' means minus. "
        f"The spread here is {spread:.0f} °C. With a spread of 3 °C or less the air is close to "
        "saturated, so mist, fog or low cloud are likely."
    )
    return MetarQuestion("Temperature / dew point", "What are the temperature and the dew point?",
                         _options(correct, distractors, padding, rng), correct, explanation,
                         group.group(0) if group else None)


def _pressure_question(report: MetarReport, rng: random.Random) -> MetarQuestion | None:
    qnh = report.pressure_hpa
    if qnh is None:
        return None
    correct = f"{qnh:.0f} hPa"
    distractors = [f"{qnh + 10:.0f} hPa", f"{qnh - 10:.0f} hPa", f"{qnh + rng.choice([-3, 3]):.0f} hPa"]
    group = _find(_PRESSURE_GROUP, report.raw_text)
    explanation = (
        f"{'In ' + group.group(0) + ', ' if group else ''}Q followed by four digits is the QNH in "
        f"hectopascals, so Q0996 = 996 hPa. Setting the wrong QNH puts the altimeter off by about "
        f"30 ft per hPa. {GLOSSARY['QNH (pressure)']}"
    )
    return MetarQuestion("QNH", "What QNH should you set on the altimeter?",
                         _options(correct, distractors, [], rng), correct, explanation,
                         group.group(0) if group else None)


_BUILDERS = [_wind_question, _visibility_question, _ceiling_question,
             _category_question, _temperature_question, _pressure_question]


def build_questions(report: MetarReport, rng: random.Random,
                    count: int = QUESTIONS_PER_REPORT) -> list[MetarQuestion]:
    """Up to `count` questions about one METAR, in a fixed topic order.

    Pass a seeded random.Random so the same report and seed always give the same
    questions and option order (tests and page reruns rely on this).
    """
    if count < 1:
        raise ValueError("Ask at least one question.")
    available = [question for builder in _BUILDERS if (question := builder(report, rng)) is not None]
    if len(available) <= count:
        return available
    keep = sorted(rng.sample(range(len(available)), count))
    return [available[i] for i in keep]
