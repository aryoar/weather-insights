"""One-page flight briefing: the flight, real METARs for its three airports, and the go/no-go.

BriefingSheet only arranges data that other modules already produced (MetarReport,
Decision, the great-circle distance) into a short text a student can download and
take to their instructor. No Streamlit code here: the page is views/briefing_sheet.py.
"""

from datetime import datetime, timezone

from .decision import Decision
from .reports import M_PER_FOOT, MetarReport
from .route import KM_PER_NM

ROLES = ("departure", "destination", "alternate")
NOTICE = "Training aid only: not for real flight planning."


class BriefingSheet:
    """A short, printable summary of one training flight."""

    def __init__(self, flight: dict[str, str], reports: dict[str, MetarReport], decision: Decision | None,
                 distance_nm: float | None, created_at: datetime | None = None) -> None:
        missing = [role for role in ROLES if role not in flight]
        if missing:
            raise ValueError(f"The flight is missing: {', '.join(missing)}.")
        if distance_nm is not None and distance_nm <= 0:
            raise ValueError("The distance must be above 0 nm.")
        self._flight = dict(flight)
        self._reports = dict(reports)
        self._decision = decision
        self._distance_nm = distance_nm
        self._created_at = created_at or datetime.now(timezone.utc)

    @property
    def title(self) -> str:
        return f"Training briefing {self._flight['departure']} → {self._flight['destination']}"

    @property
    def missing_airports(self) -> list[str]:
        """Airports of the flight without a METAR (shown as 'no report', never guessed)."""
        return [self._flight[role] for role in ROLES if self._flight[role] not in self._reports]

    @property
    def verdict(self) -> str | None:
        return None if self._decision is None else self._decision.verdict

    @property
    def file_name(self) -> str:
        return f"briefing_{self._flight['departure']}_{self._flight['destination']}_{self._created_at:%Y%m%d_%H%MZ}.md"

    def airport_rows(self) -> list[dict[str, str]]:
        """One row per airport, in departure, destination, alternate order."""
        rows = []
        for role in ROLES:
            code = self._flight[role]
            report = self._reports.get(code)
            if report is None:
                rows.append({"Role": role.title(), "Airport": code, "Category": "no report", "Wind": "",
                             "Visibility": "", "Ceiling": "", "Observed (UTC)": ""})
                continue
            ceiling = report.ceiling_ft
            rows.append({
                "Role": role.title(), "Airport": f"{code} {report.name}", "Category": report.flight_category,
                "Wind": report.wind_text, "Visibility": report.visibility_text,
                "Ceiling": "none" if ceiling is None else f"{ceiling:,} ft ({ceiling * M_PER_FOOT:,.0f} m)",
                "Observed (UTC)": f"{report.observed_at:%d %b %H:%M}",
            })
        return rows

    def to_markdown(self) -> str:
        """The sheet as Markdown text (opens in any editor, prints on one page)."""
        lines = [f"# {self.title}", "", f"_{NOTICE}_", "",
                 f"Prepared {self._created_at:%d %b %Y %H:%M} UTC · alternate {self._flight['alternate']}"]
        if self._distance_nm is not None:
            lines.append(f"Distance: {self._distance_nm:,.0f} nm ({self._distance_nm * KM_PER_NM:,.0f} km)")
        lines += ["", "## Weather at the airports", "",
                  "| Role | Airport | Category | Wind | Visibility | Ceiling | Observed (UTC) |",
                  "|---|---|---|---|---|---|---|"]
        lines += ["| " + " | ".join(row.values()) + " |" for row in self.airport_rows()]
        lines += ["", "## Raw METARs", ""]
        for role in ROLES:
            report = self._reports.get(self._flight[role])
            lines.append(f"    {report.raw_text}" if report else f"    {self._flight[role]}: no report available")
        lines += ["", "## Go / No-Go at departure (example student limits)", ""]
        if self._decision is None:
            lines.append("Not available: no METAR for the departure airport.")
        else:
            lines.append(f"**Verdict: {self._decision.verdict}** ({self._decision.limits.summary})")
            lines.append("")
            lines += [f"- {check.name}: {check.value} (limit {check.limit}) → {check.status}"
                      for check in self._decision.checks]
            lines += ["", *[f"> {reason}" for reason in self._decision.reasons]]
        lines += ["", "## Instructor sign-off", "", "Student: ____________  Instructor: ____________",
                  "", f"_{NOTICE}_", ""]
        return "\n".join(lines)

    def __str__(self) -> str:
        return f"{self.title} ({self.verdict or 'no verdict'})"

    def __repr__(self) -> str:
        return f"BriefingSheet({self._flight!r}, {len(self._reports)} reports)"

