"""Place names without asking anyone: the nearest of the ~34,000 cities of the world (GeoNames ``cities15000``, CC BY 4.0, shipped in ``data/``).

A trip goes from place to place, so the name of the nearest city is what is wanted. Works worldwide and offline, has no rate limit and sends nothing.
A spot farther than ``MAX_KM`` from every city gets no name (the coordinates stay). Names are the ones GeoNames uses (mostly the local or English name).
"""

from __future__ import annotations

import gzip
import math
import threading
from pathlib import Path

DATA = Path(__file__).parent / "geodata" / "cities15000.tsv.gz"
MAX_KM = 60.0
_cells: dict[tuple[int, int], list[tuple[float, float, str, int]]] | None = None
_lock = threading.Lock()


def _load() -> dict[tuple[int, int], list[tuple[float, float, str, int]]]:
    global _cells
    with _lock:
        if _cells is None:
            cells: dict[tuple[int, int], list[tuple[float, float, str, int]]] = {}
            with gzip.open(DATA, "rt", encoding="utf-8") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 3:
                        name, lat, lon = parts[0], float(parts[1]), float(parts[2])
                        pop = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
                        cells.setdefault((math.floor(lat), math.floor(lon)), []).append((lat, lon, name, pop))
            _cells = cells
        return _cells


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def nearest(lat: float, lon: float) -> str | None:
    """The name of the nearest city within ``MAX_KM``, else None."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    cells = _load()
    clat, clon = math.floor(lat), math.floor(lon)
    spread = max(1, math.ceil(MAX_KM / (111.0 * max(0.2, math.cos(math.radians(lat))))))  # cells to look around (more near the poles)
    found: list[tuple[float, str, int]] = []
    for dy in range(-1, 2):
        for dx in range(-spread, spread + 1):
            for plat, plon, name, pop in cells.get((clat + dy, (clon + dx + 180) % 360 - 180), ()):
                d = _km(lat, lon, plat, plon)
                if d <= MAX_KM:
                    found.append((d, name, pop))
    if not found:
        return None
    nearest_d = min(d for d, _n, _p in found)
    # GeoNames also lists districts (Mitte, Yoyogi ...): among the places about as near as the nearest one, the biggest is the city itself
    window = nearest_d + 4.0 + 0.3 * nearest_d
    return max((f for f in found if f[0] <= window), key=lambda f: (f[2], -f[0]))[1]
