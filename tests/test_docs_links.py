"""The add-on page of Home Assistant cannot follow relative links or show images: every link there must be a full address, and
every picture of the screenshot pages must exist."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _links(text: str) -> list[str]:
    return re.findall(r"\]\(([^)\s]+)\)", text)


def test_the_addon_pages_use_full_addresses_only():
    for name in (
        "DOCS.md",
        "DOCS.de.md",
        "README.md",
        "CHANGELOG.md",
        "CHANGELOG.de.md",
    ):  # Home Assistant shows these without the repository: only full addresses work
        text = (ROOT / "carassistant" / name).read_text(encoding="utf-8")
        for link in _links(text):
            assert link.startswith(("https://", "#")) or (link in ("DOCS.md", "DOCS.de.md") and name.startswith("DOCS")), (name, link)
        assert "![" not in text, name  # no pictures on the add-on page
        for url in re.findall(r"https://github\.com/Matze89x/ha-car-assistant/blob/main/([^\s)]+)", text):
            assert (ROOT / url).exists(), (name, url)


def test_the_screenshot_pages_point_to_existing_pictures():
    for page in ("screenshots.md", "screenshots.de.md"):
        text = (ROOT / "docs" / page).read_text(encoding="utf-8")
        pictures = re.findall(r'(?:\]\(|src=")(screenshots/[^)"\s]+\.png)', text)
        assert len(pictures) >= 8
        for pic in pictures:
            assert (ROOT / "docs" / pic).is_file(), (page, pic)


def test_the_start_pages_show_pictures_of_their_own_language_and_every_link_leads_somewhere():
    """The first page on GitHub: the banner and three phone pictures - from the folder of its own language (no English picture on the German page) - each with
    a description for screen readers, and every link to a file of the repository finds its file."""
    for readme, lang in (("README.md", "en"), ("README.de.md", "de")):
        text = (ROOT / readme).read_text(encoding="utf-8")
        pictures = re.findall(r'(?:\]\(|src=")(docs/[^)"\s]+\.png)', text)
        assert len(pictures) >= 4, readme
        for pic in pictures:
            assert (ROOT / pic).is_file(), (readme, pic)
            if pic.startswith("docs/screenshots/"):
                assert pic.startswith(f"docs/screenshots/{lang}/"), (readme, pic)
        assert not re.findall(r"<img(?![^>]*\balt=\"[^\"]+\")", text), f"{readme}: a picture without a description"
        for link in re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r'href="([^"]+)"', text):
            if not link.startswith(("https://", "http://", "#", "mailto:")):
                assert (ROOT / link.split("#")[0]).exists(), (readme, link)


def test_relative_links_in_the_docs_point_to_existing_files():
    for page in sorted((ROOT / "docs").rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        for link in _links(text):
            if link.startswith(("https://", "http://", "#", "mailto:")):
                continue
            target = (page.parent / link.split("#")[0]).resolve()
            assert target.exists(), (str(page.relative_to(ROOT)), link)


def test_the_example_packages_are_readable_by_the_app():
    import json

    from carassistant import addons

    for manifest in (ROOT / "docs" / "examples").glob("*/plugin.json"):
        addons.parse_package(manifest.read_bytes())
        assert json.loads(manifest.read_text(encoding="utf-8"))["id"]


def test_every_doc_page_exists_in_both_languages_and_is_linked_from_the_start_page():
    docs = ROOT / "docs"
    english = {p.name for p in docs.glob("*.md") if not p.name.endswith(".de.md")}
    for name in english:
        assert (docs / name.replace(".md", ".de.md")).exists(), f"{name} has no German page"
    start = {"README.md": "", "README.de.md": ".de"}
    for readme, suffix in start.items():
        text = (ROOT / readme).read_text(encoding="utf-8")
        for name in english:
            page = name[:-3]
            if page == "README":
                continue
            assert f"docs/{page}{suffix}.md" in text, f"{readme} does not link docs/{page}{suffix}.md"


def test_the_docs_index_lists_every_page_in_both_languages():
    """docs/README.md is the start page of the documentation website (the Help link of the app opens it, links.docs_url) and the one GitHub shows under the
    file list of docs/: a page that is not in it cannot be found. The start page lists the same pages (test above), so the two cannot drift apart."""
    docs = ROOT / "docs"
    for readme, suffix in (("README.md", ""), ("README.de.md", ".de")):
        text = (docs / readme).read_text(encoding="utf-8")
        for page in sorted(p.name for p in docs.glob("*.md") if not p.name.endswith(".de.md") and p.name != "README.md"):
            assert f"({page[:-3]}{suffix}.md)" in text, f"docs/{readme} does not link {page[:-3]}{suffix}.md"


def test_the_help_link_opens_the_documentation_website_in_the_language_of_the_app():
    from carassistant import links

    assert links.docs_url("de") == f"{links.SITE_URL}de/"
    for lang in ("en", "fr", "es"):  # a language without pages of its own reads the English ones
        assert links.docs_url(lang) == links.SITE_URL
    assert links.docs_url("de", "guide") == f"{links.SITE_URL}de/guide.html"
    assert links.docs_url("en", "guide") == f"{links.SITE_URL}guide.html"
    for lang, suffix in (("en", ""), ("de", ".de")):  # the pages the site is built from exist
        assert (ROOT / "docs" / f"README{suffix}.md").is_file(), lang


def test_the_notice_names_every_library_the_add_on_installs():
    notice = (ROOT / "NOTICE.md").read_text(encoding="utf-8").lower()
    for line in (ROOT / "carassistant" / "requirements.txt").read_text().splitlines():
        name = re.split(r"[=<>!~ ]", line.strip(), maxsplit=1)[0].lower()
        if name:
            assert name in notice, f"NOTICE.md does not name {name}"
