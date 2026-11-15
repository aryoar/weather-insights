"""Historical weather and METAR analytics."""

from datetime import date
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from weather_app.analytics import (
    LOCAL_TIMEZONE,
    daily_temperature_ranges,
    deduplicate_metar_observations,
    deduplicate_weather_observations,
)
from weather_app.storage import MetarStore, WeatherStore

from .theme import CATEGORY_STYLE, SERIES, chart, colour_for, colour_map, hero

DEFAULT_CITIES = ("Madrid", "London", "Paris")
DEFAULT_AIRPORTS = ("LEMD", "EGLL", "LFPG")
CATEGORY_ORDER = ["VFR", "MVFR", "IFR", "LIFR"]
CATEGORY_COLOURS = {code: style["colour"] for code, style in CATEGORY_STYLE.items()}
# Legend labels carry an icon as well as the colour, so colour is never the only cue.
CATEGORY_LABELS = {code: f"{style['icon']} {code}" for code, style in CATEGORY_STYLE.items()}


def _local_dates(frame: pd.DataFrame, column: str) -> pd.Series:
    timestamps = pd.to_datetime(frame[column], utc=True, errors="coerce")
    return timestamps.dt.tz_convert(LOCAL_TIMEZONE).dt.date


def _filter_dates(frame: pd.DataFrame, column: str, selected: tuple[date, date] | None) -> pd.DataFrame:
    if frame.empty or column not in frame or selected is None:
        return frame.iloc[0:0].copy()
    if selected[0] > selected[1]:
        return frame.iloc[0:0].copy()
    dates = _local_dates(frame, column)
    return frame.loc[dates.between(selected[0], selected[1])].copy()


def _combined_date_bounds(weather: pd.DataFrame, metars: pd.DataFrame) -> tuple[date, date] | None:
    all_dates = []
    for frame in (weather, metars):
        if "observed_at" not in frame or frame.empty:
            continue
        valid = _local_dates(frame, "observed_at").dropna()
        if not valid.empty:
            all_dates.extend((valid.min(), valid.max()))
    return (min(all_dates), max(all_dates)) if all_dates else None


def _normalize_date_selection(value, fallback: tuple[date, date]) -> tuple[date, date] | None:
    """Accept complete or partial Streamlit date input values without raising."""
    if isinstance(value, (tuple, list)):
        chosen = [item for item in value if isinstance(item, date)]
        if len(chosen) == 2:
            return (chosen[0], chosen[1]) if chosen[0] <= chosen[1] else None
        if len(chosen) == 1:
            return chosen[0], chosen[0]
        return fallback
    if isinstance(value, date):
        return value, value
    return fallback


def _sidebar_filters(
    weather: pd.DataFrame, metars: pd.DataFrame,
) -> tuple[tuple[date, date] | None, str | None, list[str], list[str]]:
    bounds = _combined_date_bounds(weather, metars)
    selected_range = None
    if bounds:
        st.sidebar.subheader("Shared observation filter")
        st.sidebar.caption("One date range applies to both city weather and airport METAR history. Dates use Madrid local time.")
        raw_range = st.sidebar.date_input(
            "Observation date range",
            value=bounds,
            min_value=bounds[0],
            max_value=bounds[1],
            key="analytics_shared_dates",
        )
        selected_range = _normalize_date_selection(raw_range, bounds)
        if selected_range is None:
            st.sidebar.info("The end date is before the start date. Choose a valid range.")
    else:
        st.sidebar.caption("Date filtering is unavailable until dated observations have been collected.")

    city_names = sorted(weather.loc[weather.get("city", pd.Series(dtype=str)).notna(), "city"].astype(str).unique()) if "city" in weather else []
    if city_names:
        default_city = "Madrid" if "Madrid" in city_names else city_names[0]
        st.sidebar.subheader("City weather")
        trend_city = st.sidebar.selectbox(
            "Trend city", city_names, index=city_names.index(default_city), key="analytics_trend_city",
        )
        defaults = [city for city in DEFAULT_CITIES if city in city_names] or city_names
        daily_cities = st.sidebar.multiselect(
            "Cities for daily metrics", city_names, default=defaults, key="analytics_daily_cities",
        )
        if not daily_cities:
            st.sidebar.caption("No cities selected; showing all available cities.")
            daily_cities = city_names
    else:
        trend_city, daily_cities = None, []
        st.sidebar.caption("No city weather history is available yet.")

    airport_codes = sorted(metars["icao"].dropna().astype(str).str.strip().str.upper().unique()) if "icao" in metars else []
    airport_codes = [code for code in airport_codes if code]
    if airport_codes:
        st.sidebar.subheader("Airport conditions")
        defaults = [code for code in DEFAULT_AIRPORTS if code in airport_codes] or airport_codes
        airport_names = {}
        if "name" in metars:
            airport_names = (
                metars.dropna(subset=["icao"]).assign(icao=lambda data: data["icao"].astype(str).str.upper())
                .drop_duplicates("icao", keep="last").set_index("icao")["name"].fillna("").to_dict()
            )
        selected_airports = st.sidebar.multiselect(
            "Airports", airport_codes, default=defaults, key="analytics_airports",
            format_func=lambda code: f"{code} — {airport_names.get(code, '')}".rstrip(" —"),
        )
        if not selected_airports:
            st.sidebar.caption("No airports selected; showing all available airports.")
            selected_airports = airport_codes
    else:
        selected_airports = []
        st.sidebar.caption("No airport METAR history is available yet.")

    return selected_range, trend_city, daily_cities, selected_airports


def _plot_weather_trends(history: pd.DataFrame, city: str) -> tuple[go.Figure | None, go.Figure | None, int]:
    data = history.loc[history["city"].astype(str).str.casefold() == city.casefold()].copy()
    if data.empty:
        return None, None, 0
    data["observed_at"] = pd.to_datetime(data["observed_at"], utc=True, errors="coerce")
    data = data.dropna(subset=["observed_at"]).sort_values("observed_at")
    for column in ("temperature_c", "wind_speed_mps"):
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")
    count = len(data)

    colour = colour_for(city) or SERIES[0]
    temperature = None
    if "temperature_c" in data and data["temperature_c"].notna().any():
        temps = data.dropna(subset=["temperature_c"])
        temperature = px.line(
            temps, x="observed_at", y="temperature_c",
            markers=True, title=(f"{city}: {temps['temperature_c'].iloc[0]:.0f} → {temps['temperature_c'].iloc[-1]:.0f} °C, "
                                 f"between {temps['temperature_c'].min():.0f} and {temps['temperature_c'].max():.0f} °C"),
            color_discrete_sequence=[colour],
            hover_data={"observed_at": "|%d %b %Y %H:%M UTC", "temperature_c": ":.1f"},
        )
        temperature.update_layout(xaxis_title="Observation time (UTC)", yaxis_title="Temperature (°C)")

    wind = None
    if "wind_speed_mps" in data and data["wind_speed_mps"].notna().any():
        winds = data.dropna(subset=["wind_speed_mps"])
        peak = winds.loc[winds["wind_speed_mps"].idxmax()]
        wind = px.line(
            winds, x="observed_at", y="wind_speed_mps",
            markers=True, title=(f"{city}: wind peaked at {peak['wind_speed_mps']:.1f} m/s "
                                 f"({peak['wind_speed_mps'] * 3.6:.0f} km/h) on {peak['observed_at']:%d %b}"),
            color_discrete_sequence=[colour],
            hover_data={"observed_at": "|%d %b %Y %H:%M UTC", "wind_speed_mps": ":.1f"},
        )
        wind.update_layout(xaxis_title="Observation time (UTC)", yaxis_title="Wind speed (m/s; × 3.6 = km/h)",
                           yaxis_rangemode="tozero")
    return temperature, wind, count


def _airport_category_chart(history: pd.DataFrame) -> go.Figure | None:
    if not {"icao", "flight_category"}.issubset(history.columns):
        return None
    data = history.dropna(subset=["icao", "flight_category"]).copy()
    if data.empty:
        return None
    data["icao"] = data["icao"].astype(str).str.upper()
    data["flight_category"] = data["flight_category"].astype(str).str.upper()
    counts = data.groupby(["icao", "flight_category"]).size().rename("reports").reset_index()
    counts = counts.loc[counts["flight_category"].isin(CATEGORY_ORDER)]
    if counts.empty:
        return None
    totals = counts.groupby("icao")["reports"].sum()
    poor = counts.loc[counts["flight_category"].isin(["IFR", "LIFR"])].groupby("icao")["reports"].sum()
    share = (poor / totals).fillna(0).sort_values(ascending=False)
    title = ("Every logged report was VFR or MVFR" if share.empty or share.iloc[0] == 0 else
             f"{share.index[0]} had the most IFR/LIFR time: {share.iloc[0]:.0%} of its reports")
    order = list(totals.sort_values(ascending=False).index)  # most reports first
    counts["category"] = counts["flight_category"].map(CATEGORY_LABELS)
    fig = px.bar(
        counts, x="icao", y="reports", color="category", barmode="stack",
        category_orders={"category": [CATEGORY_LABELS[c] for c in CATEGORY_ORDER], "icao": order},
        color_discrete_map={CATEGORY_LABELS[c]: CATEGORY_COLOURS[c] for c in CATEGORY_ORDER},
        title=title, hover_data={"icao": True, "category": True, "reports": True},
    )
    fig.update_layout(xaxis_title="Airport", yaxis_title="METAR reports (count)", legend_title="Flight category")
    return fig


def _airport_wind_chart(history: pd.DataFrame) -> go.Figure | None:
    if not {"icao", "observed_at", "wind_speed_kt"}.issubset(history.columns):
        return None
    data = history.copy()
    data["observed_at"] = pd.to_datetime(data["observed_at"], utc=True, errors="coerce")
    data["wind_speed_kt"] = pd.to_numeric(data["wind_speed_kt"], errors="coerce")
    data = data.dropna(subset=["observed_at", "wind_speed_kt", "icao"]).sort_values("observed_at")
    if data.empty:
        return None
    fig = go.Figure()
    colours = colour_map(sorted(data["icao"].astype(str).unique()))
    for airport, rows in data.groupby("icao"):
        fig.add_trace(go.Scatter(
            x=rows["observed_at"], y=rows["wind_speed_kt"], mode="lines+markers",
            name=f"{airport} wind", legendgroup=str(airport), line={"color": colours[str(airport)]},
            customdata=rows["wind_speed_kt"] * 1.852,
            hovertemplate=f"{airport}<br>%{{x|%d %b %H:%M UTC}}<br>Wind: %{{y:.0f}} kt (%{{customdata:.0f}} km/h)<extra></extra>",
        ))
        if "wind_gust_kt" in rows and rows["wind_gust_kt"].notna().any():
            gusts = rows.dropna(subset=["wind_gust_kt"])
            fig.add_trace(go.Scatter(
                x=gusts["observed_at"], y=pd.to_numeric(gusts["wind_gust_kt"], errors="coerce"),
                mode="markers", marker={"symbol": "diamond", "size": 9, "color": colours[str(airport)]},
                name=f"{airport} gust", legendgroup=str(airport),
                hovertemplate=f"{airport}<br>%{{x|%d %b %H:%M UTC}}<br>Gust: %{{y:.0f}} kt<extra></extra>",
            ))
    strongest = data.loc[data["wind_speed_kt"].idxmax()]
    fig.update_layout(title=(f"Strongest wind: {strongest['wind_speed_kt']:.0f} kt at {strongest['icao']} "
                             f"on {strongest['observed_at']:%d %b}"), xaxis_title="Observation time (UTC)",
                      yaxis_title="Wind / gust (kt; 1 kt = 1.852 km/h)", hovermode="x unified", yaxis_rangemode="tozero")
    return fig


def _airport_visibility_chart(history: pd.DataFrame) -> go.Figure | None:
    if not {"icao", "observed_at", "visibility_km"}.issubset(history.columns):
        return None
    data = history.copy()
    data["observed_at"] = pd.to_datetime(data["observed_at"], utc=True, errors="coerce")
    data["visibility_km"] = pd.to_numeric(data["visibility_km"], errors="coerce")
    if "visibility_at_least" in data:
        censored = data["visibility_at_least"].fillna(False).astype(str).str.casefold().isin({"true", "1"})
        data.loc[censored, "visibility_km"] = float("nan")
    data = data.dropna(subset=["observed_at", "visibility_km", "icao"]).sort_values("observed_at")
    if data.empty:
        return None
    lowest = data.loc[data["visibility_km"].idxmin()]
    fig = px.line(
        data, x="observed_at", y="visibility_km", color="icao", markers=True,
        color_discrete_map=colour_map(sorted(data["icao"].astype(str).unique())),
        title=f"Lowest exact visibility: {lowest['visibility_km']:.1f} km at {lowest['icao']} on {lowest['observed_at']:%d %b}",
        hover_data={"observed_at": "|%d %b %Y %H:%M UTC", "visibility_km": ":.1f", "icao": True},
    )
    fig.update_layout(xaxis_title="Observation time (UTC)", yaxis_title="Visibility (km)", yaxis_rangemode="tozero")
    return fig


def _airport_summary(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty or "icao" not in history:
        return pd.DataFrame()
    data = history.copy()
    data["observed_at"] = pd.to_datetime(data["observed_at"], utc=True, errors="coerce")
    rows = []
    for airport, group in data.dropna(subset=["icao", "observed_at"]).groupby("icao"):
        group = group.sort_values("observed_at")
        latest = group.iloc[-1]
        wind = pd.to_numeric(group.get("wind_speed_kt"), errors="coerce") if "wind_speed_kt" in group else pd.Series(dtype=float)
        visibility = pd.to_numeric(group.get("visibility_km"), errors="coerce") if "visibility_km" in group else pd.Series(dtype=float)
        if "visibility_at_least" in group:
            censored = group["visibility_at_least"].fillna(False).astype(str).str.casefold().isin({"true", "1"})
            visibility.loc[censored] = float("nan")
        rows.append({
            "Airport": airport,
            "Name": latest.get("name", ""),
            "Reports": len(group),
            "Latest category": latest.get("flight_category", "n/a"),
            "Latest observation (UTC)": latest["observed_at"].strftime("%Y-%m-%d %H:%M"),
            "Mean wind (kt)": wind.mean(),
            "Lowest exact visibility (km)": visibility.min(),
        })
    return pd.DataFrame(rows).sort_values("Airport").reset_index(drop=True)


def _feels_like_chart(history: pd.DataFrame) -> go.Figure | None:
    required = {"city", "country", "observed_at", "temperature_c", "feels_like_c"}
    if not required.issubset(history.columns) or history.empty:
        return None
    data = history.copy()
    data["feels_like_delta_c"] = pd.to_numeric(data["feels_like_c"], errors="coerce") - pd.to_numeric(
        data["temperature_c"], errors="coerce"
    )
    data["observed_at"] = pd.to_datetime(data["observed_at"], utc=True, errors="coerce")
    data = data.dropna(subset=["observed_at", "feels_like_delta_c"])
    if data.empty:
        return None
    data = data.sort_values("observed_at")
    data["city_label"] = data["city"].astype(str) + data["country"].fillna("").map(
        lambda country: f", {country}" if country else ""
    )
    mean_gap = data.groupby("city_label")["feels_like_delta_c"].mean()
    coldest = mean_gap.idxmin()
    fig = px.line(
        data, x="observed_at", y="feels_like_delta_c", color="city_label", markers=True,
        color_discrete_map=colour_map(sorted(data["city_label"].unique())),
        title=f"{coldest} feels {abs(mean_gap[coldest]):.1f} °C {'colder' if mean_gap[coldest] < 0 else 'warmer'} than the air on average",
        hover_data={"observed_at": "|%d %b %Y %H:%M UTC", "feels_like_delta_c": ":+.1f", "city_label": True},
    )
    fig.add_hline(y=0, line_color="#8A9BB5")
    fig.update_layout(xaxis_title="Observation time (UTC)", yaxis_title="Feels like − air temperature (°C)")
    return fig


def render() -> None:
    hero("Analytics", "How the weather changed in the cities and at the airports we logged: trends, "
         "airport conditions and daily patterns, from our own recorded observations.", kicker="Data · History")
    st.caption("Charts use recorded observations only. Dates are filtered in Madrid local time; chart timestamps use UTC.")

    try:
        weather = deduplicate_weather_observations(WeatherStore().load())
    except (OSError, ValueError) as exc:
        weather = pd.DataFrame()
        st.error(f"Could not read city weather history: {exc}")
    try:
        metars = deduplicate_metar_observations(MetarStore().load())
    except (OSError, ValueError) as exc:
        metars = pd.DataFrame()
        st.error(f"Could not read airport METAR history: {exc}")

    date_range, trend_city, daily_cities, airports = _sidebar_filters(weather, metars)
    trend_tab, airport_tab, daily_tab = st.tabs([
        "A · Weather trend", "B · Airport conditions", "C · Daily metrics",
    ])

    filtered_weather = _filter_dates(weather, "observed_at", date_range)
    filtered_metars = _filter_dates(metars, "observed_at", date_range)
    if airports and "icao" in filtered_metars:
        filtered_metars = filtered_metars.loc[
            filtered_metars["icao"].astype(str).str.upper().isin(airports)
        ]

    with trend_tab:
        st.subheader("Temperature and wind over time")
        if trend_city is None:
            st.info("City weather history is not available yet. Collect observations with Live Conditions or the logger.")
        elif filtered_weather.empty:
            st.info("No city observations fall in the selected date range.")
        else:
            temperature_fig, wind_fig, count = _plot_weather_trends(filtered_weather, trend_city)
            metric_left, metric_middle, metric_right = st.columns(3)
            city_rows = filtered_weather.loc[
                filtered_weather["city"].astype(str).str.casefold() == trend_city.casefold()
            ].copy()
            city_rows["observed_at"] = pd.to_datetime(city_rows["observed_at"], utc=True, errors="coerce")
            city_rows = city_rows.dropna(subset=["observed_at"]).sort_values("observed_at")
            metric_left.metric("Observations in range", f"{count}")
            latest = city_rows.iloc[-1] if not city_rows.empty else None
            latest_temp = pd.to_numeric(pd.Series([latest.get("temperature_c")]), errors="coerce").iloc[0] if latest is not None else float("nan")
            latest_wind = pd.to_numeric(pd.Series([latest.get("wind_speed_mps")]), errors="coerce").iloc[0] if latest is not None else float("nan")
            metric_middle.metric(
                "Latest temperature", f"{latest_temp:.1f} °C" if pd.notna(latest_temp) else "Unavailable",
                help="Latest recorded city observation within the selected date range.",
            )
            metric_right.metric(
                "Latest wind speed", f"{latest_wind:.1f} m/s" if pd.notna(latest_wind) else "Unavailable",
                help="Latest recorded wind speed within the selected date range.",
            )
            if temperature_fig is not None:
                chart(temperature_fig, key="an_temperature")
            else:
                st.info("Temperature values are missing for this city and date range.")
            if wind_fig is not None:
                chart(wind_fig, key="an_city_wind")
            else:
                st.info("Wind speed values are missing for this city and date range.")
            if count < 2:
                st.caption("One sample is shown as a point; more observations are needed to identify a trend.")

    with airport_tab:
        st.subheader("Airport condition patterns")
        if filtered_metars.empty:
            st.info("No airport METAR observations fall in the selected date range. Choose another range or collect reports.")
        else:
            category_fig = _airport_category_chart(filtered_metars)
            wind_fig = _airport_wind_chart(filtered_metars)
            visibility_fig = _airport_visibility_chart(filtered_metars)
            if category_fig is not None:
                chart(category_fig, key="an_categories")
            else:
                st.info("Flight category values are unavailable in these reports.")
            if wind_fig is not None:
                chart(wind_fig, key="an_airport_wind")
            else:
                st.info("Wind speed values are unavailable in these reports.")
            if visibility_fig is not None:
                chart(visibility_fig, key="an_visibility")
                st.caption("Visibility reports marked as 9999 or greater are omitted from the exact-value trend.")
            else:
                st.info("No exact visibility measurements are available in this range.")
            summary = _airport_summary(filtered_metars)
            if summary.empty:
                st.info("No dated airport reports are available for the summary table.")
            else:
                st.dataframe(summary, hide_index=True, width="stretch")

    with daily_tab:
        st.subheader("Daily temperature range and feels-like patterns")
        if filtered_weather.empty:
            st.info("No city observations fall in the selected date range. Collect observations or choose another range.")
        else:
            selected_weather = filtered_weather.loc[
                filtered_weather["city"].astype(str).isin(daily_cities)
            ].copy()
            if selected_weather.empty:
                st.info("No observations match the selected cities. Choose a city in the sidebar.")
            else:
                daily = daily_temperature_ranges(selected_weather)
                valid_daily = daily.loc[daily["temperature_range_c"].notna()].copy()
                feels = _feels_like_chart(selected_weather)

                card1, card2, card3 = st.columns(3)
                card1.metric("City-days with 2+ samples", f"{len(valid_daily)}")
                mean_range = valid_daily["temperature_range_c"].mean() if not valid_daily.empty else float("nan")
                card2.metric("Mean observed daily range", f"{mean_range:.1f} °C" if pd.notna(mean_range) else "Unavailable")
                if {"temperature_c", "feels_like_c"}.issubset(selected_weather.columns):
                    delta = pd.to_numeric(selected_weather["feels_like_c"], errors="coerce") - pd.to_numeric(
                        selected_weather["temperature_c"], errors="coerce"
                    )
                    mean_delta = delta.mean()
                else:
                    mean_delta = float("nan")
                card3.metric("Mean feels-like difference", f"{mean_delta:+.1f} °C" if pd.notna(mean_delta) else "Unavailable")

                if valid_daily.empty:
                    st.info("Daily range needs at least two temperatures for the same city and local date; none of the selected city-days has enough samples yet.")
                else:
                    widest = valid_daily.loc[valid_daily["temperature_range_c"].idxmax()]
                    range_fig = px.bar(
                        valid_daily, x=valid_daily["day"].astype(str), y="temperature_range_c",
                        color="location", barmode="group",
                        color_discrete_map=colour_map(sorted(valid_daily["location"].astype(str).unique())),
                        title=(f"Widest daily range: {widest['temperature_range_c']:.1f} °C in {widest['location']} "
                               f"on {widest['day']}"),
                        custom_data=["min_temperature_c", "max_temperature_c", "observation_count"],
                    )
                    range_fig.update_traces(hovertemplate=(
                        "%{fullData.name} · %{x}<br>Range: %{y:.1f} °C"
                        "<br>Low: %{customdata[0]:.1f} °C · High: %{customdata[1]:.1f} °C"
                        "<br>Observations: %{customdata[2]}<extra></extra>"
                    ))
                    range_fig.update_layout(xaxis_title="Date (Madrid local time)", yaxis_title="Daily range (°C)")
                    chart(range_fig, key="an_daily_range")
                if feels is not None:
                    chart(feels, key="an_feels")
                else:
                    st.info("Feels-like measurements are unavailable in the selected history.")
                table = daily.rename(columns={
                    "location": "City", "day": "Date (Madrid)", "min_temperature_c": "Low (°C)",
                    "max_temperature_c": "High (°C)", "observation_count": "Samples",
                    "temperature_range_c": "Range (°C)",
                })
                table["Date (Madrid)"] = table["Date (Madrid)"].astype(str)
                st.dataframe(table, hide_index=True, width="stretch")
