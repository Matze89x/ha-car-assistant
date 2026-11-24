# Roadmap

🇬🇧 English · [🇩🇪 Deutsch](roadmap.de.md)

- Vehicle integrations for car brands: log in with the manufacturer account, read mileage, service intervals, lock state
- ✅ Plugin API for integrations and plugins ([api](api.md)) with fields for ignition, doors and windows, tyre pressure, position, service data and more; the *connection map* shows every channel, also the open ones
- ✅ Community modules: an integration brings its own pages, widgets and reminders without touching the core ([integrations](integrations.md))
- Next: more languages - a language is one file, see [Translating](translating.md)
- ✅ Units and currencies: miles / km, gallons / litres, mpg, psi and the currency of each country (stored in base units, shown in the units of *Settings → System → Region*)
- ✅ Notifications per user and per car: own notify service, events chosen for each car, web push on an https page
- ✅ Settings in three levels (User, Car, System), a web app per car, the cost page and the trip analysis
- ✅ MCP access: Claude can read - and, if you allow it, complete or correct - your records ([MCP access](mcp.md))
- Beta (0.5.x): the community tests; fixes and improvements are bundled into versions (see [Maintaining](maintaining.md))
- ✅ Reminders from integrations (fuel additive) and Coding as pages of an integration
- ✅ Every page follows the design book, measured in a real browser: alignment with the *More* list, section labels, buttons (one line, one height, one main action), tap areas, names and labels; temperatures follow the unit system (°C / °F)
- ✅ Pages of the car in the original's style: vehicle passport with equipment, trips with km counters and trip cards, fuel with stations, tyres, extra work, modifications, manual (import / search / EPUB export), logs per plugin, plans for reminders (additive plan), Coding as collapsible rows
- Next: more integrations for car brands
