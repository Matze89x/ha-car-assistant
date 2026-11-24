"""The video on Home: it plays once and then stands on its last frame - and the box is NEVER empty.

After a long break the video did not start any more (the phone refused it, the page came back from the background, the file was slow) and Home showed an
empty box where the car should be. Now a picture always stands in until the video really plays: the last frame of the last visit, else the video's own picture,
and it stays when the video cannot start. Needs a real browser (tools/cdp.py) and ffmpeg for a small test video; skipped without them."""

import base64
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

REFUSE = "HTMLMediaElement.prototype.play = function () { return Promise.reject(new DOMException('no', 'NotAllowedError')); };"
# a phone in low-power / data-saving mode: it loads nothing until the person taps, and play() neither works nor says no
HANGS = (
    "Object.defineProperty(HTMLMediaElement.prototype, 'preload', { get: function () { return 'none'; }, set: function () {} });"
    "HTMLMediaElement.prototype.play = function () { return new Promise(function () {}); };"
    "var _src = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');"
    "Object.defineProperty(HTMLMediaElement.prototype, 'src', { get: function () { return _src.get.call(this); }, set: function (v) { this.setAttribute('data-wanted', v); } });"
)
# the picture takes its time (a slow connection, a busy phone) while the video is refused at once
SLOW_PICTURE = (
    "var _is = Object.getOwnPropertyDescriptor(HTMLImageElement.prototype, 'src');"
    "Object.defineProperty(HTMLImageElement.prototype, 'src', { get: function () { return _is.get.call(this); },"
    " set: function (v) { var me = this; setTimeout(function () { _is.set.call(me, v); }, 900); } });"
)
STATE = """JSON.stringify((function () {
  var w = document.querySelector('.hero-media'); if (!w) { return {none: true}; }
  var pic = w.querySelector('.hero-frozen'), v = w.querySelector('video');
  var r = w.getBoundingClientRect();
  return {
    classes: w.className, h: Math.round(r.height),
    still: pic ? pic.tagName : null, stillSrc: pic && pic.tagName === 'IMG' ? pic.src.slice(0, 22) : null,
    stillOpacity: pic ? parseFloat(getComputedStyle(pic).opacity) : null, stillWidth: pic ? Math.round(pic.getBoundingClientRect().width) : 0,
    videoHidden: v ? v.classList.contains('vgone') : null, saved: !!localStorage.getItem('ca.hero.last')
  };
})())"""


class Hero:
    def __init__(self, b, base: str, car: str, media: int, data: Path, poster: Path, slug: str):
        self.b, self.base, self.car, self.media, self.data, self.poster, self.slug = b, base, car, media, data, poster, slug

    def visit(self, script: str = "", keep_last: bool = True, settle: float = 0.5) -> None:
        """Home as a new visit opens it: nothing of an earlier session, the durable storage stays (or is emptied)."""
        self.b.open(self.base + "/healthz", 390, 900, 1, settle=0.1)
        self.b.run("sessionStorage.clear();" + ("" if keep_last else "localStorage.removeItem('ca.hero.last');"))
        ident = self.b.call("Page.addScriptToEvaluateOnNewDocument", source=script or "0;")["identifier"]
        self.b.open(self.car, 390, 900, 1, settle=settle)
        self.b.call("Page.removeScriptToEvaluateOnNewDocument", identifier=ident)

    def state(self) -> dict:
        return json.loads(self.b.run(STATE))

    def remember(self) -> None:
        """What an earlier visit leaves behind: its last frame, kept for good."""
        img = "data:image/jpeg;base64," + base64.b64encode(self.poster.read_bytes()).decode()
        self.b.open(self.base + "/healthz", 390, 900, 1, settle=0.1)
        key = json.dumps(f"/v/{self.slug}/media/{self.media}/file")  # the address the page itself gives the video (data-src)
        self.b.run(f"localStorage.setItem('ca.hero.last', JSON.stringify({{src: {key}, img: {json.dumps(img)}, bg: ''}}))")


@pytest.fixture(scope="module")
def hero():
    """A demo car whose Home shows a video (with its own picture) and a headless Chrome."""
    from cdp import Browser, find_chrome

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    if not shutil.which("ffmpeg"):
        pytest.skip("no ffmpeg for a test video")
    import make_screenshots as ms

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        clip, poster = data / "clip.webm", data / "poster.jpg"
        made = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc=size=320x180:rate=25",
                "-t",
                "1.2",
                "-c:v",
                "libvpx",
                "-b:v",
                "300k",
                str(clip),
            ],
            capture_output=True,
            timeout=60,
        )
        if made.returncode != 0:
            pytest.skip("no VP8 encoder for a test video")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-frames:v", "1", str(poster)], check=True, capture_output=True, timeout=60
        )
        (data / "app").mkdir()
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "carassistant" / "app") + os.pathsep + str(ROOT / "tools"),
            "CARASSISTANT_DATA": str(data / "app"),
            "CARASSISTANT_DEV": "1",
        }
        seed = "import sys; from pathlib import Path; import make_screenshots as ms; ms.seed(Path(sys.argv[1]), 'en')"
        subprocess.run([sys.executable, "-c", seed, str(data / "app")], check=True, env=env, capture_output=True, timeout=120)
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
            car = f"{base}/v/{ms.DIESEL}"
            with httpx.Client(follow_redirects=False, timeout=60) as c:
                up = c.post(
                    f"{car}/media",
                    files={
                        "file": ("hero.webm", clip.read_bytes(), "video/webm"),
                        "poster": ("poster.jpg", poster.read_bytes(), "image/jpeg"),
                    },
                )
                assert up.status_code == 303, up.text
                db = sqlite3.connect(data / "app" / "carassistant.db")
                mid = db.execute("SELECT id FROM vehicle_media WHERE kind = 'video' ORDER BY id DESC LIMIT 1").fetchone()[0]
                db.close()
                assert c.post(f"{car}/media/{mid}/use", data={"for": "home"}).status_code == 303
            with Browser() as b:
                yield Hero(b, base, car, mid, data, poster, ms.DIESEL)
        finally:
            server.terminate()
            server.wait(timeout=10)


def test_the_video_plays_and_its_last_frame_stands_and_is_kept(hero):
    hero.visit(keep_last=False)
    hero.b.drain()
    hero.b.wait_for("document.querySelector('.hero-media.vplay')", seconds=20)
    hero.b.wait_for(
        "localStorage.getItem('ca.hero.last')", seconds=20
    )  # the video ended: its last frame is kept for good, not only for the session
    end = hero.state()
    assert (
        end["still"] == "CANVAS" and end["videoHidden"] is True and end["stillOpacity"] == 1 and end["h"] > 100
    )  # the last frame, standing
    assert not [e for e in hero.b.drain() if e["kind"] in ("exception", "csp")]


def test_a_refused_start_leaves_the_last_frame_of_the_earlier_visit(hero):
    hero.remember()
    hero.visit(REFUSE)
    hero.b.wait_for("document.querySelector('.hero-media .hero-frozen')", seconds=10)
    s = hero.state()
    assert s["still"] == "IMG" and s["stillSrc"].startswith("data:image/jpeg") and s["stillOpacity"] == 1 and s["stillWidth"] > 100
    assert "vplay" in s["classes"] and "failed" not in s["classes"] and s["h"] > 100


def test_a_start_that_hangs_shows_a_picture_from_the_first_moment(hero):
    hero.remember()
    hero.visit(HANGS, settle=0.3)
    hero.b.wait_for("document.querySelector('.hero-media .hero-frozen')", seconds=5)
    s = hero.state()
    assert (
        s["still"] == "IMG" and "vplay" in s["classes"] and s["stillOpacity"] == 1 and s["h"] > 100
    )  # not an empty box while nothing happens


def test_the_videos_own_picture_stands_in_when_nothing_was_kept(hero):
    hero.visit(REFUSE, keep_last=False)
    hero.b.wait_for("document.querySelector('.hero-media .hero-frozen')", seconds=10)
    s = hero.state()
    assert (
        s["still"] == "IMG"
        and "failed" not in s["classes"]
        and "/poster" in hero.b.run("document.querySelector('.hero-media .hero-frozen').src")
    )


def test_a_missing_video_file_keeps_the_picture(hero):
    hero.remember()
    for f in (hero.data / "app").rglob("*.webm"):
        f.unlink()
    hero.b.call(
        "Network.setCacheDisabled", cacheDisabled=True
    )  # the file is cached for a year (immutable): this visit must really ask for it
    hero.visit()
    hero.b.wait_for("document.querySelector('.hero-media .hero-frozen')", seconds=10)
    time.sleep(1.0)
    s = hero.state()
    assert s["still"] == "IMG" and s["stillOpacity"] == 1 and s["h"] > 100


def test_a_start_that_is_refused_before_the_picture_has_arrived_waits_for_the_picture(hero):
    hero.visit(REFUSE + SLOW_PICTURE, keep_last=False, settle=0.2)
    hero.b.wait_for(
        "document.querySelector('.hero-media.vplay')", seconds=10
    )  # the picture arrives (after the video was refused) and stands
    time.sleep(0.3)
    s = hero.state()
    assert s["still"] == "IMG" and "failed" not in s["classes"] and "vplay" in s["classes"] and s["stillOpacity"] == 1 and s["h"] > 100
