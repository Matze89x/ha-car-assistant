"""The standing rules of the design on every page, measured in a headless Chrome (tools/pagecheck.py) - the things that kept slipping through by hand:

* **a button never wraps its label** and **a row of buttons stays on ONE line** (docs/design.md, "Light buttons, one line"),
* **the buttons of one row are the same height**,
* **one main action** (``.primary``) per card or form,
* **the buttons of a form bar sit bottom right** (the bar is right aligned; only the guide's Back / Next bars spread out),
* **a thing you tap is big enough**: 30 px at least (the area that takes a tap counts, a ``::after`` that grows it too),
* **every button has a name** (text, ``aria-label`` or ``title``) and **every field a label**,
* **nothing is wider than the screen** (no sideways scrolling) and **no text runs out of its own box**.

Folded forms (the add form, the edit form of a card) are opened first so that the buttons inside are measured, too. German has the longest words, a
phone the least room: ``tests/test_page_ui.py`` runs German at phone width and English wide, when Chrome is installed.

  python tools/check_ui.py [--width 360] [--lang de]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

MEASURE = r"""
(function () {
  var out = [];
  function vis(e) { var r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && !e.closest('[hidden], template, dialog:not([open])'); }
  var SKIP = '.page-head, nav, .tabbar, .more-pane, .vsw, .odo-card, .odo-flip, .wd-ctl';  /* round header buttons, bars, the dashboard's own controls */
  function where(e) { var p = e.parentElement; return p.tagName.toLowerCase() + '.' + String(p.className).split(' ').slice(0, 2).join('.'); }
  function name(e) { return (e.textContent || '').trim().slice(0, 24) || e.getAttribute('aria-label') || e.getAttribute('title') || ''; }
  var ctl = Array.prototype.filter.call(document.querySelectorAll('button, a.button, a.ghost-btn, input[type=submit]'), function (e) { return vis(e) && !e.closest(SKIP); });

  ctl.forEach(function (e) {
    var w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT), n, lines = 1;
    while ((n = w.nextNode())) {
      if (!n.textContent.trim()) { continue; }
      var r = document.createRange(); r.selectNodeContents(n);
      var tops = Array.prototype.map.call(r.getClientRects(), function (x) { return Math.round(x.top); });
      if (tops.length && Math.max.apply(null, tops) - Math.min.apply(null, tops) > 4) { lines = 2; }
    }
    if (lines > 1) { out.push('the label of a button wraps: "' + name(e) + '" (in ' + where(e) + ')'); }
    if (!name(e)) { out.push('a button without a name (in ' + where(e) + ')'); }
    var b = e.getBoundingClientRect(), w2 = b.width, h2 = b.height, ps = getComputedStyle(e, '::after');
    if (ps.content !== 'none' && ps.position === 'absolute') {  /* an ::after that grows the area that takes a tap */
      w2 += Math.max(0, -parseFloat(ps.left) || 0) + Math.max(0, -parseFloat(ps.right) || 0);
      h2 += Math.max(0, -parseFloat(ps.top) || 0) + Math.max(0, -parseFloat(ps.bottom) || 0);
    }
    if (w2 < 30 || h2 < 30) { out.push('too small to tap (' + Math.round(w2) + 'x' + Math.round(h2) + '): "' + (name(e) || e.className) + '" (in ' + where(e) + ')'); }
  });

  var de = document.documentElement, cw = de.clientWidth;  /* nothing may be wider than the screen: no sideways scrolling on a phone */
  if (de.scrollWidth > cw + 1) {
    var wide = Array.prototype.filter.call(document.body.querySelectorAll('*'), function (e) {
      var r = e.getBoundingClientRect();
      return r.width > 0 && r.right > cw + 1 && !e.closest('svg, [hidden], template, dialog:not([open]), .wd-ghost') && getComputedStyle(e).position !== 'fixed' && e.parentElement.getBoundingClientRect().right <= cw + 1;
    });
    out.push('the page is wider than the screen (' + de.scrollWidth + ' > ' + cw + ' px)' + (wide.length ? ': ' + wide[0].tagName.toLowerCase() + '.' + String(wide[0].className).split(' ').slice(0, 2).join('.') : ''));
  }

  var tw = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT), te, spilled = {};  /* text that runs out of its own box (a long address under a badge) */
  while ((te = tw.nextNode())) {
    if (te.closest('svg, template, [hidden], dialog:not([open]), script, style, .wd-ghost, pre, code, textarea, input, select')) { continue; }
    var ts = getComputedStyle(te);
    if (ts.display === 'inline' || ts.display === 'none' || ts.display === 'contents' || ts.overflowX !== 'visible') { continue; }
    var own = Array.prototype.some.call(te.childNodes, function (n) { return n.nodeType === 3 && n.textContent.trim(); });
    if (own && te.clientWidth > 0 && te.scrollWidth > te.clientWidth + 6) {  /* 6 px: the trailing letter spacing of a spaced-out word is no spill */
      var k = te.tagName.toLowerCase() + '.' + String(te.className).split(' ').slice(0, 2).join('.');
      if (!spilled[k]) { spilled[k] = 1; out.push('text runs out of its box (' + te.scrollWidth + ' > ' + te.clientWidth + ' px): ' + k + ' "' + te.textContent.trim().slice(0, 30) + '"'); }
    }
  }

  var groups = new Map();
  ctl.forEach(function (e) { var p = e.parentElement; if (!groups.has(p)) { groups.set(p, []); } groups.get(p).push(e); });
  groups.forEach(function (list, p) {
    if (list.length < 2) { return; }
    var tops = list.map(function (e) { return e.getBoundingClientRect().top; }), hs = list.map(function (e) { return Math.round(e.getBoundingClientRect().height); });
    var names = list.map(name).join(' | ');
    if (Math.max.apply(null, tops) - Math.min.apply(null, tops) > 6) { out.push('a row of buttons is on several lines: ' + names + ' (in ' + where(list[0]) + ')'); }
    else if (Math.max.apply(null, hs) - Math.min.apply(null, hs) > 2) { out.push('the buttons of a row are not the same height: ' + list.map(function (e) { return name(e) + ' ' + Math.round(e.getBoundingClientRect().height); }).join(' | ')); }
  });

  var cards = new Map();
  document.querySelectorAll('button.primary, a.primary, .button.primary').forEach(function (e) {
    if (!vis(e) || e.closest(SKIP)) { return; }
    var c = e.closest('.card, form, section') || document.body;
    cards.set(c, (cards.get(c) || []).concat([name(e)]));
  });
  cards.forEach(function (v, c) { if (v.length > 1) { out.push('more than one main action in one card: ' + v.join(' | ')); } });

  document.querySelectorAll('.form-bar').forEach(function (bar) {
    var items = Array.prototype.filter.call(bar.querySelectorAll('button, a.button, a.ghost-btn'), vis);
    if (!items.length) { return; }
    var s = getComputedStyle(bar), last = items[items.length - 1].getBoundingClientRect(), br = bar.getBoundingClientRect();
    var right = br.right - (parseFloat(s.paddingRight) || 0);
    if (s.justifyContent !== 'space-between' && Math.abs(right - last.right) > 3) { out.push('the buttons of a form bar are not bottom right: "' + name(items[items.length - 1]) + '" is ' + Math.round(right - last.right) + ' px off'); }
  });

  document.querySelectorAll('input:not([type=hidden]):not([type=submit]):not([type=button]), select, textarea').forEach(function (e) {
    if (!vis(e) || e.closest(SKIP)) { return; }
    if (!(e.labels && e.labels.length) && !e.getAttribute('aria-label') && !e.getAttribute('aria-labelledby') && !e.getAttribute('title') && !e.closest('label')) {
      out.push('a field without a label: ' + e.tagName.toLowerCase() + '[' + (e.name || e.type) + '] (in ' + where(e) + ')');
    }
  });
  return JSON.stringify(out);
})()
"""


def run(width: int = 360, lang: str = "de") -> list[str]:
    """The slips, each with the page it is on: ``["/v/demo-diesel/e/parts: a row of buttons is on several lines: ...", ...]``."""
    import pagecheck

    problems: list[str] = []
    seen: set[str] = set()
    for page, found in pagecheck.sweep(MEASURE, width=width, lang=lang, open_all=True):
        for text in found:
            if text not in seen:  # the same slip on many pages (a card repeated) is told once
                seen.add(text)
                problems.append(f"{page} [{lang} {width}px]: {text}")
    return problems


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=360)
    ap.add_argument("--lang", default="de")
    found = run(ap.parse_args().width, ap.parse_args().lang)
    print("\n".join(found) if found else "every button and field follows the design rules")
    sys.exit(1 if found else 0)
