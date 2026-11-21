# Installation

🇬🇧 English · [🇩🇪 Deutsch](install.de.md)

Requires Home Assistant OS or Supervised (apps). A plain "Home Assistant Container" install has no apps.

## Install from the repository
[![Add the repository to my Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMatze89x%2Fha-car-assistant)

Or manually: App store → ⋮ → Repositories → `https://github.com/Matze89x/ha-car-assistant`. Updates then arrive automatically whenever the version number increases.

## Alternative: local app (testing, or no GitHub)
1. Copy the folder `carassistant` of this repository into the `local_apps` share of Home Assistant (Samba share `local_apps`, or SSH path `/local_apps/carassistant`).
2. Settings → Apps → *App store* (bottom right) → ⋮ → *Check for updates*. If nothing appears, hard-refresh the browser.
3. "Car Assistant" appears in the section *Local apps* at the top → Install → Start. The image is built on your Home Assistant (internet needed once).
4. Enable *Show in sidebar*.

If it does not appear, `config.yaml` may be invalid – check Settings → System → Logs → *Supervisor*.

**Updating:** copy the new `carassistant` folder over the old one (the version number in `config.yaml` is higher). Reload the store; Home Assistant shows an *Update* button. Your data is kept.

## Ways to open it
- **Sidebar panel** (Ingress): always available, no port, no login.
- **Own port** (optional): App → Configuration → *Network*: the host port for `8099` is empty by default - enter any free port of your choice; create an account under *Settings → User* to unlock it (login page, optional passkey). If the port is already used, the app does not start and the app log says so – pick another one.
- **From outside:** reverse proxy with HTTPS to that port (see [DOCS.md](../carassistant/DOCS.md)), or simply use your normal Home Assistant remote access – the sidebar panel works there too.

## Support
Free and made in spare time – [Ko-fi](https://ko-fi.com/matze89x).

## Versioning
`0.FEATURES.BUGFIXES` – `0.2.1` = second feature release, first bug-fix. `0` becomes `1` with the first official release.
