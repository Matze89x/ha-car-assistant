"""The navigation list: a page in More looks like every other page; only a page that is switched off is dimmed. Integrations have a switch."""

import json
from pathlib import Path

from carassistant import addons, db

CSS = (Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant" / "static" / "pc-core.css").read_text()


def test_pages_in_more_are_not_dimmed_only_switched_off_ones_are():
    assert ".navrow.inmore {" not in CSS  # the old rule that made everything under "In More" half transparent and dashed
    assert ".navrow.off-row" in CSS and ":has(.switch input:not(:checked))" in CSS


def test_an_integration_card_has_the_switch_and_no_dead_open_button(client):
    pkg = {
        "id": "coding-demo",
        "kind": "integration",
        "name": "Coding demo",
        "version": "1",
        "pages": [
            {
                "id": "units",
                "title": "Units",
                "item": "Unit",
                "fields": [{"key": "name", "label": "Name", "type": "text", "required": True, "role": "title"}],
            }
        ],
    }
    client.post("/vehicles", data={"name": "Switch Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        vid = conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()["id"]
        slug = conn.execute("SELECT slug FROM vehicles WHERE id = ?", (vid,)).fetchone()["slug"]
    client.post(f"/v/{vid}/integrations/upload", files={"package": ("plugin.json", json.dumps(pkg), "application/json")})
    with db.tx() as conn:
        pk = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "coding-demo")["id"]
    client.post(f"/v/{vid}/integrations/{pk}/active", data={"active": "1"})
    on = client.get(f"/v/{slug}/integrations?tab=manage").text
    card = on.split("Coding demo", 1)[1]
    assert f"integrations/{pk}/active" in card and "/m/coding-demo" in card  # the switch, and Open while it is on
    client.post(f"/v/{vid}/integrations/{pk}/active", data={"enabled": "0"})
    off = client.get(f"/v/{slug}/integrations?tab=manage").text
    assert (
        "/m/coding-demo" not in off.split("INSTALLED", 1)[-1] and f"integrations/{pk}/active" in off
    )  # no Open that leads nowhere, the switch stays
