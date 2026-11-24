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
