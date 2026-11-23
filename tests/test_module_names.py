"""Every page a person can reach has a name in both languages: the bar, the More list and the integrations page never show a raw key."""

import pytest

from carassistant import i18n, modules


@pytest.mark.parametrize("lang", ["en", "de"])
def test_every_module_has_its_names(lang):
    catalog = i18n.CATALOGS[lang]
    missing = []
    for key in modules.BY_KEY:
        for name in (f"tab.{key}", f"mod.{key}.name"):
            if key in ("counters", "stations", "edit", "overview") and name.startswith("mod."):
                continue  # not listed on the integrations page
            if not catalog.get(name) or catalog.get(name) == name:
                missing.append(name)
    assert not missing, f"{lang}: {missing}"


def test_the_bar_label_of_the_map_is_a_word_not_a_key(env):
    from carassistant import navigation

    assert i18n.translator("de")("tab.map") == "Karte" and i18n.translator("en")("tab.map") == "Map"
    assert navigation.SHORT.get("map", "tab.map") == "tab.map"  # the bar asks for the translation of this key
