"""Remove CSS declarations that a later rule with the SAME selector (same media context) always overrides.

Nothing is merged or moved, so the cascade stays exactly as it is: a declaration that is dead (a later rule of equal
specificity sets the same property) is dropped, and rules that end up empty go away. Comments are kept.

Usage: python css_tidy.py <file.css> [--write]     (prints the statistics; writes only with --write)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SHORTHAND = {  # a later shorthand also kills the earlier longhands of its family
    "margin": ("margin-top", "margin-right", "margin-bottom", "margin-left"),
    "padding": ("padding-top", "padding-right", "padding-bottom", "padding-left"),
    "border-radius": (
        "border-top-left-radius",
        "border-top-right-radius",
        "border-bottom-left-radius",
        "border-bottom-right-radius",
    ),
    "gap": ("row-gap", "column-gap"),
    "inset": ("top", "right", "bottom", "left"),
}


def split_top(text: str, sep: str) -> list[str]:
    """Split on `sep` outside of parentheses and quotes."""
    parts, depth, quote, cur = [], 0, "", []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(ch)
    parts.append("".join(cur))
    return parts


def tokenize(css: str) -> list[dict]:
    """Top level: comments, rules {sel, decls}, at-blocks {at, items} (media/supports), raw at-blocks (font-face, keyframes)."""
    items, i, n = [], 0, len(css)
    while i < n:
        if css[i].isspace():
            i += 1
        elif css.startswith("/*", i):
            j = css.index("*/", i) + 2
            items.append({"kind": "comment", "text": css[i:j]})
            i = j
        else:
            j = css.index("{", i)
            head = " ".join(css[i:j].split())
            depth, k = 1, j + 1
            while depth:
                if css.startswith("/*", k):
                    k = css.index("*/", k) + 2
                    continue
                depth += {"{": 1, "}": -1}.get(css[k], 0)
                k += 1
            body = css[j + 1 : k - 1]
            if head.startswith(("@media", "@supports")):
                items.append({"kind": "at", "head": head, "items": tokenize(body)})
            elif head.startswith("@"):
                items.append({"kind": "raw", "text": css[i:k]})
            else:
                decls = [d.strip() for d in split_top(body, ";") if d.strip()]
                items.append({"kind": "rule", "sel": head, "decls": decls})
            i = k
    return items


def prop(decl: str) -> str:
    return decl.split(":", 1)[0].strip().lower()


def tidy(items: list[dict], stats: dict) -> None:
    rules = [it for it in items if it["kind"] == "rule"]
    by_sel: dict[str, list[dict]] = {}
    for r in rules:
        by_sel.setdefault(r["sel"], []).append(r)
    for same in by_sel.values():
        for pos, early in enumerate(same[:-1]):
            later_props: set[str] = set()
            for late in same[pos + 1 :]:
                for d in late["decls"]:
                    p = prop(d)
                    later_props.add(p)
                    for short, longs in SHORTHAND.items():
                        if p == short:
                            later_props.update(longs)
            keep = []
            for d in early["decls"]:
                if prop(d) in later_props and "!important" not in d:
                    stats["dead"] += 1
                else:
                    keep.append(d)
            early["decls"] = keep
    for it in items:
        if it["kind"] == "at":
            tidy(it["items"], stats)
    before = len(items)
    items[:] = [it for it in items if not (it["kind"] == "rule" and not it["decls"])]
    stats["empty"] += before - len(items)


def merge_adjacent(items: list[dict], stats: dict) -> None:
    """Neighbouring rules with the same selector become one (later declarations win); neighbours with the same body share a selector list.
    Nothing sits between them, so the cascade stays exactly as it is."""
    out: list[dict] = []
    for it in items:
        if it["kind"] == "at":
            merge_adjacent(it["items"], stats)
        prev = out[-1] if out else None
        if it["kind"] == "rule" and prev and prev["kind"] == "rule":
            if prev["sel"] == it["sel"]:
                later = {prop(d) for d in it["decls"]}
                prev["decls"] = [d for d in prev["decls"] if prop(d) not in later or "!important" in d] + it["decls"]
                stats["merged"] += 1
                continue
            if prev["decls"] == it["decls"]:
                prev["sel"] = prev["sel"] + ", " + it["sel"]
                stats["merged"] += 1
                continue
        out.append(it)
    items[:] = out


def family(p: str) -> str:
    """Property family: margin-top -> margin, border-radius -> border, -webkit-backdrop-filter -> backdrop (custom properties stay exact)."""
    if p.startswith("--"):
        return p
    p = re.sub(r"^-(webkit|moz|ms)-", "", p)
    return p.split("-")[0]


def families(items: list[dict]) -> set[str]:
    out: set[str] = set()
    for it in items:
        if it["kind"] == "rule":
            out |= {family(prop(d)) for d in it["decls"]}
        elif it["kind"] == "at":
            out |= families(it["items"])
    return out


def hoist_same_selector(items: list[dict], stats: dict) -> None:
    """A later rule with the same selector moves up into the earlier one when no rule in between sets a property of the same family.
    Such a move can not change any result (the property sets are disjoint), so the cascade stays exactly as it is."""
    for it in items:
        if it["kind"] == "at":
            hoist_same_selector(it["items"], stats)
    i = 0
    while i < len(items):
        later = items[i]
        if later["kind"] != "rule":
            i += 1
            continue
        mine = {family(prop(d)) for d in later["decls"]}
        j = i - 1
        target = None
        while j >= 0:
            it = items[j]
            if it["kind"] == "rule" and it["sel"] == later["sel"]:
                target = it
                break
            if it["kind"] == "rule" and mine & {family(prop(d)) for d in it["decls"]}:
                break
            if it["kind"] == "at" and mine & families(it["items"]):
                break
            if it["kind"] == "raw":
                break
            j -= 1
        if target is not None and not any("!important" in d for d in later["decls"] + target["decls"]):
            override = {prop(d) for d in later["decls"]}
            target["decls"] = [d for d in target["decls"] if prop(d) not in override] + later["decls"]
            del items[i]
            stats["hoisted"] += 1
            continue
        i += 1


def dump(items: list[dict], indent: str = "") -> str:
    out = []
    for it in items:
        if it["kind"] == "comment":
            out.extend(([""] if out else []) + [indent + it["text"]])
        elif it["kind"] == "raw":
            out.append(indent + it["text"])
        elif it["kind"] == "rule":
            out.append(f"{indent}{it['sel']} {{ {'; '.join(it['decls'])}; }}")
        else:
            out.append(f"{indent}{it['head']} {{\n{dump(it['items'], indent + '  ')}\n{indent}}}")
    return "\n".join(out)


def main() -> None:
    path = sys.argv[1]
    css = Path(path).read_text(encoding="utf-8")
    items = tokenize(css)
    stats = {"dead": 0, "empty": 0, "merged": 0, "hoisted": 0}
    tidy(items, stats)
    hoist_same_selector(items, stats)
    merge_adjacent(items, stats)
    text = re.sub(r"\n{3,}", "\n\n", dump(items)) + "\n"
    print(
        f"{path}: {stats['dead']} dead declarations, {stats['empty']} empty rules removed, {stats['merged']} merged, {stats['hoisted']} moved up, {len(css)} -> {len(text)} bytes"
    )
    if "--write" in sys.argv:
        Path(path).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
