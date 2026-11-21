"""Plugin discovery (in-car connections: something installed in/on the vehicle that Car Assistant talks to).

Plugins are folders below ``<plugin dir>/<id>/`` with a ``plugin.json`` manifest. Only the manifest is read here –
nothing from a plugin folder is executed. See docs/plugins.md for the specification.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)
ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
MAX_MANIFEST = 20_000


@dataclass(frozen=True)
class Plugin:
    id: str
    name: str
    version: str
    description: str
    author: str
    homepage: str


def plugin_dir() -> Path:
    return Path(os.environ.get("CARASSISTANT_PLUGIN_DIR", "/share/carassistant/plugins"))


def _text(data: dict, key: str, limit: int = 300) -> str:
    value = data.get(key)
    return value.strip()[:limit] if isinstance(value, str) else ""


def discover() -> list[Plugin]:
    root = plugin_dir()
    found: list[Plugin] = []
    if not root.is_dir():
        return found
    for folder in sorted(root.iterdir()):
        manifest = folder / "plugin.json"
        if not (folder.is_dir() and ID.match(folder.name) and manifest.is_file() and manifest.stat().st_size <= MAX_MANIFEST):
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.warning("Ignoring invalid plugin manifest in %s", folder.name)
            continue
        if not isinstance(data, dict) or data.get("id") != folder.name:
            continue
        homepage = _text(data, "homepage")
        found.append(
            Plugin(
                id=folder.name,
                name=_text(data, "name", 80) or folder.name,
                version=_text(data, "version", 20),
                description=_text(data, "description"),
                author=_text(data, "author", 80),
                homepage=homepage if homepage.startswith("https://") else "",
            )
        )
    return found
