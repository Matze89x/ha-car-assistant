# User guide

🇬🇧 English · [🇩🇪 Deutsch](guide.de.md)

Car Assistant is a logbook and dashboard for your cars. Everything is explained on the page itself; this is the short tour.

## The three levels
Every setting lives on exactly one level, so you always know where to look. *Settings* has three tabs, like a pyramid - you on top, the car in the middle, the whole app at the bottom:
- **User** – you: your login (name, password, passcode, passkeys), your devices and all your notifications (one list for every car), the start car, and the start links for a [web app per car](#a-web-app-per-car).
- **Car** – only the car shown under the title (switch it with the sign next to its name): its photo, video, design and icon, Home Assistant entities, backup, archive and delete.
- **System** – the whole app, for every car and every person: language, units and currency, design, map and fuel prices, sensors in Home Assistant, [MCP access](mcp.md), sources and updates, logs, the address of the app, backup of everything.

## First start
A short guide asks for a language, then your first car (or a demo car), then which functions you want. You can change all of it later.

## Dashboard
*Edit page* lets you move, hide and resize the widgets, and *Edit video or photo* opens the picture window.

## Vehicle data
*More → Vehicle data* shows everything about the car; the pencil opens the form. The form is split into boxes (*Your vehicle, Identification, Technical, Energy, Papers*) and has one **Save** in the page header. Photo, video, design, icon, Home Assistant entities and backup are not on this page: they sit on the **Car** tab of the settings.

## Settings of a car
*Settings → Car* (the car shown under the title):
- **Icon** – the car's own icon for More, the browser tab and the home screen.
- **Photo and video** – up to **10 files per car**, photos and videos together; the oldest drops out when you add an eleventh. Two choices, saved at once: *For the Dashboard* (a photo or a video) and *As the car's photo* (for the car choice and every list). A video needs a photo first.
- **Design** – the car's own design with its own colour wheel; *Like the system* follows the design of System.
- **Home Assistant entities** – optional entities that deliver odometer, fuel level, range and position (this one has a **Save**).
- **Backup and manage** – back up this car, archive it or delete it.

## Pages of a car
**Vehicle passport** (*More → first line of the car*). The head shows name, plate, *make model variant*, the facts you need all the time as chips (year, fuel, power, gearbox, odometer) and the VIN with a copy button. Below: the data in groups (only what you filled in shows), the notes, and the **Equipment** list. Equipment has twelve fixed areas (Comfort, Seats, Controls, Lights, Lines & packages, Interior, Wheels & tyres, Technology & safety, Exterior, Infotainment, Driver assistance, Glazing & roof); you can only move them up and down. Every feature gets a status - standard, special, retrofitted (blue tick) or not fitted (red cross) - and an optional code such as a PR number; the pencil edits one feature, also moving it to another area.

**Trips** holds the **km counters** on top (a counter measures the distance between a start reading and today's odometer or an end reading, for example for the tax year) and the trips below, by month. Tap a trip for its card: distance, duration, average and top speed, consumption chips (an estimate from the car's average), the route on the map coloured by speed and the driving style (needs recorded positions; trips typed by hand show duration and average from the times). *Export* writes PDF or CSV, *Import* reads a GPX file. The **trip analysis** on top of the page (30 days, 90 days, year, all) shows the number and length of the trips, their share by kind, a bar chart of the trip lengths, a heat map of weekday and time of day, and the driving style over all recorded drives (hard brakings per 100 km, average speed while moving, standing, top speed).

**Evaluation** is the cost page: the money spent in the chosen period (days, weeks or months), the share of fuel, service, modifications and parts, a chart per period and a list of every priced entry - tap a category to filter it. Below it come consumption, price per litre and kilometres.

**Fuel** holds the **fuel station search** on top (folded) and the fill-ups below, by month. **Tyres** has a *Recommended pressure* card on top (a tab per season, with normal and fully loaded pressures, and what the car last measured) and a card per set below it (mounted now, size, front and rear axle). **Extra work** shows the odometer and a card per job with interval, progress bar, *last* / *next* and *Reset*; *Add ready-made jobs* adds common jobs with guideline intervals. **Modifications** is a plain list with a quick-add line. **Manual** imports a PDF (with a text layer), an EPUB, a text / Markdown file or a [package with page images](manual-package.md), shows the pages as image or text, lists the chapters, searches, remembers where you stopped and exports an EPUB - the file stays on your server.

**Logs** belong to each plugin and integration: *Info* on its card shows its log (the switch for more detail, its lines, the calls it made).

**Home widgets.** *Attention*, *Vehicle data* and *Position* are always one full row; all others can be small or a full row.

**Buttons.** Secondary actions are light, outlined buttons and a row of buttons stays on one line; only the one main action of a page is a filled button.

## Navigation
*More → Integrations → Manage navigation*: the first four pages sit in the bar, the rest in *More*, in the same order. Integrations and Plugins are always last. Switching a fixed integration off removes its page from the navigation; the lists stay in sync.

## Notifications
Notifications are **one system per person**, under *Settings → User* – nothing about them is set under *Car* or *System*. There you switch them on for the iPhone, iPad or computer you are using (or give the name of your Home Assistant notify service when no port is set) and see your devices. Below, **choose a car** and switch every kind of message on or off with round switches (*Yes* / *No*); the choice *New cars* is what a car you add later starts with. A car you add appears in the list by itself, a removed one disappears. *General* holds messages that are not about one car (for example a new version of an installed plugin). The same words go to a person only once, and identical messages replace each other on a device.

## A web app per car
*Settings → User → Web app for one car* lists a start link per car. Open the link of a car in Safari, tap *Share* and *Add to Home Screen*: the app opens straight on that car and shows only that car - no car switch, no list of the others. It needs your own https address (*Settings → System*).

## Claude and MCP
With the **MCP access** of *Settings → System* you can let Claude read - and, if you allow it, correct - your records from anywhere: see [MCP access](mcp.md).

## Archive and delete
*Settings → Car → Backup and manage*. **Archive** hides the car from the car choice and the Dashboard; it stays greyed out at the bottom of the *Vehicles* page, where **Reactivate** brings it back. **Delete** removes the car and all its data for good.

## Optional services (off by default)
Nothing leaves your server unless you switch it on under *Settings*:
- **Map info** (*System*): shows the location map with OpenStreetMap tiles, fetched through the app, **and** names the start and the end of each trip (from an offline list of the world's cities; with an address set for place names: from that Nominatim-compatible server), so the log book shows names instead of coordinates. The map is off by default. The place names need no internet; an address for place names (a Nominatim-compatible server, https only) is optional and then asked only while the map info is on, and also gives the street of the car.
- **Fuel prices** (*System*): needs **your own** free key from tankerkoenig.de. There is no built-in key.

## Backup
*Settings → System* downloads a backup of everything and restores it; *Settings → Car → Backup and manage* backs up one car (see [Backups](backup.md)).
