"""The buttons that choose a file (the imports, the invoices, the documents ...) are a label around a file input that is not drawn. A "hidden" input cannot be
focused, so such a button could once be pressed only with a mouse or a finger. On a real browser: the input takes the focus and the label shows it. Skipped without
a browser."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

PAGES = ("/fuel/import", "/trips-csv", "/invoices", "/e/docs")

REACHED = """JSON.stringify((function () {
  var input = document.activeElement;
  if (!input || !input.matches || !input.matches('label input[type=file]')) { return null; }
  var label = input.closest('label'), r = input.getBoundingClientRect();
  return { outline: getComputedStyle(label).outlineStyle, big: r.width > 20 && r.height > 20, unseen: getComputedStyle(input).opacity === '0' };
})())"""


def _tab(b):
    for kind in ("keyDown", "keyUp"):
        b.call("Input.dispatchKeyEvent", type=kind, key="Tab", code="Tab", windowsVirtualKeyCode=9)


def test_a_button_that_chooses_a_file_can_be_reached_with_the_keyboard():
    from cdp import Browser, find_chrome

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    reached = []
    with running_app(None) as (base, slug, _pk), Browser() as b:
        for path in PAGES:
            b.open(f"{base}/v/{slug}{path}", 1000, 900, 1, settle=0.6)
            for _ in range(60):  # Tab through the page, as a person without a mouse does
                _tab(b)
                item = json.loads(b.run(REACHED))
                if item:
                    reached.append(path)
                    assert item["outline"] != "none", (path, item)  # the button shows where the focus is
                    assert item["big"] and item["unseen"], (path, item)  # the whole button is the target; the input itself is not seen
                    break
    assert "/fuel/import" in reached and "/trips-csv" in reached, reached  # the keyboard gets to the button of both imports
