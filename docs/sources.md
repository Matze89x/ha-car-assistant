# Sources and packages

🇬🇧 English · [🇩🇪 Deutsch](sources.de.md)

A **source** is a place packages (integrations and plugins) are offered from: a GitHub repository or any https address that serves the same files. The list of sources is **one list for the whole server** (*Integrations / Plugins → Sources*). *Add* and *Manage* work per vehicle.

Nothing is requested from a source on its own - only when you add it, press *Update*, open a package, install or update it. Only descriptions are read, **nothing from a package is executed** - except the service of a plugin that you approved yourself ([plugins.md](plugins.md#plugins-with-a-service)). Such a package is a readable folder plus a `package.zip`, and the index names its `sha256`.

## Folder rule

```
index.json                  (optional, reserved)
integrations/
  index.json                the list of all integrations of this source
  <id>/plugin.json          one folder per integration - the folder name is the id
plugins/
  index.json                the list of all plugins of this source
  <id>/plugin.json          one folder per plugin
```

Integrations and plugins are separated by the first folder. A source may offer any number of packages (an index is read up to 200 entries).

### `index.json` (one per kind)

```json
{
  "packages": [
    { "id": "example-plugin", "name": "Example plugin", "description": "Short text", "version": "1" }
  ]
}
```

- `id` - lower-case letters, digits, `-`, `_` (2-41 characters); **must equal the folder name**.
- `name`, `description`, `version` - shown under *Add*; a higher `version` than the installed one offers an **Update**. `icon` (optional) - a name from the icon set ([icons.md](icons.md)): the icon of the tile, before anything is installed. Give the same `icon` in the package's `plugin.json`.
- Versions are compared by numbers (`1.10` is newer than `1.9`).

### `plugin.json`

The description of one package, see [plugins.md](plugins.md) (id, name, version, description, author, homepage, settings). The folder decides the kind (integration or plugin); `id` must equal the folder name.

## Troubleshooting

- The package does not show up: press *Update list* under *Add* (nothing is read on its own unless you switch on the daily check in *Settings → System → Package updates*). One source is one repository for Integrations and Plugins alike; the repository may have `integrations/`, `plugins/` or both - a missing folder is fine. The kind's `index.json` must list the package.
- Each package lives in a folder named exactly like its `id` (`plugins/<id>/plugin.json`). An id uses lowercase letters, digits, `-` and `_` only (2-41 characters); anything else is left out and the reason is shown on the source.
- A private repository needs a token (read access to contents).
- The index may be `{"packages": [...]}` or a bare list. A root `index.json` with `{"name": "..."}` gives the source its name.

## Flow

1. **Sources** - add the address of a repository; a private repository needs an *access key* (a read-only token) which stays on the server.
2. **Add** (per vehicle) - the packages of all sources, tap one to read its description, then *Install*.
3. **Manage** (per vehicle) - settings, *Check for updates* (reads the sources and marks tiles that have a newer version) and *Update* on such a tile, *Start / Stop* (plugins only; integrations have no on/off), *Uninstall*.

A package that was installed **without a source** (from a file) shows *no source* on its tile and is marked *Installed · no source* under *Add* - it is not offered a second time. When a source offers a **newer** version of it, it gets an *Update* like any other and is linked to that source from then on (settings, token and state stay). A source with an older or equal version changes nothing.

If GitHub answers "403" because its hourly limit for anonymous requests (60 per address) is used up, the app says so - the access key is not the problem; try again later.

A source can only be deleted when **no package installed from it** remains.

## Keeping a source current

Your own plugins and integrations belong in a **source** of their own - one repository with a folder per package - and **not** in a fork of the app: a fork that carries your packages drifts away from the app with every release and has to be pulled up again by hand. A source stays independent of the app, and the app keeps it in view instead:

- `python tools/check_source.py <folder of the source>` reads every package the way **this** version of the app reads it (the same check as `tools/check_plugin.py`), compares the indexes with the folders (ids, versions, checksums) and looks at the vehicle files. Errors end with exit code 1, hints (a typo in a key, a missing icon or translation) are only printed.
- The reusable workflow `.github/workflows/check-source.yml` of the app repository runs it on a source. Copy [`docs/examples/source-ci.yml`](examples/source-ci.yml) to `.github/workflows/check.yml` of your source: on every change **and every Monday** the whole source is checked against the newest app, so you hear about a package that no longer fits without having to look. The check lives in the app, so it is always as new as the app; a private source can use it as well. To check against a fixed version, add `with: {app-ref: v0.5.24}`.
- One source for everything that belongs together (the public one for packages anyone may use, a **private** one for personal and car-specific plugins - never public), one folder per package. A package that grows into a project of its own (its own history, releases and helpers) may move to a repository of its own; the source then only lists it.

## Factory setting

After a fresh start the first source is the project's package repository, [ha-car-assistant-sources](https://github.com/Matze89x/ha-car-assistant-sources) - it also holds the instructions for writing your own packages. It can be deleted (when nothing from it is installed) and restored with *Restore the standard source*.
