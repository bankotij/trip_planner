from dataclasses import dataclass

from django.test import SimpleTestCase

from routing.services.fuel_planner import (
    estimate_fuel_gallons,
    estimate_total_cost,
    plan_stops,
)


@dataclass
class DummyStation:
    truckstop_name: str
    address: str
    city: str
    state: str
    retail_price: float
    lat: float
    lng: float


class FuelPlannerTests(SimpleTestCase):
    def test_estimate_fuel_gallons_handles_non_positive_mpg(self):
        self.assertEqual(estimate_fuel_gallons(100, mpg=0), 0.0)
        self.assertEqual(estimate_fuel_gallons(100, mpg=-5), 0.0)

    def test_plan_stops_selects_cheapest_in_window(self):
        stations = [
            {
                "station": DummyStation(
                    truckstop_name="A",
                    address="1 Main",
                    city="X",
                    state="CA",
                    retail_price=4.0,
                    lat=0.0,
                    lng=0.0,
                ),
                "at_route_mile": 470.0,
                "price_per_gallon": 4.0,
            },
            {
                "station": DummyStation(
                    truckstop_name="B",
                    address="2 Main",
                    city="Y",
                    state="CA",
                    retail_price=3.0,
                    lat=0.0,
                    lng=0.0,
                ),
                "at_route_mile": 490.0,
                "price_per_gallon": 3.0,
            },
            {
                "station": DummyStation(
                    truckstop_name="C",
                    address="3 Main",
                    city="Z",
                    state="CA",
                    retail_price=3.5,
                    lat=0.0,
                    lng=0.0,
                ),
                "at_route_mile": 900.0,
                "price_per_gallon": 3.5,
            },
        ]

        stops = plan_stops(distance_miles=1000, stations_with_milepoint=stations, range_miles=500)

        self.assertEqual(len(stops), 2)
        self.assertEqual(stops[0]["at_route_mile"], 490.0)
        self.assertEqual(stops[1]["at_route_mile"], 900.0)

    def test_plan_stops_returns_empty_when_infeasible(self):
        stations = [
            {
                "station": DummyStation(
                    truckstop_name="A",
                    address="1 Main",
                    city="X",
                    state="CA",
                    retail_price=4.0,
                    lat=0.0,
                    lng=0.0,
                ),
                "at_route_mile": 150.0,
                "price_per_gallon": 4.0,
            },
        ]

        stops = plan_stops(distance_miles=1000, stations_with_milepoint=stations, range_miles=200)

        self.assertEqual(stops, [])

    def test_estimate_total_cost_uses_stop_prices_per_segment(self):
        stops = [
            {"at_route_mile": 100.0, "price_per_gallon": 4.0},
            {"at_route_mile": 300.0, "price_per_gallon": 3.0},
        ]

        total_cost = estimate_total_cost(distance_miles=400, stops=stops, mpg=10)

        # Segment 1: 100 miles at $4 -> 10 gallons = 40
        # Segment 2: 200 miles at $3 -> 20 gallons = 60
        # Segment 3: 100 miles at $3 -> 10 gallons = 30
        self.assertAlmostEqual(total_cost, 130.0)
