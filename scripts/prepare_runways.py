"""Download/keep only route airports from public-domain OurAirports runway data.

Usage (from repository root):
    uv run python scripts/prepare_runways.py LEMD EGLL EGKK
"""

import argparse
import csv
import io
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"
KEEP = (
    "airport_ident", "closed", "le_ident", "le_heading_degT", "he_ident", "he_heading_degT",
    "le_latitude_deg", "le_longitude_deg", "he_latitude_deg", "he_longitude_deg",
)
DEFAULT_AIRPORTS = ["LEMD", "EGLL", "EGKK", "LEBL", "LEPA", "LFPG", "EHAM", "EIDW", "EGSS", "EGCC"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("codes", nargs="*", default=DEFAULT_AIRPORTS, help="Airport ICAO codes")
    parser.add_argument("--out", default="data/runways.csv", help="Output CSV path")
    args = parser.parse_args()
    codes = {c.upper() for c in args.codes}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        request = Request(URL, headers={"User-Agent": "WeatherInsightsCourseProject/1.0"})
        with urlopen(request, timeout=40) as response:
            reader = csv.DictReader(io.TextIOWrapper(response, encoding="utf-8"))
            with out.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=KEEP)
                writer.writeheader()
                n = 0
                found = set()
                for row in reader:
                    airport = (row.get("airport_ident") or "").upper()
                    if airport in codes:
                        writer.writerow({key: row.get(key, "") for key in KEEP})
                        found.add(airport)
                        n += 1
        print(f"Saved {n} real runway records for {len(found)} airports to {out}")
        missing = sorted(codes - found)
        if missing:
            print(f"No runway records found for: {', '.join(missing)}")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise SystemExit(f"Could not download/save OurAirports runway data: {exc}") from exc


if __name__ == "__main__":
    main()
