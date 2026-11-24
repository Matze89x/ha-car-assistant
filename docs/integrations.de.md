# Integrationen

[🇬🇧 English](integrations.md) · 🇩🇪 Deutsch

Eine **Integration** ist ein Zusatz, der *dem System hinzugefügt wird*: Seiten, Erinnerungen, Kacheln und Einstellungen für ein Auto, beschrieben in einer `plugin.json`. Sie wird auf der Seite *Integrationen* eingeschaltet, eingerichtet und wieder entfernt.

**Eine Integration hat keine API und kein Token.** Sie spricht weder mit einem Auto noch mit der Außenwelt und ruft die [Plugin-API](api.de.md) nie auf. Alles, was etwas von außen anbindet (ein Auto, die Cloud eines Herstellers, einen Webdienst, ein Gerät), ist ein **[Plugin](plugins.de.md)**; nur ein Plugin schickt Werte über die Plugin-API. Eine Integration darf später ein Plugin um Informationen bitten (das Plugin bietet die Schnittstelle), nie umgekehrt.

Heute eingebaut: Home Assistant (Entitäten-Bindungen), MQTT-Discovery, Benachrichtigungen, die **Karte** (siehe unten).

**Selber bauen:** Jeder kann eine Integration schreiben - sie ist eine Beschreibung, es ist also kein Code nötig (siehe unten). Nur wenn eine Integration eine eigene Seite als Werkzeug im Add-on braucht (`kind: "frame"`), darf sie einen [Dienst](plugins.de.md#plugins-mit-dienst) tragen. Teile sie mit der Community auf GitHub ([Quellen](sources.de.md)).

## Seiten (eine Integration ohne Code)

Eine Integration kann in ihrer `plugin.json` **Seiten** beschreiben. Car Assistant zeichnet sie, speichert die Einträge je Auto, und die Einträge gehören zur Fahrzeugsicherung. Aus dem Paket wird nichts ausgeführt – es ist nur eine Beschreibung, deshalb kann jeder eine schreiben.

```json
{
  "id": "my-stations", "kind": "integration", "name": "Stations", "version": "1",
  "icon": "play-circle-outline", "nav": true,
  "l10n": { "de": { "name": "Sender" } },
  "pages": [{
    "id": "list", "title": "Stations", "item": "Station", "sortable": true, "empty": "Nothing here yet.",
    "l10n": { "de": { "title": "Sender", "empty": "Noch nichts hier." } },
    "fields": [
      { "key": "name", "label": "Name", "type": "text", "required": true, "role": "title" },
      { "key": "url",  "label": "Stream", "type": "url", "required": true },
      { "key": "on",   "label": "On", "type": "bool" }
    ]
  }]
}
```

- **`icon`**: ein Name aus dem Symbolsatz der App (unbekannte Namen werden das Puzzleteil). **`nav`**: die Seite in der Navigation anbieten (sie steht in *Weiteres* jedes Autos, bei dem die Integration läuft).
- **Seite**: `id`, `title`, `item`, `empty` (Text der leeren Liste), `sortable` (hoch / runter), `order` (`{"by": "date", "dir": "desc"}`: die Liste wird nach diesem Feld sortiert, mit `desc` das Neueste zuerst; dann gibt es kein manuelles Hoch / Runter), `fields` (bis 20), bis zu 6 Seiten (mehrere Seiten bekommen eine Reiterleiste).
- **Feld**: `key`, `label`, `help`, `required`, `role` (`title` oder `subtitle`: der Kopf eines Eintrags) und ein `type`: `text`, `textarea`, `number`, `bool`, `select` (mit `options`), `url` (http/https), `hex` (Paare aus 0-9 A-F), `date` (Datumsauswahl, gespeichert als `JJJJ-MM-TT`, angezeigt im Datumsformat des Servers) und `secret` (siehe unten).
- **`once`**: Schreibt ein Plugin den Eintrag, behält das Feld seinen ersten Wert (zum Beispiel ein Originalwert); ein Mensch kann es jederzeit ändern. **`compare`** (an einem `hex`-Feld): wird Byte für Byte gegen ein anderes Hex-Feld gezeigt, geänderte Bytes sind markiert.
- **`l10n`**: Texte je Sprache (`name`, `description`, Seiten-`title` / `item` / `empty`, Feld-`label` / `help`); fehlt eine Übersetzung, steht der Originaltext da.
- Eine Integration hat einen **Ein/Aus-Schalter** auf ihrer Karte (und in der Liste unter *Navigation verwalten*): ausgeschaltet sind ihre Seite und ihr Eintrag unter *Weiteres* weg und die Karte bietet kein *Öffnen* an; die Einträge bleiben und sind beim Einschalten wieder da. Ob sie in der Leiste oder unter *Weiteres* steht, stellst du unter *Navigation verwalten* ein.
- Ein Plugin desselben Autos liest die Einträge mit `GET /api/v1/vehicles/<id>/modules/<integration>/<page>` ([Plugin-API](api.de.md)).

Offizielle Beispiele liegen im [Quellen-Repository](https://github.com/Matze89x/ha-car-assistant-sources): *Coding* (Steuergeräte, Original neben aktueller Codierung) und *Webradio* (Sender).


### Zugangscodes (`secret`)
Ein `secret`-Feld hält einen Code, der nicht herumliegen soll: einen Anmelde- oder Entsperrcode, zum Beispiel für ein Steuergerät. Er ist im Eintrag **verborgen** (`••••••`), bis jemand *Anzeigen* drückt (die Seite lädt dann mit sichtbarem Code neu und wird nie zwischengespeichert); im Formular ist das Feld leer und **ein leeres Feld behält den gespeicherten Code** (ein Häkchen entfernt ihn). Ein Code steht **nie** im Suchtext, wird **nie** an ein Plugin gegeben (`GET` lässt das Feld weg, `POST` ignoriert es) und **fehlt in der Fahrzeugsicherung** – wie das Passwort eines Plugins wird er nach einer Wiederherstellung neu eingegeben. *Fahrzeugdaten → Sicherung mit Zugangscodes* (nur sichtbar, wenn das Auto Codes gespeichert hat) erzeugt eine zweite Datei, die sie im Klartext enthält. Die System-Sicherung enthält alles, auch die Codes; die Seite sagt es. Ein `secret`-Feld taugt nicht für `order`.

### Seiten im Detail
- Eine **zweite Liste** braucht nichts Besonderes: eine weitere Seite angeben (bis zu 6, mit Reiterleiste). Ein Verlauf ist zum Beispiel eine Seite mit einem `date`-Feld, `order` danach und `search: true`.
- Eine Seite mit **zwei `title`-Feldern** zeigt das erste als kurzes Zeichen davor (eine Adresse, eine Nummer) und das zweite als Namen; `subtitle`-Felder bilden die zweite Zeile.
- Eine Seite mit einem **`compare`**-Feld bekommt je Eintrag eine aufklappbare Zeile: das Original als EINE Zeile, darunter die aktuellen Bytes (nur ein geändertes zeigt seinen alten Wert), und für ein angetipptes Byte - untereinander - seine Original- und aktuellen Bits, die acht **Bits mit Häkchen und je einer Notiz** und **Gruppen** von Bits, die zusammengehören (ein Name und ein Wert als Zahl). Notizen und Gruppen bleiben beim Eintrag, der Zahl geänderter Bytes, **Neu = Original**, einer Suche und **Nur geänderte**. `search: true` fügt jeder Seite die Suche hinzu.
- Felder mit dem Namen `notes` (ein `textarea`) und das verglichene `hex`-Feld werden direkt in der Zeile bearbeitet; alle anderen Felder liegen hinter *Daten bearbeiten*.

## Erinnerungen und Widgets

Eine Integration kann **Erinnerungen** beschreiben: „wieder nach N Kilometern“ oder „nach N Tankungen“. Die Zahlen kommen aus den eigenen Einstellungen der Integration, jeder entscheidet also selbst (1000, 2000, 3000 km ...). Es passiert nichts, bis die Integration installiert ist und läuft.

```json
"settings": [
  { "key": "mode", "label": "Remind me", "type": "select", "default": "km",
    "options": [{ "value": "km", "label": "after kilometres" }, { "value": "refuels", "label": "after refuels" }] },
  { "key": "every_km", "label": "Every ... km", "type": "number", "default": "1000" },
  { "key": "every_refuels", "label": "After ... refuels", "type": "number", "default": "2" }
],
"reminders": [{
  "id": "additive", "title": "Add fuel additive", "text_due": "Add the additive at the next refuel.", "icon": "oil",
  "mode_setting": "mode", "km_setting": "every_km", "refuels_setting": "every_refuels",
  "l10n": { "de": { "title": "Additiv nachfüllen" } }
}]
```

- Eine Einstellung darf einen **`default`** haben (was sie ist, bis der Nutzer sie ändert) und `l10n`-Texte (`label`, `help`).
- **`mode_setting`** nennt die Einstellung, die `km` oder `refuels` enthält; ohne sie nimmt die Regel die vorhandene Kilometer- oder Tank-Einstellung.
- Die App zählt Kilometer aus dem Kilometerstand und Tankungen aus den Tank-Einträgen; **Erledigt** beginnt die Zählung neu.
- Eine laufende Integration mit Erinnerung bekommt eine **Karte auf der Seite Tanken** und ein **Widget auf dem Dashboard** (verschiebbar und abschaltbar wie jedes Widget).
- Offizielles Beispiel: *Kraftstoff-Additiv* im [Quellen-Repository](https://github.com/Matze89x/ha-car-assistant-sources).

### Pläne (eine Erinnerung mit einem Wechsel)
Eine Erinnerung kann einen **`plan`** tragen: einen kurzen Wechsel, der mit **jeder Tankung** weiterrückt, die die App sieht (zum Beispiel *sauber – Additiv 1 – sauber – Additiv 2*). Die App merkt sich die Position und einen Verlauf; die Seite zeigt die nächste Tankung, den Wechsel, **Plan korrigieren** und den Verlauf mit *eingefüllt / nicht eingefüllt*.

```json
"reminders": [{
  "id": "additive", "title": "Additiv", "text_due": "Beim nächsten Tanken Additiv zugeben.", "icon": "oil",
  "active_setting": "active", "range_setting": "range",
  "plan": [
    { "label": "Sauber" },
    { "setting": "additive_1", "amount_setting": "amount_1", "label": "Additiv 1" },
    { "label": "Sauber" },
    { "setting": "additive_2", "amount_setting": "amount_2", "label": "Additiv 2" }
  ]
}],
"pages": [{ "id": "plan", "kind": "plan", "reminder": "additive", "title": "Additiv-Plan" }]
```
- Ein Schritt ist ein fester **`label`** oder eine **`setting`** (der Name, den der Benutzer eingetragen hat) mit optionaler **`amount_setting`**; ein Schritt mit `setting` ist eine „Gabe", die fällig sein kann, ein Schritt nur mit Label ist eine saubere Tankung. 2 bis 8 Schritte; `l10n` übersetzt die Labels.
- **`active_setting`** (ein Schalter) schaltet die Erinnerung ein und aus; **`range_setting`** (Kilometer Reichweite) hält sie zurück, bis die Reichweite des Autos darunter fällt.
- Die Seite der Art **`plan`** braucht keine Felder; sie verweist mit `reminder` auf die Erinnerung.

**Regel:** Eine Integration darf einen `service` nur tragen, wenn sie ihn für eine eigene Seite in der App braucht (ein Werkzeug im Add-on, `kind: "frame"` in [Plugins](plugins.de.md)), nie um ein Gerät oder Auto anzubinden – das bleibt ein Plugin. Sie bekommt kein Token und keine Plugin-API.

## Karte

Die *Karte* ist eine eingebaute Seite jedes Autos (unter *Weiteres -> Integrationen* einzuschalten; bei einem neuen Auto ist sie aus). Sie ist eine Karte über die ganze Fläche im Inhaltsbereich (auf dem Handy bis zum Bildschirmrand) mit dem Zurück-Knopf oben links, den Knöpfen *Mein Standort*, *Auto* und *Helle / dunkle Karte* oben rechts und der Suche darunter (mit genug Platz alles in einer Zeile).

- **Standardmäßig wird nichts geladen:** Die Karte braucht *Einstellungen -> System -> Online -> Karte*, dann zeigt sie OpenStreetMap über diese App (dieselben Kacheln wie das Standort-Widget).
- **Das Auto** steht an seiner letzten Position und bewegt sich, solange die Seite offen ist. **Dein eigener Standort** wird nur gezeichnet, wenn du den Knopf drückst und es im Browser erlaubst (es braucht https); er bleibt in deinem Browser und wird nie an den Server gesendet.
- **Suche:** Ort oder Adresse eintippen und Suchen drücken (nie schon beim Tippen: der öffentliche Dienst erlaubt das nicht). Die Wörter gehen zusammen mit dem Kartenausschnitt an den Nominatim-Dienst unter *System -> Karten-Info* (standardmäßig der öffentliche von OpenStreetMap). Findet er nichts, kann dieselbe Suche beim gewählten Navigationsdienst gemacht werden. Langes Drücken auf die Karte setzt einen Punkt.
- **Navigieren:** Ein gewählter Ort oder das Auto öffnet ein Blatt mit der Liste *Navigieren mit*. Zuerst stehen **Plugins des Autos, die `navigate` anbieten** (siehe [Fähigkeiten](plugins.de.md#fähigkeiten-capabilities-was-ein-plugin-für-die-app-tun-kann)); dann die Navigationsdienste - Google Maps, Apple Karten, Waze, Bing Maps, OpenStreetMap, Mapy.com, HERE WeGo, Yandex Maps / Navigator, Magic Earth, Sygic und ein allgemeiner Android-Geo-Link. Ein Dienst ist nur ein **Link** mit dem Ziel darin: Das Handy öffnet seine App (oder die Webseite); der Server schickt nichts dorthin. *Einstellungen -> System -> Navigation* legt den Standard für die ganze App fest; *Automatisch* heißt: das Plugin des Autos, wenn es eins gibt, sonst Google Maps.
