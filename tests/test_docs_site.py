"""The documentation website (GitHub Pages, built from docs/ with mkdocs.yml - docs/maintaining.md): the menu lists every page, the German menu has a name for
every entry, every link either goes to a page of the site or is a full address, the Markdown reads the same in the site's reader as on GitHub, and the
workflow publishes it. None of this needs MkDocs: the site itself is built (strictly) by .github/workflows/docs.yml."""

import importlib.util
import re
from pathlib import Path

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


def test_the_hooks_take_the_language_line_and_the_repository_lines_off_the_site():
    spec = importlib.util.spec_from_file_location("docs_site_hooks", ROOT / "docs-site" / "hooks.py")
    hooks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hooks)
    english = "# Guide\n\n🇬🇧 English · [🇩🇪 Deutsch](guide.de.md)\n\nText\n"
    assert hooks.on_page_markdown(english, None, None, None) == "# Guide\n\nText\n"
    german = "# Handbuch\n\n[🇬🇧 English](guide.md) · 🇩🇪 Deutsch\n\nText\n"
    assert hooks.on_page_markdown(german, None, None, None) == "# Handbuch\n\nText\n"
    only_german = (
        "# Mitmachen\n\n[🇬🇧 English](https://example.org/CONTRIBUTING.md) · 🇩🇪 Deutsch\n"  # the English file is on GitHub: the line stays
    )
    assert hooks.on_page_markdown(only_german, None, None, None) == only_german
    marked = "Intro\n\n<!-- repo-only:start -->\nAlso as a website.\n<!-- repo-only:end -->\n\nMore\n"
    assert hooks.on_page_markdown(marked, None, None, None) == "Intro\n\nMore\n"


def test_the_workflow_publishes_the_site_and_the_tools_are_pinned():
    workflow = (ROOT / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")
    assert "mkdocs build --strict" in workflow and "actions/deploy-pages@" in workflow and "pages: write" in workflow
    assert "if: github.event_name != 'pull_request'" in workflow  # a pull request builds, only main publishes
    for line in (ROOT / "docs-site" / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            assert re.fullmatch(r"[A-Za-z0-9_.-]+==[0-9][0-9A-Za-z.]*", line.strip()), f"{line}: an exact version"


def test_the_start_pages_link_the_website():
    from carassistant import links

    for name in ("README.md", "README.de.md", "docs/README.md", "docs/README.de.md", "carassistant/DOCS.md", "carassistant/DOCS.de.md"):
        assert links.SITE_URL in (ROOT / name).read_text(encoding="utf-8"), name
