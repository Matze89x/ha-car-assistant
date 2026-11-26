# Start here - your first integration or plugin

🇬🇧 English · [🇩🇪 Deutsch](start-here.de.md)

You do not have to know how Car Assistant works inside. This page takes you from nothing to a package that runs in a **real Car Assistant on your computer** - in about ten minutes - and then to a *source* other people can add. The other pages hold the details; this one tells you which to read when.

## 1. What do you want to build?

| I want ... | Build a ... | Code? | Go to |
|---|---|---|---|
| my own lists, notes, reminders or a plan inside Car Assistant (stations, parts, a to-do list for the car) | **integration** | none - only a description (`plugin.json`) | [section 3](#3-your-first-integration-no-code) |
| values from a web service that answers **JSON** (a token, or a login at the provider) | **plugin with a connector** | none - a description of addresses and paths | [connectors](plugins.md#connectors-without-code-connector) |
| information from a web service or cloud account I log in to, an app, a device - when that needs more | **plugin with a service** | a small Python program | [section 4](#4-your-first-plugin-with-a-service) |
| to push values from my own script or a box in the car, now and then | **plugin without a service** | your script: one HTTP request | [section 5](#5-a-plugin-without-a-service-your-own-script) |
| a whole tool with pages of its own inside the app | integration with a service | a small program | [plugin guide, section 5](plugin-guide.md#5-a-service-of-its-own) |

Not sure? Start with the first row: an integration cannot do any harm, because nothing of it runs.

## 2. How the pieces fit

```
you and your family  -->  Car Assistant     the app: pages, data, backups, notifications
                               ^
                               |  one door: the Plugin API (a token, docs/api.md)
                               |
                          a plugin      -->  the OUTSIDE: a car, a cloud account, a web service, a device
```

- The app never talks to a car or a web service itself. A **plugin** does that - and hands over what the app needs through the **Plugin API**, nothing else.
- An **integration** is only a description of pages, reminders and plans. It has no token and calls no API; Car Assistant draws it and keeps the entries per car.
- A **source** is a repository (GitHub, public or private) with the folders `integrations/` and `plugins/`. People add the source in the app and install from it - see [sources.md](sources.md).
- A package with a **service** is a program that runs inside the add-on. It is foreign code, so an administrator has to read and approve it first ([plugins.md](plugins.md#plugins-with-a-service)).

## What you need

- A copy of this repository, Python 3.12 and the requirements of the app: `pip install -r carassistant/requirements.txt`.
- Nothing else. You do not need Home Assistant to try a package: the tool below starts a real Car Assistant with temporary data and deletes it when you stop.

All commands are run in the folder of the repository. `my-source` is any folder you like: it becomes your source.

## 3. Your first integration (no code)

```
python tools/new_plugin.py my-notes --kind integration --out my-source
python tools/plugin_dev.py my-source/integrations/my-notes
```

The first command makes the folder `my-source/integrations/my-notes/` with a `plugin.json` (a page "Notes" with a title, a note and a *Done* switch) and writes the line for it into `my-source/integrations/index.json`. The second starts Car Assistant with the integration already installed and prints the addresses: open **its page**. Add a note - it is stored for the car "Dev car".

Now change something: open `plugin.json`, rename a field or add one (the field types are in [integrations.md](integrations.md)), save. The tool notices, starts again, and you reload the page. `Ctrl-C` ends it.

## 4. Your first plugin with a service

```
python tools/new_plugin.py my-plugin --out my-source
python tools/plugin_dev.py my-source/plugins/my-plugin --set user=max --set password=secret
```

This makes `my-source/plugins/my-plugin/` with a `plugin.json`, a program `service/main.py` and the helper library `service/carassistant_sdk.py`. The tool installs it, **approves the service for you** (it is your computer and your code) and shows what happens - the log lines of the service and every call it makes to the Plugin API:

```
  log  10:21:07 info  Service started (process 4711, port 52114, restarts so far 0)
  log  10:21:07 info  [info] sent odometer_km
  api  10:21:07 POST /data -> 200  odometer_km
```

`--set key=value` fills a setting and finishes the set-up for you. Without it the plugin waits, and you run the set-up in the browser like a person would: *Set up* on its tile. To see the whole thing in one second - for a script or a test of your own - add `--once`: the tool ends as soon as the plugin has delivered something (exit code 0).

### Make it yours

Open `service/main.py`. Two places say `TODO`: `login()` (log in at the web service) and `fetch()` (ask it for the car and return what you know). Everything else is already there:

| You write | What happens |
|---|---|
| `ca.settings()` | what the person typed on the settings page of your plugin |
| `ca.Http()` | a client for web services: JSON in and out, cookies for a session, a few retries; raises `ca.HttpError` for an error answer |
| `ca.State()` | a small file in the data folder for what the service has to remember (a session, a token it was given) |
| `api.send(odometer_km=1234, ...)` | hands values to Car Assistant through the Plugin API - the names are in [api.md](api.md) |
| `ca.log("...")` | a line for the log page of your plugin (never a password or a token) |
| `@ca.route("POST", "/my-plugin/check")` | a route of your service - this one is the step *Check the login* of the set-up flow |
| `return ca.passed("Logged in.")`, `ca.failed("Wrong password.")`, `ca.ask("code", message="A code was sent by SMS.")` | the answers of a `check` route; `ask` brings the step back with a one-time input for a code ([plugins.md](plugins.md#the-set-up-flow-setupflow)) |
| `api.bearer()` | the access token of the person's login at a provider (OAuth 2.0), always fresh - see below |
| `ca.run(poll, every=60)` | calls `poll()` every 60 seconds; a failed call is logged and tried again later, it never ends the service |

The settings the person sees (a user name, a password, a switch ...) are described in `plugin.json` under `settings`; the steps of the set-up under `setup.flow` (both are explained in [plugins.md](plugins.md)). `service.connects` names the web addresses your program talks to: it is shown on the approval page, so people know what they approve.

### Logging in at a provider (OAuth 2.0)

For a web service that logs people in on its own page (most car clouds do), make the plugin with `--login oauth`:

```
python tools/new_plugin.py my-plugin --login oauth --out my-source
```

The set-up then has a step of type `oauth`: the person registers an app at the provider, types its client id, and logs in; **Car Assistant keeps the tokens and renews them**, and your service only calls `api.bearer()` for the current one. Until somebody has logged in the plugin waits (`waiting for the login` in the log); an expired login shows *Log in again* on the tile. The details - the two ways the browser comes back, what is kept safe how - are in [plugins.md](plugins.md#the-set-up-flow-setupflow). A login with a code from an SMS or an authenticator app needs no OAuth: a `check` step with a one-time `ask` input does it.

Save a file and the tool packs and starts the plugin again. The log page of the plugin in the app (*Logs* on its tile) shows the same lines with the debug switch on - the tool switches it on for you.

## 5. A plugin without a service: your own script

If a box in the car or a script of yours can send an HTTP request, you need no program inside Car Assistant:

```
python tools/new_plugin.py my-device --no-service --out my-source
python tools/plugin_dev.py my-source/plugins/my-device
```

The tool prints the address of the Plugin API, the number of the car and a **token**, and a `curl` command you can copy:

```
  Plugin API       http://127.0.0.1:52114/api/v1/vehicles/1/...   token: ca_...
                   try: curl -H 'Authorization: Bearer ca_...' -H 'Content-Type: application/json' \
                             -d '{"odometer_km": 1000}' http://127.0.0.1:52114/api/v1/vehicles/1/data
```

Run it: the call shows up in the tool as `api ... POST /data -> 200`. A script of your own does the same - see `docs/examples/push_data.py` and the list of fields in [api.md](api.md). In the real app, a plugin without a service finds its token on its settings page.

## 6. Check it, publish it

1. `python tools/check_plugin.py my-source/plugins/my-plugin` - the check the app does when it reads a package. It names typos in keys, wrong icons, missing files. Before the zip exists it tells you about the zip.
2. A plugin **with a service** is handed out as a `package.zip`: `python tools/build_plugin_package.py my-source my-plugin` builds it (the same every time) and writes its checksum into the list of the source.
3. `python tools/check_source.py my-source` - the whole source, the way the app reads it. Errors end with exit code 1; hints do not.
4. Put `my-source` into a GitHub repository (public, or private with an access key). In the app: *Plugins* (or *Integrations*) *→ Sources*: add the address of the repository. Then *Add → Update list*, tap your package, install. A service waits for the approval: *Manage → Review and approve*.
5. A new version: raise `version` in `plugin.json` and in the list, rebuild the zip, push. People press *Check for updates*.

All of it is explained in [sources.md](sources.md); a repository can also check itself every week ([docs/examples/source-ci.yml](examples/source-ci.yml)).

## When something does not work

| You see | Try |
|---|---|
| `the package is not accepted: ...` | the tool reads the package the way the app does: the text names what is wrong. `tools/check_plugin.py` says more. |
| the service starts but nothing arrives | look at the `log` lines: a line `poll failed (1): ...` has the reason. A `404` from the web service means a wrong address; `401` a wrong login. |
| `Login failed: ...` on the step *Check the login* | the answer of your `check` route: `{"ok": false, "message": "..."}` is what the person reads. Never put a password into it. |
| the log says `unreachable` | the service could not reach the Plugin API: the app is not running - as when you start `main.py` by hand. Start it through the tool or the app. |
| the app says the service is waiting for approval | in the real app an administrator approves it under *Manage → Review and approve*. The tool does it for you. |
| a plugin does not show up in the app after you pushed | *Update list* under *Add*; the list of the source (`index.json`) must name it and its folder must have the same name as its `id`. |

## Words used here

| Word | Meaning |
|---|---|
| **Add-on** | Car Assistant itself, running in Home Assistant (or, for a try-out, started by the tool on your computer) |
| **Integration** | an extra described in `plugin.json`: pages, reminders, plans. No code, no token |
| **Plugin** | a connection to the outside. It gets a token and talks to the app through the Plugin API |
| **Service** | the program of a plugin, running inside the add-on. Needs the approval of an administrator |
| **Plugin API** | the one door from a plugin to the app: `POST /api/v1/vehicles/<id>/data` and a few more ([api.md](api.md)) |
| **Package** | the folder of an integration or plugin: `plugin.json`, and for a service its files and the `package.zip` |
| **Source** | a repository with `integrations/` and `plugins/` and a list (`index.json`) in each |
| **Token** | the key of a plugin for the Plugin API. One per plugin and car |
| **Set-up flow** | the steps a person walks through the first time (text, a login, a check, a token, files) |
| **Tile** | the card of a package in the list, with its buttons |

## Where to go next

- [plugin-guide.md](plugin-guide.md) - the whole path in one page, as a reference.
- [plugins.md](plugins.md) - every key of `plugin.json`: settings, set-up flow, services, files, tiles.
- [integrations.md](integrations.md) - pages, reminders, plans.
- [api.md](api.md) - every field and way to send values.
- [examples/](examples/README.md) - small complete starting points.
