import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from routing.models import FuelStation


REQUIRED_COLUMNS = {
    "Truckstop Name",
    "Address",
    "City",
    "State",
    "Retail Price",
    "OPIS Truckstop ID",
}

BATCH_SIZE = 1000


class Command(BaseCommand):
    help = "Import fuel station data from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to the CSV file")

    def handle(self, *args, **options):
        csv_path = options["csv_path"]

        try:
            with open(csv_path, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)

                # Validate required columns
                if reader.fieldnames is None:
                    raise CommandError("CSV file is empty or has no headers")

                missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames)
                if missing_columns:
                    raise CommandError(
                        f"CSV is missing required columns: {', '.join(sorted(missing_columns))}"
                    )

                created_count = 0
                skipped_count = 0
                batch = []

                # Ensure database connection is established before bulk operations
                connection.ensure_connection()

                for row in reader:
                    # Parse and validate retail_price
                    retail_price_str = row.get("Retail Price", "").strip()
                    if not retail_price_str:
                        skipped_count += 1
                        continue

                    try:
                        retail_price = Decimal(retail_price_str)
                    except InvalidOperation:
                        skipped_count += 1
                        continue

                    station = FuelStation(
                        opis_truckstop_id=row.get("OPIS Truckstop ID", "").strip() or None,
                        truckstop_name=row.get("Truckstop Name", "").strip(),
                        address=row.get("Address", "").strip(),
                        city=row.get("City", "").strip(),
                        state=row.get("State", "").strip(),
                        retail_price=retail_price,
                    )
                    batch.append(station)

                    if len(batch) >= BATCH_SIZE:
                        FuelStation.objects.bulk_create(batch)
                        created_count += len(batch)
                        batch = []

                # Insert remaining records
                if batch:
                    FuelStation.objects.bulk_create(batch)
                    created_count += len(batch)

        except FileNotFoundError:
            raise CommandError(f"CSV file not found: {csv_path}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Import complete: {created_count} created, {skipped_count} skipped"
            )
        )

