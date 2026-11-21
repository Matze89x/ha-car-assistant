"""Builds a Car Assistant vehicle file (zip) from plain Python data - the way to bring a car in from any other system.

Everything is in base units: kilometres, litres (kWh for electric), money as a plain number, dates as YYYY-MM-DD, times as HH:MM.
Restore the result under *Vehicles -> Restore a vehicle*. See docs/vehicle-file.md.
"""

import json
import zipfile
from datetime import UTC, datetime

car = {
    "app": "carassistant",
    "kind": "vehicle",
    "format": 1,
    "created": datetime.now(UTC).isoformat(timespec="seconds"),
    "vehicle": {"name": "Example", "fuel_type": "diesel", "plate": "AB-CD 123", "tank_l": 55, "created_at": "2026-01-01T00:00:00+00:00"},
    "tables": {
        "odometer": [{"date": "2026-01-01", "odometer_km": 50000, "source": "import"}],
        "fuel": [
            {"date": "2026-02-01", "odometer_km": 50400, "amount": 41.2, "price_total": 70.1, "full_tank": 1, "station": "Example Station"}
        ],
        "service": [{"date": "2025-11-10", "odometer_km": 48000, "title": "Oil change", "workshop": "Example Garage", "cost": 180.0}],
        "trips": [
            {
                "date": "2026-02-03",
                "start_time": "08:00",
                "end_time": "08:40",
                "distance_km": 32.5,
                "category": "business",
                "source": "import",
            }
        ],
    },
}

with zipfile.ZipFile("example-vehicle.zip", "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("vehicle.json", json.dumps(car, ensure_ascii=False))
print("example-vehicle.zip written")
