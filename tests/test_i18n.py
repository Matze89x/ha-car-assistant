import re
from pathlib import Path

from carassistant import entities, i18n

APP = Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant"


def test_catalogs_have_identical_keys():
    assert set(i18n.EN) == set(i18n.DE), set(i18n.EN) ^ set(i18n.DE)


def test_every_used_key_exists():
    used = set()
    for tpl in (APP / "templates").glob("*.html"):
        used |= set(re.findall(r"_\('([a-z_]+\.[a-z_0-9]+)'", tpl.read_text(encoding="utf-8")))
    for name in ("web.py", "notify.py", "trips.py", "stations.py", "backup.py", "entities.py"):
        text = (APP / name).read_text(encoding="utf-8")
        used |= set(re.findall(r'"((?:err|msg|notify|exp|trips)\.[a-z_0-9]+)"', text))
        used |= set(re.findall(r'"(f\.[a-z_0-9]+)"', text))
    for e in entities.ENTITIES.values():
        used |= {e.title, *(f.label for f in e.fields)}
        if e.empty_hint:
            used.add(e.empty_hint)
        for f in e.fields:
            used |= {f"{f.name}.{c}" for c in f.choices}
    used |= {f"fuel_type.{x}" for x in entities.FUEL_TYPES} | {
        f"tab.{x}" for x in ("overview", "service", "appointments", "tasks", "tires", "mods", "fuel", "report", "trips", "docs", "edit")
    }
    used |= {"confirm.delete", "f.lat", "f.lon", "f.bind_odometer", "f.bind_fuel_level", "f.bind_range", "f.bind_tracker"}
    missing = sorted(k for k in used if k not in i18n.EN)
    assert not missing, missing


def test_formatting_and_fallback():
    t = i18n.translator("de")
    assert t("due.in_days", n=3) == "in 3 T"
    assert t("does.not.exist") == "does.not.exist"
    assert i18n.translator("xx")("btn.save") == "Save"


def test_a_language_is_just_a_file(tmp_path, client):
    """locales/<code>.json adds a language: listed, selectable, partial translations fall back to English."""
    import json

    from carassistant import i18n

    (tmp_path / "xx.json").write_text(
        json.dumps({"_name": "Xish", "_date": "%d/%m/%Y", "_dir": "rtl", "nav.home": "Hoom"}), encoding="utf-8"
    )
    (tmp_path / "Bad Name.json").write_text("{}", encoding="utf-8")
    try:
        assert i18n.load_locales(tmp_path) == ["xx"]
        assert i18n.LANGUAGES["xx"] == {"name": "Xish", "date": "%d/%m/%Y", "dir": "rtl"}
        t = i18n.translator("xx")
        assert t("nav.home") == "Hoom" and t("nav.more") == i18n.EN["nav.more"]  # missing key -> English
        assert "Xish" in client.get("/setup/language").text  # offered without any other change
        assert client.post("/settings/language", data={"language": "xx"}).status_code == 303
        page = client.get("/").text
        assert 'lang="xx"' in page and 'dir="rtl"' in page
    finally:
        i18n.CATALOGS.pop("xx", None)
        i18n.LANGUAGES.pop("xx", None)


def test_shipped_locale_files_match_english():
    from carassistant import i18n

    for path in sorted(i18n.LOCALES_DIR.glob("*.json")):
        data = {k: v for k, v in __import__("json").loads(path.read_text(encoding="utf-8")).items() if not k.startswith("_")}
        for key, text in data.items():
            assert key in i18n.EN, f"{path.name}: unknown key {key}"
            assert sorted(__import__("re").findall(r"\{(\w+)\}", text)) == sorted(__import__("re").findall(r"\{(\w+)\}", i18n.EN[key])), (
                f"{path.name}: placeholders of {key}"
            )
