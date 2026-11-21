# ruff: noqa: S105, S310
"""Minimal plugin script: reads values from your car (replace read_car()) and pushes them to Car Assistant.

Run it on any computer / Raspberry Pi / add-on that can reach Car Assistant. Needs only the Python standard library.
"""

import json
import urllib.request

URL = "https://car.example.com"  # your Car Assistant address (direct access / reverse proxy)
TOKEN = "ca_..."  # Car Assistant → Integrations → Connections → Create token
VEHICLE_ID = 1


def read_car() -> dict:
    # Replace with your own source: OBD-II, a manufacturer cloud, a Home Assistant entity, ...
    return {"odometer_km": 52340, "fuel_level_pct": 61, "range_km": 420, "position": {"lat": 52.52, "lon": 13.405}, "ignition": False}


request = urllib.request.Request(
    f"{URL}/api/v1/vehicles/{VEHICLE_ID}/data",
    data=json.dumps(read_car()).encode(),
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=15) as response:
    print(response.read().decode())

# --- bigger deliveries (see docs/api.md): a gzip-packed track of a drive, and raw signals the app only keeps -----------------------------
# import gzip
# points = {"points": [{"ts": "2026-11-15T08:00:00Z", "lat": 52.52, "lon": 13.405, "speed_kmh": 30}]}
# urllib.request.urlopen(urllib.request.Request(f"{URL}/api/v1/vehicles/{VEHICLE_ID}/track", data=gzip.compress(json.dumps(points).encode()),
#     headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json", "Content-Encoding": "gzip"}, method="POST"))
# signals = {"signals": {"kombi.odo_km": 52340, "pc.override": True}}  # -> POST .../signals
