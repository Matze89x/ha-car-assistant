"""The documentation website (GitHub Pages, built from docs/ with Zensical: docs-site/build_site.py, mkdocs.yml - docs/maintaining.md): the menu lists every
page, the German menu has a name for every entry, every link either goes to a page of the site or is a full address, the Markdown reads the same in the site's
reader as on GitHub, the script makes an English and a German project out of the pages, and the workflow publishes it. None of this needs Zensical: the site
itself is built (strictly) by .github/workflows/docs.yml."""

import importlib.util
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPO = "https://github.com/Matze89x/ha-car-assistant"
LINK = re.compile(r"\]\(([^)\s]+)\)")
LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+\S")
PICTURES = (".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif")


class _Loader(yaml.SafeLoader):
    """mkdocs.yml names a Python function in two places (``!!python/name``): here it is just read over."""


_Loader.add_multi_constructor("tag:yaml.org,2002:python/", lambda loader, suffix, node: None)


def _config() -> dict:
    return yaml.load((ROOT / "mkdocs.yml").read_text(encoding="utf-8"), Loader=_Loader)


def _nav_items(nav):
    """``(title, file)`` of every entry of the menu (a group has no file)."""
    for entry in nav:
        for title, value in entry.items():
            if isinstance(value, list):
                yield title, None
                yield from _nav_items(value)
            else:
                yield title, value


def _german_names() -> dict:
    for plugin in _config()["plugins"]:
        if isinstance(plugin, dict) and "i18n" in plugin:
            return next(lang for lang in plugin["i18n"]["languages"] if lang["locale"] == "de")["nav_translations"]
    raise AssertionError("mkdocs.yml has no i18n plugin")


def _outside_code(text: str):
    """``(number, line)`` of the lines that are not inside a fenced code block."""
    fence = False
    for number, line in enumerate(text.split("\n")):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if not fence:
            yield number, line


def test_the_menu_lists_every_page_once():
    pages = {p.name for p in DOCS.glob("*.md") if not p.name.endswith(".de.md")} | {"examples/README.md"}
    files = [f for _, f in _nav_items(_config()["nav"]) if f]
    assert sorted(files) == sorted(pages), (set(pages) - set(files), set(files) - set(pages))
    for name in files:
        assert (DOCS / name).is_file() and (DOCS / name.replace(".md", ".de.md")).is_file(), name


def test_the_german_menu_has_a_name_for_every_entry():
    titles = {title for title, _ in _nav_items(_config()["nav"])}
    german = _german_names()
    assert titles <= set(german), titles - set(german)
    assert all(str(german[t]).strip() for t in titles)


def test_the_site_and_the_app_name_the_same_address():
    from carassistant import links

    assert _config()["site_url"] == links.SITE_URL
    assert links.SITE_URL.startswith("https://matze89x.github.io/")
    assert (DOCS / "assets" / "logo.svg").is_file() and (
        DOCS / "stylesheets" / "site.css"
    ).is_file()  # what the theme section of mkdocs.yml names


def test_a_link_goes_to_a_page_of_the_site_or_is_a_full_address():
    """The site holds the pages and their pictures: a link to a source file, a folder or an example package is a full GitHub address (it would be dead on
    the site), and every full address into this repository names something that exists."""
    for page in sorted(DOCS.rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        for link in LINK.findall(text):
            if link.startswith(("#", "mailto:")):
                continue
            where = (str(page.relative_to(ROOT)), link)
            if link.startswith("http"):
                match = re.match(rf"{re.escape(REPO)}/(?:blob|tree)/main/([^#?]+)", link)
                if match:
                    assert (ROOT / match.group(1)).exists(), where
                continue
            target = (page.parent / link.split("#")[0]).resolve()
            relative = target.relative_to(DOCS)  # a link that leaves docs/ is a full address
            example_package = relative.parts[0] == "examples" and not (len(relative.parts) == 2 and relative.suffix == ".md")
            assert target.is_file() and not example_package and target.suffix in (".md", *PICTURES), where


def test_the_markdown_reads_the_same_on_github_and_on_the_site():
    """The reader of the site (Python-Markdown) is stricter than GitHub's: a list needs a blank line before it and four spaces for a list in a list."""
    for page in sorted(DOCS.rglob("*.md")):
        lines = page.read_text(encoding="utf-8").split("\n")
        for number, line in _outside_code("\n".join(lines)):
            match = LIST.match(line)
            if not match or not number:
                continue
            before = lines[number - 1]
            where = f"{page.relative_to(ROOT)}:{number + 1}"
            if not match.group(1):
                assert not before.strip() or LIST.match(before) or before.startswith((" ", "\t", "#", "|", ">", "<", "---")), (
                    f"{where}: a blank line before the list"
                )
            if len(match.group(1)) == 2:
                assert not LIST.match(before), f"{where}: a list in a list is indented by four spaces"


def _script():
    spec = importlib.util.spec_from_file_location("docs_site_build", ROOT / "docs-site" / "build_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_language_line_and_the_repository_lines_stay_off_the_site():
    tidy = _script().tidy
    english = "# Guide\n\n🇬🇧 English · [🇩🇪 Deutsch](guide.de.md)\n\nText\n"
    assert tidy(english, "en") == "# Guide\n\nText\n"
    german = "# Handbuch\n\n[🇬🇧 English](guide.md) · 🇩🇪 Deutsch\n\nText\n"
    assert tidy(german, "de") == "# Handbuch\n\nText\n"
    only_german = (
        "# Mitmachen\n\n[🇬🇧 English](https://example.org/CONTRIBUTING.md) · 🇩🇪 Deutsch\n"  # the English file is on GitHub: the line stays
    )
    assert tidy(only_german, "de") == only_german
    marked = "Intro\n\n<!-- repo-only:start -->\nAlso as a website.\n<!-- repo-only:end -->\n\nMore\n"
    assert tidy(marked, "en") == "Intro\n\nMore\n"
    # in the German project the files lose their .de: the links between German pages follow (a full address is left alone)
    assert tidy('Siehe [Anleitung](guide.de.md#start) und [Plugins](plugins.de.md) und <a href="api.de.md">API</a>.', "de") == (
        'Siehe [Anleitung](guide.md#start) und [Plugins](plugins.md) und <a href="api.md">API</a>.'
    )
    assert tidy("[Guide](guide.md)", "en") == "[Guide](guide.md)"


def test_the_script_makes_an_english_and_a_german_project_out_of_the_pages(tmp_path):
    script = _script()
    config = script.read_config()
    base = "https://matze89x.github.io/ha-car-assistant/"
    english = script.prepare("en", tmp_path, base, config)
    german = script.prepare("de", tmp_path, base, config)
    pages = {p.name for p in DOCS.glob("*.md") if not p.name.endswith(".de.md")}
    assert {p.name for p in (english / "docs").glob("*.md")} == pages
    assert {p.name for p in (german / "docs").glob("*.md")} == pages  # the same names: page.de.md became page.md
    assert not list((english / "docs").rglob("*.de.md")) and not list((german / "docs").rglob("*.de.md"))
    for page in (german / "docs").rglob(
        "*.md"
    ):  # no link to a file that does not exist (the text of a link, or a file name in the prose, may still say .de.md)
        targets = re.findall(r"\]\((?!https?:)([^)\s]*)", page.read_text(encoding="utf-8")) + re.findall(
            r'href="(?!https?:)([^"]*)"', page.read_text(encoding="utf-8")
        )
        assert not [t for t in targets if t.split("#")[0].endswith(".de.md")], page.name
    for folder in (english, german):
        assert (folder / "docs" / "stylesheets" / "site.css").is_file() and (folder / "docs" / "assets" / "logo.svg").is_file()
        assert (folder / "docs" / "screenshots").is_dir() and (folder / "docs" / "examples" / "README.md").is_file()
        assert not [
            p for p in (folder / "docs" / "examples").rglob("*") if p.is_file() and p.name != "README.md"
        ]  # the example packages are code
    for lang, folder in (("en", english), ("de", german)):
        project = yaml.safe_load((folder / "mkdocs.yml").read_text(encoding="utf-8"))
        assert project["theme"]["language"] == lang and project["theme"]["variant"] == "classic"
        assert project["use_directory_urls"] is False and project["plugins"] == ["search"]
        assert project["site_url"] == base + ("de/" if lang == "de" else "")
        assert [a["link"] for a in project["extra"]["alternate"]] == [base, base + "de/"]
        assert "hooks" not in project
        toc = next(e["toc"] for e in project["markdown_extensions"] if isinstance(e, dict) and "toc" in e)
        assert toc["slugify"] == {"object": "pymdownx.slugs.slugify", "kwds": {"case": "lower"}}  # the anchors of GitHub: the umlauts stay
    english_menu = yaml.safe_load((english / "mkdocs.yml").read_text(encoding="utf-8"))["nav"]
    german_menu = yaml.safe_load((german / "mkdocs.yml").read_text(encoding="utf-8"))["nav"]
    assert next(iter(english_menu[1])) == "Use it" and next(iter(german_menu[1])) == "Benutzen"  # the menu has the German names
    assert [f for _, f in _nav_items(german_menu) if f] == [f for _, f in _nav_items(english_menu) if f]  # ... for the same pages


def test_the_language_selector_names_the_same_page_in_the_other_language(tmp_path):
    script = _script()
    (tmp_path / "de" / "examples").mkdir(parents=True)
    (tmp_path / "examples").mkdir()
    selector = '<a href="BASE" hreflang="en" class="md-select__link"><a href="BASE" hreflang="de" class="md-select__link"><link rel="alternate" href="BASE" hreflang="de">'
    for name in (
        "guide.html",
        "de/guide.html",
        "examples/index.html",
        "de/examples/index.html",
        "only-english.html",
        "de/only-german.html",
        "404.html",
    ):
        (tmp_path / name).write_text(selector, encoding="utf-8")
    script.point_the_selector(tmp_path, "https://example.org/docs/")

    def links(name):
        return re.findall(r'href="([^"]*)" hreflang="(en|de)"', (tmp_path / name).read_text(encoding="utf-8"))

    assert links("guide.html") == [("guide.html", "en"), ("de/guide.html", "de"), ("https://example.org/docs/de/guide.html", "de")]
    assert links("de/guide.html")[:2] == [("../guide.html", "en"), ("../de/guide.html", "de")]
    assert links("examples/index.html")[:2] == [("../examples/index.html", "en"), ("../de/examples/index.html", "de")]
    assert links("de/examples/index.html")[:2] == [("../../examples/index.html", "en"), ("../../de/examples/index.html", "de")]
    assert links("only-english.html")[1] == ("de/", "de")  # no German page of that name: the start page of the other language
    assert links("de/only-german.html")[0] == ("../", "en")
    assert links("404.html") == [("BASE", "en"), ("BASE", "de"), ("BASE", "de")]  # shown at any address: left alone


def test_zensical_builds_both_languages_strictly_when_it_is_installed(tmp_path):
    pytest.importorskip("zensical")
    out = _script().make_site(tmp_path / "site", True, "https://matze89x.github.io/ha-car-assistant/")
    for name in ("index.html", "guide.html", "de/index.html", "de/guide.html", "examples/index.html", "de/examples/index.html"):
        assert (out / name).is_file(), name
    assert 'hreflang="de" class="md-select__link"' in (out / "guide.html").read_text(encoding="utf-8")


def test_the_workflow_publishes_the_site_and_the_tools_are_pinned():
    workflow = (ROOT / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")
    assert "python docs-site/build_site.py --strict" in workflow and "actions/deploy-pages@" in workflow and "pages: write" in workflow
    assert "if: github.event_name != 'pull_request'" in workflow  # a pull request builds, only main publishes
    for line in (ROOT / "docs-site" / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            assert re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", line.strip()), f"{line}: an exact version"


def test_the_start_pages_link_the_website():
    from carassistant import links

    for name in ("README.md", "README.de.md", "docs/README.md", "docs/README.de.md", "carassistant/DOCS.md", "carassistant/DOCS.de.md"):
        assert links.SITE_URL in (ROOT / name).read_text(encoding="utf-8"), name
