# Car Assistant

<!-- release:start -->
**0.5.38 Beta** - The public test version. Please try it and report what you find.
<!-- release:end -->

**Drive · Log · Go** – the logbook and dashboard of your cars, fully local.

## First steps
1. Open **Car Assistant** in the Home Assistant sidebar. Nothing has to be set up for that.
2. Add your first car (or tap **Demo car** to look around with made-up data; delete it any time).
3. Follow the *Get started* list on Home: odometer, first fill-up, a service entry, connect the car.

More cars: *Settings → Vehicles → Add vehicle*; a **Switch vehicle** menu then appears at the top.

## What it does
- **Per car:** vehicle passport with equipment, fuel or charging, service, appointments, tasks, parts, tyres, modifications, documents, trips with km counters, the manual, photos and videos. Everything works for combustion, hybrid and electric cars.
- **Quick entry:** tap the odometer on the dashboard to type the number or photograph the cluster; *Scan receipt* on the fuel page fills in a fill-up from a photo of the receipt (date, station, fuel, amount, price, total, odometer). Read on your own server, never stored, no plugin needed.
- **Reminders:** maintenance, appointments and your own reminders; open points show as a dot on the tab. Notifications go to your phone through your own Home Assistant notify service, per user. **What is offered:** under *Settings → User → Notifications* a car only offers the messages it can really tell - judged by what its plugins and entities delivered (no tyre message without tyre pressures, no open-door message without door data); what you enter yourself (maintenance, appointments) is always there. **Low tank / battery:** you choose the level per car under *Settings → User → Notifications* (in per cent and / or as a range; empty = the yellow level of the car). You are told **once**, as soon as the car reports a level at or below it, and again only after the level was back above it by a margin (5 percentage points, or a fifth of the range) - for example after refuelling.
- **Plugins and integrations:** a plugin connects anything outside (a car, a cloud account, a web service) through the Plugin API; an integration adds pages (for example coding values or a fuel additive reminder). Both are installed from *sources* you add yourself; nothing is fetched on its own.
- **Units and currency:** one choice for the whole app under *Settings → System → Region* (km / miles, litres / gallons, mpg, psi, any currency). Everything is stored in base units, so you can switch back and forth.
- **Languages:** English and German built in; more languages are plain files.
- **Notifications and web apps per car:** *Settings → Car* turns notifications on for the device you use; *Settings → User* has a start link per car for a home screen web app.
- **MCP access for Claude:** *Settings → System → MCP access* (off by default) lets Claude read and, if you allow it, correct your records. It needs a user, your external https address and the open port of the app - not MQTT. How to set it up: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/mcp.md
- **Backup:** one car or the whole system, each on its own.

## Configuration
Open the app (*Settings → Apps → Car Assistant*) and its *Configuration* tab.

| Option | Meaning |
|---|---|
| `log_level` | How much the app writes to its log. `error` = only problems (default). Use `info` or `debug` only to find a problem. |
| `mqtt_sensors` | No longer needed - kept only so that existing configurations stay valid. The sensors in Home Assistant (MQTT) are on by default whenever a broker is found and are switched in the app (*Settings → System*). |
| `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password` | Only for your own broker. Empty = the broker of Home Assistant (for example the Mosquitto app), found automatically. |

Everything else (language, units, notifications, the external address, fuel prices) is set inside the app under *Settings*.

If a browser fills the *user name* field with an old login, empty it before saving: Home Assistant draws this page, the app cannot switch the autofill off.

## Who can reach Car Assistant
- **Through Home Assistant** (the panel in the sidebar): always works, nothing to set up, no login needed.
- **Directly** (a browser on `http://<Home Assistant address>:<port>`, a reverse proxy, a tunnel, a phone): needs a **port** and a **user**.
  - **Port:** empty by default, which means no direct access. Enter any free port of your choice under *Network* in the *Configuration* tab. If it is used by something else, the app does not start: pick another.
  - **User:** create one under *Settings → User* (or in the short setup step after your first car): name and password, optionally a **passkey** (Face ID, fingerprint, security key; add it while the app is opened through your https address). Without a user the direct address shows a page that says so, nothing else.
  - After 5 wrong attempts an address is locked for 15 minutes. A forgotten password is reset by an administrator in the Home Assistant panel (*Settings → User*); recovery codes work too.
- **From outside your network:** your router (port forwarding) or your reverse proxy / tunnel (Nginx Proxy Manager, Caddy, Cloudflare Tunnel, ...) decides. Always use **HTTPS**: without it a password travels unencrypted. Point the proxy to `http://<Home Assistant address>:<port>`, let it pass the `Host` header and give it its own subdomain (no sub-path), then enter the address under *Settings → System → External address*.
- The public routes of a plugin's service (for devices without a login) are not covered by this: they are public on purpose.

## Sensors in Home Assistant (MQTT)
On by default **when a broker is found** (for example the Mosquitto app); without a broker nothing happens and *Settings → System* says so. There is ONE place to switch it: the app. There, *Use the MQTT of Home Assistant* (on by default) means: nothing to enter; only if you switch it off do the fields for an own broker appear. When on, every car becomes a device in Home Assistant: odometer, range, appointments and - as soon as a plugin delivers them - ignition, locking, doors, windows, tyre pressures, battery, charging and more. The **GPS position** shows up as a device tracker on the Home Assistant map. Only values that exist are created; rarely useful ones start switched off, technical ones are diagnostics. Switching the sensors off removes them from Home Assistant again.

**Entity names.** Home Assistant builds an entity ID such as `sensor.my_car_odometer` from the name of the car and of the sensor **once, when it first creates the entity**, and never changes it afterwards. So that the IDs follow the names, Car Assistant **rebuilds the sensors of a car by itself when the car is renamed**, and *Settings → System → Rebuild sensors* does it for all cars (for example after you changed the language: with German the sensors are called *Kilometerstand* and the IDs become `sensor.my_car_kilometerstand`). Rebuilding takes the entities out of Home Assistant and puts them back a few seconds later: their history and automations that use the old IDs are lost.

**What is sent.** Only what the app really knows - there are no empty sensors. Under *Settings → System* five switches choose the groups: *Values from the car* (what a plugin or a bound entity delivers: ignition, doors, locking, tyres, battery, temperatures ...), *Maintenance, appointments and open items* (inspection, next task and appointment, mounted tyres), *Consumption and fuel cost*, *More statistics* (last fill-up, costs this year and per 100 km, distance this month and year, last trip; **off** until you want it) and the *position* for the Home Assistant map. The odometer is always sent. A group that is switched off takes its sensors out of Home Assistant again.

**Check Home Assistant.** The button *Check Home Assistant* (like the test push) sends a test message to the sensor *Last notification* of every car and looks in Home Assistant whether it arrived. It tells you step by step where it stops (Home Assistant reachable, broker found and connected, message arrived) and lists the entity IDs Home Assistant gave the sensors.

**Notifications as a sensor.** Every car also gets the sensor *Last notification* (switch under *Settings → System*, on by default): it shows what the app announces for the car - maintenance, appointments, reminders, messages from the car, open doors or windows, low fuel or charge, tyre pressure, finished trips, refuels - **always**, whether or not anybody set up notifications in the app. Its attributes hold the full text (`message`, `lines`), the time, a counter and the last few messages (`history`). An automation in Home Assistant can pass it on, for example as a push or a spoken message: trigger on a *state change* of the sensor (the attributes change with every message, so equal texts trigger as well).

Switch it on in the *Configuration* tab or under *Settings → System*. The app asks the Supervisor for the broker and connects automatically; for an external broker enter host, port and credentials in the same place.

## Privacy: nothing goes online on its own
- **Map info:** off by default. Under *Settings → System* you can switch on *Show map info* (Leaflet bundled, OpenStreetMap tiles, place names of trips). Car Assistant fetches the tiles for you and keeps them for a week, and asks OpenStreetMap once for the street and place of the start and the end of each trip so the log book shows names instead of coordinates (the answers are kept). OpenStreetMap sees your server's address, the map area you look at and those coordinates - not your phone or your Home Assistant address.
- **Fuel prices:** the station search uses OpenStreetMap; for live prices in Germany enter **your own** free key from https://creativecommons.tankerkoenig.de (*Settings → System*). There is no built-in key. Data: CC BY 4.0, tankerkoenig.de.
- **Sources:** a source is only asked when you add it, press *Update* or install something.
- **Notifications over the web** (browser push) are only offered on a page opened through https.

## Plugins with a service
A plugin or integration may bring a small program of its own (a *service*) that runs inside this add-on. **This is foreign code.** It runs only when the package comes from a source you added, only after you approved it on a page that lists everything it will do, as its own program with its own user and limits, and never with the Home Assistant token or the database. Only approve services from sources you trust.

## Backup
- **One car:** *Settings → Car → Backup and manage* (everything of that car; restore it as a new car).
- **Everything:** *Settings → System → Back up* (all cars, users, settings). A restore makes a safety copy first.
- **Secrets:** a backup holds no token, password, key or access code - unless you type a passphrase when you make it; then they travel in one encrypted block and come back after a restore, also on another system.
- The app is also part of every Home Assistant backup (`backup: cold`).

## More documents on GitHub
Full descriptions are kept in the repository:
- User guide: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/guide.md
- Installation: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/install.md
- Sources and packages: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/sources.md
- Plugins: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/plugins.md
- Integrations: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/integrations.md
- Plugin API: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/api.md
- Backup: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/backup.md
- Architecture (how everything fits together): https://github.com/Matze89x/ha-car-assistant/blob/main/docs/architecture.md
- Examples for your own plugin or integration: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/examples/README.md
- Screenshots: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/screenshots.md
- Changelog: https://github.com/Matze89x/ha-car-assistant/blob/main/carassistant/CHANGELOG.md
- Report a problem: https://github.com/Matze89x/ha-car-assistant/issues

## Support
Free and made in spare time: https://ko-fi.com/matze89x
