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

## Feature: Open-Meteo winds aloft client and headwind formula (Winds aloft, first step)

**Asked (Claude Code, Opus 5.5):** "Start step 2": the first small step for the Winds aloft page from the team plan: an `OpenMeteoClient(APIClient)` in `client.py` with one method returning wind and temperature at the cruise pressure levels for one coordinate, plus a test for the headwind formula (on the nose at 30 kt = +30, from behind = −30, from the side = 0).

**Got:**
- `winds.py` (new): `FLIGHT_LEVELS` (850 hPa ≈ FL050 … 200 hPa ≈ FL390), `headwind_component()` (wind speed × cos(wind direction − route direction)), and a `WindLevel` class with properties `flight_level`, `altitude_ft`, `altitude_m`, `wind_speed_kmh`, a `headwind_kt(route_direction)` method, `__str__`/`__repr__`, and `__lt__` so `sorted()` goes from low to high. `wind_levels_from_api()` leaves out levels the model did not report instead of inventing values.
- `client.py`: `OpenMeteoClient(APIClient)` with `winds_at(lat, lon)`. It needs no key, checks the coordinate range before calling the API, and asks for wind in knots. Errors go through the shared `APIClient._get` handling.
- `tests/test_winds.py`: known-answer tests for the formula (+30 / −30 / 0, and 15 kt at 60°), the `WindLevel` properties, and parsing a hand-made response.

**Checked:** First called Open-Meteo by hand. The `current=` parameter accepts pressure-level variables, and an out-of-range latitude returns HTTP 400. Ran `winds_at(40.47, -3.56)` (Madrid) live: it returned all six levels with plausible values (about 69 kt from 251° at FL340, −51 °C). A bad coordinate gives a clear `ValueError` before any request. `PYTHONPATH=src pytest tests` passed (8 tests).

**Kept as-is / changed / rejected:** Kept. Used `current=` rather than hourly forecasts because the page shows conditions now. Still to do: multi-point fetch along the route (needs `geo.py`), the page itself, and `average_headwind_kt(route, level)` for the Fuel planner.
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

---

## Feature: Winds aloft page (headwind per cruise height along the route)

**Asked (Claude Code, Opus 5.5):** After the route overview (`route.py`) was merged: build the Winds aloft page from the team plan. For the chosen route, show wind and temperature at several cruise heights along the route, the headwind or tailwind at each height, a "best height" hint and a labelled chart, and expose `average_headwind_kt(route, level)` for the Fuel planner.

**Got:**
- `winds.py`: `bearing_deg()` (great-circle direction), `tracks_along()` (direction of flight at each route point, since a great circle turns as it goes), and a `RouteWinds` class. It has properties `distances_nm`, `flight_levels` and `best_flight_level`, methods `headwinds_at(fl)`, `average_headwind_kt(fl)` and `summary_rows()`, and `__str__` / `__repr__`. A height missing at one point is averaged over the points that have it, never filled in. Also added `best_level_hint()` and the Fuel planner hand-off `average_headwind_kt(route, flight_level, point_count=8)`.
- `client.py`: `OpenMeteoClient.winds_many(points)` fetches all route points in **one** request (Open-Meteo returns a list for several coordinates). `winds_at()` now reuses it. `route_winds(route, n)` returns a `RouteWinds`.
- `views/winds_aloft.py`: a form with departure, destination and number of points. It defaults to the route chosen on the other pages, and validates codes before any call. It shows the best-height hint, metrics (distance in nm and km, best height), a Plotly heatmap (height × distance, red = headwind, blue = tailwind), a bar chart of the average headwind per height, a table in kt and km/h and in ft and m, the formula in a caption, a "why wind matters" expander and the glossary. Both API calls are cached with `@st.cache_data(ttl=300)`.
- `glossary.py`: "Flight level (FL)", "Headwind / tailwind", "Winds aloft", "Pressure level (hPa)".
- `pyproject.toml`: added `plotly`.
- `tests/test_winds.py`: bearings (north 0°, east 90°, south 180°), the track at each point, a hand-made equator route where FL300 has +40 kt and FL340 has −40 kt (best = FL340, with the exact hint text), and a height missing at one point.

**Checked:** `pytest`: 19 passed, in a fresh `uv` virtual environment with `pip install -e .`. Live: LEMD→EGLL (673 nm) gives a tailwind at every height, strongest at FL340 (about 37 kt). That makes sense for a north-north-east route under a westerly jet. KJFK→EGLL (2,991 nm) gives a tailwind at the higher levels. Ran the page with Streamlit `AppTest`: no exceptions. Both routes show the hint, 3 metrics, 2 charts and the table. `MAD`, `ZZZZ` and the same airport twice each show their own error. A simulated Open-Meteo outage shows "Winds aloft are not available right now: Could not reach Open-Meteo…" instead of crashing. The charts were not inspected visually, because the browser preview could not start the app from this folder.

**Kept / changed:** Kept. The direction-of-flight helpers went into `winds.py` rather than editing Teammate 3's `route.py`. This page does not write to `data/*.csv` (house rule: only the logger changes the logs).
