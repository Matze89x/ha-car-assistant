# Fuel price providers

🇬🇧 English · [🇩🇪 Deutsch](fuel-providers.de.md)

Fuel prices differ from country to country, so Car Assistant has no built-in price service for "the world". Instead there is an **open interface**: a provider is **one JSON file** that tells the app where an open HTTP/JSON service is, how to ask it for the stations around a point, and which field of the answer is what. A file is only read, never run; only `https` addresses are used; nothing is requested unless somebody searches for stations.

Built in: **Tankerkönig** (Germany, needs your own free key under *System*), **OpenStreetMap** (stations everywhere, no prices) and the shipped files in `carassistant/app/carassistant/fuelproviders/` (France today). **Your own files** go into the folder `fuelproviders/` of the add-on's data folder (`/data/fuelproviders/` in Home Assistant, reachable through the `share`/File editor add-ons of your choice); they win over a shipped file with the same `id`. The provider of the country of your Home Assistant is chosen first.

## The file

```json
{
  "id": "fr",
  "name": "France - prix des carburants (data.gouv.fr)",
  "countries": ["FR"],
  "license": "Licence Ouverte 2.0",
  "attribution": "Prices: Ministère de l'Économie / data.economie.gouv.fr, Licence Ouverte 2.0",
  "url": "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records",
  "params": { "where": "within_distance(geom, geom'POINT({lon} {lat})', {radius_km}km)", "limit": "100" },
  "items": "results",
  "fields": { "lat": "geom.lat", "lon": "geom.lon", "name": "{adresse}", "address": "{cp} {ville}" },
  "prices": { "e5": "sp95_prix", "e10": "e10_prix", "diesel": "gazole_prix" },
  "max_radius_km": 25
}
```

- `id` (a-z, 0-9, `-`, `_`; not `osm` or `tankerkoenig`), `name`, `countries` (ISO codes: the provider is offered first there), `license` and `attribution` (**shown next to the prices - keep what the data owner asks for**).
- `url` (https), `method` (`GET` default, or `POST`), `params`, `headers`: values may contain `{lat}`, `{lon}`, `{radius_km}`, `{radius_m}` and `{key}`.
- `key`: `{"param": "apikey", "url": "https://where-to-get-one"}` or `{"header": "X-Key", ...}`. The person enters a key of their own under *System* (there is no built-in key); without it nothing is asked.
- `items`: where the list of stations is in the answer (dotted path, empty = the answer itself). `fields`: dotted paths (`geom.lat`) or templates with fields in braces (`{street} {number}`) for `lat`, `lon`, `name`, `brand`, `address`, `open` (true/false).
- `prices`: which field holds the price of `e5`, `e10`, `diesel`. `price_scale` multiplies prices (1 by default). `max_radius_km` (1-100).

The answer of a provider is kept for five minutes per area. Please respect the terms of the service you point a file at.

Packages from sources (like plugins) for providers may follow; the file format stays the same.
