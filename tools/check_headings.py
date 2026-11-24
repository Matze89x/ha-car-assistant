"""Do the headings of every page follow the design book?

A heading that stands on its own on a page (outside a card, a notice or a tile) is a *section label* (docs/design.md, "Section labels"): 11 px, upper
case, the dim colour, left aligned, the letter spacing of ``.vd-group-h``. No page may have a label of its own - not centred, not larger, not another
colour. A title inside a card is a card title (its own rule) and is not looked at here.

This opens every page of the More list in a headless Chrome (tools/cdp.py) on a temporary demo installation and compares each free-standing heading
with a real ``.vd-group-h`` of the same page, so a theme that recolours the labels does not matter. ``tests/test_page_headings.py`` runs it when
Chrome is installed.

  python tools/check_headings.py [--width 1200]
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

MEASURE = r"""
(function () {
  var main = document.querySelector('.vpage > main') || document.querySelector('main');
  if (!main) { return JSON.stringify({err: 'no main'}); }
  var ref = document.createElement('div');
  ref.className = 'vd-group-h';
  ref.textContent = 'x';
  main.appendChild(ref);
  var rs = getComputedStyle(ref);
  var want = {fontSize: rs.fontSize, fontWeight: rs.fontWeight, color: rs.color, letterSpacing: rs.letterSpacing, textTransform: rs.textTransform};
  function boxed(e) {
    var s = getComputedStyle(e);
    return s.backgroundColor !== 'rgba(0, 0, 0, 0)' || parseFloat(s.borderTopWidth) > 0 || s.backgroundImage !== 'none';
  }
  var bad = [];
  Array.prototype.forEach.call(main.querySelectorAll('h2, h3, h4, .vd-group-h, .rec-month, .mg-head'), function (e) {
    if (e === ref || !e.getBoundingClientRect().height || e.closest('.page-head, dialog, template, .more-pane, nav, .vsw')) { return; }
    for (var p = e.parentElement; p && p !== main; p = p.parentElement) { if (boxed(p)) { return; } }  /* inside a box: a card title, not a section label */
    var s = getComputedStyle(e), why = [];
    if (e.classList.contains('mg-head')) {  /* the wrapper of a label: the label inside is looked at itself; the wrapper must not centre it */
      if (['center', 'flex-end', 'right'].indexOf(s.justifyContent) >= 0 || s.textAlign === 'center') { why.push('centred'); }
    } else {
      Object.keys(want).forEach(function (k) { if (s[k] !== want[k]) { why.push(k + ' ' + s[k] + ' (should be ' + want[k] + ')'); } });
      if (['start', 'left'].indexOf(s.textAlign) < 0) { why.push('textAlign ' + s.textAlign); }
    }
    if (why.length) { bad.push({what: e.tagName.toLowerCase() + '.' + String(e.className || '').split(' ').slice(0, 2).join('.'), text: (e.textContent || '').trim().slice(0, 30), why: why.join(', ')}); }
  });
  ref.remove();
  return JSON.stringify({bad: bad});
})()
"""


def run(width: int = 1200) -> list[str]:
    """The free-standing headings that do not look like the section label of the design book: ``["/about: h2 'Built with' - fontSize 12px (should be 11px)", ...]``."""
    import check_alignment
    import make_screenshots as ms
    from cdp import Browser

    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp)
        check_alignment._seed(data)
        port = ms.free_port()
        env = {**os.environ, "CARASSISTANT_DATA": str(data), "CARASSISTANT_DEV": "1", "CARASSISTANT_PORT": str(port)}
        env["PYTHONPATH"] = str(ROOT / "carassistant" / "app")
        server = subprocess.Popen([sys.executable, "-m", "carassistant"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
        try:
            base = f"http://127.0.0.1:{port}"
            ms.wait_for(base + "/healthz")
            with Browser() as b:
                for page in dict.fromkeys(check_alignment.page_list(b, base, ms)):
                    b.open(base + page, width, 900, 1, settle=0.35)
                    got = json.loads(b.run(MEASURE))
                    if "err" in got:
                        problems.append(f"{page}: {got['err']}")
                    problems += [f"{page}: {h['what']} '{h['text']}' - {h['why']}" for h in got["bad"]]
        finally:
            server.terminate()
            server.wait(timeout=10)
    return problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=1200)
    found = run(ap.parse_args().width)
    print("\n".join(found) if found else "every free-standing heading is a section label of the design book")
    sys.exit(1 if found else 0)
