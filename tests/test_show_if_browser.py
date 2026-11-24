"""``show_if`` on the settings page of a plugin, in a real browser: the old single test and every new form (not, in, not_in, has, any, all) show and hide the
fields as the person changes the other settings, the same way the server judges them (tests/test_show_if.py). Needs a real browser (tools/cdp.py)."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

PKG = {
    "id": "cond-browser",
    "kind": "plugin",
    "name": "Condition browser",
    "version": "1",
    "settings": [
        {
            "key": "mode",
            "type": "select",
            "label": "Mode",
            "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}, {"value": "c", "label": "C"}],
        },
        {"key": "on", "type": "bool", "label": "On"},
        {
            "key": "feat",
            "type": "multiselect",
            "label": "Features",
            "options": [{"value": "news", "label": "News"}, {"value": "map", "label": "Map"}],
        },
        {"key": "old", "type": "text", "label": "Old form", "show_if": {"key": "mode", "equals": "b"}},
        {"key": "isin", "type": "text", "label": "In", "show_if": {"key": "mode", "in": ["a", "b"]}},
        {"key": "isnot", "type": "text", "label": "Not", "show_if": {"key": "mode", "not": "a"}},
        {"key": "notin", "type": "text", "label": "Not in", "show_if": {"key": "mode", "not_in": ["a", "b"]}},
        {"key": "has", "type": "text", "label": "Has", "show_if": {"key": "feat", "has": "map"}},
        {
            "key": "tree",
            "type": "text",
            "label": "Tree",
            "show_if": {"any": [{"key": "on", "equals": True}, {"all": [{"key": "mode", "equals": "c"}, {"key": "feat", "has": "news"}]}]},
        },
    ],
}

# which fields are shown (by name), read from the page
SHOWN = (
    "JSON.stringify(Array.prototype.map.call(document.querySelectorAll('.addon-field'), function (b) {"
    "var i = b.querySelector('[name]'); return [i && i.name, !b.hidden]; }))"
)


@pytest.fixture(scope="module")
def page():
    from cdp import Browser, find_chrome

    from browser_app import running_app

    if find_chrome() is None:
        pytest.skip("no Chrome / Chromium installed")
    with running_app(PKG) as (base, slug, pk), Browser() as b:
        b.open(f"{base}/v/{slug}/integrations/{pk}/settings", 900, 900, 1, settle=1.0)
        b.wait_for("document.querySelector('.set-form')", seconds=15)
        yield b


def _shown(b) -> set[str]:
    return {name for name, shown in json.loads(b.run(SHOWN)) if shown and name in ("old", "isin", "isnot", "notin", "has", "tree")}


def _set(b, name: str, value) -> None:
    """What a person does to a setting: tick a box or choose a value - the page hears it as a ``change``."""
    b.run(
        f"(function(){{var e=document.querySelector('[name=\"{name}\"]'); if (e.type==='checkbox') {{ e.checked={json.dumps(bool(value))}; }} "
        f"else {{ e.value={json.dumps(value)}; }} e.dispatchEvent(new Event('change',{{bubbles:true}}));}})()"
    )


def test_the_fields_follow_the_settings_they_look_at(page):
    b = page
    assert _shown(b) == {"isin"}  # the choice stands on its first option, "a"
    _set(b, "mode", "b")
    assert _shown(b) == {"old", "isin", "isnot"}
    _set(b, "mode", "c")
    assert _shown(b) == {"isnot", "notin"}
    _set(b, "feat__map", True)  # a multiselect: a box named <key>__<value>
    assert _shown(b) == {"isnot", "notin", "has"}


def test_any_and_all_are_put_together_in_the_page_the_way_the_server_does(page):
    b = page
    _set(b, "mode", "c")
    _set(b, "feat__news", True)
    assert "tree" in _shown(b)  # both of the "all" part
    _set(b, "feat__news", False)
    assert "tree" not in _shown(b)
    _set(b, "on", True)  # or the switch alone
    assert "tree" in _shown(b)
    _set(b, "on", False)
    assert "tree" not in _shown(b)
