# The Home Assistant plugin

🇬🇧 English · [🇩🇪 Deutsch](home-assistant.de.md)

Your Home Assistant probably knows a lot about your car already: the integration of the car maker, a tracker, a tyre sensor, **a wallbox** that charges it. The Home Assistant plugin brings those entities into Car Assistant - **for every car on its own**. For each interface of the [Plugin API](api.md) (mileage, tank, battery, charging power, doors, tyres, position ...) you choose the entity of Home Assistant that delivers it; the app reads it, converts the unit and keeps it like any other value of the car.

- **Per car.** Each car has its own install of the plugin and its own choice. The wallbox in the garage belongs to the car that charges at it - you decide, for each car, which interfaces come from where.
- **Live.** Changes arrive at once, without anyone asking again and again (see [Live and asking](#live-and-asking)).
- **Clean.** Units are converted, a yes / no is understood by the kind of entity, a value carries the time Home Assistant gives, and one interface can only come from **one** plugin of a car ([One interface, one plugin](#one-interface-one-plugin)).
- **For everyone.** The package is a plain `plugin.json` with one key, `bridge`; it runs no code. See [For package authors](#for-package-authors).

It works in the **Home Assistant add-on** (the app talks to Home Assistant through the Supervisor). Only administrators choose the entities: the entities of Home Assistant are the system's, not the car's.

## Set up

1. *Car → More → Plugins → Add* and take **Home Assistant** from your source (or upload the example [`examples/home-assistant/plugin.json`](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/examples/home-assistant/plugin.json)).
2. Open its settings. The page lists the interfaces in groups - *Vehicle*, *Fuel and range*, *Battery and charging*, *Doors, windows and lock*, *Position*, *Tyres*, *Temperatures and climate*, *Service and warnings*.
3. Click into the field of an interface: a list of **likely entities** opens. Type to narrow it down, click one.
4. The line under the field says **what it delivers right now** (`64 %`, `7.4 kW from 7400 W`, `Locked`). Save.

From then on the values flow in; the plugin's tile and its *Logs* page say what it does.

## Choosing an entity

The list is made for the interface you click into: entities of the right kind come first (a lock for *Locked*, a sensor with the device class *distance* or a unit of length for *Range*), then the rest. What you type is looked for in the **name, the id, the device and the area** - so *garage* finds everything of the wallbox in the garage, as in Home Assistant itself. *Show all entities* lifts the filter by kind. Each line shows the name, the id, the device and area and the current state.

The line under a chosen field is checked live: *This entity does not exist*, *The unit "l" does not fit*, *Not available right now* tell you at once what is wrong.

## Live and asking

Car Assistant keeps a **live connection** to Home Assistant (its WebSocket API, through the Supervisor, like the REST access). It follows **exactly the entities you chose** - nothing else of your Home Assistant - and a change arrives at once; a burst of changes becomes one reading a second at most. The page says *Live connection to Home Assistant: changes arrive at once.* while it stands.

If the connection fails (Home Assistant restarts, the network blinks) the app builds it up again with growing waits (1 to 60 seconds), looks at everything once more when it is back (so nothing that happened meanwhile is missed) and **asks Home Assistant in the meantime**, every *Look at least every* seconds (the setting of the plugin, default 30). Without the library or outside the add-on there is simply no live connection and the plugin asks. While the connection stands, the setting only sets a safety net: Home Assistant is looked at once more every five minutes (or less often, if you set a longer time), so that nothing stays wrong for long.

## What is done on the way

- **Units.** A number is converted into the unit the Plugin API keeps: miles, feet, metres - km/h, mph, m/s, knots - W, kW, MW - psi, kPa, hPa, mbar, mmHg, inHg - gallons, millilitres, kWh - °F, K - mV - hours, seconds, days - km/l, mpg, Wh/km, mi/kWh. A unit that does not fit (litres for a percentage) is **not guessed**: the row says so, and you can choose the unit or *As it is* in the options.
- **Dates and times.** For *Charging time left* and *Days to service* an entity that holds a time or a date works too: the minutes or days until then are used.
- **The time of the measurement.** Each value carries the time Home Assistant gives (`last_reported` / `last_updated`) as `measured_at`. When two sources deliver the same field, the **newer measurement wins**; an older one never replaces a newer one.
- **Only what changed** is sent. An entity that is *unavailable* or *unknown* is skipped (the last value stays, with its age) - a car that sleeps is no error. A value the Plugin API would refuse (a tank level of 250 %) is refused for that row only; the others go on.
- **The odometer** only ever grows, as everywhere in Car Assistant: a reading that is lower than the highest known one (a fill-up or service entry typed with a higher figure counts as known) is not taken and is noted once in the log of the plugin; it counts again as soon as it is higher. Nothing has to be triggered: as soon as an entity is chosen for the odometer, every change arrives by itself, and the dashboard shows the figure instead of asking for it.

### Yes and no

A yes / no is read by what the entity is: a **lock** (`locked`), a **binary sensor** by its device class (a *door*, *window* or *opening* says open; a *plug* says plugged in; *battery charging* says charging; for the class *lock* Home Assistant means `on` = unlocked - that is turned round for you), a **cover** (`open`, `opening`, `closing` = open), a **climate** entity (anything but `off` = on), a **switch** or **light**, or a status **text** (`locked`, `plugged_in`, `Charging` ...). An entity that is about something else than the interface (a door sensor for *Locked*) is refused with a hint.

Where the entity does not say it in words Car Assistant knows, the options of the row help: **States that mean yes** (for a wallbox status sensor: `Preparing, Charging, SuspendedEV` for *Plugged in*, `Charging` for *Charging* - every other state is no), **Yes above** (a charging power above 0 means charging) and **Turn round**.

### Position, tyres, doors, warnings

- **Position.** Choose a *tracker* or a *person* (or any entity with `latitude` and `longitude`), or - lower in the group - two sensors, one for each half. A position of 0, 0 (no fix) is not taken.
- **Tyres.** Four interfaces, one for each wheel; the pressure is converted to bar.
- **Doors, windows, lights, warnings** are lists: one row for each door (`front_left`, `trunk` ...), with a name you choose and the entity. A warning shows its text (the name of the entity, or the text you type) while its entity is on, and goes away when it is off.

### Options of a row

Rarely needed, folded away until you have chosen an entity: **Attribute** (read this attribute of the entity instead of its state - the temperature of a climate entity, the course of a tracker), **Unit**, **Factor** and **Offset** (`value × factor + offset`, applied last), **States that mean yes**, **Yes above**, **Turn round**, and for a warning the **Text shown**.

## Special cases: let Home Assistant do the thinking

Every car, wallbox and integration is a little different. The options of a row cover what a single entity can say differently (unit, factor, attribute, yes-words); everything that needs **logic** is best done where it belongs, in Home Assistant itself: a template sensor or a helper is one entity more, and the plugin reads it like any other. Four recipes that come up again and again:

- **The tank in litres, the interface wants a percentage.** No template needed: choose *As it is* for the *Unit* of the row and enter the **Factor** `100 ÷ tank size` (`1.818` for a 55 litre tank). The same works for a battery in kWh (`100 ÷ capacity`).
- **One wallbox, two cars.** A helper (*Settings → Devices & services → Helpers → Dropdown*, called `input_select.wallbox_car`) says which car is plugged in; every car gets its own pair of template entities, and the plugin of that car reads those instead of the wallbox itself:

  ```yaml
  template:
    - binary_sensor:
        - name: "Car A charging"
          device_class: battery_charging
          state: "{{ is_state('sensor.wallbox_status', 'charging') and is_state('input_select.wallbox_car', 'Car A') }}"
        - name: "Car A plugged in"
          device_class: plug
          state: "{{ states('sensor.wallbox_status') in ['preparing', 'charging', 'suspended_ev'] and is_state('input_select.wallbox_car', 'Car A') }}"
  ```

- **Two sources for one value** (the car maker's integration sleeps, a tracker never does): one template sensor takes the first that is there.

  ```yaml
  template:
    - sensor:
        - name: "Car range best"
          device_class: distance
          unit_of_measurement: "km"
          state: >
            {% set a = states('sensor.car_range') %}
            {{ a if a not in ['unknown', 'unavailable'] else states('sensor.car_range_estimate') }}
  ```

- **A number with its unit in the text** (`"12.5 km"`): the plugin wants a number, so a template cuts the unit off: `{{ states('sensor.trip_text').split(' ')[0] | float(0) }}`.

The plugin reads only what Home Assistant says is a value; it never evaluates templates itself, so a template can never run anything inside Car Assistant.

## One interface, one plugin

An interface you choose here **belongs to this plugin** for that car: while it is on, no other source of the car fills it - another plugin, a connector, the older Home Assistant fields of the vehicle form. Whatever such a source sends is answered with `ignored (taken by Home Assistant)` and not stored, so a value of the car always has exactly **one origin**.

- The interface is taken when you **save**. If another plugin of the car holds one of the interfaces you chose, nothing is saved and the page names it; on the row it says *Taken by ...*.
- Switching the plugin **off** frees everything it holds (it comes back with it); a plugin whose interfaces another one holds cannot be switched on until that is settled. Removing it gives them back for good.
- Other plugins may take interfaces for themselves too (`claims` in their `plugin.json`); the *Interfaces* page of a package lists them.

The rule never touches the other cars, and never forces a plugin that does not ask for it: a plugin that sends a field nobody has taken is simply one of the sources, and the newer measurement wins.

## Several cars, one wallbox

Install the plugin on each car and choose what that car gets: the wallbox that charges the family car as *Charging*, *Plugged in* and *Charging power* of that car, the car maker's own integration for its mileage and tyres. Another car keeps its own entities. A wallbox that is already in Home Assistant needs nothing else.

## Backup

The choices belong to the car: they are in the [backup of the car](backup.md) (and in the backup of the whole system). After a restore the plugin is off, like every restored plugin; switching it on takes its interfaces again. A file that was not made by Car Assistant is checked row by row - an entity or an option that is not valid is left out.

## For package authors

A package that offers this is a `plugin.json` without a service and without a connector, with the key `bridge`:

```json
{ "id": "home-assistant", "kind": "plugin", "name": "Home Assistant", "version": "1.0.0",
  "bridge": { "type": "home_assistant" },
  "settings": [ { "key": "every", "type": "select", "label": "Look at least every", "default": "30",
                  "options": [ { "value": "10", "label": "10 s" }, { "value": "30", "label": "30 s" }, { "value": "300", "label": "5 min" } ] } ] }
```

| Key | Meaning |
|---|---|
| `type` | `home_assistant` (the only one so far) |
| `slots` | optional: only these interfaces are offered, by key - for example `["charging", "plugged", "charge_power_kw"]` for a *wallbox* package |
| `groups` | optional: only these groups (`vehicle`, `fuel`, `battery`, `access`, `position`, `tyres`, `climate`, `service`); `slots` wins when both are given |
| `every` | optional: the default of *Look at least every*, 10 to 3600 seconds (default 30) |
| setting `every` | optional: when the package declares a setting with the key `every`, the page shows it and the person's choice counts |

The package **never names an entity** and never sees the Home Assistant token: the administrator chooses the entities, the app reads them. A package with a `bridge` has no token (nobody calls the Plugin API; the app does). `bridge` and a `service` or `connector` exclude each other. Check it with `python tools/check_plugin.py <folder>`.

Any other plugin may take interfaces for itself with `"claims": ["fuel_level_pct", "range_km"]` (fields of the [Plugin API](api.md); not `measured_at`; not for a package with `bridge`, which takes what is chosen). A plugin whose interfaces another one holds is installed but stays off until that is settled.

## Limits

- It **reads**. Commands to the car (lock, charge, climate) through Home Assistant services are a later step.
- It needs the Home Assistant add-on; in a development setup Car Assistant answers *Home Assistant cannot be reached* and nothing is read.
- A value of the car can come from entities of one Home Assistant only.

## Watching it

The plugin's **Logs** page (switch the log on for a day) says what it reads and what is wrong - once for each trouble, not at every try: *the unit "l" does not fit*, *the entity does not exist*, *Home Assistant cannot be reached; trying again*, *Home Assistant can be reached again*, *Home Assistant reports less than the odometer Car Assistant already knows*. The page of its settings shows live whether the connection stands and what every entity delivers.
