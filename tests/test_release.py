"""The version and the stage live in release.json only; every other place is written from it (tools/release.py)."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_tool", ROOT / "tools" / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_every_place_agrees_with_release_json():
    data = release.load()
    assert release.problems(data) == [], "run: python tools/release.py sync"


def test_the_app_knows_its_version_and_stage():
    import carassistant

    data = json.loads((ROOT / "release.json").read_text())
    assert carassistant.__version__ == data["version"] and data["stage"] == carassistant.STAGE
    assert data["stage"] in data["notes"]  # every stage has its note in both languages
    assert set(data["notes"][data["stage"]]) == {"en", "de"}


def test_bumping_counts_the_right_number():
    data = {"version": "0.4.3", "stage": "Alpha"}
    assert release.bump(data, "fix") == "0.4.4"
    assert release.bump(data, "feature") == "0.5.0"
    assert release.bump(data, "release") == "1.0.0"


def test_the_about_page_shows_the_stage(client):
    import carassistant

    page = client.get("/about").text
    assert f"v{carassistant.__version__} {carassistant.STAGE}" in page
