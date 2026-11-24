"""The check of a whole source against this version of the app (tools/check_source.py) and the workflow that runs it."""

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import check_source  # noqa: E402


def _source(tmp_path: Path) -> Path:
    """A small source with one plain plugin."""
    manifest = {
        "id": "my-plugin",
        "kind": "plugin",
        "name": "My plugin",
        "version": "1",
        "description": "Says hello.",
        "icon": "plug",
        "l10n": {"de": {"name": "Mein Plugin"}},
    }
    (tmp_path / "plugins" / "my-plugin").mkdir(parents=True)
    (tmp_path / "plugins" / "my-plugin" / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "plugins" / "index.json").write_text(
        json.dumps({"packages": [{"id": "my-plugin", "name": "My plugin", "version": "1"}]}), encoding="utf-8"
    )
    (tmp_path / "integrations").mkdir()
    (tmp_path / "integrations" / "index.json").write_text(json.dumps({"packages": []}), encoding="utf-8")
    return tmp_path


def test_a_clean_source_passes_and_the_problems_of_a_broken_one_are_named(tmp_path):
    root = _source(tmp_path)
    errors, _hints, count = check_source.check_source(root)
    assert errors == [] and count == 1
    assert check_source.main([str(root)]) == 0

    index = root / "plugins" / "index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    data["packages"][0]["version"] = "99"  # the index says another version than the package
    data["packages"].append({"id": "Bad Id!", "version": "1"})
    index.write_text(json.dumps(data), encoding="utf-8")
    (root / "plugins" / "unlisted").mkdir()  # a folder the index does not know
    errors, _hints, _count = check_source.check_source(root)
    text = "\n".join(errors)
    assert "version differs" in text and "bad or missing id" in text and "unlisted: the folder is not listed" in text
    assert check_source.main([str(root)]) == 1


def test_an_empty_folder_is_no_source_and_a_vehicle_file_must_exist(tmp_path):
    errors, hints, count = check_source.check_source(tmp_path)
    assert errors == [] and count == 0 and any("no package found" in h for h in hints)
    (tmp_path / "vehicles").mkdir()
    (tmp_path / "vehicles" / "index.json").write_text(json.dumps({"vehicles": [{"id": "x", "file": "x.zip"}]}), encoding="utf-8")
    errors, _hints, _count = check_source.check_source(tmp_path)
    assert any("needs an existing file" in e for e in errors)


def test_the_reusable_workflow_and_the_example_that_calls_it_belong_together():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "check-source.yml").read_text(encoding="utf-8"))
    triggers = workflow.get("on") or workflow.get(True)  # YAML reads a bare "on" as True
    assert "workflow_call" in triggers and triggers["workflow_call"]["inputs"]["app-ref"]["default"] == "main"
    steps = workflow["jobs"]["check"]["steps"]
    assert any("tools/check_source.py" in str(s.get("run", "")) for s in steps)
    assert (ROOT / "tools" / "check_source.py").is_file()
    caller = yaml.safe_load((ROOT / "docs" / "examples" / "source-ci.yml").read_text(encoding="utf-8"))
    triggers = caller.get("on") or caller.get(True)
    assert "schedule" in triggers and "push" in triggers  # once a week and on every change
    assert caller["jobs"]["check"]["uses"] == "Matze89x/ha-car-assistant/.github/workflows/check-source.yml@main"
