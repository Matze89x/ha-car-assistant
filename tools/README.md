# Image tools

Scripts that produced the app icon, the add-on logo, the banner and the default car picture. They need `numpy`, `scipy`, `Pillow` and (for the banner) the Space Grotesk font as TTF
(`fontTools` converts `carassistant/app/carassistant/static/fonts/space-grotesk-variable.woff2`). The source pictures are not part of the repository.

- `make_icon.py <icon.jpg> <out_dir>` – cuts the icon free (transparent, glow kept) and grades it to the site's colours; writes `master.png`.
- `make_banner.py <assets_dir> <out_dir>` – builds `banner.png` and `logo_wide.png` from `master.png` and `SpaceGrotesk.ttf` in `assets_dir`.
- `make_car.py <car.jpg> <out.png>` – cuts the car free (soft edge, no background); shadow and glow are drawn by the page (CSS).

Site colours: accent `#e2001a`, status green `#4ade80`, background `#0d1016`, text `#f2f3f5`.

## Release and screenshots

- `release.py` - the one place of the version and the stage (`release.json`); writes them into every file and both changelogs (`python tools/release.py` shows the state, `set` / `fix` / `feature` change it).
- `make_screenshots.py` - makes every picture of `docs/screenshots/` again from the made-up demo cars with a headless Google Chrome (`--only dashboard,report`, `--langs en`); it runs the app itself on a temporary data folder and reads nothing of a real installation.
  The two *quick entry* pictures (`odometer-photo`, `fuel-scan`) need a tap and a photo first: `cdp.py` (a small DevTools client, standard library only) drives the same Chrome, `demo_photos.py` draws the made-up receipt and instrument cluster that are read by the real text recognition (Tesseract must be installed).
- `check_alignment.py` - opens every page of the *More* list in a headless Chrome on a temporary demo installation and measures that the first block of the page, its title and the gap to the list sit exactly level (`--widths 1000,1200,1440`); `tests/test_page_alignment.py` runs it where Chrome is installed.
- `check_headings.py` - opens every page of the *More* list in a headless Chrome and checks that each heading standing on its own is the section label of the design book (11 px, upper case, dim, left aligned - compared with a real `.vd-group-h` of the same page); `tests/test_page_headings.py` runs it where Chrome is installed.
- `check_ui.py` - the standing button / field rules measured on every page (folded forms opened): no label wraps, a row is one line and one height, one main action per card, form bars bottom right, tap targets of 30 px, names and labels; `--width 360 --lang de` is the hardest case. `pagecheck.py` is the shared base of the three browser checks. `tests/test_page_ui.py` runs it where Chrome is installed.
- `smoke_crawl.py` - walks through every page of a demo installation in a headless Chrome and reports server errors, script errors, failed requests and broken Content Security Policy rules.
- `practice_photos.py` / `ocr_bench.py` - a practice set of made-up instrument clusters and fuel receipts with their right answers, and the measurement of how many the reading gets right (clean and degraded); see docs/maintaining.md.
- `check_source.py` - checks a whole source (plugins/, integrations/, vehicles/) against this version of the app: every package the way the app reads it, indexes against folders, vehicle files. The reusable workflow `.github/workflows/check-source.yml` runs it for a source every week and on every change (`docs/examples/source-ci.yml` is the caller to copy); see docs/sources.md.
