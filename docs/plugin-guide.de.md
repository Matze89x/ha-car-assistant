# Ein Plugin bauen - die Anleitung

[🇬🇧 English](plugin-guide.md) · 🇩🇪 Deutsch

Ein Plugin ist eine **Verbindung nach außen**: zu einem Auto, einem Webdienst, bei dem du dich anmeldest, einem Cloud-Konto, einem Gerät. Diese Seite führt dich von Null zu einem funktionierenden Plugin in einer Quelle. Einzelheiten: [plugins.de.md](plugins.de.md) (das Paket), [api.de.md](api.de.md) (die Plugin-API), [icons.de.md](icons.de.md), [sources.de.md](sources.de.md).

## 1. Der Ordner
In einer Quelle (ein GitHub-Repository, öffentlich oder privat mit Schlüssel) ist ein Plugin ein Ordner:
```
plugins/mein-plugin/
  plugin.json          die Beschreibung (Pflicht)
  service/main.py      freiwillig: ein eigenes Programm, das im Add-on läuft
  package.zip          aus dem Ordner gebaut (nur bei einem Plugin mit Dienst)
plugins/index.json     die Liste: {"packages": [{"id": "mein-plugin", "name": "...", "version": "1", "icon": "wrench", "sha256": "..."}]}
```
Der Ordnername ist die `id` des Plugins. Beginne mit `docs/examples/echo-service/`.

## 2. plugin.json
```
{"id": "mein-plugin", "kind": "plugin", "name": "My plugin", "version": "1", "icon": "wrench",
 "description": "Ein Satz für die Kachel.", "author": "Name",
 "docs": "Ein längerer Text für die Seite Schnittstellen.",
 "l10n": {"de": {"name": "Mein Plugin", "description": "Ein Satz für die Kachel."}},
 "settings": [ ... ], "interfaces": [ ... ], "service": { ... }, "downloads": [ ... ], "connection_file": { ... }, "setup": { ... }}
```
Halte `version` in der `plugin.json` und im Index gleich; eine höhere Zahl bietet ein *Update* an. Wähle das `icon` aus [icons.de.md](icons.de.md).

## 3. Was der Benutzer einstellen kann (settings)
Beschreibe die Optionen als JSON - die App zeichnet sie auf der **Einstellungsseite** des Plugins (Schalter, Auswahl, Schieberegler, Listen, Überschriften, ...). Alle Typen, `show_if`, Prüfung und was ein Dienst bekommt: [plugins.de.md](plugins.de.md#einstellungsseite). Beispiel:
```
"settings": [
  {"type": "section", "label": "Konto"},
  {"key": "user", "type": "text", "label": "Benutzername", "required": true},
  {"key": "pass", "type": "password", "label": "Passwort"},
  {"key": "mode", "type": "radio", "label": "Modus", "options": [{"value": "a", "label": "Automatisch"}, {"value": "b", "label": "Eigene"}], "default": "a"},
  {"key": "url", "type": "url", "label": "Adresse", "show_if": {"key": "mode", "equals": "b"}},
  {"key": "feeds", "type": "multiselect", "label": "Quellen", "options": [{"value": "news", "label": "Nachrichten"}, {"value": "wx", "label": "Wetter"}]}
]
```
Passwörter (Anmeldedaten für Webdienste) bleiben aus Fahrzeugsicherungen heraus und werden nie angezeigt oder protokolliert.

Felder einer Einstellung mit `"advanced": true` stehen in der Einrichtungsanleitung zugeklappt unter *Erweiterte Einstellungen*.

## 4. Mit der App sprechen (Plugin-API)
Das Plugin bekommt ein Token (ein Plugin **ohne** Dienst: auf seiner Einstellungsseite; **mit** Dienst: das Add-on gibt es als `CA_API_TOKEN`) und sendet, was es weiß: `POST /api/v1/vehicles/<id>/data`, `/track`, `/events`, `/signals`, `/refuel`, `/logs`; `control` liefert den Debug-Schalter und den Takt. Welcher Weg für welche Daten: [plugins.de.md](plugins.de.md#welcher-weg-für-welche-daten), alle Felder: [api.de.md](api.de.md). Sende nur Echtes; rate nie.

## 5. Ein eigener Dienst
Braucht das Plugin ein Programm (um sich irgendwo anzumelden, Seiten zu holen, einem Gerät Dateien zu liefern), ergänze `"service": {"entry": "service/main.py", "requirements": [...], "routes": [{"prefix": "/my/", "public": true}], "connects": ["api.example.com"]}`. Es läuft **im Add-on**, erst nachdem ein Administrator es freigegeben hat, mit `CA_PORT`, `CA_API_URL`, `CA_API_TOKEN`, `CA_VEHICLE_ID`, `CA_DATA_DIR` und `settings.json` (typisiert). Alles zu Regeln, Grenzen und Freigabe: [plugins.de.md](plugins.de.md#plugins-mit-dienst). Zip und Prüfsumme baust du mit `python tools/build_plugin_package.py <Quellordner> <id>`.

**Ein ganzes Werkzeug mit eigener Seite** (Editor, Übersicht): Auch eine *Integration* darf einen Dienst tragen – dann ohne Token und Plugin-API – und ihre Seiten als `kind: "frame"`-Seite zeigen: Die App setzt nur ihren Kopf darauf (zurück, Name, Version), die Seite gehört dir, im Design des Autos. Alles dazu (Parameter, Header, Grenzen, Design-Kit, Kartenkacheln): [plugins.de.md](plugins.de.md#eine-seite-des-dienstes-als-eigene-seite-kind-frame).

## 6. Dateien zum Herunterladen
Ein Dienst kann jede Datei auf einer seiner Adressen liefern (Binärdateien, `Content-Disposition` und `Content-Type` gehen durch; höchstens 16 MB je Antwort). Damit die Person einen Knopf in der App bekommt, trage ihn in die `plugin.json` ein:
```
"downloads": [{"label": "Datenpaket", "path": "/my/pack.zip", "note": "für das Fahrzeug-Display"}]
```
Der Pfad muss unter einer Adresse des Dienstes liegen. Die Knöpfe erscheinen auf der Kachel des Plugins unter *Verwaltung* (solange es läuft); Dateien und die Anbindungsdatei gibt nur die Einrichtungsanleitung heraus. Eine **öffentliche** Adresse erreicht jeder (ein Gerät ohne Anmeldung); eine **nicht öffentliche** nur aus Home Assistant oder eine angemeldete Person. **Binärdateien, die keinen Dienst brauchen** (ein Programm für das Auto, ein fertiges Datenpaket), kommen in `files` / `bundles`: siehe [plugins.de.md](plugins.de.md#dateien-eines-pakets-downloads-ohne-dienst). Eine einfache Datei mit Token und Einstellungen ist die `connection_file` (siehe [plugins.de.md](plugins.de.md#anbindungsdatei)).

## 7. Sagen, was du anbietest (Schnittstellen)
Ergänze `docs` und `interfaces`, damit die Seite *Info* deines Plugins jede Schnittstelle dokumentiert, die es sendet, liest oder anbietet: [plugins.de.md](plugins.de.md#die-schnittstellen-seite-eines-pakets). Die Seite zeigt auch, was das Plugin wirklich genutzt hat (Adressen und Feldnamen, nie Werte).

Ein Plugin mit Anbindungsdatei kann eine **Einrichtungsanleitung** (`setup`) mitbringen: drei feste Schritte - Prüfen (Adresse und FIN), Token und Einstellungen, Dateien und Anleitung - auf einer Seite auf seiner Einstellungsseite. Die Anbindungsdatei kennt `{vin}` und `{url}`; ein Dienst findet `external_url` und `vehicle_vin` in seiner `settings.json`. Alles steht in [plugins.de.md](plugins.de.md#einrichtungsanleitung-setup).

## 8. Prüfen, veröffentlichen, aktualisieren
1. `python tools/check_plugin.py plugins/mein-plugin` - nennt Tippfehler, falsche Icons, fehlende Dateien, eine falsche Prüfsumme.
2. Ordner, `package.zip` und `plugins/index.json` zusammen committen.
3. In der App: *Plugins → Hinzufügen → Liste aktualisieren*, dein Plugin antippen, installieren. Mit Dienst: *Verwaltung → Prüfen und freigeben*.
4. Beobachten: *Verwaltung → Debug* (nur dieses Plugin) und *Protokoll*: Log-Zeilen, was das Add-on mit dem Dienst tut, und der Verkehr. Protokolle bleiben 1, 7 oder 30 Tage.
5. Neue Version: `version` in `plugin.json` und Index erhöhen, Zip neu bauen, committen; die Leute drücken *Nach Updates suchen*. Ein Update, das der Administrator drückt, behält die Freigabe vom Installieren.

## 9. Integrationen ohne Code: Seiten, Erinnerungen, Pläne
Eine *Integration* hat kein Programm und keinen Token: sie beschreibt nur, was die App zeichnen soll. Seiten mit typisierten Feldern (auch der Byte-für-Byte-Vergleich für Codierungen), Erinnerungen nach Kilometern oder Tankungen, **Pläne** (ein Wechsel, der mit jeder Tankung weiterrückt), Wert-Kacheln für die Startseite und Widgets stehen alle in der `plugin.json` – siehe [integrations.de.md](integrations.de.md). Ein Plugin desselben Autos kann die Einträge einer Integrationsseite über die [Plugin-API](api.de.md) lesen und schreiben.

**Später weitermachen?** Alles, was ein Paket bieten kann, ist in diesem Ordner beschrieben: [plugins.de.md](plugins.de.md) (Format, Einstellungen, Dateien, Dienste, Kacheln, Schnittstellen), [integrations.de.md](integrations.de.md) (Seiten, Erinnerungen, Pläne), [api.de.md](api.de.md) (was ein Plugin sendet und liest), [sources.de.md](sources.de.md) (Veröffentlichen) und [icons.de.md](icons.de.md). Offizielle Beispiele: das [Quellen-Repository](https://github.com/Matze89x/ha-car-assistant-sources).

## 10. Die Struktur auf einen Blick - und wie man ein Plugin darauf umbaut
Jedes Plugin sieht für die Person gleich aus, egal mit welchem Auto, Cloud-Konto, welcher App oder Home-Assistant-Funktion es spricht. **Du** bestimmst nur, was darin steckt:

| Ort | Was es ist | Wo du es festlegst |
|---|---|---|
| **Kachel** (*Plugins → Verwaltung*) | eine Knopfzeile: *Deinstallieren* (Mülleimer), *Logs*, *Einstellungen*, bis zu drei eigene Knöpfe, der Hauptknopf (beim ersten Mal *Einrichten*, danach *Öffnen*) | `buttons` ([plugins.de.md](plugins.de.md#die-kachel-eines-plugins-und-seine-knöpfe-buttons)) |
| **Einrichten** (erstes Mal) | deine eigenen Schritte: Text, Voraussetzungen, ein Formular (Benutzername / Kennwort), eine Prüfung durch deinen Dienst, das Token (nur wenn du eins willst), Dateien, eine Seite von dir, eine Datei, die dein Dienst erstellt (eine ZIP) | `setup.flow` ([plugins.de.md](plugins.de.md#der-einrichten-ablauf-setupflow)) |
| **Einstellungen** | die Felder, die die Person später ändern kann; dein Dienst darf `value` / `service_writable`-Felder selbst schreiben | `settings`, `settings_page` |
| **Logs** | seine eigene Log-Seite: alle Zeilen oder nur Probleme, ein Text-Download; geschrieben von dir über `POST /logs` oder von der Ausgabe deines Dienstes, solange Debug an ist | nichts festzulegen - sie ist da |
| **Deine Seiten** | jede Seite deines Dienstes, frei gestaltet, darf Daten sammeln oder Informationen lesen | `pages` (`kind: "frame"`), erreichbar über einen `page`-Knopf oder einen `page`-Schritt |

**Ein bestehendes Plugin umbauen - Checkliste** (nichts muss sich ändern, damit ein Plugin weiter funktioniert; so bekommt es die neue Struktur):
1. **Behalte, was funktioniert.** Jeder Schlüssel der `plugin.json`, den du heute nutzt, wird weiter genauso gelesen. Neue Schlüssel sind Ergänzungen: `buttons`, `setup.flow`.
2. **Ersetze die feste Anleitung durch einen Ablauf**, nur wenn du mehr als *Prüfen / Token / Dateien* brauchst: Verschiebe die Texte der Schritte in `flow`-Schritte (`text`, `requirements`, `form` / `check`, `token`, `files`) in der Reihenfolge, die du willst. Eine Anmeldung mit Benutzername und Kennwort ist ein `check`-Schritt mit `"settings": ["user", "password"]` und einer Route in deinem Dienst, die die Anmeldung versucht und `{"ok": true, "message": "Angemeldet als ..."}` oder `{"ok": false, "message": "Kennwort falsch."}` antwortet.
3. **Lege, was die Person lesen muss, in Seiten, nicht in Texte**: Eine Dokumentationsseite ist eine `kind: "frame"`-Seite plus ein `buttons`-Eintrag (`"page": "docs"`); eine Seite, die Daten sammelt, sendet an deinen Dienst.
4. **Mach jede Route, die etwas tut, nicht öffentlich** (`public: false`): `check`, `download`, die `action` eines Knopfs und die Routen der Frame-Seiten müssen unter einem nicht öffentlichen Präfix liegen, sonst verwirft die App sie.
5. **Protokolliere, was zählt**: `POST /api/v1/vehicles/<id>/logs` mit einem `level` (`warn` / `error` für das, was die Person zuerst ansehen soll - die Log-Seite filtert danach). Jedes Plugin hat sein eigenes Protokoll; nichts von dir steht im Protokoll eines anderen und nichts von ihnen in deinem.
6. **Prüfe das Paket**: `python tools/check_plugin.py <Ordner>` nennt jeden Schlüssel, den die App stillschweigend ignorieren würde (ein falsch geschriebener Schlüssel, ein Knopf ohne gültige Seite / Route, ein Schritt, der nicht zu seinem Typ passt). Dann in einem **Demo-Auto** (*Nur mal ansehen*) oder auf einer Entwicklungsinstanz installieren und *Einrichten*, jeden Knopf und die Log-Seite bei 320 px und in Desktop-Breite durchgehen.
7. **Veröffentliche**: `package.zip` bauen (Dienst-Plugins), `version` und `sha256` in `index.json` erhöhen, `python tools/check_source.py <Quelle>`. Ein *Aktualisieren*, das der Administrator drückt, behält die Freigabe; eine geänderte Dienstbeschreibung fragt erneut.

Nichts davon berührt die autospezifischen Teile: Wie du mit dem Auto, der Cloud oder dem Gerät sprichst, bleibt ganz deine Sache.
