"""Build the two demo vehicles (a diesel and an electric car) as vehicle backups for the sources repository.

Usage: python tools/make_demo_vehicles.py <output folder>      (writes demo-diesel.zip and demo-electric.zip)

Runs against a temporary data folder and the app's own export, so the files always have the current backup format. When the app has changed
a lot, restore a demo vehicle, adjust it and download its backup again - that new file replaces the old one.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as tmp:
    os.environ["CARASSISTANT_DATA"] = tmp
    sys.path.insert(0, str(HERE.parent / "carassistant" / "app"))
    sys.path.insert(0, str(HERE))
    import demo_data as demo

    from carassistant import config, db, summary, vehiclebackup

    db.migrate()
    DOCS = {
        False: (
            (
                "Quick guide (example)",
                "manual",
                "quick-guide.txt",
                "Quick guide - example vehicle\n\nStart: press the brake and the start button.\nTank: diesel only, 55 litres.\nService: every 15,000 km or once a year.\n",
            ),
            (
                "Service plan (example)",
                "inspection",
                "service-plan.txt",
                "Service plan - example\n\nOil and filter: every 15,000 km\nBrake fluid: every 2 years\nTyres: check pressure monthly\n",
            ),
            (
                "Insurance policy (example)",
                "insurance",
                "insurance.txt",
                "Insurance policy - example\n\nComprehensive cover, excess 300\nNo-claims class: SF 12\n",
            ),
            (
                "Registration (example)",
                "registration",
                "registration.txt",
                "Registration - example\n\nPlate AB-CD 123, first registered three years ago\n",
            ),
            (
                "Invoice oil service (example)",
                "invoice",
                "invoice-oil-service.txt",
                "Invoice - example\n\nOil & filter service, Example Garage: 205.40\n",
            ),
        ),
        True: (
            (
                "Quick guide (example)",
                "manual",
                "quick-guide.txt",
                "Quick guide - example electric vehicle\n\nCharging: AC at home, DC on the road.\nBattery: 64 kWh, aim for 20-80 % for daily use.\nPrecondition the cabin while plugged in.\n",
            ),
            (
                "Charging notes (example)",
                "other",
                "charging-notes.txt",
                "Charging notes - example\n\nHome wallbox: 11 kW\nPublic AC: 22 kW\nFast charger: up to 100 kW\n",
            ),
            (
                "Insurance policy (example)",
                "insurance",
                "insurance.txt",
                "Insurance policy - example\n\nComprehensive cover, excess 300\nNo-claims class: SF 6\n",
            ),
            (
                "Registration (example)",
                "registration",
                "registration.txt",
                "Registration - example\n\nPlate EF-GH 456, first registered four years ago\n",
            ),
            (
                "Invoice wallbox (example)",
                "invoice",
                "invoice-wallbox.txt",
                "Invoice - example\n\nHome wallbox 11 kW, installation: 1 290.00\n",
            ),
        ),
    }
    for electric, name, file in ((False, "Demo Diesel", "demo-diesel.zip"), (True, "Demo Electric", "demo-electric.zip")):
        with db.tx() as conn:
            vid = demo.create(conn, electric=electric)
            conn.execute("UPDATE vehicles SET name = ? WHERE id = ?", (name, vid))
            if not conn.execute("SELECT 1 FROM tasks WHERE vehicle_id = ?", (vid,)).fetchone():
                summary.seed_default_tasks(conn, vid)
            folder = config.files_dir() / str(vid)
            folder.mkdir(parents=True, exist_ok=True)
            for title, category, filename, text in DOCS[electric]:
                doc = conn.execute(
                    "INSERT INTO documents(vehicle_id, category, title, filename, mime, size) VALUES(?,?,?,?,?,?)",
                    (vid, category, title, filename, "text/plain", len(text)),
                ).lastrowid
                (folder / f"{doc}.txt").write_text(text, encoding="utf-8")
            from carassistant import widgets

            first = widgets.layout(
                conn, vid
            )  # every widget of the Home starts small - except the fixed ones (attention, vehicle data, position): one full row
            widgets.save(
                conn, vid, [w.key for w in first], {w.key: ("m" if w.fixed else "s") for w in first}, {w.key for w in first if w.on}, {}
            )
            conn.execute("DELETE FROM vehicle_addons WHERE vehicle_id = ?", (vid,))
            conn.execute("DELETE FROM api_tokens WHERE vehicle_id = ?", (vid,))
            manifest = {
                "id": "demo-connector",
                "kind": "plugin",
                "name": "Demo connector",
                "version": "1",
                "description": "",
                "author": "",
                "homepage": "",
                "settings": [],
            }
            conn.execute(  # the car asks for its plugin: it is installed from the standard source (the package itself is never part of a backup)
                "INSERT INTO vehicle_addons(vehicle_id, kind, addon_id, manifest, status, settings, created_at, active, source_url) VALUES(?,?,?,?,?,?,?,0,?)",
                (
                    vid,
                    "plugin",
                    "demo-connector",
                    json.dumps(manifest),
                    "missing",
                    "{}",
                    "2026-01-01T00:00:00",
                    "https://github.com/Matze89x/ha-car-assistant-sources",
                ),
            )
            (out / file).write_bytes(vehiclebackup.export(conn, vid))
            conn.execute("DELETE FROM vehicles WHERE id = ?", (vid,))
        print("wrote", out / file)
