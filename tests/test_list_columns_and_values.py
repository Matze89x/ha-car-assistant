"""A column of a ``list`` can be a number, a date or a choice (not only a text), and a ``value`` setting can write a time in the system's zone and put
a coloured dot in front of known texts. Packages that do neither are unchanged. docs/plugins.md."""

import json
import re

from tests.test_web import create_vehicle, slug

from carassistant import addons, db

PKG = {
    "id": "typed-cols",
    "kind": "plugin",
    "name": "Typed columns",
    "version": "1",
    "settings": [
        {
            "key": "licences",
            "type": "list",
            "label": "Licences",
            "name_label": "Name",
            "value_label": "Key",
            "columns": [
                {"key": "since", "label": "Since", "type": "date"},
                {"key": "price", "label": "Price", "type": "number"},
                {
                    "key": "level",
                    "label": "Level",
                    "type": "select",
                    "options": [{"value": "basic", "label": "Basic"}, {"value": "pro", "label": "Pro, with a comma?"}],
                },
            ],
        },
        {
            "key": "link",
            "type": "value",
            "label": "Link",
            "state": {"ok": ["connected", 1], "warn": ["waiting"], "bad": ["error", "lost"], "grey": ["x"]},
        },
        {"key": "seen", "type": "value", "label": "Last seen", "format": "datetime"},
        {"key": "since", "type": "value", "label": "Since", "format": "date"},
        {"key": "other", "type": "value", "label": "Other", "format": "weird"},
    ],
}


def _parsed():
    return addons.parse_package(json.dumps(PKG).encode())


def test_the_types_of_the_columns_are_read_and_a_text_column_stays_as_it_was():
    cols = {c["key"]: c for c in _parsed()["settings"][0]["columns"]}
    assert cols["since"]["type"] == "date" and cols["price"]["type"] == "number"
    assert cols["level"]["type"] == "select" and [o["value"] for o in cols["level"]["options"]] == ["basic", "pro"]
    plain = addons.parse_package(
        json.dumps(
            {
                **PKG,
                "settings": [
                    {
                        "key": "l",
                        "type": "list",
                        "label": "L",
                        "columns": [
                            {"key": "a", "label": "A"},
                            {"key": "b", "type": "select", "label": "B"},
                            {"key": "c", "type": "weird"},
                        ],
                    }
                ],
            }
        ).encode()
    )["settings"][0]["columns"]
    assert all("type" not in c for c in plain)  # no type, a choice without options, an unknown type: a text, as before


def test_a_value_has_a_time_format_and_dots_for_known_texts():
    by = {f["key"]: f for f in _parsed()["settings"]}
    assert by["link"]["state"] == {"ok": ["connected", "1"], "warn": ["waiting"], "bad": ["error", "lost"]}  # an unknown level is left out
    assert by["seen"]["format"] == "datetime" and by["since"]["format"] == "date" and "format" not in by["other"]


def test_cells_are_checked_by_their_type_and_numbers_are_stored_with_a_point():
    manifest = _parsed()
    cols = manifest["settings"][0]["columns"]

    def form(since="", price="", level="", row=0):
        return {
            f"licences__{row}n": "A",
            f"licences__{row}v": "k",
            f"licences__{row}c0": since,
            f"licences__{row}c1": price,
            f"licences__{row}c2": level,
        }

    ok = lambda **kw: not addons.check_settings(manifest, form(**kw), {})  # noqa: E731
    assert ok(since="2026-11-24", price="3,5", level="pro") and ok() and ok(price="12")
    assert not ok(since="24.11.2026") and not ok(since="2026-13-01")  # a date is YYYY-MM-DD
    assert not ok(price="abc") and not ok(price="1,2,3")
    assert not ok(level="gold")  # one of the choices
    assert addons.check_settings(manifest, form(price="x"), {})["licences"] == "err.cell_type"
    stored = addons.clean_settings(manifest, form(since="2026-11-24", price="3,5", level="pro"), {})["licences"]
    assert stored == "A | k | 2026-11-24 | 3.5 | pro"  # 3,5 is stored as 3.5
    assert addons.list_cells_fit("licences", form(), cols)


def test_a_service_gets_the_numbers_of_a_number_column_as_numbers():
    cols = _parsed()["settings"][0]["columns"]
    rows = addons.list_rows("A | k | 2026-11-24 | 3.5 | pro\nB | k2 | | 4 | basic\nC | k3 | | | ", cols)
    typed = addons.typed_rows(rows, cols)
    assert [r["price"] for r in typed] == [3.5, 4, None]  # a whole number is an int, an empty cell is null
    assert typed[0]["since"] == "2026-11-24" and typed[0]["level"] == "pro"  # the rest stays text
    assert addons.typed_rows(rows, [c for c in cols if c["key"] != "price"]) is rows  # no number column: the rows as they were


def test_the_settings_page_draws_the_right_input_for_each_column_and_the_dots(client):
    manifest = _parsed()
    vid = create_vehicle(client)
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, manifest, source, "0" * 64)
        conn.execute(
            "UPDATE vehicle_addons SET settings = ? WHERE id = ?",
            (
                json.dumps(
                    {
                        "licences": "A | k | 2026-11-24 | 3.5 | pro",
                        "link": "connected",
                        "seen": "2026-11-22T10:20:00+00:00",
                        "since": "2026-11-22",
                    }
                ),
                pk,
            ),
        )
    page = client.get(f"/v/{slug(vid)}/integrations/{pk}/settings").text
    row = page[page.index('class="lf-row"') :]
    row = row[: row.index("</span>")]  # the first row
    assert re.search(r'<input type="date" name="licences__0c0"[^>]*value="2026-11-24"', row)
    assert re.search(r'<input type="number" step="any" inputmode="decimal" name="licences__0c1"[^>]*value="3.5"', row)
    assert re.search(
        r'<select name="licences__0c2" data-cell="c2"[^>]*><option value="">Level</option><option value="basic">Basic</option><option value="pro" selected>',
        row,
    )
    assert 'class="av-dot ok"' in page  # "connected"
    # a time in the system's zone and writing (the zone of the machine decides the hour): no "T" and no "+00:00" of the stored text
    assert re.search(r'Last seen</span><b class="av-v">2026-11-2[123] \d\d:\d\d</b>', page)
    assert re.search(r'Since</span><b class="av-v">2026-11-22</b>', page)
    assert "T10:20:00+00:00" not in page
