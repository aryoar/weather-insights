# Weather Insights

Weather Insights is a Streamlit application for viewing current conditions from OpenWeatherMap and building a local, timestamped history for several locations. Its analytics include temperature trends, latest-condition comparisons, feels-like differences, and a comparative comfort ranking.

## Setup

Requires Python 3.11 or newer and an OpenWeatherMap API key.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e .
cp variables.env.example variables.env
```

Put your key in `variables.env`:

```text
OPENWEATHER_API_KEY=your_real_key
```

Do not commit `variables.env`. The app reads the key from the environment and never displays it.

## Run

```bash
streamlit run app.py
```

Run it from the activated virtual environment (`source .venv/bin/activate`). If you see
`ModuleNotFoundError: No module named 'weather_app'`, the app was started with a Python where
the project is not installed: activate `.venv` and run `python -m pip install -e .` again.

On **Live Conditions**, add locations and fetch current conditions. Successful fetches are appended to `data/weather_history.csv`. The **Analytics** view uses those recorded observations, so charts become more useful as the app is used over time. The CSV contains real fetched data and can be committed when the group has collected its observations.

## Run the tests

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

The tests use small hand-made inputs with known answers and need no API key or network.

## Collect project history

The project plan uses a fixed collection set: Madrid, London, and Paris, plus the LEMD, EGLL, and LFPG airport METARs. Run the collector from the project root at least twice a day until submission:

```bash
python scripts/log_weather.py
```

Each run appends successful observations to `data/weather_history.csv` and `data/metar_history.csv`. A failed location is reported while the other locations continue. Commit both CSV files regularly so the submitted repository contains real history across multiple days. Do not add sample or manually invented weather rows.

The **Airport weather** page also saves successful METAR fetches through the same `MetarStore`. Cached Streamlit reruns reuse the fetch timestamp, so they do not add the same cached fetch to the log again. TAFs are displayed but are not included in the METAR history.

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
- `app.py`: Streamlit entry point and sidebar navigation
- `views/`: one file per Streamlit page, including Live Conditions and Analytics
- `PROMPTS.md`: AI collaboration record

The Analytics page uses one shared observation-date filter for city weather and airport METARs. It shows city temperature and wind trends, airport flight-category mix, wind/gust and exact visibility history, plus daily temperature ranges and feels-like differences. Daily ranges require at least two temperature observations for the same city and date; the page leaves under-sampled days out rather than treating one reading as a zero range. Charts use only rows present in the history files.
