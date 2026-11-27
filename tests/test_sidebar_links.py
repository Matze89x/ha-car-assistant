"""The foot of the side bar: the version, then Help (the documentation on GitHub in the language of the app) and GitHub. Plain links that somebody has to
click - the app fetches nothing from there."""

import re

from carassistant import config, links
from conftest import demo_car


def _foot(page_text: str) -> str:
    start = page_text.index('<div class="sb-foot">')
    return page_text[start : page_text.index("</div>", start)]


def _hrefs(foot: str) -> dict[str, str]:
    """``{label: address}`` of the links in the foot."""
    return {label: href for href, label in re.findall(r'<a href="([^"]+)"[^>]*>.*?<span>([^<]+)</span></a>', foot)}


def test_the_foot_links_to_the_english_documentation_and_to_github(client, monkeypatch):
    demo_car(client)
    monkeypatch.setattr(config, "language", lambda: "en")
    foot = _foot(client.get("/about").text)
    got = _hrefs(foot)
    assert got["Help"] == f"{links.PROJECT_URL}/blob/main/docs/README.md"
    assert got["GitHub"] == links.PROJECT_URL
    assert "Documentation on GitHub (English)" in foot


def test_the_foot_links_to_the_german_documentation_in_german(client, monkeypatch):
    demo_car(client)
    monkeypatch.setattr(config, "language", lambda: "de")
    foot = _foot(client.get("/about").text)
    got = _hrefs(foot)
    assert got["Hilfe"] == f"{links.PROJECT_URL}/blob/main/docs/README.de.md"
    assert got["GitHub"] == links.PROJECT_URL
    assert "Dokumentation auf GitHub (Deutsch)" in foot


def test_the_links_open_in_a_new_tab_without_handing_over_the_page(client):
    demo_car(client)
    foot = _foot(client.get("/about").text)
    anchors = re.findall(r"<a [^>]*>", foot)
    assert len(anchors) == 2
    for anchor in anchors:
        assert 'target="_blank"' in anchor and 'rel="noopener noreferrer"' in anchor and "title=" in anchor, anchor


def test_the_version_stays_in_the_foot_and_the_about_page_uses_the_same_help_link(client, monkeypatch):
    demo_car(client)
    monkeypatch.setattr(config, "language", lambda: "de")
    page = client.get("/about").text
    assert re.search(r'<span class="sb-ver">v[\d.]+</span>', _foot(page))
    assert f'href="{links.docs_url("de")}"' in page.split('class="about-links"')[1]
