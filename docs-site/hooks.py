"""Hooks of the documentation site (mkdocs.yml, ``hooks``)."""

import re

# The line at the top of every page that switches between the two languages ("🇬🇧 English · [🇩🇪 Deutsch](guide.de.md)"): GitHub needs it, the site has the
# language selector in its header - and in a language build the link to the file of the OTHER language would find no file. Only links to another page of the
# docs go; the German-only pages that point to the English file on GitHub (an address starting with https) keep theirs.
SWITCH = re.compile(r"^(?:🇬🇧 English · \[🇩🇪 Deutsch\]\((?!https?:)[^)]*\)|\[🇬🇧 English\]\((?!https?:)[^)]*\) · 🇩🇪 Deutsch)[ \t]*\n+", re.M)


# What only makes sense in the repository (a line that points to this very site) stands between these two comments and does not go onto the site.
REPO_ONLY = re.compile(r"<!-- repo-only:start -->.*?<!-- repo-only:end -->[ \t]*\n*", re.S)


def on_page_markdown(markdown, page, config, files):
    return REPO_ONLY.sub("", SWITCH.sub("", markdown, count=1))
