import io

from PIL import Image

from carassistant import db, media


def _png(color="red"):
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(buf, "PNG")
    return buf.getvalue()


def _mp4():
    return b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 2048


def _vehicle(client):
    client.post("/vehicles", data={"name": "Media Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        return conn.execute("SELECT id FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()[0]


def test_sniff_by_content_not_name():
    assert media.sniff(_png()[:16])[:2] == ("photo", "png")
    assert media.sniff(b"\xff\xd8\xff\xe0" + b"0" * 12)[:2] == ("photo", "jpg")
    assert media.sniff(_mp4()[:16])[:2] == ("video", "mp4")
    assert media.sniff(b"\x00\x00\x00\x18ftypqt  " + b"0" * 4)[:2] == ("video", "mov")
    assert media.sniff(b"\x1a\x45\xdf\xa3" + b"0" * 12)[:2] == ("video", "webm")
    assert media.sniff(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    assert media.sniff(b"MZ\x90\x00" + b"0" * 12) is None


def test_upload_photo_and_video_and_show_video_on_home(client):
    vid = _vehicle(client)
    r = client.post(f"/v/{vid}/media", files={"file": ("renamed.txt", _png(), "text/plain")})
    assert r.status_code == 303 and "m=saved" in r.headers["location"]  # the name does not matter
    assert client.get(f"/v/{vid}/photo").content == _png()
    r = client.post(f"/v/{vid}/media", files={"file": ("car.mp4", _mp4(), "video/mp4")})
    assert "m=saved" in r.headers["location"]
    with db.tx() as conn:
        mid = media.active(conn, vid)["id"]
    assert client.get(f"/v/{vid}/media/{mid}/file").headers["content-type"] == "video/mp4"
    ranged = client.get(f"/v/{vid}/media/{mid}/file", headers={"Range": "bytes=0-99"})
    assert ranged.status_code == 206  # iPhones only play videos that can be read in ranges
    home = client.get(f"/v/{vid}").text
    assert "hero-video" in home and f"/media/{mid}/file" in home
    assert "Photos" in client.get(f"/v/{vid}/media").text


def test_rejects_wrong_files(client):
    vid = _vehicle(client)
    for name, body in (("a.svg", b"<svg/>"), ("a.png", b"MZ" + b"0" * 600), ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 600)):
        r = client.post(f"/v/{vid}/media", files={"file": (name, body, "image/png")})
        assert "err.file_type" in r.headers["location"], name
    with db.tx() as conn:
        assert conn.execute("SELECT COUNT(*) FROM vehicle_media").fetchone()[0] == 0


def test_sixth_upload_removes_the_oldest(client):
    vid = _vehicle(client)
    for i in range(media.KEEP + 1):
        client.post(f"/v/{vid}/media", files={"file": (f"{i}.png", _png(f"#{i:02x}0000"), "image/png")})
    with db.tx() as conn:
        rows = conn.execute("SELECT * FROM vehicle_media WHERE vehicle_id = ? ORDER BY id", (vid,)).fetchall()
        assert len(rows) == media.KEEP
        assert rows[-1]["id"] == media.active(conn, vid)["id"]
        files = {p.name for p in media.folder(vid).iterdir()}
    assert files == {r["file"] for r in rows}  # the oldest file is gone from the disk as well


def test_use_delete_and_background_kind(client):
    vid = _vehicle(client)
    client.post(f"/v/{vid}/media", files={"file": ("a.png", _png("red"), "image/png")})
    client.post(f"/v/{vid}/media", files={"file": ("b.png", _png("blue"), "image/png")})
    with db.tx() as conn:
        first, second = [r["id"] for r in conn.execute("SELECT id FROM vehicle_media ORDER BY id")]
    client.post(f"/v/{vid}/media/{first}/use", data={"for": "photo"})
    assert client.get(f"/v/{vid}/photo").content == _png("red")
    client.post(f"/v/{vid}/media/{first}/delete")  # the shown one is deleted: the other takes over
    assert client.get(f"/v/{vid}/photo").content == _png("blue")
    client.post(f"/v/{vid}/media/{second}/delete")
    assert client.get(f"/v/{vid}/photo").status_code == 404
    client.post(f"/v/{vid}/media/kind", data={"kind": "black"})
    with db.tx() as conn:
        assert conn.execute("SELECT media_kind FROM vehicles WHERE id = ?", (vid,)).fetchone()[0] == "black"
    other = _vehicle(client)
    assert client.post(f"/v/{other}/media/{first}/use").status_code == 404  # items belong to one car


def test_old_photo_becomes_library_item(env):
    from carassistant import config

    with db.tx() as conn:
        vid = conn.execute("INSERT INTO vehicles(name, fuel_type, photo) VALUES('Old', 'petrol', '1.png')").lastrowid
        folder = config.files_dir() / "photos"
        folder.mkdir(exist_ok=True)
        (folder / f"{vid}.png").write_bytes(_png())
        media.import_legacy(conn)
        row = media.active(conn, vid)
    assert row is not None and row["kind"] == "photo"
    assert not (folder / f"{vid}.png").exists()


def test_home_chips_only_when_there_is_something(client):
    vid = _vehicle(client)
    with db.tx() as conn:
        conn.executemany(
            "INSERT INTO tasks(vehicle_id, title, interval_km, interval_months, keywords) VALUES(?,?,?,?,?)",
            [
                (vid, "Engine oil & filter", 15000, 12, "oil"),
                (vid, "Brake fluid", None, 24, "brake fluid"),
                (vid, "Coolant", None, 60, "coolant"),
                (vid, "Air filter", 30000, 24, "air filter"),
                (vid, "Battery check", None, 24, "battery"),
            ],
        )
    page = client.get(f"/v/{vid}").text
    assert 'class="schip' in page and "hero-row-bottom" in page  # tasks exist -> the maintenance box shows
    with db.tx() as conn:
        conn.execute("DELETE FROM tasks WHERE vehicle_id = ?", (vid,))
    page = client.get(f"/v/{vid}").text
    assert 'class="schip' not in page and "hero-row-bottom" not in page  # nothing to show: the row is not even there


def test_home_editor_window_and_return_to_home(client):
    vid = _vehicle(client)
    page = client.get(f"/v/{vid}").text
    assert 'id="pe"' in page and 'class="hero-edit"' in page and 'name="back" value="home"' in page  # the picture has its own Edit button
    assert (
        'id="wd-toggle"' in page and 'data-open="pe"' not in page.split('id="wd-toggle"')[1].split(">")[0]
    )  # "Edit page" itself opens no window
    r = client.post(f"/v/{vid}/media", data={"back": "home"}, files={"file": ("a.png", _png(), "image/png")})
    assert "?edit=1" in r.headers["location"]  # the window opens again after the upload
    with db.tx() as conn:
        mid = media.active(conn, vid)["id"]
    r = client.post(f"/v/{vid}/media/{mid}/delete", data={"back": "home"})
    assert "?edit=1" in r.headers["location"]
    r = client.post(f"/v/{vid}/media/kind", data={"kind": "black"})
    assert r.headers["location"].split("?")[0].endswith("/media")  # without "back" the library page stays the target


def test_settings_are_three_tabs_car_user_system(client):
    create = client.post("/vehicles", data={"name": "A", "fuel_type": "petrol"})
    assert create.status_code in (200, 303)
    assert client.get("/settings").headers["location"].endswith("/settings/car")  # the first tab is the start page
    for section in ("car", "user", "system"):
        page = client.get(f"/settings/{section}")
        assert page.status_code == 200
        assert f'href="/settings/{section}"' in page.text and 'class="seg-tabs"' in page.text, section
    assert (
        'href="/settings/design"' not in client.get("/settings/user").text
        and 'href="/settings/region"' not in client.get("/settings/user").text
    )
    assert 'id="account"' in client.get("/settings/user").text and 'id="blocked"' in client.get("/settings/user").text
    system = client.get("/settings/system").text
    assert (
        'name="theme"' in system and 'name="language"' in system and 'name="units"' in system
    )  # Design and Region are cards of System now
    for old in ("design", "region"):
        assert client.get(f"/settings/{old}").status_code == 200  # the old addresses keep working
    car = client.get("/settings/car").text
    assert 'id="media"' in car and 'id="theme"' in car and 'id="ha"' in car and 'id="notifications"' not in car and 'id="vbackup"' in car
    assert 'name="language"' not in car and 'id="mqtt"' not in car  # nothing of the system on the Car tab
    assert car.index('id="icons"') < car.index('id="media"')  # the car's icon comes before photo and video
    assert 'id="icons"' not in system and 'id="sync"' not in system  # the app icon is fixed; "read sensors again" sits in the sensors card
    assert "accent-pick" in system and "never change" not in system and "ändern sich nie" not in system
    assert 'action="/settings/refresh-live"' in system.split('id="mqtt"')[1].split("</section>")[0]
    assert (
        'name="tiles"' in system and 'action="/settings/reset"' in system and "settings/security" in system
    )  # map, reset, sign-in protection
    assert "ko-fi" not in system  # support is asked on the About page only
    assert 'id="navlist"' not in system  # the navigation belongs to the vehicle
    assert client.get("/settings/backup.zip").status_code == 200
    assert client.get("/settings/unknown").status_code in (404, 405)


def test_units_and_currency_belong_to_the_server(client):
    from carassistant import units

    client.post("/vehicles", data={"name": "A", "fuel_type": "petrol"})
    assert units.of(None).system == "metric"
    assert "units_" not in client.get("/settings/region").text  # no per-vehicle choice: it is one setting for the whole server
    client.post("/settings/units", data={"units": "us", "currency": "USD"})
    mine = units.of(None)
    assert mine.system == "us" and mine.currency == "USD" and mine.cur == "$"
    assert round(mine.d(100), 1) == 62.1 and mine.dist_unit == "mi"
    assert round(mine.c(8), 1) == 29.4 and mine.consumption_unit() == "mpg"  # 8 L/100 km = 29.4 mpg (US)
    assert round(mine.t(20)) == 68 and round(mine.p(2.0), 1) == 29.0
    client.post("/settings/units", data={"units": "metric", "currency": "EUR"})
    assert units.of(None).system == "metric" and units.of(None).cur == "€"
    assert round(units.Units("uk", "GBP").c(8), 1) == 35.3  # 8 L/100 km = 35.3 mpg (UK)


def test_video_works_without_a_photo_and_two_separate_choices(client):
    vid = _vehicle(client)
    r = client.post(f"/v/{vid}/media", files={"file": ("car.mp4", _mp4(), "video/mp4")})
    assert "m=saved" in r.headers["location"]  # a first video works without any photo
    with db.tx() as conn:
        assert (
            media.active(conn, vid)["kind"] == "video"
            and conn.execute("SELECT photo FROM vehicles WHERE id = ?", (vid,)).fetchone()[0] is None
        )
    client.post(f"/v/{vid}/media", files={"file": ("a.png", _png("red"), "image/png")})
    client.post(f"/v/{vid}/media", files={"file": ("b.png", _png("blue"), "image/png")})
    client.post(f"/v/{vid}/media", files={"file": ("car.mp4", _mp4(), "video/mp4")})
    with db.tx() as conn:
        v = conn.execute("SELECT photo_id, media_id FROM vehicles WHERE id = ?", (vid,)).fetchone()
        video = conn.execute("SELECT id FROM vehicle_media WHERE kind = 'video' ORDER BY id DESC").fetchone()["id"]
        assert v["media_id"] == video and v["photo_id"] != video  # Dashboard: the video; lists / car choice: still a photo
        photos = [r["id"] for r in conn.execute("SELECT id FROM vehicle_media WHERE kind = 'photo' ORDER BY id")]
    assert client.get(f"/v/{vid}/photo").content == _png("blue")
    client.post(f"/v/{vid}/media/{photos[0]}/use", data={"for": "photo"})  # the list photo changes, the Dashboard keeps the video
    with db.tx() as conn:
        v = conn.execute("SELECT photo_id, media_id FROM vehicles WHERE id = ?", (vid,)).fetchone()
        assert v["photo_id"] == photos[0] and v["media_id"] == video
    assert client.post(f"/v/{vid}/media/{video}/use", data={"for": "photo"}).status_code == 404  # a video is never the list photo
    client.post(f"/v/{vid}/media/{photos[1]}/use", data={"for": "home"})
    with db.tx() as conn:
        assert conn.execute("SELECT media_id FROM vehicles WHERE id = ?", (vid,)).fetchone()[0] == photos[1]


def test_photo_and_video_live_on_the_car_tab_not_on_the_passport(client):
    vid = _vehicle(client)
    page = client.get(f"/settings/car?car={vid}").text
    assert 'id="media"' in page and ("Foto und Video" in page or "Photo and video" in page)
    assert 'name="photo"' not in page  # the old file field is gone
    assert 'id="media"' not in client.get(f"/v/{vid}/edit?mode=form").text  # moved over: it is not on the passport any more


def test_five_files_per_car_in_total_and_the_last_photo_stays(client):
    vid = _vehicle(client)
    client.post(f"/v/{vid}/media", files={"file": ("p.png", _png("red"), "image/png")})  # the only photo, also the oldest
    for _ in range(media.KEEP - 1):
        client.post(f"/v/{vid}/media", files={"file": ("v.mp4", _mp4(), "video/mp4")})
    client.post(f"/v/{vid}/media", files={"file": ("v.mp4", _mp4(), "video/mp4")})  # one more than fits
    with db.tx() as conn:
        rows = conn.execute("SELECT kind, file FROM vehicle_media WHERE vehicle_id = ? ORDER BY id", (vid,)).fetchall()
        files = {p.name for p in media.folder(vid).iterdir()}
    kinds = [r["kind"] for r in rows]
    assert files == {r["file"] for r in rows}  # the dropped file is deleted from the server's disk as well
    assert len(kinds) == media.KEEP and "photo" in kinds  # KEEP at most; the photo survived, an older video went instead


def test_ground_glow_only_for_default_car_and_png(client):
    vid = _vehicle(client)
    assert "hero-car-wrap default-car glow" in client.get(f"/v/{vid}").text  # default car: glow
    client.post(f"/v/{vid}/media", files={"file": ("a.png", _png(), "image/png")})
    page = client.get(f"/v/{vid}").text
    assert "hero-car-wrap glow" in page and "default-car" not in page.split("hero-car-wrap")[1][:40]  # PNG photo: glow
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buf, "JPEG")
    client.post(f"/v/{vid}/media", files={"file": ("a.jpg", buf.getvalue(), "image/jpeg")})
    assert "hero-car-wrap glow" not in client.get(f"/v/{vid}").text  # JPEG: none
    client.post(f"/v/{vid}/media", files={"file": ("v.mp4", _mp4(), "video/mp4")})
    assert "glow" not in client.get(f"/v/{vid}").text.split("hero-pic")[0].split("hero-car-wrap")[1]  # video: none


def test_choose_saves_both_choices_at_once(client):
    vid = _vehicle(client)
    for color in ("red", "blue"):
        client.post(f"/v/{vid}/media", files={"file": (f"{color}.png", _png(color), "image/png")})
    client.post(f"/v/{vid}/media", files={"file": ("v.mp4", _mp4(), "video/mp4")})
    with db.tx() as conn:
        ids = {r["kind"] + str(i): r["id"] for i, r in enumerate(conn.execute("SELECT id, kind FROM vehicle_media ORDER BY id"))}
    red, video = ids["photo0"], ids["video2"]
    client.post(f"/v/{vid}/media/choose", data={"home": str(video), "photo": str(red), "back": "edit"})
    with db.tx() as conn:
        v = conn.execute("SELECT media_id, photo_id FROM vehicles WHERE id = ?", (vid,)).fetchone()
    assert (v["media_id"], v["photo_id"]) == (video, red)
    page = client.get(f"/settings/car?car={vid}").text
    assert 'name="home"' in page and 'name="photo"' in page and "media/choose" in page


def _jpeg(size, orientation=None):
    buf = io.BytesIO()
    image = Image.new("RGB", size, "blue")
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    exif[0x8825] = {1: "N"}  # a GPS block that must not survive
    image.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def test_big_jpeg_is_scaled_down_upright_and_without_metadata(client, monkeypatch):
    monkeypatch.setattr(media, "SHRINK_FROM", 1)  # shrink even this small test photo
    vid = _vehicle(client)
    client.post(f"/v/{vid}/media", files={"file": ("big.jpg", _jpeg((4000, 3000)), "image/jpeg")})
    stored = Image.open(io.BytesIO(client.get(f"/v/{vid}/photo").content))
    assert max(stored.size) == media.MAX_SIDE and stored.size == (1920, 1440)
    assert not stored.getexif()  # no GPS / camera data kept
    client.post(f"/v/{vid}/media", files={"file": ("turned.jpg", _jpeg((300, 200), orientation=6), "image/jpeg")})
    turned = Image.open(io.BytesIO(client.get(f"/v/{vid}/photo").content))
    assert turned.size == (200, 300)  # turned upright (camera orientation applied)


def test_png_is_never_touched(client):
    vid = _vehicle(client)
    big = io.BytesIO()
    Image.new("RGBA", (3000, 2000), (0, 0, 0, 0)).save(big, "PNG")
    client.post(f"/v/{vid}/media", files={"file": ("cut.png", big.getvalue(), "image/png")})
    assert client.get(f"/v/{vid}/photo").content == big.getvalue()


def test_a_photo_above_the_stored_limit_is_shrunk_not_refused(client, monkeypatch):
    vid = _vehicle(client)
    big = Image.linear_gradient("L").resize((4000, 3000)).convert("RGB")
    buf = io.BytesIO()
    big.save(buf, "JPEG", quality=95)
    limit = len(buf.getvalue()) // 3
    monkeypatch.setattr(media, "MAX_PHOTO", limit)  # pretend a third of this photo is the stored limit
    monkeypatch.setattr(media, "SHRINK_FROM", 1)
    r = client.post(f"/v/{vid}/media", files={"file": ("big.jpg", buf.getvalue(), "image/jpeg")})
    assert "m=saved" in r.headers["location"]
    stored = client.get(f"/v/{vid}/photo").content
    assert len(stored) <= limit and max(Image.open(io.BytesIO(stored)).size) <= media.MAX_SIDE


def test_small_photos_and_videos_stay_exactly_as_uploaded(client):
    vid = _vehicle(client)
    small = _jpeg((3000, 2000), orientation=6)  # well below 2 MB: not touched (neither scaled nor stripped)
    assert len(small) < media.SHRINK_FROM
    client.post(f"/v/{vid}/media", files={"file": ("small.jpg", small, "image/jpeg")})
    assert client.get(f"/v/{vid}/photo").content == small
    video = _mp4() + b"\x01" * 5000
    client.post(f"/v/{vid}/media", files={"file": ("clip.mp4", video, "video/mp4")})
    with db.tx() as conn:
        mid = media.active(conn, vid)["id"]
    assert client.get(f"/v/{vid}/media/{mid}/file").content == video


def test_video_poster_is_stored_served_and_removed(client):
    vid = _vehicle(client)
    video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 600
    client.post(
        f"/v/{vid}/media",
        files={"file": ("a.mp4", video, "video/mp4"), "poster": ("poster.jpg", b"\xff\xd8\xff\xe0" + b"1" * 50, "image/jpeg")},
    )
    with db.tx() as conn:
        row = conn.execute("SELECT id FROM vehicle_media WHERE kind = 'video'").fetchone()
    mid = row["id"]
    assert client.get(f"/v/{vid}/media/{mid}/poster").headers["content-type"] == "image/jpeg"
    assert f"/media/{mid}/poster" in client.get(f"/v/{vid}/media").text
    client.post(f"/v/{vid}/media/{mid}/delete")
    assert client.get(f"/v/{vid}/media/{mid}/poster").status_code == 404


def test_a_poster_that_is_not_a_jpeg_is_ignored(client):
    vid = _vehicle(client)
    video = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 600
    client.post(f"/v/{vid}/media", files={"file": ("a.mp4", video, "video/mp4"), "poster": ("poster.jpg", b"<html>", "image/jpeg")})
    with db.tx() as conn:
        mid = conn.execute("SELECT id FROM vehicle_media WHERE kind = 'video'").fetchone()["id"]
    assert client.get(f"/v/{vid}/media/{mid}/poster").status_code == 404


def test_home_keeps_a_still_of_the_video_when_it_is_left_and_goes_on_where_it_stopped(client):
    js = client.get("/static/media.js").text
    assert 'addEventListener("ca:leave"' in js and "resumeAt" in js and '":t"' in js  # a picture is kept on leaving, the time too
    assert 'new Event("ca:leave")' in client.get("/static/softnav.js").text  # the instant page change announces that Home is left
