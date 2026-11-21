# Security policy

🇬🇧 English · [🇩🇪 Deutsch](SECURITY.de.md)

Car Assistant is made in spare time by one person. Security reports are taken seriously and read first.

## Report a vulnerability

**Please do not open a public issue for a security problem.** Use GitHub's private reporting instead: open the **Security** tab of this repository and choose **Report a vulnerability**. Describe what you found, how to reproduce it and which version you used (*Settings → About*). You will get an answer as soon as possible, usually within a few days.

## Supported versions

Only the latest release gets fixes. Please update first and check that the problem is still there.

## What is in scope

- Getting in without signing in, or reaching data of another car or user.
- A normal user doing what only an administrator may (backup, restore, system settings, sources, tokens).
- The Plugin API accepting a wrong token, or a token reaching a car it does not belong to.
- A package, a service or an uploaded file breaking out of its limits (reading the database or the Home Assistant token, writing outside its folder).
- Cross-site scripting or cross-site request forgery in the app's pages.

## How Car Assistant protects you (short)

- Inside Home Assistant the sidebar panel needs no login. Direct access needs a port **and** a user (password, optionally a passkey); after 5 wrong tries an address is locked for 15 minutes. Use HTTPS from outside.
- The Plugin API accepts one token per car and nothing else.
- Packages are read, not run - with **one exception: a service**, which is foreign code. It runs only from a source you added, only after you approved what it does, as its own unprivileged program with limits, and never sees the database or the Home Assistant token. Only approve services from sources you trust.
- Nothing is fetched from the internet on its own (map, fuel prices, sources are opt-in).

More: [Plugins and services](docs/plugins.md) · [Backup](docs/backup.md).
