"""How well does the app read an odometer and a fuel receipt? Reads every photo of the practice set (tools/practice_photos.py) - as it is and as bad
as a phone can make it - with the real text recognition (Tesseract must be installed) and counts the right answers.

  python tools/ocr_bench.py [--only cluster|receipt] [--degradations clean,blur] [--show-failures 25]

The number to watch is the last line: change the reading, run this again, and the number must not go down. The photos are made up (no real car, no
real station); a real photo is always harder than these.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "carassistant" / "app"))
sys.path.insert(0, str(ROOT / "tools"))

import practice_photos as pp  # noqa: E402

from carassistant import odometer_scan, receipt  # noqa: E402


def check(case: pp.Case, data: bytes) -> tuple[bool, str]:
    """Is the reading of this photo right? (and what was read, for the list of failures)"""
    if case.kind == "odometer":
        got = odometer_scan.read(data, case.last)
        return got["value"] == case.truth["value"], f"read {got['value']} ({'plausible' if got['plausible'] else 'odd'}), right {case.truth['value']}"
    got = receipt.scan(data, date(2026, 11, 24))
    wrong = []
    for key in ("amount", "price_per_unit", "price_total"):
        if got[key] is None or abs(got[key] - case.truth[key]) > 0.005:
            wrong.append(f"{key} {got[key]} != {case.truth[key]}")
    if got["date"] != case.truth["date"]:
        wrong.append(f"date {got['date']} != {case.truth['date']}")
    # what must not be wrong: a number that is read but not the right one (an odometer that is there but wrong is worse than none)
    odo = got["odometer"]
    if odo is not None and not odometer_scan.plausible(odo, case.last):
        odo = None  # the app does not offer a figure that does not fit the last reading (receipt_web.shown)
    if odo is not None and odo != case.truth["odometer"]:
        wrong.append(f"odometer {odo} != {case.truth['odometer']}")
    if case.truth["odometer"] is not None and odo is None:
        wrong.append("odometer missing")
    if case.truth["notes"] and got["notes"] != case.truth["notes"]:
        wrong.append(f"product {got['notes']!r} != {case.truth['notes']!r}")
    return not wrong, "; ".join(wrong) or "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="cluster or receipt")
    ap.add_argument("--degradations", default=",".join(pp.DEGRADATIONS))
    ap.add_argument("--show-failures", type=int, default=25)
    args = ap.parse_args()
    if not receipt.available():
        print("Tesseract is not installed - nothing to measure")
        return 2
    kinds = [k for k in args.degradations.split(",") if k]
    results: list[tuple[pp.Case, str, bool, str, float]] = []
    for case in pp.all_cases():
        if args.only and not case.name.startswith(args.only):
            continue
        for kind in kinds:
            data = pp.degrade(case.data, kind)
            started = time.time()
            ok, note = check(case, data)
            results.append((case, kind, ok, note, time.time() - started))
    per_kind: dict[str, list[bool]] = defaultdict(list)
    per_tag: dict[str, list[bool]] = defaultdict(list)
    for case, kind, ok, _note, _t in results:
        per_kind[kind].append(ok)
        for tag in case.tags:
            per_tag[tag].append(ok)
        per_tag[case.name.split("/")[0]].append(ok)
    def pct(v: list[bool]) -> str:
        return f"{100 * sum(v) / len(v):5.1f} % ({sum(v)}/{len(v)})"

    print("by degradation:")
    for kind in kinds:
        print(f"  {kind:10} {pct(per_kind[kind])}")
    print("by sort of photo:")
    for tag, v in sorted(per_tag.items()):
        print(f"  {tag:10} {pct(v)}")
    bad = [(c, k, n) for c, k, ok, n, _ in results if not ok]
    if bad:
        print(f"\nwrong ({len(bad)}), the first {min(len(bad), args.show_failures)}:")
        for case, kind, note in bad[: args.show_failures]:
            print(f"  {case.name:44} {kind:9} {note}")
    slowest = max(results, key=lambda r: r[4])
    allv = [ok for _c, _k, ok, _n, _t in results]
    print(f"\nright: {pct(allv)}   slowest reading {slowest[4]:.1f} s ({slowest[0].name}, {slowest[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
