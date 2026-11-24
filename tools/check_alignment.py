"""Is the first block of every page level with the first card of the More list?

Wide screens show the More list on the left and the page on the right (docs/design.md, "Page pattern"). The first card of the page has to start on
exactly the same line as the first card of the list - on every page, at every width, also with a message above, an empty page or a car with little
data. A page that starts a few pixels lower looks broken, and it is easy to do by accident (a card with its own top margin inside a grid cell).

This opens every page of the More list in a headless Chrome (tools/cdp.py) on a temporary demo installation, measures both lines and says which
page is off. ``tests/test_page_alignment.py`` runs it when Chrome is installed.

  python tools/check_alignment.py [--widths 1000,1200,1440]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

TOLERANCE = 1.0  # pixels

# the first block that is really drawn (a notice tile, a tab bar, a card ...) against the first card of the More list
MEASURE = r"""
(function () {
  var list = document.querySelector('.more-pane .mgroup');
  if (!list) { return JSON.stringify({err: 'no More list'}); }
  var left = list.getBoundingClientRect().top + scrollY;
  var main = document.querySelector('.vpage > main') || document.querySelector('main');
  function boxed(e) {
    var s = getComputedStyle(e);
    return s.backgroundColor !== 'rgba(0, 0, 0, 0)' || parseFloat(s.borderTopWidth) > 0 || s.backgroundImage !== 'none';
  }
  var kids = Array.prototype.filter.call(main.children, function (e) {
    return e.getBoundingClientRect().height > 0 && !e.classList.contains('page-head') && e.tagName !== 'TEMPLATE' && getComputedStyle(e).position !== 'fixed';
  });
  if (!kids.length) { return JSON.stringify({err: 'nothing under the header'}); }
  var c = kids[0], depth = 0;
  while (c.firstElementChild && depth < 4 && !boxed(c)) { c = c.firstElementChild; depth++; }  /* down to the first thing with a box: a wrapper does not count */
  var pane = document.querySelector('.more-pane'), head = main.querySelector(':scope > .page-head'), paneHead = pane.querySelector('.page-head');
  return JSON.stringify({
    left: left, top: c.getBoundingClientRect().top + scrollY, what: c.tagName + '.' + String(c.className || '').split(' ').slice(0, 3).join('.'),
    gap: main.getBoundingClientRect().left - pane.getBoundingClientRect().right,  /* the space between the list and the page */
    headDiff: head && paneHead ? head.getBoundingClientRect().top - paneHead.getBoundingClientRect().top : 0  /* "More" and the title of the page on one line */
  });
})()
"""


def _seed(data: Path, lang: str = "en") -> None:
    code = "import sys; from pathlib import Path; sys.path.insert(0, %r); import make_screenshots as ms; ms.seed(Path(%r), %r)" % (str(ROOT / "tools"), str(data), lang)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "carassistant" / "app") + os.pathsep + str(ROOT / "tools")}
    subprocess.run([sys.executable, "-c", code], check=True, env=env, capture_output=True, timeout=120)  # noqa: S603


def page_list(b, base: str, ms) -> list[str]:
    """Every page of the More list of a car with much data and of one with little, plus the pages that are not in the list (settings, plugins ...)."""
    pages: list[str] = []
    for car in (ms.DIESEL, ms.COMPACT):  # a car with much data and one with little
        b.open(f"{base}/v/{car}/more", 1200, 900, 1, settle=2.0)
        pages += json.loads(b.run("JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.more-pane a.mi[href]'), function (a) { return a.getAttribute('href'); }))"))
    return pages + [
        "/about",
        "/vehicles",
        "/settings/user",
        "/settings/system",
        f"/settings/car?car={ms.DIESEL}",
        f"/v/{ms.DIESEL}/edit",
        f"/v/{ms.DIESEL}/docs?m=err.required",  # a message above the page
        f"/v/{ms.DIESEL}/plugins/connections",
        f"/v/{ms.DIESEL}/plugins/add",
        f"/v/{ms.DIESEL}/plugins/sources",
        f"/v/{ms.DIESEL}/integrations/add",
        f"/v/{ms.DIESEL}/integrations/sources",
        # the two demo plugins of make_screenshots.seed (the first two packages of the car: ids 1 and 2): the pages that belong to a plugin's tile
        f"/v/{ms.DIESEL}/integrations/1/logs",
        f"/v/{ms.DIESEL}/integrations/1/info",
        f"/v/{ms.DIESEL}/integrations/1/settings",
        f"/v/{ms.DIESEL}/integrations/2/guide",
    ]


def run(widths: tuple[int, ...] = (1000, 1200, 1440)) -> list[str]:
    """The pages that start off the line of the More list: ``["/about at 1200 px: 13.6 px lower (section.card.about-hero)", ...]``."""
    import make_screenshots as ms
    from cdp import Browser

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        _seed(data)
        port = ms.free_port()
        env = {**os.environ, "CARASSISTANT_DATA": str(data), "CARASSISTANT_DEV": "1", "CARASSISTANT_PORT": str(port)}
        env["PYTHONPATH"] = str(ROOT / "carassistant" / "app")
        server = subprocess.Popen([sys.executable, "-m", "carassistant"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        try:
            base = f"http://127.0.0.1:{port}"
            ms.wait_for(base + "/healthz")
            with Browser() as b:
                pages = page_list(b, base, ms)
                for width in widths:
                    gaps: dict[str, float] = {}
                    for page in dict.fromkeys(pages):
                        b.open(base + page, width, 900, 1, settle=0.35)
                        got = json.loads(b.run(MEASURE))
                        if "err" in got:
                            problems.append(f"{page} at {width} px: {got['err']}")
                        else:
                            diff = got["top"] - got["left"]
                            if abs(diff) > TOLERANCE:
                                problems.append(f"{page} at {width} px: {abs(diff):.1f} px {'lower' if diff > 0 else 'higher'} than the More list ({got['what']})")
                            if abs(got["headDiff"]) > TOLERANCE:
                                problems.append(f"{page} at {width} px: the title is {abs(got['headDiff']):.1f} px off the line of the word More")
                            gaps[page] = round(got["gap"], 1)
                    common = max(set(gaps.values()), key=list(gaps.values()).count) if gaps else 0
                    problems += [f"{p} at {width} px: {g} px between the list and the page (the others: {common} px)" for p, g in gaps.items() if abs(g - common) > TOLERANCE]
        finally:
            server.terminate()
            server.wait(timeout=10)
    return problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--widths", default="1000,1200,1440")
    found = run(tuple(int(w) for w in ap.parse_args().widths.split(",")))
    print("\n".join(found) if found else "every page starts level with the More list")
    sys.exit(1 if found else 0)
