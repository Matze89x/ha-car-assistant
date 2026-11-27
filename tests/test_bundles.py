"""Pages that belong together are one entry of the More list with a tab for each page (modules.BUNDLES, nav_web.section_tabs)."""

from tests.test_web import create_vehicle, slug

from carassistant import db, modules


def _tabs(client, url):
    """The links of the tab bar a page opens with (its section tabs), or [] when it has none of the bundle kind."""
    import re

    page = client.get(url).text
    if '<nav class="seg-tabs fold' not in page:
        return []
    nav = page.split('<nav class="seg-tabs fold')[1].split("</nav>")[0]
    return re.findall(r'href="([^"]+)" class="(on)?"', nav)


def _all_on(vid):
    with db.tx() as conn:
        for key in ("service", "tasks", "parts", "mods", "docs", "manual", "report"):
            modules.set_vehicle_enabled(conn, vid, key, True)


def test_each_bundle_is_one_line_in_more_and_every_page_of_it_has_the_tabs(client):
    vid = create_vehicle(client, "Bundle Car")
    _all_on(vid)
    base = f"/v/{slug(vid)}"
    more = client.get(f"{base}/more").text
    for title in ("Service &amp; parts", "Documents &amp; manual", "Costs"):
        assert title in more
    for key in ("mods", "parts", "manual"):  # the pages are reached through the entry and its tabs, not one by one
        assert f'href="{base}/e/{key}"' not in more if key != "manual" else f'href="{base}/manual"' not in more
    for url, current in (
        (f"{base}/e/service", "/e/service"),
        (f"{base}/e/parts", "/e/parts"),
        (f"{base}/e/mods", "/e/mods"),
        (f"{base}/e/tasks", "/e/tasks"),
    ):
        tabs = _tabs(client, url)
        assert [href for href, _on in tabs] == [f"{base}/e/service", f"{base}/e/tasks", f"{base}/e/parts", f"{base}/e/mods"]
        assert [href for href, on in tabs if on] == [f"{base}{current}"]  # exactly the open page is marked
    docs = _tabs(client, f"{base}/docs")
    assert [href for href, _on in docs] == [f"{base}/docs", f"{base}/manual"]
    assert (
        len(_tabs(client, f"{base}/invoices")) == 3
        and len(_tabs(client, f"{base}/e/fixed")) == 3
        and len(_tabs(client, f"{base}/report")) == 3
    )


def test_a_switched_off_function_leaves_the_tabs_and_a_single_page_stands_alone(client):
    vid = create_vehicle(client, "Alone Car")
    _all_on(vid)
    base = f"/v/{slug(vid)}"
    with db.tx() as conn:
        modules.set_vehicle_enabled(conn, vid, "parts", False)
        modules.set_vehicle_enabled(conn, vid, "mods", False)
    assert [href for href, _on in _tabs(client, f"{base}/e/service")] == [f"{base}/e/service", f"{base}/e/tasks"]
    with db.tx() as conn:
        modules.set_vehicle_enabled(conn, vid, "tasks", False)
    assert _tabs(client, f"{base}/e/service") == []  # one page left: no tab bar
    more = client.get(f"{base}/more").text
    assert "Service &amp; parts" not in more  # and no bundle entry: the page has its own
    with db.tx() as conn:
        modules.set_vehicle_enabled(conn, vid, "manual", False)
    assert _tabs(client, f"{base}/docs") == []
    with db.tx() as conn:
        modules.set_vehicle_enabled(conn, vid, "report", False)
    assert client.get(f"{base}/invoices").status_code == 404 and client.get(f"{base}/e/fixed").status_code == 404


def test_a_bundle_page_in_the_bar_keeps_its_tabs_and_the_entry_leads_to_a_page_that_is_not_in_the_bar(client):
    vid = create_vehicle(client, "Bar Car")
    _all_on(vid)
    base = f"/v/{slug(vid)}"
    with db.tx() as conn:
        from carassistant import navigation

        navigation.put_in_bar(conn, vid, "parts", True)  # the bar now holds Parts (and, as by default, Service)
        in_bar = {k for k, _i in navigation.slots(conn, vid)}
    assert {"service", "parts"} <= in_bar or "parts" in in_bar
    assert len(_tabs(client, f"{base}/e/parts")) == 4  # the page in the bar shows the tabs all the same
    more = client.get(f"{base}/more").text
    assert 'href="' + base + '/e/tasks"' in more or 'href="' + base + '/e/mods"' in more  # the entry leads to a page that is not in the bar
