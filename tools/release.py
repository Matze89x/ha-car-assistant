#!/usr/bin/env python3
"""The ONE place of the version and the release stage: ``release.json`` in the repository root.

Version scheme ``RELEASE.FEATURES.FIXES`` (the first number stays 0 until the first official release):
  - the first number counts releases,
  - the second one counts feature versions (a new feature: second number up, third back to 0),
  - the third one counts bug fixes and corrections.
The stage (``Alpha`` -> ``Beta`` -> later none) is shown next to the version everywhere.

Usage (from the repository root):
  python tools/release.py                      show the current release and whether every place agrees
  python tools/release.py sync                 write release.json into every place (after editing release.json by hand)
  python tools/release.py set 0.5.0 Beta ["EN line" "DE line"]   set the version and the stage, then write them everywhere
  python tools/release.py fix  "English text" "Deutscher Text"       next fix version (0.4.0 -> 0.4.1) + a line in both changelogs
  python tools/release.py feature "English" "Deutsch"                next feature version (0.4.1 -> 0.5.0) + changelog lines
  python tools/release.py check                exit code 1 when a place disagrees (the tests run this too)

Places that get the value: pyproject.toml, carassistant/config.yaml (version and the stage in front of the description),
carassistant/app/carassistant/__init__.py (``__version__`` and ``STAGE``), the marked block ``<!-- release:start -->`` of the four
readme / docs pages, and the newest heading of both changelogs.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release.json"
START, END = "<!-- release:start -->", "<!-- release:end -->"
PAGES = {  # file -> how the block looks there ("rich" = badge + text, "plain" = text only: the add-on page cannot show images)
    "README.md": ("en", "rich"),
    "README.de.md": ("de", "rich"),
    "carassistant/README.md": ("en", "plain"),
    "carassistant/DOCS.md": ("en", "plain"),
}
CHANGELOGS = {"carassistant/CHANGELOG.md": "en", "carassistant/CHANGELOG.de.md": "de"}
VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def load() -> dict:
    data = json.loads(RELEASE.read_text(encoding="utf-8"))
    if not VERSION.match(data["version"]):
        raise SystemExit(f"release.json: '{data['version']}' is not RELEASE.FEATURES.FIXES")
    return data


def label(data: dict) -> str:
    """``0.4.0 Alpha`` (or just the number when there is no stage)."""
    return f"{data['version']} {data['stage']}".strip()


def block(data: dict, lang: str, style: str) -> str:
    note = (data.get("notes", {}).get(data["stage"]) or {}).get(lang, "")
    if style == "plain":
        return f"**{label(data)}** - {note}" if note else f"**{label(data)}**"
    badge = f"[![Release](https://img.shields.io/badge/release-{label(data).replace(' ', '%20')}-orange.svg)](carassistant/CHANGELOG{'.de' if lang == 'de' else ''}.md)"
    return f"{badge} {note}".strip()


def _write(path: Path, text: str) -> bool:
    old = path.read_text(encoding="utf-8")
    if old == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def expected(data: dict) -> dict[Path, str]:
    """What every place has to contain, as {file: full new text} (only places that exist)."""
    out: dict[Path, str] = {}
    v, stage = data["version"], data["stage"]

    p = ROOT / "pyproject.toml"
    out[p] = re.sub(r'(?m)^version = ".*"$', f'version = "{v}"', p.read_text(encoding="utf-8"), count=1)

    p = ROOT / "carassistant" / "config.yaml"
    text = re.sub(r'(?m)^version: ".*"$', f'version: "{v}"', p.read_text(encoding="utf-8"), count=1)
    text = re.sub(r"(?m)^description: (?:(?:Alpha|Beta|RC) · )?", f"description: {f'{stage} · ' if stage else ''}", text, count=1)
    out[p] = text

    p = ROOT / "carassistant" / "app" / "carassistant" / "__init__.py"
    text = p.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^__version__ = ".*"$', f'__version__ = "{v}"', text, count=1)
    text = re.sub(r'(?m)^STAGE = ".*"$', f'STAGE = "{stage}"', text, count=1) if "STAGE = " in text else text.rstrip("\n") + f'\nSTAGE = "{stage}"\n'
    out[p] = text

    for name, (lang, style) in PAGES.items():
        p = ROOT / name
        text = p.read_text(encoding="utf-8")
        new = f"{START}\n{block(data, lang, style)}\n{END}"  # on their own lines: GitHub shows the content between them as normal text
        if START in text:
            text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _m: new, text, count=1, flags=re.S)
        else:  # first time: below the language line (or the first heading)
            lines = text.split("\n")
            at = next((i for i, line in enumerate(lines) if line.startswith("🇬🇧") or line.startswith("[🇬🇧")), None)
            if at is None:
                at = next((i for i, line in enumerate(lines) if line.startswith("# ")), 0)
            lines[at + 1 : at + 1] = ["", new]
            text = "\n".join(lines)
        out[p] = text

    for name in CHANGELOGS:
        p = ROOT / name
        text = p.read_text(encoding="utf-8")
        m = re.search(r"(?m)^## (\d+\.\d+\.\d+)(?: [A-Za-z]+)?$", text)
        if m and m.group(1) == v:  # the newest section is this version: its heading carries the stage
            text = text[: m.start()] + f"## {label(data)}" + text[m.end() :]
        out[p] = text
    return out


def sync(data: dict) -> list[str]:
    return [str(p.relative_to(ROOT)) for p, text in expected(data).items() if _write(p, text)]


def problems(data: dict) -> list[str]:
    bad = [str(p.relative_to(ROOT)) for p, text in expected(data).items() if p.read_text(encoding="utf-8") != text]
    for name in CHANGELOGS:
        first = re.search(r"(?m)^## (\d+\.\d+\.\d+)", (ROOT / name).read_text(encoding="utf-8"))
        if not first or first.group(1) != data["version"]:
            bad.append(f"{name}: the newest section is not {data['version']}")
    return bad


def bump(data: dict, kind: str) -> str:
    major, minor, fix = (int(x) for x in data["version"].split("."))
    if kind == "fix":
        fix += 1
    elif kind == "feature":
        minor, fix = minor + 1, 0
    elif kind == "release":
        major, minor, fix = major + 1, 0, 0
    else:
        raise SystemExit(f"unknown kind '{kind}'")
    return f"{major}.{minor}.{fix}"


def add_changelog(data: dict, texts: dict[str, str]) -> None:
    """A new top section for the (already bumped) version in both changelogs."""
    for name, lang in CHANGELOGS.items():
        p = ROOT / name
        text = p.read_text(encoding="utf-8")
        m = re.search(r"(?m)^## ", text)
        section = f"## {label(data)}\n- {texts[lang].strip()}\n\n"
        p.write_text(text[: m.start()] + section + text[m.start() :] if m else text + "\n" + section, encoding="utf-8")


def main(argv: list[str]) -> int:
    data = load()
    cmd = argv[0] if argv else "show"
    if cmd == "show":
        print(f"{label(data)}")
        bad = problems(data)
        print("every place agrees" if not bad else "out of sync: " + ", ".join(bad) + "  (run: python tools/release.py sync)")
        return 0
    if cmd == "check":
        bad = problems(data)
        print("every place agrees" if not bad else "out of sync: " + ", ".join(bad))
        return 1 if bad else 0
    if cmd == "sync":
        print("written:", ", ".join(sync(data)) or "nothing to do")
        return 0
    if cmd == "set":
        if len(argv) < 2:
            raise SystemExit('usage: release.py set 0.5.0 Beta   (a stage is optional: "" = none)')
        data["version"], data["stage"] = argv[1], argv[2] if len(argv) > 2 else ""
        if not VERSION.match(data["version"]):
            raise SystemExit("the version must look like 0.5.0")
        RELEASE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if len(argv) == 5:  # with changelog lines: the new section is made as well
            add_changelog(data, {"en": argv[3], "de": argv[4]})
        print("written:", ", ".join(sync(data)))
        return 0
    if cmd in ("fix", "feature", "release"):
        if len(argv) != 3:
            raise SystemExit(f'usage: release.py {cmd} "English changelog line" "Deutsche Changelog-Zeile"')
        data["version"] = bump(data, cmd)
        RELEASE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        add_changelog(data, {"en": argv[1], "de": argv[2]})
        print(f"now {label(data)}; written:", ", ".join(sync(data)))
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
