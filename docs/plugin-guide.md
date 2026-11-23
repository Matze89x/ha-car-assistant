# Build a plugin - the guide

🇬🇧 English · [🇩🇪 Deutsch](plugin-guide.de.md)

A plugin is a **connection to the outside**: a car, a web service you log in to, a cloud account, a device. This page walks you from nothing to a working plugin in a source. Details: [plugins.md](plugins.md) (the package), [api.md](api.md) (the Plugin API), [icons.md](icons.md), [sources.md](sources.md).

## 1. The folder
In a source (a GitHub repository, public or private with a key), a plugin is a folder:
```
plugins/my-plugin/
  plugin.json          the description (required)
  service/main.py      optional: a program of its own that runs in the add-on
  package.zip          built from the folder (only for a plugin with a service)
plugins/index.json     the list: {"packages": [{"id": "my-plugin", "name": "...", "version": "1", "icon": "wrench", "sha256": "..."}]}
```
The folder name is the plugin's `id`. Start from `docs/examples/echo-service/`.

## 2. plugin.json
```
{"id": "my-plugin", "kind": "plugin", "name": "My plugin", "version": "1", "icon": "wrench",
 "description": "One sentence for the tile.", "author": "Name",
 "docs": "A longer text for the page Interfaces.",
 "l10n": {"de": {"name": "Mein Plugin", "description": "Ein Satz für die Kachel."}},
 "settings": [ ... ], "interfaces": [ ... ], "service": { ... }, "downloads": [ ... ], "connection_file": { ... }, "setup": { ... }}
```
Keep `version` in `plugin.json` and the index the same; a higher number offers an *Update*. Pick the `icon` from [icons.md](icons.md).

## 3. What the user can set (settings)
Describe the options as JSON - the app draws them on the plugin's **settings page** (switches, choices, sliders, lists, headings, ...). All types, `show_if`, validation and what a service receives: [plugins.md](plugins.md#settings-page). Example:
```
"settings": [
  {"type": "section", "label": "Account"},
  {"key": "user", "type": "text", "label": "User name", "required": true},
  {"key": "pass", "type": "password", "label": "Password"},
  {"key": "mode", "type": "radio", "label": "Mode", "options": [{"value": "a", "label": "Auto"}, {"value": "b", "label": "Own"}], "default": "a"},
  {"key": "url", "type": "url", "label": "Address", "show_if": {"key": "mode", "equals": "b"}},
  {"key": "feeds", "type": "multiselect", "label": "Feeds", "options": [{"value": "news", "label": "News"}, {"value": "wx", "label": "Weather"}]}
]
```
Passwords (logins to web services) stay out of vehicle backups and are never shown or logged.

Fields of a setting marked `"advanced": true` are folded under *Advanced settings* in the set-up guide.

## 4. Talking to the app (Plugin API)
The plugin gets a token (a plugin **without** a service: on its settings page; **with** a service: the add-on gives it `CA_API_TOKEN`) and sends what it knows: `POST /api/v1/vehicles/<id>/data`, `/track`, `/events`, `/signals`, `/refuel`, `/logs`; read `control` for the debug switch and the interval. Which way for which data: [plugins.md](plugins.md#which-way-for-which-data), all fields: [api.md](api.md). Send only what is real; never guess.

## 5. A service of its own
When the plugin needs a program (to log in somewhere, fetch pages, serve files to a device), add `"service": {"entry": "service/main.py", "requirements": [...], "routes": [{"prefix": "/my/", "public": true}], "connects": ["api.example.com"]}`. It runs **in the add-on**, only after an administrator approved it, with `CA_PORT`, `CA_API_URL`, `CA_API_TOKEN`, `CA_VEHICLE_ID`, `CA_DATA_DIR` and `settings.json` (typed). Everything about the rules, limits and the approval: [plugins.md](plugins.md#plugins-with-a-service). Build the zip and the checksum with `python tools/build_plugin_package.py <source folder> <id>`.

**A whole tool with its own page** (an editor, a dashboard): an *integration* may carry a service too - then without token and Plugin API - and show its pages as a `kind: "frame"` page: the app adds only its head (back, name, version) and the page is yours, in the design of the car. Everything about it (parameters, headers, limits, design kit, map tiles): [plugins.md](plugins.md#a-page-of-the-service-as-a-page-of-its-own-kind-frame).

## 6. Files for download
A service can serve any file on one of its routes (binary files, `Content-Disposition` and `Content-Type` pass through; at most 16 MB per answer). To give the person a button in the app, list it in `plugin.json`:
```
"downloads": [{"label": "Data package", "path": "/my/pack.zip", "note": "for the vehicle display"}]
```
The path must lie under one of the service's routes. The buttons show on the plugin's tile under *Manage* (while it runs); files and the connection file come from the set-up guide only. A **public** route is reachable by anyone (a device without a login); a **non-public** one only from Home Assistant or for a signed-in person. **Binary files that need no service** (a program for the car, a ready SD card package) go in `files` / `bundles`: see [plugins.md](plugins.md#files-of-a-package-downloads-without-a-service). A plain file that holds the token and the settings is `connection_file` (see [plugins.md](plugins.md#connection-file)).

## 7. Tell what you offer (Interfaces)
Add `docs` and `interfaces` so the page *Info* of your plugin documents every interface it sends, reads or offers: [plugins.md](plugins.md#the-interfaces-page-of-a-package). The page also shows what the plugin really used (addresses and field names, never values).

A plugin with a connection file can bring a **set-up guide** (`setup`): three fixed steps - check (address and VIN), token and settings, files and instructions - shown on one page from its settings page. The connection file takes `{vin}` and `{url}`; a service finds `external_url` and `vehicle_vin` in its `settings.json`. All of it is in [plugins.md](plugins.md#set-up-guide-setup).

## 8. Check, publish, update
1. `python tools/check_plugin.py plugins/my-plugin` - names typos, wrong icons, missing files, a wrong checksum.
2. Commit the folder, `package.zip` and `plugins/index.json` together.
3. In the app: *Plugins → Add → Update list*, tap your plugin, install. With a service: *Manage → Review and approve*.
4. Watch it: *Manage → Debug* (this plugin only) and *Logs*: log lines, what the add-on does with the service, and the traffic. Logs are kept 1, 7 or 30 days.
5. New version: raise `version` in `plugin.json` and the index, rebuild the zip, commit; people press *Check for updates*. An update the administrator presses keeps the approval given when installing.

## 9. Integrations without code: pages, reminders, plans
An *integration* has no program and no token: it only describes what the app should draw. Pages with typed fields (also the byte-by-byte comparison for codings), reminders after kilometres or refuels, **plans** (a rotation that moves on with every refuel), value tiles for Home and widgets are all described in `plugin.json` - see [integrations.md](integrations.md). A plugin of the same car can read and write the entries of an integration page through the [Plugin API](api.md).

**Continuing later?** Everything a package can offer is described in this folder: [plugins.md](plugins.md) (format, settings, files, services, tiles, interfaces), [integrations.md](integrations.md) (pages, reminders, plans), [api.md](api.md) (what a plugin sends and reads), [sources.md](sources.md) (publishing) and [icons.md](icons.md). Official examples: the [sources repository](https://github.com/Matze89x/ha-car-assistant-sources).
