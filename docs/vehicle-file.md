# The vehicle file (bring a car in from another system)

🇬🇧 English · [🇩🇪 Deutsch](vehicle-file.de.md)

A **vehicle file** is the zip that *Settings → Car → Backup and manage* makes (see [backup.md](backup.md)). The same format is the way to bring a car in from any other program or spreadsheet: build the zip, then *Vehicles → Restore a vehicle*. The car arrives as a new car and looks as if you had entered everything by hand.

## What goes into the zip
- `vehicle.json` - required. Everything else is optional.
- `files/documents/<id><extension>` - the files of `documents`.
- Not needed when importing: photos and videos (add them in the app), connection tokens, integrations and plugins, settings.

## `vehicle.json`
```
{"app": "carassistant", "kind": "vehicle", "format": 1,
  "vehicle": {"name": "Example", "fuel_type": "diesel", ...},
  "tables": {"fuel": [{...}, ...], "service": [...], "trips": [...], "trip_points": [...]}}
```
- `app` must be `carassistant`, `kind` `vehicle`, `format` `1` or `2` (an app only refuses a *higher* number than it knows; format 2 is what Car Assistant makes now and adds optional tables, where each package came from and the block `secrets.enc` - for a file from another program `1` is fine).
- Fields you leave out get their default; fields the app does not know are ignored. Never write `id`, `vehicle_id`, `slug`, `uid`, `media_id` or `photo_id` of the car - the app makes them (a trip's `id` is only needed so its `trip_points` can point to it).
- **Base units, always:** kilometres, litres (kWh for an electric car), money as a plain number, tyre pressure in bar, temperatures in °C. The app shows them in the units of *Settings → System → Region*.
- **Dates** `YYYY-MM-DD`, **times** `HH:MM`, yes/no as `0` / `1`.
- Keep the text free of anything you would not want to see in the app: it is shown exactly as written.

## The tables
| Table | Fields (`!` = required) |
|---|---|
| `odometer` | `date!` `odometer_km!` `source!` (any text, e.g. `import`) |
| `fuel` | `date!` `odometer_km` `amount` (litres, kWh for electric) `price_per_unit` `price_total` `full_tank!` (0/1) `station` `notes` |
| `service` | `date!` `odometer_km` `title!` `workshop` `cost` `notes` |
| `appointments` | `kind!` (`inspection`, `service`, `other`) `title!` `due_date!` `month_only!` (0/1) `notes` `done!` (0/1) |
| `tasks` | `title!` `interval_km` `interval_months` `keywords` `last_date` `last_km` `muted!` (0/1) `notes` |
| `tires` | `name!` `season!` (`summer`, `winter`, `allseason`) `size` `dot` `storage` `rear_name` `rear_size` `mounted!` (0/1) `mounted_date` `mounted_km` `notes` |
| `tire_pressure` | `season!` (`summer`, `winter`, `allseason`) `front_bar` `rear_bar` `load_front_bar` `load_rear_bar` - Recommended tyre pressures (bar) per season, normal and fully loaded |
| `mods` | `date!` `odometer_km` `title!` `cost` `notes` |
| `parts` | `date!` `name!` `part_number` `manufacturer` `shop` `quantity` `cost` `installed!` (0/1) `installed_km` `notes` |
| `counters` | `name!` `kind!` (`tax`, `business`, `private`, `other`) `start_date!` `start_km!` `end_date` `end_km` `notes` |
| `trips` | `date!` `start_time` `end_time` `start_km` `end_km` `start_place` `end_place` `category!` (`private`, `business`, `commute`) `purpose` `source!` `distance_km`; the route goes into `trip_points` (`trip_id!` = the trip's `id`, `seq!`, `lat!`, `lon!`, `ts`) |
| `documents` | `category!` `title!` `filename!` `mime` `size` - the file itself goes to `files/documents/<id><extension>` |
| `equipment` | `category!` (one of `comfort`, `seats`, `controls`, `lights`, `packages`, `interior`, `wheels`, `tech`, `exterior`, `media`, `assist`, `roof`) `title!` `code` `status!` (`series`, `option`, `retrofit`, `missing`) `note` `sort` |
| `manuals`, `manual_chapters`, `manual_pages` | the manual: one `manuals` row (`title`, `source_name`, `pages`, `page_offset`, `images`), its chapters (`grp`, `title`, `page`, `sort`, `depth`) and the text of every page (`page`, `text`); page images go to `files/manual/<NNNN>.<avif/jpg/png/webp>` |

`vehicle` (the car itself): `name!` `fuel_type!` (`petrol`, `diesel`, `lpg`, `cng`, `hybrid`, `electric`) and any of `make` `model` `variant` `year` `plate` `vin` `tank_l` `color` `notes` `build_date` `first_reg` `model_type` `engine` `power_kw` `displacement_ccm` `drivetrain` `transmission` `body_type` `engine_code` `gearbox_code` `battery` `battery_kwh` `paint_code` `hsn` `tsn` `key_numbers` `oil_spec` `oil_l` `seats` `gross_weight_kg`.

## Notes for a good import
- One **odometer** line per known reading is enough; the highest value is the car's mileage. Fuel, service and trip lines with `odometer_km` also help the charts.
- Fuel: when the amount or the total price is unknown, leave the field out - never put `0`. Mark only real full tanks with `full_tank` 1 (consumption is calculated between full tanks).
- Maintenance **tasks** need `title` and an interval (`interval_km` and/or `interval_months`); `last_date`/`last_km` tell the app when it was last done, so it can say when it is due.
- Check the result: open the car, look at the lists and the *Report*; remove the car again if something is off and build the file anew.

## Example
[`docs/examples/make_vehicle_file.py`](examples/make_vehicle_file.py) writes a small valid file with the Python standard library only.
