# Third-party notices

Car Assistant itself is licensed under the **GNU General Public License v3.0 only** (see `LICENSE`). Everything below is used under its own license; all of them are compatible with the GPL v3.0. Full texts of the licenses that ask for it are in `licenses/`.

## Fonts, icons, map

- **Space Grotesk**, **Space Mono** – SIL Open Font License 1.1 (`licenses/OFL-1.1-SpaceGrotesk-SpaceMono.txt`).
- **Material Design Icons** (Pictogrammers) – Apache License 2.0, https://pictogrammers.com/library/mdi/ (`licenses/Apache-2.0-MaterialDesignIcons.txt`). The paths are used unchanged; all icons in the app come from this set.
- **Leaflet** 1.9.4 – BSD-2-Clause, https://leafletjs.com (`licenses/BSD-2-Clause-Leaflet.txt`). Bundled unchanged under `static/vendor/leaflet/`.
- **Map data and tiles** © OpenStreetMap contributors – ODbL, https://www.openstreetmap.org/copyright. The tiles are fetched by the app from `tile.openstreetmap.org` (identifying User-Agent, cached for a week, at most two connections) and fall under the [OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/); they can be switched off in the settings.
- **Place names**: by default they come from an offline list of the cities of the world inside the app: [GeoNames](https://www.geonames.org) `cities15000` (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/), reduced to name, position and population (`carassistant/app/carassistant/geodata/`). Nothing is sent anywhere. Optional: if you enter an address for place names, a Nominatim-compatible server (for example [Nominatim](https://nominatim.openstreetmap.org), OpenStreetMap data, ODbL, [usage policy](https://operations.osmfoundation.org/policies/nominatim/)) is asked for the coordinates of trip starts and ends.
- **Fuel stations** (optional): stations everywhere come from OpenStreetMap through the public [Overpass API](https://overpass-api.de) (ODbL, cached, one request per area every five minutes). Prices come from open services of the countries, described as data files (`carassistant/app/carassistant/fuelproviders/`, see docs/fuel-providers.md): in Germany from **Tankerkönig** / Markttransparenzstelle für Kraftstoffe (MTS-K), licence **CC BY 4.0**, https://creativecommons.tankerkoenig.de - only with **your own** free API key (there is no built-in key); in France from the open data of the Ministère de l'Économie (data.economie.gouv.fr, Licence Ouverte 2.0), in Austria from the E-Control Spritpreisrechner (api.e-control.at). Each source's attribution is shown next to the prices.

## Python libraries (installed from `carassistant/requirements.txt`, not copied into this repository)

| Library | License |
|---|---|
| FastAPI | MIT |
| uvicorn | BSD-3-Clause |
| Jinja2 | BSD-3-Clause |
| python-multipart | Apache-2.0 |
| paho-mqtt | EPL-2.0 or BSD-3-Clause (used under BSD-3-Clause) |
| requests | Apache-2.0 |
| fpdf2 | LGPL-3.0 |
| Pillow | MIT-CMU (HPND) |
| webauthn (Duo Labs) | BSD-3-Clause |
| cryptography | Apache-2.0 or BSD-3-Clause |
| pywebpush | MPL-2.0 |
| py-vapid (installed with pywebpush) | MPL-2.0 |
| http-ece (installed with pywebpush) | MIT |
| pypdf | BSD-3-Clause |
| defusedxml | PSF-2.0 |

Notes: *MPL-2.0* (pywebpush, py-vapid) and *LGPL-3.0* (fpdf2) apply to those libraries only and are used unmodified; their source is available from their projects (https://pypi.org). The Apache-2.0 and BSD libraries ask for their copyright notice and license text to stay with distributed copies: the packages carry them, and the installed packages are what the add-on image contains.

## Thanks

Car Assistant runs as an app for [Home Assistant](https://www.home-assistant.io/) and is not affiliated with it.
