import requests

ORS_GEOCODE_URL = "https://api.openrouteservice.org/geocode/search"
ORS_REVERSE_GEOCODE_URL = "https://api.openrouteservice.org/geocode/reverse"
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"

METERS_TO_MILES = 0.000621371
REQUEST_TIMEOUT = 10


class ORSError(Exception):
    """Base exception for ORS errors."""
    pass


class GeocodingError(ORSError):
    """Raised when geocoding fails."""
    pass


class ReverseGeocodingError(ORSError):
    """Raised when reverse geocoding fails."""
    pass


class DirectionsError(ORSError):
    """Raised when directions request fails."""
    pass


class ORSClient:
    def __init__(self, api_key: str):
        self.api_key = api_key

    def geocode_text(self, query: str) -> dict:
        """
        Geocode a text query to coordinates.

        Returns:
            dict with keys: label, lat, lng
        Raises:
            GeocodingError if no results found or request fails
        """
        try:
            response = requests.get(
                ORS_GEOCODE_URL,
                params={"api_key": self.api_key, "text": query},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise GeocodingError(f"Geocoding request failed: {e}")

        data = response.json()
        features = data.get("features", [])

        if not features:
            raise GeocodingError(f"No results found for: {query}")

        feature = features[0]
        coords = feature.get("geometry", {}).get("coordinates", [])
        properties = feature.get("properties", {})

        if len(coords) < 2:
            raise GeocodingError(f"Invalid coordinates for: {query}")

        return {
            "label": properties.get("label", query),
            "lat": coords[1],
            "lng": coords[0],
        }

    def reverse_geocode(self, lat: float, lng: float) -> dict:
        """
        Reverse geocode coordinates to location info.

        Returns:
            dict with keys: state, country (state may be None)
        Raises:
            ReverseGeocodingError if request fails
        """
        try:
            response = requests.get(
                ORS_REVERSE_GEOCODE_URL,
                params={
                    "api_key": self.api_key,
                    "point.lat": lat,
                    "point.lon": lng,
                    "size": 1,
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise ReverseGeocodingError(f"Reverse geocoding request failed: {e}")

        data = response.json()
        features = data.get("features", [])

        if not features:
            raise ReverseGeocodingError(f"No results for coordinates: {lat}, {lng}")

        properties = features[0].get("properties", {})
        return {
            "state": properties.get("region"),
            "country": properties.get("country"),
        }

    def directions(
        self, start_lat: float, start_lng: float, end_lat: float, end_lng: float
    ) -> dict:
        """
        Get driving directions between two points.

        Returns:
            dict with keys: distance_miles, geometry_polyline
        Raises:
            DirectionsError if request fails
        """
        try:
            response = requests.post(
                ORS_DIRECTIONS_URL,
                json={
                    "coordinates": [[start_lng, start_lat], [end_lng, end_lat]],
                },
                headers={
                    "Authorization": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            raise DirectionsError(f"Directions request failed: {e}")

        data = response.json()
        routes = data.get("routes", [])

        if not routes:
            raise DirectionsError("No route found")

        route = routes[0]
        summary = route.get("summary", {})
        distance_meters = summary.get("distance", 0)
        geometry = route.get("geometry", "")

        return {
            "distance_miles": round(distance_meters * METERS_TO_MILES, 2),
            "geometry_polyline": geometry,
        }

