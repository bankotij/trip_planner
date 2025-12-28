import math
from typing import List, Tuple, Set

import polyline as polyline_lib

from routing.models import FuelStation
from routing.services.ors import ORSClient, ReverseGeocodingError


# Constants
EARTH_RADIUS_MILES = 3958.8
MILES_PER_SAMPLE = 25
MAX_SAMPLED_POINTS = 200
MAX_DISTANCE_FROM_ROUTE_MILES = 10
MAX_REVERSE_GEOCODE_CALLS = 10
MAX_STATIONS_TO_CONSIDER = 1500

# US state name to abbreviation mapping
STATE_NAME_TO_ABBREV = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
    "District of Columbia": "DC",
}


def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate the great-circle distance between two points in miles.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_MILES * c


def decode_polyline(encoded: str) -> List[Tuple[float, float]]:
    """
    Decode an encoded polyline string to a list of (lat, lng) tuples.
    """
    return polyline_lib.decode(encoded)


def sample_route_points(
    route_points: List[Tuple[float, float]],
    miles_per_sample: float = MILES_PER_SAMPLE,
    max_points: int = MAX_SAMPLED_POINTS,
) -> List[Tuple[float, float]]:
    """
    Sample route points approximately every N miles.
    Always includes start and end points.
    Caps output to max_points by downsampling if needed.
    """
    if not route_points:
        return []

    if len(route_points) == 1:
        return list(route_points)

    # Sample by distance
    sampled = [route_points[0]]
    accumulated_distance = 0.0
    prev_point = route_points[0]

    for point in route_points[1:]:
        distance = haversine_distance(prev_point[0], prev_point[1], point[0], point[1])
        accumulated_distance += distance

        if accumulated_distance >= miles_per_sample:
            sampled.append(point)
            accumulated_distance = 0.0

        prev_point = point

    # Always include the last point
    if sampled[-1] != route_points[-1]:
        sampled.append(route_points[-1])

    # Downsample if exceeds max_points
    if len(sampled) > max_points:
        step = len(sampled) / max_points
        indices = [int(i * step) for i in range(max_points - 1)]
        # Always include last point
        if len(sampled) - 1 not in indices:
            indices.append(len(sampled) - 1)
        sampled = [sampled[i] for i in indices]

    return sampled


def normalize_state(state: str) -> str:
    """
    Normalize state name to USPS two-letter abbreviation.
    If already an abbreviation or not found, return as-is.
    """
    if not state:
        return state

    # Check if it's a full state name
    if state in STATE_NAME_TO_ABBREV:
        return STATE_NAME_TO_ABBREV[state]

    # Already an abbreviation or unknown, return as-is
    return state


def get_route_states(
    ors: ORSClient,
    sampled_points: List[Tuple[float, float]],
    max_calls: int = MAX_REVERSE_GEOCODE_CALLS,
) -> Set[str]:
    """
    Reverse geocode sampled route points to determine which states the route passes through.
    Limited to max_calls API requests.
    Normalizes state names to USPS abbreviations.

    Returns:
        Set of normalized state abbreviations
    """
    states = set()

    if not sampled_points:
        return states

    # Evenly sample points for reverse geocoding
    if len(sampled_points) <= max_calls:
        points_to_check = sampled_points
    else:
        step = len(sampled_points) / max_calls
        indices = [int(i * step) for i in range(max_calls)]
        points_to_check = [sampled_points[i] for i in indices]

    for lat, lng in points_to_check:
        try:
            result = ors.reverse_geocode(lat, lng)
            state = result.get("state")
            if state:
                normalized = normalize_state(state)
                states.add(normalized)
        except ReverseGeocodingError:
            # Skip points that fail reverse geocoding
            continue

    return states


def min_distance_to_route(
    station_lat: float,
    station_lng: float,
    sampled_points: List[Tuple[float, float]],
) -> float:
    """
    Calculate the minimum distance from a station to any sampled route point.
    """
    if not sampled_points:
        return float("inf")

    return min(
        haversine_distance(station_lat, station_lng, point[0], point[1])
        for point in sampled_points
    )


def _filter_stations_near_route(
    stations_qs,
    sampled_points: List[Tuple[float, float]],
    max_distance_miles: float,
) -> List[FuelStation]:
    """
    Filter stations to those near the route.

    Args:
        stations_qs: QuerySet of stations (must already have coords)
        sampled_points: Sampled route points
        max_distance_miles: Max distance from route

    Returns:
        List of FuelStation objects near the route
    """
    candidate_stations = []
    for station in stations_qs.iterator(chunk_size=1000):
        distance = min_distance_to_route(station.lat, station.lng, sampled_points)
        if distance <= max_distance_miles:
            candidate_stations.append(station)

    return candidate_stations


def find_candidate_stations(
    ors: ORSClient,
    geometry_polyline: str,
    max_distance_miles: float = MAX_DISTANCE_FROM_ROUTE_MILES,
) -> Tuple[List[FuelStation], List[Tuple[float, float]]]:
    """
    Find fuel stations near the route.

    Only considers stations that already have lat/lng coordinates.
    Geocoding must be done offline via the geocode_missing_stations management command.

    Steps:
    1. Decode polyline to route points
    2. Sample route points every ~25 miles (capped at 200)
    3. Reverse geocode to find states the route passes through
    4. Filter stations by those states, only those with coords
    5. Limit pool to top 1500 cheapest stations (for performance)
    6. Filter stations within max_distance_miles of the route
    7. Fallback: if state filtering yields zero, retry without state filter

    Returns:
        Tuple of (List of FuelStation objects near the route, sampled route points)
    """
    # Step 1: Decode polyline
    route_points = decode_polyline(geometry_polyline)

    if not route_points:
        return [], []

    # Step 2: Sample route points
    sampled_points = sample_route_points(route_points)

    if not sampled_points:
        return [], []

    # Step 3: Get states along the route
    route_states = get_route_states(ors, sampled_points)

    # Step 4: Build base queryset - only stations WITH coordinates
    base_qs = FuelStation.objects.filter(lat__isnull=False, lng__isnull=False)

    # Check if we have any geocoded stations
    total_with_coords = base_qs.count()
    if total_with_coords == 0:
        return [], sampled_points

    # Apply state filter if we found states
    if route_states:
        stations_qs = base_qs.filter(state__in=route_states)
    else:
        stations_qs = base_qs

    # Step 5: Limit pool to cheapest stations for performance
    stations_qs = stations_qs.order_by("retail_price")[:MAX_STATIONS_TO_CONSIDER]

    # Step 6: Filter by distance to route
    candidate_stations = _filter_stations_near_route(
        stations_qs, sampled_points, max_distance_miles
    )

    # Step 7: Fallback - if state filtering yielded zero, retry without state filter
    if not candidate_stations and route_states and total_with_coords > 0:
        stations_qs = base_qs.order_by("retail_price")[:MAX_STATIONS_TO_CONSIDER]
        candidate_stations = _filter_stations_near_route(
            stations_qs, sampled_points, max_distance_miles
        )

    return candidate_stations, sampled_points
