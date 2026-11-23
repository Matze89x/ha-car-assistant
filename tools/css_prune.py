"""Remove selectors whose class is used nowhere (templates, scripts, Python), from a style sheet.

  python tools/css_prune.py carassistant/app/carassistant/static/pc-core.css [--write] [--list]

A rule that still has one live selector stays (only the dead selector goes); classes built from a prefix ("lv-" + level, "s-{{ season }}")
count as used. Formatting and comments are kept, nothing is merged or moved. Check the pages afterwards (tools/make_screenshots.py).
"""

import glob
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "carassistant" / "app" / "carassistant"
DYN = re.compile(r"^(wc-c\d|[bnilw]\d+|n\d|st-.*|sw-.*|s-(summer|winter|allseason)|leaflet-.*|c\d|a\d)$")
src = ""
for f in (
    glob.glob(str(root / "templates/**/*.html"), recursive=True) + glob.glob(str(root / "static/*.js")) + glob.glob(str(root / "*.py"))
):
    src += Path(f).read_text(encoding="utf-8", errors="ignore") + "\n"


def used(c):
    if DYN.match(c) or re.search(r"(?<![\w-])" + re.escape(c) + r"(?![\w-])", src):
        return True
    parts = c.split("-")
    for i in range(1, len(parts)):  # a class built from a prefix: "lv-{{ level }}", "s-" ~ season
        pre = "-".join(parts[:i]) + "-"
        if re.search(re.escape(pre) + r"(\{\{|'\s*~|\"\s*~|\"\s*\+|'\s*\+|\$\{)", src):
            return True
    return False


removed = []


def prune_sel(sel):
    parts = [x.strip() for x in re.split(r",(?![^()]*\))", sel)]
    keep = []
    for p in parts:
        cls = re.findall(r"\.([a-zA-Z_][\w-]*)", re.sub(r"\[[^\]]*\]", "", p))
        if all(used(c) for c in cls):
            keep.append(p)
        else:
            removed.append(p)
    return keep


def blocks(css, lo, hi):
    """yield (start, header_start, header_end, body_start, body_end, end) of top-level blocks in css[lo:hi]; comments are skipped"""
    i = lo
    while i < hi:
        if css.startswith("/*", i):
            i = css.index("*/", i) + 2
            continue
        if css[i].isspace() or css[i] == ";":
            i += 1
            continue
        k = i
        paren = 0
        q = ""
        while k < hi:
            ch = css[k]
            if q:
                if ch == q:
                    q = ""
            elif ch in "\"'":
                q = ch
            elif ch == "(":
                paren += 1
            elif ch == ")":
                paren -= 1
            elif (ch == "{" and paren == 0) or (ch == ";" and paren == 0):
                break
            k += 1
        if k >= hi or css[k] == ";":
            i = k + 1
            continue
        d = 1
        e = k + 1
        q = ""
        while e < hi and d:
            ch = css[e]
            if q:
                if ch == q:
                    q = ""
            elif ch in "\"'":
                q = ch
            elif ch == "{":
                d += 1
            elif ch == "}":
                d -= 1
            e += 1
        yield (i, i, k, k + 1, e - 1, e)
        i = e


def process(css, lo, hi):
    """return list of (start, end, replacement) edits"""
    edits = []
    for s, hs, he, bs, be, e in blocks(css, lo, hi):
        header = css[hs:he].strip()
        if header.startswith("@"):
            if header.startswith(("@media", "@supports")):
                sub = process(css, bs, be)
                edits += sub
                # remove the at-rule when nothing but whitespace/comments is left inside
                inner = css[bs:be]
                for a, b, r in sorted(sub, reverse=True):
                    inner = inner[: a - bs] + r + inner[b - bs :]
                if not re.sub(r"/\*.*?\*/", "", inner, flags=re.S).strip():
                    edits.append((s, e, ""))
            continue
        keep = prune_sel(header)
        if not keep:
            edits.append((s, e, ""))
        elif len(keep) != len([x for x in re.split(r",(?![^()]*\))", header)]):
            edits.append((hs, he, ", ".join(keep) + " "))
    return edits


def main(path, write):
    css = Path(path).read_text()
    edits = process(css, 0, len(css))
    # drop edits nested inside a removed span
    edits.sort()
    out = []
    last = 0
    for a, b, r in edits:
        if a < last:
            continue
        out.append(css[last:a])
        out.append(r)
        last = b
    out.append(css[last:])
    new = "".join(out)
    new = re.sub(r"\n[ \t]*\n([ \t]*\n)+", "\n\n", new)
    print(path, len(css), "->", len(new), "removed selectors:", len(removed))
    if write:
        Path(path).write_text(new)
    return removed


if __name__ == "__main__":
    r = main(sys.argv[1], "--write" in sys.argv)
    if "--list" in sys.argv:
        print("\n".join(sorted(set(r))))
