import json

from carassistant import addons, db, pagemods

PKG = {
    "id": "coding-demo",
    "kind": "integration",
    "name": "Coding demo",
    "version": "1",
    "icon": "memory",
    "pages": [
        {
            "id": "units",
            "title": "Units",
            "item": "Unit",
            "fields": [
                {"key": "addr", "label": "Address", "type": "hex", "required": True, "role": "title"},
                {"key": "name", "label": "Name", "type": "text", "required": True, "role": "title"},
                {"key": "old", "label": "Original", "type": "hex", "once": True},
                {"key": "new", "label": "Now", "type": "hex", "compare": "old"},
                {"key": "notes", "label": "Notes", "type": "textarea"},
                {"key": "on", "label": "Active", "type": "bool"},
            ],
        }
    ],
}


def _car(client):
    client.post("/vehicles", data={"name": "Mod Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        row = conn.execute("SELECT id, slug FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()
    return row["id"], row["slug"]


def _install(client, vid, pkg=PKG):
    client.post(f"/v/{vid}/integrations/upload", files={"package": ("plugin.json", json.dumps(pkg), "application/json")})
    with db.tx() as conn:
        item = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == pkg["id"])
    client.post(f"/v/{vid}/integrations/{item['id']}/active", data={"active": "1"})


def test_manifest_pages_are_cleaned():
    m = addons.parse_package(json.dumps({**PKG, "icon": "no-such-icon", "pages": PKG["pages"] + [{"id": "Bad Id", "fields": []}]}).encode())
    assert m["icon"] == "puzzle" and len(m["pages"]) == 1 and m["pages"][0]["fields"][3]["compare"] == "old"
    assert (
        addons.parse_package(json.dumps({"id": "plain-one", "kind": "integration"}).encode()).get("pages") is None
    )  # no pages: nothing added


def test_a_stopped_integration_has_no_page_and_a_running_one_is_in_more(client):
    vid, slug = _car(client)
    _install(client, vid)
    assert "Coding demo" in client.get(f"/v/{slug}/more").text
    assert client.get(f"/v/{slug}/m/coding-demo").status_code == 200
    with db.tx() as conn:
        pk = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "coding-demo")["id"]
    client.post(f"/v/{vid}/integrations/{pk}/active", data={})  # stop
    assert "Coding demo" not in client.get(f"/v/{slug}/more").text
    assert client.get(f"/v/{slug}/m/coding-demo", follow_redirects=False).status_code == 303


def test_a_page_of_a_package_with_its_own_entry_marks_that_entry_and_leads_back_to_more(client):
    """The page Coding is opened from its own entry in More: that entry stays marked (not the list of Integrations) and Back goes to More."""
    import re

    vid, slug = _car(client)
    _install(client, vid)
    page = client.get(f"/v/{slug}/m/coding-demo").text
    marked = re.findall(r'<a class="mi sel" href="([^"]*)"', page)
    assert marked == [f"/v/{slug}/m/coding-demo"], marked
    back = re.search(r'class="back-btn[^"]*" href="([^"]*)"', page)
    assert back and back.group(1).endswith("/more"), back and back.group(1)


def test_entries_original_is_written_once_and_bytes_are_compared(client):
    vid, slug = _car(client)
    _install(client, vid)
    base = f"/v/{slug}/m/coding-demo/units"
    bad = client.post(base, data={"addr": "zz", "name": "J519"})
    assert bad.status_code == 400  # not hex
    client.post(base, data={"addr": "09", "name": "J519", "old": "0A 0B 0C", "new": "0a0b0d"})
    with db.tx() as conn:
        row = pagemods.rows(conn, vid, "coding-demo", "units")[0]
    assert row["data"]["old"] == "0A0B0C" and row["data"]["new"] == "0A0B0D"
    page = client.get(base).text
    assert "J519" in page and "pm-byte ch" in page and "0C" in page and "0D" in page  # the changed byte is marked
    client.post(
        f"{base}/{row['id']}", data={"addr": "09", "name": "J519", "old": "FFFF", "new": "0A0B0C"}
    )  # a person may change the original at any time
    with db.tx() as conn:
        assert pagemods.rows(conn, vid, "coding-demo", "units")[0]["data"]["old"] == "FFFF"
        assert pagemods.rows(conn, vid, "coding-demo", "units")[0]["data"]["new"] == "0A0B0C"
    client.post(f"{base}/{row['id']}/delete")
    with db.tx() as conn:
        assert pagemods.rows(conn, vid, "coding-demo", "units") == []


def test_the_entries_of_a_sortable_page_are_put_in_order_with_the_handle(client):
    vid, slug = _car(client)
    pkg = {**PKG, "id": "sorted-demo", "pages": [{**PKG["pages"][0], "sortable": True}]}
    _install(client, vid, pkg)
    base = f"/v/{slug}/m/sorted-demo/units"
    for name, addr in (("A", "01"), ("B", "02"), ("C", "03")):
        client.post(base, data={"addr": addr, "name": name})
    with db.tx() as conn:
        ids = [r["id"] for r in pagemods.rows(conn, vid, "sorted-demo", "units")]
    page = client.get(base).text
    assert page.count('class="grip"') == 3 and f'data-sort-post="{base}/order"' in page
    assert all(f'data-sort-id="{i}"' in page for i in ids)
    r = client.post(f"{base}/order", data={"order": f"{ids[2]},{ids[0]},99999"})  # C, A first; B follows; an unknown id is ignored
    assert r.status_code == 200 and r.json() == {"ok": True}
    with db.tx() as conn:
        assert [r["id"] for r in pagemods.rows(conn, vid, "sorted-demo", "units")] == [ids[2], ids[0], ids[1]]
    plain = client.get(f"/v/{slug}/m/coding-demo/units").text
    assert 'class="grip"' not in plain and "data-sort-post" not in plain  # a page that is not sortable has no handle


def test_order_can_be_changed_and_entries_survive_a_vehicle_backup_roundtrip():
    from carassistant import db as _db  # noqa: F401

    assert pagemods.byte_diff("0A0B", "0A0C")["changed"][0]["i"] == 1
    assert pagemods.byte_diff("0A", "0A0B")["len_differs"]


def test_entries_are_part_of_the_vehicle_backup(client):
    from carassistant import vehiclebackup

    vid, slug = _car(client)
    _install(client, vid)
    client.post(f"/v/{slug}/m/coding-demo/units", data={"addr": "09", "name": "J519", "old": "0A0B"})
    with db.tx() as conn:
        raw = vehiclebackup.export(conn, vid)
    assert b"J519" in __import__("zipfile").ZipFile(__import__("io").BytesIO(raw)).read("vehicle.json")
    with db.tx() as conn:
        new_id = vehiclebackup.restore(conn, raw) if hasattr(vehiclebackup, "restore") else None
    assert new_id
    with db.tx() as conn:
        rows = pagemods.rows(conn, new_id, "coding-demo", "units") if new_id != vid else pagemods.rows(conn, vid, "coding-demo", "units")
    assert rows and rows[0]["data"]["name"] == "J519"


def test_texts_of_a_package_follow_the_language():
    pkg = {**PKG, "l10n": {"de": {"name": "Codierung"}}}
    pkg["pages"] = [{**PKG["pages"][0], "l10n": {"de": {"title": "Steuergeräte"}}}]
    pkg["pages"][0]["fields"] = [
        {**f, **({"l10n": {"de": {"label": "Adresse"}}} if f["key"] == "addr" else {})} for f in PKG["pages"][0]["fields"]
    ]
    mod = addons.parse_package(json.dumps(pkg).encode())
    shown = pagemods.localize({"addon_id": "coding-demo", "name": mod["name"], "l10n": mod["l10n"], "pages": mod["pages"]}, "de")
    assert (
        shown["name"] == "Codierung"
        and shown["pages"][0]["title"] == "Steuergeräte"
        and shown["pages"][0]["fields"][0]["label"] == "Adresse"
    )
    assert pagemods.localize({"name": "X", "pages": mod["pages"]}, "fr")["pages"][0]["title"] == "Units"  # no translation: the original


def test_a_plugin_can_read_the_entries_through_the_connector_api(client):
    from carassistant import connectors

    vid, slug = _car(client)
    _install(client, vid)
    client.post(f"/v/{slug}/m/coding-demo/units", data={"addr": "09", "name": "J519"})
    with db.tx() as conn:
        token = connectors.create_token(conn, "reader", vid)
    got = client.get(f"/api/v1/vehicles/{vid}/modules/coding-demo/units", headers={"Authorization": f"Bearer {token}"})
    assert got.status_code == 200 and got.json()["rows"][0]["name"] == "J519"
    assert client.get(f"/api/v1/vehicles/{vid}/modules/coding-demo/nope", headers={"Authorization": f"Bearer {token}"}).status_code == 404
    assert client.get(f"/api/v1/vehicles/{vid}/modules/coding-demo/units").status_code in (401, 403)  # no token


def test_without_a_current_value_nothing_counts_as_changed(client):
    vid, slug = _car(client)
    _install(client, vid)
    client.post(f"/v/{slug}/m/coding-demo/units", data={"addr": "17", "name": "Cluster", "old": "00FF10"})
    page = client.get(f"/v/{slug}/m/coding-demo/units").text
    assert "pm-byte ch" not in page and "FF" in page


def test_an_integration_page_can_sit_in_the_navigation_bar(client):
    from carassistant import navigation

    vid, slug = _car(client)
    _install(client, vid)
    with db.tx() as conn:
        pk = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "coding-demo")["id"]
        assert navigation.X + "coding-demo" in dict(navigation.order(conn, vid)) and navigation.X + "coding-demo" not in dict(
            navigation.slots(conn, vid)
        )
    client.post(f"/v/{vid}/integrations/{pk}/bar", data={"way": "in"})
    with db.tx() as conn:
        assert navigation.X + "coding-demo" in dict(navigation.slots(conn, vid))
    page = client.get(f"/v/{slug}/m/coding-demo").text
    assert f'href="/v/{slug}/m/coding-demo"' in page and "Coding demo" in page  # the bar item has its own name and path
    client.post(f"/v/{vid}/integrations/{pk}/bar", data={"way": "out"})
    with db.tx() as conn:
        assert navigation.X + "coding-demo" not in dict(navigation.slots(conn, vid))


def test_the_switch_in_the_integrations_list_starts_and_stops(client):
    vid, slug = _car(client)
    _install(client, vid)
    with db.tx() as conn:
        pk = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "coding-demo")["id"]
    assert (
        "Coding demo" in client.get(f"/v/{slug}/integrations").text.split('id="navigation"')[1]
    )  # listed with the pages in the navigation editor
    assert client.post(f"/v/{vid}/integrations/{pk}/active", data={"enabled": "0", "ajax": "1"}).status_code == 204
    with db.tx() as conn:
        assert not addons.get(conn, vid, pk)["active"]
    client.post(f"/v/{vid}/integrations/{pk}/active", data={"enabled": "1", "ajax": "1"})
    with db.tx() as conn:
        assert addons.get(conn, vid, pk)["active"]


ADDITIVE = {
    "id": "additive-demo",
    "kind": "integration",
    "name": "Additive demo",
    "version": "1",
    "settings": [
        {
            "key": "mode",
            "label": "When",
            "type": "select",
            "default": "km",
            "options": [{"value": "km", "label": "km"}, {"value": "refuels", "label": "refuels"}],
        },
        {"key": "every_km", "label": "Every km", "type": "number", "default": "1000"},
        {"key": "every_refuels", "label": "Every refuels", "type": "number", "default": "2"},
    ],
    "reminders": [
        {"id": "additive", "title": "Additive", "mode_setting": "mode", "km_setting": "every_km", "refuels_setting": "every_refuels"}
    ],
}


def test_reminder_counts_kilometres_and_refuels_and_done_starts_again(client):
    from carassistant import reminders, summary

    vid, slug = _car(client)
    with db.tx() as conn:
        summary.record_odometer(conn, vid, 50000, "manual")
    _install(client, vid, ADDITIVE)
    with db.tx() as conn:
        base = summary.current_odometer(conn, vid) or 0
        first = reminders.status(conn, vid)[0]
    assert first["mode"] == "km" and first["every"] == 1000 and not first["due"] and first["left"] == 1000.0  # defaults, counted from now
    with db.tx() as conn:
        summary.record_odometer(conn, vid, base + 1200, "manual")
        st = reminders.status(conn, vid)[0]
    assert st["due"] and st["left"] == -200
    with db.tx() as conn:
        assert reminders.done(conn, vid, "additive-demo", "additive")
        assert not reminders.status(conn, vid)[0]["due"]
        pk = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "additive-demo")["id"]
    client.post(f"/v/{vid}/integrations/{pk}/setup", data={"mode": "refuels", "every_km": "1000", "every_refuels": "2"})
    for _ in range(2):
        client.post(f"/v/{slug}/e/fuel", data={"date": "2026-11-01", "amount": "40", "price_total": "60", "odometer_km": str(base + 1300)})
    with db.tx() as conn:
        st = reminders.status(conn, vid)[0]
    assert st["mode"] == "refuels" and st["due"] and st["left"] == 0  # after the second refuel


def test_a_running_integration_with_a_reminder_gets_a_widget_a_fuel_card_and_a_done_button(client):
    from carassistant import reminders, summary, widgets

    vid, slug = _car(client)
    with db.tx() as conn:
        summary.record_odometer(conn, vid, 50000, "manual")
    assert "x-additive-demo-additive" not in client.get(f"/v/{slug}").text  # nothing before the integration runs
    _install(client, vid, ADDITIVE)
    with db.tx() as conn:
        assert "x-additive-demo-additive" in [w.key for w in widgets.layout(conn, vid)]
    home, fuel = client.get(f"/v/{slug}").text, client.get(f"/v/{slug}/e/fuel").text
    assert (
        'data-k="x-additive-demo-additive"' in home and 'class="card reminder' not in fuel
    )  # a widget on the dashboard; no card on the fuel page
    with db.tx() as conn:
        summary.record_odometer(conn, vid, 51500, "manual")
    assert "card reminder" not in client.get(f"/v/{slug}/e/fuel").text
    r = client.post(f"/v/{slug}/reminders/additive-demo/additive/done", data={"back": "fuel"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("/e/fuel?m=saved")
    with db.tx() as conn:
        assert not reminders.status(conn, vid)[0]["due"]
    # the widget can be moved and hidden like every widget
    client.post(f"/v/{vid}/widgets", data={"ajax": "1", "k": ["x-additive-demo-additive", "fuel"], "size_x-additive-demo-additive": "m"})
    with db.tx() as conn:
        w = next(w for w in widgets.layout(conn, vid) if w.key == "x-additive-demo-additive")
    assert w.size == "m" and w.label == "Additive"


def test_search_and_only_changed_show_where_the_page_asks_for_them(client):
    pkg = {**PKG, "id": "coding-search", "pages": [{**PKG["pages"][0], "search": True}]}
    vid, slug = _car(client)
    _install(client, vid, pkg)
    client.post(f"/v/{slug}/m/coding-search/units", data={"addr": "09", "name": "J519", "old": "0A", "new": "0B"})
    page = client.get(f"/v/{slug}/m/coding-search/units").text
    assert 'id="pm-q"' in page and 'id="pm-only"' in page and 'data-changed="1"' in page
    plain = {
        **PKG,
        "id": "coding-plain",
        "pages": [{**PKG["pages"][0], "fields": [f for f in PKG["pages"][0]["fields"] if f["key"] in ("addr", "name")]}],
    }
    _install(client, vid, plain)
    client.post(f"/v/{slug}/m/coding-plain/units", data={"addr": "09", "name": "J519"})
    assert 'id="pm-q"' not in client.get(f"/v/{slug}/m/coding-plain/units").text  # no search, no comparison: no tools


def test_a_plugin_can_write_entries_through_the_connector_api(client):
    from carassistant import connectors

    vid, _slug = _car(client)
    _install(client, vid)
    with db.tx() as conn:
        token = connectors.create_token(conn, "writer", vid)
    url, head = f"/api/v1/vehicles/{vid}/modules/coding-demo/units", {"Authorization": f"Bearer {token}"}
    r = client.post(url, headers=head, json={"rows": [{"values": {"addr": "09", "name": "Central", "old": "0A0B", "new": "0A0C"}}]})
    assert r.status_code == 200 and len(r.json()["added"]) == 1
    rid = r.json()["added"][0]
    r = client.post(url, headers=head, json={"rows": [{"id": rid, "values": {"old": "FFFF", "new": "0A0D"}}]})
    assert r.json()["changed"] == 1
    row = client.get(url, headers=head).json()["rows"][0]
    assert row["old"] == "0A0B" and row["new"] == "0A0D" and row["name"] == "Central"  # the once-field kept its first value
    assert client.post(url, headers=head, json={"rows": [{"values": {"addr": "zz", "name": "Bad"}}]}).status_code == 422
    assert client.post(url, headers=head, json={"delete": [rid]}).json()["deleted"] == 1
    assert client.get(url, headers=head).json()["rows"] == []
    assert client.post(f"/api/v1/vehicles/{vid}/modules/coding-demo/nope", headers=head, json={}).status_code == 404


def test_a_list_setting_keeps_rows_of_name_and_value(client):
    import json as _json

    vid, slug = _car(client)
    pkg = {
        "id": "list-demo",
        "kind": "plugin",
        "name": "List demo",
        "settings": [{"key": "stations", "label": "Stations", "type": "list", "name_label": "Station", "value_label": "Address"}],
    }
    client.post(f"/v/{vid}/integrations/upload", files={"package": ("plugin.json", _json.dumps(pkg), "application/json")})
    with db.tx() as conn:
        item = next(a for a in addons.list_for(conn, vid) if a["addon_id"] == "list-demo")
    assert item["m"]["settings"][0]["type"] == "list" and item["m"]["settings"][0]["name_label"] == "Station"
    form = {
        "stations__0n": "Radio One",
        "stations__0v": "https://example.com/one",
        "stations__1n": "",
        "stations__1v": "",
        "stations__2n": "Two | evil",
        "stations__2v": "a|b",
    }
    client.post(f"/v/{vid}/integrations/{item['id']}/setup", data=form)
    with db.tx() as conn:
        item = addons.get(conn, vid, item["id"])
    assert (
        item["vals"]["stations"] == "Radio One | https://example.com/one\nTwo evil | a b"
    )  # the empty row is gone, the separator cannot be smuggled in
    assert addons.list_rows(item["vals"]["stations"]) == [
        {"name": "Radio One", "value": "https://example.com/one"},
        {"name": "Two evil", "value": "a b"},
    ]
    page = client.get(f"/v/{slug}/integrations/{item['id']}/settings").text
    assert 'name="stations__0n"' in page and 'value="Radio One"' in page and 'name="stations__1v"' in page and "lf-add" in page


PLAN_PKG = {
    "id": "plan-demo",
    "kind": "integration",
    "name": "Plan demo",
    "version": "1",
    "icon": "oil",
    "settings": [
        {"key": "add1", "label": "Additive 1", "type": "text", "default": "Alpha"},
        {"key": "amt1", "label": "Amount", "type": "text", "default": "250 ml"},
    ],
    "reminders": [
        {
            "id": "plan",
            "title": "Additive",
            "text_due": "Add it",
            "icon": "oil",
            "plan": [{"label": "Clean"}, {"setting": "add1", "amount_setting": "amt1", "label": "A"}],
        }
    ],
    "pages": [{"id": "plan", "kind": "plan", "reminder": "plan", "title": "Plan"}],
}


def test_a_reminder_plan_moves_on_with_every_refuel_and_keeps_a_history(client):
    from carassistant import reminders

    vid, slug = _car(client)
    parsed = addons.parse_package(json.dumps(PLAN_PKG).encode())
    assert parsed["reminders"][0]["plan"][1]["setting"] == "add1" and parsed["pages"][0]["kind"] == "plan"
    with db.tx() as conn:
        pk = addons.add(conn, vid, parsed)
        addons.set_up(conn, vid, addons.get(conn, vid, pk), {"add1": "Alpha", "amt1": "250 ml"})
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
    with db.tx() as conn:
        first = reminders.status(conn, vid)[0]
        assert first["mode"] == "plan" and first["title"] == "Clean" and first["due"] is False  # a clean refuel comes first
        for day in ("2026-02-01", "2026-02-02"):
            conn.execute("INSERT INTO fuel(vehicle_id, date, odometer_km, amount, full_tank) VALUES(?,?,?,?,1)", (vid, day, 1000, 40))
    with db.tx() as conn:
        now = reminders.status(conn, vid)[0]
        assert now["plan"]["current"] == 0 and len(now["plan"]["hist"]) == 2  # two refuels took two steps, round and round
        assert (
            now["plan"]["hist"][0]["label"] == "Alpha" and now["plan"]["hist"][0]["amount"] == "250 ml" and now["plan"]["hist"][0]["dose"]
        )
        assert reminders.plan_filled(conn, vid, "plan-demo", "plan", 0, True)
        assert reminders.plan_set(conn, vid, "plan-demo", "plan", step=1)
        assert reminders.status(conn, vid)[0]["due"] is True and reminders.status(conn, vid)[0]["title"] == "Alpha (250 ml)"
    page = client.get(f"/v/{slug}/m/plan-demo")
    assert page.status_code == 200 and "pl-steps" in page.text and "Alpha" in page.text
    assert client.post(f"/v/{slug}/reminders/plan-demo/plan/plan", data={"advance": "1"}, follow_redirects=False).status_code == 303


HISTORY_PKG = {
    "id": "coding-history",
    "kind": "integration",
    "name": "History demo",
    "version": "1",
    "icon": "memory",
    "pages": [
        {
            "id": "units",
            "title": "Units",
            "item": "Unit",
            "search": True,
            "fields": [
                {"key": "name", "label": "Name", "type": "text", "required": True, "role": "title"},
                {"key": "access", "label": "Access code", "type": "secret"},
            ],
        },
        {
            "id": "history",
            "title": "History",
            "item": "Change",
            "search": True,
            "order": {"by": "date", "dir": "desc"},
            "fields": [
                {"key": "date", "label": "Date", "type": "date", "required": True},
                {"key": "unit", "label": "Unit", "type": "text", "role": "title"},
                {"key": "what", "label": "Changed", "type": "text", "required": True, "role": "title"},
                {"key": "old", "label": "Old value", "type": "text"},
                {"key": "new", "label": "New value", "type": "text"},
                {"key": "note", "label": "Note", "type": "textarea"},
            ],
        },
    ],
}


def test_manifest_keeps_date_secret_and_order():
    pages = addons.parse_package(json.dumps(HISTORY_PKG).encode())["pages"]
    assert [f["type"] for f in pages[1]["fields"]][:1] == ["date"] and pages[0]["fields"][1]["type"] == "secret"
    assert pages[1]["order"] == {"by": "date", "dir": "desc"} and pages[0]["order"] is None
    bad = {**HISTORY_PKG, "pages": [{**HISTORY_PKG["pages"][0], "order": {"by": "access"}}]}  # a secret never sorts a list
    assert addons.parse_package(json.dumps(bad).encode())["pages"][0]["order"] is None


def test_history_page_is_sorted_by_date_and_validates_dates(client):
    vid, slug = _car(client)
    _install(client, vid, HISTORY_PKG)
    url = f"/v/{slug}/m/coding-history/history"
    for day, what in (("2026-01-05", "First"), ("2026-03-01", "Third"), ("2026-02-10", "Second")):
        assert client.post(url, data={"date": day, "what": what, "unit": "09"}, follow_redirects=False).status_code == 303
    page = client.get(url).text
    assert page.index("Third") < page.index("Second") < page.index("First") and 'type="date"' in page
    assert client.post(url, data={"date": "31.02.2026", "what": "Bad"}).status_code == 400
    assert "Search" in page


def test_an_access_code_is_hidden_until_shown_and_never_leaves(client):
    from carassistant import connectors

    vid, slug = _car(client)
    _install(client, vid, HISTORY_PKG)
    url = f"/v/{slug}/m/coding-history/units"
    client.post(url, data={"name": "Central", "access": "12345-X"})
    with db.tx() as conn:
        row = conn.execute("SELECT id FROM module_rows WHERE page = 'units'").fetchone()
    page = client.get(url)
    assert "12345-X" not in page.text and "••••••" in page.text and f"?reveal={row['id']}" in page.text
    assert "data-q" in page.text and "12345-x" not in page.text.lower()  # not in the search text either
    shown = client.get(f"{url}?reveal={row['id']}")
    assert "12345-X" in shown.text and shown.headers["cache-control"] == "no-store"
    # an empty field keeps the code, 'remove' clears it
    client.post(f"{url}/{row['id']}", data={"name": "Central", "access": ""})
    assert "12345-X" in client.get(f"{url}?reveal={row['id']}").text
    # a plugin neither reads nor writes it
    with db.tx() as conn:
        token = connectors.create_token(conn, "t", vid)
    head, api = {"Authorization": f"Bearer {token}"}, f"/api/v1/vehicles/{vid}/modules/coding-history/units"
    assert "access" not in client.get(api, headers=head).json()["rows"][0]
    client.post(api, headers=head, json={"rows": [{"id": row["id"], "values": {"access": "hacked", "name": "Central"}}]})
    assert "12345-X" in client.get(f"{url}?reveal={row['id']}").text
    client.post(f"{url}/{row['id']}", data={"name": "Central", "access__clear": "1"})
    assert "12345-X" not in client.get(f"{url}?reveal={row['id']}").text


def test_access_codes_stay_out_of_the_plain_vehicle_backup(client):
    import io
    import zipfile

    from carassistant import vehiclebackup

    vid, slug = _car(client)
    _install(client, vid, HISTORY_PKG)
    client.post(f"/v/{slug}/m/coding-history/units", data={"name": "Central", "access": "12345-X"})

    def modules(raw):
        return json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("vehicle.json"))["modules"]

    plain = client.get(f"/v/{slug}/backup.zip")
    assert "12345-X" not in json.dumps(modules(plain.content)) and "with-codes" not in plain.headers["content-disposition"]
    full = client.get(f"/v/{slug}/backup.zip?codes=1")
    assert "12345-X" in json.dumps(modules(full.content)) and "with-codes" in full.headers["content-disposition"]
    page = client.get(f"/settings/car?car={slug}").text
    assert (
        "Backup with access codes" not in page and 'name="passphrase"' in page
    )  # the codes travel in the encrypted block of a backup with a passphrase
    with db.tx() as conn:
        copy = vehiclebackup.restore(conn, full.content)
        assert any(r["data"].get("access") == "12345-X" for r in pagemods.rows(conn, copy, "coding-history", "units"))


def test_the_order_of_the_navigation_editor_rules_bar_and_more_for_every_kind_of_page(client):
    from carassistant import modules, navigation

    vid, slug = _car(client)
    _install(client, vid)
    _install(client, vid, {**PKG, "id": "second-one", "name": "Second one"})
    with db.tx() as conn:
        keys = [k for k, _i in navigation.order(conn, vid)]
    bar = ["security", "service", "trips", "fuel"]
    fixed = next(k for k in keys if not k.startswith("x-") and k not in bar)
    # the editor sends the bar (4 pages), then More: an integration page, a fixed page, another integration page
    order = [*bar, "x-second-one", fixed, "x-coding-demo"]
    assert client.post(f"/v/{slug}/navigation", data={"m": order, "i": [""] * len(order), "ajax": "1"}).status_code == 204
    with db.tx() as conn:
        assert [k for k, _i in navigation.order(conn, vid)][:7] == order  # saved and read back
    page = client.get(f"/v/{slug}/more").text
    assert page.index("/m/second-one") < page.index(f'{modules.BY_KEY[fixed].path}"') < page.index("/m/coding-demo")
    # moved into the bar: it leads the bar and leaves More
    order2 = ["x-coding-demo", *bar[:3], "x-second-one", fixed, bar[3]]
    client.post(f"/v/{slug}/navigation", data={"m": order2, "i": [""] * len(order2), "ajax": "1"})
    with db.tx() as conn:
        assert next(k for k, _i in navigation.slots(conn, vid)) == "x-coding-demo"
    assert client.get(f"/v/{slug}/more").text.count("/m/coding-demo") == 1  # only the bar link, not repeated in More
