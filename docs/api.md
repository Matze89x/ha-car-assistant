# Plugin API

🇬🇧 English · [🇩🇪 Deutsch](api.de.md)

How a plugin or integration sends vehicle data to Car Assistant. Car Assistant never talks to a car itself: **the plugin does** (in the car, on a Raspberry Pi, in a cloud bridge, …) and delivers the values with one HTTP request. Nothing is fetched from the internet and nothing is invented – a page shows only what a plugin has delivered.

## One token = one car
Everything is per vehicle, because every car can be connected differently. Set a plugin up under *Car → More → Integrations* (see [plugins.md](plugins.md)); a **plugin** gets its own token at that moment (shown once, can be replaced, revoked by removing the plugin). A token works for **its car only** – any other vehicle id answers `403`.

The API is reached through the address of your direct access (the port you chose or your reverse proxy, see [DOCS.md](../carassistant/DOCS.md)). The token is the only credential: `Authorization: Bearer ca_…`. Use HTTPS from outside.

## Send data
```
POST /api/v1/vehicles/<id>/data
Authorization: Bearer ca_...
Content-Type: application/json

{"odometer_km": 52340, "ignition": false, "doors": {"front_left": false, "trunk": true}, "locked": true}
```
All fields are optional – send what you know. Unknown fields are rejected (`422`). Body: max 20 kB.

| Field | Type | Rule | Shown |
|---|---|---|---|
| `odometer_km` | number | 1 … 2 000 000; stored only if higher than the known reading | everywhere (badge "from car") |
| `vin` | string | letters and digits, 5 … 20 (spaces and hyphens are dropped, upper case). **Only compared, never stored from the plugin:** the VIN is typed in by a person in the vehicle data. If it matches, the vehicle page shows *Confirmed by the car*; if it differs, the whole request is refused (`409 vin_mismatch`, nothing stored); if none is typed in yet, the answer says `not checked` | vehicle page |
| `fuel_level_pct` | number | 0 … 100 | Home |
| `range_km` | number | 0 … 3000 | Home |
| `fuel_amount` | number | 0 … 1000: litres in the tank (kWh in the battery of an electric car), when the car reports the amount itself. With the size of the tank (vehicle data) the app also shows the per cent; with the per cent and the size it works out the amount | Home |
| `position` | `{"lat": .., "lon": .., "street": "..", "place": ".."}` | valid coordinates; `street` (with house number) and `place` (town) are optional text, up to 120 characters: when the car knows them itself they replace the address lookup for that spot (nothing is asked from a server) and name the place of trips | Home: location card |
| `ignition` | boolean | `true` = on | Home plaque, "parked since" |
| `doors` | object `name → boolean/null` | `true` = open, `false` = closed, `null` = remove the name | Home plaque, Security page |
| `windows` | object `name → boolean/null` | same as `doors` | Home plaque, Security page |
| `locked` | boolean | `true` = locked | Security page |
| `warnings` | object `code → text/null` | a message from the car; `null` removes the code; text up to 120 characters, at most 16 codes | Home: "Vehicle messages" widget |
| `speed_kmh` | number | 0 … 450 | Home: car data |
| `outside_temp_c` | number | -60 … 70 | Home: car data |
| `battery_12v_v` | number | 0 … 30 (volts) | Home: car data |
| `battery_pct` | number | 0 … 100 (high-voltage battery of an electric / hybrid car) | Home: car data |
| `charging` | boolean | `true` = charging | Home: car data |
| `charge_power_kw` | number | 0 … 1000 | Home: car data (while charging) |
| `tyre_pressure_bar` | object `fl/fr/rl/rr → number/null` | 0 … 8 bar; `null` removes a wheel | Home: car data |
| `coolant_temp_c`, `oil_temp_c` | number | -40 … 200 (°C) | Home: car data |
| `cabin_temp_c` / `target_temp_c` | number | -40 … 80 / 5 … 40 (°C) | Home: car data |
| `climate_on` | boolean | `true` = climate control running | Home: car data |
| `heading_deg` | number | 0 … 360 | (stored, for plugins and trips) |
| `consumption_l_100km` | number | 0 … 100 (l or kWh per 100 km, from the car) | Home: car data |
| `service_due_days` / `service_due_km` | number | days / km until the car's own service; negative = overdue | Home: car data |
| `oil_change_due_days` / `oil_change_due_km` | number | days / km until the oil change; negative = overdue | Home: car data, vehicle messages |
| `plugged` | boolean | `true` = charging cable connected | Home: car data |
| `charge_limit_pct` / `charge_minutes_left` | number | 0 … 100 / 0 … 5000 | Home: car data |
| `parking_brake` | boolean | `true` = applied | Home: car data (when applied) |
| `lights` | object `name → boolean/null` | `true` = on; names `low_beam`, `high_beam`, `hazard`, `parking` (others as written) | Home: car data |
| `adblue_level_pct` / `adblue_range_km` | number | 0 … 100 / 0 … 50000 (exhaust fluid of a diesel) | Home: car data |
| `oil_level_pct` / `oil_warning` | number / boolean | 0 … 100 / `true` = the car asks to check the oil | Home: car data |
| `speed_limit_kmh` | number | 0 … 250, the limit the car currently reads | Home: car data |

### Doors and windows
- **Names:** lower-case letters, digits and `_`, up to 32 characters, starting with a letter; at most 16 per object. Recommended names get a translated label: doors `front_left`, `front_right`, `rear_left`, `rear_right`, `trunk`, `hood`; windows `front_left`, `front_right`, `rear_left`, `rear_right`, `sunroof`. Any other name is shown as written.
- **Left/right** means as seen from the driver's seat looking forward, independent of the side of the steering wheel.
- **Only the names you send change.** Send a single door when it changes, or the whole set – both work. `null` removes a name.
- Each value keeps **the time the car reported it**; the pages show "last signal 5 min ago". Send `measured_at` (an ISO time such as `2026-11-20T08:15:00Z`, or seconds since 1970) with the request when you know when the car really reported - then that time is kept, never a time in the future, and a value never gets an older time than it had. Without it the arrival counts, **but a value that is exactly the one already stored is no news**: sending the remembered values again (for example after a restart of Car Assistant or of the plugin) does not make the car look as if it had just reported. Values from bound Home Assistant entities carry the time Home Assistant gives (`last_reported` / `last_updated`). Values do not expire: if the car reports nothing while parked, send nothing – the last state stays with its age.

## Bigger deliveries
- **gzip:** every `POST` may send `Content-Encoding: gzip`. The limits count the **unpacked** size (a small file cannot blow up); a broken file answers `400 invalid_gzip`.
- **Track (drives)** – `POST /api/v1/vehicles/<id>/track`, up to 500 points per request, newest 50 000 kept per car:
  ```
  {"points": [{"ts": "2026-11-15T08:00:00Z", "lat": 52.5, "lon": 13.4, "speed_kmh": 30}]}
  ```
  `ts` is optional (default: now); the car's clock may be unset, so send the time you know. The newest point also becomes the car's current position and speed. Read back with `GET …/track?since=<ISO time>&limit=200`. **Trips:** a run of points with no gap over ten minutes becomes a trip in the log book (date, times, start/end place, distance, the route) once nothing new has come for ten minutes; runs under 0.3 km or 3 points are dropped. Nothing to do for the plugin.
- **Raw signals** – `POST /api/v1/vehicles/<id>/signals` with `{"signals": {"kombi.odo_km": 52340, "pc.override": true, "old.name": null}}`. For values that have no field above (flags, diagnostics, anything specific to your car). Names: lower-case letters, digits, `_` and `.`, up to 64 characters; values are kept as text (up to 2000 characters); `null` removes one; at most 300 per car. The app **only keeps and shows** them (*Debug & log* page) and does not interpret them. Read back with `GET …/signals`.
- **Events** – `POST /api/v1/vehicles/<id>/events` with `{"events": [{"type": "speed_sign", "ts": "2026-11-15T08:00:00Z", "text": "50", "value": 50, "lat": 52.5, "lon": 13.4}]}`: anything with a time and maybe a place (traffic signs read, town borders crossed, warnings). `type` is lower-case letters, digits, `_` and `.` (up to 40); `text` up to 200 characters, `value` a number, `lat`/`lon` together; up to 200 per request, the newest 2000 per car are kept. Read back with `GET …/events?type=speed_sign&since=<ISO time>&limit=200`.
- **Trip computer values** – `POST /api/v1/vehicles/<id>/trip-summary` with `{"ts": "2026-11-15T08:30:00Z", "distance_km": 12.5, "consumption_l_100km": 8.2, "avg_speed_kmh": 26, "minutes": 28}` (all optional, at least one). The values of the car's own trip computer are given to the trip that ended within 20 minutes of `ts` (shown on the trip card and the trip page); when that trip is not made yet they wait up to 3 days for it. Send it when the ignition goes off.
- **Refuel** – `POST /api/v1/vehicles/<id>/refuel` with `{"date": "2026-11-15", "odometer_km": 52340, "amount": 41.5, "price_total": 72.3, "full_tank": true}` (all optional; `amount` in litres or kWh). Use it when the car noticed that the tank jumped. It becomes an entry of the fuel log marked `api:<plugin name>`; if the log already has an entry for that day and mileage (within 5 km) nothing is added. Never invent an amount - leave it out when you do not know it, a person completes the entry.
- **Entries of an integration page** – `POST /api/v1/vehicles/<id>/modules/<integration>/<page>` (the integration must be installed and running) with `{"rows": [{"values": {...}}, {"id": 5, "values": {...}}], "delete": [7]}`: an entry without `id` is added, one with an `id` is changed (fields marked *once* keep their first value), `delete` removes entries. Values are checked exactly like in the form; one bad value rejects the whole request (`422`). At most 500 items per request. This is how a plugin delivers, for example, the control units of the *Coding* integration.


## Towards the vehicle: one switch (first step)
Everything above flows **from** the plugin **to** Car Assistant. The only thing that flows the other way is a small set of switches the dashboard sets and the plugin only **reads**. The first one is **debug**:
```
GET /api/v1/vehicles/<id>/control   →   {"ok": true, "control": {"debug": false, "interval_s": 120}}
```
Every `POST …/data` answers with the same `control` object, so a plugin that reports regularly does not need to poll separately. The switch is set by a person in the dashboard (*Car → More → Plugins → Logs of the plugin*). The same page sets `interval_s` (30, 60, 120, 180 or 300; default 120): how often the person would like the plugin to report. It is a request - a plugin may report faster while driving and slower when parked.

While **debug is on**, the plugin should send its log lines:
```
POST /api/v1/vehicles/<id>/logs
{"lines": [{"level": "debug", "message": "CAN frame 0x3C0 decoded"}, "plain text lines work too"]}
```
`level` is `debug`, `info`, `warn` or `error` (default `info`), `ts` is optional (ISO time), `message` up to 500 characters, up to 50 lines per request. **While debug is off the answer is `409 debug_off` and nothing is kept** – a plugin must not send logs then. The dashboard keeps the newest lines **per plugin** (default 1000; *Settings → System → Plugin logs* sets it, the oldest go first), shows them on the *Debug & log* page (filter per plugin) and deletes them when the plugin is removed.

## Read back
```
GET /api/v1/vehicles/<id>/data   →   {"ok": true, "data": {...}, "updated": {"doors": "2026-11-13T18:00:00+00:00", ...}}
```
The same shape as the POST body plus the arrival time of each value – to test a plugin.

## Other endpoints
- `GET /api/v1` – checks the token; returns `version`, `connector` and the accepted `fields`.
- `GET /api/v1/vehicles` – the vehicle this token may use.

## Answers and errors
Success: `{"ok": true, "result": {"odometer_km": "stored", …}, "control": {"debug": false, "interval_s": 120}}`. Errors have the form `{"error": "<code>", "message": "…"}`: `401` token missing/invalid, `403` token not allowed for this vehicle, `404` unknown vehicle, `400` body is not JSON, `413` body too large, `422` invalid value (the message names the field), `409` debug logs sent while debug is off.

## Good practice for plugins
- Send on change, and not more often than every few seconds. Do not repeat unchanged values endlessly.
- Send only what the car really reports. Never send guessed or fake values.
- Map your car's own signals to the standard names above; keep car-specific details inside your plugin.
- One plugin per car; use *New token* if a token was exposed.

## Example
[`docs/examples/push_data.py`](examples/push_data.py) – Python standard library only. The same works with `curl`, Node, a Home Assistant `rest_command` or a microcontroller.

## Stability and compatibility (a promise to everyone who writes plugins)
People write their own plugins and integrations, so **what works today keeps working**. The rules:

- **`/api/v1` is frozen.** Inside `v1` existing fields, their meaning and the answers of existing endpoints do not change in a way that breaks a plugin. Only **additions** happen: new optional request fields, new keys in answers, new endpoints, new allowed values. A plugin must **ignore keys it does not know** in answers.
- **Look before you send.** `GET /api/v1` returns `version`, `api` and `fields` (what this Car Assistant accepts). An older Car Assistant answers an unknown request field with `422 unknown_field`, so a plugin that wants to use a newer field checks that it is listed in `fields` first (example: `measured_at`).
- **Nothing is changed or removed silently.** A function that is to change, be replaced or go away is first **announced as deprecated**: in the changelog, in these documents (a *Deprecated* note with the date it will be removed and what to use instead) and - where a request is concerned - with the answer headers `Deprecation: true` and `Sunset: <date>`. The replacement exists **when** the announcement is made.
- **Notice period.** A deprecated function keeps working, unchanged, **for a stated time after the announcement** and is only then removed. **Fixed periods are set with the official release 1.0** (while Car Assistant is in Beta, 0.x, we announce every such change in the changelog and keep the old way working as long as we reasonably can, but we make no fixed promise yet). Security fixes are the one exception (shorter, with the reason named).
- **Breaking changes** only come in a **new API version** (`/api/v2`); how long `v1` then stays available is set with 1.0, too.
- **The package file (`plugin.json`)** follows the same rules: new keys are optional, old keys keep working; keys an older Car Assistant does not know are ignored, so one package can serve several versions.
- **Backups:** every older backup format stays restorable ([backup](backup.md)).
- **Beta (0.x):** we keep to the principles above already (nothing silent, additions only, announce first), so that plugins written now do not have to be rewritten at 1.0. The fixed periods follow with 1.0.

**Currently deprecated:** nothing. When something is announced, every answer that touches it carries the standard HTTP headers `Deprecation: true`, `Sunset: <date>` (when a date is set) and a `Link` to this section, and a `POST` answer that used a deprecated field lists it under `deprecated` (`field`, `since`, `sunset`, `use`). These headers are only a label that says "this will change - see the docs"; the function keeps working. Test a plugin against a current Car Assistant and look at the headers of the answers.

*For the maintainers:* any change to the API or the package file is checked against this list before it is merged (see `CLAUDE.md`).

- `GET /api/v1/vehicles/<id>/modules/<integration>/<page>` - the entries of a page of an installed, running [integration](integrations.md) of this car (for example the stations of the web radio), in their order. `secret` fields (access codes) are never part of it.
