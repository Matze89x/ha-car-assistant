"""The standing rules of the design on every page, measured in a headless Chrome (tools/pagecheck.py) - the things that kept slipping through by hand:

* **a button never wraps its label and the label stays inside the button** and **a row of buttons stays on ONE line** (docs/design.md, "Light buttons, one line"),
* **the buttons of one row are the same height**,
* **one main action** (``.primary``) per card or form,
* **the buttons of a form bar sit bottom right** (the bar is right aligned; only the guide's Back / Next bars spread out),
* **a thing you tap is big enough**: 30 px at least (the area that takes a tap counts, a ``::after`` that grows it too),
* **every button has a name** (text, ``aria-label`` or ``title``) and **every field a label**,
* **nothing is wider than the screen** (no sideways scrolling) and **no text runs out of its own box or is cut off by it**,
* **the space below the last thing in a card is only the card's padding** (the same distance below as at its left),
* **cards one under the other stand `--sp-col` apart** (no margin on top of the gap),
* **a switch is the last thing at the right end of its row** (like the settings of an iPhone; never on the left).

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
  var ctl = Array.prototype.filter.call(document.querySelectorAll('button, a.button, a.ghost-btn, input[type=submit]'), function (e) { return vis(e) && !e.closest(SKIP) && !e.classList.contains('grip'); });  /* the handle of a sortable row is the edge of the row (a strip as high as the row), not one of its buttons */

  ctl.forEach(function (e) {
    var w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT), n, lines = 1;
    while ((n = w.nextNode())) {
      if (!n.textContent.trim()) { continue; }
      var r = document.createRange(); r.selectNodeContents(n);
      var tops = Array.prototype.map.call(r.getClientRects(), function (x) { return Math.round(x.top); });
      if (tops.length && Math.max.apply(null, tops) - Math.min.apply(null, tops) > 4) { lines = 2; }
    }
    if (lines > 1) { out.push('the label of a button wraps: "' + name(e) + '" (in ' + where(e) + ')'); }
    var br = e.getBoundingClientRect(), tw2 = document.createTreeWalker(e, NodeFilter.SHOW_TEXT), tx;  /* the label must stay inside its button (squeezed buttons print over each other) */
    while ((tx = tw2.nextNode())) {
      if (!tx.textContent.trim() || tx.parentElement.closest('.sr, .sr-only')) { continue; }  /* text for screen readers only is no label */
      var rr = document.createRange(); rr.selectNodeContents(tx);
      var lr = rr.getBoundingClientRect();
      if (lr.width && (lr.right > br.right + 1.5 || lr.left < br.left - 1.5)) { out.push('the label of a button runs out of the button: "' + name(e) + '" (in ' + where(e) + ')'); break; }
    }
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
    if (te.closest('svg, template, [hidden], dialog:not([open]), script, style, .wd-ghost, pre, code, textarea, input, select, .about-slogan, .sb-slogan, .brand-lock')) { continue; }  /* the lockup's letter spacing is worked out from the real font */
    var ts = getComputedStyle(te);
    if (ts.display === 'inline' || ts.display === 'none' || ts.display === 'contents' || ts.overflowX !== 'visible') { continue; }
    var own = Array.prototype.some.call(te.childNodes, function (n) { return n.nodeType === 3 && n.textContent.trim(); });
    var spill = 0;
    if (own && te.clientWidth > 0) {  /* the text itself, not what else sticks out (a tap area that grows with ::after) */
      var ter = te.getBoundingClientRect(), edge = ter.right - (parseFloat(ts.borderRightWidth) || 0) - (parseFloat(ts.paddingRight) || 0);
      Array.prototype.forEach.call(te.childNodes, function (n) {
        if (n.nodeType !== 3 || !n.textContent.trim()) { return; }
        var rn = document.createRange(); rn.selectNodeContents(n);
        spill = Math.max(spill, rn.getBoundingClientRect().right - edge);
      });
    }
    if (own && spill > 6) {  /* 6 px: the trailing letter spacing of a spaced-out word is no spill */
      var k = te.tagName.toLowerCase() + '.' + String(te.className).split(' ').slice(0, 2).join('.');
      if (!spilled[k]) { spilled[k] = 1; out.push('text runs out of its box (' + Math.round(spill) + ' px too far): ' + k + ' "' + te.textContent.trim().slice(0, 30) + '"'); }
    }
  }

  var cw2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), tn, cut = {};  /* text that is cut off by a box with overflow hidden (not an ellipsis, not a scroll area) */
  while ((tn = cw2.nextNode())) {
    if (!tn.textContent.trim()) { continue; }
    var holder = tn.parentElement;
    if (!holder || holder.closest('svg, template, [hidden], dialog:not([open]), script, style, .wd-ghost, .odo-drum, .odo-plate, .odo-flip, .lmz-stage, .sr, .sr-only')) { continue; }
    var rg = document.createRange(); rg.selectNodeContents(tn);
    var tr = rg.getBoundingClientRect(); if (!tr.width) { continue; }
    var ellipsis = false;
    for (var a = holder; a && a !== document.body; a = a.parentElement) {
      var as = getComputedStyle(a);
      if (as.textOverflow === 'ellipsis') { ellipsis = true; }
      if (as.overflowX === 'auto' || as.overflowX === 'scroll') { break; }  /* a scroll area: nothing is cut off, it scrolls */
      if (as.overflowX === 'hidden' || as.overflowX === 'clip') {
        var ar = a.getBoundingClientRect();
        if (!ellipsis && (tr.right > ar.right + 1.5 || tr.left < ar.left - 1.5) && ar.width > 0) {
          var ck = a.tagName.toLowerCase() + '.' + String(a.className).split(' ').slice(0, 2).join('.');
          if (!cut[ck]) { cut[ck] = 1; out.push('text is cut off by its box: ' + ck + ' "' + tn.textContent.trim().slice(0, 30) + '"'); }
        }
        break;
      }
    }
  }

  /* the space below the last thing in a card is the card's own padding and nothing else: the same distance below as at its left */
  function inflow(e) { var cs = getComputedStyle(e); return cs.display !== 'none' && cs.position !== 'absolute' && cs.position !== 'fixed' && cs.visibility !== 'hidden' && !e.hidden && e.getBoundingClientRect().height > 0 && ['SCRIPT', 'STYLE', 'TEMPLATE', 'DIALOG'].indexOf(e.tagName) < 0; }
  function lastOf(e) { var k = Array.prototype.filter.call(e.children, inflow); return k.length ? k[k.length - 1] : null; }
  document.querySelectorAll('.card, .wd, .rec, .tile, .notice, .ov, .stn-card, .lm-card, .status-banner').forEach(function (box) {
    var br0 = box.getBoundingClientRect();
    if (br0.width < 60 || br0.height < 30 || !vis(box) || box.closest('.wd-ghost, .page-head')) { return; }
    var e = lastOf(box), pad = 0, mar = 0, neg = 0, name2 = '';
    while (e) {
      var ls = getComputedStyle(e), mb = parseFloat(ls.marginBottom) || 0;
      if (mb < 0) { neg += mb; } else { mar = Math.max(mar, mb); }
      name2 = e.tagName.toLowerCase() + '.' + String(e.className).split(' ').filter(Boolean)[0];
      var boxed = ls.backgroundColor !== 'rgba(0, 0, 0, 0)' || parseFloat(ls.borderLeftWidth) > 0 || parseFloat(ls.borderBottomWidth) > 0;
      if (boxed || ['svg', 'IMG', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'CANVAS'].indexOf(e.tagName) >= 0) { break; }  /* a chip, a row with a line, a control: its edge is the content */
      pad += parseFloat(ls.paddingBottom) || 0;
      e = lastOf(e);
    }
    var extra = Math.round(pad + mar + neg);
    if (extra > 6) { out.push('more space below the last thing of a card than its padding (' + extra + ' px extra): ' + box.tagName.toLowerCase() + '.' + String(box.className).split(' ').filter(Boolean).slice(0, 2).join('.') + ' ends with ' + name2); }
  });

  /* cards one under the other stand at the distance of the design (--sp-col): not a margin on top of the gap, not none */
  var spcol = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sp-col')) || 14;
  document.querySelectorAll('.card').forEach(function (a) {
    var b = a.nextElementSibling;
    while (b && !vis(b)) { b = b.nextElementSibling; }  /* hidden things between do not count */
    if (!b || !(b.matches('.card')) || !vis(a) || a.closest('[hidden], dialog')) { return; }
    var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    if (rb.left > ra.right - 10 || ra.left > rb.right - 10 || rb.top < ra.bottom - 1) { return; }  /* side by side, or not one under the other */
    var gap = Math.round(rb.top - ra.bottom);
    if (Math.abs(gap - spcol) > 1.5) {
      var tt = function (e) { return e.tagName.toLowerCase() + '.' + String(e.className).split(' ').filter(Boolean).slice(0, 2).join('.') + ' "' + ((e.querySelector('h2, h3') || e).textContent || '').trim().replace(/\s+/g, ' ').slice(0, 20) + '"'; };
      out.push('cards one under the other are ' + gap + ' px apart instead of ' + spcol + ': ' + tt(a) + ' / ' + tt(b));
    }
  });

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
  /* a switch is always the LAST thing at the right end of its row, like the settings of an iPhone - never on the left, never with a label or button
     to its right (docs/design.md, "Switch"); the row is the switch row, the line of a list or the label around it */
  document.querySelectorAll('.switch').forEach(function (sw) {
    if (!vis(sw)) { return; }
    var row = sw.closest('.nm-row, .sw-row, .navrow, .fn-row, [data-sort-item], li') || sw.parentElement, rr = row.getBoundingClientRect(), sr = sw.getBoundingClientRect();
    var label = (row.textContent || sw.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ').slice(0, 24);
    if (rr.right - sr.right > 28) { out.push('a switch is not at the right end of its row (' + Math.round(rr.right - sr.right) + ' px from it): "' + label + '"'); return; }
    var beside = Array.prototype.some.call(row.querySelectorAll('*'), function (e) {
      return !sw.contains(e) && !e.contains(sw) && vis(e) && e.getBoundingClientRect().left >= sr.right - 1 && (e.matches('button, a, input, select') || (e.children.length === 0 && (e.textContent || '').trim()));
    });
    if (beside) { out.push('something stands to the right of a switch: "' + label + '"'); }
  });
  return JSON.stringify(out);
})()
"""


def run(width: int = 360, lang: str = "de") -> list[str]:
    """The slips, each with the page it is on: ``["/v/demo-diesel/e/parts: a row of buttons is on several lines: ...", ...]``."""
    import pagecheck

    problems: list[str] = []
    seen: set[str] = set()
    for page, found in pagecheck.sweep(MEASURE, width=width, lang=lang, open_all=True, home=True):
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
