# Trip Planner

A Django-based trip planner that calculates optimal fuel stops along a route, minimizing fuel costs based on real station prices.

## Features

- Plan trips between any two US locations
- Find fuel stations along the route
- Optimize fuel stops based on price and vehicle range
- Interactive map showing route and fuel stops
- Estimate total fuel cost for the trip

## Prerequisites

- Python 3.10+
- OpenRouteService API key (free at https://openrouteservice.org/)

## Setup

### 1. Create virtual environment and install dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```
SECRET_KEY=your-django-secret-key
DEBUG=True
ORS_API_KEY=your-openrouteservice-api-key
```

### 3. Run migrations

```bash
python manage.py migrate
```

### 4. Load fuel station data

```bash
python manage.py load_fuel_csv data/fuel-prices-for-be-assessment.csv
```

This imports fuel station data from the CSV file.

### 5. Geocode fuel stations (required for planning)

The API requires stations to have lat/lng coordinates. Geocode them in batches:

```bash
# Geocode 500 stations (default)
python manage.py geocode_missing_stations

# Geocode more stations
python manage.py geocode_missing_stations --limit 1000

# Geocode specific states first (for targeted routes)
python manage.py geocode_missing_stations --state TX --state FL --state LA --limit 500

# Adjust rate limit if needed (default 0.2s between calls)
python manage.py geocode_missing_stations --limit 500 --rate-limit 0.3
```

**Note:** The free ORS tier has rate limits. Run this command multiple times if you have many stations.

### 6. Run the development server

```bash
python manage.py runserver
```

Visit http://localhost:8000 to use the trip planner.

## API Endpoints

### GET /health/

Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

### POST /api/plan

Plan a trip with optimal fuel stops.

**Request:**
```json
{
  "start": "Miami, FL",
  "end": "Austin, TX"
}
```

**Response:**
```json
{
  "route": {
    "distance_miles": 1312.5,
    "geometry_polyline": "encoded_polyline...",
    "candidates_count": 42
  },
  "vehicle": {
    "range_miles": 500,
    "mpg": 10
  },
  "stops": [
    {
      "sequence": 1,
      "name": "Pilot Travel Center",
      "address": "123 Highway Rd",
      "city": "Tallahassee",
      "state": "FL",
      "price_per_gallon": 3.299,
      "lat": 30.4383,
      "lng": -84.2807,
      "at_route_mile": 478.2
    }
  ],
  "totals": {
    "fuel_gallons": 131.25,
    "estimated_cost_usd": 432.81
  }
}
```

## Project Structure

```
trip_planner/
├── routing/
│   ├── management/commands/    # Management commands
│   │   ├── load_fuel_csv.py    # Import fuel station CSV
│   │   └── geocode_missing_stations.py  # Geocode stations
│   ├── services/
│   │   ├── ors.py              # OpenRouteService client
│   │   ├── geo.py              # Geographic utilities
│   │   └── fuel_planner.py     # Fuel stop planning logic
│   ├── models.py               # FuelStation model
│   ├── serializers.py          # DRF serializers
│   └── views.py                # API views
├── templates/
│   └── index.html              # Frontend UI
├── trip_planner/
│   ├── settings.py
│   └── urls.py
├── data/                       # CSV data files
├── requirements.txt
└── README.md
```

## Development Notes

- Vehicle defaults: 500 mile range, 10 MPG (configurable in code)
- Fuel stop planning uses a greedy algorithm targeting stops every ~480 miles
- Stations are filtered to within 10 miles of the route
- Only the 1500 cheapest stations in route states are considered
