"""Where the project and its documentation live. The app only LINKS there (a plain link somebody has to click) - it never fetches anything from there.

The documentation is a website (GitHub Pages, built from the pages in ``docs/`` with Zensical, see docs-site/build_site.py and docs/maintaining.md) in two languages: the English
start page is the address of the site, the German one lies under ``de/``. The language of the app decides which one a link opens, and every language
without pages of its own reads the English ones.
"""

from __future__ import annotations

PROJECT_URL = "https://github.com/Matze89x/ha-car-assistant"
AUTHOR_URL = "https://github.com/Matze89x"
SITE_URL = "https://matze89x.github.io/ha-car-assistant/"  # the documentation website; mkdocs.yml names the same address (site_url)
DOCS_LANGUAGES = ("de",)  # the languages that have pages of their own: docs/<page>.<code>.md, on the site under <code>/


def docs_url(lang: str, page: str = "") -> str:
    """The documentation website in the language of the app: its start page, or one page by its name (``"guide"`` opens ``guide.html``)."""
    folder = f"{lang}/" if lang in DOCS_LANGUAGES else ""
    return f"{SITE_URL}{folder}{page + '.html' if page else ''}"
