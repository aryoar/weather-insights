"""Analytics calculated only from observations persisted by WeatherStore."""

import pandas as pd


def _with_location(history: pd.DataFrame) -> pd.DataFrame:
    result = history.copy()
    country = result["country"].fillna("").astype(str).str.strip()
    city = result["city"].fillna("").astype(str).str.strip()
    result["location"] = city.where(country.eq(""), city + ", " + country)
    return result


def temperature_trend(history: pd.DataFrame, location: str) -> pd.DataFrame:
    """Return timestamped temperature observations for one city and country."""
    if history.empty:
        return history.copy()
    locations = _with_location(history)
    result = locations.loc[locations["location"].str.casefold() == location.casefold()].copy()
    return result.sort_values("observed_at")


def latest_comparison(history: pd.DataFrame) -> pd.DataFrame:
    """Latest observation per city, with derived apparent-temperature delta."""
    if history.empty:
        return history.copy()
    result = _with_location(history)
    result = result.sort_values("observed_at").groupby("location", as_index=False).tail(1).copy()
    result["feels_like_delta_c"] = result["feels_like_c"] - result["temperature_c"]
    return result.sort_values("temperature_c", ascending=False)


def comfort_ranking(history: pd.DataFrame) -> pd.DataFrame:
    """Rank latest city observations using the app's simple comfort formula."""
    latest = latest_comparison(history)
    if latest.empty:
        return latest
    latest["comfort_index"] = (
        latest["temperature_c"]
        - latest["wind_speed_mps"] * 0.5
        - (latest["humidity_pct"] - 60).clip(lower=0) * 0.1
    )
    return latest.sort_values("comfort_index", ascending=False)
