# Charging point providers

🇬🇧 English · [🇩🇪 Deutsch](charge-providers.de.md)

Electric cars find charging points around the car (or around you) on the **Charging** page of the vehicle: with the plugs and their power, sorted by distance or power, filtered by *at least 22 / 50 / 150 kW* and by plug (*CCS, Type 2, CHAdeMO, NACS*). Nothing is requested before you press search, and nothing is sent anywhere else than to the source you chose.

**What it cannot tell you: whether a point is free right now.** No open source delivers that reliably (Open Charge Map has crowd-sourced status, OpenStreetMap none; the live data the EU operators must publish goes to national access points in a format that differs from country to country). The page says so, and shows nothing it does not know.

## Sources

| Source | Key | Data | Licence |
|---|---|---|---|
| **OpenStreetMap** (built in, the start value) | none | position, name, operator, plugs and power as far as the map has them (`amenity=charging_station`, `socket:*`), fee, opening hours, access | ODbL - *© OpenStreetMap contributors* is shown under the list. Asked through the public Overpass API, one request per area every five minutes, with an identifying User-Agent |
| **Open Charge Map** (shipped as a file) | a free key **of your own** (openchargemap.org -> profile -> *my apps*) | worldwide register: plugs, power, operator, points, usage cost, status | The data has **mixed licences**. Car Assistant asks only for data with an open licence (`opendata=true`) and names the **data provider of each point** under it. Contributions by people are CC BY 4.0 |

There is no built-in key: you enter yours under the cog on the Charging page. Without it, nothing is asked from Open Charge Map.

## Your own source (a JSON file)

Like the fuel price providers ([fuel-providers.md](fuel-providers.md)) a source is **one JSON file** - data, never code - in `<data folder>/chargeproviders/`. The shipped `chargeproviders/ocm.json` is the model:

```json
{
  "id": "x",
  "name": "Example register",
  "countries": ["NO"],
  "license": "CC BY 4.0",
  "attribution": "Charging points: Example register, CC BY 4.0",
  "url": "https://api.example.com/charging",
  "params": { "lat": "{lat}", "lon": "{lon}", "km": "{radius_km}" },
  "key": { "header": "X-API-Key", "url": "https://example.com/get-a-key" },
  "items": "results",
  "fields": {
    "lat": "position.lat", "lon": "position.lon", "name": "{title}", "address": "{street}, {zip} {town}",
    "operator": "operator.name", "points": "numberOfPoints", "fee": "usageCost", "hours": "openingHours",
    "access": "access", "provider": "{dataProvider}", "operational": "status.operational"
  },
  "connections": { "path": "connectors", "type": "type", "kw": "powerKW", "count": "quantity" },
  "max_radius_km": 25
}
```

- `id` (`a-z`, `0-9`, `-`, `_`; not `osm`), `name`, `countries` (ISO codes: the source is offered first there), `license` and `attribution` (**shown with the results - keep what the data owner asks for**).
- `url` (https only), `method` (`GET` or `POST`), `params`, `headers`: values may contain `{lat}`, `{lon}`, `{radius_km}`, `{radius_m}` and `{key}`.
- `key`: `{"param": "apikey", "url": "..."}` or `{"header": "X-Key", "url": "..."}`. The person enters a key of their own; without it nothing is asked and the page says so. The key travels in a header or a parameter, is stored on the server only and is never logged.
- `items`: where the list is in the answer (dotted path, empty = the answer itself). `fields`: dotted paths (`position.lat`) or templates with fields in braces (`{street} {number}`); only `lat` and `lon` are required. `provider` names the data provider of a point (shown under it), `operational` is a true / false field.
- `connections`: `path` is the list of plugs of one point, `type` the name of the plug (the words are mapped to *CCS, Type 2, CHAdeMO, NACS, Type 1, household, other*), `kw` the power and `count` how many of them.
- `max_radius_km` (1 to 100). The answer is kept for five minutes per area.

A file that cannot be used (not https, no coordinates, a taken id) is ignored with a note in the log. **Please respect the terms of the service you point a file at** - especially its licence and what it asks to be named. Files for other regions can be shared as examples in this repository.

## Not included (yet)

- **Bundesnetzagentur charging point register** (Germany, CC BY 4.0, a 50 MB CSV with a daily web service) and other national registers: they are lists, not "ask around a point" services, so they do not fit a provider file. A country pack that is read offline may follow.
- **Live availability** from the national access points of the EU (DATEX II): to be added per country when a feed can be used without a contract.
