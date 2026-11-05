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

On **Live Conditions**, add locations and fetch current conditions. Successful fetches are appended to `data/weather_history.csv`. The **Analytics** view uses those recorded observations, so charts become more useful as the app is used over time. The CSV contains real fetched data and can be committed when the group has collected its observations.

## Project structure

- `src/weather_app/client.py`: generic JSON API client and OpenWeatherMap client
- `src/weather_app/models.py`: validated weather snapshot and computed metrics
- `src/weather_app/storage.py`: append-only CSV history
- `src/weather_app/analytics.py`: trend, comparison, and ranking calculations
- `app.py`: Streamlit interface
- `PROMPTS.md`: AI collaboration record
