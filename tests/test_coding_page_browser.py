"""The Coding page (the control units of the car and their codings) on a real browser, at the width of a small phone, a phone and a tablet.

It had been checked without any data: with a unit whose byte is opened, the editor was wider than the screen (a note field cut off at the edge, the
round bit buttons running out of the box). Needs a real browser (tools/cdp.py); skipped without one."""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

OLD = " ".join(f"{(i * 7) % 256:02X}" for i in range(40))
NEW = OLD.replace(OLD.split()[6], "FF", 1)  # one byte changed

# The opened editor of a changed byte: what leaves its box, what is too small to type in without a phone zooming, what is not even
MEASURE = """JSON.stringify((function () {
  var u = document.querySelector('.pm-unit'); u.open = true;
  var cells = u.querySelectorAll('.pm-byte'); cells[6].click();
  var sel = u.querySelector('.pm-sel'), sr = sel.getBoundingClientRect(), out = [];
  Array.prototype.forEach.call(sel.querySelectorAll('*'), function (e) {
    var r = e.getBoundingClientRect();
    if (r.width && (r.right > sr.right + 0.5 || r.left < sr.left - 0.5)) { out.push(e.className + ' ' + Math.round(r.right - sr.right)); }
  });
  var small = [];
  Array.prototype.forEach.call(u.querySelectorAll('input[type=text], input[type=number], textarea'), function (e) {
    if (e.type !== 'hidden' && parseFloat(getComputedStyle(e).fontSize) < 16) { small.push(e.className || e.name); }
  });
  var sizes = {};
  Array.prototype.forEach.call(cells, function (c) { var r = c.getBoundingClientRect(); sizes[Math.round(r.width) + 'x' + Math.round(r.height)] = 1; });
  return {
    shown: !sel.hidden, outside: out, small: small, cellSizes: Object.keys(sizes),
    pageScrolls: document.documentElement.scrollWidth > window.innerWidth + 1,
    spin: getComputedStyle(u.querySelector('.pm-gval') || u).getPropertyValue('-moz-appearance') || ''
  };
})())"""


@pytest.fixture(scope="module")
def coding():
    from cdp import Browser, find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    import make_screenshots as ms

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "app"
        data.mkdir()
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "carassistant" / "app") + os.pathsep + str(ROOT / "tools"),
            "CARASSISTANT_DATA": str(data),
            "CARASSISTANT_DEV": "1",
        }
        seed = "import sys; from pathlib import Path; import make_screenshots as ms; ms.seed(Path(sys.argv[1]), 'en')"
        subprocess.run([sys.executable, "-c", seed, str(data)], check=True, env=env, capture_output=True, timeout=120)
        install = (
            "import json, sys; from carassistant import addons, db; from tests.test_pagemods import PKG\n"
            "with db.tx() as conn:\n"
            "    vid = conn.execute('SELECT id FROM vehicles WHERE slug = ?', (sys.argv[1],)).fetchone()['id']\n"
            "    source = conn.execute('SELECT id FROM sources LIMIT 1').fetchone()['id']\n"
            "    pk = addons.add(conn, vid, addons.parse_package(json.dumps(PKG).encode()), source, '0' * 64)\n"
            "    conn.execute('UPDATE vehicle_addons SET active = 1 WHERE id = ?', (pk,))\n"
        )
        env["PYTHONPATH"] += os.pathsep + str(ROOT)
        subprocess.run([sys.executable, "-c", install, ms.DIESEL], check=True, env=env, capture_output=True, timeout=60, cwd=ROOT)
        port = ms.free_port()
        server = subprocess.Popen(
            [sys.executable, "-m", "carassistant"],
            env={**env, "CARASSISTANT_PORT": str(port)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            ms.wait_for(base + "/healthz")
            page = f"{base}/v/{ms.DIESEL}/m/coding-demo"
            with httpx.Client(follow_redirects=False, timeout=30) as c:
                for addr, name, old, new, notes in (
                    ("09", "Central electronics (a name that is rather long for a small screen)", OLD, NEW, "A long note " * 12),
                    ("5F", "Information electronics 1", "0A 0B 0C 0D", "0A 0B 0C 0D", ""),
                ):
                    r = c.post(page + "/units", data={"addr": addr, "name": name, "old": old, "new": new, "notes": notes})
                    assert r.status_code == 303, r.status_code
            with Browser() as b:
                yield b, page
        finally:
            server.terminate()
            server.wait(timeout=10)


@pytest.mark.parametrize("width", [320, 390, 768])
def test_the_opened_byte_editor_fits_the_screen(coding, width):
    import json

    b, page = coding
    b.open(page, width, 900, 1, settle=0.8)
    b.wait_for("document.querySelector('.pm-unit .pm-byte')", seconds=15)
    got = json.loads(b.run(MEASURE))
    time.sleep(0.2)
    assert got["shown"], got
    assert not got["outside"], got  # nothing of the editor stands out of its box
    assert not got["pageScrolls"], got  # and the page itself never scrolls sideways
    assert not got["small"], got  # a field below 16px makes iPhone Safari zoom in when it is touched
    assert len(got["cellSizes"]) == 1, got  # the bytes are one even grid: a changed byte is not bigger than the rest
