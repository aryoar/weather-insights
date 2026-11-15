"""Go/No-Go practice: check a REAL METAR against a student pilot's personal limits.

A flight school gives each student "personal minimums": the worst weather they may
fly in at their stage of training. This module compares one METAR with those limits
and explains every check in plain words. The preset numbers are EXAMPLE school limits
for training practice, not regulations and not advice for a real flight.

Crosswind reuses the suitability page's maths (weather_app.airports.crosswind_kt and
choose_runway) and the runway headings in data/runways.csv.
"""

from dataclasses import dataclass, field

from .airports import RunwayEnd, choose_runway
from .reports import FLIGHT_CATEGORIES, KMH_PER_KNOT, M_PER_FOOT, MetarReport

NEAR_LIMIT_SHARE = 0.8  # within 20% of a limit counts as "close to the limit" (CAUTION)
VERDICTS = ("GO", "CAUTION", "NO-GO")


@dataclass(frozen=True)
class PilotLimits:
    """Personal weather minimums for one pilot. Frozen, so a preset can never be changed by accident."""

    max_crosswind_kt: float
    min_visibility_km: float
    min_ceiling_ft: float
    max_gust_spread_kt: float
    vfr_required: bool = True
    name: str = "Custom limits"

    def __post_init__(self) -> None:
        if self.max_crosswind_kt <= 0:
            raise ValueError("The crosswind limit must be above 0 kt.")
        if self.min_visibility_km <= 0:
            raise ValueError("The visibility minimum must be above 0 km.")
        if self.min_ceiling_ft < 0 or self.max_gust_spread_kt < 0:
            raise ValueError("Ceiling and gust limits cannot be negative.")

    @property
    def summary(self) -> str:
        """One line for the page, metric next to aviation units."""
        return (
            f"crosswind ≤ {self.max_crosswind_kt:.0f} kt ({self.max_crosswind_kt * KMH_PER_KNOT:.0f} km/h) · "
            f"visibility ≥ {self.min_visibility_km:g} km · ceiling ≥ {self.min_ceiling_ft:,.0f} ft "
            f"({self.min_ceiling_ft * M_PER_FOOT:,.0f} m) · gust spread ≤ {self.max_gust_spread_kt:.0f} kt"
            + (" · VFR only" if self.vfr_required else "")
        )


STUDENT_LIMITS = PilotLimits(
    max_crosswind_kt=10, min_visibility_km=5, min_ceiling_ft=1500, max_gust_spread_kt=10,
    vfr_required=True, name="Student pilot (example school limits)",
)


@dataclass(frozen=True)
class Check:
    """One line of the Go/No-Go table. passed=None means the data could not settle it."""

    name: str
    value: str
    limit: str
    passed: bool | None
    explanation: str
    near_limit: bool = False

    @property
    def status(self) -> str:
        if self.passed is None:
            return "Unknown"
        if not self.passed:
            return "Fail"
        return "Pass (close to limit)" if self.near_limit else "Pass"


@dataclass(frozen=True)
class Decision:
    """All checks for one airport, and the verdict they add up to."""

    airport: str
    checks: tuple[Check, ...]
    limits: PilotLimits
    runway: str | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def failed_checks(self) -> list[Check]:
        return [check for check in self.checks if check.passed is False]

    @property
    def verdict(self) -> str:
        """NO-GO if any limit is broken; CAUTION if a check is unknown or close to its limit; else GO."""
        if self.failed_checks:
            return "NO-GO"
        if any(check.passed is None or check.near_limit for check in self.checks):
            return "CAUTION"
        return "GO"

    @property
    def reasons(self) -> list[str]:
        """The sentences that explain the verdict, most important first."""
        if self.failed_checks:
            return [check.explanation for check in self.failed_checks]
        doubtful = [check.explanation for check in self.checks if check.passed is None or check.near_limit]
        return doubtful or ["Every check is inside the limits with a comfortable margin."]

    def __str__(self) -> str:
        return f"{self.airport}: {self.verdict} ({len(self.failed_checks)} limit(s) broken)"


# ---------------------------------------------------------------- the checks ----

def _category_check(report: MetarReport) -> Check:
    category = report.flight_category
    if category not in FLIGHT_CATEGORIES:
        return Check("Flight category", "not reported", "VFR", None,
                     "The report has no flight category, so 'VFR only' cannot be confirmed.")
    passed = category == "VFR"
    explanation = (f"Flight category is {category}: {FLIGHT_CATEGORIES[category]['explanation']}"
                   + ("" if passed else " Student pilots in this example may only fly in VFR."))
    return Check("Flight category", category, "VFR", passed, explanation)


def _visibility_check(report: MetarReport, limits: PilotLimits) -> Check:
    limit = f"≥ {limits.min_visibility_km:g} km"
    if report.visibility_km is None:
        return Check("Visibility", "not reported", limit, None, "Visibility is missing from the report.")
    passed = report.visibility_km >= limits.min_visibility_km
    near = passed and not report.visibility_at_least and report.visibility_km < limits.min_visibility_km / NEAR_LIMIT_SHARE
    if not passed:
        explanation = f"Visibility {report.visibility_text} is below your minimum of {limits.min_visibility_km:g} km."
    elif near:
        explanation = f"Visibility {report.visibility_text} is only just above your minimum of {limits.min_visibility_km:g} km."
    else:
        explanation = f"Visibility {report.visibility_text} is well above your minimum."
    return Check("Visibility", report.visibility_text, limit, passed, explanation, near)


def _ceiling_check(report: MetarReport, limits: PilotLimits) -> Check:
    limit = f"≥ {limits.min_ceiling_ft:,.0f} ft"
    ceiling = report.ceiling_ft
    if ceiling is None:
        return Check("Ceiling", "no ceiling", limit, True,
                     "There is no broken or overcast layer, so no ceiling limits you.")
    passed = ceiling >= limits.min_ceiling_ft
    near = passed and ceiling < limits.min_ceiling_ft / NEAR_LIMIT_SHARE
    value = f"{ceiling:,} ft ({ceiling * M_PER_FOOT:,.0f} m)"
    if not passed:
        explanation = f"The ceiling at {value} is below your minimum of {limits.min_ceiling_ft:,.0f} ft."
    elif near:
        explanation = f"The ceiling at {value} is only just above your minimum of {limits.min_ceiling_ft:,.0f} ft."
    else:
        explanation = f"The ceiling at {value} is well above your minimum."
    return Check("Ceiling", value, limit, passed, explanation, near)


def _gust_check(report: MetarReport, limits: PilotLimits) -> Check:
    limit = f"≤ {limits.max_gust_spread_kt:.0f} kt"
    if report.wind_speed_kt is None:
        return Check("Gust spread", "not reported", limit, None, "Wind is missing from the report.")
    if not report.wind_gust_kt:
        return Check("Gust spread", "no gusts", limit, True, "No gusts are reported.")
    spread = report.wind_gust_kt - report.wind_speed_kt
    passed = spread <= limits.max_gust_spread_kt
    near = passed and spread > limits.max_gust_spread_kt * NEAR_LIMIT_SHARE
    explanation = (f"Gusts reach {report.wind_gust_kt:.0f} kt over a {report.wind_speed_kt:.0f} kt wind: "
                   f"a spread of {spread:.0f} kt" + (" (too gusty for your limits)." if not passed else "."))
    return Check("Gust spread", f"{spread:.0f} kt", limit, passed, explanation, near)


def _crosswind_check(report: MetarReport, runways: list[RunwayEnd], limits: PilotLimits) -> tuple[Check, str | None]:
    limit = f"≤ {limits.max_crosswind_kt:.0f} kt"
    if report.wind_speed_kt is None:
        return Check("Crosswind", "not reported", limit, None, "Wind is missing from the report."), None
    # Use the gust when there is one: the strongest wind is the one that pushes you off the centreline.
    wind = report.wind_gust_kt or report.wind_speed_kt
    basis = "gust" if report.wind_gust_kt else "wind"
    if wind == 0:
        return Check("Crosswind", "0 kt (calm)", limit, True, "The wind is calm."), None

    direction_known = not report.wind_variable and report.wind_direction_deg is not None
    if direction_known and runways:
        runway, crosswind = choose_runway(report.wind_direction_deg, wind, runways)
        passed = crosswind <= limits.max_crosswind_kt
        near = passed and crosswind > limits.max_crosswind_kt * NEAR_LIMIT_SHARE
        explanation = (f"On runway {runway.name}, the best one for this wind, the crosswind from the "
                       f"{wind:.0f} kt {basis} is {crosswind:.0f} kt ({crosswind * KMH_PER_KNOT:.0f} km/h)"
                       + (f", above your limit of {limits.max_crosswind_kt:.0f} kt." if not passed else "."))
        return Check("Crosswind", f"{crosswind:.0f} kt (runway {runway.name})", limit, passed, explanation, near), runway.name

    # Without a known direction or runway headings, assume the worst case: wind straight across.
    why = "the wind direction is variable" if not direction_known else f"there is no runway data for {report.icao}"
    if wind <= limits.max_crosswind_kt:
        return Check("Crosswind", f"≤ {wind:.0f} kt (worst case)", limit, True,
                     f"Because {why}, we assume the whole {wind:.0f} kt {basis} blows straight across "
                     "the runway. Even then it is inside your limit.",
                     wind > limits.max_crosswind_kt * NEAR_LIMIT_SHARE), None
    return Check("Crosswind", f"up to {wind:.0f} kt", limit, None,
                 f"Because {why}, the crosswind cannot be worked out: it could be anything up to "
                 f"{wind:.0f} kt, above your {limits.max_crosswind_kt:.0f} kt limit. Ask your instructor."), None


def evaluate_go_no_go(report: MetarReport, runways: list[RunwayEnd], limits: PilotLimits) -> Decision:
    """Compare one METAR with a pilot's limits. `runways` are that airport's runway ends (may be empty)."""
    crosswind, runway = _crosswind_check(report, runways, limits)
    checks = [crosswind, _visibility_check(report, limits), _ceiling_check(report, limits),
              _gust_check(report, limits)]
    if limits.vfr_required:
        checks.insert(0, _category_check(report))
    return Decision(report.icao, tuple(checks), limits, runway)


def grade_choice(choice: str, decision: Decision) -> tuple[bool, str]:
    """Was the student's GO / NO-GO right? Returns (counts as correct, explanation).

    For a CAUTION verdict both answers count: it is a judgement call, and the
    explanation says what a careful student pilot would weigh up.
    """
    if choice not in ("GO", "NO-GO"):
        raise ValueError("Choose GO or NO-GO.")
    verdict = decision.verdict
    if verdict == "CAUTION":
        lean = ("NO-GO is the safer call for a student" if choice == "NO-GO"
                else "GO is defensible, but only with your instructor's agreement")
        return True, f"Borderline day: {lean}. " + " ".join(decision.reasons)
    if choice == verdict:
        return True, f"Correct, this is a {verdict}. " + " ".join(decision.reasons)
    if verdict == "NO-GO":
        return False, "This is a NO-GO: " + " ".join(decision.reasons)
    return False, ("This is a GO: every check is inside your limits. Being cautious is good, but "
                   "turning down a flight that is within limits also costs training time.")


# ---------------------------------------------------------------- instructor scenarios ----

def flight_category_for(visibility_km: float | None, ceiling_ft: float | None) -> str:
    """FAA flight category from visibility and ceiling (the same rules aviationweather.gov uses)."""
    if visibility_km is None:
        return "UNKNOWN"
    visibility_sm = visibility_km / 1.609344
    ceiling = float("inf") if ceiling_ft is None else ceiling_ft
    if ceiling < 500 or visibility_sm < 1:
        return "LIFR"
    if ceiling < 1000 or visibility_sm < 3:
        return "IFR"
    if ceiling <= 3000 or visibility_sm <= 5:
        return "MVFR"
    return "VFR"


def apply_scenario(report: MetarReport, *, wind_direction_deg: float | None = None,
                   wind_speed_kt: float | None = None, wind_gust_kt: float | None = None,
                   visibility_km: float | None = None, ceiling_ft: int | None = None,
                   clear_ceiling: bool = False) -> MetarReport:
    """A copy of a real report with instructor-chosen values (a SCENARIO, never saved).

    Values left as None keep the real report's value. The flight category is worked
    out again from the (possibly changed) visibility and ceiling.
    """
    if wind_speed_kt is not None and wind_speed_kt < 0:
        raise ValueError("Wind speed cannot be negative.")
    if visibility_km is not None and visibility_km <= 0:
        raise ValueError("Visibility must be above 0 km.")
    if ceiling_ft is not None and ceiling_ft < 0:
        raise ValueError("The ceiling cannot be negative.")
    speed = report.wind_speed_kt if wind_speed_kt is None else wind_speed_kt
    gust = report.wind_gust_kt if wind_gust_kt is None else (wind_gust_kt or None)
    if gust is not None and speed is not None and gust <= speed:
        gust = None  # a "gust" no stronger than the wind is not a gust
    direction = report.wind_direction_deg if wind_direction_deg is None else wind_direction_deg % 360
    variable = report.wind_variable and wind_direction_deg is None

    if clear_ceiling:
        clouds = [(cover, base) for cover, base in report.clouds if cover not in ("BKN", "OVC", "OVX", "VV")]
    elif ceiling_ft is not None:
        below = [(cover, base) for cover, base in report.clouds
                 if cover in ("FEW", "SCT") and base is not None and base < ceiling_ft]
        clouds = below + [("BKN", int(ceiling_ft))]
    else:
        clouds = list(report.clouds)
    visibility = report.visibility_km if visibility_km is None else visibility_km
    at_least = report.visibility_at_least if visibility_km is None else False

    scenario = MetarReport(
        icao=report.icao, name=report.name, observed_at=report.observed_at, raw_text=report.raw_text,
        flight_category="UNKNOWN", temperature_c=report.temperature_c, dewpoint_c=report.dewpoint_c,
        wind_direction_deg=direction, wind_variable=variable, wind_speed_kt=speed, wind_gust_kt=gust,
        visibility_km=visibility, visibility_at_least=at_least, pressure_hpa=report.pressure_hpa,
        weather_codes=report.weather_codes, clouds=clouds,
        latitude=report.latitude, longitude=report.longitude,
    )
    scenario.flight_category = flight_category_for(visibility, scenario.ceiling_ft)
    return scenario
