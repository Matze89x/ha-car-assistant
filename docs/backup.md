# Backups

🇬🇧 English · [🇩🇪 Deutsch](backup.de.md)

Car Assistant has two separate backups. Each can be made and restored on its own.

## Secrets and the passphrase

A backup file is made to be carried around - to another system, into a cloud folder, to a friend - so **without a passphrase it holds no secret**: no kept connection token, no password of a plugin, no access key of a source, no access code of an integration page.

With a **passphrase** (at least 8 characters, chosen when the backup is made, never stored) all of them travel in one block of the file, `secrets.enc`. The block is encrypted with a key derived from the passphrase (scrypt with a fresh random salt) and authenticated: a wrong passphrase or a changed block is recognised, and nobody reads it without the passphrase. The passphrase is typed into a form - it is never part of an address, a log or the file.

- A file with secrets asks for its passphrase when it is restored. A wrong one stops before anything is touched. *Restore without the secrets* brings everything else back and leaves tokens, passwords, keys and codes empty.
- A lost passphrase loses only the secrets (set the plugins up again, enter the passwords again); the data is in the file anyway.
- The safety copy that Car Assistant makes before it replaces a car or the whole system stays on this system and keeps its secrets sealed with this system's key, so undoing a restore there needs no passphrase.

## 1. Vehicle backup (one car)

The file format is described in [vehicle-file.md](vehicle-file.md) - it is also the way to import a car from another program.

*Settings → Car → Backup and manage* downloads one zip with everything that belongs to **that car only**:

- the vehicle and all its lists (service, fuel and charging, **charging sessions**, trips with their route and summaries, appointments, tasks, tyres, modifications, parts, counters, documents, photos and videos), its live values, and the events, positions and signals its plugins reported
- the **manual** with its page images, when it was imported as a package (see [manual-package.md](manual-package.md); the images add their size to the file, up to the 500 MB limit)
- **every setting of that car** (navigation, Home widgets, hidden functions, the price of electricity at home, ...)
- its **connection tokens** (the fingerprint the server keeps, so a plugin keeps working with the token it already has); with a passphrase also the kept token itself, so the set-up guide can offer it again
- its **integrations and plugins** with their settings and entries, **where each one came from** (its source, version and checksum) and whether it was running - but **not the packages themselves**; with a passphrase also the passwords of the plugins, the access keys of their sources and the access codes of the integration pages

*Add vehicle → Restore a vehicle from a backup* creates a **new** vehicle from such a file (the same name gets a number); a car that is already here is replaced or copied, as you choose. After a restore:

- integrations and plugins are **switched off** - switch them on on purpose;
- a package that is not installed yet shows as *needs the package* under Plugins / Integrations. If a source offers it there is an *Install* button; if the source is missing the page says which address to add under *Sources* first;
- a token that this system already knows (a copy next to the original) is not duplicated: set the plugin up again for a new one.

## 2. System backup (everything)

*Settings → System → Back up* is the whole database plus all files: every vehicle, **users** and settings. With a passphrase, the secrets of the database - the kept tokens, the passwords of plugins, the access keys of sources, the access codes and the push key - leave the copy and travel in the encrypted block, so a restore on **another system** brings them back (sealed with that system's key). Without one they stay sealed with this system's key and are useless anywhere else. The password hashes of all users are in the file either way: keep it safe. Restoring replaces everything (a safety copy of the current state is kept).

## Compatibility

Every backup carries a `format` number (now **2**; the system backup also the number of its database `schema`). **A newer Car Assistant restores every older format** - from now on, not only from 1.0:

- the *golden files* of [`tests/fixtures/backups/`](../tests/fixtures/backups/README.md) - one backup of every format that ever existed, made by the code of that format and never changed - are restored by the test suite on every change; a new format brings its golden file first, or the tests fail;
- an older database is brought up to date by the migrations; the reader ignores columns it does not know and fills missing ones with their default, so small changes never break an old file;
- a backup from a **newer** app is refused with a hint to update;
- nothing of a car can be forgotten when the app grows: every table of the database is either part of the vehicle backup or named in `vehiclebackup.py` as left out, with the reason (logs and traffic views of the plugins, the people and devices of the whole system) - a test fails for a new table that is in neither list - and so is every setting the code keeps per car.

What changed: **format 2** (0.5.37) - charging sessions, trip summaries, events, positions and signals of a car, every setting of a car (the price of electricity at home was missing), where each package came from, and the secrets block; **format 1** - the first.

The demo cars of the [sources repository](https://github.com/Matze89x/ha-car-assistant-sources) are vehicle backups made this way (`tools/make_demo_vehicles.py`); to refresh one, restore it, adjust it and download its backup again.
