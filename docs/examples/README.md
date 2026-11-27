# Examples

🇬🇧 English · [🇩🇪 Deutsch](README.de.md)

Small, complete starting points. Copy one, change the names and build your own. How the parts fit together is drawn in [architecture.md](../architecture.md).

| Example | What it shows | Read |
|---|---|---|
| [push_data.py](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/examples/push_data.py) | A **plugin script**: reads values (replace `read_car()`) and sends them with one HTTP request. Standard library only. | [Plugin API](../api.md) |
| [sdk/carassistant_sdk.py](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/examples/sdk/carassistant_sdk.py) | The **helper library** of a plugin service, one file, standard library only: settings, a small web client with sessions, the Plugin API, routes, the main loop. `tools/new_plugin.py` copies it next to your `main.py`. | [Start here](../start-here.md) |
| [echo-service/](https://github.com/Matze89x/ha-car-assistant/tree/main/docs/examples/echo-service) | A **plugin with a service**: its own small program that answers on a route (`/echo/ping`), with a setting. | [Plugins](../plugins.md#plugins-with-a-service) |
| [example-stations/](https://github.com/Matze89x/ha-car-assistant/tree/main/docs/examples/example-stations) | An **integration without code**: a page with typed fields that Car Assistant draws and stores per car. | [Integrations](../integrations.md) |
| [home-assistant/](https://github.com/Matze89x/ha-car-assistant/tree/main/docs/examples/home-assistant) | A **plugin without code or service** that brings entities of Home Assistant into the car: the whole settings page comes from one key, `bridge`. | [Home Assistant plugin](../home-assistant.md) |
| [make_vehicle_file.py](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/examples/make_vehicle_file.py) | Writes a **vehicle file** to bring a car from another program. | [Vehicle file](../vehicle-file.md) |

Check a package before you share it: `python tools/check_plugin.py <folder>`. Everything here uses neutral values (`car.example.com`, `Example`); a test keeps these examples readable by the app.
