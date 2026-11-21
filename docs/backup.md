# Backups

🇬🇧 English · [🇩🇪 Deutsch](backup.de.md)

Car Assistant has two separate backups. Each can be made and restored on its own.

## 1. Vehicle backup (one car)

The file format is described in [vehicle-file.md](vehicle-file.md) - it is also the way to import a car from another program.

*Settings → Car → Backup and manage* downloads one zip with everything that belongs to **that car only**:

- the vehicle and all its lists (service, fuel / charging, trips with their route, appointments, tasks, tyres, modifications, parts, counters, documents, photos and videos), its live values
- the **manual** with its page images, when it was imported as a package (see [manual-package.md](manual-package.md); the images add their size to the file, up to the 500 MB limit)
- its settings (navigation, Home widgets, hidden functions)
- its **connection tokens** (the fingerprint the server keeps, so a plugin keeps working with the token it already has)
- its **integrations and plugins with their settings** - but **not the packages themselves**

*Add vehicle → Restore a vehicle from a backup* creates a **new** vehicle from such a file (the same name gets a number). After a restore:

- integrations and plugins are **switched off** - switch them on on purpose;
- a package that is not installed yet shows as *needs the package* under Plugins / Integrations. If a source offers it there is an *Install* button; if the source is missing the page says which address to add under *Sources* first;
- a token that this system already knows (a copy next to the original) is not duplicated: set the plugin up again for a new one.

The file holds plugin settings, which can include passwords: keep it safe. Access codes saved in `secret` fields of an integration (see [integrations.md](integrations.md)) are **left out**; *Backup with access codes* (offered only when the car has some) makes a separate file that contains them in plain text.

## 2. System backup (everything)

*Settings → System → Back up* is the whole database plus all files: every vehicle, **users** and settings. The file also contains saved **access codes** and the password hashes of all users: keep it safe. Restoring replaces everything (a safety copy of the current state is kept).

## Compatibility

Every backup carries a `format` number. **From version 1.0 on, a newer Car Assistant restores every older format**; a backup from a newer app is refused with a hint to update. The reader ignores columns it does not know and fills missing ones with their default, so small changes never break an old file. Before 1.0 the format may still change.

The demo cars of the [sources repository](https://github.com/Matze89x/ha-car-assistant-sources) are vehicle backups made this way (`tools/make_demo_vehicles.py`); to refresh one, restore it, adjust it and download its backup again.
