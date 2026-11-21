import json

from tests.test_web import create_vehicle

from carassistant import connectors, db


def test_the_pressures_the_car_reported_are_shown_below_the_label_and_only_when_there_are_some(client):
    vid = create_vehicle(client, "Reading Car")
    base = f"/v/{vid}/e/tires"
    client.post(base, data={"name": "Summer set", "season": "summer", "size": "205/55 R16"})
    client.post(f"{base}/pressure", data={"season": "summer", "front": "2.4", "rear": "2.6"})
    assert "received from the vehicle" not in client.get(base).text and "Reifendruck vom Fahrzeug" not in client.get(base).text
    with db.tx() as conn:
        connectors._store(conn, vid, "tyre_pressure_bar", json.dumps({"fl": None, "fr": None, "rl": None, "rr": None}))  # an empty report
    assert "received from the vehicle" not in client.get(base).text
    with db.tx() as conn:
        connectors._store(conn, vid, "tyre_pressure_bar", json.dumps({"fl": 2.3, "fr": 2.4, "rl": 2.5, "rr": 2.5}))
    page = client.get(base).text
    assert "Tyre pressure received from the vehicle on" in page
    assert page.index('class="tp-label"') < page.index("received from the vehicle")  # below the label of the set
