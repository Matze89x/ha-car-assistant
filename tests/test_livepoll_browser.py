"""The page of a connected car reads itself again while the values change (static/livepoll.js): the wallbox card of the Charging page must follow what the server says
through every state - the pill, the ring, the note, the figures and the buttons always belong together. (They once did not: a part that was put into the page left
the tree it came from, and the next part was compared with the wrong one - a card with the pill of one state and the note of another.)

The pages are the real ones of the app, one for every state of the wallbox, with the buttons of the entities of Home Assistant; between them and a real browser stands
a small server that says "something changed" and hands out the page as the app rendered it at that moment. The browser polls ten times as fast as it does for a
person. Skipped without a browser (tools/cdp.py)."""

import json
import mimetypes
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from tests.test_habridge import BRIDGE
from tests.test_wallbox_card import CHARGING, electric, page, say

from carassistant import addons, db, ha

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

STATIC = ROOT / "carassistant" / "app" / "carassistant" / "static"
FAST = "(function () { var every = window.setInterval; window.setInterval = function (f, ms) { return every.call(window, f, ms === 4000 ? 40 : ms); }; })();"
BOUND = {  # what the administrator chose in Home Assistant: the buttons of the card come from these
    "wb_allow": "switch.wb_allowed",
    "wb_start": "button.wb_start",
    "wb_stop": "button.wb_stop",
    "wb_ack": "button.wb_ack",
    "charge_current_limit_a": "number.wb_limit",
    "charge_mode": "input_select.wb_mode",
}

# The card as the browser has it must read like the card the server hands out now (the blanks of the markup do not count, nor an opened fold-out).
SAME = """(async function (ms) {
  function norm(el) { return el ? el.outerHTML.replace(/ open=""/g, '').replace(/\\s+/g, ' ').replace(/> </g, '><') : ''; }
  var html = await (await fetch(location.pathname, { cache: 'no-store' })).text();
  var fresh = norm(new DOMParser().parseFromString(html, 'text/html').getElementById('wb')), live = '';
  var end = Date.now() + ms;
  while (Date.now() < end) {
    live = norm(document.getElementById('wb'));
    if (live === fresh) { return { ok: true, st: document.getElementById('wb').getAttribute('data-st') }; }
    await new Promise(function (resolve) { setTimeout(resolve, 25); });
  }
  return { ok: false, live: live, fresh: fresh };
})(MS)"""

# (what the wallbox says to the app, what its entities say in Home Assistant) - the states a car goes through, and a few jumps in between
STORY = [
    ("unplugged", {"charge_state": "unplugged", "charging": False, "plugged": False, "charge_total_kwh": 4300.5}, {}),
    ("plugged", {"charge_state": "plugged", "plugged": True}, {}),
    ("waiting", {"charge_state": "waiting", "battery_pct": 31, "charge_limit_pct": 80, "charge_mode": "Solar", "charge_current_limit_a": 16}, {"allowed": "off"}),
    ("charging", CHARGING, {}),
    ("charging", {"charge_power_kw": 7.2, "charge_session_kwh": 4.1, "charge_session_minutes": 33, "battery_pct": 53}, {}),  # only the figures move
    ("finished", {"charge_state": "finished", "charging": False, "battery_pct": 80, "charge_session_kwh": 28.4, "charge_session_minutes": 208}, {}),
    ("fault", {"charge_state": "fault", "charge_fault": "E-12 residual current"}, {}),
    ("charging", {**CHARGING, "charge_fault": ""}, {}),
    ("unplugged", {"charge_state": "unplugged", "charging": False, "plugged": False}, {}),
    ("fault", {"charge_state": "fault", "charge_fault": "E-12 residual current"}, {}),
]  # fmt: skip


def entities(allowed="on", limit="16", mode="Solar") -> dict[str, dict]:
    """What Home Assistant says about the entities the card may use."""

    def one(entity, state, **attributes):
        return entity, {"entity_id": entity, "state": state, "attributes": attributes}

    return dict(
        [
            one(BOUND["wb_allow"], allowed),
            one(BOUND["wb_start"], "unknown"),
            one(BOUND["wb_stop"], "unknown"),
            one(BOUND["wb_ack"], "unknown"),
            one(BOUND["charge_current_limit_a"], limit, min=6, max=16, step=1),
            one(BOUND["charge_mode"], mode, options=["Solar", "Fast", "Plan"]),
        ]
    )


class Server:
    """What the browser talks to: the page as the app rendered it last, and the number that tells that something changed."""

    def __init__(self):
        self.page, self.version, self.missing = "", 0, []  # (missing: what the page asked for and the server did not have)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = self.path.split("?")[0]
                if path == "/v/car/live-state":
                    body, kind = json.dumps({"v": owner.version}).encode(), "application/json"
                elif path == "/v/car/e/fuel":
                    body, kind = owner.page.encode(), "text/html; charset=utf-8"
                elif path.startswith("/static/") and ".." not in path and (STATIC / path[len("/static/") :]).is_file():
                    file = STATIC / path[len("/static/") :]
                    body, kind = file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream"
                elif path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                    return
                else:
                    owner.missing.append(path)
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.address = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def show(self, html: str) -> None:
        self.page = html
        self.version += 1

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def standalone(html: str) -> str:
    """The page of the app without its own scripts and styles, but with the one that is tested, and with the mark that makes it read itself again."""
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S)
    html = re.sub(r"<link\b[^>]*>", "", html)
    html = html.replace("<body", '<body data-live-poll="/v/car/live-state"', 1)
    return html.replace("</body>", '<script src="/static/livepoll.js"></script></body>', 1)


def where(a: str, b: str) -> str:
    """The first place two texts differ, with some of what stands around it."""
    n = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), min(len(a), len(b)))
    return f"at {n}: ...{a[max(0, n - 60) : n + 90]!r} / ...{b[max(0, n - 60) : n + 90]!r}"


@pytest.fixture()
def wallbox_car(client, monkeypatch):
    """An electric car with the Home Assistant plugin bound to a wallbox; ``current`` is what Home Assistant says (the test changes it)."""
    vid, slug = electric(client)
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, addons.parse_package(json.dumps(BRIDGE).encode()), source, None)
        conn.execute("UPDATE vehicle_addons SET active = 1 WHERE id = ?", (pk,))
        conn.executemany(
            "INSERT INTO ha_bindings(addon_pk, slot, entity, options) VALUES(?,?,?,'{}')",
            [(pk, slot, entity) for slot, entity in BOUND.items()],
        )
    current = {"states": entities()}
    monkeypatch.setattr(ha, "all_states", lambda seconds=4.0: current["states"])
    return vid, slug, current


def test_the_card_follows_the_server_through_every_state_and_moves_in_place_when_only_figures_change(client, wallbox_car):
    from cdp import Browser, find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    vid, slug, current = wallbox_car

    def render(data, entity):
        current["states"] = entities(**entity)
        say(vid, **data)
        return standalone(page(client, slug))

    server = Server()
    try:
        first = STORY[0]
        server.show(render(first[1], first[2]))
        with Browser() as b:
            b.call("Page.addScriptToEvaluateOnNewDocument", source=FAST)
            b.open(
                f"{server.address}/v/car/e/fuel", 1000, 900, settle=0.5
            )  # (the first look at the number only takes it as the one to compare with)
            b.run("window.__start = document.getElementById('wb').getAttribute('data-st')")
            assert b.run("window.__start") == first[0]
            for n, (state, data, entity) in enumerate(STORY[1:], start=1):
                figures_only = STORY[n - 1][0] == state == "charging"
                if figures_only:
                    b.run(
                        "window.__card = document.getElementById('wb'); window.__arc = document.querySelector('#wb .arc');"
                        "window.__dash = window.__arc.getAttribute('stroke-dasharray'); document.querySelector('#wb .wb-src').open = true"
                    )
                server.show(render(data, entity))
                seen = b.run(SAME.replace("MS", "5000"))
                assert seen["ok"], (
                    f"step {n} ({state}): the card is not the one the server says: {where(seen.get('live', ''), seen.get('fresh', ''))}"
                )
                assert seen["st"] == state, (n, seen)
                if figures_only:
                    kept = b.run(
                        "JSON.stringify({card: document.getElementById('wb') === window.__card, arc: document.querySelector('#wb .arc') === window.__arc,"
                        "moved: window.__arc.getAttribute('stroke-dasharray') !== window.__dash, open: document.querySelector('#wb .wb-src').open})"
                    )
                    assert json.loads(kept) == {"card": True, "arc": True, "moved": True, "open": True}, (
                        kept
                    )  # in place: the arc moves instead of jumping
            wrong = [e for e in b.drain() if e["kind"] in ("exception", "console")]
            assert not wrong, (
                wrong,
                server.missing,
            )  # nothing went wrong on the way (the card is also put in whole when it does: that is the safety net, not the way)
    finally:
        server.stop()
