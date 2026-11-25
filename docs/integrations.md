# Integrations

🇬🇧 English · [🇩🇪 Deutsch](integrations.de.md)

An **integration** is an extra that is *added to the system*: pages, reminders, tiles and settings for a car, described in a `plugin.json`. It switches on, is configured and removed on the *Integrations* page.

**An integration has no API and no token.** It does not talk to a car or to the outside, and it does not call the [Plugin API](api.md). Everything that connects something outside (a car, a manufacturer's cloud, a web service, a device) is a **[plugin](plugins.md)**; only a plugin sends values through the Plugin API. An integration may later ask a plugin for information (the plugin offers the interface), never the other way round.

Built in today: Home Assistant (entity bindings), MQTT discovery, notifications, the **Map** (see below).

**Build your own:** anyone can write an integration - it is a description, so no code is needed (see below). Only when an integration needs a page of its own as a tool inside the add-on (`kind: "frame"`) may it carry a [service](plugins.md#plugins-with-a-service). Share it with the community on GitHub ([Sources](sources.md)).

## Pages (an integration without code)

An integration may describe **pages** in its `plugin.json`. Car Assistant draws them, stores the entries per car, and the entries are part of the vehicle backup. Nothing from the package is executed - it is only a description, so everyone can write one.

```json
{
  "id": "my-stations", "kind": "integration", "name": "Stations", "version": "1",
  "icon": "play-circle-outline", "nav": true,
  "l10n": { "de": { "name": "Sender" } },
  "pages": [{
    "id": "list", "title": "Stations", "item": "Station", "sortable": true, "empty": "Nothing here yet.",
    "l10n": { "de": { "title": "Sender", "empty": "Noch nichts hier." } },
    "fields": [
      { "key": "name", "label": "Name", "type": "text", "required": true, "role": "title" },
      { "key": "url",  "label": "Stream", "type": "url", "required": true },
      { "key": "on",   "label": "On", "type": "bool" }
    ]
  }]
}
```

- **`icon`**: a name from the app's icon set (unknown names become the puzzle piece). **`nav`**: offer the page in the navigation (it is listed in *More* of every car where the integration runs).
- **Page**: `id`, `title`, `item`, `empty` (text of the empty list), `sortable` (up / down), `order` (`{"by": "date", "dir": "desc"}`: the list is sorted by that field, newest first with `desc`; then there is no manual up / down), `fields` (up to 20), up to 6 pages (several pages get a tab bar).
- **Field**: `key`, `label`, `help`, `required`, `role` (`title` or `subtitle`: the head of an entry) and a `type`: `text`, `textarea`, `number`, `bool`, `select` (with `options`), `url` (http/https), `hex` (pairs of 0-9 A-F), `date` (a date picker, saved as `YYYY-MM-DD`, shown in the server's date format) and `secret` (see below).
- **`once`**: when a plugin writes the entry, the field keeps its first value (for example an original value); a person can change it at any time. **`compare`** (on a `hex` field): shown byte by byte against another hex field, the changed bytes marked.
- **`l10n`**: texts per language (`name`, `description`, page `title` / `item` / `empty`, field `label` / `help`); a missing translation shows the original.
- An integration has an **on/off switch** on its card (and in the list under *Manage navigation*): switched off, its page and its entry in *More* are gone and the card offers no *Open*; the entries are kept and come back when it is switched on again. Whether it sits in the bar or in *More* is chosen under *Manage navigation*.
- A plugin of the same car reads the entries with `GET /api/v1/vehicles/<id>/modules/<integration>/<page>` ([Plugin API](api.md)).

Official examples live in the [sources repository](https://github.com/Matze89x/ha-car-assistant-sources): *Coding* (control units, original next to current coding) and *Additive* (a plan for the fuel additive).


### Access codes (`secret`)
A `secret` field holds a code that must not lie around: a log-in or unlock code, for example for a control unit. It is **hidden** in the entry (`••••••`) until someone presses *Show* (the page then reloads with the code visible and is never cached); in the form the field is empty and **an empty field keeps the saved code** (a tick box removes it). A code is **never** in the search text, **never** sent to a plugin (`GET` leaves the field out, `POST` ignores it), and **left out of the vehicle backup** - like the password of a plugin it is entered again after a restore. *Vehicle data → Backup with access codes* (shown only when the car has saved codes) makes a second file that contains them in plain text. The system backup holds everything, codes included; the page says so. A `secret` field cannot be used for `order`.

### Page details
- A **second list** needs nothing special: add another page (up to 6, tab bar). A history, for example, is a page with a `date` field, `order` by it and `search: true`.
- A page with **two `title` fields** shows the first as a short badge in front (an address, a number) and the second as the name; `subtitle` fields form the second line.
- A page with a **`compare`** field gets, for every entry, a collapsible row: the original as ONE line, below it the current bytes (only a changed byte shows its old value), and for a tapped byte - one under the other - its original and current bits, the eight **bits with a tick box and a note each**, and **groups** of bits that belong together (a name and a value as a number). Notes and groups are kept with the entry, the count of changed bytes, **New = original**, a search box and **Only changed**. `search: true` adds the search box to any page.
- Fields named `notes` (a `textarea`) and the compared `hex` field are edited right in the row; every other field sits behind *Edit data*.

## Reminders and widgets

An integration may describe **reminders**: "again after N kilometres" or "after N refuels". The numbers come from the integration's own settings, so every user decides (1000, 2000, 3000 km ...). Nothing happens until the integration is installed and running.

```json
"settings": [
  { "key": "mode", "label": "Remind me", "type": "select", "default": "km",
    "options": [{ "value": "km", "label": "after kilometres" }, { "value": "refuels", "label": "after refuels" }] },
  { "key": "every_km", "label": "Every ... km", "type": "number", "default": "1000" },
  { "key": "every_refuels", "label": "After ... refuels", "type": "number", "default": "2" }
],
"reminders": [{
  "id": "additive", "title": "Add fuel additive", "text_due": "Add the additive at the next refuel.", "icon": "oil",
  "mode_setting": "mode", "km_setting": "every_km", "refuels_setting": "every_refuels",
  "l10n": { "de": { "title": "Additiv nachfüllen" } }
}]
```

- A setting may have a **`default`** (what it is until the user changes it) and `l10n` texts (`label`, `help`).
- **`mode_setting`** names the setting that holds `km` or `refuels`; without it the rule uses the kilometre or the refuel setting that exists.
- The app counts kilometres from the odometer and refuels from the fuel entries; **Done** starts the count again.
- A running integration with a reminder gets a **card on the Fuel page** and a **widget on the Dashboard** (movable and switchable like every widget).
- Official example: *Fuel additive* in the [sources repository](https://github.com/Matze89x/ha-car-assistant-sources).

### Plans (a reminder with a rotation)
A reminder may carry a **`plan`**: a short rotation that moves on with **every refuel** the app sees (for example *clean - additive 1 - clean - additive 2*). The app keeps the position and a history; the page shows the next refuel, the rotation, **Correct the plan** and the history with *added / not added*.

```json
"reminders": [{
  "id": "additive", "title": "Fuel additive", "text_due": "Add the additive at the next refuel.", "icon": "oil",
  "active_setting": "active", "range_setting": "range",
  "plan": [
    { "label": "Clean" },
    { "setting": "additive_1", "amount_setting": "amount_1", "label": "Additive 1" },
    { "label": "Clean" },
    { "setting": "additive_2", "amount_setting": "amount_2", "label": "Additive 2" }
  ]
}],
"pages": [{ "id": "plan", "kind": "plan", "reminder": "additive", "title": "Additive plan" }]
```
- A step is a fixed **`label`**, or a **`setting`** (the name the user typed) with an optional **`amount_setting`**; a step with a `setting` is a "dose" that can be due, a step with only a label is a clean refuel. 2 to 8 steps; `l10n` translates the labels.
- **`active_setting`** (a switch) turns the reminder on and off; **`range_setting`** (kilometres of range) holds it back until the car's range falls below that value.
- The page of kind **`plan`** needs no fields; it points to the reminder with `reminder`.

**Rule:** an integration may carry a `service` only when it needs it for a page of its own inside the app (a tool in the add-on, `kind: "frame"` in [plugins](plugins.md)), never to connect a device or a car - that stays a plugin. It gets no token and no Plugin API.

## Map

*Map* is a built-in page of every car (switch it on under *More -> Integrations*; it is off for a new car). It is one full-area map inside the content area (on a phone down to the screen edge) with a back button at the top left, the buttons *My position*, *Car* and *Light / dark map* at the top right and the search below them.

- **Nothing is loaded by default:** the map needs *Settings -> System -> Online -> Map*, then it shows OpenStreetMap through this app (the same tiles as the location widget).
- **The car** is drawn at its last position and moves while the page is open. **Your own position** is drawn only after you press the button and allow it in the browser (it needs https); it stays in your browser and is never sent to the server.
- **Search:** type a place or address and press search (never while typing: the public service does not allow that). The words go to the Nominatim service set under *System -> Map info* (the public OpenStreetMap one by default), together with the area of the map. When it gives nothing, the same words can be searched at the chosen navigation service. A long press on the map drops a point.
- **Navigate:** a chosen place or the car opens a sheet with the list *Navigate with*. The first entries are **plugins of the car that offer `navigate`** (see [Capabilities](plugins.md#capabilities-capabilities-what-a-plugin-can-do-for-the-app)); then come the navigation services - Google Maps, Apple Maps, Waze, Bing Maps, OpenStreetMap, Mapy.com, HERE WeGo, Yandex Maps / Navigator, Magic Earth, Sygic and a generic Android geo link. A service is only a **link** with the destination in it: the phone opens its app (or the website); nothing is sent from the server to it. *Settings -> System -> Navigation* sets the default for the whole app; *Automatic* means the plugin of the car if there is one, else Google Maps.
