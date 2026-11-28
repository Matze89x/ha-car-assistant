"""The made-up charging points of tools/demo_server.py (the picture of the Charging page in the documentation): a short list around the place that is asked
for, inside the radius, with the strongest plug first - and importing the file does not change the app."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import demo_server

from carassistant import stations


def test_importing_the_demo_server_leaves_the_real_search_alone():
    assert stations.fetch_osm_charge is not demo_server.made_up_charging_points


def test_the_made_up_charging_points_lie_around_the_place_inside_the_radius():
    found = demo_server.made_up_charging_points(52.512, 13.389, 15)
    assert len(found) == len(demo_server.MADE_UP) and all(0 < s.distance_km <= 15 for s in found)
    for s in found:
        assert s.max_kw == max(p["kw"] for p in s.plugs) == s.plugs[0]["kw"]  # the strongest plug first
        assert {p["type"] for p in s.plugs} <= {"ccs", "type2", "chademo", "nacs", "type1", "household", "other"}
    near = demo_server.made_up_charging_points(52.512, 13.389, 1.0)
    assert 0 < len(near) < len(found)  # a smaller radius leaves the far ones out
    assert {s.name for s in near} <= {s.name for s in found}
