"""Checks a whole SOURCE (a repository with plugins/, integrations/ and vehicles/) against THIS version of Car Assistant.

    python tools/check_source.py <folder of the source>

Every package of ``integrations/index.json`` and ``plugins/index.json`` is read the way the app reads it (tools/check_plugin.py), the indexes are
compared with the folders (ids, versions, checksums), and the vehicle files of ``vehicles/index.json`` must be zips that exist. Errors end with exit
code 1; hints (a typo in a key, a missing icon or translation) are printed but do not fail.

It lives in the app so that it is always as new as the app: the reusable workflow ``.github/workflows/check-source.yml`` runs it on a source every
week and on every change (see docs/sources.md, "Keeping a source current").
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "carassistant" / "app"))

import check_plugin  # noqa: E402

from carassistant import __version__  # noqa: E402

ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")


def _json(path: Path, problems: list[str], root: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        problems.append(f"{path.relative_to(root)}: {exc}")
        return None


def check_source(root: Path) -> tuple[list[str], list[str], int]:
    """``(errors, hints, number of packages)`` for the source in ``root``."""
    errors: list[str] = []
    hints: list[str] = []
    count = 0
    for kind in ("integrations", "plugins"):
        folder = root / kind
        if not folder.is_dir():
            continue
        index = _json(folder / "index.json", errors, root) if (folder / "index.json").is_file() else None
        if not isinstance(index, dict) or not isinstance(index.get("packages"), list):
            errors.append(f"{kind}/index.json: needs a list under 'packages'")
            continue
        listed: set[str] = set()
        for item in index["packages"]:
            pid = item.get("id") if isinstance(item, dict) else None
            if not isinstance(pid, str) or not ID.match(pid):
                errors.append(f"{kind}/index.json: bad or missing id {pid!r}")
                continue
            if pid in listed:
                errors.append(f"{kind}/index.json: id {pid} listed twice")
            listed.add(pid)
            target = folder / pid
            if not (target / "plugin.json").is_file():
                errors.append(f"{kind}/{pid}: no plugin.json in the folder")
                continue
            count += 1
            problems, notes = check_plugin.check(target)
            errors += [f"{kind}/{pid}: {p}" for p in problems]
            hints += [f"{kind}/{pid}: {n}" for n in notes]
            try:
                version = str(json.loads((target / "plugin.json").read_text(encoding="utf-8")).get("version", ""))
            except ValueError:
                continue
            if version != str(item.get("version", "")):
                errors.append(
                    f"{kind}/{pid}: the version differs between index.json ({item.get('version', '')!r}) and plugin.json ({version!r})"
                )
        for name in sorted(p.name for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")):
            if name not in listed:
                errors.append(f"{kind}/{name}: the folder is not listed in {kind}/index.json")
    vehicles = root / "vehicles"
    if (vehicles / "index.json").is_file():
        index = _json(vehicles / "index.json", errors, root)
        for item in (index or {}).get("vehicles", []) if isinstance(index, dict) else []:
            file = vehicles / str(item.get("file", ""))
            if not item.get("id") or not file.is_file():
                errors.append(f"vehicles/index.json: {item.get('id')!r} needs an existing file ({item.get('file')!r})")
            elif not zipfile.is_zipfile(file):
                errors.append(f"vehicles/{file.name}: is no zip file")
    if count == 0 and not errors:
        hints.append("no package found: is this the folder of a source (with plugins/ or integrations/)?")
    return errors, hints, count


def main(argv: list[str]) -> int:
    root = Path(argv[0] if argv else ".").resolve()
    errors, hints, count = check_source(root)
    print(f"Car Assistant {__version__}: {count} package(s) in {root.name}")
    for line in hints:
        print(f"  hint   {line}")
    for line in errors:
        print(f"  ERROR  {line}")
    print("OK" if not errors else f"{len(errors)} problem(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
