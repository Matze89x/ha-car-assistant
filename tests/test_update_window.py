"""The update window of a package (Integrations and Plugins): the line *Update available* and the *Update* button open a window with the installed and the
available version and the changelog of the package, read from its source when the window opens (docs/sources.md, "The changelog of a package").

Nothing here talks to the network: a source answers from a dict, and the files of a source that are not there are "not found"."""

import json
import re
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from carassistant import accounts, addons, auth_web, changelog, config, db, pluginsvc, sources, web

REPO = {
    "integrations/index.json": json.dumps({"packages": []}),
    "plugins/index.json": json.dumps({"packages": [{"id": "demo-one", "name": "Demo One", "description": "First", "version": "1.9"}]}),
    "plugins/demo-one/plugin.json": json.dumps(
        {"id": "demo-one", "name": "Demo One", "version": "1.9", "description": "First", "settings": []}
    ),
}

LOG = """# Changelog

## Unreleased
- Not released yet

## [2.0] - 2026-11-20
### Added
- A **new** page with `settings`
- Read [the guide](https://evil.example/phish) first

### Fixed
- The thing <script>alert(1)</script> and <b>bold</b>

## 1.9 - 2026-10-01
- The version you have

## 1.8
- Older news
"""


@pytest.fixture(autouse=True)
def fake_source(monkeypatch):
    """A source answers from this dict (path -> text); a path that is not in it is 'not found'. ``seen`` lists what was asked for."""
    state = {"files": dict(REPO), "seen": [], "down": set()}

    def fake_http(url, headers, check_host, limit=0):
        state["seen"].append(url)
        for path, text in state["files"].items():
            if url.endswith("/" + path.replace(" ", "%20")):
                if path in state["down"]:
                    raise sources.SourceError("err.src_net")
                return text.encode()
        raise sources.SourceError("err.src_missing")

    monkeypatch.setattr(sources, "_http", fake_http)
    return state


def _text(parsed: dict) -> str:
    """All the words of a parsed changelog in one string."""
    out = []
    for block in parsed["blocks"]:
        out += (
            [t for _k, t in block.get("spans", [])] + [t for it in block.get("rows", []) for _k, t in it["spans"]] + [block.get("text", "")]
        )
    return " ".join(out)


def _car(client):
    """A new car (``vid``, ``slug``) and the standard source (``sid``)."""
    client.post("/vehicles", data={"name": "Window Car", "fuel_type": "petrol"})
    with db.tx() as conn:
        row = conn.execute("SELECT id, slug FROM vehicles ORDER BY id DESC LIMIT 1").fetchone()
        sid = conn.execute("SELECT id FROM sources WHERE is_default = 1").fetchone()[0]
    return SimpleNamespace(vid=row["id"], slug=row["slug"], sid=sid)


def _pk(vid):
    with db.tx() as conn:
        return conn.execute("SELECT id FROM vehicle_addons WHERE vehicle_id = ?", (vid,)).fetchone()["id"]


def _forget_what_was_read():
    """What was kept a minute ago is not what a test is about."""
    with db.tx() as conn:
        conn.execute("DELETE FROM source_cache")


def _offer(client, fake_source, sid, version="2.0", log=None):
    """The source now offers ``version`` of the package (and a changelog, when ``log`` is given)."""
    fake_source["files"]["plugins/index.json"] = json.dumps({"packages": [{"id": "demo-one", "name": "Demo One", "version": version}]})
    fake_source["files"]["plugins/demo-one/plugin.json"] = json.dumps({"id": "demo-one", "name": "Demo One", "version": version})
    if log is not None:
        fake_source["files"]["plugins/demo-one/CHANGELOG.md"] = log
    _forget_what_was_read()
    client.post(f"/sources/{sid}/refresh", data={"kind": "plugin"})


def _window(page: str, pk: int) -> str:
    """The update window of one package out of a page."""
    return re.search(rf'<dialog id="upd-{pk}".*?</dialog>', page, re.S).group(0)


@pytest.fixture()
def offered(client, fake_source):
    """A car with 'Demo One' 1.9 installed from the source, which now offers 2.0 and a changelog (``vid``, ``slug``, ``sid``, ``pk``)."""
    car = _car(client)
    client.post(f"/sources/{car.sid}/refresh", data={"kind": "plugin"})
    client.post(f"/v/{car.vid}/packages/{car.sid}/plugin/demo-one/install")
    _offer(client, fake_source, car.sid, "2.0", LOG)
    car.pk = _pk(car.vid)
    return car


# ------------------------------------------------------------------ the reader


def test_only_what_is_newer_than_the_installed_version_is_shown():
    got = changelog.parse(LOG, "1.9")
    text = _text(got)
    assert got["structured"] and not got["empty"]
    assert "new" in text and "settings" in text and "The thing" in text
    assert "The version you have" not in text and "Older news" not in text  # not news for 1.9
    assert "Not released yet" not in text  # a section without a version is no release
    assert "The version you have" in _text(changelog.parse(LOG, "1.8"))  # the installed version decides what stays
    assert "Older news" in _text(changelog.parse(LOG, "")), "no installed version: everything is new"


def test_versions_are_compared_as_numbers_and_headings_may_look_different():
    text = "# Changes\n\n## v1.10.0\n### Added\n- ten\n\n## Version 1.9 (2026-10-01)\n- nine\n\n## [1.2]\n- two\n"
    got = _text(changelog.parse(text, "1.9"))
    assert "ten" in got and "Added" in got  # a heading under a version belongs to that version
    assert "nine" not in got and "two" not in got  # 1.10 is newer than 1.9 (numbers, not text); 1.9 and 1.2 are not news
    assert changelog.versions(text) == ["1.10.0", "1.9", "1.2"]
    assert changelog.versions("Just some text.\n\n- a\n- b\n") == []  # not in sections per version


def test_a_changelog_without_versions_is_shown_as_it_is():
    got = changelog.parse("Fixed a bug.\n\n- one\n- two\n\n1. first\n2. second\n", "5")
    assert not got["structured"] and not got["empty"]
    assert [b["kind"] for b in got["blocks"]] == ["p", "ul", "ol"]
    assert [it["spans"] for it in got["blocks"][1]["rows"]] == [[("t", "one")], [("t", "two")]]


def test_sections_that_are_all_older_leave_nothing_to_show():
    got = changelog.parse("## 1.0\n- a\n\n## 0.9\n- b\n", "1.0")
    assert got["structured"] and got["empty"] and not got["blocks"]
    assert changelog.parse("   \n\n", "1")["empty"]  # nothing at all


def test_the_markup_becomes_plain_pieces_and_nothing_of_it_stays():
    spans = changelog.spans("**Fixed** the `thing` in [the guide](https://x.example/a) and ![pic](https://x.example/p.png) *really*")
    assert spans == [
        ("b", "Fixed"),
        ("t", " the "),
        ("c", "thing"),
        ("t", " in "),
        ("t", "the guide"),
        ("t", " and "),
        ("t", "pic"),
        ("t", " "),
        ("i", "really"),
    ]
    assert changelog.spans("<b>x</b> & <script>alert(1)</script>") == [("t", "<b>x</b> & <script>alert(1)</script>")]  # text stays text
    assert changelog.spans("snake_case_name and 2*3*4") == [("t", "snake_case_name and 2*3*4")]  # not every underscore is a style
    assert changelog.spans("window.__a=1 and window.__b=2") == [("t", "window.__a=1 and window.__b=2")]  # nor a pair of them inside names
    assert changelog.spans("__bold__ and _it_") == [("b", "bold"), ("t", " and "), ("i", "it")]


def test_comments_control_characters_and_pieces_of_code():
    got = changelog.parse("<!-- hidden note -->\n- visible\x00\x07 item\n\n```\nraw <b>code</b>\n```\n")
    assert "hidden" not in _text(got) and "visible item" in _text(got)
    assert got["blocks"][-1] == {"kind": "code", "text": "raw <b>code</b>"}
    assert changelog.parse("\N{ZERO WIDTH NO-BREAK SPACE}## 1.0\n- a\n", "")["structured"]  # the mark some editors put in front of a file


def test_a_long_changelog_is_cut_not_dumped():
    got = changelog.parse("\n".join(f"- item number {n}" for n in range(5000)))
    assert got["cut"] and len(got["blocks"]) <= changelog.MAX_BLOCKS and len(_text(got)) <= changelog.MAX_TEXT + 6000
    big_line = changelog.parse("x" * 5000)["blocks"][0]["spans"][0][1]
    assert len(big_line) <= changelog.MAX_LINE


def test_a_text_made_to_make_the_reader_slow_is_read_fast():
    """The text comes from a source: nothing in it may keep the page waiting (every pattern works on a line of at most 1000 characters)."""
    import time

    worst = [
        "# x" + " " * 150_000 + "y\n",  # a heading with a long run of blanks
        "<!--" * 50_000 + "\n- a\n",  # thousands of comments that are never closed
        "**a " * 40_000 + "\n",  # emphasis that never closes
        "- " + "[x](" * 30_000 + "\n",  # links that never end
        ("`" * 3 + "\n") * 20_000,  # pieces of code
        "\n".join(f"## {n}.0\n- a" for n in range(20_000)),  # a heading per version, 20,000 of them
    ]
    for text in worst:
        started = time.monotonic()
        changelog.parse(text, "1.0")
        changelog.versions(text)
        assert time.monotonic() - started < 2.5, text[:30]


# ------------------------------------------------------------------ the source


def test_the_file_of_the_language_comes_first_then_the_plain_one(client, fake_source):
    sid = _car(client).sid
    with db.tx() as conn:
        assert sources.fetch_changelog(conn, sid, "plugin", "demo-one", "en") is None  # the source has none
        fake_source["files"]["plugins/demo-one/CHANGELOG.md"] = "english"
        conn.execute("DELETE FROM source_cache")
        assert sources.fetch_changelog(conn, sid, "plugin", "demo-one", "de") == "english"  # no German file: the plain one
        fake_source["files"]["plugins/demo-one/CHANGELOG.de.md"] = "deutsch"
        conn.execute("DELETE FROM source_cache")
        assert sources.fetch_changelog(conn, sid, "plugin", "demo-one", "de") == "deutsch"
        assert sources.fetch_changelog(conn, sid, "plugin", "demo-one", "en") == "english"
        for bad in ("../x", "de/../..", "", "DE", "d"):  # a language is two or three letters: nothing else becomes part of a path
            conn.execute("DELETE FROM source_cache")
            fake_source["seen"].clear()
            assert sources.fetch_changelog(conn, sid, "plugin", "demo-one", bad) == "english"
            assert all("CHANGELOG.md" in url for url in fake_source["seen"]), (bad, fake_source["seen"])
        with pytest.raises(sources.SourceError):
            sources.fetch_changelog(conn, sid, "plugin", "../demo-one", "en")  # an id is a plain id


def test_a_source_that_cannot_be_reached_is_an_error_not_no_changelog(client, fake_source):
    sid = _car(client).sid
    fake_source["files"]["plugins/demo-one/CHANGELOG.md"] = "x"
    fake_source["down"].add("plugins/demo-one/CHANGELOG.md")
    with db.tx() as conn, pytest.raises(sources.SourceError):
        sources.fetch_changelog(conn, sid, "plugin", "demo-one", "en")


# ------------------------------------------------------------------ the route


def test_the_window_gets_the_news_since_the_installed_version_with_every_text_escaped(client, offered):
    r = client.get(f"/v/{offered.vid}/integrations/{offered.pk}/changelog")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html") and "no-store" in r.headers["cache-control"]
    page = r.text
    assert "<strong>new</strong>" in page and "<code>settings</code>" in page and "the guide" in page and "2.0" in page
    assert "The version you have" not in page and "Older news" not in page and "Not released yet" not in page
    assert "<script" not in page and "<b>" not in page and "&lt;script&gt;alert(1)&lt;/script&gt;" in page  # the source's markup is text
    assert "<a " not in page and "href" not in page and "evil.example" not in page  # no link of a source ever gets on the page
    assert "<html" not in page and "<body" not in page  # a piece of a page


def test_no_changelog_says_so(client, fake_source, offered):
    del fake_source["files"]["plugins/demo-one/CHANGELOG.md"]
    _forget_what_was_read()
    page = client.get(f"/v/{offered.vid}/integrations/{offered.pk}/changelog").text
    assert 'data-state="none"' in page and "No changelog available for this package." in page


def test_a_changelog_without_an_entry_for_the_update_says_so(client, fake_source, offered):
    fake_source["files"]["plugins/demo-one/CHANGELOG.md"] = "## 1.9\n- the version you have\n\n## 1.8\n- older\n"
    _forget_what_was_read()
    page = client.get(f"/v/{offered.vid}/integrations/{offered.pk}/changelog").text
    assert 'data-state="nothing"' in page and "The changelog has no entry for this update." in page
    assert "the version you have" not in page


def test_a_source_that_does_not_answer_says_so_and_the_update_stays_possible(client, fake_source, offered):
    fake_source["down"].add("plugins/demo-one/CHANGELOG.md")
    _forget_what_was_read()
    page = client.get(f"/v/{offered.vid}/integrations/{offered.pk}/changelog").text
    assert 'data-state="error"' in page and "could not be loaded right now" in page


def test_the_changelog_is_read_in_the_language_of_the_page(client, fake_source, offered, monkeypatch):
    fake_source["files"]["plugins/demo-one/CHANGELOG.de.md"] = "## 2.0\n- Neue Seite\n"
    _forget_what_was_read()
    monkeypatch.setattr(config, "language", lambda: "de")
    fake_source["seen"].clear()
    page = client.get(f"/v/{offered.vid}/integrations/{offered.pk}/changelog").text
    assert "Neue Seite" in page
    assert fake_source["seen"] and fake_source["seen"][0].endswith("/plugins/demo-one/CHANGELOG.de.md")


def test_the_route_answers_only_for_a_package_that_has_an_update(client, fake_source, offered):
    vid, pk = offered.vid, offered.pk
    assert client.get(f"/v/{vid}/integrations/{pk + 99}/changelog").status_code == 404  # no such package
    client.post(f"/v/{vid}/integrations/{pk}/update")  # now it is current
    fake_source["seen"].clear()
    assert client.get(f"/v/{vid}/integrations/{pk}/changelog").status_code == 404  # nothing to update: ...
    assert not any("CHANGELOG" in url for url in fake_source["seen"])  # ... and nothing is read from the source


def test_a_package_without_a_source_reads_the_changelog_of_the_source_that_offers_the_update(client, offered):
    with db.tx() as conn:
        conn.execute("UPDATE vehicle_addons SET source_id = NULL WHERE id = ?", (offered.pk,))
    page = client.get(f"/v/{offered.vid}/integrations/{offered.pk}/changelog").text
    assert "<strong>new</strong>" in page


def test_only_people_who_may_update_read_it(client, offered, monkeypatch):
    with db.tx() as conn:
        admin = accounts.create_session(conn, accounts.create_user(conn, "owner", "a-long-pass-123", "Owner", True))
        guest = accounts.create_session(conn, accounts.create_user(conn, "guest", "a-long-pass-123", "Guest", False))
    monkeypatch.delenv("CARASSISTANT_DEV", raising=False)  # somebody from outside is not the Home Assistant gateway
    outside = TestClient(web.app, base_url="https://car.example.com", follow_redirects=False, headers={"Origin": "https://car.example.com"})
    url = f"/v/{offered.vid}/integrations/{offered.pk}/changelog"
    assert outside.get(url, cookies={auth_web.COOKIE: guest}).status_code == 403
    assert outside.get(url, cookies={auth_web.COOKIE: admin}).status_code == 200
    assert outside.get(url).status_code in (303, 401, 403)


# ------------------------------------------------------------------ the cards


def test_the_line_and_the_button_open_a_window_that_names_both_versions(client, fake_source, offered):
    fake_source["seen"].clear()
    page = client.get(f"/v/{offered.slug}/plugins").text
    pk, slug = offered.pk, offered.slug
    assert page.count(f'data-open="upd-{pk}"') == 2  # the line "Update available" and the Update button: one window
    assert f'<button type="button" class="addon-status upd" data-open="upd-{pk}"' in page
    assert f'<button type="button" class="primary" data-open="upd-{pk}"' in page
    dialog = _window(page, pk)
    assert "Update Demo One" in dialog and "Installed" in dialog and "v1.9" in dialog and "Available" in dialog and "v2.0" in dialog
    assert "What&#39;s new" in dialog or "What's new" in dialog
    assert f'data-changelog="/v/{slug}/integrations/{pk}/changelog"' in dialog
    assert f'<form method="post" action="/v/{slug}/integrations/{pk}/update">' in dialog  # Update now
    assert (
        "Update now" in dialog and "Cancel" in dialog and dialog.index("Cancel") < dialog.index("Update now")
    )  # Cancel left of the main button
    assert "A new page" not in page and not any(
        "CHANGELOG" in url for url in fake_source["seen"]
    )  # nothing is read before somebody opens the window
    assert f'action="/v/{slug}/integrations/{pk}/update"' not in page.replace(
        dialog, ""
    )  # the card itself no longer updates with one click


def test_the_window_is_in_german_too(client, offered, monkeypatch):
    monkeypatch.setattr(config, "language", lambda: "de")
    dialog = _window(client.get(f"/v/{offered.slug}/plugins").text, offered.pk)
    for word in ("Demo One aktualisieren", "Installiert", "Verfügbar", "Neuigkeiten", "Abbrechen", "Jetzt aktualisieren"):
        assert word in dialog, word


def test_a_package_that_is_current_has_no_window(client, fake_source):
    car = _car(client)
    client.post(f"/sources/{car.sid}/refresh", data={"kind": "plugin"})
    client.post(f"/v/{car.vid}/packages/{car.sid}/plugin/demo-one/install")
    page = client.get(f"/v/{car.slug}/plugins").text
    assert 'id="upd-' not in page and 'data-open="upd-' not in page and "addon-status upd" not in page


def _install_service_package(car, approved):
    """A plugin with a service (nobody ran it: only its description counts) that the source now offers in version 2; returns its id."""
    manifest = {
        "id": "svc-demo",
        "kind": "plugin",
        "name": "Svc Demo",
        "version": "1",
        "service": {"entry": "service/main.py", "routes": []},
    }
    with db.tx() as conn:
        pk = addons.add(conn, car.vid, addons.parse_package(json.dumps(manifest).encode()), car.sid, "0" * 64)
        conn.execute(
            "INSERT INTO source_packages(source_id, kind, pkg_id, name, description, version, icon) VALUES(?,?,?,?,?,?,?)",
            (car.sid, "plugin", "svc-demo", "Svc Demo", "", "2", ""),
        )
        if approved:
            pluginsvc.approve(conn, addons.get(conn, car.vid, pk))
    return pk


def test_a_package_that_waits_for_its_approval_is_reviewed_first_not_updated(client, fake_source):
    """A service nobody approved does not run: the card's main button is *Review*, and the line stays a plain note - the window would update it unseen."""
    car = _car(client)
    _install_service_package(car, approved=False)
    page = client.get(f"/v/{car.slug}/plugins").text
    assert "Update available: v2" in page
    assert '<p class="addon-status upd">' in page and 'id="upd-' not in page and 'data-open="upd-' not in page
    assert "Review" in page


def test_a_package_with_a_service_says_that_its_approval_carries_over(client, fake_source):
    car = _car(client)
    pk = _install_service_package(car, approved=True)
    dialog = _window(client.get(f"/v/{car.slug}/plugins").text, pk)
    assert "runs its own program here" in dialog and "carries over" in dialog


def test_a_package_with_files_says_that_its_approval_carries_over_too(client, fake_source):
    car = _car(client)
    manifest = {
        "id": "files-demo",
        "kind": "plugin",
        "name": "Files Demo",
        "version": "1",
        "files": [{"name": "a.jar", "path": "assets/a.jar", "sha256": "0" * 64, "size": 3}],
    }
    with db.tx() as conn:
        pk = addons.add(conn, car.vid, addons.parse_package(json.dumps(manifest).encode()), car.sid, "0" * 64)
        conn.execute(
            "INSERT INTO source_packages(source_id, kind, pkg_id, name, description, version, icon) VALUES(?,?,?,?,?,?,?)",
            (car.sid, "plugin", "files-demo", "Files Demo", "", "2", ""),
        )
        pluginsvc.approve(conn, addons.get(conn, car.vid, pk))
    dialog = _window(client.get(f"/v/{car.slug}/plugins").text, pk)
    assert "hands out files" in dialog and "carries over" in dialog and "runs its own program" not in dialog


def test_the_integrations_page_has_the_same_window(client, fake_source):
    car = _car(client)
    fake_source["files"]["integrations/index.json"] = json.dumps({"packages": [{"id": "demo-int", "name": "Demo Int", "version": "1"}]})
    fake_source["files"]["integrations/demo-int/plugin.json"] = json.dumps(
        {"id": "demo-int", "kind": "integration", "name": "Demo Int", "version": "1"}
    )
    client.post(f"/sources/{car.sid}/refresh", data={"kind": "integration"})
    client.post(f"/v/{car.vid}/packages/{car.sid}/integration/demo-int/install")
    fake_source["files"]["integrations/index.json"] = json.dumps({"packages": [{"id": "demo-int", "name": "Demo Int", "version": "2"}]})
    fake_source["files"]["integrations/demo-int/CHANGELOG.md"] = "## 2\n- A new integration page\n"
    _forget_what_was_read()
    client.post(f"/sources/{car.sid}/refresh", data={"kind": "integration"})
    page = client.get(f"/v/{car.slug}/integrations").text
    with db.tx() as conn:
        pk = conn.execute("SELECT id FROM vehicle_addons WHERE vehicle_id = ? AND addon_id = 'demo-int'", (car.vid,)).fetchone()["id"]
    assert f'<dialog id="upd-{pk}"' in page and "Update Demo Int" in page
    assert "A new integration page" in client.get(f"/v/{car.vid}/integrations/{pk}/changelog").text


# ------------------------------------------------------------------ the checker of a package


def test_the_checker_names_what_the_update_window_will_lack(tmp_path):
    from check_plugin import changelog_notes

    folder = tmp_path / "my-plugin"
    folder.mkdir()
    assert "No CHANGELOG.md" in changelog_notes(folder, "1.2.0")[0]
    (folder / "CHANGELOG.de.md").write_text("## 1.2.0\n- x\n")
    assert any("plain one" in n for n in changelog_notes(folder, "1.2.0"))  # only a language file: the others see nothing
    (folder / "CHANGELOG.md").write_text("Just some text.\n")
    assert any("no sections per version" in n for n in changelog_notes(folder, "1.2.0"))
    (folder / "CHANGELOG.md").write_text("## 1.1.0\n- x\n")
    assert any("CHANGELOG.md: no section for version 1.2.0" in n for n in changelog_notes(folder, "1.2.0"))
    (folder / "CHANGELOG.md").write_text("## 1.2.0 - 2026-11-27\n- x\n")
    assert changelog_notes(folder, "1.2.0") == []  # both files have a section for the current version
    (folder / "CHANGELOG.fr.md").write_text("## 1.2.0\n- x\n")
    (folder / "CHANGELOG.txt").write_text("not a changelog file of the app")
    assert changelog_notes(folder, "1.2.0") == []
