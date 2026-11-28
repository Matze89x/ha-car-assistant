"""A real app on a free port with the demo cars (and, when asked, one package installed on the first car), for the tests that drive a real browser
(tools/cdp.py). Not a test file."""

import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

INSTALL = (
    "import json, sys; from carassistant import addons, db\n"
    "with db.tx() as conn:\n"
    "    vid = conn.execute('SELECT id FROM vehicles WHERE slug = ?', (sys.argv[1],)).fetchone()['id']\n"
    "    source = conn.execute('SELECT id FROM sources LIMIT 1').fetchone()['id']\n"
    "    pk = addons.add(conn, vid, addons.parse_package(json.dumps(json.loads(sys.argv[2])).encode()), source, '0' * 64)\n"
    "    conn.execute('UPDATE vehicle_addons SET active = 1 WHERE id = ?', (pk,))\n"
    "    print(pk)\n"
)

OFFER = (  # the source offers a newer version of a package and keeps its changelog (as if it had been read a minute ago: nothing goes online)
    "import json, sys; from datetime import UTC, datetime; from carassistant import db\n"
    "spec = json.loads(sys.argv[1])\n"
    "with db.tx() as conn:\n"
    "    source = conn.execute('SELECT id FROM sources LIMIT 1').fetchone()['id']\n"
    "    conn.execute('DELETE FROM source_packages WHERE source_id = ? AND kind = ? AND pkg_id = ?', (source, spec['kind'], spec['id']))\n"
    "    conn.execute('INSERT INTO source_packages(source_id, kind, pkg_id, name, description, version, icon) VALUES(?,?,?,?,?,?,?)', "
    "(source, spec['kind'], spec['id'], spec['name'], '', spec['version'], ''))\n"
    "    now = datetime.now(UTC).isoformat(timespec='seconds')\n"
    "    for path, body in spec.get('files', {}).items():\n"
    "        conn.execute('INSERT INTO source_cache(source_id, path, etag, body, checked_at) VALUES(?,?,?,?,?) "
    "ON CONFLICT(source_id, path) DO UPDATE SET body = excluded.body, checked_at = excluded.checked_at', (source, path, 'x', body.encode(), now))\n"
)


@contextmanager
def running_app(package: dict | None = None, extra_env: dict | None = None, offer: dict | None = None):
    """Yields ``(base, slug, pk)``: the address of the app, the slug of the first demo car and the id of the installed package (or None).
    ``extra_env``: more variables for the app (for example the address and token of a made-up Home Assistant). ``offer``: the source offers a newer
    version of a package - ``{"kind", "id", "name", "version", "files": {path of the source: text}}`` (the files are kept as if read a minute ago)."""
    import make_screenshots as ms

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "app"
        data.mkdir()
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(ROOT / "carassistant" / "app"), str(ROOT / "tools"), str(ROOT)]),
            "CARASSISTANT_DATA": str(data),
            "CARASSISTANT_DEV": "1",
            **(extra_env or {}),
        }
        seed = "import sys; from pathlib import Path; import make_screenshots as ms; ms.seed(Path(sys.argv[1]), 'en')"
        subprocess.run([sys.executable, "-c", seed, str(data)], check=True, env=env, capture_output=True, timeout=120)
        pk = None
        if package is not None:
            done = subprocess.run(
                [sys.executable, "-c", INSTALL, ms.DIESEL, json.dumps(package)],
                check=True,
                env=env,
                capture_output=True,
                timeout=60,
                cwd=ROOT,
                text=True,
            )
            pk = int(done.stdout.strip().splitlines()[-1])
        port = ms.free_port()
        server = subprocess.Popen(
            [sys.executable, "-m", "carassistant"],
            env={**env, "CARASSISTANT_PORT": str(port)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            ms.wait_for(base + "/healthz")
            if offer is not None:  # after the start: the app lists the copy of the standard source when it starts
                subprocess.run(
                    [sys.executable, "-c", OFFER, json.dumps(offer)], check=True, env=env, capture_output=True, timeout=60, cwd=ROOT
                )
            yield base, ms.DIESEL, pk
        finally:
            server.terminate()
            server.wait(timeout=10)
