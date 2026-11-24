# Screenshots

🇬🇧 English · [🇩🇪 Deutsch](screenshots.de.md)

This is what Car Assistant looks like in use. All pictures show a **demo car with made-up data** (a diesel and an electric car with two years of history); no real vehicle, no real places. You can create the demo car yourself: *Add vehicle → Demo car*.

## Dashboard

The car at a glance: the odometer (with a *Change odometer* button), range, messages of the car, next inspection, open points and widgets such as the last trip, fuel and consumption.

![Dashboard](screenshots/en/dashboard.png)

### Location on a real map

Below the car data the **location card** shows where the car is parked (or that it is driving), on a map in the colours of your design, and three links to open the place in Waze, Google Maps or Apple Maps. The map tiles come from OpenStreetMap only when you allow it (*Settings → System*); nothing is loaded before.

![Dashboard with the location map](screenshots/en/dashboard-map.png)

## Dashboard (electric)

The same page for an electric car: charging, battery and range instead of a tank.

![Dashboard (electric)](screenshots/en/dashboard-ev.png)

## Fuel

All fill-ups by month with consumption and prices. The **station search** on top is deliberately simple: the car decides the fuel, the radius is 15 km, each station is one line with name, distance and price, and the cheapest is marked in green.

![Fuel](screenshots/en/fuel.png)

## Evaluation (costs)

What the car costs in the chosen period: the total, the share of fuel, service, modifications and parts, a chart per period and a list of every priced entry.

![Evaluation](screenshots/en/report.png)

## Trips and trip analysis

The analysis on top (30 days, 90 days, year, all): trips by kind and length, a heat map of weekday and time of day, and the driving style; below it the km counters and the trips by month.

![Trips](screenshots/en/trips.png)

### A trip on the map

Tap a trip and its card opens with the distance, duration, average speed, an estimate of consumption and cost, and the **route on a full-width map** - coloured by speed from blue (slow) over green and yellow to red (from 130 km/h), start and end marked. *Route as GPX* exports it. A link can open a trip directly: `…/e/trips?open=<id>`.

![A trip on the map](screenshots/en/trip-map.png)

## Service

Maintenance with odometer, costs and notes; tap a card to edit it.

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

| A trip on the map | Tyres |
|---|---|
| <img src="screenshots/en/mobile-trip-map.png" alt="A trip on the map" width="260"> | <img src="screenshots/en/mobile-tires.png" alt="Tyres" width="260"> |

More: [User guide](guide.md) · [Install](install.md) · [MCP access](mcp.md)
