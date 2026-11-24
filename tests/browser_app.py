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


@contextmanager
def running_app(package: dict | None = None):
    """Yields ``(base, slug, pk)``: the address of the app, the slug of the first demo car and the id of the installed package (or None)."""
    import make_screenshots as ms

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "app"
        data.mkdir()
        env = {
            **os.environ,
            "PYTHONPATH": os.pathsep.join([str(ROOT / "carassistant" / "app"), str(ROOT / "tools"), str(ROOT)]),
            "CARASSISTANT_DATA": str(data),
            "CARASSISTANT_DEV": "1",
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
            yield base, ms.DIESEL, pk
        finally:
            server.terminate()
            server.wait(timeout=10)
