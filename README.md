# Weather Insights: SkyBrief Academy (flight-school edition)

**SkyBrief Academy** is a training app for flight schools: "DataCamp for aviation weather". Student pilots practise decoding **real** METARs and making go/no-go decisions on **live** data; instructors set the limits and build practice scenarios. Units follow EASA practice: metric next to knots and feet.

> ⚠️ Training aid only: not for real flight planning. Every page says so.

What a student does in one session:

1. **Learn**: *Start here* explains the flow; the **METAR trainer** shows a real METAR from one of eight European airports (LEMD, LEBL, LEPA, EGLL, LFPG, EDDF, LIRF, EHAM) and asks five multiple-choice questions (wind, visibility, ceiling, flight category, temperature/dew point, QNH), each with an explanation.
2. **Brief**: choose the flight once in the sidebar (**Your flight**: departure, destination, alternate; default LEMD → EGLL, alternate LFPG). Airport weather, Route overview, Winds aloft, Airport suitability and Fuel planner all use it. The **Briefing sheet** puts it on one downloadable page.
3. **Practise**: on **Go / No-Go** the student commits to GO or NO-GO for the departure airport first, then sees every check (crosswind on the best runway, visibility, ceiling, gust spread, VFR) against EXAMPLE student limits (10 kt, 5 km, 1,500 ft, 10 kt, VFR only; not regulations). **Instructor mode** in the sidebar edits the limits and can override wind, visibility and ceiling as a clearly marked SCENARIO.
4. **Data**: Live Conditions and Analytics keep the original weather-history features (three analytics views on our real logged data).

Weather data is always real (aviationweather.gov, OpenWeatherMap, Open-Meteo, and our own logs). If aviationweather.gov cannot be reached, the trainer, Go/No-Go and the briefing sheet fall back to the latest real METARs in `data/metar_history.csv` and say so on the page; nothing is invented.

The app also builds a local, timestamped history for several cities and airports. Analytics charts show city temperature and wind trends, airport condition patterns, daily temperature ranges, and feels-like differences.

## Setup

Requires Python 3.11 or newer and an OpenWeatherMap API key.

```bash
uv sync
cp variables.env.example variables.env
```

Put your key in `variables.env`:

```text
OPENWEATHER_API_KEY=your_real_key
```

Do not commit `variables.env`. The app reads the key from the environment and never displays it.

## Run

```bash
uv run streamlit run app.py
```

`uv sync` installs the project and its default development group from the committed lockfile. Put your OpenWeatherMap key in `variables.env` before fetching city conditions.

`uv sync` creates or updates the project’s `.venv`; it does not activate it or change the interpreter selected by your IDE. Use the `uv run ...` commands above and below, or select `.venv/bin/python` as the IDE interpreter. A virtual environment can report Anaconda as `sys.base_prefix`; it is using the project environment when `sys.prefix` points to this project’s `.venv`.

On **Live Conditions**, add locations and fetch current conditions. Successful fetches are appended to `data/weather_history.csv`. The **Analytics** view uses those recorded observations, so charts become more useful as the app is used over time. The CSV contains real fetched data and can be committed when the group has collected its observations.

## Run the tests

```bash
uv run pytest
```

The tests use small hand-made inputs with known answers and need no API key or network.

## Collect project history

The project plan uses a fixed collection set: Madrid, London, and Paris, plus the LEMD, EGLL, and LFPG airport METARs. Run the collector from the project root at least twice a day until submission:

```bash
uv run python scripts/log_weather.py
```

Each run appends successful city observations and new METAR observations to `data/weather_history.csv` and `data/metar_history.csv`. METAR rows are unique by airport and observation time. A failed location is reported while the other locations continue. Commit both CSV files regularly so the submitted repository contains real history across multiple days. Do not add sample or manually invented weather rows.

The **Airport weather** page also saves successful METAR fetches through the same `MetarStore`. Repeated fetches of an already logged airport observation are skipped. TAFs are displayed but are not included in the METAR history.

## Project structure

- `src/weather_app/client.py`: generic JSON API client (`APIClient`) and one subclass per provider: OpenWeatherMap (`WeatherClient`) and aviationweather.gov (`AviationWeatherClient`, free, no key)
- `src/weather_app/models.py`: validated weather snapshot and computed metrics
- `src/weather_app/reports.py`: METAR (observed) and TAF (forecast) airport reports, translated into plain language
- `src/weather_app/glossary.py`: plain-language explanations of aviation terms, used as tooltips
- `src/weather_app/storage.py`: append-only CSV history
- `src/weather_app/analytics.py`: trend, comparison, and ranking calculations
- `src/weather_app/route.py` and `winds.py`: great-circle route geometry, and winds aloft with the headwind along a route
- `src/weather_app/airports.py`: educational airport suitability checks (runway crosswind, daylight, flight category)
- `src/weather_app/fuel.py`: educational fuel estimate (`FuelPlan`) from the real distance and winds plus a hypothetical aircraft and load
- `src/weather_app/training.py`: METAR trainer questions (`MetarQuestion`, `build_questions`, `Scoreboard`) built from a real `MetarReport`
- `src/weather_app/decision.py`: Go/No-Go checks (`PilotLimits`, `Check`, `Decision`, `evaluate_go_no_go`, `grade_choice`) and instructor scenarios (`apply_scenario`)
- `src/weather_app/logged_metars.py`: reads the METAR history back as `MetarReport` objects (offline fallback)
- `src/weather_app/briefing.py`: `BriefingSheet`, the one-page flight summary
- `app.py`: Streamlit entry point: `st.navigation` with four sections (Learn, Brief, Practise, Data) and the shared **Your flight** sidebar
- `views/`: one file per Streamlit page (each has `render()`), including `home.py` (Start here), `metar_trainer.py`, `go_no_go.py`, `briefing_sheet.py`, Live Conditions and Analytics
- `views/common.py`: shared helpers: `sidebar_flight()` / `get_route()` (the flight used by every page), glossary, SCENARIO banner, METARs with logged fallback
- `views/theme.py` and `.streamlit/config.toml`: app name (`APP_NAME`, easy to rename), dark theme, colour palette (contrast-checked), page header, cards, status badges and the shared chart style
- `tests/test_training.py`, `tests/test_decision.py`, `tests/test_briefing.py`: hand-made inputs with known answers, no network
- `PROMPTS.md`: AI collaboration record

The Analytics page uses one shared observation-date filter for city weather and airport METARs. It shows city temperature and wind trends, airport flight-category mix, wind/gust and exact visibility history, plus daily temperature ranges and feels-like differences. Daily ranges require at least two temperature observations for the same city and date; the page leaves under-sampled days out rather than treating one reading as a zero range. Repeated identical city payloads fetched within two minutes and repeated airport observations are counted once in analytics. Charts use only rows present in the history files.
