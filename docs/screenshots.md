# Screenshots

🇬🇧 English · [🇩🇪 Deutsch](screenshots.de.md)

This is what Car Assistant looks like in use. All pictures show a **demo car with made-up data** (a diesel and an electric car with two years of history, and a compact car with little data); no real vehicle, no real places. You can create the demo car yourself: *Add vehicle → Demo car*.

## Dashboard

The car at a glance: the odometer (with a *Change odometer* button), range, messages of the car, next inspection, open points and widgets such as the last trip, fuel and consumption.

![Dashboard](screenshots/en/dashboard.png)

### Location on a real map

Below the car data the **location card** shows where the car is parked (or that it is driving), on a map in the colours of your design, and three links to open the place in Waze, Google Maps or Apple Maps. The map tiles come from OpenStreetMap only when you allow it (*Settings → System*); nothing is loaded before.

![Dashboard with the location map](screenshots/en/dashboard-map.png)

## Dashboard (electric)

The same page for an electric car: charging, battery and range instead of a tank.

![Dashboard (electric)](screenshots/en/dashboard-ev.png)

## Quick entry: the odometer from a photo

Tap the odometer on the dashboard: it turns over to a box. Type the number or tap the camera and photograph the lower part of the cluster - the server reads the number (the trip counter and the dial numbers are ignored), shows it for you to check and saves it only when you press the arrow. No plugin needed.

![The odometer turned over, a photo of the cluster read](screenshots/en/odometer-photo.png)

## Quick entry: a fill-up from a receipt

*Fuel → plus* (or *Complete* on the card of a refuel the car noticed): at the top of the form of every fill-up stand *Scan* (the camera) and *Load file* (a photo from the library, or a PDF receipt). Date, station, fuel, amount, price per unit, total and - when the receipt prints it - the odometer are filled in and marked; amount × price = total is checked. Nothing is saved before *Save*.

![A fuel receipt read: the form is filled in](screenshots/en/fuel-scan.png)

## Fuel

All fill-ups by month with consumption and prices - each one is a till receipt: date and station on top, the amount and its price in a line, the details below; tap it to correct it or to scan a receipt again. When the tank level of the car jumps, a **message card** *Refuel noticed* asks for the receipt with one button; it goes away when the entry is saved, after three trips or after three days. The **station search** on top is deliberately simple: the car decides the fuel, the radius is 15 km, each station is one line with name, distance and price, and the cheapest is marked in green.

![Fuel](screenshots/en/fuel.png)

## All connections of the plugins

*Plugins → Connections*: a zoomable map with the plugins on the left, **every channel of the Plugin API** in the middle - the open ones (hollow rings) too - and where it lands on the right. Zoom with the mouse wheel, drag to move; a click on a plugin, a channel, a place or a line opens the explanation, the connections, the raw value and the last values with date and time below.

![The connection map with one channel opened](screenshots/en/connections-map.png)

## Evaluation (costs)

What the car costs in the chosen period: the total, the share of fuel, service, modifications, parts and fixed costs, a chart per period and a list of every priced entry. The page has three tabs: *Overview*, *Fixed costs* and *Invoices*.

![Evaluation](screenshots/en/report.png)

## Invoices

The third tab of the cost page: *Photograph* an invoice or *Upload* a PDF, a picture or a scan (up to ten files at once). Car Assistant reads it on this server - nothing is sent anywhere - and shows what it found: date, total (net + VAT = total is checked), sender, invoice number, odometer and what kind of cost it is. *Check and book* opens the ordinary form of a service, parts, modification, fixed cost or fill-up entry, filled in; nothing is booked before you save.

![Invoices](screenshots/en/invoices.png)

![One invoice: what was read and the ways to book it](screenshots/en/invoice.png)

## Trips and trip analysis

The analysis on top (30 days, 90 days, year, all): trips by kind and length, a heat map of weekday and time of day, and the driving style; below it the km counters and the trips by month.

![Trips](screenshots/en/trips.png)

### A trip on the map

Tap a trip and its card opens with the distance, duration, average speed, an estimate of consumption and cost, and the **route on a full-width map** - coloured by speed from blue (slow) over green and yellow to red (from 130 km/h), start and end marked. *Route as GPX* exports it. A link can open a trip directly: `…/e/trips?open=<id>`.

![A trip on the map](screenshots/en/trip-map.png)

## Service

Maintenance with odometer, costs and notes; tap a card to edit it. *Service*, *extra work*, *parts* and *modifications* are one entry in *More* with a bar of tabs - like *Costs* (overview, fixed costs, invoices) and *Documents & manual*.

![Service](screenshots/en/service.png)

## Extra work and appointments

Jobs with interval, progress and *Reset*; appointments with their countdown.

![Extra work](screenshots/en/tasks.png)

![Appointments](screenshots/en/appointments.png)

## Parts, tyres and documents

![Parts](screenshots/en/parts.png)

![Tyres](screenshots/en/tires.png)

Tyres have one tab per season; the set carries its name as heading and, when it is on the car, a shield symbol. Modifications are cards by year, added with the plus button.

![Modifications](screenshots/en/mods.png)

## One notice tile on every page

Under every page header sits the same tile: the introduction of the page with an ⓘ - and the messages of the app: *Saved* (green), warnings (yellow) and errors (red), always in the same place and in the colours of your design.

![The notice tile](screenshots/en/notice.png)

![Documents](screenshots/en/documents.png)

## Security

Doors, windows and locking as the car reports them.

![Security](screenshots/en/security.png)

## Vehicle passport

Everything about the car in groups, the VIN with a copy button and the equipment.

![Vehicle passport](screenshots/en/passport.png)

## More, plugins and About

![More](screenshots/en/more.png)

![Plugins](screenshots/en/plugins.png)

![About](screenshots/en/about.png)

## Settings: User, Car, System

The settings have three tabs. **Car** is about the car shown under the title (icon, photo and video, design, Home Assistant entities, backup); **User** is about you (login, your devices and notifications, a start link per car for a web app); **System** is about the whole app (language, units, design, sensors, MCP access, sources, address, backup).

![Settings: User](screenshots/en/settings-user.png)

![Settings: Car](screenshots/en/settings-car.png)

![Settings: System](screenshots/en/settings-system.png)

## Designs

The classic red design and the designs with a colour of your own (light, dark, automatic) - for the whole app or just for one car.

| Classic red | Light | Dark | Automatic |
|---|---|---|---|
| <img src="screenshots/en/design-classic.png" alt="Classic red" width="220"> | <img src="screenshots/en/design-light.png" alt="Light" width="220"> | <img src="screenshots/en/design-dark.png" alt="Dark" width="220"> | <img src="screenshots/en/design-auto.png" alt="Automatic" width="220"> |

## On the phone

On a phone the sidebar becomes a bar at the bottom (Home, up to four pages of your choice, More); the cards stack in one column.

| Dashboard | Fuel | Trips |
|---|---|---|
| <img src="screenshots/en/mobile-dashboard.png" alt="Dashboard" width="260"> | <img src="screenshots/en/mobile-fuel.png" alt="Fuel" width="260"> | <img src="screenshots/en/mobile-trips.png" alt="Trips" width="260"> |

| Evaluation | More | Settings: Car |
|---|---|---|
| <img src="screenshots/en/mobile-report.png" alt="Evaluation" width="260"> | <img src="screenshots/en/mobile-more.png" alt="More" width="260"> | <img src="screenshots/en/mobile-settings-car.png" alt="Settings: Car" width="260"> |

| A trip on the map | Tyres | An invoice |
|---|---|---|
| <img src="screenshots/en/mobile-trip-map.png" alt="A trip on the map" width="260"> | <img src="screenshots/en/mobile-tires.png" alt="Tyres" width="260"> | <img src="screenshots/en/mobile-invoice.png" alt="An invoice" width="260"> |

More: [User guide](guide.md) · [Install](install.md) · [MCP access](mcp.md)
