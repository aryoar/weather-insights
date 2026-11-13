"""Analytics calculated only from observations persisted by the weather stores."""

from datetime import date

import pandas as pd

LOCAL_TIMEZONE = "Europe/Madrid"
WEATHER_DUPLICATE_WINDOW = pd.Timedelta(minutes=2)


def deduplicate_weather_observations(
    history: pd.DataFrame,
    duplicate_window: pd.Timedelta = WEATHER_DUPLICATE_WINDOW,
) -> pd.DataFrame:
    """Drop identical weather payloads fetched close together, keeping the first.

    Observation timestamps are excluded from the payload comparison because each
    fetch assigns its own timestamp. Repeated values more than two minutes apart
    remain separate readings, even if the weather happens to be unchanged.
    """
    if history.empty or "observed_at" not in history or len(history.columns) < 2:
        return history.copy()

    result = history.copy().reset_index(drop=True)
    payload_columns = [column for column in result.columns if column != "observed_at"]
    if not payload_columns:
        return result
    timestamps = pd.to_datetime(result["observed_at"], utc=True, errors="coerce")
    result["observed_at"] = timestamps
    payload_hashes = pd.util.hash_pandas_object(result[payload_columns], index=False)
    window = pd.Timedelta(duplicate_window)
    last_kept_at: dict[int, pd.Timestamp] = {}
    duplicate_indices = []

    ordered_indices = timestamps.sort_values(kind="stable", na_position="last").index
    for index in ordered_indices:
        timestamp = timestamps.iloc[index]
        if pd.isna(timestamp):
            continue
        key = int(payload_hashes.iloc[index])
        previous = last_kept_at.get(key)
        if previous is not None and timestamp - previous < window:
            duplicate_indices.append(index)
        else:
            last_kept_at[key] = timestamp

    return result.drop(index=duplicate_indices).sort_values(
        "observed_at", kind="stable", na_position="last"
    ).reset_index(drop=True)


def deduplicate_metar_observations(history: pd.DataFrame) -> pd.DataFrame:
    """Keep the latest fetched version of each airport observation."""
    if history.empty or not {"icao", "observed_at"}.issubset(history.columns):
        return history.copy()

    result = history.copy().reset_index(drop=True)
    result["icao"] = result["icao"].fillna("").astype(str).str.strip().str.upper()
    result["observed_at"] = pd.to_datetime(result["observed_at"], utc=True, errors="coerce")
    valid = result["icao"].ne("") & result["observed_at"].notna()
    if not valid.any():
        return result

    unique_rows = result.loc[valid].copy()
    if "fetched_at" in unique_rows:
        unique_rows["fetched_at"] = pd.to_datetime(unique_rows["fetched_at"], utc=True, errors="coerce")
        unique_rows = unique_rows.sort_values("fetched_at", kind="stable", na_position="first")
    unique_rows = unique_rows.drop_duplicates(["icao", "observed_at"], keep="last")
    invalid_rows = result.loc[~valid]
    combined = unique_rows if invalid_rows.empty else pd.concat([unique_rows, invalid_rows], ignore_index=True)
    return combined.sort_values(
        "observed_at", kind="stable", na_position="last"
    ).reset_index(drop=True)


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
    locations = _with_location(deduplicate_weather_observations(history))
    result = locations.loc[locations["location"].str.casefold() == location.casefold()].copy()
    return result.sort_values("observed_at")


def latest_comparison(history: pd.DataFrame) -> pd.DataFrame:
    """Latest observation per city, with derived apparent-temperature delta."""
    if history.empty:
        return history.copy()
    result = _with_location(deduplicate_weather_observations(history))
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


def daily_temperature_ranges(history: pd.DataFrame) -> pd.DataFrame:
    """Return each city's observed daily temperature range in Madrid local dates.

    A day with a single temperature observation is retained with a missing range;
    reporting a range of zero from one sample would imply unsupported certainty.
    """
    required = {"observed_at", "city", "temperature_c"}
    if history.empty or not required.issubset(history.columns):
        return pd.DataFrame(columns=["location", "day", "min_temperature_c", "max_temperature_c",
                                     "observation_count", "temperature_range_c"])

    result = _with_location(deduplicate_weather_observations(history))
    result["observed_at"] = pd.to_datetime(result["observed_at"], utc=True, errors="coerce")
    result["temperature_c"] = pd.to_numeric(result["temperature_c"], errors="coerce")
    result = result.dropna(subset=["observed_at", "temperature_c", "location"])
    if result.empty:
        return pd.DataFrame(columns=["location", "day", "min_temperature_c", "max_temperature_c",
                                     "observation_count", "temperature_range_c"])

    result["day"] = result["observed_at"].dt.tz_convert(LOCAL_TIMEZONE).dt.date
    daily = (
        result.groupby(["location", "day"], as_index=False)
        .agg(min_temperature_c=("temperature_c", "min"),
             max_temperature_c=("temperature_c", "max"),
             observation_count=("temperature_c", "count"))
    )
    daily["temperature_range_c"] = daily["max_temperature_c"] - daily["min_temperature_c"]
    daily.loc[daily["observation_count"] < 2, "temperature_range_c"] = float("nan")
    return daily.sort_values(["day", "location"]).reset_index(drop=True)


def airport_ifr_lifr_share(
    history: pd.DataFrame,
    start_date: date,
    end_date: date,
    airports: list[str] | None = None,
) -> pd.DataFrame:
    """Rank airports by observed IFR/LIFR share over inclusive Madrid-local dates.

    Each eligible METAR record counts once. The result includes the sample size so
    rankings based on very few observations remain visible to the reader.
    """
    columns = ["icao", "name", "ifr_lifr_count", "observation_count", "ifr_lifr_share_pct"]
    if start_date > end_date:
        return pd.DataFrame(columns=columns)
    required = {"observed_at", "icao", "flight_category"}
    if history.empty or not required.issubset(history.columns):
        return pd.DataFrame(columns=columns)

    result = deduplicate_metar_observations(history)
    result["observed_at"] = pd.to_datetime(result["observed_at"], utc=True, errors="coerce")
    result["icao"] = result["icao"].fillna("").astype(str).str.strip().str.upper()
    result["flight_category"] = result["flight_category"].fillna("").astype(str).str.strip().str.upper()
    result = result.dropna(subset=["observed_at"])
    result = result.loc[result["icao"].ne("") & result["flight_category"].ne("")].copy()
    local_dates = result["observed_at"].dt.tz_convert(LOCAL_TIMEZONE).dt.date
    result = result.loc[local_dates.between(start_date, end_date)].copy()
    if airports is not None:
        selected = {code.strip().upper() for code in airports}
        result = result.loc[result["icao"].isin(selected)]
    if result.empty:
        return pd.DataFrame(columns=columns)

    result["is_ifr_lifr"] = result["flight_category"].isin({"IFR", "LIFR"})
    if "name" not in result:
        result["name"] = ""
    result["name"] = result["name"].fillna("").astype(str)
    ranked = (
        result.groupby("icao", as_index=False)
        .agg(name=("name", "last"), ifr_lifr_count=("is_ifr_lifr", "sum"),
             observation_count=("is_ifr_lifr", "size"))
    )
    ranked["ifr_lifr_share_pct"] = 100 * ranked["ifr_lifr_count"] / ranked["observation_count"]
    return ranked.sort_values(["ifr_lifr_share_pct", "observation_count", "icao"],
                              ascending=[False, False, True]).reset_index(drop=True)
