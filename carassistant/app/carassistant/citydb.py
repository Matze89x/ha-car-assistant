"""Place names without asking anyone: the nearest of the ~172,000 places of the world with more than 1,000 inhabitants (GeoNames ``cities1000`` and
its German names, CC BY 4.0, shipped in ``geodata/``).

A trip goes from place to place, so the name of the nearest city is what is wanted. Works worldwide and offline, has no rate limit and sends nothing.
A spot farther than ``MAX_KM`` from every city gets no name (the coordinates stay). Names are in German when the language is German and GeoNames knows one (München, Prag), else the name GeoNames uses.
"""

from __future__ import annotations

import gzip
import math
import threading
from pathlib import Path

DATA = Path(__file__).parent / "geodata" / "cities1000.tsv.gz"
MAX_KM = 60.0
_cells: dict[tuple[int, int], list[tuple[float, float, str, int, str]]] | None = None
_lock = threading.Lock()


def _load() -> dict[tuple[int, int], list[tuple[float, float, str, int, str]]]:
    global _cells
    with _lock:
        if _cells is None:
            cells: dict[tuple[int, int], list[tuple[float, float, str, int, str]]] = {}
            with gzip.open(DATA, "rt", encoding="utf-8") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 3:
                        name, lat, lon = parts[0], float(parts[1]), float(parts[2])
                        pop = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
                        german = parts[4] if len(parts) > 4 else ""
                        cells.setdefault((math.floor(lat), math.floor(lon)), []).append((lat, lon, name, pop, german))
            _cells = cells
        return _cells


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))


def nearest(lat: float, lon: float, lang: str = "") -> str | None:
    """The name of the place for a spot, else None: the nearest one within ``MAX_KM`` - or a bigger city that is close enough to be what the
    spot belongs to (a district of Berlin is Berlin, a village next to a town stays the village)."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    cells = _load()
    clat, clon = math.floor(lat), math.floor(lon)
    spread = max(1, math.ceil(MAX_KM / (111.0 * max(0.2, math.cos(math.radians(lat))))))  # cells to look around (more near the poles)
    found: list[tuple[float, str, int, str]] = []
    for dy in range(-1, 2):
        for dx in range(-spread, spread + 1):
            for plat, plon, name, pop, german in cells.get((clat + dy, (clon + dx + 180) % 360 - 180), ()):
                d = _km(lat, lon, plat, plon)
                if d <= MAX_KM:
                    found.append((d, name, pop, german))
    if not found:
        return None
    nearest_d = min(f[0] for f in found)
    eligible = [f for f in found if f[0] <= max(nearest_d + 0.5, 1.5 * math.sqrt(f[2] / 10000))]  # the reach of a place grows with its size
    best = max(eligible, key=lambda f: (f[2], -f[0]))
    return (best[3] if lang == "de" and best[3] else best[1]) or None
