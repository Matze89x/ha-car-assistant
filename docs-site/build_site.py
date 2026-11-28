"""Builds the documentation website (``docs/`` -> ``site/``) with Zensical - see docs/maintaining.md.

    python docs-site/build_site.py [--strict] [--out site] [--serve [port]]

*Zensical* (the maintained successor of Material for MkDocs) builds ONE language per project. The pages of this repository are written once for two
languages (``docs/<page>.md`` and ``docs/<page>.de.md``, so that GitHub shows both), so this script makes two small projects out of ``docs/`` in a work folder -
an English one and a German one -, builds both and puts the German site under ``site/de/``. The structure stays where it always was, in ``mkdocs.yml`` (menu,
the German names of the menu, theme, address): Zensical reads that format and so does this script.

What the older tool chain did with a plugin and a hook is done here:

* a German page ``guide.de.md`` becomes ``guide.md`` of the German project, and the links between German pages (``other.de.md``) follow;
* the line at the top of a page that switches between the languages (GitHub needs it, the site has the language selector in its header) goes, and so does
  what is marked ``<!-- repo-only:start -->`` ... ``<!-- repo-only:end -->`` (a line that points to this very site);
* the menu of the German project has the German names (``nav_translations``).

``--strict`` makes a broken link, a missing picture or a wrong anchor fail the build (the workflow does that on every change of the pages).
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

# The line at the top of every page that switches between the two languages ("🇬🇧 English · [🇩🇪 Deutsch](guide.de.md)"): GitHub needs it, the site has the
# language selector in its header - and in a language project the link to the file of the OTHER language would find no file. Only links to another page of the
# docs go; the German-only pages that point to the English file on GitHub (an address starting with https) keep theirs.
SWITCH = re.compile(r"^(?:🇬🇧 English · \[🇩🇪 Deutsch\]\((?!https?:)[^)]*\)|\[🇬🇧 English\]\((?!https?:)[^)]*\) · 🇩🇪 Deutsch)[ \t]*\n+", re.M)

# What only makes sense in the repository (a line that points to this very site) stands between these two comments and does not go onto the site.
REPO_ONLY = re.compile(r"<!-- repo-only:start -->.*?<!-- repo-only:end -->[ \t]*\n*", re.S)

LANGUAGES = {"en": "English", "de": "Deutsch"}


class _Loader(yaml.SafeLoader):
    """mkdocs.yml may name a Python function (``!!python/name``): it is not needed for the structure that is read here, so it is just read over."""


_Loader.add_multi_constructor("tag:yaml.org,2002:python/", lambda loader, suffix, node: None)


def read_config(path: Path | None = None) -> dict:
    return yaml.load((path or ROOT / "mkdocs.yml").read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506 - a SafeLoader that only reads over a tag


def german_names(config: dict) -> dict[str, str]:
    """The German names of the menu (``nav_translations`` of the German language in ``mkdocs.yml``)."""
    for plugin in config["plugins"]:
        if isinstance(plugin, dict) and "i18n" in plugin:
            return next(lang for lang in plugin["i18n"]["languages"] if lang["locale"] == "de")["nav_translations"]
    raise ValueError("mkdocs.yml has no i18n block with a German language")


def tidy(text: str, lang: str) -> str:
    """A page as the site shows it: without the language line and the repository-only lines; in the German project the links between German pages point at
    ``page.md`` (the files lose their ``.de``)."""
    text = REPO_ONLY.sub("", SWITCH.sub("", text, count=1))
    if lang == "de":
        text = re.sub(r"(\]\([^)#\s]*?)\.de\.md", r"\1.md", text)
        text = re.sub(r'(href="[^"#]*?)\.de\.md', r"\1.md", text)
    return text


def nav_of(items: list, names: dict[str, str] | None) -> list:
    """The menu with the names of the language (``names``: German names, or None for the English ones)."""
    out = []
    for item in items:
        for title, value in item.items():
            name = (names or {}).get(title, title)
            out.append({name: nav_of(value, names) if isinstance(value, list) else value})
    return out


def prepare(lang: str, work: Path, base_url: str, config: dict | None = None) -> Path:
    """The project of one language in ``work/<lang>``: its pages (``docs/``), its ``mkdocs.yml``. Returns the folder of the project."""
    config = config or read_config()
    root = work / lang
    docs = root / "docs"
    if root.exists():
        shutil.rmtree(root)
    docs.mkdir(parents=True)
    for path in sorted(DOCS.rglob("*")):
        rel = path.relative_to(DOCS)
        if path.is_dir() or any(part.startswith(".") for part in rel.parts):
            continue
        if rel.parts[0] == "examples" and path.name not in ("README.md", "README.de.md"):
            continue  # the example packages are code, not pages: they stay in the repository (the pages link to them there)
        if path.suffix == ".md":
            german = path.name.endswith(".de.md")
            if (lang == "de") != german:
                continue
            target = docs / (str(rel)[: -len(".de.md")] + ".md" if german else str(rel))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(tidy(path.read_text(encoding="utf-8"), lang), encoding="utf-8")
        else:
            target = docs / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
    base = base_url.rstrip("/")
    project = {
        "site_name": config["site_name"],
        "site_description": config["site_description"],
        "site_url": base + ("/de/" if lang == "de" else "/"),
        "docs_dir": "docs",
        "site_dir": "site",
        "use_directory_urls": config.get("use_directory_urls", True),
        "theme": {**{k: v for k, v in config["theme"].items() if k != "name"}, "variant": "classic", "language": lang},
        "nav": nav_of(config["nav"], german_names(config) if lang == "de" else None),
        "markdown_extensions": _extensions(config["markdown_extensions"]),
        "extra_css": config.get("extra_css", []),
        "extra": {
            **config.get("extra", {}),
            "alternate": [
                {"name": name, "link": base + ("/de/" if code == "de" else "/"), "lang": code} for code, name in LANGUAGES.items()
            ],
        },
        "plugins": ["search"],
    }
    (root / "mkdocs.yml").write_text(yaml.safe_dump(project, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return root


def _extensions(extensions: list) -> list:
    """The Markdown extensions of ``mkdocs.yml`` in a form every reader can take: the two places that name a Python function by a YAML tag (the anchors of
    GitHub - the umlauts stay -, so the links between the pages work in both places - and the Mermaid fence) name it by a string."""
    out = []
    for ext in extensions:
        if ext == "toc" or (isinstance(ext, dict) and "toc" in ext):
            out.append({"toc": {"permalink": True, "slugify": {"object": "pymdownx.slugs.slugify", "kwds": {"case": "lower"}}}})
        elif isinstance(ext, dict) and "pymdownx.superfences" in ext:
            out.append(
                {
                    "pymdownx.superfences": {
                        "custom_fences": [{"name": "mermaid", "class": "mermaid", "format": "pymdownx.superfences.fence_code_format"}]
                    }
                }
            )
        else:
            out.append(ext)
    return out


def build(project: Path, strict: bool) -> Path:
    """Build one project with Zensical; returns the folder of the site it made."""
    command = [sys.executable, "-m", "zensical", "build", "--clean", "-f", "mkdocs.yml"] + (["--strict"] if strict else [])
    done = subprocess.run(command, cwd=project, capture_output=True, text=True, check=False)  # noqa: S603
    if done.returncode:
        sys.stderr.write(f"--- {project.name}: the build failed\n{done.stdout[-3000:]}\n{done.stderr[-3000:]}\n")
        raise SystemExit(done.returncode)
    return project / "site"


SELECTOR = re.compile(r'<a href="[^"]*" hreflang="(en|de)" class="md-select__link">')
ALTERNATE = re.compile(r'<link rel="alternate" href="[^"]*" hreflang="(en|de)">')


def _selector_link(links: dict, match: re.Match) -> str:
    return f'<a href="{links[match.group(1)][0]}" hreflang="{match.group(1)}" class="md-select__link">'


def _alternate_link(links: dict, match: re.Match) -> str:
    return f'<link rel="alternate" href="{links[match.group(1)][1]}" hreflang="{match.group(1)}">'


def point_the_selector(site: Path, base_url: str) -> int:
    """Every page of the merged site: the language selector (and the hint for search engines) names the SAME page in the other language, not its start page -
    Zensical knows only one address for each language, the older plugin knew every page. A page that has no counterpart points to the start page of the other
    language. The links of the selector are relative (they work on this computer too), those of the hint are full addresses. Returns the number of pages changed."""
    base = base_url.rstrip("/") + "/"
    changed = 0
    for page in sorted(site.rglob("*.html")):
        whole = page.relative_to(site).as_posix()
        if page.name == "404.html":
            continue  # it is shown at any address: relative links would lead astray
        rel = whole[3:] if whole.startswith("de/") else whole  # the page inside its own language
        to_root = "../" * whole.count("/")
        links = {}
        for lang, folder in (("en", ""), ("de", "de/")):
            name = rel if (site / folder / rel).is_file() else ""
            links[lang] = (to_root + folder + name, base + folder + name)
        text = page.read_text(encoding="utf-8")
        new = SELECTOR.sub(functools.partial(_selector_link, links), text)
        new = ALTERNATE.sub(functools.partial(_alternate_link, links), new)
        if new != text:
            page.write_text(new, encoding="utf-8")
            changed += 1
    return changed


def make_site(out: Path, strict: bool, base_url: str, work: Path | None = None) -> Path:
    """Both languages, merged: English in ``out``, German in ``out/de``."""
    config = read_config()
    with tempfile.TemporaryDirectory() as tmp:
        folder = work or Path(tmp)
        sites = {lang: build(prepare(lang, folder, base_url, config), strict) for lang in LANGUAGES}
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(sites["en"], out)
        shutil.copytree(sites["de"], out / "de")
    point_the_selector(out, base_url)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--strict", action="store_true", help="a broken link, picture or anchor fails the build")
    parser.add_argument("--out", default="site", help="the folder of the site (default: site)")
    parser.add_argument("--serve", nargs="?", const=8000, type=int, metavar="PORT", help="look at it on this computer (default port 8000)")
    args = parser.parse_args()
    config = read_config()
    out = (ROOT / args.out).resolve()
    if args.serve is None:
        make_site(out, args.strict, config["site_url"])
        print(f"the site is in {out} ({sum(1 for _ in out.rglob('*.html'))} pages, English and German)")
        return
    # for looking at it: the same address layout as on GitHub Pages (/ha-car-assistant/...), the language selector stays on this computer
    base = f"http://127.0.0.1:{args.serve}/" + config["site_url"].rstrip("/").rsplit("/", 1)[-1]
    with tempfile.TemporaryDirectory() as tmp:
        served = Path(tmp) / "served"
        site = make_site(Path(tmp) / "site", args.strict, base)
        served.mkdir()
        (served / base.rsplit("/", 1)[-1]).symlink_to(site)
        print(f"open {base}/ - Ctrl-C ends it")
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(served))
        with http.server.ThreadingHTTPServer(("127.0.0.1", args.serve), handler) as httpd, contextlib.suppress(KeyboardInterrupt):
            httpd.serve_forever()


if __name__ == "__main__":
    main()
