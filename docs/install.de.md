# Installation

[🇬🇧 English](install.md) · 🇩🇪 Deutsch

Voraussetzung: Home Assistant OS oder Supervised (Apps). Eine reine „Home Assistant Container“-Installation kennt keine Apps.

> Home Assistant nennt Add-ons jetzt **Apps**. Car Assistant läuft als eine davon; in dieser Dokumentation bedeuten *Add-on* und *App* in Bezug auf Home Assistant dasselbe (*die App* allein ist Car Assistant selbst).

## Aus dem Repository installieren
[![Repository zu meinem Home Assistant hinzufügen](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2FMatze89x%2Fha-car-assistant)

Oder manuell: App Store → ⋮ → Repositories → `https://github.com/Matze89x/ha-car-assistant`. Updates kommen dann automatisch, sobald die Versionsnummer steigt.

## Alternative: lokale App (zum Testen, oder ohne GitHub)
1. Den Ordner `carassistant` aus diesem Repository in die Freigabe `local_apps` von Home Assistant kopieren (Samba-Freigabe `local_apps`, oder per SSH `/local_apps/carassistant`).
2. Einstellungen → Apps → *App Store* (unten rechts) → ⋮ → *Nach Updates suchen*. Erscheint nichts, den Browser hart neu laden.
3. „Car Assistant“ erscheint oben im Bereich *Lokale Apps* → Installieren → Starten. Das Image wird auf deinem Home Assistant gebaut (einmalig Internet nötig).
4. *In Seitenleiste anzeigen* aktivieren.

Erscheint sie nicht, ist evtl. die `config.yaml` ungültig – prüfe Einstellungen → System → Protokolle → *Supervisor*.

**Updaten:** Den neuen Ordner `carassistant` über den alten kopieren (die Versionsnummer in `config.yaml` ist höher). Store neu laden; Home Assistant zeigt *Aktualisieren*. Deine Daten bleiben erhalten.

## Wege zur Oberfläche
- **Seitenleiste** (Ingress): immer da, kein Port, kein Login.
- **Eigener Port** (optional): App → Konfiguration → *Netzwerk*: der Host-Port für `8099` ist standardmäßig leer - trage einen beliebigen freien Port deiner Wahl ein; lege unter *Einstellungen → Benutzer* ein Konto an, um ihn freizuschalten (Login-Seite, optional Passkey). Ist der Port schon belegt, startet die App nicht und das App-Protokoll sagt es – dann einen anderen wählen.
- **Von außen:** Reverse-Proxy mit HTTPS auf diesen Port (siehe [DOCS.de.md](https://github.com/Matze89x/ha-car-assistant/blob/main/carassistant/DOCS.de.md)) oder einfach den normalen Home-Assistant-Fernzugriff nutzen – das Seitenleisten-Panel funktioniert auch dort.

## Unterstützen
Kostenlos und in der Freizeit gemacht – [Ko-fi](https://ko-fi.com/matze89x).

## Versionierung
`0.FEATURES.BUGFIXES` – `0.2.1` = zweite Feature-Version, erster Bugfix. Aus `0` wird `1` mit dem ersten offiziellen Release.
