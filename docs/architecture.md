# Architecture: how everything fits together

🇬🇧 English · [🇩🇪 Deutsch](architecture.de.md)

Three pictures, from the big to the small. They are drawn straight from the text (Mermaid).

## 1. The whole system

Car Assistant is **one** app inside Home Assistant. Everything that talks to the outside (a car, a cloud, a web service) is a **plugin** and talks to the app only through the Plugin API.

```mermaid
flowchart TD
  you["You: browser or phone"]
  ha["Home Assistant: sidebar panel (Ingress)"]
  direct["Direct access: port + user, HTTPS through a proxy"]
  app["Car Assistant (FastAPI + SQLite)"]
  pages["Pages and lists per car"]
  api["Plugin API /api/v1 (token per car)"]
  worker["Background: reminders, notifications, clean-up"]
  mqtt["MQTT broker -> sensors and location in Home Assistant"]
  notify["Home Assistant notify service and web push"]
  plugin["Plugin: connects something outside"]
  outside["Car, cloud, web service, device"]
  you --> ha --> app
  you --> direct --> app
  app --> pages
  app --> api
  app --> worker
  worker --> notify
  app --> mqtt
  plugin -->|token| api
  plugin --> outside
```

## 2. A plugin: from the outside to the page

A plugin knows only the Plugin API. It reads outside, sends values to the app, and the app shows only what a plugin has delivered - nothing is invented.

```mermaid
flowchart LR
  car["Car / cloud / web service"]
  plugin["Plugin (own code, own place)"]
  api["POST /api/v1/vehicles/ID/data"]
  db[("Database: current values, history, log")]
  home["Home: tiles, location, open points"]
  more["Security, trips, vehicle data"]
  rem["Reminders and notifications"]
  mqtt["MQTT sensors in Home Assistant"]
  car --> plugin
  plugin -->|"Bearer token, this car only"| api
  api --> db
  db --> home
  db --> more
  db --> rem
  db --> mqtt
```

The interface is described in the [Plugin API](api.md); how to build a plugin is in the [plugin guide](plugin-guide.md) and in [Plugins](plugins.md).

## 3. Sources, packages and services (plugins and integrations)

Plugins and integrations are **packages**: a readable folder with a `plugin.json`. They come from *sources* that you add yourself. Only a package with a **service** runs code, and only after your approval.

```mermaid
flowchart TD
  src["Source: GitHub repository or https address with an index.json"]
  pkg["Package: plugin.json, files, package.zip (sha256 checked)"]
  user["You: add, install, approve"]
  plug["Plugin: token, Plugin API, this car only"]
  integ["Integration: pages, reminders, tiles, no token"]
  svc["Service (optional, foreign code): own process, own user, limits"]
  proxy["App proxy: signed-in people only, routes from the package"]
  page["Own page of the service under More"]
  src --> pkg
  user --> pkg
  pkg --> plug
  pkg --> integ
  pkg -.->|"only after approval"| svc
  svc --> proxy --> page
  plug --> svc
  integ --> svc
```

The service gets neither the Home Assistant token nor the database; an integration gets no token and never calls the Plugin API. The rules are in [Sources](sources.md), [Integrations](integrations.md) and [Plugins](plugins.md#plugins-with-a-service).

## Build your own

1. Read the [plugin guide](plugin-guide.md) and the [Plugin API](api.md).
2. Look at the examples in [docs/examples](examples/README.md): a service with a page, a script that sends values, and a script that writes a vehicle file.
3. Put your package in a repository with an `index.json` ([Sources](sources.md)), add it as a source and install it.
