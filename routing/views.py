from django.conf import settings
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response

from routing.serializers import PlanRequestSerializer
from routing.services.ors import ORSClient, GeocodingError, DirectionsError
from routing.services.geo import find_candidate_stations
from routing.services.fuel_planner import (
    estimate_fuel_gallons,
    compute_route_mile_markers,
    attach_station_milepoint,
    plan_stops,
    estimate_total_cost,
)


def index(request):
    """Serve the frontend page."""
    return render(request, "index.html")


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["POST"])
def plan_trip(request):
    serializer = PlanRequestSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)

    # Check for API key
    api_key = settings.ORS_API_KEY
    if not api_key:
        return Response(
            {"error": "ORS_API_KEY is not configured"},
            status=500,
        )

    ors = ORSClient(api_key)
    validated = serializer.validated_data

    # Geocode start and end
    try:
        start_geo = ors.geocode_text(validated["start"])
    except GeocodingError as e:
        return Response(
            {"error": f"Failed to geocode start location: {e}"},
            status=400,
        )

    try:
        end_geo = ors.geocode_text(validated["end"])
    except GeocodingError as e:
        return Response(
            {"error": f"Failed to geocode end location: {e}"},
            status=400,
        )

    # Get directions
    try:
        route_data = ors.directions(
            start_geo["lat"],
            start_geo["lng"],
            end_geo["lat"],
            end_geo["lng"],
        )
    except DirectionsError as e:
        return Response(
            {"error": f"Failed to get directions: {e}"},
            status=502,
        )

    distance_miles = route_data["distance_miles"]
    geometry_polyline = route_data["geometry_polyline"]

    # Find candidate fuel stations near the route
    candidates, sampled_points = find_candidate_stations(ors, geometry_polyline)

    # Vehicle parameters
    range_miles = 500
    mpg = 10

    # Compute fuel needs
    fuel_gallons = estimate_fuel_gallons(distance_miles, mpg)

    # Plan fuel stops
    if candidates and sampled_points:
        # Compute mile markers for sampled route points
        route_miles = compute_route_mile_markers(sampled_points)

        # Attach milepoint to each station
        stations_with_milepoint = attach_station_milepoint(
            candidates, sampled_points, route_miles
        )

        # Plan the stops
        planned_stops = plan_stops(distance_miles, stations_with_milepoint, range_miles)

        # Estimate total cost
        estimated_cost = estimate_total_cost(distance_miles, planned_stops, mpg)
    else:
        planned_stops = []
        estimated_cost = None

    return Response({
        "route": {
            "distance_miles": distance_miles,
            "geometry_polyline": geometry_polyline,
            "candidates_count": len(candidates),
        },
        "vehicle": {
            "range_miles": range_miles,
            "mpg": mpg,
        },
        "stops": planned_stops,
        "totals": {
            "fuel_gallons": round(fuel_gallons, 2),
            "estimated_cost_usd": round(estimated_cost, 2) if estimated_cost is not None else None,
        },
    })
