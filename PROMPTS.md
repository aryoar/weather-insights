# AI collaboration log

Add one entry per feature/class you asked an AI agent to help with, in the order you worked on them.
Keep this running as you go — don't reconstruct it from memory at the end.

## Feature: Project implementation from the capstone brief

**Asked:** "Learn from these to do the project" with the group capstone README and summary supplied as context.

**Got:** Implemented API client and weather model in `src/weather_app/client.py` and `models.py`; CSV history in `storage.py`; trend, comparison, and comfort ranking in `analytics.py`; Streamlit views in `app.py`; setup documentation and secret ignores.

**Checked:** `python -m compileall -q app.py src/weather_app`, `git diff --check`, and built and inspected a wheel with `python -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/weather-insights-wheel .`. No API key was available, so live requests and a real history file have not been produced. No automated tests have been run.

**Kept as-is / changed / rejected:** Kept the starter `src/` package layout and completed its stub modules. Used a local CSV so only successful API fetches become history; left the history empty until the group runs the app with its own key.

---

## Feature: aviation app skeleton and airport weather page (METAR/TAF)

**Asked (Claude Code, Opus 5.5):** "I want to start with the sort of skeleton and base and also start writing some code for the final product, and then they can build on it." Context: the aviation weather briefing plan (airport weather, route overview, winds aloft, airport suitability, fuel planner).

**Got:**
- `client.py`: `APIClient` no longer mentions OpenWeatherMap. Each subclass sets `provider_name`, so error messages name the real provider. The API key is now `__private` (`self.__api_key`): only `_get` adds it to the request (via the subclass's `_key_param`), and `__repr__` shows it as hidden. Added handling for 429 (too many requests) and 204 (no content). `WeatherClient.current` turns "not found" into a message naming the city. New subclass `AviationWeatherClient` with `metars()` and `tafs()`. One request covers all airports, and invalid, unknown or unreadable codes are skipped with a message instead of stopping the rest.
- `reports.py` (new): `MetarReport`, `TafReport` and `TafPeriod` classes, written as plain classes in the s13 style. Properties for ceiling, wind, visibility, weather and clouds in plain language. `MetarReport.__lt__` ranks airports by flight category, so `sorted(reports, reverse=True)` puts the worst first. `clean_icao_code()` validates input before any API call, and `explain_weather_codes()` translates codes like `-SHRA` into "light showers of rain".
- `glossary.py` (new): aviation terms for tooltips.
- `views/` (new): one file per page. `airport_weather.py` is a working page: departure, destination and alternate codes, flight category, wind, visibility, ceiling, temperature, raw METAR, TAF table, glossary. The other four pages are placeholders whose docstrings give the plan, the free data source and a first small step for whoever takes them. `views/common.py` has a glossary expander, a SCENARIO banner for simulated inputs, and an "observed X min ago" helper.
- `app.py`: new title and sidebar entries for the new pages (only those lines changed).

**Checked:** looked at real aviationweather.gov JSON first (unknown code → status 204; visibility can be a number, "6+", "10+" or empty; wind direction can be "VRB"; CAVOK has no cloud list). Check script: weather codes translate as expected, bad codes (`""`, `MAD`, `12AB`, `LEMDX`) are refused, the key is hidden in `repr` and `owm.__api_key` raises `AttributeError`. Live OpenWeatherMap still works (good city, unknown city, wrong key each give their own message). Live METAR/TAF for LEMD, EGLL and LFPG parse; ZZZZ and duplicates are handled. Ran every page with Streamlit's `AppTest`: no exceptions. Submitting the form shows the 3 airports, the worst-first summary and the TAF tables. "MAD" shows a validation error, and "ZZZZ" shows a warning while the others still load. That test found a real bug (the form and the session-state value had the same name), which was fixed. Found that CAVOK showed "no cloud information" and fixed it.

**Kept as-is / changed / rejected:** Kept as-is after reviewing the diff and trying the Airport weather page.


## Feature: future-proof weather log (CSV) before collecting data

**Asked (Claude Code, Opus 5.5):** After planning an aviation weather briefing app, "let's continue building on it". The agent proposed fixing the log format first, because OpenWeatherMap's free tier only returns current conditions and any field we don't save now can't be recovered later.

**Got:**
- `models.py`: `LocationSnapshot` now also stores latitude, longitude, pressure, wind direction, wind gust, visibility and cloud cover. Gust, direction, visibility and clouds are optional because OpenWeatherMap leaves them out of some responses. Coordinates and cloud cover are range-checked.
- `storage.py`: the log is always saved to `<project>/data/weather_history.csv`, whichever folder the app is started from (`DEFAULT_PATH`). Appending to a file with an older column layout now raises a clear `ValueError` instead of silently mixing formats.
- `app.py`: shows that storage error to the user.

**Checked:** ran a check script with hand-made responses (a complete one, and one with no gust, visibility or clouds). Both saved and loaded back correctly, with missing values as empty cells. An old-format file was refused with the message. An incomplete response raised "incomplete weather response". One live fetch for Madrid parsed correctly, and the real response had no gust field. Converted the one real row already in `data/weather_history.csv` to the new columns, leaving the new fields empty (not invented). Analytics functions and `app.py` still run.

**Kept as-is** _(Kept as-is after reviewing the diff)_

---

## Feature: Twice-daily weather and METAR collection script

**Asked:** "Do the logging script with argparse and a `__main__` guard. Each run logs OpenWeatherMap for a fixed list of cities and METARs for fixed airports. Run it at least twice a day until submission, and commit the logs."

**Got:** Added `scripts/log_weather.py` for Madrid, London, Paris and LEMD, EGLL, LFPG, plus `MetarStore` in `src/weather_app/storage.py` to append timestamped METAR records to a separate CSV. Documented the collection command in `README.md`.

**Checked:** `python scripts/log_weather.py --help` and syntax compilation succeeded. A live run on 2026-11-10 appended 3 OpenWeatherMap rows and 3 METAR rows; the weather log contains 11 rows across 3 observation dates, and the new METAR log contains 3 real airport reports. Existing weather rows and schema were preserved; `MetarStore` stores both collection time and METAR observation time.

**Kept as-is.**

## Feature: Save METAR reports fetched from the Streamlit page

**Asked:** "Keep the fixed logger lists and also save successful airport METAR fetches from Streamlit to `metar_history.csv`, with protection from duplicate rows on reruns."

**Got:** `views/airport_weather.py` now saves each successful METAR result through `MetarStore`. The cached fetch returns its UTC collection timestamp, and `MetarStore.append_if_new()` prevents Streamlit reruns from logging the same cached fetch twice. TAFs remain display-only.

**Checked:** Reviewed the cache key and storage key (`icao` plus the cached `fetched_at` timestamp). Syntax compilation and `git diff --check` passed. METAR and TAF request failures are handled separately, so one report type failing does not discard successful METARs. No API requests or automated tests were run for this change.

**Kept as-is.**

---

## Feature: Route overview page (map, weather along the route, possible alternates)

**Asked (Claude Code, Opus 5.5):** "I need a streamlit page for the route overview that I will push into the project", following the plan in the `views/route_overview.py` placeholder.

**Got:**
- `src/weather_app/route.py` (new): `Route` class for a great-circle route. It has `distance_nm` / `distance_km` properties, `points(n)` for evenly spaced points, `distance_from_route_nm()`, `bounding_box(margin_nm)`, `crosses_antimeridian`, and `__str__` / `__repr__`. There is no Streamlit code in it, so it can be tested on its own.
- `client.py`: `WeatherClient.current_at(lat, lon, label)` gets OpenWeatherMap weather by coordinates, for points over the sea. `AviationWeatherClient.metars_in_area(box)` makes one bbox request and skips unreadable reports.
- `views/route_overview.py`: a form with departure and destination codes, a number of weather points and a corridor width. It shows a pydeck map zoomed to the route, with the route as a black line, weather dots coloured by temperature, wind or cloud cover, nearby airports coloured by flight category, and hover tooltips. It also shows charts of temperature (°C) and wind (kt) against distance (nm), and a table of possible alternates with the closest VFR/MVFR airport to the destination. If one weather point fails, it is skipped, and a missing key only hides the weather part. Departure and destination METARs are saved with `MetarStore.append_if_new`, the same as on Airport weather.
- `glossary.py`: added "Nautical mile (nm)" and "Great circle".
- `pyproject.toml`: added `pydeck` as a dependency. The page imports it directly, and Anaconda's Streamlit does not include it, so the app failed on a clean Anaconda install.
- `tests/test_route.py`: hand-checkable cases. Madrid–London is about 670 nm, 1° along the equator is 60 nm, points are evenly spaced, a margin of 60 nm adds 1° of latitude, Tokyo–Los Angeles crosses the 180° line, and invalid routes are refused.

**Checked:** `pytest` passes (8 tests). One of my own tests was too strict at first, so I relaxed it to the documented accuracy of the sampled distance (about 3 nm). I ran the whole app with Streamlit `AppTest` against live aviationweather.gov data. LEMD→EGLL gives 673 nm, 16 airports near the route and EGSS as the closest good alternate. KJFK→EGLL gives 2,991 nm and 43 airports. `mad`, the same airport twice and `ZZZZ` each show their own error message. With no OpenWeatherMap key, the page shows a warning and the rest still works. There was no real key on this machine, so the weather-dot and chart code was run with a stand-in OpenWeatherMap response. That code path has **not** been checked against live OpenWeatherMap yet. The AppTest run found a real bug: the form inputs used `value=` defaults that change after each submit, so Streamlit recreated the widgets and ignored a new entry. Stable widget `key`s fixed it.

**Decision:** route weather points are **not** added to `weather_history.csv`. They are named after distances or nearby places, so they would fill the city-based Analytics page with one-off locations.
