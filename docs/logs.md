# The logs

🇬🇧 English · [🇩🇪 Deutsch](logs.de.md)

Car Assistant keeps **two logs**. They say different things, and each one is where you look for its own kind of trouble.

| | The log of the add-on | The *Logs* page of a plugin |
|---|---|---|
| **Where** | Home Assistant: *Settings → Apps → Car Assistant → Log* (or *Settings → System → Logs*, then choose the app) | In the app: the tile of a plugin → *Logs* |
| **What it says** | The app itself: how it starts, what it cannot reach, what went wrong - and, one level lower, what it does | What ONE plugin does for ONE car: readings, runs, commands, logins, the life of its service |
| **How much** | The option `log_level` of the app (*Configuration* tab, see below) | Problems always; the detail lines only while the *Debug* switch of that plugin is on (it switches itself off after a few days) |
| **Kept** | By Home Assistant | By the app: the newest lines of every plugin; for how long: *Settings → System* |

## The levels of the add-on log

| `log_level` | What you see |
|---|---|
| `error` | Only errors: something broke - a round of a job, a plugin's service that stopped by itself, a login that failed - with the details a developer needs. |
| `warning` (default) | Errors and warnings: Home Assistant or the MQTT broker cannot be reached, a notification could not be sent, a plugin has trouble with one of its entities, a source or a provider answered badly. The same warning is written once in five minutes; the next one says *repeated 12x in the last 6 min*. |
| `info` | And what the app does: the start, a database that moved on, the live connection to Home Assistant, MQTT, the reading of sources, the look for a newer version, backups, and the lines the app writes for plugins (a reading started, a command sent, a login, a service started). |
| `debug` | And one line for every page that is asked for (`GET /v/{vid}/fuel -> 200 (31 ms)`) and one for every delivery of values (`data from Home Assistant for vehicle 1: odometer_km: stored`). |

Change it in *Settings → Apps → Car Assistant → Configuration*, save, and restart the app. `info` and `debug` are for finding a problem: switch back to `warning` afterwards. An app that was set up before this page existed keeps the level it was saved with (`error` was the default then).

A line looks like this:

```text
2026-11-27 12:03:10 DEBUG   carassistant.http: GET /v/{vid}/fuel -> 200 (31 ms)
2026-11-27 12:03:11 DEBUG   carassistant.connectors: data from Home Assistant for vehicle 1: odometer_km: stored
2026-11-27 12:05:00 WARNING carassistant.plugins: [car 1] home-assistant: Home Assistant cannot be reached; trying again
```

The lines that start with `[car 1] home-assistant` are the lines the app writes into the *Logs* page of that plugin, said here as well - so one place tells the whole story. What a plugin sends or prints itself stays on its own page.

## What is never in it

The log of the add-on is what people copy into a forum, so it is written to be safe to copy - at every level:

- **No token, password or key.**
- **No value of the car** (position, odometer, tank level ...): a delivery names the fields and what became of each (*stored*, *ignored*), never the numbers.
- **No address with numbers or a token in it, no query, no body.** A request is called by the *pattern* of its route (`/v/{vid}/fuel`), not by what was asked for. The checks of the watchdog and the files of the app's own styles and scripts are left out.
- **No name of a person.** A command says what was sent, not who pressed the button - that stands on the *Logs* page of the plugin.
- **No free text of a plugin.** What a plugin sends to the app or prints stays on its own *Logs* page.

The libraries the app uses are heard only from warning on, whatever the level is, so `debug` shows the app and not its parts.

Still read what you copy before you post it.
