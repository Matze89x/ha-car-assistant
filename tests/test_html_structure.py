"""Every page is well nested: no closing tag without its opening tag, no box closed by a stray ``</div>``.

A stray ``</div>`` once closed a column of Settings -> System too early, so every card after it fell out of its column into a grid of rows and left a big hole
beside them. The page still "worked", which is why nobody saw it in the markup - so every page the demo car reaches by its links is parsed here."""

import re
from html.parser import HTMLParser

from tests.conftest import demo_car
from tests.test_web import slug

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
    "path", "circle", "rect", "line", "polyline", "polygon", "use", "stop", "ellipse",
}  # fmt: skip
OPTIONAL = {
    "p",
    "li",
    "dt",
    "dd",
    "option",
    "optgroup",
    "tr",
    "td",
    "th",
    "thead",
    "tbody",
    "tfoot",
    "colgroup",
    "caption",
    "rt",
    "rp",
}  # may be left open


class Nesting(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, int]] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                skipped = [t for t, _line in self.stack[i + 1 :] if t not in OPTIONAL]
                if skipped:
                    self.problems.append(f"line {self.getpos()[0]}: </{tag}> closes {skipped} that are still open")
                del self.stack[i:]
                return
        self.problems.append(f"line {self.getpos()[0]}: </{tag}> without an opening tag")


def check(html: str) -> list[str]:
    parser = Nesting()
    parser.feed(html)
    return parser.problems


def test_the_checker_finds_a_stray_div():
    assert check("<div><section><p>a</p></div></section>") == [
        "line 1: </div> closes ['section'] that are still open",
        "line 1: </section> without an opening tag",
    ]
    assert check("<div><ul><li>a<li>b</ul></div>") == []


def test_every_page_of_the_demo_car_is_well_nested(client):
    vid = demo_car(client)
    start = [
        f"/v/{slug(vid)}",
        f"/v/{slug(vid)}/more",
        "/vehicles",
        "/about",
        "/settings/user",
        "/settings/system",
        f"/settings/car?car={slug(vid)}",
    ]
    seen: set[str] = set()
    queue = list(start)
    bad: dict[str, list[str]] = {}
    skip = (
        "logout",
        "delete",
        "export",
        "/api/",
        "/static",
        "/icon",
        "manifest",
        "download",
        "backup",
        "/docs/",
        "/media/",
        "/photo",
        "/video",
        ".ics",
    )
    while queue and len(seen) < 150:
        url = queue.pop(0)
        if url in seen or any(s in url for s in skip):
            continue
        seen.add(url)
        r = client.get(url)
        if "text/html" not in r.headers.get("content-type", ""):
            continue
        problems = check(r.text)
        if problems:
            bad[url] = problems[:3]
        for href in re.findall(r'href="(/[^"#]*)"', r.text):
            if href not in seen and href.startswith(("/v/", "/settings", "/vehicles", "/about")):
                queue.append(href)
    assert len(seen) > 40  # it really walked the app
    assert not bad, "\n".join(f"{url}: {p}" for url, p in bad.items())
