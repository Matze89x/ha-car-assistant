# Die Fahrzeugdatei (ein Auto aus einem anderen System holen)

[🇬🇧 English](vehicle-file.md) · 🇩🇪 Deutsch

Eine **Fahrzeugdatei** ist die Zip-Datei, die *Einstellungen → Auto → Sichern & verwalten* erzeugt (siehe [backup.de.md](backup.de.md)). Dasselbe Format ist der Weg, ein Auto aus jedem anderen Programm oder jeder Tabelle zu holen: Zip bauen, dann *Fahrzeuge → Fahrzeug wiederherstellen*. Das Auto kommt als neues Auto an und sieht aus, als hättest du alles von Hand eingetragen.

## Was in die Zip gehört
- `vehicle.json` - Pflicht. Alles andere ist freiwillig.
- `files/documents/<id><Endung>` - die Dateien von `documents`.
- Beim Import nicht nötig: Fotos und Videos (in der App hinzufügen), Verbindungs-Token, Integrationen und Plugins, Einstellungen.

## `vehicle.json`
```
{"app": "carassistant", "kind": "vehicle", "format": 1,
  "vehicle": {"name": "Beispiel", "fuel_type": "diesel", ...},
  "tables": {"fuel": [{...}, ...], "service": [...], "trips": [...], "trip_points": [...]}}
```
- `app` muss `carassistant` sein, `kind` `vehicle`, `format` `1` (eine App lehnt nur eine *höhere* Zahl ab).
- Weggelassene Felder bekommen ihren Standard; unbekannte Felder werden ignoriert. Schreibe nie `id`, `vehicle_id`, `slug`, `uid`, `media_id` oder `photo_id` des Autos - die macht die App (die `id` einer Fahrt braucht es nur, damit ihre `trip_points` darauf zeigen können).
- **Immer Basis-Einheiten:** Kilometer, Liter (kWh bei Elektro), Geld als reine Zahl, Reifendruck in bar, Temperaturen in °C. Die App zeigt sie in den Einheiten von *Einstellungen → System → Region*.
- **Datum** `JJJJ-MM-TT`, **Zeit** `HH:MM`, Ja/Nein als `0` / `1`.
- Schreibe nichts in die Texte, was du in der App nicht sehen willst: Es wird genau so angezeigt.

## Die Tabellen
| Tabelle | Felder (`!` = Pflicht) |
|---|---|
| `odometer` | `date!` `odometer_km!` `source!` (beliebiger Text, z. B. `import`) |
| `fuel` | `date!` `odometer_km` `amount` (Liter, kWh bei Elektro) `price_per_unit` `price_total` `full_tank!` (0/1) `station` `notes` |
| `service` | `date!` `odometer_km` `title!` `workshop` `cost` `notes` |
| `appointments` | `kind!` (`inspection`, `service`, `other`) `title!` `due_date!` `month_only!` (0/1) `notes` `done!` (0/1) |
| `tasks` | `title!` `interval_km` `interval_months` `keywords` `last_date` `last_km` `muted!` (0/1) `notes` |
| `tires` | `name!` `season!` (`summer`, `winter`, `allseason`) `size` `dot` `storage` `rear_name` `rear_size` `mounted!` (0/1) `mounted_date` `mounted_km` `notes` |
| `tire_pressure` | `season!` (`summer`, `winter`, `allseason`) `front_bar` `rear_bar` `load_front_bar` `load_rear_bar` - Empfohlener Reifendruck (bar) je Saison |
| `mods` | `date!` `odometer_km` `title!` `cost` `notes` |
| `parts` | `date!` `name!` `part_number` `manufacturer` `shop` `quantity` `cost` `installed!` (0/1) `installed_km` `notes` |
| `counters` | `name!` `kind!` (`tax`, `business`, `private`, `other`) `start_date!` `start_km!` `end_date` `end_km` `notes` |
| `trips` | `date!` `start_time` `end_time` `start_km` `end_km` `start_place` `end_place` `category!` (`private`, `business`, `commute`) `purpose` `source!` `distance_km`; die Route kommt in `trip_points` (`trip_id!` = die `id` der Fahrt, `seq!`, `lat!`, `lon!`, `ts`) |
| `documents` | `category!` `title!` `filename!` `mime` `size` - die Datei selbst liegt in `files/documents/<id><Endung>` |
| `equipment` | `category!` (eines von `comfort`, `seats`, `controls`, `lights`, `packages`, `interior`, `wheels`, `tech`, `exterior`, `media`, `assist`, `roof`) `title!` `code` `status!` (`series`, `option`, `retrofit`, `missing`) `note` `sort` |
| `manuals`, `manual_chapters`, `manual_pages` | das Handbuch: eine Zeile `manuals` (`title`, `source_name`, `pages`, `page_offset`, `images`), seine Kapitel (`grp`, `title`, `page`, `sort`, `depth`) und der Text jeder Seite (`page`, `text`); Seitenbilder liegen unter `files/manual/<NNNN>.<avif/jpg/png/webp>` |

`vehicle` (das Auto selbst): `name!` `fuel_type!` (`petrol`, `diesel`, `lpg`, `cng`, `hybrid`, `electric`) und beliebig viele von `make` `model` `variant` `year` `plate` `vin` `tank_l` `color` `notes` `build_date` `first_reg` `model_type` `engine` `power_kw` `displacement_ccm` `drivetrain` `transmission` `body_type` `engine_code` `gearbox_code` `battery` `battery_kwh` `paint_code` `hsn` `tsn` `key_numbers` `oil_spec` `oil_l` `seats` `gross_weight_kg`.

## Hinweise für einen guten Import
- Eine **odometer**-Zeile je bekanntem Stand genügt; der höchste Wert ist der Kilometerstand des Autos. Tank-, Service- und Fahrtzeilen mit `odometer_km` helfen auch den Diagrammen.
- Tanken: Ist Menge oder Gesamtpreis unbekannt, lass das Feld weg - schreibe nie `0`. Markiere nur echte Volltankungen mit `full_tank` 1 (der Verbrauch wird zwischen Volltankungen berechnet).
- Wartungs-**Aufgaben** brauchen `title` und ein Intervall (`interval_km` und/oder `interval_months`); `last_date`/`last_km` sagen der App, wann es zuletzt gemacht wurde, damit sie die Fälligkeit nennen kann.
- Prüfe das Ergebnis: Auto öffnen, die Listen und den *Bericht* ansehen; stimmt etwas nicht, das Auto wieder löschen und die Datei neu bauen.

## Beispiel
[`docs/examples/make_vehicle_file.py`](examples/make_vehicle_file.py) schreibt eine kleine gültige Datei, nur mit der Python-Standardbibliothek.
