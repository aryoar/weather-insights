"""Great-circle route geometry: distance, evenly spaced points, and the map area around a route.

Aircraft fly (roughly) along great circles: the shortest path between two points on a sphere.
On a flat map that path looks curved, so we draw it as many short straight pieces between
points calculated here. All maths uses a spherical Earth, which is accurate to well under 1%.
"""

import math

EARTH_RADIUS_NM = 3440.065  # mean Earth radius in nautical miles
KM_PER_NM = 1.852
NM_PER_DEGREE_LAT = 60.0     # one degree of latitude is (almost exactly) 60 nautical miles


def _check_coordinates(lat: float, lon: float) -> None:
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError(f"Coordinates ({lat}, {lon}) are outside the valid range")


def great_circle_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Shortest distance over the Earth's surface, in nautical miles (haversine formula)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(min(1.0, math.sqrt(a)))


class Route:
    """A direct great-circle route between two airports."""

    def __init__(self, origin: str, destination: str,
                 start: tuple[float, float], end: tuple[float, float]) -> None:
        for lat, lon in (start, end):
            _check_coordinates(lat, lon)
        self.origin = origin
        self.destination = destination
        self.start = (float(start[0]), float(start[1]))  # (latitude, longitude)
        self.end = (float(end[0]), float(end[1]))
        if self.distance_nm < 1:
            raise ValueError("Departure and destination must be two different airports.")

    @property
    def distance_nm(self) -> float:
        return great_circle_nm(*self.start, *self.end)

    @property
    def distance_km(self) -> float:
        return self.distance_nm * KM_PER_NM

    def _point_at(self, fraction: float) -> tuple[float, float]:
        """The point a given fraction (0 = start, 1 = end) of the way along the great circle."""
        lat1, lon1 = map(math.radians, self.start)
        lat2, lon2 = map(math.radians, self.end)
        angle = self.distance_nm / EARTH_RADIUS_NM  # angular distance in radians
        a = math.sin((1 - fraction) * angle) / math.sin(angle)
        b = math.sin(fraction * angle) / math.sin(angle)
        x = a * math.cos(lat1) * math.cos(lon1) + b * math.cos(lat2) * math.cos(lon2)
        y = a * math.cos(lat1) * math.sin(lon1) + b * math.cos(lat2) * math.sin(lon2)
        z = a * math.sin(lat1) + b * math.sin(lat2)
        return math.degrees(math.atan2(z, math.hypot(x, y))), math.degrees(math.atan2(y, x))

    def points(self, count: int) -> list[tuple[float, float]]:
        """`count` evenly spaced (lat, lon) points, including departure and destination."""
        if count < 2:
            raise ValueError("A route needs at least 2 points (departure and destination).")
        return [self._point_at(i / (count - 1)) for i in range(count)]

    def distance_from_route_nm(self, lat: float, lon: float, samples: int = 100) -> float:
        """Approximate distance from a position to the nearest part of the route.

        Measures to `samples` points along the route; with 100 samples the error is at most
        half the gap between samples (about 3 nm on a 700 nm route).
        """
        return min(great_circle_nm(lat, lon, p_lat, p_lon) for p_lat, p_lon in self.points(samples))

    @property
    def crosses_antimeridian(self) -> bool:
        """True if the route crosses the 180° line (e.g. Tokyo to Los Angeles), where longitudes jump."""
        path = self.points(100)
        return any(abs(b[1] - a[1]) > 180 for a, b in zip(path, path[1:]))

    def bounding_box(self, margin_nm: float = 0) -> tuple[float, float, float, float]:
        """(min_lat, min_lon, max_lat, max_lon) around the whole curved route, plus a margin."""
        path = self.points(100)
        lats = [lat for lat, _ in path]
        lons = [lon for _, lon in path]
        lat_margin = margin_nm / NM_PER_DEGREE_LAT
        # A degree of longitude gets shorter towards the poles, so the margin needs more degrees.
        widest_lat = min(max(abs(min(lats)), abs(max(lats))) + lat_margin, 89.0)
        lon_margin = margin_nm / (NM_PER_DEGREE_LAT * math.cos(math.radians(widest_lat)))
        return (
            max(min(lats) - lat_margin, -90.0),
            max(min(lons) - lon_margin, -180.0),
            min(max(lats) + lat_margin, 90.0),
            min(max(lons) + lon_margin, 180.0),
        )

    def __str__(self) -> str:
        return f"{self.origin} → {self.destination} ({self.distance_nm:,.0f} nm)"

    def __repr__(self) -> str:
        return f"Route({self.origin!r}, {self.destination!r}, {self.distance_nm:.0f} nm)"
