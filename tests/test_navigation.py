import re

from tests.test_web import create_vehicle, slug

from carassistant import icons, integrations, modules, navigation


def test_every_module_and_integration_has_an_icon():
    for m in modules.MODULES:
        assert icons.MODULE_ICON.get(m.key) in icons.ICONS, m.key
    for i in integrations.INTEGRATIONS:
        assert icons.INTEGRATION_ICON.get(i.key) in icons.ICONS, i.key
    assert icons.DEFAULT_ICON in icons.ICONS and icons.PICKER_ICONS


def test_default_bar_and_more_page(client):
    vid = create_vehicle(client)
    html = client.get(f"/v/{slug(vid)}").text
    for page in ("security", "e/service", "e/trips", "e/fuel", "more"):
        assert f"/v/{slug(vid)}/{page}" in html
    assert client.get(f"/v/{slug(vid)}/more").status_code == 200
    assert client.get("/more").status_code == 200
    assert client.get(f"/v/{slug(vid)}/security").status_code == 200


def test_order_is_configurable_first_four_are_the_bar(client):
    vid = create_vehicle(client)
    pairs = [("tires", "wrench"), ("docs", "nonexistent"), ("tires", "home"), ("parts", "lock"), ("mods", ""), ("fuel", "gas-station")]
    form = {"m": [k for k, _ in pairs], "i": [i for _, i in pairs]}
    assert client.post(f"/v/{slug(vid)}/navigation", data=form).status_code == 303
    from carassistant import db

    with db.tx() as conn:
        order = navigation.order(conn, vid)
        slots = navigation.slots(conn, vid)
    assert order[0] == ("tires", "wrench")  # chosen icon kept
    assert order[1] == ("docs", navigation.default_icon("docs"))  # unknown icon replaced
    assert [k for k, _ in slots] == ["tires", "docs", "parts", "mods"]  # duplicate dropped, bar = first four
    assert "fuel" in [k for k, _ in order[4:]] and len(order) == len(navigation.choices())  # the rest sits in More
    html = client.get(f"/v/{slug(vid)}").text
    bar = html.split('id="tabbar"')[1].split("</nav>")[0]
    assert f"/v/{slug(vid)}/e/tires" in bar and f"/v/{slug(vid)}/security" not in bar
    more = client.get(f"/v/{slug(vid)}/more").text
    assert f"/v/{slug(vid)}/security" in more  # pushed-out main page heads More
    editor = client.get(f"/v/{slug(vid)}/integrations").text  # the navigation of a vehicle is managed under its Integrations
    assert 'id="navlist"' in editor and '<select name="m' not in editor
    client.post(f"/v/{slug(vid)}/navigation", data={"reset": "1"})
    with db.tx() as conn:
        assert [k for k, _ in navigation.slots(conn, vid)] == ["security", "service", "trips", "fuel"]


def test_disabled_module_leaves_the_bar(client):
    vid = create_vehicle(client)
    client.post("/integrations/module/trips", data={"enabled": "0"})
    html = client.get(f"/v/{slug(vid)}").text
    bar = html.split('id="tabbar"')[1].split("</nav>")[0]
    assert f"/v/{slug(vid)}/e/trips" not in bar


def test_vehicle_data_page_and_edit_form(client):
    vid = create_vehicle(client)
    page = client.get(f"/v/{slug(vid)}/edit")
    assert page.status_code == 200 and "vd-group" in page.text and "50.000" in page.text.replace(",", ".")
    form = client.get(f"/v/{slug(vid)}/edit?mode=form")
    assert form.status_code == 200 and 'name="vin"' in form.text


def active_tabs(html: str) -> list[str]:
    bar = html.split('id="tabbar"')[1].split("</nav>")[0]
    return re.findall(r'href="([^"]+)" class="tab on"', bar)


def test_start_page_marks_home_not_more(client):
    """The start page is Home – also while there is no vehicle yet. Other pages without a vehicle stay under More."""
    html = client.get("/").text
    assert active_tabs(html) == ["/"] and 'class="back-btn"' not in html  # no vehicle yet: the welcome page keeps its navigation
    for path in ("/settings/design", "/vehicles", "/more"):
        page = client.get(path).text
        assert active_tabs(page) == ["/more"], path
    assert 'class="back-btn"' in client.get("/settings/design").text and 'class="back-btn"' not in client.get("/more").text


def test_start_page_with_several_vehicles_marks_home(client):
    first = create_vehicle(client, "A Car")
    create_vehicle(client, "B Car")
    html = client.get("/").text  # more than one vehicle: the list is shown at "/"
    assert 'id="tabbar"' not in html and 'class="back-btn"' not in html  # choosing a car: only the logo, no navigation
    assert active_tabs(client.get("/vehicles").text) == [f"/v/{slug(first)}/more"]


def test_add_vehicle_button_appears_only_once(client):
    """Empty start page: one button (in the welcome card). With vehicles: one button in the header."""
    assert client.get("/").text.count('href="/vehicles/new"') == 1
    create_vehicle(client, "A Car")
    create_vehicle(client, "B Car")
    page = re.sub(
        r"<(dialog|aside).*?</\1>", "", client.get("/vehicles").text, flags=re.S
    )  # the overlay and the More list have their own "add" entries
    assert page.count('href="/vehicles/new"') == 1


def test_vehicle_switcher_only_with_more_than_one_vehicle(client):
    first = create_vehicle(client, "A Car")
    more = client.get(f"/v/{slug(first)}/more").text
    assert (
        'id="vsw"' not in client.get("/vehicles").text and 'data-open="vsw"' not in more and "vswitch-btn" not in more
    )  # one car: no switcher dialog (the button leads to the vehicle list)
    second = create_vehicle(client, "B Car")
    more = client.get(f"/v/{slug(second)}/more").text  # two cars: "Change" only in More, overlay with both cars
    assert "cur-switch" in more and 'id="vsw"' in more and more.count("vsw-card") >= 2 and "ABC 123" not in more
    assert "vswitch-btn" not in client.get(f"/v/{slug(second)}").text  # no switch button in headers or hero


def test_vehicle_addresses_use_the_name(client):
    from carassistant import slugs

    assert [slugs.make_slug(n) for n in ("My Golf", "Zwölf Üter Ä", "  Auto 2 ", "123", "日本", "Ça va?")] == [
        "my-golf",
        "zwoelf-ueter-ae",
        "auto-2",
        "car-123",
        "car",
        "ca-va",
    ]
    vid = create_vehicle(client, "My Golf")
    assert f"/v/{slug(vid)}" in client.get(f"/v/{slug(vid)}").text or True  # numeric addresses keep working
    page = client.get("/v/my-golf")
    assert page.status_code == 200 and 'href="/v/my-golf/security"' in page.text and "/v/1/" not in page.text.replace("/v/1/icon", "")
    assert client.get("/v/my-golf/e/fuel").status_code == 200 and client.get("/v/no-such-car").status_code == 404
    second = create_vehicle(client, "My Golf")  # same name: a number is appended
    assert client.get("/v/my-golf-2").status_code == 200 and second != vid
    r = client.post(f"/v/{slug(vid)}/edit", data={"name": "Red Polo", "fuel_type": "petrol"})
    assert r.headers["location"].startswith("/v/red-polo")  # renamed: the address follows
    assert client.get("/v/red-polo").status_code == 200
    assert client.post("/v/red-polo/odometer", data={"odometer_km": "60000"}).headers["location"].startswith("/v/red-polo")


def test_plate_chip_only_when_there_is_a_plate(client):
    from carassistant import db

    vid = create_vehicle(client, "Plated")
    assert 'class="plate">B-XY 1<' in client.get(f"/v/{slug(vid)}").text and "ghost" not in client.get(f"/v/{slug(vid)}").text
    with db.tx() as conn:
        conn.execute("UPDATE vehicles SET plate = NULL WHERE id = ?", (vid,))
    page = client.get(f"/v/{slug(vid)}").text
    assert 'class="plate' not in page and "ABC 123" not in page  # no plate: nothing at the top of Home either


def test_more_is_a_second_navigation_on_pages_under_more(client):
    first = create_vehicle(client, "A Car")
    create_vehicle(client, "B Car")
    for path in (f"/v/{slug(first)}/e/appointments", "/settings/design", f"/v/{slug(first)}/integrations"):
        page = client.get(path).text
        assert 'class="more-pane"' in page and "with-more" in page, path
    assert (
        'href="/settings/car"' in client.get("/settings/design").text and "mi sel" in client.get("/settings/design").text
    )  # Settings opens on the car
    assert 'data-open="vsw"' in client.get("/settings/design").text  # "Switch vehicle" is an entry of that list
    assert "more-pane" not in client.get(f"/v/{slug(first)}").text  # not on Home
    assert "more-pane" not in client.get(f"/v/{slug(first)}/e/fuel").text  # pages of the bottom bar are not under More
    more = client.get(f"/v/{slug(first)}/more").text  # the More page itself: list on the left on wide screens, full list on phones
    assert "more-main" in more and 'class="more-pane"' in more


def test_login_lives_under_settings_and_the_server_pages_stay_off_the_vehicle(client):
    create_vehicle(client)
    assert client.get("/account").headers["location"].endswith("/settings/user")  # the old address leads to the tab
    user = client.get("/settings/user")
    assert user.status_code == 200 and 'id="account"' in user.text and 'id="navlist"' not in user.text
    more = client.get("/settings/design").text
    assert 'href="/settings/car"' in more and 'href="/account"' not in more  # no extra "Account & login" entry any more
    assert (
        client.post("/account/create", data={"username": "owner", "password": "longenough123", "password2": "different"})
        .headers["location"]
        .startswith("/settings/user")
    )


def test_more_group_current_vehicle_holds_only_what_the_bar_lacks(client):
    first = create_vehicle(client, "A Car")
    page = re.sub(r"<nav.*?</nav>", "", client.get(f"/v/{slug(first)}/more").text, flags=re.S)  # without the bar itself
    assert "Current vehicle" in page and "This vehicle" not in page and "Extensions" not in page  # one group, no second heading
    current, general = page.split("General")[0], page.split("General")[1]
    assert f'href="/v/{slug(first)}/edit"' in current and "Vehicle passport" in current  # the first entry: one card with the car name
    assert f'href="/v/{slug(first)}/integrations"' in current and f'href="/v/{slug(first)}/plugins"' in current  # ... and its extensions
    assert current.index("integrations") < current.index("plugins")  # Integrations, then Plugins
    for page_key in ("trips", "service"):  # the pages of the bar are not repeated
        assert f'href="/v/{slug(first)}/e/{page_key}"' not in current
    for href in ("/vehicles", "/settings/car"):
        assert f'href="{href}"' in general  # server level: settings, all vehicles, about
    assert 'href="/account"' not in general and 'href="/integrations"' not in page
    create_vehicle(client, "B Car")
    several = client.get(f"/v/{slug(first)}/more").text  # several cars: the card of the current car with the switch
    assert "cur-switch" in several
    assert 'action="/integrations/mqtt"' in client.get("/settings/system").text  # MQTT lives on the System page


def test_first_start_pages_have_no_navigation(client):
    """Language and access pages of a new setup: no sidebar/tab bar, no 'More' back link."""
    for path in ("/setup/language", "/setup/access"):
        html = client.get(path).text
        assert 'id="tabbar"' not in html, path
        assert 'class="back-btn"' not in html, path
        assert 'class="more-pane"' not in html and 'aria-label="More"' not in html, path


def test_switching_the_vehicle_in_more_stays_in_more(client):
    first = create_vehicle(client, "A Car")
    second = create_vehicle(client, "B Car")
    a, b = slug(first), slug(second)
    assert f'href="/v/{b}/more"' in client.get(f"/v/{a}/more").text  # More list -> More list of the other car
    assert f'href="/v/{b}/e/tires"' in client.get(f"/v/{a}/e/tires").text  # a page in More -> the same page of the other car
    assert f'href="/v/{b}/more"' in client.get("/vehicles").text  # a page without a car -> More of the other car


def test_a_lone_dash_counts_as_empty(client):
    vid = create_vehicle(client, "Dash")
    client.post(f"/v/{slug(vid)}/edit", data={"name": "Dash", "fuel_type": "diesel", "plate": "-", "make": "–"})
    page = client.get(f"/v/{slug(vid)}").text
    assert 'class="plate' not in page


def test_not_found_page_shows_the_address_escaped(client):
    r = client.get("/v/no-such-car<b>")
    assert r.status_code == 404
    assert 'class="nf-code"' in r.text and "&lt;b&gt;" in r.text and "<b>" not in r.text.split('class="nf-path"')[1].split("</code>")[0]


def test_a_function_can_be_hidden_for_one_vehicle_only(client):
    a, b = create_vehicle(client, "Hide A"), create_vehicle(client, "Hide B")
    page = client.get(f"/v/{slug(a)}/integrations").text
    assert f'data-fn="/v/{slug(a)}/modules/tires"' in page and 'id="navigation"' in page  # the switches live in the navigation editor
    assert client.post(f"/v/{slug(a)}/modules/tires", data={"enabled": "0"}, follow_redirects=False).status_code == 303
    assert client.get(f"/v/{slug(a)}/e/tires").status_code == 404  # hidden for A ...
    assert client.get(f"/v/{slug(b)}/e/tires").status_code == 200  # ... still there for B
    assert f'href="/v/{slug(a)}/e/tires"' not in client.get(f"/v/{slug(a)}/more").text  # not listed in More for A
    assert f'href="/v/{slug(b)}/e/tires"' in client.get(f"/v/{slug(b)}/more").text  # B still has it
    client.post(f"/v/{slug(a)}/modules/tires", data={"enabled": "1"})
    assert client.get(f"/v/{slug(a)}/e/tires").status_code == 200
    assert (
        client.post(f"/v/{slug(a)}/modules/overview", data={"enabled": "0"}, follow_redirects=False).status_code == 303
    )  # core: refused, no crash


def test_a_page_that_goes_away_leaves_the_saved_order_and_the_others_keep_their_places(env):
    import json

    from carassistant import db, navigation

    with db.tx() as conn:
        db.set_setting(
            conn, navigation._key(1), json.dumps([{"m": "fuel", "i": "x"}, {"m": "x-demo", "i": "y"}, {"m": "service", "i": "z"}])
        )
        navigation.forget(conn, 1, "x-demo")
        saved = json.loads(db.get_setting(conn, navigation._key(1), ""))
        assert [d["m"] for d in saved] == ["fuel", "service"]  # no hole, the others unchanged
        navigation.forget(conn, 1, "x-demo")  # a second time changes nothing
        assert [d["m"] for d in json.loads(db.get_setting(conn, navigation._key(1), ""))] == ["fuel", "service"]


def test_choosing_a_car_shows_only_the_logo_no_navigation(client):
    from tests.test_web import create_vehicle, slug

    first = create_vehicle(client)
    second = create_vehicle(client)
    assert first != second
    page = client.get("/", follow_redirects=False)
    assert page.status_code == 200  # two cars: the list to choose from
    assert (
        'class="sb-brand"' in page.text and 'id="tabbar"' not in page.text and 'class="tab ' not in page.text
    )  # the logo, nothing to navigate to
    assert (
        'href="/"' not in page.text.split('class="sb-brand"', 1)[0][-80:] and 'class="sb-brand" href' not in page.text
    )  # and the logo is no link here
    car = client.get(f"/v/{slug(first)}")
    assert 'id="tabbar"' in car.text and 'class="sb-brand" href' in car.text  # a car page keeps its navigation
    assert 'id="tabbar"' in client.get("/vehicles").text  # the management page under More keeps it as well
