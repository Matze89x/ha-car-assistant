"""The changelog of a package: a small, safe reader for the ``CHANGELOG.md`` a source keeps next to a package (docs/sources.md).

The text comes from a source - a place somebody else runs - so it is never put on a page as it is. It is cut into plain blocks (headings, lists,
paragraphs, code) made of plain spans (text, bold, italic, code); the template writes every text escaped. Links and pictures become their words and
nothing else of the markup is kept, so a changelog can neither bring a link nor any HTML onto the page.

A changelog that is written in sections per version (``## 1.2.0 - 2026-11-20``) is shortened to what is NEW for the person: the sections newer than the
version that is installed. Any other text is shown as it is (cut at a sensible length).
"""

from __future__ import annotations

import re

from .sources import is_newer

MAX_BLOCKS = 120  # blocks shown at most (a heading, a list, a paragraph, a piece of code each)
MAX_ITEMS = 60  # items of one list
MAX_TEXT = 24_000  # characters of text shown at most
MAX_LINE = 600  # characters of one paragraph or list item
READ_LINE = 1000  # characters of a line that are looked at at all (the rest of a line that long is never text a person wrote)

HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
ITEM = re.compile(r"^(\s*)(?:[-*+]|\d{1,3}[.)])[ \t]+(.*)$")
ORDERED = re.compile(r"^\s*\d{1,3}[.)][ \t]")
FENCE = re.compile(r"^\s*(```|~~~)")
RULE = re.compile(r"^ {0,3}(?:([-*_])(?:[ \t]*\1){2,}|={3,})[ \t]*$")  # a line, or the underline of a title: nothing to show
COMMENT = re.compile(
    r"<!--.*?(?:-->|\Z)", re.S
)  # an unclosed comment runs to the end of the text (and one match eats it: no start is looked at twice)
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
BOM = "\N{ZERO WIDTH NO-BREAK SPACE}"  # the mark some editors put in front of a file
# the first number of a heading is the version: "1.2.0", "v1.2", "[1.2.0] - 2026-11-20", "Version 1.2 (2026-11-20)"
VERSION = re.compile(r"^[^\w]*(?:version|release|ver\.?|v)?[ \t]*v?(\d+(?:\.\d+)*(?:-[0-9A-Za-z.]+)?)", re.I)
INLINE = re.compile(
    r"!?\[(?P<link>[^\]\n]{0,200})\]\([^)\s]{0,500}(?:[ \t]+\"[^\"\n]*\")?\)"  # a link or a picture: only its words stay
    r"|`(?P<code>[^`\n]{1,200})`"
    r"|\*\*(?P<bold>[^\s*](?:.*?[^\s*])?)\*\*"
    r"|(?<![\w_])__(?P<boldu>[^\s_](?:.*?[^\s_])?)__(?![\w_])"
    r"|(?<![\w*])\*(?P<star>[^\s*](?:[^*\n]*?[^\s*])?)\*(?![\w*])"
    r"|(?<![\w_])_(?P<under>[^\s_](?:[^_\n]*?[^\s_])?)_(?![\w_])"
)


def spans(text: str) -> list[tuple[str, str]]:
    """One line of text as ``(kind, text)`` pieces: ``t`` plain, ``b`` bold, ``i`` italic, ``c`` code."""
    text = text.strip()
    if len(text) > MAX_LINE:
        text = text[: MAX_LINE - 1].rstrip() + "…"
    out: list[tuple[str, str]] = []
    pos = 0
    for found in INLINE.finditer(text):
        if found.start() > pos:
            out.append(("t", text[pos : found.start()]))
        kind = {"link": "t", "code": "c", "bold": "b", "boldu": "b", "star": "i", "under": "i"}[found.lastgroup]
        out.append((kind, found.group(found.lastgroup)))
        pos = found.end()
    if pos < len(text):
        out.append(("t", text[pos:]))
    return [s for s in out if s[1]]


def version_of(heading: str) -> str:
    """The version a heading names ('' when it names none, like 'Unreleased')."""
    found = VERSION.match(heading)
    return found.group(1).rstrip(".-") if found else ""


def _clean(text: str) -> str:
    """The text without comments and control characters, with plain line ends."""
    plain = CONTROL.sub("", COMMENT.sub("", (text or "").replace("\r\n", "\n").replace("\r", "\n").lstrip(BOM)))
    return "\n".join(line[:READ_LINE] for line in plain.split("\n"))  # no pattern below ever sees a line of 200,000 characters


def _heads(lines: list[str]) -> tuple[dict[int, tuple[int, str]], int]:
    """The headings (line -> level, text) and the level of the headings that name a version (0: none does - the text is not in sections per version)."""
    heads = {i: (len(m.group(1)), m.group(2)) for i, line in enumerate(lines) if (m := HEADING.match(line))}
    return heads, next((lv for lv, text in heads.values() if version_of(text)), 0)


def versions(text: str) -> list[str]:
    """The versions a changelog has a section for, in the order of the text (``[]`` when it is not written in sections per version)."""
    heads, level = _heads(_clean(text).split("\n"))
    return [version_of(t) for lv, t in heads.values() if lv == level and version_of(t)] if level else []


def _sections(lines: list[str], installed: str) -> tuple[list[str], bool, bool]:
    """The lines of the sections that are newer than ``installed``: ``(lines, structured, any)``. ``structured`` is false when no heading names a version
    (then every line is kept); ``any`` says whether a section was kept."""
    heads, level = _heads(lines)
    if not level:
        return lines, False, True
    keep: list[str] = []
    kept = False
    inside = False
    for i, line in enumerate(lines):
        head = heads.get(i)
        if head and head[0] <= level:  # a heading of the version level (or above it) ends the section before it
            version = version_of(head[1]) if head[0] == level else ""
            inside = bool(version) and is_newer(version, installed)
            kept = kept or inside
        if inside:
            keep.append(line)
    return keep, True, kept


def parse(text: str, installed: str = "") -> dict:
    """The changelog as ``{"blocks": [...], "structured": bool, "empty": bool, "cut": bool}``.

    A block is ``{"kind": "h", "level": 4|5, "spans": [...]}``, ``{"kind": "p", "spans": [...]}``, ``{"kind": "ul" | "ol", "rows": [{"spans": [...],
    "depth": 0..2}]}`` or ``{"kind": "code", "text": "..."}``. ``empty``: there is nothing to show - the text is in sections per version and none of
    them is newer than ``installed``, or there is no text at all. ``cut``: it was longer than what is shown."""
    lines, structured, anything = _sections(_clean(text).split("\n"), installed)
    blocks: list[dict] = []
    para: list[str] = []
    fence: list[str] | None = None

    def flush_para() -> None:
        if para:
            blocks.append({"kind": "p", "spans": spans(" ".join(s.strip() for s in para))})
            para.clear()

    for line in lines:
        if fence is not None:  # inside a piece of code: kept as it is, line by line
            if FENCE.match(line):
                blocks.append({"kind": "code", "text": "\n".join(fence)[:2000]})
                fence = None
            else:
                fence.append(line.rstrip()[:200])
            continue
        if FENCE.match(line):
            flush_para()
            fence = []
            continue
        if not line.strip() or RULE.match(line):
            flush_para()
            continue
        head = HEADING.match(line)
        if head:
            flush_para()
            blocks.append({"kind": "h", "level": 4 if len(head.group(1)) <= 2 else 5, "spans": spans(head.group(2))})
            continue
        item = ITEM.match(line)
        if item:
            flush_para()
            row = {"spans": spans(item.group(2)), "depth": min(len(item.group(1).replace("\t", "    ")) // 2, 2)}
            kind = "ol" if ORDERED.match(line) else "ul"
            if not row["spans"]:
                continue
            if blocks and blocks[-1]["kind"] == kind and len(blocks[-1]["rows"]) < MAX_ITEMS:
                blocks[-1]["rows"].append(row)
            else:
                blocks.append({"kind": kind, "rows": [row]})
            continue
        if line.startswith((" ", "\t")) and blocks and blocks[-1]["kind"] in ("ul", "ol") and not para:  # the next line of an item
            blocks[-1]["rows"][-1]["spans"] += spans(" " + line)
            continue
        para.append(line)
    flush_para()
    if fence:  # a piece of code that was never closed
        blocks.append({"kind": "code", "text": "\n".join(fence)[:2000]})
    shown: list[dict] = []
    used = 0
    cut = False
    for block in blocks:
        size = sum(len(t) for _k, t in block.get("spans", [])) + sum(len(t) for it in block.get("rows", []) for _k, t in it["spans"])
        size += len(block.get("text", ""))
        if len(shown) >= MAX_BLOCKS or used + size > MAX_TEXT:
            cut = True
            break
        shown.append(block)
        used += size
    return {"blocks": shown, "structured": structured, "empty": not shown or (structured and not anything), "cut": cut}
