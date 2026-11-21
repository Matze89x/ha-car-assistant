import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant" / "static"


def test_more_opens_the_first_page_only_where_the_list_stands_next_to_it():
    """Below the width where CSS shows the More list next to the page, "More" must show the list itself - else the page has no way back (a loop)."""
    css = (STATIC / "pc-core.css").read_text()
    js = (STATIC / "more.js").read_text()
    pane_from = int(re.search(r"@media \(min-width: (\d+)px\) \{\s*/\* the original switches to list \+ page", css).group(1))
    redirect_from = int(re.search(r"min-width: (\d+)px", js).group(1))
    assert redirect_from == pane_from
