# Maintaining: from a report to a version

🇬🇧 English · [🇩🇪 Deutsch](maintaining.de.md)

How reports and contributions become the next version. Contributors never touch the version - the maintainers bundle it.

## The way of a change

1. **Report or pull request** comes in (an issue with a template, or a pull request from a fork - also one made with an AI assistant).
2. **Triage:** it gets the label `needs-triage`, then `accepted`, `needs-info`, `needs-decision` or `wontfix`. Questions and ideas go to *Discussions*.
3. **Bundle:** accepted work is put into a **milestone** named like the next version, for example `0.5.1 Beta`. A fix release collects about 4-5 corrections or small improvements.
4. **Merge** the pull requests of the milestone into `main` (CI must be green, the code owner reviews).
5. **Version:** the maintainer runs `python tools/release.py fix "English line" "Deutsche Zeile"` once per bundle (a new feature: `feature`). It counts the number up and writes it into every place and both changelogs.
6. **Tag and release:** `git tag v0.5.1-beta`, then *Releases → Draft a new release → Generate release notes* (sorted by label, see `.github/release.yml`).

## Version numbers

`RELEASE.FEATURES.FIXES` plus the stage (Alpha / Beta): the first number counts releases, the second features, the third fixes and corrections. Only `release.json` holds the value; `tools/release.py` writes it everywhere. See [CONTRIBUTING](../CONTRIBUTING.md).

## The Developer add-on

`carassistant-dev/` is a second add-on in the same repository (*Car Assistant Developer*, slug `carassistant_dev`, own data). Its Dockerfile downloads the `dev` branch when it is built. Its version is the next release plus a counter (`0.5.1.3`), kept in `release.json` (`dev`): run `python tools/release.py dev` for every step users should get as an update (`dev 0.5.2` starts a new base at `.1`). The store reads the add-on list from `main`, so after `git push origin dev` run `tools/publish_dev.sh`: it puts only the folder `carassistant-dev/` onto `main` (the released app there stays untouched). When a release goes to `main` (merge `dev`, `python tools/release.py set 0.5.1`), start the next base right away: `python tools/release.py dev 0.5.2`.

## Labels and automation

- Labels are listed in `.github/labels.yml`; *Actions → Sync labels → Run workflow* creates them.
- `.github/CODEOWNERS` makes every pull request wait for the maintainer.
- `.github/dependabot.yml` proposes library updates; `.github/workflows/ci.yml` runs the tests on every push and pull request.

## Keeping the style sheets clean

The look of the app lives in two files (`static/app.css`, then `static/pc-core.css` on top) and one rule: **one definition per component** (see [design.md](design.md), "The fixed building blocks"). Two small tools keep them tidy; run them from time to time and look at every page afterwards (`python tools/make_screenshots.py`, compare before and after):

- `python tools/css_tidy.py <file.css> [--write]` drops declarations that a later rule with the same selector always overrides.
- `python tools/css_prune.py <file.css> [--write] [--list]` drops selectors whose class is used nowhere (templates, scripts, Python); classes built from a prefix count as used.

`tests/test_design_rules.py` guards the rest: braces balanced (a stray `}` makes the browser skip the next rule silently), the font scale, the radii, one button rule, only two kinds of tab bars.

## Checking the app in a browser and with practice photos

Four small tools in `tools/` (they need Google Chrome or Chromium; the photo tool also Tesseract) look at the app the way a person does, on a temporary installation with made-up cars - nothing of a real installation is read:

- `python tools/check_alignment.py` - opens every page of the *More* list and measures that the first block, the title and the gap to the list sit level (see [Design](design.md)); `tests/test_page_alignment.py` runs it.
- `python tools/check_headings.py` - opens every page of the *More* list and checks that each heading standing on its own is the section label of the [design book](design.md) (11 px, upper case, dim, left aligned); `tests/test_page_headings.py` runs it.
- `python tools/check_ui.py [--width 360] [--lang de]` - opens every page (folded forms opened) and measures the standing rules: no button wraps, a row of buttons is one line and one height, one main action per card, form bars bottom right, tap targets of 30 px at least, every button a name and every field a label, nothing wider than the screen; `tests/test_page_ui.py` runs German at 320 px (the narrowest phone) and English wide.
- `python tools/perf_sweep.py [--cars 15] [--scale 1]` - builds a temporary installation with 15 cars and thousands of rows per car (readings, fill-ups, trips with points, track, signal history ...), opens every reachable page and lists the slowest; it fails when a page needs more than `--limit` ms (110), `--profile PAGE` shows where a page's time goes. Last measured: every page below 76 ms at `--scale 1`, the trip pages about 280 ms at five times the data.
- A red CI run: its log can only be read signed in, but every failed test is also written as an *annotation* that the public API shows (`curl https://api.github.com/repos/<owner>/<repo>/check-runs/<id>/annotations`) - see `pytest_terminal_summary` in `tests/conftest.py`.
- `python tools/smoke_crawl.py` - walks through all pages (a few minutes) and reports a server error, a script error, a failed request or a broken rule of the Content Security Policy; a short walk runs as `tests/test_smoke_crawl.py`.
- `python tools/ocr_bench.py` - reads every photo of the **practice set** (`tools/practice_photos.py`: made-up instrument clusters and fuel receipts in several styles and languages, each with its right answer) as it is and as bad as a phone can make it (blurred, dim, crooked, small, over-compressed, with glare) and counts the right answers. Run it before and after a change of the reading: the number must not go down (clean photos: `tests/test_ocr_practice.py`). `python tools/practice_photos.py <folder>` writes the photos and their answers, for practising by hand.
- `python tools/make_screenshots.py` - the pictures of the documentation (see its docstring); `tools/cdp.py` is the small DevTools client the tools above share.

## Settings of the repository (once)

A short list lives in the maintainer's checklist: a branch rule for `main` (pull request, CI must pass, code owner review, no force push), *Actions* approval for first-time contributors and a read-only token, *Discussions* on, private vulnerability reporting, Dependabot alerts, secret scanning with push protection.
