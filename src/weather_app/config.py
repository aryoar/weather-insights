"""Environment configuration for the weather application."""

import os
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[2] / "variables.env"
load_dotenv(ENV_FILE)


def get_api_key() -> str:
    """Return the configured API key or raise a user-actionable error."""
    key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    if not key or key == "your_key_here":
        raise RuntimeError(
            "OpenWeatherMap API key is missing. Copy variables.env.example to "
            "variables.env and add your key."
        )
    return key
