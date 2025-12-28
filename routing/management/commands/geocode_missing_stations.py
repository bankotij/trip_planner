"""
Management command to geocode fuel stations missing lat/lng coordinates.

This should be run offline before using /api/plan for fast responses.
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from routing.models import FuelStation
from routing.services.ors import ORSClient, GeocodingError


class Command(BaseCommand):
    help = "Geocode fuel stations that are missing lat/lng coordinates"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="Maximum number of stations to geocode (default: 500)",
        )
        parser.add_argument(
            "--state",
            action="append",
            dest="states",
            help="Filter by state (can be repeated, e.g. --state TX --state FL)",
        )
        parser.add_argument(
            "--rate-limit",
            type=float,
            default=0.2,
            help="Seconds to sleep between API calls (default: 0.2)",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        states = options["states"]
        rate_limit = options["rate_limit"]

        # Check for API key
        api_key = settings.ORS_API_KEY
        if not api_key:
            self.stderr.write(self.style.ERROR("ORS_API_KEY is not configured in .env"))
            return

        ors = ORSClient(api_key)

        # Build queryset for stations missing coordinates
        missing_qs = FuelStation.objects.filter(
            Q(lat__isnull=True) | Q(lng__isnull=True)
        )

        # Apply state filter if provided
        if states:
            # Normalize states (handle comma-separated values)
            normalized_states = []
            for s in states:
                normalized_states.extend([x.strip().upper() for x in s.split(",")])
            missing_qs = missing_qs.filter(state__in=normalized_states)
            self.stdout.write(f"Filtering to states: {', '.join(normalized_states)}")

        # Count and limit
        total_missing = missing_qs.count()
        self.stdout.write(f"Found {total_missing} stations missing coordinates")

        if total_missing == 0:
            self.stdout.write(self.style.SUCCESS("No stations need geocoding!"))
            return

        # Apply limit
        stations_to_geocode = missing_qs[:limit]

        attempted = 0
        success = 0
        failed = 0

        self.stdout.write(f"Geocoding up to {limit} stations (rate limit: {rate_limit}s)...")
        self.stdout.write("")

        for station in stations_to_geocode:
            attempted += 1

            full_address = f"{station.address}, {station.city}, {station.state}, USA"

            try:
                result = ors.geocode_text(full_address)
                station.lat = result["lat"]
                station.lng = result["lng"]
                station.save(update_fields=["lat", "lng"])
                success += 1

                if attempted % 50 == 0 or attempted == 1:
                    self.stdout.write(
                        f"  [{attempted}/{limit}] Success: {station.truckstop_name} - "
                        f"{station.city}, {station.state}"
                    )

            except GeocodingError as e:
                failed += 1
                if failed <= 10:  # Only show first 10 failures
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [{attempted}/{limit}] Failed: {station.truckstop_name} - {e}"
                        )
                    )

            # Rate limit
            if attempted < limit:
                time.sleep(rate_limit)

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("Geocoding complete!"))
        self.stdout.write(f"  Attempted: {attempted}")
        self.stdout.write(self.style.SUCCESS(f"  Success:   {success}"))
        if failed > 0:
            self.stdout.write(self.style.WARNING(f"  Failed:    {failed}"))
        else:
            self.stdout.write(f"  Failed:    {failed}")

        # Show remaining
        remaining = FuelStation.objects.filter(
            Q(lat__isnull=True) | Q(lng__isnull=True)
        ).count()
        if remaining > 0:
            self.stdout.write("")
            self.stdout.write(
                f"  Remaining stations without coords: {remaining}"
            )
            self.stdout.write(
                "  Run this command again to geocode more stations."
            )

