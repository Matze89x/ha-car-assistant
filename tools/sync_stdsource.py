#!/usr/bin/env python3
"""Puts a copy of the standard source (the repository ha-car-assistant-sources) into the app, so that it works without any connection.

    python tools/sync_stdsource.py <folder of the source>          check the source, then copy it into carassistant/app/carassistant/stdsource/
    python tools/sync_stdsource.py --check <folder of the source>  only compare: exit code 1 when the copy of the app is behind (or differs)

Why a copy: GitHub allows 60 requests an hour per internet address for its API, and every program behind that address shares them. The app reads public
sources from raw.githubusercontent.com and keeps what it read, but the standard source is also what a fresh start and the demo cars need - so it comes
with the app and is read from there until the person updates it (docs/sources.md, "The standard source comes with the app").

Run it before every release and when the source changed: the copy is what people get with an update of the add-on (dev and main alike). It copies
``index.json``, ``integrations/``, ``plugins/`` and ``vehicles/`` (what the app reads, nothing else) and writes ``VERSION``: the commit of the source,
or - for a folder that is no checkout - a checksum of the files; a change of it makes the app list its copy again (``sources.seed_bundled``)."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "carassistant" / "app" / "carassistant" / "stdsource"
PARTS = ("integrations", "plugins", "vehicles")


def files(source: Path) -> list[Path]:
    """The files of the source the app reads, relative to it (sorted)."""
    found = [Path("index.json")] if (source / "index.json").is_file() else []
    for part in PARTS:
        found += sorted(p.relative_to(source) for p in (source / part).rglob("*") if p.is_file())
    return found


def version_of(source: Path, listed: list[Path]) -> str:
    done = subprocess.run(["git", "-C", str(source), "rev-parse", "--short=12", "HEAD"], capture_output=True, text=True, check=False)  # noqa: S603, S607
    if done.returncode == 0 and done.stdout.strip():
        dirty = subprocess.run(["git", "-C", str(source), "status", "--porcelain"], capture_output=True, text=True, check=False)  # noqa: S603, S607
        return done.stdout.strip() + ("+" if dirty.stdout.strip() else "")
    digest = hashlib.sha256()
    for rel in listed:
        digest.update(str(rel).encode() + (source / rel).read_bytes())
    return "sha256-" + digest.hexdigest()[:12]


def differences(source: Path) -> list[str]:
    listed = files(source)
    have = sorted(p.relative_to(TARGET) for p in TARGET.rglob("*") if p.is_file() and p.name != "VERSION") if TARGET.is_dir() else []
    out = [f"missing in the app: {p}" for p in listed if p not in have]
    out += [f"not in the source any more: {p}" for p in have if p not in listed]
    out += [f"differs: {p}" for p in listed if p in have and (source / p).read_bytes() != (TARGET / p).read_bytes()]
    return out


def main(argv: list[str]) -> int:
    check = "--check" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1 or not Path(args[0]).is_dir():
        print(__doc__)
        return 2
    source = Path(args[0]).resolve()
    if check:
        diff = differences(source)
        print(
            "the copy in the app is the same as the source" if not diff else "the copy in the app is behind:\n  " + "\n  ".join(diff[:20])
        )
        return 1 if diff else 0
    sys.path.insert(0, str(ROOT / "tools"))
    import check_source

    if check_source.main([str(source)]) != 0:
        print("the source has errors - nothing was copied")
        return 1
    listed = files(source)
    if TARGET.is_dir():
        shutil.rmtree(TARGET)
    for rel in listed:
        (TARGET / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, TARGET / rel)
    (TARGET / "VERSION").write_text(version_of(source, listed) + "\n", encoding="utf-8")
    size = sum(p.stat().st_size for p in TARGET.rglob("*") if p.is_file())
    print(
        f"copied {len(listed)} files ({size // 1024} kB) into {TARGET.relative_to(ROOT)}, version {(TARGET / 'VERSION').read_text().strip()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
