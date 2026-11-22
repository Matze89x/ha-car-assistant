# Changelog

🇬🇧 English · [🇩🇪 Deutsch](https://github.com/Matze89x/ha-car-assistant/blob/main/carassistant/CHANGELOG.de.md)

Versioning: `RELEASE.FEATURES.FIXES` – the first number counts releases (it becomes `1` with the first official release), the middle one feature versions, the last one bug fixes and corrections. The stage (Alpha, Beta) stands next to the version.

## 0.5.9 Beta
- The word "Assistant" in the name is shown in the main colour of the design (side bar, About, login); the slogan stays green.

## 0.5.8 Beta
- Dashboard widgets share one look (icon and title left, note or arrow right, at most one line); charts keep their shape, status chips sit on the right; live car data as slim rows with the car's last signal; compact position widget ("parked here since" / "driving here").
- Appointments in one compact column with an Edit button each (Upcoming / Completed); Extra work without ready-made jobs, fitting icons, Reset inside Edit; Modifications by year with sums; Parts & purchases as till receipts; Documents as cards with Edit (title, category, date, valid until, note).
- New setting Date & time (date order, 12 / 24 hours) used everywhere; "Report" is now "Costs" (Kostensicht).
- Updates: optional daily look for a new Car Assistant and for package updates; the dot at the foot of the side bar turns amber and says why.
- Integrations have no on/off button any more (install / uninstall), lists can be sorted; GitHub's hourly limit is reported as such, not as a wrong access key.
- MCP: new read tools (plugins, documents, charging, tyres, settings) and tools to complete a car (vehicle data, documents, tyre pressure).
- Faster vehicle passport equipment list and Modifications page, a calmer logo, name and slogan always one unit (also in the side bar), switch rows with lines above and below, softer trip analysis colours, styles never stale.

## 0.5.7 Beta
- Tyres: the edit page looks exactly like the view (name, sizes front / rear, the four pressures, stored at, notes) with Save at the bottom right of each set; DOT / age and the rear axle name are gone as fields (what was typed there moved into the notes).
- The pressures the car reported are shown below the label as "received from the vehicle on <date>" and are not shown when the car reports none.
- Buttons at the bottom of a block share one size and one line.

## 0.5.6 Beta
- Fixed: the page change between Settings and a car no longer flashes, wobbles or plays its animation twice (instant, also in the installed web app); on screens 760-1000 px wide More shows its list instead of opening the vehicle passport with no way back.
- The vehicle passport columns run on by themselves (no gap under a short group).
- Settings tabs: Car, User, System (Car is the start page); lists can load 4 entries at a time.

## 0.5.5 Beta
- Notifications are now one system per person under Settings > User: choose a car, switch each kind of message on or off (Yes / No), the choice for new cars, general messages (new plugin versions), all devices in one place; nothing about notifications under Car or System any more, and the same message goes out only once.
- Refuels are noticed from the tank level and charging sessions from the battery (time, levels, power, cost, price per kWh, charging loss, 90-day summary); an unfinished entry with a Complete button waits for the bill.
- Fuel page: a cog opens all settings for stations and prices (sources, keys, start values); Austria added as a price source.
- Tyre pressure: every set shows a label like the one in the car, more compact; the location widget has no empty street line and a bigger place.
- Place names: a bigger offline list (172,000 places) with German names.
- Round-cornered Yes / No switches in the Settings (one shared component); sensors in Home Assistant: the own broker (optional) folds away and the switch saves by itself.
- German unit Tage for Home Assistant sensors; updated dependencies (FastAPI, pypdf and more).

## 0.5.4 Beta
- Place names come from an offline list of the world's cities (GeoNames, CC BY 4.0): worldwide, nothing is sent; Nominatim only when an address is set. Fuel prices: an open provider interface (one JSON file per country, docs/fuel-providers.md), France added; Tankerkönig and OpenStreetMap stay. Updated dependencies and CI actions.

## 0.5.3 Beta
- Map and data: map attribution reads © OpenStreetMap contributors with a link on every map; NOTICE lists the optional data services (Nominatim, Overpass, Tankerkönig) with their licences; the address used for place names can be changed under System > Map info (https only).

## 0.5.2 Beta
- Set-up guide, step 3: only the ZIP downloads (install / remove) with one shared token field; the single connection file is folded away; the texts of a bundle can be translated (l10n).

## 0.5.1 Beta
- Plugins: a bundle can carry the connection file (with the token) in step 3 of the set-up guide - one ZIP to install, one to remove, nothing to copy by hand (never stored, administrators only). The demo page is tidier.

## 0.5.0 Beta
- **0.5.0 Beta:** the Beta phase starts - the public test version. New since the Alpha: settings in three levels (User, Car, System), notifications and web apps per car, MCP access for Claude (one switch, one key), the trip analysis and the cost page, the own design and icon of a car. Documentation and screenshots of all pages are renewed with this version; please try it and report what you find (see CONTRIBUTING).

## 0.4.20 Alpha
- **Web app, top distance 30 px** (one number: --app-gap).

## 0.4.19 Alpha
- **Web app, top distance 28 px:** the soft blur iOS lays over the status bar still touched the top edge of the title and the plate at 18 px; the page now keeps 28 px (one number: --app-gap).

## 0.4.18 Alpha
- **Web app, top distance back to a safe value:** the page keeps 18 px below the status bar again (it was 4 px and fell into the soft blur iOS puts over the status bar area). The empty band below the title stays removed. The distance is one number in the stylesheet (--app-gap) in case it needs another step.

## 0.4.17 Alpha
- **Connector, safe and simple:** the key page now says exactly which entry to choose in Claude (*Add custom connector* / *Benutzerdefinierten Konnektor hinzufügen*, not one of the ready-made ones) and that the dialog has only two fields, Name and URL. New choice in the MCP card: *Allow the key in the address* (on = simplest way, only name and address; off = the key must come in an Authorization header and stays out of proxy logs). The app itself never writes an access log, so the key is never in its own log.

## 0.4.16 Alpha
- **Connector guide, simpler:** the key page now leads with the easiest way - name and the address that already contains the key, everything else left empty. The header way (plain address plus an Authorization header) is the second card, marked as the safer one for dialogs that have a request-header field.

## 0.4.15 Alpha
- **Web app, no empty band at the top:** in an installed web app (home screen) every page now starts right below the status bar - the extra distance above the title is gone, and a title without a second line (the car name is hidden there) is only as tall as the title itself. Earlier I only removed the car name and the change-car sign; this is the missing part.

## 0.4.14 Alpha
- **MCP, simpler: one switch, one key.** The level (off / read / read and write) is the only setting and holds for the whole system; there is one access key - *Create access key* once, later *Renew key* (a new one is made and the old one stops working at once) or *Delete*. The per-key level and the list of keys are gone; an existing key keeps working until you renew it.

## 0.4.13 Alpha
- **Values to copy, as fields:** the access key page (key, name, address, header name and value) and the card *Web app for one car* show every value in a read-only field with its own *Copy* button - a tap selects it all. The web-app addresses are now your own https address (never the Home Assistant panel path); without a saved address the card says to save it first. The key page also tells step by step how to add the connector in Claude, and offers the key in the address for connector dialogs without a header field.

## 0.4.12 Alpha
- **MCP card, tidier:** the level, the address for the client, the access keys (with a counter), a framed *New key* form and the latest calls are separate blocks with the same distance and a thin line between them; the address sits in its own box.

## 0.4.11 Alpha
- **MCP, for completing data from everywhere:** a new tool *data_gaps* lists what is missing for a vehicle (empty vehicle fields, refuels without odometer / amount / price, service without cost or odometer, tasks never done, trips without places) so Claude can ask you for the values and fill them in. The lookup an MCP client makes for an OAuth server now gets a plain 404 instead of the sign-in page. The MCP page explains how to add it as a connector in your Claude account (web chat, desktop, phone).

## 0.4.10 Alpha
- **Trip analysis (Trips page):** a new card with a choice of 30 days / 90 days / year / all: number of trips, distance, per trip, driving time, average speed and the longest trip; the share of commute / private / business; how long the trips are (length classes in the units shown); when you drive (weekday × time of day as a heat map); and the driving style over all recorded trips with time stamps - hard brakings per 100 km, average speed while moving, standing share, top speed.

## 0.4.9 Alpha
- **Notifications per car (Settings → Car):** turning notifications on for a device now happens on the *Car* tab of each car - the iPhone / iPad / computer you are using is switched on for that car (one device can serve several cars, and the web app of a car works the same way). *User* shows your devices with the cars they serve and lets you remove them; the test message is sent from the car's tab to that car's devices. **MCP:** the level now has its own *Save* button.

## 0.4.8 Alpha
- **Home video no longer disappears (iPhone):** when you leave Home while the video is still playing and come back, the page used to show an empty box until the video was loaded again. Now a picture of the moment you left is kept and shown at once, and the video goes on from there (a video that had finished still stands on its last frame, as before).

## 0.4.7 Alpha
- **Web app, more room at the top:** in a car's own web app the line with the car's name under every page title is gone on all pages, so every page starts directly (it only repeated what the app already is). In the normal browser nothing changes.

## 0.4.6 Alpha
- **More, tighter on a phone:** the empty band between the title *More* and the first list is gone.

## 0.4.5 Alpha
- **Web app, quieter:** in an installed web app (home screen) the little *change car* sign next to the car name is hidden everywhere - every car has its own web app; the card *This app shows only …* at the bottom of More is gone. The way back to all cars stays on Settings → User, in the card *Web app for one car*, and shows only while that device shows one car.

## 0.4.4 Alpha
- **Car tab and sensors, tidied:** photo and video no longer need a Save button - choosing what Home shows or the car's photo saves at once; the three choices of the video background wrap their explanation inside the tile instead of running out of it (phone: one under the other). In the card *Sensors in Home Assistant* (System): Save on its own line, below it a short text for each of the two actions and then one line with the buttons *Read again* (Home Assistant to the app: linked sensors such as odometer, tank, position) and *Send again* (app to Home Assistant: all car sensors; switched off while MQTT sensors are off).

## 0.4.3 Alpha
- **Settings tidied:** the general app icon is fixed (no icon card on System any more), the car's own icon is its own card at the top of the Car tab (before photo and video); *Read linked sensors again* (and *Send sensors again*) moved into the *Sensors in Home Assistant* card, the card *Update data* is gone; the line about one colour for everyone is removed from the colour wheel.

## 0.4.2 Alpha
- **Settings in three levels - User, Car, System:** the tabs are now *User* (what is personal), *Car* (everything that belongs to one car) and *System* (the whole app). *Design* and *Region* are cards of System now. The new *Car* tab is about the car shown under its title (change it with the switch next to the name) and holds: photo and video (moved from the passport), the car's own design with its own colour wheel, the car's icon, the Home Assistant entities, notifications for this car, and backup / archive / delete (rearranged as clear rows). Under *User* you choose per car whether you want to be notified at all, and say how; which events you get for a car is chosen on its Car tab. The passport no longer carries design, entities, photo or backup. Fixed on the way: a message after a save on a page address with an anchor was lost.

## 0.4.1 Alpha
- **Changelog links work in Home Assistant:** the language link and the documentation links in both changelogs are full addresses now, because the update dialog of Home Assistant shows the changelog without the repository and turned the relative links into a page that could not be opened. A test keeps it that way. The versioning note at the top describes the new scheme.

## 0.4.0 Alpha
- **0.4.0 Alpha:** the app is now in its Alpha phase. The version and the stage live in one file (`release.json`) and are written everywhere with `tools/release.py`. Scheme: release.features.fixes – a new feature raises the middle number, a bug fix the last one. Page documentation and new screenshots follow with the Beta.
- **MCP access (Settings → System):** Claude Code (or another MCP client) can read - and with the highest level correct - the records of your cars. Off by default and switchable only with a user, a saved external https address and an open port; own access keys per client (shown once, stored as a hash) with the level read or read + write that never exceeds the server level; no way in through the Home Assistant panel or from other websites; wrong keys are slowed down and blocked, calls are rate-limited and logged. Tools: app info, vehicles, vehicle data, records, costs, plugin logs, add / change / delete a record. See `docs/mcp.md`.

## 0.3.585
- **Links with an anchor keep their place:** on the Evaluation page the category links of the expense list (All / Fuel / Service / Modifications / Parts) no longer jump to the top of the page – the list stays in view. The same works for every other link with an anchor.

## 0.3.584
- **Web app for one car:** under Settings → User there is now “Web app for one car” with a start link per car. Add that link to the home screen and the app opens straight on that car and shows only that car – no car switch, no list of the others (under More a button brings all cars back on that device). The web app's scope is now the whole app, so no link opens the phone's little in-app browser any more – that was the odd, unclickable page after switching cars.
- **Notifications lead to the right page:** a message about one topic opens that page of that car (appointments, tasks, tyres, trips); about several topics, the car's overview. A device that turned notifications on inside a car's web app now only gets that car's messages (still per person and per car in the choices); the others get all, as before.
- **Demo cars:** much more data in every area (service, appointments, modifications, parts, documents) and every kind of message has something to say per car – low tank or battery, a soft tyre, an open door or boot, a car warning, an upcoming service, due tasks and appointments, a trip that just ended.

## 0.3.583
- **Evaluation is now the cost page:** on top the money spent in the chosen period (days / weeks / months) with the average per period, all costs per 100 km and the most expensive entry; “Where the money goes” splits it into fuel, service, modifications and parts (tap a category to filter); below the cost chart a list of every entry with a price – refuels, service jobs, modifications and parts – grouped by month with a subtotal, filterable by category, each row leading to its page. Consumption, price and kilometre charts follow underneath.

## 0.3.582
- **Dashboard widgets, new look:** every tile gets a tint and a colour line in its own colour and bigger figures; small charts show the trend – consumption and price per refuel as sparklines, the last seven days of driving as mini bars with the weekly total; the consumption tile shows how the last fill compares to the average; the next appointment shows a big countdown in days; the service tile a progress bar of the next due job; “Needs attention” as a clean list (title on top, the details in small text below, two columns on wide screens).

## 0.3.581
- **Buttons top right, everywhere:** the vehicle edit page has its Save in the page header (the extra Save bars inside the groups are gone), the modifications page has its Add in the header (the one next to the field is gone). Saving returns to the view page.

## 0.3.580
- **Tyres, one edit page:** the page opens on Summer; the tabs are always Summer / Winter / All-season in the usual design (no dots). The tyre pressure sits at the top of the set tile as “Tyre pressure”: the value the car measured, the recommended one in brackets. Edit is one page with one Save (top right) for the pressures, all sets, which one is mounted and removing sets – no Cancel, no Add; a blank set per season is always there.
- **Passport:** the two columns are separated cleanly again (a wide row no longer shifts the divider line); a single tile is paired with an empty one.
- **Documents:** the upload button in the header is the only one and works – it opens the file picker and uploads at once, the category is guessed from the file name (typing a title used to submit the form too early).
- **Extra work:** field, “Reset” and Edit in one line at the bottom of the tile, phone-friendly.
- **Integration pages:** the head bar runs over the whole width, its content keeps the maximum width of Car Assistant.

## 0.3.579
- **Report:** new chart “Price per unit” (price per litre / kWh over time with the trend line), following the same filter.

## 0.3.578
- **Tyres:** the recommended pressure now sits inside the tyre set tile (normal and loaded, front and rear in one tile). Saving the pressures returns straight to the page; in edit mode the header button is now “Cancel” instead of an extra “Done”.

## 0.3.577
- **Start page video, done properly:** when the video has played to its end, its last frame is kept as a picture; coming back to Home shows that picture at once and does not load or start the video again (it vanished on the phone when it had to be loaded and sought again). A tap plays it again.

## 0.3.576
- **Navigation list (More → Integrations):** no more drag & drop – the drag handle in every row is gone, the icon sits right at the edge of the row, and only the arrows move a page up and down. Lighter, and nothing gets in the way on a phone.

## 0.3.575
- **Report extended:** costs per period as stacked bars (fuel, service, modifications, parts, with totals), kilometres per period, and a dashed trend line (average of 5) in the consumption chart. All follow the days / weeks / months filter.

## 0.3.574
- **Tyres:** the read-only view uses the full width – every value (axle sizes, DOT, storage, pressures) on its own line instead of two columns.

## 0.3.573
- **Lighter on the GPU/CPU:** the endless pulsing dot and the large glow of running plugin tiles are gone (they repainted every tile all the time), the green start button has no big shadow, and the side bar blurs less (12 px, no colour boost). Looks the same, costs much less – especially on the Integrations and Plugins pages.

## 0.3.572
- **Vehicle passport:** fix – the choice tiles (fuel, energy view) pushed long names such as “Autogas (LPG)” over the edge of the card on a phone; the names now wrap inside the tile.

## 0.3.571
- **Start page video:** it plays once per visit; when you come back to Home it stands at its last frame instead of starting over or vanishing. A tap on it plays it again.

## 0.3.570
- **Dashboard:** “Needs attention” shows the four most urgent points and “+n more” as a link to the tasks, so the widget stays compact.

## 0.3.569
- **Google search helper (off by default):** under *Settings → System* you can switch on a magnifier next to the vehicle fields you may not know by heart (variant, engine code, oil specification, HSN/TSN and more). A click opens a Google search for your vehicle and that field in a new tab (e.g. “… 2.0 TDI - Engine oil specification”). The app sends nothing itself.

## 0.3.568
- **About page:** left-aligned and more compact, in two columns on wide screens (the app, the libraries and the credits on the left, what is installed per vehicle on the right); one column on a phone.
- **Dashboard:** the content has the same fixed width as the other pages.

## 0.3.567
- **Buttons:** fix – the tighter icon padding of 0.3.564 also hit round icon-only buttons (uneven padding on the left). It now applies only to buttons with a visible text and never overrides the round header buttons.

## 0.3.566
- **Position widget:** besides “Here is your car” it shows the place (like the trips) and, small below, the street – looked up once per spot when the map info is on. The map is lower, zoomed closer with the car in the middle, and the pin is a car in the accent colour.

## 0.3.565
- **Navigation rebuilt like a one-page app:** the bar (bottom bar on phones, side bar on wide screens) now stays in the page when you change pages; only the content is swapped and the bar just changes its active entry, so the marker glides once. No more page cross-fade (it made the bar flash), no layers, no second glide.

## 0.3.564
- **Buttons, one system:** the header buttons of all list pages (add) and the tyres page (Edit coloured, Done plain) now look like those of Integrations – icon plus text on wide screens, a round icon on phones. Buttons with an icon and a text have less padding on the icon side.

## 0.3.563
- **Vehicle passport:** fix – a car with a first registration but no inspection appointment gave a server error (500) because the estimated inspection date was handed over as a date object instead of text.

## 0.3.562
- **Report:** the period filter uses the usual tabs (Days / Weeks / Months) with the number of periods as a select on the right, in one row.

## 0.3.561
- **More:** on a tablet or a wide screen it opens the vehicle passport at once (no empty “Choose a page” screen); the phone shows the list. The version line at the bottom of More is gone.

## 0.3.560
- **Mobile navigation:** the glide of the marker no longer uses separate browser layers (they were drawn as rectangular pictures with a distorted edge around the round field while moving). The marker simply slides from the old to the new entry in the live bar; the layer tricks for the bar and its entries are removed.

## 0.3.559
- **Integrations page lighter:** the icon choices of the navigation list are no longer repeated in every row (the page was 270 KB with over 500 icons, now about a quarter of that); they appear when you open an icon.

## 0.3.558
- **Notifications per car:** under *Settings → User → Notifications* you pick a car (tabs, when there is more than one) and choose the events for that car on its own. Until you choose, a car uses your general choice.
- **“Trip finished” arrives at once:** the check only ran every six hours, so the message came late or not at all; now a finished drive is announced right away.

## 0.3.557
- **Report:** fix – the new period filter broke the links in 0.3.556 (a name clash); they work now.

## 0.3.556
- **Report:** choose the grouping – days, weeks or months – and how many periods to show (days 30 by default, up to 365; weeks 4, up to 52; months 6, up to 60). The chart follows the same window.

## 0.3.555
- **Tyres page redone:** it is now a clean read-only view with larger tiles – tabs (Summer/Winter/All-season) only for seasons that have a tyre set or pressures, the pressures as plain values, and “Measured values” only when the car reported some. **Edit** (top right, icon only on phones) opens the forms with all three seasons; **Done** returns.

## 0.3.554
- **Dashboard:** without a range reported by the car, the range is estimated from your refuelling (tank size ÷ average of the last five full-to-full intervals, minus the km since the last full tank) and marked “≈ … estimated from refuelling”. Needs a tank size and two full tanks; the car's own figure always wins; electric cars are not estimated.

## 0.3.553
- **Fuel page:** the additive card at the top is gone (the additive keeps its own page and the dashboard reminder). The additive package is now called *Additive* / *Additivzusatz* (source, version 4).

## 0.3.552
- **Folding groups in two columns:** in the equipment of the vehicle passport each column is its own stack. Opening a group on the left no longer pushes the groups on the right far down; they all stay where they are. On a phone it is one list in the original order.

## 0.3.551
- **Header buttons on every page, icon + text (a round icon on a phone), always at the top right:** *Documents*: one *Upload data* button (the second one is gone); *Manual*: *Export*, *Replace*, *Delete* (with a question before everything is removed); *Plugins* and *Integrations*: *Check for updates* and *Add*; the *Add* tab: *Update list*; *Sources*: *Add source*.
- **Coding:** the list is ONE column on every width; the chosen byte sits in one row, like in a diagnostic tool: *Byte N* at the left and its bits to type next to it (the extra original line is gone).

## 0.3.550
- **Web app name:** *Car Assistant* is no longer cut to *Car Assistan* when you add it to the home screen.
- **Navigation:** a second tap on the entry of the page you are on scrolls to the top, nothing reloads or jumps.
- **Vehicle passport:** in the navigation settings it is the fixed FIRST entry of *More* (not sortable, not hideable), no longer above Home.
- **Trips:** a drive is closed as soon as the ignition goes off (not ten minutes later), so its place names are ready when you open the trips; place names are only the **place** (no street): from place to place. Names kept earlier with a street become the place.

## 0.3.549
- **Set up on the tile:** a plugin with a set-up guide that is not set up yet shows **Set up** as the one main action on the right of its tile (it gives way to *Update* / *Open* once it is set up); the guide stays on its settings page, at the top.

## 0.3.548
- **Set-up guide on top:** on the settings page of a plugin that brings a set-up guide, its card is now the first one (it was below the settings fields).

## 0.3.547
- **Trip map:** the map of a trip is **square** (as wide as high) and the route sits in its **middle**; it is dark in a dark design and light in a light design (like the location map); below it a **legend** shows what the colours mean (a scale from slow to fast in your speed unit, the start and the end). The texts of the trip card (points, hard braking, average while moving) show up again.
- **Driving style:** two by two on a phone as before, **one column** on a tablet and on the web.
- **Place names for older trips:** with the map info on, up to 1500 of the latest trips and 100 lookups per run (the next visit goes on).

## 0.3.546
- **Map info with place names:** the switch under *Settings -> System* is now *Show map info (map and place names)*. Switched on, the app also asks OpenStreetMap (Nominatim) once for the street and place of the start and the end of each trip and writes the name into the log book instead of the coordinates; the answers are kept, a name you typed yourself is never touched, and nothing is asked while the switch is off.

## 0.3.545
- **Updates keep the approval:** a package (a service, files, bundles) you allowed when installing it stays allowed when you press *Update*; the new description is approved with that click. Nothing is updated on its own, and a package you never approved stays unapproved. No second approval step after an update any more.
- **Coding, new layout:** the original code is ONE line (it scrolls sideways); below it the current bytes stand free of it - only a changed byte shows its old value (*was 2A*); a tapped byte opens one under the other its original bits and its current bits (typed or ticked) and the eight bits, each with a **note**; bits that belong together can be **grouped** (a name and a value as a number, like in the old dashboard); a dot marks bytes with notes. Everything looser. The original value can be changed by a person at any time (only a plugin's write keeps it).
- **Plugin tile in ONE line:** *Start/Stop*, *Info* and *Settings* on the left and the one main action on the right - *Update* when a newer version is offered (its version as a badge in the head), otherwise *Open*. The *More* menu is gone: the set-up guide, *Show in the bar* and *Uninstall* are on the settings page.

## 0.3.544
- **One Info page per plugin:** *Interfaces*, *Logs* and the debug switch are now one page, *More* -> *Info*: overview, what the plugin offers and uses (interfaces, files), then its log with the debug switch; jump links at the top, empty interface groups are left out. The old addresses lead there. The tile's *More* menu is down to *Set-up guide*, *Show in the bar*, *Info* and *Uninstall*.

## 0.3.543
- **Docs for plugins:** the short guide names `setup` and `advanced` and points to the full description; the pages that spoke of the old tile buttons (*Logs*, *Debug* ...) now say *More*.

## 0.3.542
- **Set-up guide, tidied:** step 2 has ONE token box with the two choices side by side (keep the existing token / make a new one; on a phone one under the other) and the settings below it; short step names; in step 3 the connection file sits in its own line with a light *Download* button and *Finish* is the one main action; the same gaps and the same *Back* / main action row on every step.

## 0.3.541
- **Set-up guide, existing token:** when the app has no token yet, step 2 also offers *Use an existing token* (one that is already in the file on the device). It must look like a Car Assistant token and may not be in use elsewhere; only its fingerprint is stored, and from then on it is fixed - only *Make a new token* replaces it.

## 0.3.540
- **Set-up guide in three fixed steps:** 1 check (address and VIN read-only, *Next* shut until both are there), 2 token and settings (*Make a new token*, or - when one exists - its mark and *Keep using the existing token*, compared with the fingerprint; the settings with the advanced ones folded; *Next* saves), 3 files and instructions (the connection file, the packages, the text, *Finish*). The token only travels inside the pages and is never stored. A setting may be marked `advanced`.

## 0.3.539
- **More, narrower list:** on a tablet or desktop the list at the left of *More* is about 310 px wide (310 to 330 px) instead of a share of the screen (about 380 px); the page gets the rest.

## 0.3.538
- **Plugin card in order:** three buttons with words - *Stop/Start*, *Settings*, *More* - and the one main action *Open* on the right. Everything else (set-up guide, bar, interfaces, logs, debug, uninstall) sits under *More*, each with a line of explanation; no icon-only buttons, no hover tips.
- **Set-up guide for plugins:** a manifest may bring `setup` (steps with text, the token, the connection file and the downloads on one page, after a check that an https address and the VIN are there). `{vin}` is a new placeholder of the connection file; a service finds `external_url` and `vehicle_vin` in `settings.json`.

## 0.3.537
- **Fix: the order of the navigation editor now also rules *More*.** The bar followed the order, but in *More* the pages of integrations (Coding, ...) were always listed after all fixed pages. Fixed pages and integration pages are now one list in the order you set (per car).

## 0.3.536
- **Pages of integrations: date and access codes.** New field type `date` (date picker, validated) and page option `order` (list sorted by a field, e.g. a history newest first); new field type `secret` for access codes: hidden until *Show*, empty field keeps the saved code, never in the search text, never given to a plugin, left out of the plain vehicle backup (*Backup with access codes* makes a separate file), and the system backup now says it contains them. A second list is simply a second page (see `docs/integrations.md`).

## 0.3.535
- **One list for the pages:** the separate *Integrations* group in the navigation editor is gone. An integration with a page sits in the same sortable list as the other pages, with its own switch; one added later joins at the end. Switching it off or removing it takes it out of the saved order, so the others keep their places.
- **Coding:** below the byte grid a selected byte shows one row with two windows (the original, fixed - and the new value as bits you can type) and the bit rows *Bit 0 ... Bit 7* with tick boxes; every tick changes the new value in the field of the row. A person can now change the original value at any time (only a plugin's write still keeps it).
- **Coding:** every control unit row is one line (address, name, sub-line, changed bytes; too long is cut with ...), also the values inside a row.

## 0.3.534
- **VIN as a key:** the VIN is typed in by a person in the vehicle data. A plugin can send `vin` through the Plugin API and it is only compared: a match shows *Confirmed by the car*, a different VIN refuses the request (`409 vin_mismatch`, nothing stored). A plugin never writes it.

## 0.3.533
- **Tappable page references on the page image:** a package can carry the position of each "page 137" on a page (`t/NNN.json.gz`); the reader lays a faint red area over it (strong on hover) that jumps to the page, using the page offset. Optional and backward compatible (see `docs/manual-package.md`).
- **Docs:** the example of an integration without code now lives in the folder `example-stations` (folder name = identifier, the package checker accepts it).

## 0.3.532
- **Simple manual package:** a zip with only numbered page images (`001.avif`, ...) is enough; `meta.json` and the text index are optional.

## 0.3.531
- **Manual with page images:** a manual can be imported as a package (zip with `meta.json`, page images and an optional text index); the reader shows the page as an image or as text, chapters can have sections, and a reference like "page 137" jumps to the right page using the stored page offset. The images belong to the car and are included in the vehicle backup and the system backup (see `docs/manual-package.md`).

## 0.3.530
- **CI fix:** the design tests read the stored accent colour and failed on a clean checkout (GitHub) because no database existed; each test now gets its own empty database.

## 0.3.529
- **Mouse pointer like in Home Assistant:** a plain arrow over the page and its text, a hand only over buttons, links and other things you can click, the text cursor only in fields you type into.

## 0.3.528
- **Fix, notifications:** a notification was never sent: the sender address the push library checks was rejected, so every send stopped before it left the server. Now it is accepted, and a test sends one to a local test server and checks what leaves.

## 0.3.527
- **Tick boxes:** the colour gradient of a ticked box now covers the whole box including its border, so no light flashes appear at the top and bottom edge; the glow ring around ticked boxes is gone for real.

## 0.3.526
- **Account card:** *Add passkey* now looks like the other small buttons (*Change*, *Set passcode*, *Add user*), and on a phone these buttons show only their icon.

## 0.3.525
- Under the address in *Settings -> System* a line says that passkeys and notifications are only switched on once an address is saved.

## 0.3.524
- **Fix, notifications:** registering a device crashed on the server (the text lookup had no language), so every phone ended with a generic error after allowing notifications. Now the device is saved, and a test covers the whole way from the key to the card.

## 0.3.523
- **One place for the address:** the external address lives only under *Settings -> System* (no longer moving to *User* when a port is set). Under *User*, passkeys and notifications show up only once that address is saved.

## 0.3.522
- **System page:** without a user the external address shows only the notice and one link (no dead form, no repeated sentence); the broker host no longer says "optional" twice; fields one under the other keep a clear gap.

## 0.3.521
- **Notifications:** the permission is asked first, straight from the tap (iPhone refused it after other waiting); a failure now says the step and the real reason; on an iPhone or iPad outside the home-screen app the button is replaced by the plain instruction to add the app to the Home Screen.
- **Tidier settings:** the address appears once (the field), the tick boxes sit level with the first line of their text without a glow ring.

## 0.3.520
- **Direct access, short:** the row now reads *On* (or *Off*) followed by *Port: 8099*; the long wording is gone.

## 0.3.519
- **Address with a fixed `https://`:** in *Settings -> System* you only type the host (`auto.example.com`); `https://` stands in front and cannot be changed, `http://` is refused. The field is one piece that also fits a phone.

## 0.3.518
- **System page on a phone:** the port of the direct access (for example `:8099`) no longer sits tight on the status badge; they stand side by side and, when narrow, one under the other with a gap.

## 0.3.517
- **Security headers everywhere:** the refusals that never reach a page (wrong API token, locked direct access, redirect to the sign-in) now carry the same headers (`nosniff`, referrer policy, content security policy) as every other answer.

## 0.3.516
- **Ready for the public:** `SECURITY.md` (how to report a vulnerability, what the app protects), `CONTRIBUTING.md` (rules, tests), issue forms for bugs and ideas, a pull request checklist, and the CI and license badges on the start page. The install page now starts with *Install from the repository*; the local app is the alternative.
- **Cleaned up:** two doc examples named a real car-service address and a head-unit brand term; they are neutral now. The internal working notes and the write-guard script are no longer part of the repository.

## 0.3.515
- **Security review of the ways in from outside:** a signed-in user who is *not* an administrator could download the full system backup (every user, token and car) or restore over it from the direct address, and change system-wide settings. These routes - backup, restore, factory reset, external address, map, fuel key, logs, source updates, language, units, design and colour - are now for administrators only (inside Home Assistant nothing changes). Personal preferences, notifications and list size stay open to everyone. A test covers it.
- A GPX file is now read with the hardened XML parser (like the EPUB import).
- The *Back to the original* button of the design is gone again (it was meant for car icons, which have the bin next to them).

## 0.3.514
- **The app icon is fixed, the cars have their own:** the icon of the app itself can no longer be replaced - its coloured frame follows the colour of your design (Classic red keeps the original red-to-green). Every car keeps an icon of its own (logo or photo) that gets the same frame in the design's colours; it is the car in *More* and the favicon, iPhone and web-app icon of that car's pages. There is no icon per user.
- A car's own icon can be removed again in *Settings -> Design -> Icon* (the bin next to it): the car then wears the original icon.

## 0.3.513
- **Your own icon gets the coloured frame:** a logo or photo you upload for the app or for a car (Settings -> Design -> Icon, or the icon in *More*) is put into the frame of the real icon - dark tile, rounded corners, red-to-green edge - and from it the app makes every size: browser favicon, iPhone home-screen icon, web-app and Android icons. The same icon shows in *More* and everywhere else, so a car can wear its own brand logo.

## 0.3.512
- **One click for packages with code:** the page of a package with a service, files or a page of its own now shows *What this package will do* (program, requirements, addresses it answers on, what it connects to, files) **before** anything is installed, and its one button *I trust it - approve and install* installs and approves in one go. No second step afterwards. Only an administrator can do it; a package without code keeps the plain *Install*. A later update that changes the description still needs a new approval.
- **First start:** the first page now asks for the language **and the design** (with the colour wheel) before *Continue*.
- The *Auto* tile has a neutral grey edge now (the old edge flickered between dark and light designs).

## 0.3.511
- **Design page:** *Your colour* now sits inside the *Colours* card, right below the designs, and shows only while *Light*, *Dark* or *Auto* is chosen. The designs are simply called *Light*, *Dark* and *Auto* (*Classic red* stays).

## 0.3.510
- **Fewer, clearer designs:** *Classic red* stays exactly as it was. The other designs (Ocean, Sunset, Light blue, Light, Day / night) are replaced by three that take your colour: *Light + colour*, *Dark + colour* and *Light / dark + colour* (follows the device). A design you had chosen moves to the nearest one and keeps its colour (also per car and per user). The files of a theme of your own in the data folder keep working.

## 0.3.509
- **Colour presets:** the ready-made colours are real circles again (a general button height had stretched them) and larger on touch screens (phone, tablet). The wheel itself works with finger and mouse.

## 0.3.508
- **Your own colour:** two new designs, *Dark + colour* and *Light + colour*. Pick any colour on a colour wheel (or type a value, or tap a ready-made one): the whole app follows at once and the colour is kept for everyone. From the one colour the app works out the button gradient, the light shade for text and the text colour on a button (white or dark, whichever stays readable); the lightness is kept in a range that suits the background. Green, amber and red for done, soon and overdue never change. The pages a package shows (frames) take the colour too.
- **Plugin sources:** the closed *Add source* card had an extra strip below its row; now the space above and below is equal.
- In light designs the last odometer drum uses the accent colour with a readable text colour.

## 0.3.507
- **"Connector API" is now the "Plugin API"** in every text, page and doc (the address `/api/v1` and the file `docs/api.md` stay, so nothing breaks). The page about integrations now says clearly: an integration has no API and no token; only a plugin connects the outside and uses the Plugin API.

## 0.3.506
- **Start page with a documentation overview:** the README now lists every document in three groups (use it / connect your own / work on the app) with one line each, and `docs/README.md` is the same list inside the folder. English and German are kept in step; a test fails when a page has no German twin or is missing from the start page.

## 0.3.505
- **Architecture page** (`docs/architecture.md`): three diagrams that GitHub draws by itself - the whole system, the way of a plugin from the outside to the page, and sources / packages / services for plugins and integrations - plus the steps to build your own.
- **Examples:** a new example of an integration without code (`docs/examples/integration-pages`) and an overview page for all examples; a test keeps every relative link in the docs and every example package readable.
- **Checked the background connections:** the worker loop keeps going when one job (MQTT publish, reminder check) fails; two new tests prove it.

## 0.3.504
- **Documentation tab of the add-on rewritten:** first steps, what the app does, every option, who can reach it (port and user), MQTT, privacy (what is online only when you switch it on), foreign-code services, backup. Every link is a full address now (Home Assistant cannot follow relative ones). Doubled sections are gone, the old `external_url` / `access_password` hints too.
- **Screenshots page** (`docs/screenshots.md`, linked from the README): the app in use with the demo cars, desktop and phone, English and German pictures. A test keeps the links and pictures from breaking.

## 0.3.503
- **Vehicle passport:** the unit was shown twice (in the label and in the value); now only in the value. Tank size and oil amount follow the units of *Settings -> Region* (gallons for US / UK).

## 0.3.502
- **Quiet log:** with the log level *warning* or *error* the add-on no longer writes its "Starting Car Assistant" line. The few lines of the start-up system before it (s6) come from the Home Assistant base image and cannot be switched off.

## 0.3.501
- **Roadmap tidied:** units, notifications per user, reminders from integrations and Coding are marked as done; what is next is listed.

## 0.3.500
- **Trips:** the "more" button loaded further trips into the km counters; fixed. Adding a km counter is a plus in the heading of the counters (the panel opens right under it); the text button below the list is gone.

## 0.3.499
- **Trips:** the add panel is titled *Add a trip manually*, has more air below it and its save button on the right. A trip is checked for sense: not in the future, not more than 3000 per trip, the end time not before the start time. New km counters no longer offer the kind *Tax* (existing ones keep it).

## 0.3.497
- **Home, first steps:** *Connect the car* (no bracket text) opens the plugins of the car directly.

## 0.3.496
- **Fuel:** the button to the evaluation in the header is gone - the evaluation has its place in *More* (and may be switched off), and the header keeps export and add.

## 0.3.495
- **Notifications only on https:** the switch and the test button for browser notifications appear only when the page is opened through its https address; on any other address the card says where to go (your external address) instead of offering something that cannot work.

## 0.3.494
- **Service and Parts:** a period with only one card shows it across the whole row instead of leaving the right half empty.

## 0.3.493
- **Docs:** the plugin guide points to tools with a page of their own (`kind: "frame"`, also for integrations with a service).

## 0.3.492
- **MQTT sensors in the Home Assistant configuration of the add-on:** *Sensors in Home Assistant (MQTT)* is now an option under Settings -> Apps -> Car Assistant -> Configuration (switch on, and optionally the host, port, user and password of an own broker). The switch in the app still works; what is set there wins.

## 0.3.491
- **MQTT sensors can be set up in one go:** the switch *Create the sensors in Home Assistant* is always shown (Settings -> System), and the first own broker you enter switches the sensors on - no second visit to find the switch.
- **Saving the MQTT settings no longer fails** when the broker cannot be reached (switching the sensors off used to end in an error page).

## 0.3.490
- **Tyres like every other list:** the sets sit in two columns (one on a phone), a tap on a set opens it for editing in place (*Cancel*, *Delete*, *Save* under a line, right), the facts fit the half-width card and the list loads in batches with the chosen size. Tyre pressure: one row per load, heading left, front and rear next to it.

## 0.3.486
- **Tap a card to edit it in place:** on Service, Parts, Appointments, Mods and Tasks a tap on a record card turns its fields into inputs; underneath, below a line, *Cancel*, *Delete* and *Save* (right). Escape or *Cancel* closes it again. The *Edit* button is gone.

## 0.3.484
- **Vehicle passport:** every *Save* in edit mode saves everything that changed and falls back to the passport view. The VIN sits in an engraved slot - one unbroken line, scaled to fit, with the copy button inside the slot.
- **"Service book" is now simply "Service"** (tab, module, page title).

## 0.3.481
- **Pages of a package are pages of their own (no iframe):** the entry in *More* opens the page of the package's service as the whole window; Car Assistant only puts a head on top of its HTML - back to *More*, the name of the package and, at the right, its version (no script, not fixed, follows the design of the car). The page gets language, car, units, design and the addresses of the design variables, the kit and the OpenStreetMap tiles (`/tiles`). Replaces the embedded frame of 0.3.475.

## 0.3.480
- **Trips like in a logbook:** a trip card shows only the essentials (date and time, route, distance); tap it and the whole trip opens - facts, map, speeds, driving style, edit. On top three figures for the last 30 days (trips, distance, drive time).

## 0.3.479
- **Trips as cards:** every trip is a card (two columns, one on a phone) under a heading per period - *Today*, *Yesterday*, *This week*, *Last week*, then the month - with category, duration, average speed, odometer and purpose; the title of a recorded trip opens its map and driving style. Search runs over all trips, the next batch loads while scrolling. The km counters are cards, too. **Export** (download icon): choose everything, last 7 / 30 days, this or last month, this or last year or your own dates, as PDF or CSV; the GPX import sits there as well.

## 0.3.477
- **An integration may carry a service** (for tools with a page of their own, e.g. an editor): same approval as a plugin's service, but no token, no `CA_API_URL` / `CA_API_TOKEN` and no Connector API. Its `frame` pages and its entry in *More* exist only while the service runs; the version of the package is shown at the right of the header. Plugins with a service can show frame pages as before.

## 0.3.476
- **Design contract:** one page (`docs/design-contract.md`) says what stays the same in every design, page and package - identity (name, slogan, colours, fonts, logo, banner), the variables everyone can rely on, the rules a design must keep, the components and page patterns. Tests keep it true: every design has all the variables and is readable (contrast 4.5 : 1 for text, 3 : 1 for accent and status colours). The *Sunset* design now has dark text on its orange buttons (white was too faint).

## 0.3.475
- **Frame pages for packages with a service:** a package can show a page of its own service inside the app (`kind: "frame"`, docs/plugins.md): the usual header with the package's version on the right, the page below it growing with its content, an entry in *More* while the service runs. The page gets language, car, units and design; the service gets `X-CA-Vehicle` / `X-CA-User` (no cookies), changing requests need `X-Requested-With: frame`. The design goes along as variables (`/frame-theme.css`) and as a small kit (`/frame-kit.css`), so such a page matches every design. The approval page says that the package brings a page with its own code.

## 0.3.474
- **Lists, one way (step 1):** a person chooses under *Settings → User → Lists* how many cards a list loads at a time - 10, 25 or 50 (a page loads faster with fewer); the next batch loads while scrolling. Service book, parts and fuel put a heading above each period (*Today*, *Yesterday*, *This week*, *Last week*, then the month) and show their cards in two columns (one on a phone).

## 0.3.473
- **Package page, clearer:** who and what at a glance (kind, version, author, source as chips), the description as one lead sentence with *Read more* for the rest, the settings listed as rows - label on top, help text below - with headings and notes where the package has them, files likewise, and the install button docked on the right.

## 0.3.472
- **Fuel page:** the fill-ups are cards again (two columns, one on a phone) under a heading per month, ten at a time - the next ten load while you scroll; search works over all of them. **Export** (the download icon): choose what to export - everything, last 7 or 30 days, this or last month, this or last year, or your own dates - as CSV or PDF.

## 0.3.471
- **Compact record cards:** the thin divider and the *Edit* button stay at the bottom right, but with less space around them (about 14 px less height per card).
- **Buttons stand out more:** every button and icon button has a clearer edge (a new design value `--btn-edge`) and the small icons in the lists show it permanently; the icon is white, not grey. The *Edit* of a card is a real small button, docked on the right edge of the card.
- **Small icon buttons** (the pencil and cross in lists) always show their outline and fill like the other buttons, not only when you touch them.
- **Edit:** under every record card (appointments, service, parts, tyres, extra work) the pencil is followed by the word *Edit* again - a lone pencil got lost. The small rows of the lists (fuel, modifications, trips) keep the pencil only.

## 0.3.464
- **Appointments:** the *.ics* button is an export icon (arrow down, round like the other icon buttons); the label stays for screen readers.

## 0.3.463
- **Extra work and list cards (design step):** the cards of every list (appointments, service, parts, extra work) have the same inner space (18 px) and the same distance (14 px) like all other cards; the *reset* row of an extra job has a short fixed field for the odometer and a pencil for editing (like every other record) instead of three dots.

## 0.3.462
- **Documents page rebuilt:** instead of a table with red *Delete* buttons, one card with a row per document - a coloured chip for its category (manual, invoice, insurance, registration, inspection report, other), the title with category, date and size beneath, a delete icon. Uploading is one button: fill in title and category, choose the file, it is uploaded at once. Empty state like the other pages.

## 0.3.460
- **CSS tidy-up (design step 3, part 2):** unused style rules (about 50 selectors of removed features such as the old car menu, source rows and equipment category editor) are gone, neighbouring rules of the same selector are merged and 13 later rules moved up into their earlier twin - all provably without changing any result. Checked by rendering 26 pages at two widths (28,000 elements) before and after: no difference. `tools/css_tidy.py` does the mechanical part.

## 0.3.459
- **A function that is switched off is really off:** it raises no hints and no notifications, shows nothing on Home (inspection, tyres, next service) and creates no sensors in Home Assistant, and its queries are skipped. The data stays and is back when you switch the function on again.

## 0.3.458
- **Home with only a name:** without a model line the line under the name stays free, so the car keeps its distance from the name (before, the car was glued to it). Without a number plate nothing is left free above the name.

## 0.3.456
- Setup, step 3: the intro says what is true now - the recommended functions are on, the others are switched on when needed, any time under More → Integrations (English and German).

## 0.3.455
- **Setup, step 3:** one list again, without the headings *Recommended* / *When you need it*: the functions most people need come first and are on, the others follow below with their switches off.

## 0.3.454
- **A new car starts with what most people need:** service book, appointments, fuel, documents, safety and report are on; extra work, tyres, modifications, parts, km counters, trips, manual and fuel stations are off until you need them (More → Integrations, or step 3 of the guide, which now shows two groups: *Recommended* and *When you need it*). The demo cars always have everything on.

## 0.3.453
- Step 3: the hint that the functions can be changed later is part of the intro card on top now; the button row holds just *Back* and *Next*.

## 0.3.452
- Step 3: the intro text is short and sits in a card with an info icon; the hint beside the buttons is shorter too.
- **Guide buttons:** under every step *Back* is on the left and the one main action (*Next* / *Save*) on the right, always in one line; in step 3 the hint about switching functions later sits between them (on a phone above the buttons).

## 0.3.450
- **Setup, step 3:** on a wide screen the list of functions runs in two columns.

## 0.3.449
- **Setup, step 3 (*What does this car need?*):** each row is one line again - icon, name with its short text, switch - instead of centred, stacked and in capital letters.

## 0.3.448
- **Navigation bar (phone and tablet):** while switching pages the icon of the new page was shown light red for a moment and then turned dark red. The gliding marker is its own layer during the page change and was painted over the icons; now every entry of the bar is a layer above the marker, so the icon is the same red the whole time.

## 0.3.447
- Internal: a local settings backup file is no longer tracked and is ignored.

## 0.3.446
- **Navigation:** the icon of the active page no longer fades from grey through light red to dark red when you switch pages - it is the accent red from the first frame.
- **Icon buttons (design step 4):** where an icon says it all, the button shows only the icon - delete (bin), save (check), cancel (cross), add a line (+) and the pencil under each card. The text stays for screen readers, there are no hover tooltips. Texts of the one main action and of important deletions (a car, a user) stay.

## 0.3.444
- Internal: the CSS helper passes the lint check.

## 0.3.443
- **Vehicle passport:** the selected passport line in the More list is no longer red; it is marked like every other selected row (a lighter background).
- **CSS tidy-up (design step 3, part 1):** 181 dead declarations and 35 empty rules removed (a later rule of the same selector always overrode them), colours that were written as hex values inside rules now come from tokens (`--on-dark`, `--black`, `--on-ok`, `--retro`, the season colours), no change in how any page looks. New helper `tools/css_tidy.py`.

## 0.3.441
- The car drawing of a new car (no photo yet) keeps its distance from the name and the model line on Home.
- **Page layout (design step 2):** every page header now has the same height (title row plus the line for the car's name), so content starts on the same line on every page - also on the settings pages. Record cards (appointments, service, parts, ...) use the same gap as the rest and keep their *Edit* on the bottom line. The round icon buttons (back, plus, switch ...) have the same glass look as the other buttons.

## 0.3.439
- **One glass button everywhere (design step 1):** every button - save, add, edit, delete, links and file pickers - now has the same translucent glass look with a light edge: 44 px, or `small` 36 px. The one main action is red glass, delete is a red outline. Only design tokens are used, so all designs (dark, light, frost, ocean, sunset and your own theme files) recolour the buttons; light designs get a brighter edge.

## 0.3.438
- **Tyres: the earlier view is back** (recommended-pressure card with a tab per season, a card per set), with the newer functions built in: pressure when fully loaded, a rear axle of its own (size and name) and the rear axle on the set card.

## 0.3.436
- **MQTT sensors reworked:** still off by default, and the switch only appears when a broker is found (Home Assistant's or your own). When on, a car becomes a device with many more sensors - ignition, locking, doors, windows, tyre pressures, battery, charging, temperatures, AdBlue, service - created only once a plugin delivers the value; rarely useful ones start switched off or as diagnostics.
- **GPS position in Home Assistant:** the car appears on the map as a device tracker (with speed, heading and time of the fix).
- Nothing is sent twice (only changes), *Send sensors again* sends everything once more, and switching the sensors off removes them from Home Assistant.

## 0.3.435
- **README intro reworded:** says what makes the app special - every document and all data of a vehicle in one place, including the data of the car itself.

## 0.3.434
- **Add-on logo:** *Car Assistant* in one line like the banner, the green slogan below it, the whole block vertically centred on the icon.

## 0.3.433
- **Original logo in the navigation:** the side bar always shows the standard logo and the slogan, never a car's icon or name. The car (with its own icon) lives in the *More* list only.
- **New banner and add-on logo:** *DRIVE · LOG · GO* sits under the name in the app's font, spread exactly from the C to the t of *Car Assistant*; same lockup in the README banner and the Home Assistant logo.

## 0.3.432
- **Documentation brought up to date:** add-on description (no recovery codes any more, km counters and fuel stations on their pages), plugin docs (the *Logs* page of each plugin), the vehicle file format (equipment, manual, loaded tyre pressures, rear axle).
- **Demo cars** (only them) get their own icon: the demo car's picture on a dark tile (1024 px, the largest an icon can be, the picture at its own pixel size), in *More*, on the home screen and in the lists.
- **Demo cars:** both demo cars (and the built-in demo) carry made-up equipment in all twelve areas with every status (standard, special, retrofitted, not fitted), codes and notes, plus loaded tyre pressures and a separate rear axle.
- **Documentation:** the user guide describes the new pages, the plugin documentation describes page details, reminders and plans; README and roadmap are up to date.
- **Home widgets:** *Attention*, *Vehicle data* and *Position* are now always one full row and cannot be made small (no resize handle); the demo cars follow this.
- **Plans for reminders (additive plan):** a reminder can carry a rotation (for example clean - additive 1 - clean - additive 2) that moves on with every refuel; its own page shows the next refuel, the rotation, *Correct the plan*, and the history with *added / not added*. The reminder can wait until the range gets low.
- **Integration pages (Coding) like the original:** every entry is a collapsible row with a short code badge, name, subtitle and the count of changed bytes; inside the part numbers, notes, the byte grid (original / current, changed bytes marked, tap a byte for its bits), the new value and notes to edit right there, *Save* and *New = original*; the other data behind *Edit data*. Search and *Only changed* sit on top.
- **Manual:** a new page *Manual* for every car: import a PDF (with a text layer), an EPUB or a text / Markdown file; chapters grouped like the original, a search with hits marked on the page, "Continue reading", "page 137" references you can tap, and an **EPUB export**. The file stays on your server.
- **Extra work (formerly Maintenance) like the original:** the current odometer on top with a status pill, a card per job (icon, interval, progress bar, last / next, a km field with *Reset*, a menu to edit), and a button to add ready-made jobs with guideline intervals. *Maintenance* is now called *Extra work* everywhere.
- **Tyres like the original:** a card per tyre set (*Mounted now* or a *Mount* button, a pencil), the tyre pressure as big tiles for normal use and fully loaded (front / rear), the front and rear axle sizes (a separate rear axle is possible), notes. The pencil opens the set data and the pressures.
- **Modifications like the original:** a quick-add line on top (*e.g. Dashcam installed* + *Add*), a plain list with a dot, a pencil (edit date, odometer, cost, note) and a cross (delete) per entry, and a search.
- **Logs per plugin:** the *Logs* entry in More is gone. Every plugin and integration has its own, simple log page (button *Logs* on its card): the switch for more detail, only ITS log lines, the calls it made (folded) and *Clear*. The old common log page leads to the plugins.
- **Fuel + fuel stations on one page:** *Fuel* now holds the station search (collapsed) on top and the fill-ups below, grouped by month in collapsible areas with slim rows, search, a pencil per fill-up (edit, delete) and a **+** to add one. The separate *Fuel stations* page is gone (the old address leads here).
- **Trip card like the original:** times and a *Route* tag on top, the distance big with duration / average / top speed, consumption chips (an estimate from the car's average and price), the route map with its points line, the *Driving style* tiles (acceleration, braking with hard brakings, average while moving, standing share) worked out from the recorded positions, and the GPX download. Without recorded positions the duration and average come from the entered times.
- **Trip card:** tap a trip to open its card - the distance big, duration, average and top speed, and the route on the map coloured by speed (blue slow to red from 130 km/h; drawn without a map when online maps are off), plus the GPX download.
- **Trips + km counters on one page:** *Trips* now holds the km counters on top (rows with the driven distance, edit, add, delete) and the trips below, grouped by month in collapsible areas with slim rows, search, a pencil per trip (edit, delete) and a **+** to add a trip by hand. Export (PDF / CSV) and GPX import sit in one collapsed area at the end. The separate *Km counters* page is gone.
- **Car card in More:** the switch button only shows when there is more than one car.
- **Passport head:** name, plate and *make model variant* on top, then one row of chips with year, fuel, power, gearbox and odometer, then the VIN. Those values no longer repeat as tiles in the groups below.
- **Vehicle passport:** empty fields are no longer drawn as "-" tiles (only what you filled in shows), the key numbers row is gone from the passport (still in the form), and the grid lines are drawn cleanly - a tile that stands alone runs over the full width.
- **Vehicle passport:** one even rhythm - every block starts 20 px under the previous one and every heading sits 8 px above its content.
- **Equipment:** the heading lines up with the other headings and shows the number of features next to it; the extra count line is gone.
- **Vehicle passport:** *Notes* sit above the equipment. In the vehicle form *Back up* and *Manage* are one tidy card (backup, archive, delete as rows with a short text and a light button); the archive button says *Reactivate* in German again.
- **Equipment:** the areas (Comfort, Seats, Controls, Lights, Lines & packages, Interior, Wheels & tyres, Technology & safety, Exterior, Infotainment, Driver assistance, Glazing & roof - twelve, translated in every language) are the same fixed set for every car and always there; they can only be moved up and down (arrow buttons in the area). Nobody has to add or edit areas, and there is no ready-made feature list: everybody adds their own features per area.
- **Buttons:** secondary actions are light, outlined buttons everywhere (delete is outlined red, no filled block) and button rows stay on one line; only the one main action of a page is a filled primary button.
- **Equipment:** every area has *Add a feature* and a **+** next to the title adds an area; a feature is removed in its edit form. *Next inspection* and *Maintenance* chips on the dashboard got icons; they are laid out like the top chips (left chip left, right chip right, coloured icon).
- **Passport:** a value that stands alone on the left (for example the odometer) now runs over the full width; the equipment rows are slimmer.
- **Equipment rebuilt like the original:** a search box and a count on top, every area is a collapsed row (icon, name, *n of m*) that opens to the groups *Standard / Special equipment / Retrofitted / Not fitted* with green, blue and red marks. Every feature has its own edit button on the right (text, code, status, and the category it belongs to - this moves it). The legend sits at the bottom in one line.
- **Car card in More** is now ONE block with the list: the car's own icon (the home-screen icon of this car, a bit larger) with its name and the switch on top, the vehicle passport as the second line under the name (no separate row), then the pages. Tap the icon to upload your own picture for this car (centred and cut to a full square).

## 0.3.359
- **Vehicle passport:** the car card in *More* (and the side list) shows the car name with a *switch* button on top (with one car it leads to the vehicle list) and the **Vehicle passport** underneath as a row like all others; the icon is a car seen from the front. The same fixed first row sits in *Manage navigation*. The VIN stands on top of the passport with a copy button. New **Equipment** list (categories with an icon, status standard / special / retrofitted / not fitted with green, blue and red marks, optional code such as a PR number, a neutral starter list, edit per category). The page icons in *Manage navigation* now look exactly like in *More*.

## 0.3.356
- **Navigation:** the first card of a car in *More* is now one fixed two-line card: car name and plate on top, its **Vehicle passport** (formerly *Vehicle data*) underneath. *Manage navigation* now holds the on/off switch of every page and of every integration (the separate *Integrations* card is gone); switched-off pages stay listed. The page icons are coloured glass tiles, the same everywhere.
- *Settings > System* is single-column on phones again. *My preferences* is now *Personal settings*.

## 0.3.355
- **System page tidier:** the port line is short (*Port: Off / On, protected by users*), the long "how do I make it reachable" guide is gone (it lives in the docs; **About -> Help** opens them on GitHub). Passkeys and web push are greyed out with *The external URL must be set first.* until an external URL exists.
- **Own icon:** any picture (PNG, JPEG, WebP, GIF, BMP, TIFF) is padded to a square without cropping or stretching.
- *Restore a vehicle from a backup* now sits at the end of the vehicle list.
- A car's own design now also applies on its *More* page.

## 0.3.354
- **Settings -> User redesigned** in the app's own look: one compact card per topic, rows with a small *Change* button instead of folding arrows, the sign-out buttons at the end. Recovery codes are gone (a forgotten password is set again in the Home Assistant panel). The explaining text is short and hidden when you already use the page over the port. With a port set, status, address and lock rules, design and touch feedback live under User; without a port they stay under System. Checkboxes are drawn in the design's own colour.

## 0.3.351
- *Settings -> User*: the status no longer claims that direct access is active when no port is set. Without a port it says that Car Assistant is only reachable through Home Assistant and that the login applies once a port is set.

## 0.3.350
- The address of the built-in icon changes with every app version, so a phone (and any cache in between) fetches the new icon after an update instead of keeping the old one.

## 0.3.349
- iPhone icon: the ring now follows the exact smooth shape iOS cuts out of a home-screen icon, so it is equally thick everywhere and the corners fit perfectly. (Remove the old home-screen link and add it again: iOS keeps the old icon.)

## 0.3.348
- **The system and every car are web apps of their own:** each car's manifest has its own name, icon, colours (its design) and a scope that ends at that car's pages, so a car can be put on the iPhone home screen on its own. Inside one car or the system the pages change instantly; another car or the system is a page of its own.

## 0.3.347
- **Icons for a phone that is not signed in:** the two addresses iOS asks for on its own (`/apple-touch-icon.png`, `/apple-touch-icon-precomposed.png`) were behind the login, and the page that says "locked" (port set, no user yet) named no icon at all. Both fixed: icons are served without a login (they show nothing about the cars) and every page names them. A car's pages still use that car's own uploaded icon.

## 0.3.346
- Login lock: the message now shows the real minutes of the setting (it always said 15 for passkeys and password recovery). The passkey round trip (register, sign in, replayed or forged answers refused) is tested with a software authenticator.

## 0.3.345
- **New app icons in the new look for every device:** the iPhone home screen gets a full square (iOS rounds it itself, no black corners), Android gets a maskable icon in the safe zone, browser tabs get a sharp SVG favicon. Every size has the same contour and the same distance between car and contour. Your own uploaded icons keep working (also as maskable).

## 0.3.344
- The slogan "Drive · Log · Go" is shown in the green of the app everywhere (side bar, About, login, locked page).

## 0.3.343
- The login page has the same look: soft red / green light, glass card, the logo with its moving lines.

## 0.3.342
- The page shown for a direct visit without any user is designed now: logo with the moving lines, soft red / green gradient, a clear "locked" badge. It needs no file of the app.

## 0.3.341
- No port is suggested anywhere any more (neither 8321 nor 8099): the texts say the owner chooses any free port in Home Assistant.

## 0.3.340
- README (English and German) brought up to date: plugins as the connection to the outside, sources and plugin services, tyre pressures, backups, demo, port and user rule, link to the plugin guide.

## 0.3.339
- About page: more effects - very fine lines with glowing red-to-green light streaks running towards the car, a slow breathing glow behind it and a gleam that glides over the ring (all switched off for people who prefer less motion).

## 0.3.338
- The car in the logo at the top left is a little smaller again (as before).

## 0.3.337
- About page: the logo is exactly as wide as the name below it; the lines behind the car are thin colour gradients (red to green) that disappear completely behind the car, with a soft light running along them.

## 0.3.336
- **New logo as a real vector graphic** (the car redrawn from the large original: sharp at any size): in the sidebar and on the About page, where it is shown large with faint red / green signals running along the lines behind the car (animated, switched off for people who prefer less motion). GitHub logo, add-on icon and title picture follow the same look; `docs/logo.svg` is the source.

## 0.3.335
- The demo plugin of the standard source is no longer offered in the plugin list (it only belongs to the two demo cars, which still install it themselves). The demo cars now have every vehicle field filled and recommended tyre pressures.

## 0.3.334
- The two demo cars (diesel, electric) start with every Home widget small. `tools/make_demo_vehicles.py` builds them that way.

## 0.3.333
- The logo tile at the top left has a stronger contour (the ring grows inwards; the size is unchanged). The list next to the page (*More*) no longer shows a Back arrow of its own.

## 0.3.332
- The hints under *Settings -> System* no longer talk about the removed add-on options (external address option, default port 8321).

## 0.3.331
- **Instant page changes:** a click on a link of the app loads the next page in the background and swaps it in without a browser reload (nothing flashes, styles and scripts stay loaded; the browser fades between the pages). Forms, downloads and the login stay ordinary page loads. Every answer also carries a `Server-Timing` header so the browser's network tab shows how long the app itself needed.

## 0.3.330
- **Faster pages:** settings are read once and remembered for a moment (a page opened about 30 database connections, now about 5), the database mode is set once instead of on every connection. On wide screens the plain Back arrow to *More* is hidden because the More list stands next to the page.

## 0.3.329
- The last traces of the removed add-on options (notify service, language, external address, MQTT switch) are gone from the code too; all of it is set inside the app.

## 0.3.328
- **Home Assistant configuration: only the log level is left.** Language, reminders to your phone, MQTT sensors and the external address are set inside the app (Settings / Integrations), so the options are gone. MQTT sensors are off until you switch them on.

## 0.3.327
- **Tyres:** recommended pressures per season (summer / winter / all-season tabs, front and rear axle, editable); below them the pressures the car reported last, if a plugin offers them (a red dash while none does). The tile "Stored at" is hidden when empty. Included in the vehicle backup.

## 0.3.326
- **Pages load faster inside Home Assistant:** the answers of Home Assistant and the Supervisor (currency and country, mapped port, list of entities) are remembered for a short time instead of being asked again on every page view.

## 0.3.325
- **Configuration simplified:** the option *Who may open the port* is gone. The port is empty by default; enter one (suggestion 8321) to reach the website from outside - this works only with a user (name and password). Defaults are now empty/off, log level `error`.

## 0.3.324
- `tools/check_plugin.py` runs again with plain Python (the encryption library is loaded only when a secret is really stored).

## 0.3.323
- **The configuration in Home Assistant is tidied up:** the old shared-password option is gone (a direct visit needs a user of the app, nothing else); the remaining options have short, plain names and descriptions in German and English. Direct access without any user shows the page that explains it.

## 0.3.322
- **Value tiles on Home:** a plugin or integration can put small tiles on the Home page (`tiles` in `plugin.json`): the value comes from a raw signal it delivered or from a standard number of the API, with unit and decimals. A tile shows only while the plugin runs and a value exists; it can be moved, resized and hidden like any widget.

## 0.3.321
- **Secrets are encrypted in the database:** the passwords of a plugin's settings and the access key of a source are stored encrypted (key in `secret.key` in the data folder, readable by the app only, not part of a backup). Old plain values are still read and sealed the next time they are saved.
- **Menu entry *Logs*** under *More* leads to the logs, traffic and debug page of the car.
- The public packages (Coding, Webradio, Fuel additive) have an icon, a description text and their interfaces now (versions raised in the sources repository).

## 0.3.320
- **Who may open the port:** a new add-on option *Who may open the port* - `home_assistant` (only through the Home Assistant panel), `home_network` (also directly from your own network, VPN ranges included) or `everywhere` (also the internet); default `everywhere`. A user must always sign in, and without a user direct access stays locked. Home Assistant cannot publish a port "only to the home network", so the app looks at the address a connection comes from; behind a reverse proxy or tunnel it also reads the forwarded addresses and counts a request as internet when any of them is public. A direct connection that is refused now gets a friendly page that says why, not a bare line. *Settings -> System* shows the mode.
- **The configuration in Home Assistant is clearer:** the options are in a sensible order with plain names and descriptions (German and English), the old shared password is marked as such, the port has an explanation.

## 0.3.319
- **Files of a package:** a package may bring checked binary files (`files`: `.jar .zip .bin .json .txt .md .pdf`, at most 10, 8 MB each, 20 MB together, every file with sha256 and size - also named in `plugins/index.json`) that the app hands out itself, without a running service. They lie read-only in their own folder, are never opened or run, and go to signed-in people only (`/plugins/<id>/files/<name>`, `attachment`, `no-store`). They are listed with checksums on the approval page and the package page; a new version with other files needs a new approval; removing the plugin deletes them. **Bundles** build a zip on request from the package's files (fixed order and times, same bytes every time). Shown as the group *Files* on *Interfaces* and the settings page; `{file:name}` in `docs` becomes a link. `tools/build_plugin_package.py` and `tools/check_plugin.py` know about them.

## 0.3.318
- **Files for download:** a plugin lists files its service offers (`downloads` in `plugin.json`, under its routes); the app shows buttons on the settings page and the page *Interfaces*. Non-public routes also work for a signed-in person from outside (before: only from Home Assistant). Binary answers and `Content-Disposition` pass through the proxy (tested).
- **A plugin with a service AND a connection file has one token** (before, the file could not get one): shown once on setup, the same one goes to the service; *New token* updates both and restarts the service; *I already have the token* works for it, too.
- **New guide:** `docs/plugin-guide.md` - a plugin from nothing to a source in eight steps (folder, plugin.json, settings, Connector API, service, downloads, interfaces, check and publish).

## 0.3.317
- **A plugin is a connection to the outside:** the docs and the rules now say it plainly - to a car, a web service you log in to, a cloud account, a device, anything. The credentials are settings of the plugin (a `password` field); they are not part of a vehicle backup file. A service can state the hosts it talks to (`service.connects`), shown on the approval page (a change needs a new approval).

## 0.3.316
- **Interfaces page per package:** every tile has a button *Interfaces*: one page with everything a package offers or uses (sends to the app, reads from the app, offers itself, settings), declared in its `plugin.json` (`interfaces`, `docs`) and *seen* (really used: address, names of fields, how often, when - never values, always noted, removed with the package). The routes of a service, the pages of an integration and the connection file are listed by themselves. Also fixed: removing a plugin now also removes its watched traffic.

## 0.3.315
- **Existing token for the connection file:** on the settings page of a plugin with a connection file there is a second way next to *New token*: *I already have the token*. The typed token is compared with the stored fingerprint; if it matches, the connection file is downloaded again with this token - no new token is made. Wrong entries get a clear message and change nothing; the token is never shown or logged; administrator only; five wrong tries in 15 minutes stop further guessing.

## 0.3.314
- **Back is always there:** on wide screens the Back button was hidden on every page under *More* (the list at the left was meant to replace it). It now shows on every page that leads somewhere, on any screen size. The Logs page of a plugin always shows the plugin chips, also while it has no lines yet.

## 0.3.313
- **Settings of plugins are a page, with many more kinds of fields:** the pop-up is gone (also the access key of a source). *Settings* opens a page with a fixed *Back* to *Manage* (also on wide screens). New field types, rendered like the settings of Home Assistant: slider, radio buttons, checkbox group (`multiselect`), url, e-mail, time, date, colour, headings (`section`) and texts (`info`), plus `required`, `placeholder`, `unit`, and `show_if` (a field appears only while another setting has a value). Wrong entries are named and nothing is saved until they are fixed. A service gets typed values in `settings.json`. Up to 40 fields.
- *Manage* is one column again; the buttons *Install a file* and *Add a source* sit under the tiles of *Add*; *Sources* shows the add form last and the access key as a button.
- Pages that lead somewhere have a **fixed Back** (a package, the sources, debug, service approval, trip, report, library, widgets ...), never an address taken from a link.

## 0.3.312
- **Plugins and Integrations as tiles:** the three tabs are clearer. *Add* has the button *Update list*, *Manage* has *Check for updates* (it says what it found), *Sources* has no update button any more. Packages show as tiles with their icon (from the index of the source or the plugin), name, short text and state; "Install a file" and "Add a source" are tiles at the end. New (opt-in): *Settings -> System -> Package updates* reads the sources once a day.
- **Logs per plugin:** every tile has *Logs* and its own *Debug* button (more detail for that plugin only, until switched off); logs are kept for 1, 7 or 30 days (*Settings -> System*). Fixed the English tab name (*Manage* on both).
- **Range and tank:** the amount in the tank can be delivered (`fuel_amount`); an electric car reads its battery level for the per cent; litres / kWh show next to the per cent also without a range.
- **For plugin authors:** `tools/check_plugin.py` checks a package and names typos and wrong icons; `docs/icons.md` lists the icon names.

## 0.3.311
- **Watch plugins and services:** the *Debug & log* page has a *Traffic* view (while debug is on: every call of a plugin to the API and every request on a route of its service - time, status, address, size, duration, field names, never values) and shows what the add-on does with a service (install, pip errors, start, stop, crash with exit code and pause) - always, as lines of the plugin's own log, filterable per plugin and removed with the plugin.

## 0.3.310
- **Settings -> System tells the truth about direct access:** it showed *Off* whenever the old shared-password option was empty, even with a port set. Now it asks Home Assistant for the port and says: off (no port), on (protected by your users), on (old password), locked (port but no user yet) or unknown. A new text explains where what is set: the **port only in Home Assistant** (Apps -> Car Assistant -> Configuration -> Network), the **external address here or in the app options** (the option wins). The password option is marked as old - leave it empty and use users. The Home Assistant configuration texts say the same.

## 0.3.309
- **Plugin logs:** log lines now belong to their plugin (also the output of a plugin's service). *Settings -> System -> Plugin logs* sets how many lines each plugin may keep (200 to 20 000, default 1000; the oldest go first, one noisy plugin does not push out another) and can delete all of them. The *Debug & log* page can be filtered per plugin and shows who wrote a line. Removing a plugin deletes all its log lines.

## 0.3.308
- **Plugins with a service:** a plugin from a source may bring a program of its own that runs inside this add-on (no second container). Strict rules: readable text files only, sha256 of the index checked, an administrator approves a page that lists everything it does (a changed description needs a new approval), its own process, virtual environment and unprivileged user with limits, a clean environment (no Home Assistant token, no database), the Connector API as its only door to the app. Public routes (for example for the car) are passed on unchanged. Start / Stop on the plugin card; a crash restarts it with a growing pause; removing the plugin cleans everything. New: `tools/build_plugin_package.py` and the example `docs/examples/echo-service`. See docs/plugins.md.

## 0.3.307
- **Connection file for plugins:** a plugin manifest may carry `connection_file` (a file name and a text template with `{token}`, `{vehicle}`, `{url}` and its settings as `{key}`). When the token is shown (set-up or *New token*) there is a download button: the file already contains the token and the plugin's settings, so a device in the car only needs that file next to it. Lines with an empty value are left out. Nothing is stored or executed. The default of a setting may now be up to 200 characters (was 60).

## 0.3.307
- **Connector API:** events (`/events`, for example traffic signs read or town borders crossed, newest 2000 kept), a refuel a plugin noticed (`/refuel`, added to the fuel log, duplicates ignored) and the reporting interval (`interval_s` in `control`, set on the *Debug & log* page).
- **Vehicle file:** the file format is documented (`docs/vehicle-file.md`) with an example script - the way to bring a car in from another program.

## 0.3.306
- **Trips from the track:** positions a plugin sends to `/track` become trips of the log book on their own: a drive ends after ten minutes without a point; date, times, start/end place, distance and the route are filled in (marked as made from the track). Very short runs are dropped.

## 0.3.305
- **Preferences per user:** under *Settings -> User -> My preferences* every signed-in user chooses the car that opens first (or is asked); the touch-feedback switch is now saved per user as well. Everything not set follows the system settings.

## 0.3.304
- **Connector API, more connections:** gzip bodies; a track endpoint for drives (`/track`, many points, also sets the current position); raw signals (`/signals`) for anything without a standard field, shown on the Debug page; plugins can add, change and delete entries of an integration page (`POST /modules/<integration>/<page>`, for example the control units of Coding); new fields AdBlue level/range, oil level/warning and the current speed limit (also shown in the car data). Body limit 20 kB. See docs/api.md and docs/plugins.md.

## 0.3.303
- **Small things:** a round plus button (top right) on Integrations, Plugins and Sources; the offer *Add typical items* for maintenance tasks is gone (you enter your own); a video gets a stored preview picture (taken by the browser when you upload it), so the library no longer loads the videos just to show thumbnails. The preview is part of the car backup.

## 0.3.302
- Clean-up: the unused built-in package offer (code and page card) is removed.

## 0.3.301
- **Hidden widgets:** a widget switched off (eye) is really hidden on Home again; it only shows, dimmed, while you edit.

## 0.3.300
- **Webradio and Fuel additive in the list:** the built-in Webradio placeholder is gone - Webradio, Coding and Fuel additive now come only from the sources (tap *Refresh all sources* once). A package installed earlier from a file is taken over by its source when you install it from there; settings and entries stay.

## 0.3.299
- **Notifications per user:** under *Settings -> User* every signed-in user chooses their own Home Assistant notify service and which events they want: maintenance due, appointments, reminders of integrations (for example fuel additive), messages from the car, doors or windows open - plus a *Send a test* button. Everything is optional; nothing is sent until a service is entered and an event ticked. Each user is told about an item once in a few days. The general service of the add-on options keeps working as before.

## 0.3.298
- **Design per car:** in the vehicle data a car can choose *Like the system* or an own design (colour theme). It shows on the pages of that car; the system design stays the default everywhere else.

## 0.3.297
- **Pages of integrations:** an optional search box (`"search": true` on a page), a *Only changed* filter on pages with a hex comparison, and a tap on a byte shows its bits (old above, new below, changed bits marked). *Coding* and *Webradio* use the search (version 2 in the sources repository).

## 0.3.295
- **Reminders and dashboard widgets from integrations (first example: *Fuel additive*):** an integration can describe reminder rules - "again after N kilometres" or "after N refuels", with the numbers from its settings (setting defaults are new). The app counts from the odometer and the fuel entries; *Done* starts the count again. A running integration with a reminder gets a card on the *Fuel* page and a widget on the Dashboard (movable like every widget). Everything is optional: nothing happens until the integration is installed and running. The package *Fuel additive* is in the sources repository.

## 0.3.294
- The start page `/` (where a car is chosen) preselects no car any more: the side bar names none (name and slogan then sit centred next to the logo) and the bar has no car pages until you choose one.
- Side bar: under the name the slogan *Drive · Log · Go* always stands, and below it the car the navigation belongs to (with the change-car icon) in its own fixed line, so nothing jumps between pages any more; the logo is bigger in the wide side bar so the three lines sit next to it.

## 0.3.290
- *Report* (Auswertung) has its own colour (teal) in the menus; purple now belongs to integrations and plugins only.

## 0.3.289
- **One list of integrations:** *Fixed integrations* is now just *Integrations* and also holds the integrations you installed (Coding, Webradio, ...), each with its switch: off = stopped (page and navigation entry gone), on = running. The cards with the details (open, bar, settings, remove) stay below.
- **Integration pages in the navigation bar:** a running integration with pages can be put into the bar (button *Show in the bar* on its card under *Manage*, or in the *Navigation* editor) and taken out again; in the bar it shows its own icon and name, otherwise it is listed in *More*. The card of an integration shows its own icon and translated name, an *Open* button, and *Settings* only when it has settings; the buttons of integration and plugin cards are icons only (the name is in the tooltip).

## 0.3.286
- **Integrations can describe pages (page modules):** a package may bring pages with typed fields (text, number, yes/no, choice, web address, hex), an icon, translations and - for hex values - a byte-by-byte comparison with an original that is written once. The app draws and stores them per car (part of the vehicle backup); a running integration shows up in *More*, a stopped one disappears. A plugin of the car reads the entries via `GET /api/v1/vehicles/<id>/modules/<integration>/<page>`. Official examples in the sources repository: *Coding* and *Webradio*. See `docs/integrations.md`.

## 0.3.284
- **Package pages:** the links to a package and to the sources page no longer carry a `?back=` address in the query; *Back* is worked out from the page itself. (Opening a package page gave a *400 Bad Request* in Home Assistant for one setup.)
- **A video without a photo:** a first video can be uploaded without any photo; the car choice and lists then show the standard car until a photo is added.

## 0.3.283
- **Photo and video as a slider:** the library of the photo / video window (Dashboard and vehicle data) is no longer five small columns but one row of bigger pictures that you push left and right, to choose or delete the right one. *Save* stays at the very end of the page. The pictures fill their tile completely (no bars above and below). Up to **10** files per car instead of 5.
- **Dashboard icon:** the Dashboard tab and entries use a speedometer instead of the house.
- **Widgets with one more line:** *Service* shows how far it is to the next service (or how long it is overdue), *Fuel / Charging* the price of the last fill-up, *Last trip* its duration (when start and end time are known) and *Security* the first open door or window.

## 0.3.277
- **Add button at the top right:** on the list pages (service book, fuel, trips, counters, parts, tasks, appointments, tyres, documents) *Add* is now just a round plus button at the top right of the page header, always the last one on the right; it opens the add form (and closes it again). The extra *Add* card above the list is gone. *Add typical items* (tasks) moved out of the header: it appears in the empty task list.

## 0.3.275
- Widgets: less padding inside the tiles (10 / 12 px instead of 14 / 16 px, 8 px between title and value, a smaller icon chip of 28 px); the gap between the tiles stays.

## 0.3.273
- Live updates: when the car reports a new odometer value the drums just count on, without the roll-in effect (the effect plays only when the page opens).

## 0.3.272
- Video previews in the photo / video window show the middle of the video instead of its first frame (taken by the browser, nothing is stored or changed).

## 0.3.271
- **Photo / video window:** it is now a page of its own over the whole screen (no window in a window) in the theme's own background, readable in light and dark themes; the cards scroll like any page, the close button stays at the top right and *Save* is the last thing at the very bottom.

## 0.3.265
- **Big photos are compressed instead of refused:** JPEG / WebP photos from 2 MB on are shrunk when saved (scaled to 1920 px, upright, metadata removed, quality lowered step by step until it is below 10 MB); a photo of up to 40 MB is accepted for that. Smaller photos, every PNG and all videos are kept exactly as uploaded. JPEGs are decoded in a reduced size, so even a 100 MP photo needs little memory. Also: with a video picture the maintenance / inspection boxes no longer overlap the odometer below.

## 0.3.263
- **Widget settings:** while editing the page every widget that has settings gets a pencil button next to the eye. It opens a small window with its settings (the odometer: *Look* - drums or tile); changes apply and save at once. The mechanism is generic, so more widgets can offer settings later.

## 0.3.262
- **Odometer as a widget with two looks, both inside the normal tile, the drums over the full width with the unit on the digits' baseline in the same row (the drums scale with the size of the widget; no service line in the widget, that stays under the car picture):** as soon as the car reports a range (it takes the place under the car), the odometer moves into the widgets. While editing the page, a button on the widget switches between the *Drums* look (free, with the progress line, wide) and the *Tile* look (framed, small); the choice is saved per car and is also in the widget list (edit page).

## 0.3.255
- Odometer drums: the last three units now tick up while the drums roll in (done in about a second instead of two), and the roll-in itself is a little slower and smoother.

## 0.3.254
- The odometer drums now play the last three units of distance after the roll-in (e.g. 179,997 -> 180,000), a few text changes in about a second; off with *reduce motion*. The drums follow the server units (miles shown as miles).

## 0.3.253
- Odometer drums with a thin progress line and "to the next service" underneath (the task that is due first by kilometres; "overdue by" when past due). No frame around it.

## 0.3.252
- **Odometer as drums:** the odometer on the dashboard is now shown like a real car counter - one dark glass cell per digit, the last digit in the accent colour, with a short roll-in when the page opens (off with *reduce motion*).

## 0.3.251
- Home picture with a photo: one box alone in its row sits centred (and still reaches into the picture); more air between the boxes and the model line above and between the boxes and the odometer below. Checked with 0, 1 and 2 boxes above and below.

## 0.3.250
- Home picture: the status boxes above and below the photo reach into the picture again, with the glass effect (the 0.3.244 fix had removed that). The photo still never covers the name or the model line when there is no box above it, and the odometer card no longer docks into the boxes below a photo.

## 0.3.249
- Fixed: the *Edit photo / video* button on the dashboard picture jumped to the right when pressed (the press effect replaced its centring). It is now centred without a transform.

## 0.3.248
- **Photos are shrunk on upload:** JPEG and WebP photos are turned upright, scaled down to 1920 px on the longest side and stripped of metadata (GPS position, camera) when they are saved. PNG pictures (cut-outs with transparency) and videos stay untouched.

## 0.3.247
- The *change car* icon next to a car name (page title, dashboard, and now also the side bar under the logo) is just the symbol, without the round button.

## 0.3.246
- With two or more cars the *change car* button now sits right next to the car name under the page title on every page (not only on the dashboard).

## 0.3.245
- The project slogan **Drive · Log · Go** (the same in every language): under the name in the side bar when no car is chosen, on the About page, and in the READMEs and the add-on description.

## 0.3.244
- **Home with a photo:** an opaque photo no longer reaches over the model line under the name, and the maintenance / inspection boxes below it no longer overlap the odometer card (the overlap is only for cut-out pictures and the default car).

## 0.3.243
- The logo always leads to the start page `/` (no address of its own): the dashboard with one car, the choice of cars with several.

## 0.3.242
- **Home with little data:** a new car shows a *Get started* list (odometer, first fill-up, service entry, connect the car) instead of an empty page; a single small tile that would sit alone in its row now spans the full row; the fill-up tile no longer shows a lone unit when there is no amount.

## 0.3.241
- Vehicle list at the start (two or more cars) is only a choice. Adding, restoring, saving and deleting cars now live only under **More -> Vehicles**; the vehicle switcher no longer has an *Add vehicle* tile. Without any car the welcome page still offers *Add vehicle*.

## 0.3.240
- **One source, both kinds:** a source (one repository) now always serves Integrations and Plugins alike - it appears in both tabs, is read for `integrations/` and `plugins/` in one go, and is deleted as a whole. Existing sources were put into both lists.

## 0.3.239
- **Vehicle list** (several cars) is now just a choice: no plus button at the top, no restore box, no download/delete buttons on the cards and no hint at the bottom. Adding, restoring, saving and deleting live in the vehicle switcher, *Add vehicle* and the vehicle's edit page. With one car you still land on its dashboard.

## 0.3.238
- **Sources:** a source you did not name gets a clean name (`owner/repository` for GitHub, or the name from its root `index.json`) instead of "github.com". One tick adds it to both lists (Integrations and Plugins). The index files are read more leniently (`{"packages": [...]}`, a bare list, the kind's own key); entries that were left out (e.g. an invalid id) are shown on the source with the reason. The *Add* page now lists everything the sources offer, with already installed packages marked, plus the *Update* button and a hint.
- Vehicle form and data page: **HSN / TSN** now sit right next to *Type / generation*.

## 0.3.237
- **Units everywhere:** distances, volumes and prices per volume are now entered AND shown in the units of *Settings -> Region* in every list and form (service, fuel, trips, counters, parts, tasks), in the vehicle form (odometer, range levels), in the report (mpg, miles), in due texts and notifications, and in the station search (radius and distances). Everything is still stored in km / litres / price per litre; typing a value and saving it unchanged keeps the stored value. Electric cars keep kWh and money.

## 0.3.236
- **Settings -> System** reworked, more compact: one *System* card (version, data, Home Assistant, MQTT, reminders) with the test tools folded away; *Sign-in protection* with the two choices side by side; *Online services* (map, fuel prices) in one card; *Backup* with restore and reset folded away.
- New: **External address (URL)** - enter the address you reach the app from outside (an address set in the Home Assistant app option wins and is shown read-only). The field is locked until a user exists, with the reason and a link (otherwise anyone on the internet could read your cars), and a short how-to explains the port in Home Assistant, the user, the HTTPS reverse proxy and where to enter the address.

## 0.3.234
- Settings window: the fields first, then the token, and *Save* at the very end - it saves everything in the window at once and closes it. What you save lives in the plugin (per car) and is part of the vehicle backup (long notes included); only the package itself is not.

## 0.3.233
- Plugin and integration cards have exactly three buttons: *Start / Stop*, *Settings*, *Uninstall*. *Settings* opens a window with everything the plugin lets you change (text, text area, password, checkbox, number, choice - each with an optional help text) and its connection token; the values are saved with the plugin only after *Save* ([docs/plugins.md](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/plugins.md)).

## 0.3.232
- Plugin cards on a phone: the four buttons are icons only, equally wide in one row (the labels stay as tooltips and for screen readers), nothing overlaps on narrow screens; the source line wraps instead of being cut.

## 0.3.231
- The plugin cards show who made the package and which source it came from (*by Matze89x · from Car Assistant*, or *own upload*). The Debug card at the bottom of Plugins is gone: debug moves into the plugin that offers it.

## 0.3.226
- Plugin and integration cards redesigned: icon, name and a state pill (green and beating while it runs), the description, the settings, and ONE row of buttons - *Start / Stop* as a real button (green *Start*, plain *Stop*), *Save*, *New token*, *Uninstall* (icons only on a phone).

## 0.3.225
- The navigation stays on the first *Add vehicle* page (it was hidden there); only the guide's own `/setup` pages have none.

## 0.3.224
- About: the closing text now says what the app is - practical, handy, only the functions you really need.

## 0.3.223
- Fix: after a factory reset the standard source is back, like on a fresh install (it was missing); it can be removed again when nothing is installed from it.

## 0.3.222
- *Just have a look* is the single entry for the demo cars (no second list with the same cars). It shows only while the standard source is in your list: remove that source and the entry is gone - there is no connection, so no demo.

## 0.3.221
- **Just have a look, for real:** *Add vehicle -> Just have a look* asks once (it goes online), reads the standard source, restores the demo car from it, installs the *Demo connector* plugin from that source and switches it on. A generic scenario player then sends a report every 5 seconds through the normal interface (`/api/v1`, with the plugin's token): parked, get in, drive (position, odometer and level change), stop, get out, sometimes a fault; an electric car plugs in when its battery is low. Only a plugin installed from a source is played, never an uploaded one. *Start / Stop* on the plugin card parks the car for good - nothing is sent and its token is refused. The built-in demo code is gone; the made-up data lives in `tools/demo_data.py` and the two demo cars in the sources repository.
- *Add vehicle* offers the cars of your sources (`vehicles/index.json`, `vehicles/<id>.zip`) and restores them like an uploaded backup; it also shows the restore on the very first start.
- A vehicle backup now also carries the car's own app icon and its debug switch.
- Back leads to the page you came from when you open *Sources* or a package from *Add*.

## 0.3.220
- The car switcher and the confirmation dialogs have their own solid surface, so they are readable on the light designs too (the text was dark on a dark veil).

## 0.3.219
- Restoring a vehicle backup of a car that is already here (same identity or name) asks first: *Replace the data* (the car keeps its address; a copy of its current state is saved first) or *Add as a copy* (name and address get a number) or cancel.

## 0.3.218
- The *Back up* button on the vehicle cards is a solid green circle like the red bin next to it (it was almost invisible).

## 0.3.217
- The *Vehicles* page has a *Back up* button on every car and a *Restore a vehicle from a backup* row.

## 0.3.215
- *Fuel log* is now *Fuel* (and *Charging log* is *Charging* for electric cars). When the fuel stations function is on, the nearby stations with prices sit at the top of the Fuel page (search around the car or around you, online only after you press search); the fill-up history follows below.

## 0.3.214
- **Vehicle backup:** *Vehicle data -> Back up this vehicle* downloads everything of ONE car (data, files, settings, connection tokens, the settings of its integrations and plugins - not the packages); *Add vehicle -> Restore* creates a new vehicle from it. Integrations and plugins come back switched off; a missing package is shown as *needs the package* with an *Install* button or the hint which source to add first. Backups carry a format number; from 1.0 on every older format stays restorable ([docs/backup.md](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/backup.md)). The system backup (with users) is separate and now has a format number too.
- Two demo vehicles (diesel, electric) as vehicle backups for the sources repository (`tools/make_demo_vehicles.py`).

## 0.3.213
- *Add* of Integrations and Plugins ends with an *Add source* row that leads to the Sources tab.

## 0.3.212
- The "Under construction" notes are gone from the Add pages of Integrations and Plugins.

## 0.3.211
- Sources inside the tab strip: *Integrations* and *Plugins* each have their own *Sources* tab with their own list (server-wide, for every vehicle). One address can be in both lists; taking it out of one list is refused while something of that kind is installed from it.
- Fix: the update note showed on every card (a name clash in the template).

## 0.3.210
- Sources, for real: a source is a GitHub repository (or an https address) with a fixed folder rule - `integrations/` and `plugins/`, each with an `index.json` (id, name, description, version) and one folder per package with its `plugin.json` ([docs/sources.md](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/sources.md)). Nothing is requested on its own: only on *Update*, when adding, opening, installing or updating.
- *Add* (per vehicle) lists the packages of all sources; tap one to read it, then *Install*. Installed packages live under *Manage*: settings, *Update* when the source has a newer version, *Active* on/off (a switched-off plugin's token is refused), *Uninstall*.
- A source can only be deleted when nothing installed from it remains. Private repositories: optional read-only access key, stored on the server and never shown.
- Factory setting: the first source is the project's package repository `ha-car-assistant-sources` (*Restore the standard source* brings it back).

## 0.3.206
- Home-screen icon (built-in): a full square with a thin red-to-green ring just inside the corners iOS cuts, instead of a framed picture with a wide black margin. Favicon and sidebar logo are unchanged.

## 0.3.205
- iOS home screen: the 180 px icon has no transparency at all (iOS paints it black), the page names its size, and the two addresses iOS asks for by itself (`/apple-touch-icon.png`, `-precomposed`) are answered.

## 0.3.204
- Sources are one list for the whole server: the *Sources* tab of Integrations and Plugins opens it for every vehicle (add by https address, remove with confirmation). Only the address is stored, nothing is requested. *Add* and *Manage* stay per vehicle.
- Long lists load 5 at a time while scrolling (on every width; it keeps loading until the screen is full).

## 0.3.199
- Touch feedback: the invisible switch is fully transparent and clipped to the tab's rounded shape.

## 0.3.198
- Touch feedback, third try: an invisible system switch now lies over each tab (and the *Try it* button), so the finger itself toggles it - newer iOS versions ignore haptics triggered from script.
- Fix: the scroll loading of long lists had been dropped from the script in 0.3.191 - restored, and a test now guards the script's features.

## 0.3.197
- About: the story and the closing line are one short text; the coffee note is shorter.

## 0.3.196
- About: the story is now two short sentences.

## 0.3.195
- About: the story behind the app (spare-time project, built partly alone and partly with Claude Code, with love for detail and practical use).

## 0.3.193
- Car switcher: photos run edge to edge with the card's rounded corners and fade softly into the card; the default car stays centred.

## 0.3.192
- Spacing of multi-line values: the label sits at the first line (System), units like *L/100 km* never break apart.

## 0.3.191
- Touch feedback now fires from the real click on the label of the hidden switch (the way that works on iOS); a *Try it* button in Settings -> Design.
- Fixes: status badges on System no longer overlap, space above the currency field on Region.

## 0.3.190
- Long lists (service, fuel, trips, appointments, tasks, tyres, parts, counters, documents) show 10 entries and load the next 10 while you scroll; the count reads "10 of 134 entries". Without script the Next button stays.

## 0.3.189
- Touch feedback: on an iPhone (iOS 17.4+) the bottom bar gives a soft tap like the keyboard. Switch in Settings -> Design, on by default; other devices do nothing.

## 0.3.188
- One button, one definition: every button (also the ones in forms, system and tires) is 44 px / 15 px / 12 px radius from a single rule; the scattered overrides are gone. Tyre cards use the normal card padding.
- Type and corners follow a fixed scale (radii only as tokens, font sizes in 10 / 11 / 12 / 13 / 14 / 15 / 16 / 18 / 20 / 24 / 32 steps).
- One pattern each: the *Edit* link of every record (pencil + text, also on tyres), one `facts` list style (System page), report cards titled like all others, the navigation hint no longer says the same thing twice, plugin versions read `v1`.
- Faster and smaller: the default car picture is a 35 KB WebP instead of a 256 KB PNG, the sidebar logo is 9 KB instead of 25 KB, unused style rules removed.

## 0.3.186
- One size everywhere: fields 48 px, primary and danger buttons 44 px with the same type size and radius on every page.

## 0.3.185
- Design check of every page at phone, tablet and desktop width: only the System page pushed wider than the screen (a long status badge) - fixed.
- *Photo and video* is named the same everywhere; new user guide (docs/guide.md).

## 0.3.184
- Page changes: back to the short cross-fade (it ran for 80 versions without a white frame), now laid over a solid theme-coloured backdrop. The 0.3.178 variant let the old page vanish before the new one was drawn - a white flash.

## 0.3.183
- **System page in one readable column** (two only on very wide screens); duplicate rows removed.
- **About:** a new closing text - made with love for detail, free and without a subscription (EN and DE).

## 0.3.182
- **Integrations: both lists stay in sync live.** Switching a fixed integration off removes its page from *Manage navigation* at once (on adds it back); the order above still re-sorts the list below.

## 0.3.181
- **Photo and video has a Save button like every other box.** The two choices (Dashboard / car photo) are picked and saved together; adding and deleting files still act at once. The "saved right away" line is gone.

## 0.3.180
- Date and time fields no longer slide out of the screen on the iPhone (service book, from/to, every date).
- The odometer keeps proper air below the picture when there are no boxes under it.
- Car switcher: the close button's blue focus ring is no longer cut off.

## 0.3.179
- **Fuel prices (Tankerkönig) moved to Settings → System** as an optional, separate card with your own key. It is no longer an integration, there is no add-on option and no environment variable for it: nothing is built in, and nothing is sent to the service without your key.

## 0.3.178
- Page changes: the old page stays until the new one is ready and is replaced at once on a solid background - no cross-fade of the whole page any more (its additive blending can flash bright/white on glass surfaces).

## 0.3.177
- Fix: the sidebar jumped by one line on pages without a car (the version line was removed there); the title now always keeps its second line, so switching pages no longer flickers.

## 0.3.176
- Ground glow under the car only for the default car and PNG photos - never behind JPEG photos or videos.
- Fix: a photo on the Dashboard now shows the one picked *for the Dashboard* (it showed the car-choice photo).

## 0.3.175
- **At most 5 files per car, photos and videos together** - the oldest falls out (the last photo never does). The grids always show five tiles per row, so the page stays compact.

## 0.3.174
- Photo and video window tidied: four equal boxes (add, Dashboard, car photo, video background) with the same inner spacing, and clean small delete buttons on the tiles.

## 0.3.173
- Code formatting only.

## 0.3.172
- Dashboard edit mode: the button on the picture reads *Edit video or photo* and sits exactly in the middle of it.

## 0.3.171
- The Save button of each box starts exactly where its fields start (it was indented).

## 0.3.170
- Save buttons are normal buttons again (not full width), left aligned like on the other pages; Delete sits next to Save at the same height.

## 0.3.169
- Photo and video: no more double indent - the content lines up with the other boxes.

## 0.3.168
- **Every box of the vehicle form has its own Save** (the box stays open afterwards); Photo and video keeps saving live. Media tiles and the two choices are framed boxes, videos included.

## 0.3.167
- **Photo and video sits between *Energy* and *Papers & look*** on the vehicle page and offers two choices: *For the Dashboard* (photos and videos together) and *As the car's photo* (photos only - car choice, lists, everywhere a still picture is needed). A video still needs a photo first.
- **More vehicle data:** *First registration* (the next inspection is estimated from it - first after 3 years, then every 2 - until you enter an appointment), *engine oil* specification and amount, *seats* and *permitted gross weight*.

## 0.3.166
- **Vehicle edit page tidied up:** all groups start closed; *Photo and video* is a group of its own that saves right away (it says so); one Save for the form; compact fuel selection without the empty line.
- **One *Notes* field** instead of two: *Bulbs & spare parts* was merged into *Notes* (existing texts are appended, the old column is removed from the database).
- **Archive explained:** the manage card says what Archive and Delete do; archived cars sit greyed out at the bottom of the Vehicles page with a *Reactivate* button.

## 0.3.165
- **Photo and video is its own section** on the vehicle edit page (the same panel as the Dashboard editor).
- **A car always keeps a chosen photo; a video is optional on top of it.** Both stay chosen (lists and the car choice show the photo, the Dashboard plays the video). A video needs a photo first; tap the chosen video again to switch it off.
- Vehicle data page: the variant has its own row (it was glued to the model); the demo car's 12 V battery no longer holds traction-battery text.

## 0.3.164
- Vehicle photo fills the full width of the dashboard and keeps its proportions; the height follows (no empty space at the sides, nothing cropped).

## 0.3.163
- Narrow sidebar: the logo is as wide as the navigation tiles, and the tiles are square too.

## 0.3.162
- Sidebar: the logo now lines up exactly with the left edge of the navigation.

## 0.3.161
- Sidebar: logo flush left with the title right beside it; the version no longer shows under the title (it is at the bottom). The Dashboard shows the vehicle switch button next to the car name again.

## 0.3.160
- Fix: tyre icon outline uses the theme colour (light themes).

## 0.3.159
- **One action bar in every form:** *Save* fills the row and *Delete* sits right next to it, both the same height - at the bottom of each edit form (entries, tyre sets, vehicle, integrations, debug, account).
- **Tyres:** one column, season-tinted cards with a glowing icon and larger facts.
- **Fixed integrations follow the navigation order** and re-sort live when you move a page above.

## 0.3.158
- **Navigation order is live in More:** the order set under Integrations -> Management now decides the order in More as well, right away. The editor ends with two fixed rows, *Integrations* and *Plugins*, shown like the others with greyed, inactive arrows.

## 0.3.143
- **Settings are four tabs:** *Design* (colours, app icon, map), *Region*, *Navigation*, *System* - a segmented bar at the top instead of a list (the first tab is the start page).
- **Region: units and currency.** Besides the language there is a default system (*Metric*, *US*, *UK*) and a currency, and each vehicle can have its own (a car in another country). Everything stays stored in base units, so you can switch back and forth. Shown in the chosen units so far: Home (range, odometer, last trip, last fuel-up, consumption), the vehicle cards, the vehicle data page and the trip page. **Lists, entry forms and the report still show and take km / litres - they follow next.**
- **More only holds what the bar does not:** the "This vehicle" group lists each page that is not already in the bottom bar by its own name; entries of the bar are no longer repeated there.

## 0.3.142
- Settings: the *Map* switch moved into *Design* (the map follows the design anyway); the list is now Design, Region, Navigation, System.

## 0.3.141
- **The small trash icon on the vehicle cards is gone** (it was barely readable without text). Deleting a vehicle is a clearly red "Delete vehicle" button in the vehicle's edit page (archived vehicles keep a text button in their list).
- **Vehicle cards are easier to read:** instead of "Appointments: in 19 d" plus loose chips there are two labelled lines with an icon - *Next inspection* (date and how soon) and *Maintenance* (overdue / due soon / all good) - the same words as the boxes on Home. A line only appears when there is something to say.

## 0.3.140
- **Delete buttons are clearly red in every design:** they used the design's accent colour (blue in *Light blue*, barely visible in red designs); now they use the danger red of the design (a tint, a strong border, bold text; the round delete buttons of the vehicle list likewise).

## 0.3.139
- **Settings are a short list now** instead of one endless page: *Design* (colours and app icon), *Region* (language - units and currency are planned here), *Navigation*, *Map* and *System* (status, system services, backup, factory reset). Every entry opens its own page; *About* is its own entry in More only. The coffee link of the old settings page is gone (support is asked on the About page only). Navigation has its own icon (menu).

## 0.3.138
- The ground glow under the default car is a little stronger and sits right under the car.

## 0.3.137
- Home: the four boxes now float - they reach 12 px into the picture and stay 12 px in from its left and right edge (the same distance), so they no longer hang at the grid. The same for photo, default car and video.

## 0.3.134
- Home: the four boxes (ignition and doors above, inspection and maintenance below) reach a little more visibly into the picture - about 7 % of its width for photos and videos, 5 % for the default car - and show the picture through their glass. Checked with a cut-out car, a wide photo, a front view on white and a video.

## 0.3.133
- Home: less air around the default car (the car now fills 84 % of its picture instead of 70 %) and the old extra margins around the picture are gone; the overlap of the boxes is smaller (default car 4 %).

## 0.3.132
- Home: the four boxes always reach a little into the picture, in proportion to its size (default car 7 %, video 5 %, photo 3 % of the width - the default car has free space for it inside its picture). The ground glow of the default car sits right under the car.

## 0.3.131
- The default car picture now carries its free space inside the image (the car is smaller on a canvas of the same size, 15 % free on every side) and uses the full width; photos get the radius of a card.

## 0.3.129
- Home: an uploaded photo uses the **full width** the page offers (left and right as much as possible); only the cut-out default car keeps its room around it.

## 0.3.128
- Photos with their own background (not cut out) get rounded corners like a card.

## 0.3.127
- **A changed photo shows at once:** the picture's address now carries the name of the chosen file, so the browser no longer keeps showing the previous photo for an hour after you pick another one.

## 0.3.126
- Home video: its first frame shows as soon as it is loaded, so there is never an empty box or a photo before the video starts. A photo is only a stand-in when the video cannot play.

## 0.3.125
- Home: photos and the default car have **no fade** any more (only videos melt into the page) and sit with more room around them, so the boxes do not stick to the picture.

## 0.3.124
- Home: the default car and photos get room on all four sides (they were stretched over the full width and the boxes touched them); only a video reaches slightly under the boxes.

## 0.3.123
- Home boxes: each takes only the room it needs (never as tall as its neighbour) and they reach a few pixels into the faded edge of the picture - the car itself stays uncovered; still glass.

## 0.3.122
- **Home: the four boxes sit in the corners around the picture - for photo, default car and video alike.** Above it: ignition (left) and doors & windows (right); below it: next inspection (left) and maintenance (right). Compact glass boxes with left-aligned text (the right one of each pair right-aligned), no longer stretched. Each only exists with data; if a row has only one box it is centred. The picture takes the full width offered, the video keeps its soft fade.

## 0.3.119
- **Video: the boxes keep their distance from the car.** They no longer reach into the picture (0.3.116 let them touch the car); they sit above it with a clear gap. Tested with a real car video: the fade at the top, bottom and sides melts into the page without a visible frame, and nothing covers the car. (0.3.117 / 0.3.118: longer fades at the edges, fixed boxes being pushed down by a generic offset.)

## 0.3.116
- **Video: glass boxes reaching a little into the picture.** The two boxes and ignition / doors are glass again (blurred, see-through) and overlap the top of the video by a few pixels; the video keeps its natural width.

## 0.3.115
- **Video gradient is back ("Match"):** the video's own background is rebuilt from its edge colours as a band across the whole width that fades into the page at the top and bottom, and the video fades out at its sides - so it melts into the page like in the original dashboard. The layout stays as in 0.3.114 (natural width, boxes above, range below).
- **No picture behind a playing video:** the photo is no longer shown behind or before the video; it only stands in when the video cannot play.

## 0.3.114
- **Video on Home like the original dashboard** (correction of 0.3.113): the video takes the width the page offers - not wider - keeps its own proportions and fades softly into the page. Nothing lies on top of it any more: the two boxes and ignition / doors & windows sit above it (ignition left, doors right), the range below it. The next inspection / maintenance boxes still disappear when empty.

## 0.3.113
- **Video on Home, full width and in front:** a video now fills the whole width (a little beyond the screen edges, so nothing of it is lost), without fade or shadow around it. Plate, name, the two boxes, ignition / doors and the range lie in front of it and the picture reaches up behind them and down behind the range - a tall video no longer pushes the page down. On a wide screen it stays inside its column. Photos keep their soft edges.
- The video background choices are now *Natural* (as recorded), *Black* (black disappears) and *Transparent*; the old edge-colour rebuild ("Match") is gone.

## 0.3.111
- **Map follows the design:** with a light design (Light, Light blue, or Day / night during the day) the location map starts light and is tinted to the design's colours (a touch of blue in Light blue); with a dark design it starts dark. The sun / moon button still overrides this and is remembered. Before, light designs forced a light map and the button did nothing there.

## 0.3.110
- **About page centred:** the title, the section headings, the vehicle cards with their plugin rows, the credits and the author box are all centred now.

## 0.3.109
- **Own identity:** the About page and the READMEs no longer describe Car Assistant as "Home Assistant for your car". It is a logbook and dashboard of its own; Home Assistant is only where it runs.

## 0.3.108
- **Map shows "Access blocked" fixed:** OpenStreetMap refuses tile requests that come without an identifying Referer or User-Agent - exactly what a browser inside the Home Assistant app sends (we also told the browser to send no Referer). Now Car Assistant fetches the tiles itself: it identifies itself (`CarAssistant/<version> (+project address)`), uses at most two connections, keeps every tile for a week on disk (cache limited to 200 MB, a stale tile is used when there is no internet) and the browser only talks to the app. As a bonus OpenStreetMap no longer sees your phone or your Home Assistant address, and the page needs no exception for outside hosts any more (stricter content security policy). Still off by default.

## 0.3.107
- Roadmap and working notes: units (miles, gallons, mpg, °F, psi) and currencies per vehicle are planned; new code keeps values in base units and avoids hard-wired "km", "€" and "L".

## 0.3.106
- **"Edit page" on Home:** the button at the bottom (before: *Edit widgets*) now opens one window with everything: *Arrange widgets* (move, resize, hide) and *Photo & video* (upload, choose what Home shows, delete, how a video's background blends in). After an upload or delete the window opens again. The *Photos & videos* link in the vehicle form is gone; its photo field still works.
- **Fixed:** the "Match" background of a video reached beyond the screen and made the page wider than the phone (it zoomed out / scrolled sideways). It is now clipped.

## 0.3.104
- **Next inspection and maintenance only when there is something to show:** the two boxes above the car appear only if the car has an inspection date / maintenance tasks (and the page is switched on). With neither, they vanish and the space above the car is given back.

## 0.3.103
- **Home header on one line:** make · model · year and "just now" now sit side by side instead of on two lines (they only wrap on a really narrow screen).

## 0.3.102
- **Photos and videos per vehicle.** Vehicle → Edit → *Photos & videos*: upload PNG, JPG, WebP, MP4, MOV or WebM (photos up to 10 MB, videos up to 40 MB); the type is recognised from the file's content, not its name. Each car keeps its latest 5 photos and 5 videos - the 6th upload deletes the oldest one together with its file. Tap a picture to show it on Home; delete with the x.
- **A video plays once** when Home is visible, then stands still on its last frame (also after leaving and coming back); tap it to play again. It pauses while hidden and falls back to the photo when it cannot play (power saving, errors, "reduce motion"). Choose how its background blends into the page: *Match* (colours from the video's edges, recommended), *Black* or *Transparent* (video with real transparency).
- **Soft edges:** photos and videos fade into the background on all sides instead of ending in a hard frame.
- Existing photos move into the library automatically. Videos are served in ranges (iPhone needs that).

## 0.3.100
- **Demo cars report every 5 seconds** (was 10), so changes show up on Home faster.

## 0.3.99
- **Navigation marker glided twice on a page change:** the marker slid to its place with a script on top of the browser's own page-change fade, so it looked like a second bar arriving and gliding again. Now one mechanism does it: where the browser supports animated page changes, the marker is its own layer and glides once from the old to the new entry (the script only remains as fallback for older browsers).

## 0.3.98
- **Long press never opens a page by itself:** pressing and holding a navigation icon, widget or list row showed the system's link preview ("401: Unauthorized") and the Open / Copy / Share menu in the Home Assistant app. Links now behave like buttons on touch screens: no preview, no menu, no dragging of the link.
- **Long press on a widget opens the widget editor** (like on a phone's home screen, with a short vibration): move, resize or hide widgets right away; the release does not open the widget.

## 0.3.97
- **Doubled navigation bar after a page change (phone):** during the page-change fade the old and the new bar were shown on top of each other, and the glass lost its blur while it was only a picture. The bar (and the sidebar on tablets) is now its own layer: the old copy vanishes the moment the new page is ready and nothing is cross-faded.
- Versioned files are cached for a year, so a style change always comes with a new version number (the page address carries it).

## 0.3.96
- **Much faster with lots of data** (tested with 15 cars and thousands of entries each; every page now answers in about 0.1 s or less):
  - The maintenance check no longer reads the whole service book again for every task (home page of a big garage: 1.8 s → 0.08 s).
  - Long lists show 50 entries per page (Previous / Next, total count) instead of everything at once (fuel list: 2.7 s and 4 MB → 0.1 s).
  - A route with tens of thousands of GPS points was drawn in quadratic time (35 s) and is now instant; the picture uses at most 1,500 points, the GPX file keeps all.
  - A plugin reporting every few seconds now adds one odometer row per day instead of one per kilometre.
  - Indexes for every per-vehicle table, gzip for pages and styles (a page shrinks to about a fifth), long cache for versioned files, daily database housekeeping, safer SQLite settings (`synchronous=NORMAL`, busy timeout, cache).
- **Electric cars say "Charging stations"** instead of "Fuel stations" (a charging-point integration is still to come).
- Duplicate style rules between `app.css` and `pc-core.css` folded; design handbook got a speed/data-volume chapter and entries for the About page and the pager.

## 0.3.95
- **New page "About"** (More → General): version, database and file size, number of vehicles and entries, and for every vehicle which plugins and integrations are installed - with version, author and when a plugin last sent data - plus the app's own services, the libraries it is built with, the credits and a short note about the author with an optional coffee link. Only this page asks for support.
- The demo connector now names its author.

## 0.3.94
- **Logo in the sidebar:** the car is the original picture, cut free (transparent background, same pixels, same place); the frame is rebuilt: as big and as round as a navigation item, with a thin rim that follows the theme (accent to green) instead of the thick baked-in one. An uploaded icon is shown whole. Click: with one vehicle it leads back to the dashboard, with several to the list of all vehicles.

## 0.3.93
- **Fuel or charging - per vehicle.** Each vehicle has an "Energy view" (automatic / fuel / charging; vehicle form → Energy). Electric vehicles say *Charging* by default (charging log, charging point, energy in kWh, battery level), everything else says *Fuel*; a plug-in hybrid can be switched by hand. Only the wording changes, and it is chosen for each vehicle separately.
- **Warning levels per vehicle.** Set when the bar and the symbol under the car turn yellow and red - by level (default 25 % / 10 %) and/or by range in km. The worse of both counts.
- **Demo EV:** a second demo car (electric) that plugs in and charges when its battery is low - charging, plugged-in, power, minutes left, limit - all through the plugin interface.
- **Docs:** what a plugin is (every connection to a car, the only way, and what can be behind it) in the plugin docs and in `CLAUDE.md`.

## 0.3.92
- **What the car reports counts:** the car's own messages and a service that the car reports as due within 30 days / 1,000 km (or overdue) now count in the "Security" tile and the alert dot on the Security tab, and appear on the Security page ("Vehicle messages") and in the Home widget of the same name.

## 0.3.91
- **Connector API: the typical vehicle signals.** New read fields: coolant and oil temperature, cabin and target temperature, climate on/off, heading, consumption, the car's own service due (days / km), plugged-in, charge limit and minutes left, parking brake and lights (low beam, high beam, hazard, parking). They appear in the "Car data" widget on Home when a plugin sends them.

## 0.3.90
- **More read fields in the Connector API:** `speed_kmh`, `outside_temp_c`, `battery_12v_v`, `battery_pct`, `charging`, `charge_power_kw`, `tyre_pressure_bar` (per wheel) - shown on Home in a "Car data" widget that appears only when a plugin sends any of them.
- **First interface towards the vehicle: debug.** A person switches debug on or off per vehicle (Integrations & plugins → Debug & log). The plugin reads the switch (`GET /control`, also in every data answer) and, while it is on, sends log lines (`POST /logs`); while it is off they are refused (`409`) and nothing is kept. The *Debug & log* page shows the newest 1000 lines. The demo car's plugin does exactly this.
- API documentation extended (EN and DE).

## 0.3.89
- **Home shows what the car reports, live.** Home and Security update by themselves (no reload) for every vehicle that gets data from a plugin or has a connector token - doors, windows, range, fuel level, position, ignition, lock.
- **New: messages from the car.** The Connector API accepts `warnings` (`{"code": "text"}`, `null` removes a code), e.g. a tyre-pressure or engine warning; Home shows them in a "Vehicle messages" widget while they are active.
- **The demo car now talks through the real interface:** every 10 seconds it POSTs to `/api/v1/vehicles/<id>/data` with its own token - like a plugin in the car - including now and then a vehicle message that comes and goes.

## 0.3.88
- **Demo car: more happenings, less writing.** While parked, doors and windows of all kinds open and close at random; while driving, position, odometer, range and fuel level change every report. The odometer keeps one entry per drive that is updated while driving, instead of a new entry for every report.

## 0.3.87
- **Demo car: only what a connector sends, without reloads.** The demo car now only reports what a real plugin can send (position, odometer, fuel level, range, ignition, doors, windows, lock) - it no longer creates trips or fuel-log entries. Home and Security update just the parts that changed instead of reloading the page, so the navigation no longer flashes and the "Saved" notice no longer keeps coming back.

## 0.3.86
- **Demo car like a connected car:** new values every 10 seconds, and the car now has a "Demo connector" with its own token whose "last used" time updates with every report - the car lists it as an installed, set-up plugin under Integrations & plugins - it looks as if a plugin is installed and delivering data.

## 0.3.85
- **Demo car sends live data:** the demo car now behaves like a connected car - every few seconds it unlocks, opens a door, starts, drives a route (position, odometer, fuel level and range change), stops, saves the trip (with track), refuels when low, locks again, opens a window now and then. The data goes through the same path as a real connector (`connectors.ingest`), and Home and Security reload by themselves when something changes - ideal to watch every widget live. Only demo cars do this.

## 0.3.84
- **Colours in every theme:** the alert dot on a tab had a fixed dark ring (wrong on light themes), a few greens, the "soon" yellow and focus/drag outlines were fixed colours too - all follow the theme tokens now.

## 0.3.83
- **Flicker between pages:** a screen recording from the Home Assistant app showed one white frame at every page change on dark themes. Pages now change with a short cross-fade (`@view-transition`), which keeps the old page on screen until the new one is ready (needs a recent iOS / browser; older ones simply behave as before).

## 0.3.82
- **"Saved" notice floats:** the green confirmation no longer pushes the page down under the Home Assistant header (which squeezed the content); it floats at the top and fades away after a few seconds. Error notices stay in the page with proper spacing.

## 0.3.81
- **No more flicker in the Home Assistant app:** the "embedded" margins are set before the first paint (a tiny script in the page head instead of a deferred one), and the Day / night theme loads its light colours as a normal blocking stylesheet instead of an `@import`.

## 0.3.80
- **Day / night colours:** new theme "Day / night" (Settings → Colours): the original red look that follows the device automatically - light by day, dark by night - on every device that switches its appearance.

## 0.3.79
- **Lists on phones:** service log, fuel, trips, appointments, maintenance plan, parts etc. no longer run off the screen - every entry is a small card with labels above the values. The maintenance plan no longer shows "last done" twice; "Add typical items" collapses to an icon on small screens.

## 0.3.78
- **Light colours:** two new themes, "Light" (red accent) and "Light blue", under Settings → Colours. The whole app follows (cards, tab bar, chips, map without dark filter); the browser's own colours (`color-scheme`, status bar) follow too. A theme file marks itself light with `/* scheme: light */` on the first line.

## 0.3.77
- **Demo car:** on the new-vehicle page, "Create demo car" adds a made-up vehicle with two years of data in every area (service, fuel, trips with tracks, appointments in all states, tasks, parts, tyres, counters, live values) to try the whole app.
- **Home Assistant mobile:** inside the app the extra top and bottom margins are gone, so pages no longer waste space or look squeezed.

## 0.3.76
- **First start:** a language drop-down comes first; choosing a language reloads the page in that language (welcome text, the hint that it can be changed later in Settings, and the Continue button).
- **Create / edit vehicle:** icon cards instead of one long form - *Your vehicle* (name, plate, year, make, model, fuel as big icon tiles, odometer, photo, maintenance suggestions) is always open; identification, technology, energy, papers and the Home Assistant link are collapsible groups, closed when creating. A short welcome banner explains that only the name is needed.
- **Colours picker:** the theme names stay inside their tiles.

## 0.3.75
- **More has four umbrella entries** (Vehicle, Maintenance, Trips & fuel, Security) instead of a dozen single pages. Each umbrella page shows a segmented bar to switch between its pages (Vehicle: Data · Documents · Tyres; Maintenance: Appointments · Plan · Service log · Parts · Mods; Trips & fuel: Trips · Fuel · Odometer · Analysis). Addresses and functions are unchanged; functions hidden for a vehicle drop out of the bar.

## 0.3.74
- **Vehicle data, order and logic:** identity (make, model, year, build date, type, odometer, VIN last as a wide tile), technology (engine, the two codes side by side, drive and gearbox side by side, body), energy, papers (plate, HSN/TSN, colour and colour code as separate tiles, key numbers wide). The form follows the same order; the name takes the whole row.

## 0.3.73
- **Vehicle data in two columns,** also on phones: each value is a compact tile (small label with icon above, value below); long values (VIN, engine, key numbers) take the whole row.

## 0.3.72
- **Vehicle data:** tank size, battery capacity and the 12 V battery are three separate fields in their own group *Energy* (fuel, tank size in L, battery capacity in kWh, 12 V battery). The range line on Home shows the litres (or kWh for electric cars) left.

## 0.3.71
- **Colours are tokens:** every accent and status colour in the CSS is a token (`--accent`, `--accent-rgb`, `--ok-rgb` ...). A **theme** is one small CSS file in `static/themes/` that only overrides these tokens - layout and functions stay identical (Settings → Colours; *Ocean* and *Sunset* ship as examples). A test guards against fixed colours creeping back in.
- **One button system:** a single definition (radius `--r-m`, modern red gradient for primary, outlined red for danger) and one circle icon-button rule; old duplicate card, button and table rules removed.
- **Design handbook** in `docs/design.md` (EN) and `docs/design.de.md` (DE): tokens, breakpoints, components, behaviour rules and a checklist.
- **Page headers:** a calmer title size on all pages; the title shrinks before it can push the action button out of the screen.

## 0.3.70
- **Tyres:** each set is a card (season icon chip, mounted badge, tiles for size, season, DOT and storage, notes, mount button) - two side by side on wide screens. The add form is modern: a season picker with icons, big fields with example values and one clear save button.

## 0.3.69
- **Hide built-in functions per vehicle:** under *Extensions* of each vehicle a list of the shipped functions (tires, parts, documents, ...) with a switch each. A hidden function disappears from the navigation, Home, More and the alert dots of that vehicle only; other vehicles keep it. The system-wide switches stay under Settings → System services.

## 0.3.68
- **List pages** (service, trips, fuel, appointments, maintenance, tires, parts, mods, counters): the add form is collapsed behind one clear "+ Add" bar, an empty list shows a proper empty state instead of a loose line.

## 0.3.67
- **Live editing of the Home widgets:** *Edit widgets* now turns Home itself into the editor. Grab a widget by its grip: it is lifted with a white contour, a white dashed outline shows where it will land, the others slide aside (the page scrolls when you hold it near the top or bottom edge). Drag the red bar on its right edge to make it small or wide, tap the eye to hide it. Everything is saved immediately; hidden widgets stay visible (dimmed) while editing. The separate editor page stays as a fallback.

## 0.3.66
- **Home widgets:** the mixed tiles and cards are now uniform widgets in one two-column grid (small = half a row, wide = a full row; rows are always equally high). Widgets without data do not appear ("Needs attention" only when something is due).
- **Edit widgets** (button at the bottom of Home): show or hide, small or wide, move up and down - saved per vehicle - and a "+" entry that leads to the vehicle's integrations, where further widgets will come from. The inline odometer form is gone from Home (use the odometer page).
- The version line at the bottom now only appears in *More*.

## 0.3.65
- **Home hero, odometer only:** the icon is an odometer counter (not a speedometer) and green.

## 0.3.64
- **Home hero, odometer only:** label a little lower and closer to the number.

## 0.3.63
- **Home hero, odometer only:** docked to the car (the glow under the car sits behind the label) with the standard block gap below.

## 0.3.62
- **Home hero, odometer only:** no box any more - a small label with a speedometer icon and the big number below, centred under the car.

## 0.3.61
- **Home hero, range:** below the bar "about 38.1 L left in the tank · range as reported by the car" (litres only when the tank size is set) and "last: 13.11. 16:04" - instead of "just now".
- **Home hero, odometer only:** shown in a glass card with a speedometer icon chip (and the tank level with a fuel pump icon, when known).

## 0.3.60
- **Home hero:** the big figure under the car is the *range* the car reports, with the tank level (fuel pump icon, amber when nearly empty) and the time of the last report. Without a range it is the odometer; the odometer tile only appears when the range is the big figure, so nothing is shown twice.
- Under the name: the model line, and a separate "last signal" line with the green dot (only when the car has reported something).

## 0.3.59
- **Home on tablet / desktop:** car column and cards column are split 50 / 50.

## 0.3.58
- **Home on tablet / desktop:** the car column is no longer squeezed - the wide sidebar with labels now starts at 1280 px (icons only below), and Home uses the same edge (14 px), column gap (14 px) and top line (18 px) as *More*.

## 0.3.57
- **Delete a vehicle:** trash button on every card in *Vehicles* (also for archived ones) with an in-app confirmation dialog that lists what is deleted; everything that belongs to the vehicle is removed (data, files, photo, tokens, connections), other vehicles stay untouched.
- **Vehicles page:** even gaps between the cards and the car picture on every card.

## 0.3.56
- **New 404 page:** big gradient 404 with a car on a moving road, a short hint (renamed vehicles get a new address), the requested address, and buttons to Overview and Vehicles.

## 0.3.55
- **Home without model line:** more air between the name and the HU / maintenance chips, and the car sits closer to the chips.

## 0.3.54
- **Home on phones:** the top of the hero (plate or name) is 18 px from the top edge like the header of every other page (it was 14 px).

## 0.3.53
- **No plate, no plate chip:** without a licence plate Home shows nothing at the top (the dashed placeholder is gone).
- A lone dash in a text field (plate, make, …) counts as empty and is not saved.

## 0.3.52
- **Phones:** the primary button in a page header (Edit, Add vehicle) is an icon-only circle, so it can no longer be cut off at the right edge.

## 0.3.51
- **Vehicle data:** *Edit* is a button at the top right of the page header (instead of a small pencil inside the card).

## 0.3.50
- **More:** the vehicle entry is called *Vehicle data*.
- **Vehicle data form** is grouped like the page itself (Vehicle, Technical, Papers & look, Other) with neutral example values as placeholders.

## 0.3.49
- **Back button on phones:** the red "‹ More" line is replaced by a round glass button with an arrow in front of the page title (saves a row, matches the other round buttons).

## 0.3.48
- **Phone tab bar follows the radius tokens:** outer radius = tab radius + padding, so the bar and the highlighted tab are concentric again.

## 0.3.47
- **Changing the car in More keeps you in More:** you land on the More list (or the same page) of the other car instead of its start page.

## 0.3.46
- **Same line everywhere:** the page title sits in a fixed 44 px row on every page, and next to the More list the first card of the page starts on exactly the same line as the first card of the list (checked on vehicle data, vehicles, documents, tires, appointments, settings, integrations).

## 0.3.45
- **Switch-car icon is a real circle** (40 × 40 px, 9 px to the card edge on all sides): the global button rule had stretched it.

## 0.3.44
- **Less rounded corners everywhere:** radius tokens reduced (cards 22 → 16 px, medium 16 → 12 px, small 12 → 8 px); round chips and the floating tab bar stay round.

## 0.3.43
- **Fixed spacing tokens** (`--sp-edge`, `--sp-col`, `--sp-top`, `--sp-head`, `--sp-block`, `--head-h` in `pc-core.css`): edge, column gap, top edge and header height are defined once and used by the page layout, so list and page line up on the same grid (14 px to the edges, 14 px between columns, header 18 px from the top).

## 0.3.42
- **Tablet / desktop:** the page header next to the More list and the *More* title sit on exactly the same line, 18 px from the top like the header of every other page.

## 0.3.41
- **Tablet / desktop:** the page next to the More list fills its column with the same side margin as the list has on the left (it was shrunk and centred).

## 0.3.40
- **Tablet:** the More list no longer sticks to the sidebar (side margin), and it is narrower and more compact between 1000 and 1100 px.

## 0.3.39
- **More like the original:** list + page side by side only from 1000 px (below that the plain list, full width), list column 340–390 px with the *More* heading on top, type sizes of the list as in the original. *Change car* exists only in More, as an icon next to the current car, and only with more than one car (no plate, no button in page headers or the hero).

## 0.3.38
- **First-start pages have no navigation:** language and access pages no longer show the sidebar, tab bar or a "‹ More" link.

## 0.3.37
- **More is ordered for any number of cars:** on top the current car with *Change*, then everything that belongs to this car (pages, *Extensions* = its integrations and plugins), and at the bottom *General* with Account & login, Vehicles and Settings, which are always there. The global page "Services" is now "System services" and reached from Settings.

## 0.3.36
- **Account & login is its own page** (More → App → Account & login), separate from Settings.

## 0.3.35
- The chosen entry in the More list is only a little lighter now; its icons keep their colour (no red).

## 0.3.34
- **Fix: on tablets and desktops the "More" list was missing on the More page itself.** It now stands on the left next to the page, like on all pages under More.

## 0.3.33
- Project notes for contributors (`CLAUDE.md`) and the image scripts (`tools/`). No change to the app.

## 0.3.32
- Start-up tests: `run.sh` is run under unset-variable rules with every combination of optional options, and the real server is started on a fresh data folder (migrations, `/healthz`, first page). The 0.3.30 start failure would have been caught.

## 0.3.31
- **Fix: the add-on did not start in 0.3.30** ("CARASSISTANT_LANGUAGE: unbound variable" in `run.sh`). The optional `language` option is now handled safely, and a test checks that `run.sh` never reads a possibly unset variable.

## 0.3.30
- **Readable vehicle addresses:** `/v/my-golf` instead of `/v/1` (umlauts resolved, spaces become hyphens, a number is appended for equal names; a renamed car gets the new address; old numeric addresses keep working).
- **Vehicle switcher:** a switch button next to the car's name opens a dark overlay with every car (picture, name, plate). It replaces the top bar that pushed every page down with more than one car.
- **Licence plate** as a neutral chip that fits any country; a dashed placeholder until one is entered.
- **Tablet / desktop:** "More" is a second navigation on the left (with "Switch vehicle"), the chosen page opens on the right. Phones are unchanged.
- **Languages are extensible:** a language is one file in `locales/<code>.json` (see `docs/translating.md`); it appears in the first-start question and in Settings by itself, with its own date format and text direction. The add-on option `language` is now optional.
- The cross-fade between pages is removed (it made pages flash light).

## 0.3.29
- After the first vehicle the app now redirects to the access question without a query string (an attempt to avoid a "400: Bad Request" from the Home Assistant proxy seen after adding the first car).
- The first-start language page is always English, including the navigation, until you choose Deutsch.

## 0.3.28
- Home Assistant add-on page: English only, no image and no links (they cannot be used there).
- CI repariert: Die Tests finden ihren Importpfad in der pyproject (die CI ruft `pytest` direkt auf), und `pyyaml` wird installiert.

## 0.3.27
- **Integrations and plugins per car:** *Car → More → Integrations*. Upload a package (`plugin.json` or zip; only the description is read, nothing is executed), set it up, change its settings, replace a plugin's token or remove it. Optional extras (e.g. Webradio) are offered, never added by themselves. The global page is now "Services" (Tankerkönig, MQTT, notifications).
- **A connection token belongs to exactly one car** ("all vehicles" is gone).
- **Connector API:** new fields `doors`, `windows` (merged by name, `null` removes) and `locked`, plus `GET /api/v1/vehicles/<id>/data` to read back. Complete developer docs (EN/DE) in `docs/api*.md` and `docs/plugins*.md`.
- **Security page:** lock banner, summary and door/window lists with their age; open doors and windows count as open points and light the Security tab dot.
- **First start asks for the language** (English or Deutsch); it can still be changed in Settings.
- **Every page except Home has the same header:** icon, title (and the car's name), actions on the right; the car hero with plate and mileage appears on Home only.
- **Settings → Reset to factory settings:** deletes all data and uploaded files after typing RESET; the app starts like new (for testing and a fresh start).
- **Favicon:** trimmed for small sizes plus a `/favicon.ico`; new app icon, add-on logo and banner everywhere.
- Default car picture for vehicles without a photo, home layout with floating inspection/maintenance chips.

## 0.3.26
- **Fix: adding a vehicle could end in "400 Bad Request".** Values typed by hand are now understood: power as `110`, `110 kW` or `150 PS`, displacement as `1968`, `1.968`, `2.0` or `1,6 l`, a VIN with spaces or hyphens, the build date as `03.05.2020`. A rejected form still shows what was wrong and keeps what you typed; it never creates a vehicle.
- **Fix: the start page is Home.** The navigation marked *More* (and showed "‹ More") on the start page while no vehicle existed.
- **Fix: in the narrow sidebar (tablet) the logo now sits exactly centred over the icons.**
- The two main fonts are preloaded to reduce flicker when changing pages.
- **Start page:** "Add vehicle" appears only once (it was shown twice while no vehicle existed). The vehicle switcher at the top right still appears only with more than one vehicle.
- **New app icon, add-on logo and banner**, cut out with a transparent background and matched to the site's colours (accent red to status green, the site's blue-black, Space Grotesk lettering).

## 0.3.25
- Housekeeping: neutral wording in the changelog and in code comments, neutral user name in a test. No functional change.

## 0.3.24
- **The location map is now off by default.** Car Assistant loads nothing from the internet until you switch the map on under Settings → Map. The tile host is allowed in the Content-Security-Policy only while the map is on. Without the map the card shows the coordinates and the navigation buttons.

## 0.3.23
- **Home status:** two plaques at the car picture – **Ignition** (on/off) and **Doors & windows** (closed / one open / n open). They appear only when data exists.
- **Location card** on Home: last known position, "parked since", "last signal", a map and navigation buttons (Waze, Google Maps, Apple Maps). The map is Leaflet (bundled) with OpenStreetMap tiles, dark by default with a sun/moon switch. **Settings → Map** turns the tiles off (OpenStreetMap otherwise sees your IP address and map area); the position is then shown as coordinates.
- Connector API: new field `ignition` (true/false).
- Content-Security-Policy now allows images from `*.tile.openstreetmap.org` and nothing else new; the map script is a separate file (no inline scripts).

## 0.3.22
- **Sidebar fixed:** the glass box around the navigation list is gone. That glass capsule belongs to the phone bar only; the sidebar list is flat again and only the active entry is highlighted. Logo (46 px, small rounding), sidebar width (84 px), subtitle font and the status dot are back to the intended values, and the late style overrides that drifted away from them are removed. A test guards against the box coming back.

## 0.3.21
- **Dots on the tabs:** a tab gets a small dot when the page behind it has an open point (overdue or due soon): Security for every open point, Service and Maintenance for due maintenance, Appointments for due appointments. More only gets a dot when the point sits on a page moved into More. Works in the bottom bar and in the narrow and wide sidebar; screen readers announce "needs attention".

## 0.3.20
- **Vehicle data** page completed: hero card with plate chip and engine line, three groups (Vehicle, Technical, Papers & look) in two columns on wide screens and one column on phones. New optional fields: build date, type, engine, power, displacement, engine and gearbox code, drivetrain, transmission, body, battery, paint code, registration codes (HSN/TSN), key numbers and a notes field for bulbs and spare parts.
- Green badges say where a value comes from: **from car** (pushed by an integration or plugin) and **from VIN** (model year read from the VIN while no year is entered).
- Development: the README now lists the missing test dependency (`pyyaml`).

## 0.3.19
- Navigation settings: no more drop-downs. Drag the handle or use the arrows to arrange all pages; the first four are the bar, the rest moves into More. Pages moved out of the bar head the More page.

## 0.3.18
- New **Vehicle data** page: grouped list (label left, value right in Space Mono, "from car" badge); the pencil opens the edit form.

## 0.3.17
- Pages opened from More now have a back button "‹ More" at the top.

## 0.3.16
- New look: transparent glass (the red glow shines through the tiles), tiles, tab bar and More page. Icons are the Material Design Icons set again (not Google's).

## 0.3.15
- New navigation: Home (fixed), four pages of your choice with your own icons (Settings → Navigation), More (fixed). Icon-only bar; labels only in the wide sidebar.
- New pages: **More** (grouped menu with coloured icon chips) and **Security**. Home tiles appear only when data exists.
- All icons are now Material Design Icons (Apache-2.0). Sidebar: app icon centred above the navigation icons.

## 0.3.14
- Foundation for the community: **Connector API** (`/api/v1`). Integrations and plugins connect with a token (*Integrations → Connections*) and push odometer, fuel level, range and position with one HTTP request. No third-party code runs inside the app. Docs, example script and tests added.

## 0.3.13
- License: GNU GPL v3.0 (`LICENSE`); license texts of Material Design Icons (Apache-2.0) and the fonts (OFL 1.1) added under `licenses/`.

## 0.3.12
- Sidebar: the app icon now lines up exactly with the navigation items (same width, centred). Credits for icons and fonts in README and Settings.

## 0.3.11
- No more white flash when moving between pages: dark colour scheme and cross-page view transition (the old page stays until the next one is ready).

## 0.3.10
- Documentation updated (login, passkeys, icons); "Add repository to my Home Assistant" button in README and install guide; Ko-fi support link (README, settings, GitHub sponsor button).

## 0.3.9
- Navigation: on a car's pages the bottom capsule shows the car's tabs plus a "More" sheet (other tabs, vehicles, filling stations, integrations, settings); the tab strip below the car is gone.
- Fixes the unstyled/white start in Home Assistant: dark background immediately, stylesheet and script are versioned and always revalidated.

## 0.3.8
- Logo: "Car" above "Assistant", set in the app's own font (Space Grotesk).

## 0.3.7
- Login for direct (external) access: users, passwords, passkeys (WebAuthn) and one-time recovery codes. Inside Home Assistant no login is needed; direct access stays locked until an account exists.
- After creating the first car a short setup step asks whether the app stays without login for now or is reachable from outside (account required).
- New *Account & login* card under Settings.

## 0.3.6
- Replace the icon for the whole app or per car under Settings → Icon; icons are used everywhere. Each car has its own web-app manifest (one home-screen app per car).

## 0.3.5
- Banner added to the README files.

## 0.3.4
- New app icon with a thick red-to-green gradient outline, used everywhere (sidebar, favicon, Home Assistant, GitHub banner).

## 0.3.3
- Icons now use the Material Design Icons paths unchanged.

## 0.3.2
- New design: filled Material icons, green status chips and segmented tabs, overview tiles with icon squares and tinted gradients, large light odometer, two-column home on wide screens.

## 0.3.1
- New navigation: sidebar on desktop, floating glass tab bar on phones, vehicle hero card and pill tabs with icons.
- New flat app icon, logo and banner (no gradients).

## 0.3.0
- The web UI is now also reachable on host port 8321 by default (change or switch off under Configuration → Network). Without `access_password` the port stays blocked; the sidebar panel works as before. Settings shows the published port.

## 0.2.2
- Fix: app failed to start with "Invalid configuration – expected a URL" (empty default for the optional `external_url`).

## 0.2.1
- First release as a standalone Home Assistant app (Ingress).
- Vehicles: service book, appointments, maintenance, tyres, modifications, parts, fuel (full-tank-to-full-tank stats), own km counters, trips (GPX/CSV), documents.
- Modular UI: modules and integrations can be switched on/off; "Switch vehicle" menu for several cars.
- MQTT discovery (automatic broker, no password), notifications, ICS calendar, PDF report, backup/restore, fuel stations (Tankerkönig/OpenStreetMap).
- Optional direct access: port, password protection, CSRF protection, `external_url`.
- Dark design with icons; English and German.
