# AI collaboration log

Add one entry per feature/class you asked an AI agent to help with, in the order you worked on them.
Keep this running as you go — don't reconstruct it from memory at the end.

## Feature: Project implementation from the capstone brief

**Asked:** "Learn from these to do the project" with the group capstone README and summary supplied as context.

**Got:** Implemented API client and weather model in `src/weather_app/client.py` and `models.py`; CSV history in `storage.py`; trend, comparison, and comfort ranking in `analytics.py`; Streamlit views in `app.py`; setup documentation and secret ignores.

**Checked:** `python -m compileall -q app.py src/weather_app`, `git diff --check`, and built and inspected a wheel with `python -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/weather-insights-wheel .`. No API key was available, so live requests and a real history file have not been produced. No automated tests have been run.

**Kept as-is / changed / rejected:** Kept the starter `src/` package layout and completed its stub modules. Used a local CSV so only successful API fetches become history; left the history empty until the group runs the app with its own key.

---

## Feature: future-proof weather log (CSV) before collecting data

**Asked (Claude Code, Opus 5.5):** After planning an aviation weather briefing app, "let's continue building on it". The agent proposed fixing the log format first, because OpenWeatherMap's free tier only returns current conditions and any field we don't save now can't be recovered later.

**Got:**
- `models.py`: `LocationSnapshot` now also stores latitude, longitude, pressure, wind direction, wind gust, visibility and cloud cover. Gust, direction, visibility and clouds are optional because OpenWeatherMap leaves them out of some responses. Coordinates and cloud cover are range-checked.
- `storage.py`: the log is always saved to `<project>/data/weather_history.csv`, whichever folder the app is started from (`DEFAULT_PATH`). Appending to a file with an older column layout now raises a clear `ValueError` instead of silently mixing formats.
- `app.py`: shows that storage error to the user.

**Checked:** ran a check script with hand-made responses (a complete one, and one with no gust, visibility or clouds). Both saved and loaded back correctly, with missing values as empty cells. An old-format file was refused with the message. An incomplete response raised "incomplete weather response". One live fetch for Madrid parsed correctly, and the real response had no gust field. Converted the one real row already in `data/weather_history.csv` to the new columns, leaving the new fields empty (not invented). Analytics functions and `app.py` still run.

**Kept as-is** _(Kept as-is after reviewing the diff)_

---
