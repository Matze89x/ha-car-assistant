#!/usr/bin/env python3
"""The app, started exactly like ``python -m carassistant`` - with ONE difference: the charging points around a place come from a short made-up list
instead of the Overpass API. ``tools/make_screenshots.py`` starts the app this way, so the picture of the Charging page shows results without anything
going online and without a real operator or a real street in it.

Needs ``PYTHONPATH`` to hold ``carassistant/app`` and the usual ``CARASSISTANT_*`` variables (the data folder, the port); nothing here is part of the app.
"""

from __future__ import annotations

from carassistant import __main__ as app_main
from carassistant import stations

# name, address, operator, (north, east) offset in degrees from the place searched around, points, plugs (type, kW, count), what the fee is (text), free
MADE_UP = (
    ("Example Charging Hub", "1 Example Street, 10000 Example City", "Example Energy", (0.0030, 0.0042), 8, (("ccs", 150, 6), ("type2", 22, 2)), "", None),
    ("Demo Power Plaza", "12 Sample Road, 10000 Example City", "Demo Power", (-0.0055, 0.0020), 4, (("ccs", 50, 2), ("chademo", 50, 1), ("type2", 22, 1)), "0.49 / kWh", False),
    ("Town Hall Car Park", "3 Placeholder Square, 10000 Example City", "Example City Utilities", (0.0071, -0.0062), 2, (("type2", 22, 2),), "", True),
    ("Sample Supermarket", "40 Test Lane, 10000 Example City", "Sample Retail", (-0.0090, -0.0110), 6, (("ccs", 75, 4), ("type2", 22, 2)), "", True),
    ("Example Motorway Services", "Junction 7, 10000 Example City", "Example Energy", (0.0160, 0.0210), 12, (("ccs", 350, 8), ("ccs", 150, 4)), "0.59 / kWh", False),
    ("Demo Garage", "7 Made-up Avenue, 10000 Example City", "", (-0.0125, 0.0170), 1, (("type2", 11, 1),), "", None),
)  # fmt: skip


def made_up_charging_points(lat: float, lon: float, radius: float) -> list[stations.Station]:
    found = []
    for name, address, operator, (north, east), points, plugs, fee, free in MADE_UP:
        place = (lat + north, lon + east)
        kinds: dict[str, dict] = {}
        for kind, kw, count in plugs:
            have = kinds.setdefault(kind, {"type": kind, "label": "", "n": 0, "kw": float(kw)})
            have["n"] += count
            have["kw"] = max(have["kw"], float(kw))
        found.append(
            stations.Station(
                name=name,
                brand="",
                address=address,
                lat=place[0],
                lon=place[1],
                distance_km=stations.haversine_km(lat, lon, *place),
                operator=operator,
                points=points,
                max_kw=max(float(kw) for _, kw, _ in plugs),
                plugs=tuple(sorted(kinds.values(), key=lambda p: -p["kw"])),
                fee=fee,
                free=free,
            )
        )
    return [s for s in found if s.distance_km <= radius]


def main() -> None:
    stations.fetch_osm_charge = made_up_charging_points  # only in the process that serves the pictures: importing this file changes nothing
    app_main.main()


if __name__ == "__main__":
    main()
