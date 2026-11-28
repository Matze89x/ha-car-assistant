"""The bar of the update window on a real browser (static/app.js, templates/_addon_cards.html): *Update now* stays on the page, the buttons give way to a bar that
says how far the update is - as the server says it, stage by stage and with the bytes that have come - the window cannot be closed while it works, and when the
update is over the page is read again with its message. At the width of a phone nothing runs out of the screen.

The page is the real one of the app, with the real update window of a package; between it and the browser stands a small server that plays the update with the real
``updprogress`` (the numbers and the words are the ones the app would send). Skipped without a browser (tools/cdp.py)."""

import json
import mimetypes
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from tests.test_update_window import LOG, REPO, _car, _offer, _pk

from carassistant import i18n, sources, updprogress

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

STATIC = ROOT / "carassistant" / "app" / "carassistant" / "static"
STEP = 0.35  # seconds between two words of the update that is played

# What the person sees while it runs: sampled every moment, from the page itself.
LOOK = """JSON.stringify((function () {
  var dlg = document.querySelector('dialog.upd-dlg'), box = dlg.querySelector('.upd-prog'), meter = box.querySelector('[role=progressbar]');
  var bar = dlg.querySelector('.form-bar'), x = dlg.querySelector('.vsw-x'), fill = box.querySelector('.bar-fill');
  var visible = function (e) { var r = e.getBoundingClientRect(); return getComputedStyle(e).display !== 'none' && r.width > 0 && r.height > 0; };
  return {
    open: dlg.open, busy: dlg.hasAttribute('data-busy'), shown: !box.hidden && visible(box),
    pct: Number(meter.getAttribute('aria-valuenow')), width: fill.style.width,
    label: box.querySelector('.upd-prog-label').textContent, number: box.querySelector('.upd-prog-pct').textContent,
    detail: box.querySelector('.upd-prog-detail').textContent, state: box.getAttribute('data-state'),
    buttons: visible(bar), close: getComputedStyle(x).pointerEvents,
    side: document.documentElement.scrollWidth > window.innerWidth + 1,
    out: dlg.scrollWidth > dlg.clientWidth + 1 || box.getBoundingClientRect().right > dlg.getBoundingClientRect().right + 1
  };
})())"""


class Server:
    """The app, as far as the window needs it: the page, the static files, the update that is played and the answers about how far it is."""

    def __init__(self, page: str, slug: str, pk: int, ok: bool = True):
        self.page, self.slug, self.pk, self.ok = page, slug, pk, ok
        self.done = threading.Event()
        owner = self
        t = i18n.translator("en")

        def numbers(value, digits=0):
            return f"{value:.{digits}f}"

        class Handler(BaseHTTPRequestHandler):
            def reply(self, status: int, body: bytes, kind: str):
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = self.path.split("?")[0]
                if path == f"/v/{owner.slug}/plugins":
                    self.reply(200, owner.page.encode(), "text/html; charset=utf-8")
                elif path == f"/v/{owner.slug}/integrations/{owner.pk}/update-progress":
                    run = parse_qs(urlsplit(self.path).query).get("run", [""])[0]
                    answer = updprogress.describe(updprogress.read(owner.pk, updprogress.token_of(run)), t, numbers)
                    self.reply(200, json.dumps(answer).encode(), "application/json")
                elif path.startswith("/static/") and ".." not in path and (STATIC / path[len("/static/") :]).is_file():
                    file = STATIC / path[len("/static/") :]
                    self.reply(200, file.read_bytes(), mimetypes.guess_type(file.name)[0] or "application/octet-stream")
                elif path == "/favicon.ico":
                    self.reply(204, b"", "image/x-icon")
                else:
                    self.reply(404, b"", "text/plain")

            def do_POST(self):
                if self.path != f"/v/{owner.slug}/integrations/{owner.pk}/update" or self.headers.get("X-Requested-With") != "fetch":
                    self.reply(400, b"", "text/plain")
                    return
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                pk = owner.pk
                run = updprogress.begin(pk, updprogress.plan_for(True, False), updprogress.token_of(self.headers.get("X-Update-Run")))
                for name, fraction, got, total in (
                    ("read", 0, None, None),
                    ("download", 0.5, 5_000_000, 10_000_000),
                    ("download", 1.0, 10_000_000, 10_000_000),
                    ("check", 0, None, None),
                    ("save", 0, None, None),
                ):
                    run.stage(name, fraction, got, total)
                    time.sleep(STEP)
                    if name == "download" and fraction == 0.5 and not owner.ok:
                        break
                run.finish(owner.ok)
                to = f"/v/{owner.slug}/plugins?m=" + ("addon.updated" if owner.ok else "err.src_net")
                self.reply(200, json.dumps({"to": to, "ok": owner.ok}).encode(), "application/json")
                owner.done.set()

            def log_message(self, *_args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.address = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def standalone(html: str) -> str:
    """The page of the app with its own script (and nothing else of the scripts)."""
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.S)
    return html.replace("</body>", '<script src="/static/app.js"></script></body>', 1)


@pytest.fixture()
def fake_source(monkeypatch):
    state = {"files": dict(REPO)}

    def fake_http(url, headers, check_host, limit=0):
        for path, text in state["files"].items():
            if url.endswith("/" + path):
                return text.encode()
        raise sources.SourceError("err.src_missing")

    monkeypatch.setattr(sources, "_http", fake_http)
    return state


@pytest.fixture()
def window(client, fake_source):
    """The real page of a car with a package that has an update (``page``, ``slug``, ``pk``)."""
    car = _car(client)
    client.post(f"/sources/{car.sid}/refresh", data={"kind": "plugin"})
    client.post(f"/v/{car.vid}/packages/{car.sid}/plugin/demo-one/install")
    _offer(client, fake_source, car.sid, "2.0", LOG)
    return standalone(client.get(f"/v/{car.slug}/plugins").text), car.slug, _pk(car.vid)


def _run(b, server, slug, pk, width):
    """Open the window and press *Update now*; the samples of what the person sees until the page has been read again."""
    b.open(f"{server.address}/v/{slug}/plugins", width, 900, settle=0.6)
    b.run(f"document.querySelector('[data-open=\"upd-{pk}\"]').click()")
    b.wait_for("document.querySelector('dialog.upd-dlg').open", seconds=5)
    before = json.loads(b.run(LOOK))
    b.run("document.querySelector('dialog.upd-dlg .form-bar .primary').click()")
    samples = []
    end = time.time() + 12
    while time.time() < end:
        if "m=" in (b.run("location.search") or ""):
            break
        try:
            samples.append(json.loads(b.run(LOOK)))
        except RuntimeError:  # the page is being read again
            break
        time.sleep(0.03)
    return before, samples


@pytest.mark.parametrize("width", [320, 1000])
def test_the_bar_follows_the_update_and_the_page_is_read_again_when_it_is_over(window, width):
    from cdp import Browser, find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    page, slug, pk = window
    server = Server(page, slug, pk)
    try:
        with Browser() as b:
            before, samples = _run(b, server, slug, pk, width)
            assert (
                before["open"] and not before["shown"] and before["buttons"] and not before["busy"]
            )  # the window is as it was: the bar waits
            assert samples, "the page did not stay"
            running = [s for s in samples if s["shown"]]
            assert running and all(
                s["open"] and s["busy"] and not s["buttons"] and s["close"] == "none" for s in running
            )  # the buttons gave way; it cannot be closed
            counted = [s["pct"] for s in running]
            assert counted == sorted(counted), counted  # it never goes back
            words = {s["label"] for s in running}
            assert {"Loading the package", "Checking and unpacking the files"} <= words, words
            mid = next(s for s in running if s["detail"])  # the bytes that have come
            assert mid["detail"] == "5.0 of 10.0 MB" and mid["number"] == f"{mid['pct']} %" and mid["width"] == f"{mid['pct']}%"
            assert not any(s["side"] or s["out"] for s in running), "something runs out of the window"
            server.done.wait(5)
            b.wait_for("location.search.indexOf('m=addon.updated') >= 0", seconds=8)  # read again, with its message
            assert b.run("location.pathname") == f"/v/{slug}/plugins"
    finally:
        server.stop()


def test_the_window_stays_open_when_escape_is_pressed_while_it_works_and_a_failure_shows_in_red(window):
    from cdp import Browser, find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    page, slug, pk = window
    server = Server(page, slug, pk, ok=False)
    try:
        with Browser() as b:
            b.open(f"{server.address}/v/{slug}/plugins", 390, 900, settle=0.6)
            b.run(f"document.querySelector('[data-open=\"upd-{pk}\"]').click()")
            b.wait_for("document.querySelector('dialog.upd-dlg').open", seconds=5)
            b.run("document.querySelector('dialog.upd-dlg .form-bar .primary').click()")
            b.wait_for("document.querySelector('.upd-prog .upd-prog-detail').textContent", seconds=5)  # it works now
            b.call("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
            b.call("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
            time.sleep(0.1)
            assert b.run("document.querySelector('dialog.upd-dlg').open") is True  # Escape did not close it
            b.wait_for("document.querySelector('.upd-prog').getAttribute('data-state') === 'failed'", seconds=8)
            failed = json.loads(b.run(LOOK))
            assert failed["label"] == "The update did not finish." and failed["pct"] < 100 and failed["state"] == "failed"
            b.wait_for("location.search.indexOf('m=err.src_net') >= 0", seconds=8)  # the page says what went wrong
    finally:
        server.stop()
