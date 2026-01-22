# Trip Planner

## 1. Project Overview
Trip Planner is a Django service that builds a fuel-stop plan for a road trip. It
uses OpenRouteService (ORS) for geocoding and directions, then finds nearby fuel
stations and selects cost-effective stops based on vehicle range.

Intentionally out of scope:
- Real-time traffic or dynamic pricing updates.
- Multi-vehicle fleets or scheduling.
- Authentication or user accounts.

## 2. Architecture & Data Flow
Components:
- `routing/views.py`: REST endpoints (`/plan`, `/health`).
- `routing/services/ors.py`: ORS API client.
- `routing/services/geo.py`: route decoding, sampling, station filtering.
- `routing/services/fuel_planner.py`: stop selection and cost estimation.
- `routing/models.py`: `FuelStation` storage.

ASCII diagram:
```
Client
  |
  v
Django REST view (/plan)
  |
  v
ORS client (geocode + directions)
  |
  v
Route sampling + station filtering
  |
  v
Stop planning + cost estimation
  |
  v
Response JSON
```

Primary execution path:
1. Validate request payload with `PlanRequestSerializer`.
2. Geocode start/end and fetch a route polyline from ORS.
3. Sample route points and filter nearby fuel stations.
4. Plan stops based on range constraints and price.
5. Return route summary, stops, and cost estimate.

## 3. Design Principles
1. **Deterministic planning** → stop selection is rule-based and repeatable.
2. **Bounded external calls** → ORS reverse geocoding is capped by `MAX_REVERSE_GEOCODE_CALLS`.
3. **Data locality** → fuel stations are stored locally and filtered by route.

## 4. Critical Workflows
**Trip planning request**
1. Geocode start/end.
2. Fetch driving route and total distance.
3. Sample route points (~25 miles apart, capped).
4. Filter stations near the route and within relevant states.
5. Select stops to keep each leg within vehicle range.

State, retries, and recovery:
- Station data is persisted in SQLite; no automatic retries for ORS calls.
- If no feasible stops are found, an empty plan is returned.

## 5. Failure Modes & Guarantees
- **ORS geocode failure** → 400 with a specific error message.
- **ORS directions failure** → 502 with a specific error message.
- **No geocoded stations** → empty `stops`, cost `null`.
- **Infeasible route** → empty `stops`, cost `null`.

Guarantees:
- Best-effort planning based on available station data.
- No guarantee of optimality beyond the implemented heuristic.

## 6. Testing Strategy
Tested:
- Fuel planning logic: stop selection, infeasible routes, cost calculations.

Not tested:
- ORS client integration or end-to-end API calls.
- Database ingestion of station data.

## 7. Tradeoffs & Alternatives
- **Heuristic stop selection vs global optimization**: faster and simpler but not globally optimal.
- **SQLite default**: easy local setup but not tuned for large datasets.

## 8. Operational Considerations
- Logging: default Django logging only.
- Metrics: none.
- Debugging: validate ORS_API_KEY, inspect station counts, and review planner output.
- Risk: insufficient geocoded stations yields empty plans.

## 9. Running Locally
Prereqs: Python 3.11, ORS API key.

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py load_fuel_csv --path data/fuel-prices-for-be-assessment.csv
export ORS_API_KEY=your_key
python manage.py runserver
```

## 10. Scope & Limitations
- Depends on ORS availability and API quotas.
- Fuel pricing is static at load time.
- No persistence of user trips or history.
