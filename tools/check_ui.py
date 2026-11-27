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
* **blocks one under the other stand a distance the design knows** (`--sp-col` 14, `--sp-head` 16 or `--sp-block` 20 - never an 18 or a 22 written by hand) and
  **a message card stands `--sp-block` from the block under it** (the same as the notice tile above it),
* **sub-windows one under the other stand `--sp-sub` apart and are padded by the tokens** (docs/design.md, 4c: spacing is measured),
* **a switch is the last thing at the right end of its row** (like the settings of an iPhone; never on the left),
* **a thing you tap in a corner of a rounded box has rounded corners too** (no square flash behind a round card),
* **the buttons at the bottom of a plugin tile lie inside the tile** (nothing cut off, however many downloads and buttons the plugin has),
* **every button lies inside the box it belongs to** (a card, the panel of a new entry, a record) - the panels of a new entry are opened for the check, too.

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
      if (!tx.textContent.trim() || tx.parentElement.closest('.sr, .sr-only') || getComputedStyle(tx.parentElement).textOverflow === 'ellipsis') { continue; }  /* a label that is shortened with "..." on purpose stays inside */  /* text for screen readers only is no label */
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
  var nextCard = function (a) {  /* the next thing in the column; the cards of a form that saves several windows (.card-form, no box of its own) count as the cards of the column */
    var e = a;
    while (e) {
      var s = e.nextElementSibling;
      while (s) {
        if (s.matches('.card-form')) { var inner = s.querySelector(':scope > .card'); if (inner && vis(inner)) { return inner; } }
        else if (vis(s)) { return s; }  /* hidden things between do not count */
        s = s.nextElementSibling;
      }
      e = e.parentElement && e.parentElement.matches('.card-form') ? e.parentElement : null;
    }
    return null;
  };
  document.querySelectorAll('.card').forEach(function (a) {
    var b = nextCard(a);
    if (!b || !(b.matches('.card')) || a.matches('.msg-card') || !vis(a) || a.closest('[hidden], dialog')) { return; }  /* a message card has its own distance (below) */
    var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    if (rb.left > ra.right - 10 || ra.left > rb.right - 10 || rb.top < ra.bottom - 1) { return; }  /* side by side, or not one under the other */
    var gap = Math.round(rb.top - ra.bottom);
    if (Math.abs(gap - spcol) > 1.5) {
      var tt = function (e) { return e.tagName.toLowerCase() + '.' + String(e.className).split(' ').filter(Boolean).slice(0, 2).join('.') + ' "' + ((e.querySelector('h2, h3') || e).textContent || '').trim().replace(/\s+/g, ' ').slice(0, 20) + '"'; };
      out.push('cards one under the other are ' + gap + ' px apart instead of ' + spcol + ': ' + tt(a) + ' / ' + tt(b));
    }
  });

  /* the space between blocks (docs/design.md, "The space between blocks"): two blocks one under the other of a page stand a distance the design knows -
     --sp-col (cards of one stack), --sp-head (under the page header or a tab bar) or --sp-block (between blocks). An 18, a 22 or a 12 is a margin somebody wrote by hand. */
  var spblock = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sp-block')) || 20, sphead = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--sp-head')) || 16;
  var BLOCK = '.page-head, .notice-slot, .seg-tabs, .card, .stn-card, .rec, .tile, .mgroup-wrap, .tp-sec, .rec-grid, .pk-grid, .cards, .rp-bar, .rp-hero, .status-banner, .about-wrap, .vd';
  var ident = function (e) { return e.tagName.toLowerCase() + '.' + String(e.className).split(' ').filter(Boolean).slice(0, 2).join('.'); };
  document.querySelectorAll('main, main .tp-sec, main .vd, main .sys-col, main .cards, main .guide-stack').forEach(function (flow) {
    if (!vis(flow) || flow.closest('[hidden], dialog')) { return; }
    var kids = Array.prototype.filter.call(flow.children, inflow);
    for (var i = 1; i < kids.length; i++) {
      var a = kids[i - 1], b = kids[i];
      if (!a.matches(BLOCK) || !b.matches(BLOCK)) { continue; }
      var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      if (rb.left > ra.right - 10 || ra.left > rb.right - 10 || rb.top < ra.bottom - 1) { continue; }  /* side by side, or not one under the other */
      var gap = rb.top - ra.bottom;
      if (gap > 3 * spblock) { continue; }  /* something that is not drawn lies between them (a layout of its own) */
      if ([spcol, sphead, spblock].every(function (want) { return Math.abs(gap - want) > 1.5; })) {
        out.push('blocks one under the other are ' + Math.round(gap * 10) / 10 + ' px apart - the design knows ' + spcol + ', ' + sphead + ' and ' + spblock + ': ' + ident(a) + ' / ' + ident(b));
      }
    }
  });
  /* a message card (docs/design.md, 4e) is a block of its own: the same distance below it as the notice tile has above it (--sp-block), one stack when another message follows */
  document.querySelectorAll('.msg-card').forEach(function (a) {
    var b = nextCard(a);
    if (!b || !vis(a) || a.closest('[hidden], dialog')) { return; }
    var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    if (rb.left > ra.right - 10 || ra.left > rb.right - 10 || rb.top < ra.bottom - 1) { return; }
    var gap = Math.round(rb.top - ra.bottom), want = b.matches('.msg-card') ? spcol : spblock;
    if (Math.abs(gap - want) > 1.5) { out.push('a message card is ' + gap + ' px from the block under it instead of ' + want + ': ' + ident(a) + ' / ' + ident(b)); }
  });

  /* the sub-windows of a card (docs/design.md, 4c): one under the other they stand --sp-sub apart, and each one is padded by --sp-sub-pad-y / --sp-sub-pad-x - the spacing is a measure, not a taste */
  var rootCs = getComputedStyle(document.documentElement);
  var spsub = parseFloat(rootCs.getPropertyValue('--sp-sub')) || 10, padY = parseFloat(rootCs.getPropertyValue('--sp-sub-pad-y')) || 10, padX = parseFloat(rootCs.getPropertyValue('--sp-sub-pad-x')) || 12;
  document.querySelectorAll('.sub-card').forEach(function (a) {
    if (!vis(a) || a.closest('[hidden], dialog')) { return; }
    var cs = getComputedStyle(a), lab = ((a.querySelector('.sub-h') || a).textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24);
    var band = a.firstElementChild && a.firstElementChild.classList.contains('sub-h') ? a.firstElementChild : null;  /* the label is the header band: it sits at the top edge of the window, so the window has no padding on top (the band has its own) */
    if (band) {
      var bh = band.getBoundingClientRect(), ah = a.getBoundingClientRect();
      if (Math.abs(bh.top - ah.top - 1) > 1 || Math.abs(bh.height - 34) > 1 || Math.abs(bh.width - (ah.width - 2)) > 1.5) {
        out.push('the header band of a sub-window is not 34 px high and as wide as the window (' + Math.round(bh.height) + ' x ' + Math.round(bh.width) + ' px, ' + Math.round(bh.top - ah.top) + ' px from the top): "' + lab + '"');
      }
    }
    if (Math.abs(parseFloat(cs.paddingTop) - (band ? 0 : padY)) > .5 || Math.abs(parseFloat(cs.paddingBottom) - padY) > .5 || Math.abs(parseFloat(cs.paddingLeft) - padX) > .5 || Math.abs(parseFloat(cs.paddingRight) - padX) > .5) {
      out.push('a sub-window is not padded by the tokens (' + cs.paddingTop + ' ' + cs.paddingRight + ' instead of ' + (band ? 0 : padY) + 'px ' + padX + 'px): "' + lab + '"');
    }
    var b = a.nextElementSibling;
    while (b && !vis(b)) { b = b.nextElementSibling; }
    if (!b || !b.matches('.sub-card')) { return; }
    var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
    if (rb.left > ra.right - 10 || ra.left > rb.right - 10 || rb.top < ra.bottom - 1) { return; }
    var gap = Math.round(rb.top - ra.bottom);
    if (Math.abs(gap - spsub) > 1.5) { out.push('sub-windows one under the other are ' + gap + ' px apart instead of ' + spsub + ': "' + lab + '" / "' + ((b.querySelector('.sub-h') || b).textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24) + '"'); }
  });

  /* the lines of a window stand BETWEEN things (docs/design.md, 4c): none directly under its label (or hint, or tab bar), none at its bottom edge, none after the last row of a list unless buttons follow */
  document.querySelectorAll('.sub-card *').forEach(function (e) {
    if (!vis(e) || e.closest('dialog')) { return; }
    var cs = getComputedStyle(e), top = parseFloat(cs.borderTopWidth) > 0, bottom = parseFloat(cs.borderBottomWidth) > 0, sides = parseFloat(cs.borderLeftWidth) + parseFloat(cs.borderRightWidth);
    if (sides > 0 || (top && bottom) || !(top || bottom)) { return; }  /* a box has four sides, a line has one */
    var lab = ((e.closest('.sub-card').querySelector('.sub-h') || e).textContent || '').trim().slice(0, 24), what = e.tagName.toLowerCase() + '.' + String(e.className).split(' ').filter(Boolean).slice(0, 2).join('.') + ' "' + name(e) + '"';
    var p = e.previousElementSibling; while (p && !vis(p)) { p = p.previousElementSibling; }
    var n = e.nextElementSibling; while (n && !vis(n)) { n = n.nextElementSibling; }
    if (top && (!p || p.matches('.sub-h, .hint, .seg-tabs, h3'))) { out.push('a line directly under the label of a window ("' + lab + '"): ' + what); }
    if (bottom && !n) { out.push('a line at the bottom edge of a window ("' + lab + '"): ' + what); }
    else if (bottom && n.className !== e.className && !n.matches('.form-bar, .nm-actions, details, button, a.button, .acct-fields')) { out.push('a line after the last row of a list, with no buttons after it ("' + lab + '"): ' + what); }
  });

  /* a line never touches a field (docs/design.md, 4b): the line that begins a row (a switch row, a flat row) stands at least --sp-field - 6 px under the field above it; a hairline hard against the edge of a select looks like a rendering bug */
  document.querySelectorAll('.card *, .sub-card *').forEach(function (e) {
    if (!vis(e) || e.closest('dialog')) { return; }
    var cs = getComputedStyle(e);
    if (!(parseFloat(cs.borderTopWidth) > 0) || parseFloat(cs.borderLeftWidth) + parseFloat(cs.borderRightWidth) > 0 || parseFloat(cs.borderBottomWidth) > 0) { return; }  /* a line has one side */
    var p = e.previousElementSibling; while (p && !vis(p)) { p = p.previousElementSibling; }
    if (!p) { return; }
    var cts = p.matches('input:not([type=hidden]), select, textarea, .fld') ? [p] : Array.prototype.slice.call(p.querySelectorAll('input:not([type=hidden]), select, textarea, .fld')).filter(vis);
    if (!cts.length) { return; }
    var bottom = Math.max.apply(null, cts.map(function (x) { return x.getBoundingClientRect().bottom; })), gap = e.getBoundingClientRect().top - bottom;
    if (gap < 8) { out.push('a line touches the field above it (' + Math.round(gap) + ' px): ' + e.tagName.toLowerCase() + '.' + String(e.className).split(' ').filter(Boolean).slice(0, 2).join('.') + ' "' + name(e) + '"'); }
  });

  /* a line runs through the WHOLE window (docs/design.md, 4c): a hairline that separates rows or parts of a card, a sub-window or a popup reaches both edges of it - never only as wide as the text */
  document.querySelectorAll('.card *, .sub-card *, dialog.vsw *').forEach(function (e) {
    if (!vis(e)) { return; }
    var cs = getComputedStyle(e), t = parseFloat(cs.borderTopWidth) > 0, b = parseFloat(cs.borderBottomWidth) > 0;
    if (t === b || parseFloat(cs.borderLeftWidth) + parseFloat(cs.borderRightWidth) > 0 || e.matches('hr, summary, .seg-tabs, .seg-tabs *, table, td, th, tr, thead, tbody')) { return; }  /* a line has ONE horizontal side and no vertical one */
    var win = null, up = e.parentElement;  /* the window of a line: the nearest card, sub-window, popup or framed box (a label, a table box) around it */
    while (up && up !== document.body) {
      var uc = getComputedStyle(up);
      if (up.matches('.card, .sub-card, dialog.vsw') || (['Top', 'Bottom', 'Left', 'Right'].every(function (s) { return parseFloat(uc['border' + s + 'Width']) > 0; }) && uc.borderTopStyle !== 'none')) { win = up; break; }
      up = up.parentElement;
    }
    if (!win || !vis(win)) { return; }
    var r = e.getBoundingClientRect(), w = win.getBoundingClientRect(), wcs = getComputedStyle(win), bl = parseFloat(wcs.borderLeftWidth) || 0, br = parseFloat(wcs.borderRightWidth) || 0;
    if (r.width < w.width * 0.5) { return; }  /* a short thing with an edge is not a divider of the window */
    if (Math.abs(r.left - (w.left + bl)) > 1.5 || Math.abs((w.right - br) - r.right) > 1.5) {
      out.push('a line does not run through the whole window (' + Math.round(r.left - w.left - bl) + ' px from the left, ' + Math.round(w.right - br - r.right) + ' px from the right): ' + e.tagName.toLowerCase() + '.' + String(e.className).split(' ').filter(Boolean).slice(0, 2).join('.') + ' "' + name(e) + '"');
    }
  });

  /* the lines and the buttons of EVERY window (card, sub-window, popup): no line directly under its heading, none at its bottom edge, and the buttons that save stand at the very bottom (docs/design.md, 4c) */
  document.querySelectorAll('.card, .sub-card').forEach(function (win) {
    if (!vis(win) || win.closest('dialog, [hidden]')) { return; }
    var wr = win.getBoundingClientRect(), wcs = getComputedStyle(win), inner = wr.bottom - (parseFloat(wcs.borderBottomWidth) || 0) - (parseFloat(wcs.paddingBottom) || 0), title = ((win.querySelector('h2, .sub-h') || win).textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24);
    win.querySelectorAll('*').forEach(function (e) {
      if (!vis(e) || e.closest('dialog') || e.closest('.sub-card') !== (win.matches('.sub-card') ? win : e.closest('.sub-card')) && false) { return; }
      var cs = getComputedStyle(e), t = parseFloat(cs.borderTopWidth) > 0, b = parseFloat(cs.borderBottomWidth) > 0;
      if (t === b || parseFloat(cs.borderLeftWidth) + parseFloat(cs.borderRightWidth) > 0 || e.matches('hr, summary, .seg-tabs, .seg-tabs *, table, td, th, tr, thead, tbody')) { return; }
      var r = e.getBoundingClientRect(), what = e.tagName.toLowerCase() + '.' + String(e.className).split(' ').filter(Boolean).slice(0, 2).join('.') + ' "' + name(e) + '"';
      if (r.width < wr.width * 0.5) { return; }
      var p = e.previousElementSibling; while (p && !vis(p)) { p = p.previousElementSibling; }
      if (t && p && p.matches('h2, h3, .sub-h') && !e.closest('.sub-card') === !win.matches('.sub-card')) { out.push('a line directly under the heading of a window ("' + title + '"): ' + what); }
      if (b && inner - r.bottom <= 1.5) { out.push('a line at the bottom edge of a window ("' + title + '"): ' + what); }
    });
    win.querySelectorAll('.form-bar').forEach(function (bar) {
      if (!vis(bar) || bar.closest('dialog') || !bar.querySelector('button.primary')) { return; }
      var host = bar.closest('.sub-card, .card'); if (host !== win) { return; }
      var gap = inner - bar.getBoundingClientRect().bottom;
      if (gap > 6) { out.push('the buttons that save are not at the very bottom of their window ("' + title + '", ' + Math.round(gap) + ' px of other things below): ' + name(bar)); }
    });
  });

  /* explanations stand at the TOP of their window, with the info symbol (docs/design.md, 4c): a hint paragraph is never below the content (rows, fields, buttons) of its window, and it begins with the info symbol */
  var INFO = '__INFO_PATH__';
  document.querySelectorAll('.card p.hint, .sub-card p.hint').forEach(function (h) {
    if (!vis(h) || h.closest('dialog, [hidden], .lm-detail, .lmz-detail') || !(h.textContent || '').trim()) { return; }
    var win = h.closest('.sub-card, .card'), title = ((win.querySelector('h2, .sub-h') || win).textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24), svg = h.querySelector('svg path');
    if (!svg || svg.getAttribute('d') !== INFO) { out.push('an explanation has no info symbol in front ("' + title + '"): "' + name(h) + '"'); }
    var before = Array.prototype.slice.call(win.querySelectorAll('input:not([type=hidden]), select, textarea, .fld, button, .nm-row, .mk-field, .form-bar, .switch')).filter(function (x) { return vis(x) && !x.closest('dialog') && !x.closest('summary') && x.closest('.sub-card, .card') === win && (x.compareDocumentPosition(h) & Node.DOCUMENT_POSITION_FOLLOWING); });
    if (before.length) { out.push('an explanation stands below the content of its window, not at the top ("' + title + '"): "' + name(h) + '"'); }
  });

  /* ONE explanation with the info symbol per window (docs/design.md, 4c): at the top of a window (before anything to touch) there is one such sentence - two are put together, or only the one that applies is shown */
  document.querySelectorAll('.card, .sub-card').forEach(function (win) {
    if (!vis(win) || win.closest('dialog, [hidden], .lm-detail, .lmz-detail')) { return; }
    var first = Array.prototype.slice.call(win.querySelectorAll('input:not([type=hidden]), select, textarea, button, .nm-row, .mk-field, .fld, .switch, a.button')).filter(vis)[0];
    var hints = Array.prototype.slice.call(win.querySelectorAll('p.hint')).filter(function (p) {
      var s = p.querySelector('svg path');
      return vis(p) && (p.textContent || '').trim() && s && s.getAttribute('d') === INFO && p.closest('.card, .sub-card') === win && !p.closest('.addon-field, .nm-thr, details') && (!first || (p.compareDocumentPosition(first) & Node.DOCUMENT_POSITION_FOLLOWING));
    });
    if (hints.length > 1) { out.push('a window shows ' + hints.length + ' explanations with an info symbol at its top - put them together into one ("' + ((win.querySelector('h2, .sub-h') || win).textContent || '').trim().replace(/\s+/g, ' ').slice(0, 30) + '")'); }
  });

  /* a switch that ends its card: its text stands in the middle between the line above it and the edge of the card (not more air below than above) */
  document.querySelectorAll('.card').forEach(function (c) {
    if (!vis(c) || c.closest('dialog, [hidden]')) { return; }
    var row = c.querySelector(':scope > label.nm-row.sw-row:last-child, :scope > form:last-child > label.nm-row.sw-row:last-child');
    if (!row || !vis(row) || parseFloat(getComputedStyle(row).borderTopWidth) < 1) { return; }
    var tr = row.querySelector('.nm-t').getBoundingClientRect(), rr = row.getBoundingClientRect(), cr = c.getBoundingClientRect(), cs = getComputedStyle(c);
    var above = tr.top - rr.top - 1, below = cr.bottom - parseFloat(cs.borderBottomWidth) - tr.bottom;
    if (Math.abs(above - below) > 3) { out.push('the text of a switch at the end of a card is not centred between its line and the card edge (' + Math.round(above) + ' px above, ' + Math.round(below) + ' px below): "' + name(row) + '"'); }
  });

  /* rows that stand directly one under the other have a line between them (docs/design.md, 4c): a missing line is a rendering bug the eye sees at once */
  (function () {
    var ROWS = '.nm-row, .rg-row, .about-row, .icon-row, .odo-hrow, .ifc-row, .addon-value, .tpl-row, .acct-users > li, .lm-tiles > li, .wa-list > .mk-field, .sub-card .mk-field';
    var rows = Array.prototype.slice.call(document.querySelectorAll('.card ' + ROWS.split(',').join(', .card '))).filter(function (r) { return vis(r) && !r.closest('dialog, [hidden]'); });
    var seenPair = {};
    rows.forEach(function (a) {
      var ra = a.getBoundingClientRect();
      rows.forEach(function (b) {
        if (a === b || a.contains(b) || b.contains(a)) { return; }
        var rb = b.getBoundingClientRect();
        if (Math.abs(rb.top - ra.bottom) > 3 || rb.left > ra.right - 10 || ra.left > rb.right - 10) { return; }  /* b stands right under a */
        var bt = parseFloat(getComputedStyle(b).borderTopWidth) > 0, ab = parseFloat(getComputedStyle(a).borderBottomWidth) > 0;
        if (bt || ab) { return; }
        var key = name(a) + '|' + name(b);
        if (seenPair[key]) { return; } seenPair[key] = 1;
        var win = a.closest('.sub-card, .card'), title = ((win.querySelector('h2, .sub-h') || win).textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24);
        out.push('two rows one under the other have no line between them ("' + title + '"): "' + name(a) + '" / "' + name(b) + '"');
      });
    });
  })();

  /* every window of the settings begins with a short explanation (docs/design.md, 4c): an info line right under its heading, before anything to touch */
  if (location.pathname.indexOf('/settings/') === 0) {
    document.querySelectorAll('.card').forEach(function (c) {
      var h = c.querySelector(':scope > h2');
      if (!h || !vis(c) || c.closest('dialog, [hidden]')) { return; }
      var hint = Array.prototype.slice.call(c.querySelectorAll(':scope > p.hint')).filter(function (p) { return vis(p) && (p.textContent || '').trim(); })[0];
      var ctl = c.querySelector('input:not([type=hidden]), select, textarea, .fld, button, .nm-row, .mk-field, .form-bar, .switch, .sub-card, .season-pick');
      if (!hint || (ctl && !(hint.compareDocumentPosition(ctl) & Node.DOCUMENT_POSITION_FOLLOWING))) { out.push('a window has no short explanation at its top ("' + (h.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 30) + '")'); }
    });
  }

  var groups = new Map();
  ctl.forEach(function (e) { var p = e.parentElement; if (!groups.has(p)) { groups.set(p, []); } groups.get(p).push(e); });
  groups.forEach(function (list, p) {
    if (list.length < 2 || p.matches('.addon-bar:is(.fb3, .fb4, .fb5, .fb6, .fb7, .fb8, .fb9)')) { return; }  /* a tile bar with three or more extra buttons takes a second line on a phone on purpose: better than a button cut off */
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
  /* the bar at the bottom of a plugin tile: every button lies inside it and inside the tile - nothing is cut off at either side, however many
     buttons and downloads the plugin has (a tile never grows wider than the page either) */
  document.querySelectorAll('.addon-bar').forEach(function (bar) {
    if (!vis(bar)) { return; }
    var tile = bar.closest('.card') || bar, tr = tile.getBoundingClientRect();
    Array.prototype.forEach.call(bar.querySelectorAll('a.button, button, summary'), function (b) {
      if (!vis(b)) { return; }
      var r = b.getBoundingClientRect();
      if (r.left < tr.left - 0.5 || r.right > tr.right + 0.5) { out.push('a button of a tile bar lies outside its tile: "' + (name(b) || b.getAttribute('aria-label') || b.className) + '" (' + Math.round(Math.min(r.left - tr.left, 0) + Math.max(r.right - tr.right, 0)) + ' px)'); }
    });
    if (bar.scrollWidth > bar.clientWidth + 1) { out.push('the bar of a tile is wider than the tile (' + (bar.scrollWidth - bar.clientWidth) + ' px)'); }
  });
  /* every button lies inside the box it belongs to (a card, the panel of a new entry, a record): nothing sticks out at the left or the right. A light button that
     is as wide as its bar and has a neighbour pushes the row out of the card - the Cancel button of the form of a new fill-up did, and no check opened that panel */
  var BOXES = '.card, .tp-add, .stn-card, .rec, .msg-card, .sub-card, .notice';
  document.querySelectorAll('button, a.button, a.ghost-btn').forEach(function (b) {
    if (!vis(b) || b.closest('.addon-bar, .tabbar, .page-head, .more-pane, nav, .wd-ctl')) { return; }
    var pos = getComputedStyle(b).position, box = b.closest(BOXES);
    if (pos === 'fixed' || pos === 'absolute' || !box || !vis(box)) { return; }
    for (var p = b.parentElement; p && p !== box; p = p.parentElement) { var ov = getComputedStyle(p).overflowX; if (ov === 'auto' || ov === 'scroll') { return; } }  /* a row that scrolls sideways on purpose */
    var r = b.getBoundingClientRect(), br = box.getBoundingClientRect();
    if (r.width > 1 && (r.left < br.left - 0.5 || r.right > br.right + 0.5)) {
      out.push('a button lies outside its box (' + Math.round(Math.min(r.left - br.left, 0) + Math.max(r.right - br.right, 0)) + ' px): "' + (name(b) || b.getAttribute('aria-label') || b.className) + '" in ' + ident(box));
    }
  });
  /* a thing with a background - or a thing you tap (the tap highlight of a phone is the rectangle of what you tap) - that fills a corner of a rounded
     box has the same corners, or square corners poke out of the round ones */
  function rad(s) { return Math.max(parseFloat(s.borderTopLeftRadius) || 0, parseFloat(s.borderTopRightRadius) || 0, parseFloat(s.borderBottomLeftRadius) || 0, parseFloat(s.borderBottomRightRadius) || 0); }
  function transparent(c) { return !c || c === 'transparent' || /rgba\(.*,\s*0\)$/.test(c); }
  document.querySelectorAll('body *').forEach(function (e) {
    if (!(e instanceof HTMLElement) || !vis(e) || e.closest('.switch, .tabbar') || parseFloat(getComputedStyle(e).opacity) === 0) { return; }  /* an invisible file field inside a button is nothing to see */
    var tappable = e.matches('a, summary, label, button, [role=button]');
    var s = getComputedStyle(e), r = e.getBoundingClientRect(), p = e.parentElement;
    while (p && p !== document.body && rad(getComputedStyle(p)) <= 0) { p = p.parentElement; }
    if (!p || p === document.body) { return; }
    var ps = getComputedStyle(p), pr = p.getBoundingClientRect();
    if (ps.overflow !== 'visible' || rad(s) >= rad(ps) - 2) { return; }
    var near = function (a, b) { return Math.abs(a - b) <= 3; };
    var corner = (near(r.left, pr.left) && near(r.top, pr.top)) || (near(r.right, pr.right) && near(r.top, pr.top)) || (near(r.left, pr.left) && near(r.bottom, pr.bottom)) || (near(r.right, pr.right) && near(r.bottom, pr.bottom));
    var visible = !transparent(s.backgroundColor) || (tappable && !transparent(s.webkitTapHighlightColor));
    if (corner && visible) { out.push('square corners inside a rounded box (a tap or hover shows a rectangle): ' + e.tagName.toLowerCase() + '.' + String(e.className).split(' ').slice(0, 2).join('.') + ' in ' + p.tagName.toLowerCase() + '.' + String(p.className).split(' ').slice(0, 2).join('.')); }
  });
  return JSON.stringify(out);
})()
"""


def run(width: int = 360, lang: str = "de") -> list[str]:
    """The slips, each with the page it is on: ``["/v/demo-diesel/e/parts: a row of buttons is on several lines: ...", ...]``."""
    import pagecheck

    sys.path.insert(0, str(ROOT / "carassistant" / "app"))
    from carassistant.icons import ICONS

    INFO_PATH = ICONS["info"]  # the path of the info symbol: an explanation must begin with exactly it
    problems: list[str] = []
    seen: set[str] = set()
    for page, found in pagecheck.sweep(MEASURE.replace("__INFO_PATH__", INFO_PATH), width=width, lang=lang, open_all=True, home=True):
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
