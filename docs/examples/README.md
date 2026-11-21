# Examples

🇬🇧 English · [🇩🇪 Deutsch](README.de.md)

Small, complete starting points. Copy one, change the names and build your own. How the parts fit together is drawn in [architecture.md](../architecture.md).

| Example | What it shows | Read |
|---|---|---|
| [push_data.py](push_data.py) | A **plugin script**: reads values (replace `read_car()`) and sends them with one HTTP request. Standard library only. | [Plugin API](../api.md) |
| [echo-service/](echo-service) | A **plugin with a service**: its own small program that answers on a route (`/echo/ping`), with a setting. | [Plugins](../plugins.md#plugins-with-a-service) |
| [example-stations/](example-stations) | An **integration without code**: a page with typed fields that Car Assistant draws and stores per car. | [Integrations](../integrations.md) |
| [make_vehicle_file.py](make_vehicle_file.py) | Writes a **vehicle file** to bring a car from another program. | [Vehicle file](../vehicle-file.md) |

Check a package before you share it: `python tools/check_plugin.py <folder>`. Everything here uses neutral values (`car.example.com`, `Example`); a test keeps these examples readable by the app.
