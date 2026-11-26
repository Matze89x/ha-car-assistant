# Plugins and integrations

🇬🇧 English · [🇩🇪 Deutsch](plugins.de.md)

> **New here?** Start with [start-here.md](start-here.md) - a first integration or plugin running on your computer in ten minutes. The guide for reference: [plugin-guide.md](plugin-guide.md).

Everything here belongs to **one car**: each car can be connected differently, and which integrations are possible can depend on the plugin. You manage it under *Car → More → Integrations*.

- A **plugin** is the connection to a car (something in the car or next to it). Setting it up creates its token for the [Plugin API](api.md); the plugin uses it to exchange data between the car and Car Assistant.
- An **integration** is an optional extra for that car (for example a web radio). It has settings but no token unless it needs one.

## What a plugin is - a connection to the outside
Car Assistant never talks to a car - or to any other outside system - itself. **Every connection to the outside is a plugin**: to a car, to a web service you log in to, to a cloud account, to a device or program. A plugin talks to the app **only through the [Plugin API](api.md)** - the same interface for all of them - and may do whatever its own side needs: log in somewhere (the credentials are settings of the plugin, a `password` field), fetch information, serve pages or data to a device, pass on what the app needs. What is behind it does not matter:

- a device **in the car** or next to it (a small computer, an OBD adapter, ...),
- a **manufacturer app or cloud account** (a bridge that reads the brand's own app / online service),
- **any web service** with or without a login (weather, news, traffic, fuel prices, ...),
- **Home Assistant itself**: a plugin that looks for entities that already deliver this information (from an integration you have installed) and passes them on,
- or anything else that can make an HTTP request.

An *integration* never calls the Plugin API and has no token. It may ask a plugin for information (the plugin offers the interface); the plugin then asks the car, the web or whatever it connects to.

Reading comes first (position, doors, fuel / battery level, charging, tyres, messages, ...). Towards the car there is only one switch so far: **debug** (see the API page). Everything the pages show a car can do must come through this interface, so the demo cars play their whole life through it too.

## Flow, like in Home Assistant
1. **Upload** a package (or pick an optional one offered on the page). It is listed as *uploaded*.
2. **Set up** – fill in its settings. A plugin now gets its token (shown once).
3. When *set up* you can **change the settings**, **replace the token** or **remove** it (the token is revoked). You can also remove it before setting it up.

**Before anything is installed**, the page of the package (*Plugins → Add*, then its tile) says what the package does - read from its description, nothing of it runs: what it **sends** to the app, what it **reads** from the app, what it **offers** (routes of its service, pages, actions, a destination for the map) and what it **brings along** (files, data packages, a connection file, a token, settings it may change itself). A package that declares nothing says so. At the bottom there are two buttons: **Deny** (left) and **Allow** (bottom right); for a package with its own code or files, *Allow* also approves exactly what is listed. So declare `interfaces` completely (direction, name, path and the names of the fields): that is what a person reads before saying yes.

## The package
A `plugin.json`, or a `.zip` with a `plugin.json` at its root (max. 100 kB). Only this description is read and stored. **Nothing in a package is executed** – the plugin itself runs elsewhere and talks to the API. The one exception is a plugin with a [service](#plugins-with-a-service), which has to come from a source and be approved by an administrator.

```json
{
  "id": "my-plugin",
  "kind": "plugin",
  "name": "My plugin",
  "version": "1.0.0",
  "description": "What it reads from the car.",
  "author": "Your name",
  "homepage": "https://github.com/you/my-plugin",
  "settings": [
    {"key": "host", "label": "Address of the car module", "type": "text", "help": "optional help text"},
    {"key": "account_key", "label": "Key", "type": "password"},
    {"key": "verbose", "label": "Detailed log", "type": "bool"}
  ]
}
```
| Field | Rule |
|---|---|
| `id` | required; 2–41 characters: lower-case letters, digits, `-`, `_` |
| `kind` | `plugin` (default) or `integration` |
| `name`, `description`, `author`, `version` | text, shortened if too long |
| `homepage` | only `https://` links are kept |
| `settings` | up to 12 fields: `key` (`a-z0-9_`), `label`, `type` `text` / `password` / `bool`, optional `help` |

A package can be added once per car. Passwords are stored but never shown again; leaving a password field empty keeps the stored one. Settings are available to the plugin only through its own configuration – Car Assistant does not hand them out through the API.

## Writing a plugin
1. Read your car's values in your plugin (that part is specific to the car and stays in your plugin).
2. Map them to the standard fields of the [Plugin API](api.md) and send them with the plugin's token.
3. Describe it with a `plugin.json` and share it.

### Which way for which data
| You have | Send it as | Where it ends up |
|---|---|---|
| Standard values (mileage, tank, position, doors, tyres, AdBlue, oil, speed limit, messages, …) | `POST …/data` | Home, Security, widgets, notifications |
| Positions of a drive, many at once (gzip) | `POST …/track` | current position and speed; history readable through the API |
| Anything that has no standard field (flags, diagnostics) | `POST …/signals` | kept and shown on the plugin's *Logs* page, readable through the API |
| Entries of an integration page (for example control units for *Coding*) | `POST …/modules/<integration>/<page>` | the integration's page, with the same checks as the form |
| Debug lines | `POST …/logs` (only while debug is on, see `control`) | the plugin's own *Logs* page |
| What the dashboard asks of the plugin | read `control` in every answer or `GET …/control` | first switch: debug |
| Entries a person keeps in an integration (for example the station list) | `GET …/modules/<integration>/<page>` | read-only for the plugin |

What the app deliberately does **not** do: it fetches no news, traffic or weather for the car, it talks to no car by itself, and a plugin cannot create log book entries (refuels, services) - it delivers readings, people keep the book.

## Scenarios (demo plugins)

A plugin that is installed **from a source** may carry a `simulation` object in its `plugin.json`. Car Assistant then plays it while the plugin is switched on (*Start / Stop* on its card) and sends one report per `interval_s` seconds through the normal interface (`POST /api/v1/vehicles/<id>/data` with the plugin's token) - the same way a real plugin would. An uploaded package is never played.

```json
"simulation": {
  "interval_s": 5, "timelapse": 12,
  "places": [ { "name": "Home", "lat": 52.52, "lon": 13.405 }, { "name": "Office", "lat": 52.50, "lon": 13.438 } ],
  "cycle": [["parked", 3], ["enter", 1], ["start", 1], ["drive", 8], ["stop", 1], ["leave", 1]],
  "fuel": { "pct_per_km": 0.1, "km_per_pct": 10 },
  "electric": { "pct_per_km": 0.27, "km_per_pct": 5.2, "charge_below_pct": 40, "charge_step_pct": 9, "charge_limit_pct": 80, "charge_kw": 11 },
  "warnings": [ { "code": "washer_fluid", "text": "Washer fluid low" } ]
}
```

At least two `places`; everything is bounded and unknown keys are dropped. See the *Demo connector* in the [sources repository](https://github.com/Matze89x/ha-car-assistant-sources).

## Files of a package (downloads without a service)
A package may bring checked **binary files** that the app hands out itself - for example the program for the device in the car or a ready data package. No service has to run. The package stays readable; the binaries are only material to download and are **never executed**. Download only from sources you trust.

```
"files": [{"name": "carassistant.jar", "path": "assets/carassistant.jar", "label": "Program for the car", "note": "...",
           "sha256": "<checksum>", "size": 125840}],
"bundles": [{"name": "install.zip", "label": "Data package",
             "entries": [{"from": "scripts/custom.sh", "to": "mod/custom.sh"},
                         {"from": "assets/carassistant.jar", "to": "mod/carassistant/carassistant.jar"}]}],
"docs": "Get {file:carassistant.jar} and put it on the card."
```
- **`files`** (at most 10): allowed endings `.jar .zip .bin .json .txt .md .pdf` (a fixed list, nothing runnable), at most 8 MB each and 20 MB together. `sha256` and `size` are required, and the same checksum and size stand in the index (`plugins/index.json`, `"files": [{"name", "sha256", "size"}]`) next to the checksum of `package.zip`. When one file does not match, **nothing** is unpacked or offered.
- **Storage:** on install the files go, read-only, into a folder of the app (`plugin-files`) - apart from the code folder and closed to the service. They are not unpacked and not opened.
- **Delivery:** `GET /plugins/<id>/files/<name>` for **signed-in people** only, with `Content-Disposition: attachment`, the `Content-Type` of the ending and `Cache-Control: no-store`. It works while a service is stopped. When the plugin is removed, the files are deleted.
- **Approval:** the files are listed with their checksums on the approval page (the same one as for a service) and on the package page before installing; nothing is handed out before an **administrator approves** exactly this list. A new version with other files (or another service description) is approved with the *Update* you press, if you approved the package before.
- **`bundles`** (at most 5, up to 40 entries): a zip the app **builds on request** from files of the package - its text files (also `.sh`, as text; they are never run) and its `files`. Order, paths and the times are fixed, so the same package always gives the same bytes. The source of an entry is always a file of the package, never something from the net; paths without `..`. A bundle is offered like a file. **Exception: `connection_file_to`** (a path in the zip, only with a `connection_file` in the manifest): the app puts the connection file there, filled with the token of that run. Such a bundle is never offered as a plain download; it is built only in step 3 of the set-up guide (`setup` step `files`, listed in its `bundles`) for an administrator, after the token was compared with the stored fingerprint, with `Cache-Control: no-store`, and nothing of it is stored. The page warns that the zip holds the token like a password. Bundles without the key never contain the token. A bundle may carry `l10n` (`label`, `note` per language) like the settings; the guide shows only the label and note of the bundle, its list of entries only on the info page, and one token field for all such bundles (the single connection file is folded away behind *Load the file alone*).
- **Where it shows:** the group *Files* on the page *Info* and on the settings page of the plugin: button, name, size, short checksum, the note, and for a bundle what goes into it. In `docs`, `{file:carassistant.jar}` becomes a link to the file.
- **Build and check:** `tools/build_plugin_package.py` takes the files from `assets/`, fills `sha256` and `size` in `plugin.json` and writes the files into the index; `tools/check_plugin.py` checks them (sizes, checksums, index, bundle sources, `{file:...}`).
- **`hidden: true`** on a file: it is not offered as a download (`GET /plugins/<id>/files/<name>` answers 404), it is not listed on its own under *Files for the car* or on the page *Info*, and `{file:<name>}` in `docs` stays text. It stays on the approval page with name, size and checksum (marked *for the service only*), counts as approved like every file (changing `hidden` needs a new approval), may be an entry of a `bundle`, and is readable by a service with `"files": "read"` (see below). Anything but a yes / no refuses the package.
- **A service that reads the files of its package.** `"service": {"entry": "svc.py", "files": "read"}` gives the service the environment variable **`CA_FILES_DIR`**: a folder with exactly the `files` of the package under their `name`, **read-only** (the service cannot write or change them; every file is checked against its checksum and size when the copy is made). Typical use: a service that builds ONE zip from its own binaries (`hidden: true`) and the person's choices. The key is part of the approval - the approval page says *Reads the package files* with the list and checksums, and a new version that adds or removes the key is approved with the *Update* you press (if you approved the package before), otherwise it needs a new approval. Without the key the service does not see the files (they lie in a folder that is closed to it); any other value than `"read"` refuses the package.
- The rule "a package is readable (only text and plain images)" applies to everything except `files`.

## Value tiles on Home
A plugin or integration can put small **value tiles** on the Home page of the car, while it runs:
```
"tiles": [
  {"id": "cabin", "label": "Cabin", "icon": "weather-cloudy", "signal": "climate.temp", "unit": "°C", "decimals": 1},
  {"id": "speed", "label": "Speed", "data": "speed_kmh", "unit": "km/h", "l10n": {"de": {"label": "Tempo"}}},
  {"id": "service_days", "label": "Service in", "data": "service_due_days", "unit": "days", "l10n": {"de": {"label": "Service in", "unit": "Tage"}}}
]
```
A tile takes its value from a raw signal the plugin delivered (`signal`, see `POST …/signals`) **or** from a standard number of the Plugin API (`data`, for example `speed_kmh`). At most 8 tiles; `icon` is from [icons.md](icons.md); `unit` and `decimals` (0-3) are optional. `l10n` translates the `label` **and the `unit`** per language (the unit of a plugin's own translation wins); without a translated unit the app translates the time words it knows itself - `days`, `hours`, `minutes`, `weeks`, `months`, `years` (singular too) - into the language of the app (*Tage*, *Std.* ...), any other unit is shown as written. A tile shows only **while the plugin is running and a value exists**; the person can move, resize and hide it like any widget.

## The Interfaces page of a package
Every tile under *Manage* has the button **Info**, and its section **Interfaces** is one page that shows everything the package offers or uses - so anyone can see where an interface is reached and what another package could use. It has three groups (*Sends to Car Assistant*, *Reads from Car Assistant*, *Offers itself*) and the settings it reads. Each row is either **declared** by the package or **seen** (the package really used it: address, the **names** of the fields, how often, when last - never a value; this is noted always, not only in debug, and goes with the package when it is removed).

A package describes itself in its `plugin.json` (both keys optional):
```
"docs": "A longer text for the page (up to 3000 characters).",
"interfaces": [
  {"direction": "sends", "name": "Vehicle data", "path": "/api/v1/vehicles/<id>/data", "fields": ["odometer_km", "position"], "note": "every 2 minutes"},
  {"direction": "reads", "name": "Control", "path": "/api/v1/vehicles/<id>/control", "note": "debug switch and interval"},
  {"direction": "offers", "name": "News for the vehicle display", "path": "/car/news/", "note": "called by the car, no login"}
]
```
`direction` is `sends` (to the app), `reads` (from the app) or `offers` (an address, page or file the package provides). At most 40 entries. The page adds by itself: the routes of the service (with the full address), the pages of an integration (with their API address), the connection file and everything the package really used that it did not declare (marked *not declared by the package*).

**Who may use the interfaces?** Today only a **plugin** talks to the Plugin API (it has a token). An *integration* describes pages, reminders and widgets and has no token; it cannot call the API. Other packages can use what a package **offers** (its routes, its pages through `GET /api/v1/vehicles/<id>/modules/<integration>/<page>`) - the Interfaces page shows where.

## Credentials of a plugin
A plugin that logs in to a web service keeps the credentials in its settings (a `password` field: hidden in the page, blank = keep). The values lie in the database of the app, are handed to the plugin's service in `settings.json` and are part of a backup **only when it was made with a passphrase** ([backups](backup.md)): then they travel in its encrypted block and come back after a restore, also on another system. They are never shown, logged or put into the traffic view, and they are stored **encrypted** in the database (the key lies in `secret.key` in the data folder and is never part of a backup file). The access key of a source is stored the same way.

## Settings page

*Manage* shows each plugin as a tile with ONE line of buttons at the bottom: *Start / Stop*, *Info* (overview, interfaces, the log and the debug switch on one page) and *Settings*, and on the right the one main action: *Update* when a newer version is offered (the version stands as a badge in the head), otherwise *Open* for a plugin with a page. **Remembering the token (always on):** the token of every plugin is also kept **encrypted** (the key lies in `secret.key` in the data folder; a plugin with a service gets its copy at its next start), and the guide offers *Use the saved token* instead of asking again. It is shown only to an administrator - in that guide and on the tab *General* of the settings page - never in a log. A backup carries the kept token only when it was made with a passphrase ([backups](backup.md)), so it works after a restore on another system. The set-up guide (when the plugin brings one), *Show in the bar* and *Uninstall* are on the settings page. *Settings* opens a **page of its own** (Back leads to *Manage*) with everything the user can change: the fields from `settings` in the `plugin.json`, and the connection token (*New token*). Nothing is saved before *Save*; wrong entries are named and nothing is saved until they are fixed. It works like the settings of Home Assistant: you describe the options as JSON, the app turns them into switches, choices, sliders and so on.

| `type` | what the user sees | extra keys |
|---|---|---|
| `text` (default) | one line | `placeholder`, `unit`, `required` |
| `textarea` | several lines | `rows` (2-12), `placeholder`, `required` |
| `password` | hidden; blank = keep the saved secret | `required` |
| `number` | a number, checked against the bounds | `min`, `max`, `step`, `unit`, `required` |
| `slider` | a slider with its value shown | `min` (0), `max` (100), `step`, `unit` |
| `bool` | a switch, drawn by the app at the right end of its row (like on an iPhone; a plugin cannot place it elsewhere) | `default`: `true` / `false` (or the text `"1"` / `"0"`; it starts off without one) |
| `select` | a dropdown | `options`: `[{"value": "eco", "label": "Economy"}]` (at most 30; a value has no comma) |
| `radio` | choose one of a few, all visible | `options` |
| `multiselect` | tick any of a few (checkboxes) | `options`; stored as `a,b` |
| `list` | rows of a name and a value (for example news feeds and their addresses), add / remove, and put in order with the **handle on the left of each row** (drag it with the mouse or a finger, or press the arrow keys on it), at most 30; the service gets them in the order shown as `[{"name", "value"}]` | `name_label`, `value_label`, `value_max`, `columns`, `min_rows`, `templates`, `default` (see below) |
| `url` | a web address (http / https), checked | `required` |
| `email` | an e-mail address, checked | `required` |
| `time` | a time `HH:MM` | |
| `date` | a date `YYYY-MM-DD` | |
| `color` | a colour picker; stored as `#rrggbb` | |

**More on `list`.** `columns` (at most 3): more cells in a row than a name and a value - `[{"key": "second", "label": "Second line", "max": 80, "l10n": {"de": {"label": "Zweite Zeile"}}}, {"key": "logo", "label": "Logo address"}]`. `key` is a lower-case name (`a-z`, digits, `_`, at most 20 characters; not `name`, `value`, `label`, `l10n`, and not twice), `max` the length of the cell (1 to 500, default 120). `value_max` (1 to 500, default 200) sets the same for the `value` of the row (a long stream address); the name stays at 80. A text longer than its limit is **refused with a message and nothing is saved** - never cut quietly, because an address cut in the middle leads nowhere; the page itself stops typing at the limit. A column that cannot be used is left out; more than three are not read. The page shows the extra cells under the name and the value, in pairs. The service gets every row as `{"name", "value", "second", "logo"}` - every column a key of its own, an empty cell is `""`. Stored (and given to `{key}` in `env`) the row is one line `name | value | second | logo`; a `|` inside a cell is replaced by a blank. A list without `columns` stays as it was (name and a value that takes the rest of the line). `default` rows and `templates` may carry the same keys (`{"name": "Radio A", "value": "https://...", "second": "News"}`). `min_rows` counts a row as soon as one of its cells is filled. `min_rows` (1 to 30): saving with fewer rows is refused with a plain message and the last rows cannot be removed. `templates` (at most 30): `[{"label": "Comfort <-> Dynamic", "name": "ADS Comfort Dynamic", "value": "comfort_dynamic", "l10n": {"de": {"label": "..."}}}]` - the page shows a select of the ready-made rows and a button *Add* that appends the chosen row; after that it is an ordinary row, which the person can change, remove and put in order. `default` of a `list` may be the rows a new installation starts with: `[{"name": "...", "value": "..."}]` (at most 30; a `|` in a text is replaced by a blank). Apps that do not know these keys ignore them: the list stays an ordinary list. **Typed columns:** a column may say `"type": "number"` (a number input; the service gets a number, an empty cell is `null`, `3,5` is stored as `3.5`), `"date"` (a date input; stored and given as `YYYY-MM-DD`) or `"select"` (a choice with `"options": [{"value": "pro", "label": "Professional"}]`, like a choice setting, up to 12; without options it is a text). A cell that does not fit its type is refused with a message and nothing is saved. Without `type` a column is a text, as before. **`value_options`** (at most 30, optional): the `value` cell of the row becomes a choice - `[{"value": "comfort_dynamic", "label": "Comfort / Dynamic", "l10n": {"de": {"label": "Komfort / Dynamisch"}}}]` (the value has no comma and at most 40 characters). The stored row stays `name | value | ...`, the service gets `value` as text, exactly as before; an app that does not know the key shows an ordinary text field. **Old values are kept.** A stored cell that does not fit its column any more (an old text in a `select` or in a `value_options` choice, an old text in a `date` or `number` column) is shown as it is, marked *old value* with a short note, and stays stored when the settings are saved unchanged; it is never emptied or dropped quietly. A **new** entry that does not fit is refused as before.

**`docs` and its translation.** `docs` (3000 characters) keeps its paragraphs: lines are tidied, at most one empty line in a row, line breaks stay and are shown. `l10n.<language>.docs` is the same text in another language and is shown instead of `docs` when the page has that language.

**Lengths of texts - longer ones are cut without a message in the app.** `label` 60 characters (the label of a tab 40), `help` 300 (in the fields of a page, `pages[].fields`: 200), all of them also in `l10n.<language>`; line breaks become spaces. `tools/check_plugin.py` warns about a text that would be cut - a help text that ends in the middle of a sentence has been cut.
| `section` | a heading (with `help` as text) that groups the fields below it | |
| `tab` | a tab of the settings page: `id` (lower case, `_`), `label`, optional `icon` (an app icon) and `l10n`. Every setting after it belongs to this tab, until the next `tab`; settings before the first `tab` form the tab *General*. Without `tab` (or with only one) the page stays one list. Everything around the settings (set-up guide, files, the token and the connection file, uninstall) sits under the first tab. A tab holds no value, `show_if`, `advanced` and the key of each setting work as before The first tab is always called *General* on the page, whatever its `label` says (see [The tab General](#when-things-show-and-the-tab-general)). | `id`, `label`, `icon` |
| `info` | a text only (`label` bold, `help` as text), nothing stored | |

Every field has `key` (lower case, `_`), `label` and an optional `help` text (shown under the field), `default` and `l10n` (translated `label` / `help`). `section`, `info` and `tab` need no `key`. At most 40 fields and 12 tabs (tabs do not count as fields).

**Conditions:** `"show_if": {"key": "mode", "equals": "custom"}` shows a field only while another setting has that value (for a switch: `"equals": true`). A hidden field is not checked and not demanded. Example:
```
{"key": "mode", "type": "radio", "label": "Mode", "options": [{"value": "auto", "label": "Automatic"}, {"value": "custom", "label": "Custom"}], "default": "auto"},
{"key": "address", "type": "url", "label": "Address", "required": true, "show_if": {"key": "mode", "equals": "custom"}}
```
More than one setting, and more than "is equal": a single test is `{"key": ..., <one of these>}` -

| Test | The field is shown while ... |
|---|---|
| `"equals": "x"` | the setting is exactly `x` (a switch: `true` / `false`) |
| `"not": "x"` | the setting is anything but `x` (an empty choice counts) |
| `"in": ["a", "b"]` | the setting is one of these values (up to 12) |
| `"not_in": ["a", "b"]` | the setting is none of them |
| `"has": "x"` | the box `x` of a `multiselect` is ticked |

Tests are put together with `{"any": [...]}` (one of them is enough) and `{"all": [...]}` (every one); a plain list means `all`. They nest (three levels, eight tests at most):
```
"show_if": {"any": [{"key": "advanced", "equals": true},
                    {"all": [{"key": "mode", "in": ["custom", "expert"]}, {"key": "features", "has": "map"}]}]}
```
A condition that cannot be used (a wrong key, an empty list, too many tests) is dropped: the setting is then simply always shown, and `tools/check_plugin.py` tells you. A test of a setting that does not exist counts as true, so a typo never hides a field. Packages that only use `equals` need no change.

**What a service gets** in `settings.json` (see below): numbers and sliders as numbers, switches as `true` / `false`, a `multiselect` as a list of the ticked values, a `list` as `[{"name": ..., "value": ...}]`, everything else as text. In the connection file all values are text (a switch is `1` / `0`).

## Connection file

On the settings page of a plugin with a connection file there are two ways to get the file: **New token** (makes a new token and gives the file) and **I already have the token** (type the token you got before; the app compares it with the fingerprint it keeps and, when it matches, gives the file again with that token - no new token, the device keeps working). The token is never shown or logged, only an administrator may do it, and five wrong tries in 15 minutes stop further guessing.

A device in the car often needs a small file with the address, the vehicle and the token. The manifest can describe it, and Car Assistant offers it for download **when the token is shown** (set-up or *New token*; the token is stored only as a fingerprint, so this is the one moment it can go into a file):

```json
"connection_file": { "name": "link.cfg", "template": "server={server}\nvehicle={vehicle}\ntoken={token}\ninterval={interval}\n" }
```
`{token}`, `{vehicle}` (the id used in `/api/v1/vehicles/<id>`), `{url}` (the external address, if one is set) and every setting of the plugin by its `key`. A line whose value is empty is left out, so an optional setting never writes `key=`. Fill in the settings first: they go into the file. The file name may contain letters, digits, `.`, `_`, `-`; the template is at most 2000 characters. Nothing is executed or stored.

`{vin}` is the VIN typed into the vehicle data of the car (a setting of the same name loses against it); a line without a value is left out. A **service** finds the same two values in `settings.json` as fixed keys: `external_url` (the external address, or `""`) and `vehicle_vin` (or `""`), read when the service starts - so the plugin never has to ask for them again.

### Set-up guide (`setup`)

**Its name (optional):** `"setup": {"title": "Install & uninstall on the car", "l10n": {"de": {"title": "Am Auto installieren & deinstallieren"}}}` names the guide for its button on the tile, the card on the settings page and the heading of the guide. Without `title` the app's own word stays: *Set up* in all three places (the same word on the button, the card and the heading), which is also the recommendation: `"title": "Set up"` and `l10n.de.title` *Einrichten*. At most 60 characters.

A plugin with a connection file can bring a guide that Car Assistant shows in **three fixed steps** (on its card under *More*: *Set up*; it can be gone through again at any time):

```json
"setup": {
  "requires": ["external_https", "vehicle_vin"],
  "steps": [
    {"id": "token", "text": "Short text above the token."},
    {"id": "files", "bundles": ["install.zip", "uninstall.zip"], "text": "1. Put the card in ...\n2. Unpack the ZIP into the main folder\n3. Put the file into [the folder](https://example.com/notes)",
     "l10n": {"de": {"text": "1. Karte einlegen ...\n2. ZIP in den Hauptordner entpacken"}}}
  ]
}
```

**Choosing the settings of the guide (optional).** A step may list the settings it shows: `{"id": "token", "settings": ["server", "interval"]}`. As soon as **any** step lists settings, the guide shows **only** the listed ones (in the order of `settings`; `advanced` ones stay folded) and every other setting keeps its stored or default value when the person presses *Next* - a switch that is not in the page is not switched off. The other settings stay on the normal settings page. Unknown keys are ignored. Without `settings` in any step nothing changes: the guide shows all settings, as before.

1. **Check.** The guide shows the external address (saved under *Settings -> System*, `https://`) and the VIN (typed into the vehicle data) read-only, with a link to where they are set. *Next* stays shut until everything listed in `requires` (`external_https`, `vehicle_vin`) is there.
2. **Token and settings.** The token: *Make a new token* (shown once) or - when the app has none yet - *Use an existing token* (a token that is already in the file on the device: it must look like a Car Assistant token, may not be in use elsewhere, and is stored only as a fingerprint); when one exists, the mark of the stored token and *Keep using the existing token* (type it; it is compared with the stored fingerprint, never stored). Below, the plugin's settings; those with `"advanced": true` are folded under *Advanced settings*. *Next* saves the settings.
3. **Files and instructions.** The connection file (named in `connection_file`) for the token of step 2 - for a token kept from before the guide asks for it once more - and the `bundles` named in the step `files` (while the package is approved), then the instructions (`text` of the step `files`). *Finish* ends it.

A step brings an optional `text` (up to 3000 characters; the steps `check`, `token` and `files` are the ones the guide knows) and `l10n` per step (`title`, `text`). The text is plain text with `1. ` / `- ` lists, `**bold**` and `[label](https://...)` links (https only); everything else is shown as typed. The `note` of a bundle says what it does (for example that it saves the old state first).

**Beginner-friendly steps 2 and 3.** Step 2 shows three boxes with a choice on top (exactly one is chosen): *Use the saved token* (only when the app holds a decryptable saved copy; preselected), *Make a new token* (left; the old one becomes invalid; asked again at *Next* when one exists) and *Keep using the existing token* (right; type the one in the file on the device - Car Assistant does not have to know it beforehand, only its fingerprint is kept). *Next* does the chosen action and goes to step 3. With `"settings": []` on the step the settings block (heading and hint) is left out completely. Step 3 shows the plugin's `bundles` as equal boxes (name, `note`, size, one download button); the single connection-file download appears only when the plugin has **no** bundle with `connection_file_to`, because that file is already inside the bundle.

### Freedom for the plugin: its own steps, settings and values
Everything below is **optional** and only an addition; the security stays with the app (address and VIN check, the token, the connection file, packages, the administrator's approval).

- **Steps with a page.** A step of `setup.steps` may carry `"page": "<id of a frame page of the package>"` (and a `title`, `text`): after the three fixed steps the guide shows it as a further step with a button that opens that page of the plugin's own service, and *Next* / *Back* around it. Only a `kind: "frame"` page of the same package can be named (the same safeguards as for every frame page); an unknown id is dropped.
- **Own settings page.** `"settings_page": "<id of a frame page>"` names a page of the service as the plugin's settings page: the settings page of the plugin gets a main button to it. The field list stays as the fallback.
- **Field type `value`.** `{"key": "status", "label": "Status", "type": "value"}` shows a value that the person cannot edit, only the plugin's service sets (for example *Running until 14:20*). Two optional looks: `"format": "datetime"` (or `"date"`) writes a time the service stored as ISO text (`2026-11-22T10:20:00+00:00`, UTC when it has no zone) in the system's time zone and writing; `"state": {"ok": ["connected"], "warn": ["waiting"], "bad": ["error", "lost"]}` puts a green, amber or red dot in front of exactly these texts (up to 8 per level; the text itself still says the same).
- **The service changes its own settings.** A setting marked `"service_writable": true` (not for lists and multiple choice) and every `value` field may be changed by the service itself:
  - `GET /api/v1/vehicles/<id>/plugin-settings` with the plugin's token -> `{"ok": true, "settings": {...typed...}, "writable": [...]}`. A password is never readable (`"***"` when set).
  - `PUT /api/v1/vehicles/<id>/plugin-settings` with `{"values": {"mode": "eco", "interval": 30, "status": "Running until 14:20"}}` -> `{"ok": true, "changed": [...]}`. Only writable keys (`403 not_writable` otherwise), checked like the form (`422 invalid_value` with the keys that are wrong - nothing is stored then; numbers are held to their bounds), at most 30 calls a minute (`429`).
  - **The list of writable keys belongs to what the administrator approves:** a new version that changes it needs a new approval. A change is noted in the plugin's log (the names of the keys, never the values).
- `GET /api/v1` lists `features` (`measured_at`, `plugin-settings`) so a plugin can check before it uses them.

### The set-up flow (`setup.flow`)
The three fixed steps above suit a plugin with a token and a connection file. A plugin that has to **log in somewhere, ask for details, check them and hand out something at the end** (a ZIP, say) needs more freedom - and gets it with a **flow**: *you* decide the steps, their order and their texts. A package without `flow` keeps the three fixed steps exactly as before; with a `flow` the flow takes their place (`steps` may stay for older apps).

```json
"setup": { "title": "Connect the account", "flow": [
  { "id": "intro",  "type": "text", "title": "Welcome", "text": "Log in with the account you use in the car app." },
  { "id": "login",  "type": "check", "action": "/priv/login", "settings": ["user", "password"], "label": "Check the login",
    "l10n": { "de": { "label": "Anmeldung prüfen" } } },
  { "id": "needs",  "type": "requirements", "requires": ["external_https"], "filled": ["user"] },
  { "id": "pack",   "type": "download", "action": "/priv/zip", "label": "Create the install ZIP" },
  { "id": "docs",   "type": "page", "page": "docs" }
] }
```
Every step has `id` (`a-z0-9_`), `type`, `title` (80 characters; without it the app names the type), `text` (3000; paragraphs, lists, `**bold**`, https links) and `l10n` (`title`, `text`, `label` per language); up to **12 steps**. The page shows numbered steps with *Back* and *Next*; the last step ends with *Finish* and the plugin then counts as **set up** (the *Set up* button of its tile goes away). A step that does not fit its type is dropped when the package is read.

| `type` | What the person sees / what happens | Fields |
|---|---|---|
| `text` | only the text | - |
| `requirements` | a list of what must be there; **nothing behind this step opens until everything is met** | `requires` (`external_https`, `vehicle_vin`: checked by the app), `filled` (settings that need a value) |
| `form` | the listed settings as fields (a user name and a password are just settings of the type `text` / `password`); *Next* saves them | `settings` |
| `check` | the fields (optional), then the main button: **the app asks the plugin's service** to check them | `action`, `settings`, `label` |
| `token` | *Make a new token* (shown once; the old one becomes invalid) - the token is **one option, not a must** | - |
| `files` | the plugin's `bundles` and its connection file, as step 3 of the fixed guide | `bundles`, `connection_file` |
| `page` | a button that opens a `kind: "frame"` page of the plugin (freely designed: documentation, a wizard of its own ...) | `page` |
| `download` | the main button: **the service makes a file** (a ZIP made for exactly this person's input) and the person downloads it | `action`, `settings`, `label` |

**`check`** - `POST <action>` (a route of the plugin's own service that is **not** public, the same rule as for `capabilities`) with `{"vehicle": 3, "step": "login", "language": "en", "values": {"user": "max", "password": "..."}, "settings": {...all settings, with what was just typed...}}` and the identity headers. The service answers within 10 seconds: **2xx** (or `{"ok": true}`) = fine, anything else or `{"ok": false, "message": "Wrong password."}` = the person stays on the step and reads `message` (200 characters at most). **Nothing the person typed is stored when the check fails.** On success the typed settings are stored (passwords sealed), and the answer may carry `"settings": {"status": "Connected", "token": "..."}`: the keys the service may write itself (`service_writable` / `value`, see above) are stored - a refused key counts as a failed check. `message` of a success is shown on the next step ("Logged in as Max.").

**`download`** - the same request; the service answers with the **file**: at most **8 MB**, 30 seconds; `Content-Type` `application/zip`, `application/octet-stream`, `text/plain`, `text/csv` or `application/json` (anything else is handed out as `application/octet-stream` - never as a page), a name in `Content-Disposition` (cleaned to letters, digits, `.`, `_`, `-`). An error answer (`{"ok": false, "message": "..."}`) is shown on the step. Because the service builds the file, it can contain anything the person typed - and the token the service itself holds. The app stores nothing of it.

Both types need a **running, approved** service; the step says so when it is not. A password typed in a step is only ever sent to the plugin's own service (which reads the same settings anyway). The token of a `token` step travels from step to step inside the page only (never stored), exactly as in the fixed guide.

## Plugins with a service
Some plugins need a program of their own, for example to serve pages or data to a device in the car. They can bring one as a **service**. It runs **inside this add-on** (never in a second container): you install the plugin and that is all.

**This is foreign code.** Only approve a service from a source you trust, and read what it does first. The app protects you as far as it can:
- It must come from a **source**, never from an uploaded file. The index of the source names the **sha256** of `package.zip`; a file that does not match is not unpacked.
- A package is **readable**: only text files (`.py`, `.json`, `.md`, ...) and plain images. No binaries, no compiled code, no links. The folder lies open on GitHub; the approval page lists every file.
- Nothing runs before an **administrator approves** it on a page that shows the source, the checksum, the program, the Python packages it needs, the addresses it answers and the settings it receives. A package you allowed when installing it stays allowed when **you press *Update***: the new description is approved with that click (the page still shows it). Nothing is updated on its own, and a package you never approved stays unapproved after an update. Taking the approval back stops it.
- It runs as **its own process** in **its own virtual environment**, as **its own unprivileged user** (when the add-on runs as root), with limits for memory (768 MB), open files and processes. It may write only to its own folder `/data/plugins/<id>/<car>/`.
- Its environment holds only what is listed below - **never** the Home Assistant (Supervisor) token and never the database. The database and all other data of the app are closed to it.
- It reaches the app only through the normal [Plugin API](api.md) with a token of its own.
- Its output is kept only while **debug** is on for the car (the plugin's *Logs* page).
- *Start / Stop* on the plugin card starts and stops it; a crash restarts it with a growing pause (5 s ... 2 min). Removing the plugin stops it and deletes its data folder, its environment and - when no other car uses the package - its code.

The python packages it needs (`requirements`) are installed **once, when you approve**, from the Python package index (the only time this goes online; only ready-made wheels, nothing is built). A package may not carry its own wheels or binaries.

### The package
In the source: the **readable folder** `plugins/<id>/` with `plugin.json` and the service files, plus a `package.zip` built from it, and the `sha256` of that zip in `plugins/index.json`:
```
plugins/echo-service/plugin.json
plugins/echo-service/service/main.py
plugins/echo-service/package.zip      <- built by tools/build_plugin_package.py
plugins/index.json                    <- {"packages": [{"id": "echo-service", ..., "sha256": "..."}]}
```
`tools/build_plugin_package.py <source folder> <id>` builds the zip the same way every time and writes the checksum into the index. A working example is in [`docs/examples/echo-service/`](examples/echo-service/).

`plugin.json` gets an optional `service`:
```
"service": {
  "entry": "service/main.py",
  "python": ">=3.9",
  "requirements": ["fastapi", "uvicorn"],
  "routes": [{"prefix": "/svc/", "public": true}],
  "env": {"GREETING": "{greeting}"}
}
```
- `files` - optional, `"read"` = the service may **read** the files of its package (`CA_FILES_DIR`, see *Files* above); anything else refuses the package.
- `token` - optional, `false` = this service has **no token** and no Plugin API (see *A service without a token* below); `true` is the default and may be left out. Anything but a yes / no refuses the package.
- `entry` - the program (a `.py` file of the package). `python` - the lowest Python version (`>=3.x`). `requirements` - names with optional versions, at most 30; no links, no options.
- `routes` - addresses the service answers on **this app's address** (`https://<your address>/svc/...`). `public: true` = reachable **without a login** (the car sends none); `false` = only from Home Assistant. A prefix starts and ends with `/`, may not cover a page of the app (`/api/`, `/v/`, `/static/`, ...) and may not overlap another plugin's prefix. The check is made again whenever the service starts: a page that a later version of the app takes is never shadowed by a service - the app wins, and the route is simply not handed on. The app passes the request on **unchanged** (method, query, headers, body - also an empty one without a length and `multipart/*` - and the answer's status and content type), except cookies and authorization, which never cross. Limits: 8 MB request, 16 MB answer, 30 s.
- `routes[].token_header` - optional, only on a `public: true` route: a header name (`X-My-Token`, letters, digits and `-`; not `Authorization`, `Cookie`, `Content-*`, `X-CA-*` and the like). The app then checks that header against the **token of the plugin** *before* the service sees anything and answers `401` itself when it is missing or wrong (compared by fingerprint, in constant time; a plugin without a token passes nothing). The check uses only the fingerprint of the token; the service still receives the header unchanged and may check it again. Only the header you name counts (not `Authorization`: that one never crosses). The approval page shows *only with the plugin's token in the header X-My-Token* next to the route. A manifest with a `token_header` that cannot be used (a non-public route, a forbidden or malformed name) is refused when it is read - a hardening that is dropped silently would leave the route open. Older versions of the app ignore the key, so keep your own check in the service as well. Use it for the requests of a car, which has no login and cannot send `Authorization`. A plugin may declare several public routes, some with and some without `token_header` (for example `/webradio/` with it and `/webradio-open/` or a health route without it); where prefixes lie inside each other, the longest one decides. The app notes refused requests in the plugin's log as one warning a minute, with the number of refusals since the last line (nothing about the sender, no value); with debug on, each one is in the traffic view too. It adds no pause for repeated failures: the token has 256 bits, so guessing it is hopeless.
- `downloads` (a key of `plugin.json`, not of `service`) - files the service offers: `[{"label": "Data package", "path": "/svc/pack.zip", "note": "..."}]`, at most 10; the path must lie under one of the routes. `place` is `tile` (default: a button on the plugin's tile under *Manage*, only while the plugin runs; keep it to one or two - the log of the car, for example) or `settings` (a button in the card *Files for the car* of the tab *General* of the settings page); on the info page there is none. `when` (see *Conditions*) says when the button shows. `l10n` brings `label` and `note` in other languages (`{"de": {"label": "Datenpaket"}}`); a missing translation shows the original. Connection file, files and bundles are handed out by the set-up guide and the card *Files for the car*; the service serves the file (binary, `Content-Disposition` passes through, at most 16 MB). A public route is open to anyone, a non-public one only from Home Assistant or for a signed-in person.
- `connects` - optional: the hosts the service says it talks to (`api.example.com`, `*.cloud.example.org`, at most 10), shown on the approval page. It is a statement for the person who approves; the app does not block other addresses. A change needs a new approval.
- `env` - additional environment variables; `{key}` becomes the value of that plugin setting. Names starting with `CA_`, `PYTHON`, `LD_` and a few system names are not allowed.

### Watching what happens
Two things show on the *Logs* page of each plugin (*Info* on its tile, section *Log*):
- **What the add-on does with the service** (install, pip errors, start, stop, crash with the exit code and the pause before the next start, approval) - always, whether or not debug is on. After a crash the last output lines are added while debug is on.
- **Traffic**, only while debug is on: every call of the plugin to the Plugin API and every request from outside on a route of its service, with time, status, address, size, duration and the **names** of the fields (never their values). Its output and your own `print` lines are kept as log lines while debug is on.

### Logs and the debug button of a plugin
Every tile under *Manage* (also a stopped one) has a **Logs** button, and the settings of every plugin (the tab *General*, fixed for all of them) have the card **Log**:
- **Logs** opens the plugin's own page (`/v/<car>/integrations/<id>/logs`): only ITS log lines - *All* or only *Problems* (warnings and errors, with their number) -, what the add-on did with its service, and the traffic (folded), with *Clear* and *Download as text* (`logs.txt`, the last 1000 lines, to read offline or to send along with a bug report). This is the place to look first when something does not work.
- **Log** (settings, tab *General*) switches more detail on **for this plugin only**, for **1, 3 or 7 days** counted from the moment you switch it on: while it is on, the plugin is told (`control.debug` is `true`, so it sends its log lines), its calls are noted in the traffic view and the output of its service is kept. When the time has run out the switch goes off by itself; choosing another time starts it again; removing or installing the plugin again also switches it off. The switch for the whole car on the *Debug & log* page does the same for every plugin of the car.

Logs are kept for 7 days and at most a fixed number of lines per plugin - **every plugin has its own log**: its lines, its watched calls and what it used belong to it alone, are cut down for it alone and never push out those of another plugin; older lines are removed by themselves. Removing a plugin deletes its lines, its calls and its connection-map history - and nothing of any other plugin.

### What the service gets
**Token:** a plugin with a service and **no** `connection_file` gets a token of its own from the add-on (`CA_API_TOKEN`). A plugin with a service **and** a `connection_file` has **one** token: it is shown once on setup (for the file the car needs; *I already have the token* and *New token* work as for any plugin) and the same token is given to the service - a new token reaches the service by itself and restarts it.

Environment variables: `CA_PORT` (listen on `127.0.0.1:<port>`), `CA_API_URL` and `CA_API_TOKEN` (Plugin API and a token of its own), `CA_VEHICLE_ID`, `CA_DATA_DIR` (its folder; `settings.json` with the plugin's settings lies there, rewritten when you save the settings - the service is restarted then). Nothing else of the app.

### A page of the service as a page of its own (`kind: "frame"`)
A package with a service can show a page of its own service as a **page of its own** - a whole tool with its own code. It works for an **integration** with a service (the usual case for a tool such as an editor: no token, no `CA_API_URL` / `CA_API_TOKEN`, no Plugin API - only `CA_PORT`, `CA_DATA_DIR`, `CA_VEHICLE_ID` and its settings) and for a plugin with a service. The service needs the same approval in both cases.

```json
"pages": [{ "id": "editor", "kind": "frame", "title": "Editor", "route": "/ext/editor/", "icon": "settings",
            "l10n": { "de": { "title": "Editor" } } }]
```
- `route` must lie under a **non-public** `routes` prefix of the same package's service (`public: false`); any other address is refused when the package is read. Without a service there is no frame page.
- With `"nav": true` (the default) the package has its entry in *More* of every car where it is installed (under *Integrations* or *Plugins*, by its `kind`) **and its service runs**. Stopped = entry and page are gone. The entry opens the `route`.
- **Which page opens first:** *Open* on the tile of the package opens the **first page** of `pages` (`pages[0]`); this is a promise, put the page that should open first at the top of the list.
- **No iframe, no app navigation:** the service's page is the whole window. Car Assistant only puts a **head** on top of the HTML the service sends: a back button (to *More* of the car), the name of the package and, at the right, its `version`. The head is plain HTML plus a style sheet, no script, its variables are scoped so they never touch your page; it is not fixed - it scrolls away with the page. It is added only when the page is opened as a page (a navigation), not to a `fetch`, an `iframe` or an answer that is not HTML. Your page should be a normal HTML document with a `<body>`. The content of your page is yours, including its own `Content-Security-Policy`.
- **Approval:** the approval page says *This package shows a page of its own, with its own code, inside the app.* The `route` is part of what is approved; an update you press keeps the approval.

**What the page gets** (parameters on its address): `lang` (e.g. `de`), `car` (the car's id), `units` (`metric`, `us`, `uk`), `theme` (the design of this car) and ready-made addresses that already contain the app's path - use them as they are: `css`, `kit` (design, see below) and `tiles` (map tiles).

**What the service gets** from the proxy for such a route (never the app's cookies): `X-CA-Vehicle` (the car's id, only if the car exists) and `X-CA-User` (the id of the signed-in person - no name -, or `ha` inside Home Assistant). What a caller sends under these names is dropped. A request that **changes** something (POST / PUT / PATCH / DELETE) must carry `X-Requested-With: frame`, otherwise the proxy answers `403` (protection against foreign sites). Limits: a request body up to **8 MB** (small uploads work), an answer up to **16 MB**, **30 seconds** per request. Only signed-in people reach the page, never the public.

**Design:** the page matches the car's design if it links what the app hands out:
- `css` = `/frame-theme.css?theme=<design>`: only the design variables (`--accent`, `--bg`, `--ok`, glass values, radii ...) and `color-scheme` of the chosen design, also of your own theme file. The list that is promised is in the [design contract](design-contract.md).
- `kit` = `/frame-kit.css?theme=<design>`: those variables **plus** a small kit (`.card`, `.grid`, fields, `button` / `.primary` / `.danger`, `.icon-btn`, `.chip`, `.badge`, tables, fonts and the same fixed building blocks as the app: the section label `.label`, the notice tile `.notice` with `.ok` / `.warn` / `.err`, the tab bar `.seg-tabs` and the round symbol switch `.seg-icons`; put your own SVG symbol in front of the text; `.on` marks the active tab) built only from them. Use the classes and the page looks like the app in every design. The body is transparent; give the page `html { background: var(--bg) }` yourself (the head sets a background for `html`, your own style wins).

**Maps:** the app has its own tile address for OpenStreetMap, `tiles` + `/{z}/{x}/{y}.png`, the same one the location map and the trip maps use: same origin, only for signed-in people, cached, and only while the person switched maps on (*Settings → System*, off by default - then it answers `404`). Bring your own map script (for example Leaflet) and point its tile layer there; nothing is loaded from the internet by your page.

**Rule:** an integration may carry a service only for a page of its own inside the app (a tool in the add-on); to connect a device or a car it stays a plugin.

## The tile of a plugin and its buttons (`buttons`)
Every plugin has a **tile** under *Plugins → Manage* with ONE line of buttons at the bottom, always in this order:

| Button | What it is |
|---|---|
| **Uninstall** (a bin, no text) | removes the plugin after a confirmation (its token is revoked) |
| **Logs** | the plugin's own log page (see [Logs and the debug button](#logs-and-the-debug-button-of-a-plugin)) |
| **Settings** | the plugin's settings page |
| *your own buttons* | up to **three**, see below |
| *downloads* | every entry of `downloads` (a log, a data package) while the plugin runs and its service is approved |
| **the main button** (right, red) | what is to be done next: *Review and approve*, *Update*, *Set up* (while the plugin has a `setup` that is not finished) or *Open* |

**Before the approval of the service** nothing that needs it is offered: buttons with an `action` (they call the service), buttons that open a `frame` page (the service serves it) and the `downloads`. A button that opens a step of the set-up or a page of the app itself stays, and so does the way to the approval (*Review and approve*).

The tile decides by its own width, not the window's: while there is room the buttons carry their words, then only their symbols (the name stays in `aria-label` / `title`), and with two or more extra buttons (own buttons plus downloads) on the smallest tile the main button becomes a symbol, too; a long name of the main button is shortened with "...". Nothing is ever cut off at the edge of the tile. Only a plugin with **three or more extra buttons** takes a second line on a phone - keep to one or two downloads and use the own buttons for what matters.

**Your own buttons.** A package may list up to three buttons of its own (`buttons`). A button either **opens a page** of the package or **triggers an action** of its service and shows the answer:

```json
"pages": [{ "id": "docs", "kind": "frame", "title": "Documentation", "route": "/priv/docs/" }],
"buttons": [
  { "id": "docs", "label": "Documentation", "icon": "file-document-outline", "page": "docs" },
  { "id": "wake", "label": "Wake the car", "icon": "power", "action": "/priv/wake",
    "confirm": "Wake the car now?", "l10n": { "de": { "label": "Auto wecken", "confirm": "Auto jetzt wecken?" } } }
]
```
- `id` (`a-z0-9_-`, unique), `label` (up to 40 characters), `icon` (one of the app's symbols; unknown names show a round *play* symbol) and **exactly one of**:
  - `page`: the `id` of a `kind: "frame"` page of the same package. The button opens it like the *Open* entry does - the page is **freely designed by the plugin** (documentation, a form that collects data, a view that reads information from the service, ...). It can use the app's design kit (`kit`, see above).
  - `action`: a route of the plugin's own service that lies under a **non-public** `routes` prefix (the same rule as for `capabilities`). A press sends `POST <action>` with `{"vehicle": <id>, "button": "<id>", "language": "en"}` and the two identity headers (`X-CA-Vehicle`, `X-CA-User`) and shows a result page: **2xx** (optionally `{"ok": true, "message": "text for the person"}`) = done, anything else or `{"ok": false, "message": "why"}` = the reason, taken from `message` / `error` (200 characters at most). The service has 10 seconds. A plugin that is not running or not approved is never called; the result page says so.
- `confirm` (optional, `action` only): a question the person has to confirm first.
- `l10n`: `label` and `confirm` per language.
- Buttons are shown while the plugin is switched on; only people who may manage packages can press them. A button that does not fit these rules is dropped when the package is read (no error), and more than three are cut off - put everything else on one of your own pages, which can link anywhere. Buttons that are rarely used can stand in the tab *General* of the settings page instead (`place`), and `when` decides when a button shows: see [When things show, and the tab General](#when-things-show-and-the-tab-general).

Like everything in the interface this is an addition: a package without `buttons` has the same tile with *Uninstall*, *Logs* and *Settings*.

## When things show, and the tab *General*

**`place`.** Buttons (`buttons`) and service downloads (`downloads`) stand on the tile by default, and the tile has room for ONE line. What is used rarely belongs into the tab *General* of the settings page instead: `"place": "settings"` (up to **six** buttons; for downloads the same limit as before). Log out, change the login, delete the data, a full export - none of them takes room on the tile.

**`when`.** A button or a download shows only while its condition holds - on the tile and on the settings page. A condition is ONE test or a list of up to five (all must hold):

| test | holds when |
|---|---|
| `{"setup": "done"}` / `{"setup": "open"}` | the set-up is done (see below) / still open |
| `{"token": true}` / `{"token": false}` | the plugin has a token / has none |
| `{"key": "account", "set": true}` | the setting is filled in (a switch: on); `"set": false` = empty (a switch: off) |
| `{"key": "mode", "equals": "eco"}` | the setting has exactly this value (a switch: `true` / `false`) |
| `{"downloaded": true}` / `{"downloaded": "install.zip"}` | the app has handed out a package or file of this plugin for this car (any, or that one); `false` = none yet |

Typical: *Log out* with `"when": {"key": "account", "set": true}` and *Log in* with `"set": false` - the plugin makes `account` a `value` field and writes it after the login (`PUT .../plugin-settings`). A `when` that cannot be read (unknown key, wrong shape) makes the app **drop the button** - it is never shown instead. A hidden action button is not run either (the page says it is not available right now).

**When the set-up counts as done (`setup.done_when`).** Without it the set-up is done when the guide or the flow has ended. `done_when` is a `when` (the tests `token` and `key`, not `setup`) that must hold **in addition**: `"done_when": [{"token": true}, {"key": "status", "equals": "connected"}]`. While the set-up is not done, the main button of the tile is the set-up (named by `setup.title`, per language in `setup.l10n`); as soon as it is done the button is gone; when a condition stops holding later (the login fails) it comes back. `"settings_after": true` (only with a `flow`) hides the *Settings* button of the tile until the set-up is done. A `done_when` that cannot be read is ignored: the set-up then counts as done at the end of the guide, as before.

**The tab *General*.** On a settings page with tabs the first tab is ALWAYS called *General* - the `label` the package gave it is not used (its `id` stays, a link to it keeps working). It is the home of everything around the settings, from top to bottom: the set-up guide, **Actions** (the buttons with `place: "settings"` that show right now), the settings of the first tab, the connection token (readable for administrators), **Files for the car** (the `files`, the `bundles` and the downloads with `place: "settings"`), the entry in the bar and *Uninstall*. Without tabs it is one page with the same cards: one page for a few settings, tabs when there are many.

**Versions of files.** A `files` or `bundles` entry may carry `version` (what the plugin offers; up to 20 characters: letters, digits, `.`, `_`, `+`, `-`) and `installed` (the `key` of a `value` setting - or one marked `service_writable` - in which the plugin reports what lies on the car). The app shows *Ready 1.4* and *On the car 1.2* and a mark: *Update ready*, *Up to date* or *The car has a newer one*; numbers are compared as numbers (1.10 is newer than 1.9); what stands before the first digit does not matter (`v8` = `V8` = `Build 7` is 8 / 7; `V1.23` = `1.23`). A `version` may contain single spaces (`Build 7`), up to 20 characters. Without `installed` only the version is shown. The version is not part of what an administrator approves. The card also says **when it was last handed out** (*Last downloaded 3 · 24.11.2026 14:03*; for a plugin that cannot report what lies on the car, the next version is compared with that) and, for a package that carries the connection file, **whether the settings changed since** (*Settings changed since - download again*). A bundle with the connection file (`connection_file_to`) is made right on the card when the file holds no token or when the app keeps the token (it keeps that of every plugin, encrypted); otherwise the set-up guide makes it and the card says so.

**A plugin without a token.** A plugin without a service whose connection file has no `{token}` (only settings, nothing secret) or that says `"setup": {"token": false}` has no token: the fixed guide leaves the token part out (step 2 is only the settings), no token is made, the tab *General* shows no token card and the install page shows no token row. A service has a token too (that flag is ignored for it) - unless the package says **`"service": {"token": false}`** (see *A service without a token* below). For such a plugin `done_when` cannot test the token; `{"downloaded": true}` says the set-up is done once the package was handed out.

**A service without a token (`service.token: false`).** A plugin with a service that never talks to Car Assistant - it reads nothing from the Plugin API and sends nothing to it (for example a service that only answers its own page and files from the car) - says `"service": {"token": false}`. Then: the app makes **no token** for it (an old one is revoked when a package with `token: false` is installed or updated), the service gets **no** `CA_API_URL` / `CA_API_TOKEN` (only `CA_PORT`, `CA_DATA_DIR`, `CA_VEHICLE_ID` and its settings - like an integration with a service), the tab *General* shows no token card, the guide has no token step and the install page no token row (*It needs no token*). It stays a **plugin**: *Start / Stop*, the debug switch, the approval of the service, settings, downloads and pages work as before. What only works with a token is **refused when the package is read**: a connection file with `{token}`, a bundle with `connection_file_to`, a public route with `token_header`, `tiles`, a flow step of the type `token`, and settings the service writes itself (`value` fields, `service_writable`). `capabilities` stay possible (the app calls the service there). The flag belongs to what an administrator approves: a new version that adds or removes it needs a new approval.

**A button that opens a step of the flow.** `{"id": "login", "label": "Change the login", "step": "login", "place": "settings"}` opens the step `login` of `setup.flow` again - the natural way to change a login without a page of its own. A step id the flow does not have drops the button.

**What the install page says about a package that says nothing.** `"interfaces": []` (an explicit empty list) means: *it sends nothing to Car Assistant and reads nothing from it*; the page says so (and, for a plugin without a token, *It needs no token*). A package that has no `interfaces` key at all says nothing, and the page says that instead.

## Capabilities (`capabilities`): what a plugin can do for the app

A package with a `service` may say that it can do something for the **app** besides sending data. The key is optional; without it nothing changes. Today there is one capability, **`navigate`**: the plugin takes a destination and passes it on to its car.

```json
"capabilities": { "navigate": { "path": "/mycar/navigate", "label": "Send to my car" } }
```

- **`path`** is a route of the plugin's own service and must lie under a route that is **not** `public` (so nobody from outside can call it); otherwise the capability is ignored. `label` (optional, up to 40 characters) is the name in the list of the *Map* page; without it the package name is used.
- The **Map** page lists every running plugin of the car that offers `navigate` **first**, before the navigation services, and it is chosen at first unless a service was picked under *Settings -> System -> Navigation*.
- When a person presses *Navigate*, the app sends `POST <path>` to the service (on `127.0.0.1`, with the two identity headers `X-CA-Vehicle` and `X-CA-User`) and a JSON body:

```json
{ "vehicle": 3, "name": "Brandenburger Tor", "address": "Pariser Platz, Berlin", "lat": 52.516275, "lon": 13.377704, "language": "en" }
```

- The service answers within 10 seconds: **2xx** (optionally `{"ok": true, "message": "text for the person"}`) when it took the destination, anything else - or `{"ok": false, "message": "..."}` - when it did not; the message is shown on the map.
- How the destination reaches the car is the plugin's own business. The app only hands it over, and only after the press of a button, never on its own. It is offered only while the service runs and is approved.

Like everything in the interface this is an addition: a plugin without `capabilities` keeps working exactly as before.

## The connection map (*Plugins → Connections*)

One zoomable map of everything the plugins of a car do. **Plugins on the left, in the middle every channel of the Plugin API, on the right the place where it lands** (an area of the app or an installed integration, and whether it also goes to Home Assistant as sensors).

![The connection map: plugins, channels and places, one channel opened with its raw value and history](screenshots/en/connections-map.png)

- **Every channel is on the map - also the open ones.** Each data field a plugin may send (odometer, doors, tyre pressure, battery ...), each interface (track, refuel, events, free signals, logs, settings ...) and each page of an installed integration is a row in the group of the place where it lands. A channel nobody uses is **open** (a hollow, dashed ring - it could be connected); a channel in use has a dot (green just now, yellow within a day, grey older) and says how long ago. A small arrow shows whether a plugin may **send** (to the right) or **read** (to the left) there. At the top: *n channels in use, n open*.
- **Lines.** One line per plugin, channel and direction in the colour of the plugin (solid = the plugin sends, *set*; dashed = it reads, *get*). What is connected comes first; the open channels follow below.
- **Zoom and move.** The mouse wheel zooms at the pointer, drag moves, a double click zooms in, two fingers pinch on a touch screen. The buttons zoom out, show everything, zoom in and use the **whole window** (Escape leaves). With the keyboard: `+` `-` zoom, arrow keys move, `0` shows everything.
- **Click anything** - a plugin, a channel, a place or a line - and everything about it opens below: an **explanation** (what it is, where it lands, whether a plugin sends or reads), the **connections** (who, which way, how often, when), and the **data** with the **last value, the raw value and the last ten values with date and time**. An open channel explains that it is open and what a plugin would have to do to use it. A second click on the same thing closes it.

On a phone (narrow screen) the map becomes one card per plugin with a tile for each place it talks to; the signals open right under the card.

**Where the data comes from - nothing to do for a plugin.** The app notes every successful call of a plugin to the Plugin API *per signal* (a field of `POST /data`, a free signal, an interface such as `track`, `refuel` or a page of an integration): the direction, the place it lands in, the last raw value and time, and a history of the last **10** different values (reads keep only their time). A value is written only when it changed (or after 30 seconds), a plugin may have at most 400 signals per car, a value is cut at 2000 characters, and everything of a plugin is deleted with it. Only administrators see the values; the names and times are visible to everyone who may see the plugin. The values of earlier calls are not available: the map starts to fill when this version runs.
