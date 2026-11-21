import os
import time

from carassistant import tiles

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


def test_tile_validation():
    assert tiles.valid(0, 0, 0) and tiles.valid(17, 70000, 42000)
    assert not tiles.valid(20, 0, 0) and not tiles.valid(3, 8, 0) and not tiles.valid(3, 0, -1)


def test_tiles_off_by_default_then_cached_fetch_with_identifying_agent(client, monkeypatch):
    assert client.get("/tiles/3/4/2.png").status_code == 404  # the map is off by default: nothing is fetched
    client.post("/settings/map", data={"tiles": "1"})
    seen = []

    class Reply:
        status_code = 200
        content = PNG
        headers = {"content-type": "image/png"}

    def fake_get(url, headers=None, timeout=None):
        seen.append((url, headers))
        return Reply()

    monkeypatch.setattr(tiles.requests, "get", fake_get)
    first = client.get("/tiles/3/4/2.png")
    again = client.get("/tiles/3/4/2.png")
    assert first.status_code == again.status_code == 200 and first.content == PNG
    assert len(seen) == 1  # the second request comes from the disk
    assert seen[0][0] == "https://tile.openstreetmap.org/3/4/2.png"
    assert seen[0][1]["User-Agent"].startswith("CarAssistant/") and "github.com" in seen[0][1]["User-Agent"]
    assert client.get("/tiles/3/9/2.png").status_code == 404  # outside the world


def test_stale_tile_is_used_when_the_service_is_down(client, monkeypatch):
    client.post("/settings/map", data={"tiles": "1"})
    path = tiles.path_of(2, 1, 1)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(PNG)
    old = time.time() - tiles.MAX_AGE - 100
    os.utime(path, (old, old))

    def down(url, headers=None, timeout=None):
        raise tiles.requests.ConnectionError("offline")

    monkeypatch.setattr(tiles.requests, "get", down)
    assert client.get("/tiles/2/1/1.png").content == PNG
    assert client.get("/tiles/2/1/2.png").status_code == 502  # never seen and not reachable
