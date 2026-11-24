"""``show_if`` of a plugin setting: the old single test stays as it was, and a setting can now look at several settings (not, in, not_in, has, any, all).
A condition that cannot be used is dropped - the setting is then simply always shown (a typo never hides a setting). docs/plugins.md."""

import json
import re

from tests.test_web import create_vehicle, slug

from carassistant import addons, db

clean = addons.clean_show_if


def test_the_old_single_test_stays_exactly_as_it_was():
    assert clean({"key": "mode", "equals": "custom"}) == {"key": "mode", "equals": "custom"}
    assert clean({"key": "flag", "equals": True}) == {"key": "flag", "equals": "1"}  # a switch is 1 / 0
    assert clean({"key": "flag", "equals": False}) == {"key": "flag", "equals": "0"}
    assert clean({"key": "n", "equals": 3}) == {"key": "n", "equals": "3"}
    assert clean({"key": "mode", "equals": "custom", "note": "ignored"}) == {
        "key": "mode",
        "equals": "custom",
    }  # a foreign word did no harm before


def test_more_tests_and_the_ways_to_put_them_together():
    assert clean({"key": "mode", "not": "off"}) == {"key": "mode", "not": "off"}
    assert clean({"key": "mode", "in": ["a", "b", 3, True]}) == {"key": "mode", "in": ["a", "b", "3", "1"]}
    assert clean({"key": "mode", "not_in": ["a"]}) == {"key": "mode", "not_in": ["a"]}
    assert clean({"key": "features", "has": "news"}) == {"key": "features", "has": "news"}
    both = {"any": [{"key": "a", "equals": "1"}, {"all": [{"key": "b", "not": "x"}, {"key": "c", "in": ["p", "q"]}]}]}
    assert clean(both) == both
    assert clean([{"key": "a", "equals": "1"}, {"key": "b", "equals": "2"}]) == {  # a plain list means: every one
        "all": [{"key": "a", "equals": "1"}, {"key": "b", "equals": "2"}]
    }


def test_what_cannot_be_used_is_dropped_whole():
    bad = [
        None,
        "x",
        {},
        {"key": "Mode", "equals": "x"},  # not a key
        {"key": "mode"},  # no test
        {"key": "mode", "equals": ["a"]},  # a list is no value here
        {"key": "mode", "in": []},
        {"key": "mode", "in": "a"},
        {"key": "mode", "in": [["a"]]},
        {"any": []},
        {"any": "no"},
        {"all": [{"key": "a", "equals": "1"}, {"key": "b"}]},  # one bad part spoils the whole (it is then simply always shown)
    ]
    for cond in bad:
        assert clean(cond) is None, cond
    leaf = {"key": "a", "equals": "1"}
    assert clean({"all": [leaf] * 8}) is not None and clean({"all": [leaf] * 9}) is None  # at most 8 tests
    deep = leaf
    for _ in range(3):
        deep = {"any": [deep]}
    assert clean(deep) is not None
    assert clean({"any": [deep]}) is None  # three levels at most
    assert clean({"key": "m", "in": [str(i) for i in range(12)]}) is not None
    assert clean({"key": "m", "in": [str(i) for i in range(13)]}) is None


def _settings():
    parsed = addons.parse_package(
        json.dumps(
            {
                "id": "cond-demo",
                "kind": "plugin",
                "name": "Condition demo",
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
                    {"key": "x1", "type": "text", "label": "X1", "show_if": {"key": "mode", "in": ["a", "b"]}},
                    {"key": "x2", "type": "text", "label": "X2", "show_if": {"key": "mode", "not": "a"}},
                    {"key": "x3", "type": "text", "label": "X3", "show_if": {"key": "feat", "has": "map"}},
                    {
                        "key": "x4",
                        "type": "text",
                        "label": "X4",
                        "required": True,
                        "show_if": {
                            "any": [
                                {"key": "on", "equals": True},
                                {"all": [{"key": "mode", "equals": "c"}, {"key": "feat", "has": "news"}]},
                            ]
                        },
                    },
                    {"key": "x5", "type": "text", "label": "X5", "show_if": {"key": "ghost", "equals": "1"}},
                ],
            }
        ).encode()
    )
    return parsed, {x["key"]: x for x in parsed["settings"]}


def test_the_form_is_judged_by_the_whole_condition():
    manifest, by = _settings()
    holds = lambda key, form: addons.show_if_holds(by[key]["show_if"], by, form)  # noqa: E731
    assert holds("x1", {"mode": "a"}) and holds("x1", {"mode": "b"}) and not holds("x1", {"mode": "c"}) and not holds("x1", {})
    assert not holds("x2", {"mode": "a"}) and holds("x2", {"mode": "b"}) and holds("x2", {})  # "not a": an empty choice is not "a" either
    assert holds("x3", {"feat__map": "1"}) and not holds("x3", {"feat__news": "1"})
    assert holds("x4", {"on": "1"})  # one of two: the switch
    assert holds("x4", {"mode": "c", "feat__news": "1"})  # ... or both of the others
    assert not holds("x4", {"mode": "c"}) and not holds("x4", {"feat__news": "1"}) and not holds("x4", {})
    assert holds("x5", {})  # a setting that does not exist: the field is shown, never hidden by a typo
    assert addons._is_shown(by["x4"], manifest, {"on": "1"}) and not addons._is_shown(by["x4"], manifest, {})


def test_a_hidden_required_setting_is_not_asked_for():
    manifest, _by = _settings()
    assert "x4" not in addons.check_settings(manifest, {"mode": "a"}, {})  # required, but hidden: no complaint
    assert addons.check_settings(manifest, {"mode": "c", "feat__news": "1"}, {}).get("x4") == "err.required"  # shown now, and empty
    assert "x4" not in addons.check_settings(manifest, {"on": "1", "x4": "filled"}, {})


def test_the_page_carries_the_condition_for_the_script(client):
    manifest, _by = _settings()
    single = {"key": "k", "type": "text", "label": "K", "show_if": {"key": "mode", "equals": "b"}}
    manifest = addons.parse_package(json.dumps({**manifest, "settings": [*manifest["settings"], single]}).encode())
    vid = create_vehicle(client)
    with db.tx() as conn:
        source = conn.execute("SELECT id FROM sources LIMIT 1").fetchone()["id"]
        pk = addons.add(conn, vid, manifest, source, "0" * 64)
    page = client.get(f"/v/{slug(vid)}/integrations/{pk}/settings").text
    # the old single test keeps its two small attributes; every other form is one JSON attribute (read by app.js)
    assert 'data-showif-key="mode" data-showif-eq="b"' in page
    assert re.search(r'data-showif-key="" data-showif-eq="" data-showif="\{[^"]*&#34;in&#34;', page)
    assert "&#34;any&#34;" in page and "&#34;has&#34;" in page and "&#34;not&#34;" in page
