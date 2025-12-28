"""
Fuel stop planning module.

Provides functions to plan fuel stops along a route based on vehicle range,
station locations, and fuel prices.
"""

from typing import List, Tuple, Dict, Any, Optional

from routing.models import FuelStation
from routing.services.geo import haversine_distance


# Default vehicle constants
DEFAULT_RANGE_MILES = 500
DEFAULT_MPG = 10

# Stop planning constants
STOP_INTERVAL_MILES = 480  # Target stop every 480 miles (leaving 20 mile buffer)
WINDOW_NARROW_MILES = 60   # First try ±60 miles from target
WINDOW_WIDE_MILES = 120    # Fallback to ±120 miles
PREFERRED_FORWARD_RATIO = 0.6  # Prefer stations at least 60% of range ahead


def estimate_fuel_gallons(distance_miles: float, mpg: float = DEFAULT_MPG) -> float:
    """
    Estimate total fuel needed for a given distance.

    Args:
        distance_miles: Total trip distance in miles
        mpg: Miles per gallon fuel efficiency

    Returns:
        Estimated gallons of fuel needed
    """
    if mpg <= 0:
        return 0.0
    return distance_miles / mpg


def compute_route_mile_markers(
    route_points: List[Tuple[float, float]]
) -> List[float]:
    """
    Compute cumulative mile markers for each route point.

    Args:
        route_points: List of (lat, lng) tuples representing the route

    Returns:
        List of cumulative miles at each point (first point = 0.0)
    """
    if not route_points:
        return []

    mile_markers = [0.0]
    cumulative = 0.0

    for i in range(1, len(route_points)):
        prev = route_points[i - 1]
        curr = route_points[i]
        distance = haversine_distance(prev[0], prev[1], curr[0], curr[1])
        cumulative += distance
        mile_markers.append(cumulative)

    return mile_markers


def attach_station_milepoint(
    stations: List[FuelStation],
    route_points: List[Tuple[float, float]],
    route_miles: List[float],
) -> List[Dict[str, Any]]:
    """
    For each station, find the nearest route point and assign the mile marker.

    Args:
        stations: List of FuelStation objects with lat/lng
        route_points: List of (lat, lng) tuples representing the sampled route
        route_miles: Cumulative mile markers for each route point

    Returns:
        List of dicts with:
            - station: FuelStation object
            - at_route_mile: float (mile marker of nearest route point)
            - price_per_gallon: float (station's retail price)
    """
    if not route_points or not route_miles:
        return []

    stations_with_milepoint = []

    for station in stations:
        if station.lat is None or station.lng is None:
            continue

        # Find nearest route point by haversine distance
        min_dist = float("inf")
        nearest_idx = 0

        for i, (lat, lng) in enumerate(route_points):
            dist = haversine_distance(station.lat, station.lng, lat, lng)
            if dist < min_dist:
                min_dist = dist
                nearest_idx = i

        stations_with_milepoint.append({
            "station": station,
            "at_route_mile": route_miles[nearest_idx],
            "price_per_gallon": float(station.retail_price),
        })

    return stations_with_milepoint


def plan_stops(
    distance_miles: float,
    stations_with_milepoint: List[Dict[str, Any]],
    range_miles: float = DEFAULT_RANGE_MILES,
) -> List[Dict[str, Any]]:
    """
    Plan fuel stops along the route ensuring the vehicle never exceeds its range.

    Strategy:
    1. Create target milepoints at 480, 960, 1440, ... until < distance_miles
    2. For each target:
       a. Try narrow window (±60 miles) for cheapest feasible station
       b. If none, try wide window (±120 miles)
       c. If still none, fallback to any reachable station (cheapest ahead within range)
       d. If no reachable station exists, return empty list (infeasible)
    3. After all targets, verify last leg is feasible (distance - last_stop <= range)
       If not, add one more stop using reachable station logic
    4. Ensure all stops are strictly increasing and within range constraints

    Args:
        distance_miles: Total route distance
        stations_with_milepoint: List of station dicts with at_route_mile and price_per_gallon
        range_miles: Vehicle range in miles

    Returns:
        List of planned stop dicts, or empty list if no feasible plan exists
    """
    if not stations_with_milepoint or distance_miles <= 0:
        return []

    # If trip is shorter than range, no stops needed
    if distance_miles <= range_miles:
        return []

    # Generate target milepoints
    targets = []
    target = STOP_INTERVAL_MILES
    while target < distance_miles:
        targets.append(target)
        target += STOP_INTERVAL_MILES

    if not targets:
        # Trip is short enough to not need stops
        return []

    planned_stops = []
    last_stop_mile = 0.0

    for target_mile in targets:
        # Skip target if we've already passed it
        if target_mile <= last_stop_mile:
            continue

        # Try narrow window first
        best_station = _find_feasible_cheapest_in_window(
            stations_with_milepoint,
            target_mile,
            WINDOW_NARROW_MILES,
            last_stop_mile,
            range_miles,
        )

        # Try wide window if narrow failed
        if best_station is None:
            best_station = _find_feasible_cheapest_in_window(
                stations_with_milepoint,
                target_mile,
                WINDOW_WIDE_MILES,
                last_stop_mile,
                range_miles,
            )

        # Fallback: any reachable station ahead (cheapest)
        if best_station is None:
            best_station = _find_any_reachable_cheapest(
                stations_with_milepoint,
                last_stop_mile,
                range_miles,
                distance_miles,
            )

        # If still no station found, plan is infeasible
        if best_station is None:
            return []

        station = best_station["station"]
        at_mile = best_station["at_route_mile"]

        # Sanity check: ensure within route
        if at_mile > distance_miles:
            continue

        planned_stops.append({
            "sequence": len(planned_stops) + 1,
            "name": station.truckstop_name,
            "address": station.address,
            "city": station.city,
            "state": station.state,
            "price_per_gallon": float(station.retail_price),
            "lat": station.lat,
            "lng": station.lng,
            "at_route_mile": round(at_mile, 2),
        })

        last_stop_mile = at_mile

    # Verify last leg is feasible
    if planned_stops:
        last_stop_mile = planned_stops[-1]["at_route_mile"]
    else:
        last_stop_mile = 0.0

    remaining_distance = distance_miles - last_stop_mile

    # If last leg exceeds range, we need another stop
    while remaining_distance > range_miles:
        additional_stop = _find_any_reachable_cheapest(
            stations_with_milepoint,
            last_stop_mile,
            range_miles,
            distance_miles,
        )

        if additional_stop is None:
            # Cannot complete the trip - infeasible
            return []

        station = additional_stop["station"]
        at_mile = additional_stop["at_route_mile"]

        # Ensure we're making progress
        if at_mile <= last_stop_mile:
            return []

        planned_stops.append({
            "sequence": len(planned_stops) + 1,
            "name": station.truckstop_name,
            "address": station.address,
            "city": station.city,
            "state": station.state,
            "price_per_gallon": float(station.retail_price),
            "lat": station.lat,
            "lng": station.lng,
            "at_route_mile": round(at_mile, 2),
        })

        last_stop_mile = at_mile
        remaining_distance = distance_miles - last_stop_mile

    # Re-sequence all stops
    for i, stop in enumerate(planned_stops, start=1):
        stop["sequence"] = i

    return planned_stops


def _find_feasible_cheapest_in_window(
    stations_with_milepoint: List[Dict[str, Any]],
    target_mile: float,
    window_miles: float,
    last_stop_mile: float,
    range_miles: float,
) -> Optional[Dict[str, Any]]:
    """
    Find the cheapest station within a window that is also within vehicle range.

    Args:
        stations_with_milepoint: List of station dicts
        target_mile: Target milepoint
        window_miles: Window size (±miles from target)
        last_stop_mile: Milepoint of previous stop (or 0 for start)
        range_miles: Maximum distance from last stop

    Returns:
        Best feasible station dict or None if not found
    """
    # Filter candidates within window, after last stop, and within range
    candidates = [
        s for s in stations_with_milepoint
        if (target_mile - window_miles) <= s["at_route_mile"] <= (target_mile + window_miles)
        and s["at_route_mile"] > last_stop_mile
        and (s["at_route_mile"] - last_stop_mile) <= range_miles
    ]

    if not candidates:
        return None

    # Sort by price (cheapest first)
    candidates.sort(key=lambda s: s["price_per_gallon"])

    return candidates[0]


def _find_any_reachable_cheapest(
    stations_with_milepoint: List[Dict[str, Any]],
    last_stop_mile: float,
    range_miles: float,
    max_mile: float,
) -> Optional[Dict[str, Any]]:
    """
    Find the cheapest reachable station ahead of current position.

    Prefers stations that are at least 60% of range ahead to avoid stopping too early.
    Falls back to any reachable station if none exist in the preferred forward band.

    A station is reachable if:
    - at_route_mile > last_stop_mile (ahead)
    - at_route_mile - last_stop_mile <= range_miles (within range)
    - at_route_mile <= max_mile (within route)

    Args:
        stations_with_milepoint: List of station dicts
        last_stop_mile: Current position (milepoint of last stop or 0)
        range_miles: Maximum distance we can travel
        max_mile: Maximum milepoint (usually distance_miles)

    Returns:
        Cheapest reachable station dict or None if none found
    """
    # All reachable stations
    all_reachable = [
        s for s in stations_with_milepoint
        if s["at_route_mile"] > last_stop_mile
        and (s["at_route_mile"] - last_stop_mile) <= range_miles
        and s["at_route_mile"] <= max_mile
    ]

    if not all_reachable:
        return None

    # Preferred: stations at least 60% of range ahead
    min_preferred_mile = last_stop_mile + (PREFERRED_FORWARD_RATIO * range_miles)
    preferred = [
        s for s in all_reachable
        if s["at_route_mile"] >= min_preferred_mile
    ]

    # Use preferred candidates if available, otherwise fall back to all reachable
    candidates = preferred if preferred else all_reachable

    # Sort by price (cheapest first)
    candidates.sort(key=lambda s: s["price_per_gallon"])

    return candidates[0]


def estimate_total_cost(
    distance_miles: float,
    stops: List[Dict[str, Any]],
    mpg: float = DEFAULT_MPG,
) -> Optional[float]:
    """
    Estimate total fuel cost for the trip.

    Splits the route into segments between stops and calculates cost based on
    the fuel price at each stop.

    Segment boundaries and pricing:
    - Segment 1: start (0) -> stop1.at_route_mile, uses stop1's price
    - Segment 2: stop1 -> stop2, uses stop2's price
    - ...
    - Last segment: last_stop -> end (distance_miles), uses last_stop's price

    Args:
        distance_miles: Total route distance
        stops: List of planned stop dicts with price_per_gallon and at_route_mile
        mpg: Miles per gallon

    Returns:
        Estimated total cost in USD, or None if no stops
    """
    if not stops or mpg <= 0:
        return None

    total_cost = 0.0

    # Segment from start to first stop (uses first stop's price)
    first_stop = stops[0]
    first_segment_miles = first_stop["at_route_mile"]
    first_segment_gallons = first_segment_miles / mpg
    total_cost += first_segment_gallons * first_stop["price_per_gallon"]

    # Segments between stops (each uses the destination stop's price)
    for i in range(1, len(stops)):
        prev_stop = stops[i - 1]
        curr_stop = stops[i]
        segment_miles = curr_stop["at_route_mile"] - prev_stop["at_route_mile"]
        segment_gallons = segment_miles / mpg
        total_cost += segment_gallons * curr_stop["price_per_gallon"]

    # Segment from last stop to end (uses last stop's price)
    last_stop = stops[-1]
    last_segment_miles = distance_miles - last_stop["at_route_mile"]
    if last_segment_miles > 0:
        last_segment_gallons = last_segment_miles / mpg
        total_cost += last_segment_gallons * last_stop["price_per_gallon"]

    return total_cost
