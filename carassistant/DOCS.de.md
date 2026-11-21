# Car Assistant

[🇬🇧 English](DOCS.md) · 🇩🇪 Deutsch

**Drive · Log · Go** – das Logbuch und Dashboard deiner Autos, komplett lokal.

## Erste Schritte
1. Öffne **Car Assistant** in der Seitenleiste von Home Assistant. Dafür ist nichts einzurichten.
2. Lege dein erstes Auto an (oder tippe auf **Demo-Auto**, um dich mit erfundenen Daten umzusehen; jederzeit löschbar).
3. Arbeite die Liste *Los geht's* auf Home ab: Kilometerstand, erste Tankung, ein Service-Eintrag, Auto verbinden.

Weitere Autos: *Einstellungen → Fahrzeuge → Fahrzeug hinzufügen*; oben erscheint dann das Menü **Auto wechseln**.

## Was sie kann
- **Je Auto:** Fahrzeugpass mit Ausstattung, Tanken oder Laden, Service, Termine, Aufgaben, Teile, Reifen, Umbauten, Dokumente, Fahrten mit Km-Zählern, das Handbuch, Fotos und Videos. Alles funktioniert für Verbrenner, Hybride und Elektroautos.
- **Erinnerungen:** Wartung, Termine und eigene Erinnerungen; offene Punkte zeigen sich als Punkt auf dem Reiter. Benachrichtigungen kommen aufs Handy über deinen eigenen Home-Assistant-Notify-Dienst, je Benutzer.
- **Plugins und Integrationen:** Ein Plugin verbindet etwas von außen (ein Auto, ein Cloud-Konto, einen Webdienst) über die Plugin-API; eine Integration fügt Seiten hinzu (zum Beispiel Coding-Werte oder eine Kraftstoff-Additiv-Erinnerung). Beide kommen aus *Quellen*, die du selbst hinzufügst; nichts wird von allein geholt.
- **Einheiten und Währung:** eine Wahl für die ganze App unter *Einstellungen → System → Region* (km / Meilen, Liter / Gallonen, mpg, psi, jede Währung). Gespeichert wird in Basiseinheiten, du kannst also hin- und herschalten.
- **Sprachen:** Deutsch und Englisch eingebaut; weitere Sprachen sind einfache Dateien.
- **Benachrichtigungen und Web-Apps je Auto:** *Einstellungen → Auto* schaltet Benachrichtigungen für das Gerät ein, das du benutzt; *Einstellungen → Benutzer* hat je Auto einen Startlink für eine Web-App auf dem Home-Bildschirm.
- **MCP-Zugriff für Claude:** *Einstellungen → System → MCP-Zugriff* (standardmäßig aus) lässt Claude deine Einträge lesen und, wenn du es erlaubst, korrigieren. Einrichtung: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/mcp.de.md
- **Backup:** ein Auto oder das ganze System, jeweils für sich.

## Konfiguration
Öffne die App (*Einstellungen → Apps → Car Assistant*) und den Reiter *Konfiguration*.

| Option | Bedeutung |
|---|---|
| `log_level` | Wie viel die App in ihr Protokoll schreibt. `error` = nur Probleme (Standard). `info` oder `debug` nur, um ein Problem zu finden. |
| `mqtt_sensors` | Jedes Auto als Gerät mit Sensoren in Home Assistant anlegen (MQTT). Lässt sich auch in der App schalten (*Einstellungen → System*); was dort eingestellt ist, gilt. |
| `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password` | Nur für einen eigenen Broker. Leer = der Broker von Home Assistant (zum Beispiel die Mosquitto-App), wird automatisch gefunden. |

Alles andere (Sprache, Einheiten, Benachrichtigungen, die externe Adresse, Spritpreise) stellst du in der App unter *Einstellungen* ein.

Wenn der Browser das Feld *Benutzername* mit einem alten Login füllt, leere es vor dem Speichern: Diese Seite zeichnet Home Assistant, die App kann die Autofüllung nicht abschalten.

## Wer kann Car Assistant erreichen
- **Über Home Assistant** (das Panel in der Seitenleiste): geht immer, nichts einzurichten, keine Anmeldung nötig.
- **Direkt** (ein Browser auf `http://<Adresse von Home Assistant>:<Port>`, ein Reverse-Proxy, ein Tunnel, ein Handy): braucht einen **Port** und einen **Benutzer**.
  - **Port:** standardmäßig leer, das heißt kein Direktzugriff. Trage unter *Netzwerk* im Reiter *Konfiguration* einen beliebigen freien Port ein. Wird er schon von etwas anderem benutzt, startet die App nicht: Wähle einen anderen.
  - **Benutzer:** Lege einen unter *Einstellungen → Benutzer* an (oder im kurzen Einrichtungsschritt nach dem ersten Auto): Name und Passwort, optional ein **Passkey** (Face ID, Fingerabdruck, Sicherheitsschlüssel; füge ihn hinzu, während die App über deine https-Adresse geöffnet ist). Ohne Benutzer zeigt die Direktadresse eine Seite, die das sagt, sonst nichts.
  - Nach 5 falschen Versuchen wird eine Adresse 15 Minuten gesperrt. Ein vergessenes Passwort setzt ein Administrator im Home-Assistant-Panel zurück (*Einstellungen → Benutzer*); Wiederherstellungscodes gehen ebenfalls.
- **Von außerhalb deines Netzwerks:** Das entscheiden dein Router (Portfreigabe) oder dein Reverse-Proxy / Tunnel (Nginx Proxy Manager, Caddy, Cloudflare Tunnel, ...). Immer **HTTPS** benutzen: ohne läuft ein Passwort unverschlüsselt. Richte den Proxy auf `http://<Adresse von Home Assistant>:<Port>`, lass ihn den `Host`-Header durchreichen und gib ihm eine eigene Subdomain (kein Unterpfad), dann trage die Adresse unter *Einstellungen → System → Externe Adresse* ein.
- Die öffentlichen Adressen des Dienstes eines Plugins (für Geräte ohne Anmeldung) fallen nicht darunter: Sie sind absichtlich öffentlich.

## Sensoren in Home Assistant (MQTT)
Standardmäßig aus. Wenn an, wird jedes Auto zu einem Gerät in Home Assistant: Kilometerstand, Reichweite, Termine und - sobald ein Plugin sie liefert - Zündung, Verriegelung, Türen, Fenster, Reifendruck, Batterie, Laden und mehr. Die **GPS-Position** erscheint als Geräte-Tracker auf der Home-Assistant-Karte. Es werden nur Werte angelegt, die es gibt; selten nützliche starten ausgeschaltet, technische sind Diagnose. Schaltest du die Sensoren aus, verschwinden sie wieder aus Home Assistant.

Schalte es im Reiter *Konfiguration* oder unter *Einstellungen → System* ein. Die App fragt den Supervisor nach dem Broker und verbindet sich automatisch; für einen externen Broker trägst du Adresse, Port und Zugangsdaten an derselben Stelle ein.

## Datenschutz: nichts geht von allein ins Internet
- **Karteninfos:** standardmäßig aus. Unter *Einstellungen → System* schaltest du *Karteninfos anzeigen* ein (Leaflet mitgeliefert, OpenStreetMap-Kacheln, Ortsnamen der Fahrten). Car Assistant holt die Kacheln für dich und behält sie eine Woche und fragt bei OpenStreetMap einmal nach Straße und Ort von Start und Ziel jeder Fahrt, damit das Fahrtenbuch Namen statt Koordinaten zeigt (die Antworten werden behalten). OpenStreetMap sieht also die Adresse deines Servers, den Kartenausschnitt und diese Koordinaten - nicht dein Handy oder deine Home-Assistant-Adresse.
- **Spritpreise:** Die Tankstellensuche nutzt OpenStreetMap; für Live-Preise in Deutschland trägst du **deinen eigenen** kostenlosen Schlüssel von https://creativecommons.tankerkoenig.de ein (*Einstellungen → System*). Es gibt keinen eingebauten Schlüssel. Daten: CC BY 4.0, tankerkoenig.de.
- **Quellen:** Eine Quelle wird nur gefragt, wenn du sie hinzufügst, *Aktualisieren* drückst oder etwas installierst.
- **Benachrichtigungen über das Web** (Browser-Push) werden nur auf einer über https geöffneten Seite angeboten.

## Plugins mit Dienst
Ein Plugin oder eine Integration kann ein kleines Programm mitbringen (einen *Dienst*), das in diesem Add-on läuft. **Das ist fremder Code.** Er läuft nur, wenn das Paket aus einer von dir hinzugefügten Quelle kommt, nur nachdem du ihn auf einer Seite freigegeben hast, die alles auflistet, was er tut, als eigenes Programm mit eigenem Benutzer und Grenzen, und nie mit dem Home-Assistant-Token oder der Datenbank. Gib nur Dienste aus Quellen frei, denen du vertraust.

## Backup
- **Ein Auto:** *Einstellungen → Auto → Sichern & verwalten* (alles von diesem Auto; die Wiederherstellung legt ein neues Auto an).
- **Alles:** *Einstellungen → System → Sichern* (alle Autos, Benutzer, Einstellungen). Eine Wiederherstellung macht vorher eine Sicherheitskopie.
- Die App ist außerdem Teil jedes Home-Assistant-Backups (`backup: cold`).

## Weitere Dokumente auf GitHub
Die ausführlichen Beschreibungen liegen im Repository:
- Benutzerhandbuch: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/guide.de.md
- Installation: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/install.de.md
- Quellen und Pakete: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/sources.de.md
- Plugins: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/plugins.de.md
- Integrationen: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/integrations.de.md
- Plugin-API: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/api.de.md
- Backup: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/backup.de.md
- Architektur (wie alles zusammenhängt): https://github.com/Matze89x/ha-car-assistant/blob/main/docs/architecture.de.md
- Beispiele für ein eigenes Plugin oder eine eigene Integration: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/examples/README.de.md
- Screenshots: https://github.com/Matze89x/ha-car-assistant/blob/main/docs/screenshots.de.md
- Änderungsprotokoll: https://github.com/Matze89x/ha-car-assistant/blob/main/carassistant/CHANGELOG.de.md
- Ein Problem melden: https://github.com/Matze89x/ha-car-assistant/issues

## Unterstützen
Kostenlos und in der Freizeit gemacht: https://ko-fi.com/matze89x
