"""Generic JSON API behavior and the OpenWeatherMap implementation."""

from typing import Any

import requests

from .models import LocationSnapshot, snapshot_from_api


class APIClient:
    """Reusable JSON GET client with explicit timeout and status handling."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.base_url}/{endpoint.lstrip('/')}",
                params=params,
                timeout=self._timeout,
            )
        except requests.Timeout as exc:
            raise ConnectionError("The weather service timed out. Please try again.") from exc
        except requests.RequestException as exc:
            raise ConnectionError("Could not reach the weather service. Check your connection.") from exc

        if response.status_code == 401:
            raise PermissionError("The OpenWeatherMap API key is invalid or inactive.")
        if response.status_code == 404:
            raise LookupError("Location not found. Check the city name and try again.")
        if response.status_code >= 500:
            raise RuntimeError("OpenWeatherMap is temporarily unavailable. Please try again later.")
        if response.status_code != 200:
            raise RuntimeError(f"OpenWeatherMap returned an unexpected status ({response.status_code}).")
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("OpenWeatherMap returned an unreadable response.") from exc


class WeatherClient(APIClient):
    """OpenWeatherMap current-conditions client."""

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        super().__init__("https://api.openweathermap.org/data/2.5", api_key, timeout)

    def current(self, city: str) -> LocationSnapshot:
        cleaned_city = city.strip()
        if not cleaned_city or len(cleaned_city) > 100 or not any(ch.isalpha() for ch in cleaned_city):
            raise ValueError("Enter a valid city name (1–100 characters, including a letter).")
        payload = self._get(
            "weather",
            {"q": cleaned_city, "appid": self._api_key, "units": "metric"},
        )
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
