from pathlib import Path

import yaml

CONFIG = yaml.safe_load((Path(__file__).resolve().parents[1] / "carassistant" / "config.yaml").read_text())


def test_defaults_match_schema_types():
    """Supervisor rejects an option whose default does not fit its schema type (e.g. "" for url?)."""
    for key, rule in CONFIG["schema"].items():
        if rule.rstrip("?") in ("url", "email", "port"):
            assert key not in CONFIG["options"], f"{key}: optional {rule} must have no default"
        if rule.startswith("list("):
            assert CONFIG["options"][key] in rule[5:-1].split("|")


def test_version_scheme():
    major, minor, patch = CONFIG["version"].split(".")
    assert major == "0" and minor.isdigit() and patch.isdigit()


def test_run_sh_never_reads_an_unset_variable():
    """run.sh uses `set -e` and the add-on runs it with `set -u` semantics of bashio: a variable that is exported only conditionally
    (optional options) must be read with a default (${VAR:-...})."""
    import re

    text = (Path(__file__).resolve().parents[1] / "carassistant" / "run.sh").read_text()
    exported_always = {m for m in re.findall(r"^export (\w+)=", text, flags=re.M)}
    used = re.findall(r"\$\{(\w+)(:-[^}]*)?\}", text)
    for name, default in used:
        assert default or name in exported_always, f"{name} may be unset when run.sh reads it - use ${{{name}:-...}}"


def test_mqtt_sensors_are_on_until_switched_off_in_the_app(env, monkeypatch):
    from carassistant import config, db

    assert config.mqtt_discovery_enabled() is True  # on by default: without a broker nothing happens, the System page says so
    monkeypatch.delenv("MQTT_HOST", raising=False)
    assert config.mqtt_settings() is None  # ... and that is no problem
    with db.tx() as conn:
        db.set_setting(conn, "int.mqtt.enabled", "0")
    assert config.mqtt_discovery_enabled() is False
    with db.tx() as conn:
        db.set_setting(conn, "int.mqtt.enabled", "1")
    assert config.mqtt_discovery_enabled() is True


def test_developer_addon_matches_the_main_addon():
    """The Developer add-on (carassistant-dev) is the same app: same options, own slug, version = next release + counter."""
    root = Path(__file__).resolve().parents[1]
    dev = yaml.safe_load((root / "carassistant-dev" / "config.yaml").read_text())
    assert dev["slug"] != CONFIG["slug"] and dev["name"] != CONFIG["name"]
    for key in ("options", "schema", "ingress_port", "arch", "services", "map", "watchdog"):
        assert dev[key] == CONFIG[key], key
    parts = dev["version"].split(".")
    assert len(parts) == 4 and all(p.isdigit() for p in parts)
    now = tuple(int(x) for x in CONFIG["version"].split("."))
    assert tuple(int(x) for x in parts[:3]) > now, "the Developer version must be ahead of the released one"
    assert (root / "carassistant-dev" / "Dockerfile").exists()
