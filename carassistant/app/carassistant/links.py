"""Where the project and its documentation live on GitHub. The app only LINKS there (a plain link somebody has to click) - it never fetches anything
from there on its own.

The documentation exists in two languages (``docs/<page>.md`` English, ``docs/<page>.de.md`` German, docs/translating.md): the language of the app
decides which one a link opens, and every language without pages of its own reads the English ones.
"""

from __future__ import annotations

PROJECT_URL = "https://github.com/Matze89x/ha-car-assistant"
AUTHOR_URL = "https://github.com/Matze89x"
DOCS_LANGUAGES = ("de",)  # the languages that have pages of their own: docs/<page>.<code>.md


def docs_url(lang: str, page: str = "README") -> str:
    """A page of the documentation on GitHub in the language of the app: ``README`` is the index of all pages (``docs/README.md``)."""
    suffix = f".{lang}" if lang in DOCS_LANGUAGES else ""
    return f"{PROJECT_URL}/blob/main/docs/{page}{suffix}.md"
