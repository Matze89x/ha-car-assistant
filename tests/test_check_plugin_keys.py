"""The plugin checker knows every top-level key the app reads from a ``plugin.json`` - it once called ``setup``, ``bundles`` and ``files`` typos."""

import re
from pathlib import Path

import check_plugin  # tools/ is on the path (conftest)


def test_the_checker_knows_every_key_parse_package_reads():
    source = (Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant" / "addons.py").read_text(encoding="utf-8")
    start = source.index("def parse_package")
    body = source[start : source.index("\ndef ", start + 10)]
    read = set(re.findall(r'data(?:\.get\(|\[)"([a-z_0-9]+)"', body))
    assert read and not read - check_plugin.KNOWN, sorted(read - check_plugin.KNOWN)
