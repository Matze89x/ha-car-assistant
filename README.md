# Car Assistant

![Car Assistant](docs/banner.png)

[![CI](https://github.com/Matze89x/ha-car-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Matze89x/ha-car-assistant/actions/workflows/ci.yml) [![License: GPL v3](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)

📷 **[Screenshots](docs/screenshots.md)** – the app in use · 🧭 **[Architecture](docs/architecture.md)** – how everything fits together, for plugins and integrations too

🇬🇧 English · [🇩🇪 Deutsch](README.de.md)

<!-- release:start -->
[![Release](https://img.shields.io/badge/release-0.5.26%20Beta-orange.svg)](carassistant/CHANGELOG.md) The public test version. Please try it and report what you find.
<!-- release:end -->

**Your car's own logbook and dashboard.** Car Assistant keeps **every document and all the data of your vehicles in one place** – papers, invoices and manuals stored digitally, plus the data of the car itself as soon as a plugin delivers it (it runs as an app inside Home Assistant) – one or many cars, combustion, hybrid or electric:

- ⛽ fuel stops and charging sessions with consumption and cost statistics, the cheapest **fuel stations nearby** in one line each
- 🔧 service book, extra work (maintenance schedule) with reminders, appointments (MOT/TÜV, insurance) and calendar export
- 📦 spare parts you bought (part number, shop, price, installed where)
- 📄 all documents: manuals, invoices, insurance and registration papers
- 🛞 tyre sets with recommended pressures per season, modifications, trips with the **route on a map coloured by speed** (GPX/CSV, PDF export)
- 🧮 your own km counters, e.g. for the tax year
- 📘 the **vehicle passport** with the facts you need, a VIN copy button and a list of equipment; the car's **manual** (import a PDF / EPUB / text, chapters, search, EPUB export)
- 📍 status and location on Home (ignition, doors, tyre pressures, position with map) as soon as a plugin delivers the data
- 🔌 **plugins connect the outside world** – a car, a manufacturer's cloud, a web service you log in to, a device: the plugin talks to the outside, Car Assistant only offers the [Plugin API](docs/api.md)
- 🔔 reminders to your phone **per car** (web push or the Home Assistant notify service), optional sensors and the car's GPS position in Home Assistant via MQTT (off by default)
- 📊 a **cost page** (what every car costs, by fuel, service, modifications and parts, with every entry listed) and a **trip analysis** (lengths, weekday and time of day, driving style)
- 🤖 **MCP access for Claude**: let Claude read your records - and, if you allow it, complete or correct them - from the web chat, the desktop app or your phone; off by default, one switch, one key ([MCP access](docs/mcp.md))
- 📱 a **web app per car** for the home screen: it opens straight on that car and shows only that car
- 💾 backups of one car or of everything, a demo car to just have a look, language and units (metric / imperial) as you like
- 🔐 login for access from outside (password, passkeys) – none needed inside Home Assistant; the port is off until you set it, and direct access always needs a user
- 🎨 a design in light, dark or automatic with a colour of your own - for the whole app or for one car - and an icon per car (logo or photo in the coloured frame; favicon, iPhone and web-app icons are made for you)

Everything is modular: switch modules and integrations on or off under **Integrations**, like in Home Assistant. Data stays local, nothing goes online unless you switch it on.

**Built for a community.** Anyone can write a plugin and dock it on with one HTTP request – start with the [plugin guide](docs/plugin-guide.md). Plugins come from *sources* (a repository with an index) and can offer settings, files, pages and even a small service of their own. A service runs inside the app only after an administrator approved it – it is foreign code, so use sources you trust. New things are meant to be added without touching the core.

## Installation
[![Add the repository to my Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMatze89x%2Fha-car-assistant)

The button adds the repository to your Home Assistant; install *Car Assistant* from the app store. The same store also lists *Car Assistant Developer* (the newest development state, version like `0.5.1.3`, own data, for testing). More ways (also without GitHub): [docs/install.md](docs/install.md).

## Documentation

Everything exists in English and in German; switch the language at the top of any page.

**Use it**

| Page | What it is about |
|---|---|
| [User guide](docs/guide.md) | every page of a car, step by step |
| [Screenshots](docs/screenshots.md) | the app in use |
| [Install](docs/install.md) | in Home Assistant, from the repository or as a local app |
| [Backups](docs/backup.md) | back up and restore one car or everything |
| [MCP access](docs/mcp.md) | let Claude Code read and correct your records (off by default) |
| [Manual package](docs/manual-package.md) | import a manual with page images |
| [Vehicle file](docs/vehicle-file.md) | bring a car in from another program |
| [Roadmap](docs/roadmap.md) | what is done and what is next |

**Connect your own (plugins and integrations)**

| Page | What it is about |
|---|---|
| [Architecture](docs/architecture.md) | how everything fits together, as diagrams |
| [Plugin guide](docs/plugin-guide.md) | the quickest start |
| [Plugins](docs/plugins.md) | package format, settings page, services, files, tiles |
| [Fuel price providers](docs/fuel-providers.md) | an open JSON file per country for fuel prices |
| [Integrations](docs/integrations.md) | pages without code, reminders, plans |
| [Plugin API](docs/api.md) | all fields and ways to send values to the app |
| [Sources and packages](docs/sources.md) | offer a repository as a source |
| [Examples](docs/examples/README.md) | complete starting points to copy |

**Work on the app itself**

| Page | What it is about |
|---|---|
| [Design](docs/design.md) | components, colours, spacing |
| [Design contract](docs/design-contract.md) | the fixed rules of the interface |
| [Icons](docs/icons.md) | the icon set and how to use it |
| [Maintaining](docs/maintaining.md) | from a report to a version: labels, milestones, releases |
| [Translating](docs/translating.md) | a new language as a file |

**Also**

| Page | What it is about |
|---|---|
| [Add-on page in Home Assistant](carassistant/DOCS.md) | the *Documentation* tab of the add-on |
| [Security](SECURITY.md) | how to report a vulnerability and how the app protects you |
| [Contributing](CONTRIBUTING.md) | how to help: rules, tests, pull requests |
| [Changelog](carassistant/CHANGELOG.md) | what changed in which version |

## Development
```
pip install -r carassistant/requirements.txt pytest ruff httpx pyyaml
CARASSISTANT_DEV=1 pytest
ruff check . && ruff format --check .
```

## Why this project exists
Car Assistant grew out of an idea that has been with me for many years: one place where everything about the cars of a family is kept and evaluated - papers, service, fuel, and above all *what becomes due next in which car*. For years I collected and documented this data privately, down to the values read from the cars with a diagnostic tool, and built my own overview with HTML, PHP and an SQLite database. What was still missing was building it properly. This app is that step, made together with Claude (an AI assistant) and shared with everyone who looks after one or more cars.

## Support
Car Assistant is free and made in spare time. If it helps you, you can buy me a coffee:

[![Support on Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/matze89x)

## Thanks
Thanks to [Home Assistant](https://www.home-assistant.io/) and its community - the home of this app - and to everyone who tests, reports and improves. Car Assistant stands on many open-source projects; the full list is in [NOTICE.md](NOTICE.md). Icons: [Material Design Icons](https://pictogrammers.com/library/mdi/) (Apache License 2.0), fonts Space Grotesk and Space Mono (SIL Open Font License 1.1).

## License
[GNU General Public License v3.0](LICENSE) – © 2026 Matze89x. You may use, study, change and share Car Assistant; if you pass it on (changed or not), it must stay under the same license with the source code available.
