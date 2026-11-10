"""Generic JSON API behavior, plus one subclass per data provider.

APIClient knows HOW to call any JSON API (build the URL, add the key, send the request,
turn each failure into a clear error). Each subclass only knows WHICH API to call and
what its answers mean:
- WeatherClient: OpenWeatherMap (needs an API key)
- AviationWeatherClient: aviationweather.gov METAR/TAF reports (free, no key)
- OpenMeteoClient: Open-Meteo model winds and temperature at altitude (free, no key)
"""

from typing import Any, Callable

import requests

from .models import LocationSnapshot, snapshot_from_api
from .reports import MetarReport, TafReport, clean_icao_code, metar_from_api, taf_from_api
from .winds import FLIGHT_LEVELS, WindLevel, wind_levels_from_api


class APIClient:
    """Reusable JSON GET client with explicit timeout and status handling."""

    provider_name = "The data service"  # subclasses replace this, so messages name the real provider
    _key_param = None                   # query parameter that carries the API key, if the API needs one

    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        # Private (name-mangled to _APIClient__api_key): only _get below reads it, so no
        # subclass, log line or error message can expose the key by accident.
        self.__api_key = api_key
        self._timeout = timeout

    def __repr__(self) -> str:
        key_state = "set, hidden" if self.__api_key else "none"
        return f"{type(self).__name__}(base_url={self.base_url!r}, api_key=<{key_state}>)"

    def _get(self, endpoint: str, params: dict[str, Any]) -> Any:
        """Send a GET request and return the decoded JSON (None if the API had no content)."""
        query = dict(params)
        if self._key_param and self.__api_key:
            query[self._key_param] = self.__api_key
        try:
            response = requests.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                params=query,
                timeout=self._timeout,
            )
        # We never show the original requests error text: it can contain the full URL,
        # including the API key.
        except requests.Timeout as exc:
            raise ConnectionError(f"{self.provider_name} took too long to answer. Please try again.") from exc
        except requests.RequestException as exc:
            raise ConnectionError(f"Could not reach {self.provider_name}. Check your internet connection.") from exc

        if response.status_code == 401:
            raise PermissionError(f"The {self.provider_name} API key is invalid or inactive. Check variables.env.")
        if response.status_code == 404:
            raise LookupError(f"{self.provider_name} could not find what was requested.")
        if response.status_code == 429:
            raise RuntimeError(f"Too many requests to {self.provider_name}. Wait a minute and try again.")
        if response.status_code >= 500:
            raise RuntimeError(f"{self.provider_name} is temporarily unavailable. Please try again later.")
        if response.status_code == 204:
            return None  # "No content": the request was fine but there is nothing to return
        if response.status_code != 200:
            raise RuntimeError(f"{self.provider_name} returned an unexpected status ({response.status_code}).")
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"{self.provider_name} returned an unreadable response.") from exc


class WeatherClient(APIClient):
    """OpenWeatherMap current-conditions client."""

    provider_name = "OpenWeatherMap"
    _key_param = "appid"

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        super().__init__("https://api.openweathermap.org/data/2.5", api_key, timeout)

    def current(self, city: str) -> LocationSnapshot:
        cleaned_city = city.strip()
        if not cleaned_city or len(cleaned_city) > 100 or not any(ch.isalpha() for ch in cleaned_city):
            raise ValueError("Enter a valid city name (1–100 characters, including a letter).")
        try:
            payload = self._get("weather", {"q": cleaned_city, "units": "metric"})
        except LookupError:
            raise LookupError(f"City '{cleaned_city}' was not found. Check the spelling and try again.") from None
        return snapshot_from_api(cleaned_city, payload)

    def current_many(self, cities: list[str]) -> tuple[list[LocationSnapshot], dict[str, str]]:
        """Fetch each location independently, returning successes and clear failures."""
        snapshots: list[LocationSnapshot] = []
        errors: dict[str, str] = {}
        for city in cities:
            try:
                snapshot = self.current(city)
                snapshots.append(snapshot)
            except (ValueError, LookupError, PermissionError, ConnectionError, RuntimeError) as exc:
                errors[city] = str(exc)
        return snapshots, errors


class AviationWeatherClient(APIClient):
    """aviationweather.gov (NOAA) client for METAR and TAF reports. Free and needs no key."""

    provider_name = "aviationweather.gov"

    def __init__(self, timeout: float = 10.0) -> None:
        super().__init__("https://aviationweather.gov/api/data", timeout=timeout)

    def metars(self, codes: list[str]) -> tuple[list[MetarReport], dict[str, str]]:
        """Latest observed weather for each airport, plus a message for each one that failed."""
        return self._fetch_reports("metar", codes, metar_from_api)

    def tafs(self, codes: list[str]) -> tuple[list[TafReport], dict[str, str]]:
        """Current official forecast for each airport, plus a message for each one that failed."""
        return self._fetch_reports("taf", codes, taf_from_api)

    def _fetch_reports(self, endpoint: str, codes: list[str], parse: Callable[[dict], Any]) -> tuple[list, dict[str, str]]:
        """One request for all valid codes. Invalid, unknown or unreadable airports are
        reported in the errors dict and skipped, so they never stop the others."""
        reports: list = []
        errors: dict[str, str] = {}
        valid_codes: list[str] = []
        for code in codes:
            try:
                cleaned = clean_icao_code(code)
            except ValueError as exc:
                errors[code] = str(exc)
                continue
            if cleaned not in valid_codes:
                valid_codes.append(cleaned)
        if not valid_codes:
            return reports, errors

        payload = self._get(endpoint, {"ids": ",".join(valid_codes), "format": "json"}) or []

        found: set[str] = set()
        for item in payload:
            code = item.get("icaoId", "?")
            if code in found:
                continue  # keep only the first (newest) report per airport
            try:
                reports.append(parse(item))
                found.add(code)
            except ValueError as exc:
                errors[code] = str(exc)
        for code in valid_codes:
            if code not in found and code not in errors:
                errors[code] = (
                    f"No {endpoint.upper()} available. The code may not exist, "
                    "or this airport does not publish one."
                )
        return reports, errors


class OpenMeteoClient(APIClient):
    """Open-Meteo forecast client for winds aloft. Free, no key, under 10,000 calls a day.

    Gives model wind and temperature at pressure levels (850 to 200 hPa), which we
    present as approximate flight levels. This is model data, not an official chart.
    """

    provider_name = "Open-Meteo"

    def __init__(self, timeout: float = 10.0) -> None:
        super().__init__("https://api.open-meteo.com/v1", timeout=timeout)

    def winds_at(self, latitude: float, longitude: float) -> list[WindLevel]:
        """Current model wind and temperature at each cruise height above one point, lowest first."""
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("Coordinates out of range (latitude −90 to 90, longitude −180 to 180).")
        variables = [
            f"{name}_{hpa}hPa"
            for hpa in FLIGHT_LEVELS
            for name in ("wind_speed", "wind_direction", "temperature")
        ]
        payload = self._get(
            "forecast",
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": ",".join(variables),
                "wind_speed_unit": "kn",
                "timezone": "GMT",
            },
        )
        return wind_levels_from_api(payload)
