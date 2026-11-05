# AI collaboration log

Add one entry per feature/class you asked an AI agent to help with, in the order you worked on them.
Keep this running as you go — don't reconstruct it from memory at the end.

## Feature: Project implementation from the capstone brief

**Asked:** "Learn from these to do the project" with the group capstone README and summary supplied as context.

**Got:** Implemented API client and weather model in `src/weather_app/client.py` and `models.py`; CSV history in `storage.py`; trend, comparison, and comfort ranking in `analytics.py`; Streamlit views in `app.py`; setup documentation and secret ignores.

**Checked:** `python -m compileall -q app.py src/weather_app`, `git diff --check`, and built and inspected a wheel with `python -m pip wheel --no-deps --no-build-isolation --wheel-dir /tmp/weather-insights-wheel .`. No API key was available, so live requests and a real history file have not been produced. No automated tests have been run.

**Kept as-is / changed / rejected:** Kept the starter `src/` package layout and completed its stub modules. Used a local CSV so only successful API fetches become history; left the history empty until the group runs the app with its own key.

---
