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



---
