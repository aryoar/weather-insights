"""Environment configuration. Boilerplate — no need to change this."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "variables.env")

API_KEY = os.getenv("OPENWEATHER_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "OPENWEATHER_API_KEY is not set. Copy variables.env.example to variables.env "
        "and fill in your own key."
    )
