# Plugin API

[🇬🇧 English](api.md) · 🇩🇪 Deutsch

So schickt ein Plugin oder eine Integration Fahrzeugdaten an Car Assistant. Car Assistant spricht nie selbst mit einem Auto: **Das Plugin tut es** (im Auto, auf einem Raspberry Pi, in einer Cloud-Brücke, …) und liefert die Werte mit einer HTTP-Anfrage. Nichts wird aus dem Internet geholt und nichts erfunden – eine Seite zeigt nur, was ein Plugin geliefert hat.

## Ein Token = ein Auto
Alles gilt pro Fahrzeug, weil jedes Auto anders angebunden sein kann. Ein Plugin richtest du unter *Auto → Weiteres → Integrationen* ein (siehe [plugins.de.md](plugins.de.md)); ein **Plugin** bekommt dabei sein eigenes Token (wird einmal angezeigt, lässt sich ersetzen und wird durch Entfernen des Plugins ungültig). Ein Token gilt **nur für sein Auto** – jede andere Fahrzeug-ID antwortet mit `403`.

Die API erreichst du über die Adresse deines Direktzugriffs (der Port, den du gewählt hast, oder dein Reverse Proxy, siehe [DOCS.de.md](../carassistant/DOCS.de.md)). Das Token ist die einzige Zugangsangabe: `Authorization: Bearer ca_…`. Von außen immer HTTPS.

## Daten senden
```
POST /api/v1/vehicles/<id>/data
Authorization: Bearer ca_...
Content-Type: application/json

{"odometer_km": 52340, "ignition": false, "doors": {"front_left": false, "trunk": true}, "locked": true}
```
Alle Felder sind optional – sende, was du weißt. Unbekannte Felder werden abgelehnt (`422`). Body: max. 20 kB.

| Feld | Typ | Regel | Angezeigt |
|---|---|---|---|
| `odometer_km` | Zahl | 1 … 2 000 000; nur gespeichert, wenn höher als der bekannte Stand | überall (Plakette „vom Auto“) |
| `vin` | Text | Buchstaben und Ziffern, 5 … 20 (Leerzeichen und Striche werden entfernt, Großbuchstaben). **Wird nur verglichen und nie vom Plugin gespeichert:** Die FIN trägt ein Mensch in den Fahrzeugdaten ein. Stimmt sie, zeigt die Fahrzeugseite *Vom Auto bestätigt*; weicht sie ab, wird die ganze Anfrage abgelehnt (`409 vin_mismatch`, nichts gespeichert); ist noch keine eingetragen, sagt die Antwort `not checked` | Fahrzeugseite |
| `fuel_level_pct` | Zahl | 0 … 100 | Home |
| `range_km` | Zahl | 0 … 3000 | Home |
| `fuel_amount` | Zahl | 0 … 1000: Liter im Tank (kWh in der Batterie eines Elektroautos), wenn das Auto die Menge selbst meldet. Mit der Tankgröße (Fahrzeugdaten) zeigt die App auch die Prozent; mit Prozent und Größe rechnet sie die Menge aus | Home |
| `position` | `{"lat": .., "lon": ..}` | gültige Koordinaten | Home: Standort-Karte |
| `ignition` | Wahrheitswert | `true` = an | Home-Plakette, „Geparkt seit“ |
| `doors` | Objekt `Name → Wahrheitswert/null` | `true` = offen, `false` = zu, `null` = Namen entfernen | Home-Plakette, Sicherheits-Seite |
| `windows` | Objekt `Name → Wahrheitswert/null` | wie `doors` | Home-Plakette, Sicherheits-Seite |
| `locked` | Wahrheitswert | `true` = verriegelt | Sicherheits-Seite |
| `warnings` | Objekt `Code → Text/null` | eine Meldung des Autos; `null` entfernt den Code; Text bis 120 Zeichen, höchstens 16 Codes | Home: Widget „Fahrzeugmeldungen“ |
| `speed_kmh` | Zahl | 0 … 450 | Home: Fahrzeugdaten |
| `outside_temp_c` | Zahl | -60 … 70 | Home: Fahrzeugdaten |
| `battery_12v_v` | Zahl | 0 … 30 (Volt) | Home: Fahrzeugdaten |
| `battery_pct` | Zahl | 0 … 100 (Hochvoltbatterie eines Elektro-/Hybridautos) | Home: Fahrzeugdaten |
| `charging` | Wahrheitswert | `true` = lädt | Home: Fahrzeugdaten |
| `charge_power_kw` | Zahl | 0 … 1000 | Home: Fahrzeugdaten (beim Laden) |
| `tyre_pressure_bar` | Objekt `fl/fr/rl/rr → Zahl/null` | 0 … 8 bar; `null` entfernt ein Rad | Home: Fahrzeugdaten |
| `coolant_temp_c`, `oil_temp_c` | Zahl | -40 … 200 (°C) | Home: Fahrzeugdaten |
| `cabin_temp_c` / `target_temp_c` | Zahl | -40 … 80 / 5 … 40 (°C) | Home: Fahrzeugdaten |
| `climate_on` | Wahrheitswert | `true` = Klimaanlage läuft | Home: Fahrzeugdaten |
| `heading_deg` | Zahl | 0 … 360 | (wird gespeichert, für Plugins und Fahrten) |
| `consumption_l_100km` | Zahl | 0 … 100 (l oder kWh je 100 km, vom Auto) | Home: Fahrzeugdaten |
| `service_due_days` / `service_due_km` | Zahl | Tage / km bis zum Service des Autos; negativ = überfällig | Home: Fahrzeugdaten |
| `plugged` | Wahrheitswert | `true` = Ladekabel steckt | Home: Fahrzeugdaten |
| `charge_limit_pct` / `charge_minutes_left` | Zahl | 0 … 100 / 0 … 5000 | Home: Fahrzeugdaten |
| `parking_brake` | Wahrheitswert | `true` = angezogen | Home: Fahrzeugdaten (wenn angezogen) |
| `lights` | Objekt `Name → Wahrheitswert/null` | `true` = an; Namen `low_beam`, `high_beam`, `hazard`, `parking` (andere wie geschrieben) | Home: Fahrzeugdaten |
| `adblue_level_pct` / `adblue_range_km` | Zahl | 0 … 100 / 0 … 50000 (Harnstofflösung eines Diesels) | Home: Fahrzeugdaten |
| `oil_level_pct` / `oil_warning` | Zahl / Boolean | 0 … 100 / `true` = das Auto fordert auf, das Öl zu prüfen | Home: Fahrzeugdaten |
| `speed_limit_kmh` | Zahl | 0 … 250, das Limit, das das Auto gerade liest | Home: Fahrzeugdaten |

### Türen und Fenster
- **Namen:** Kleinbuchstaben, Ziffern und `_`, bis 32 Zeichen, mit einem Buchstaben beginnend; höchstens 16 je Objekt. Empfohlene Namen bekommen eine übersetzte Beschriftung: Türen `front_left`, `front_right`, `rear_left`, `rear_right`, `trunk`, `hood`; Fenster `front_left`, `front_right`, `rear_left`, `rear_right`, `sunroof`. Jeder andere Name wird so angezeigt, wie er geschrieben ist.
- **Links/rechts** gilt aus Sicht des Fahrersitzes nach vorn, unabhängig von der Lenkradseite.
- **Nur die gesendeten Namen ändern sich.** Sende eine einzelne Tür bei einer Änderung oder den ganzen Satz – beides geht. `null` entfernt einen Namen.
- Jeder Wert merkt sich, **wann das Auto ihn gemeldet hat**; die Seiten zeigen „letztes Signal vor 5 Min.“. Sende `measured_at` (eine ISO-Zeit wie `2026-11-20T08:15:00Z` oder Sekunden seit 1970) mit, wenn du weißt, wann das Auto wirklich gemeldet hat – diese Zeit bleibt erhalten, nie eine Zeit in der Zukunft, und ein Wert bekommt nie eine ältere Zeit als zuvor. Ohne sie zählt die Ankunft, **aber ein Wert, der genau dem gespeicherten entspricht, ist keine Neuigkeit**: erneutes Senden der gemerkten Werte (zum Beispiel nach einem Neustart von Car Assistant oder des Plugins) lässt das Auto nicht so aussehen, als hätte es gerade gemeldet. Werte aus gebundenen Home-Assistant-Entitäten tragen die Zeit, die Home Assistant angibt (`last_reported` / `last_updated`). Werte laufen nicht ab: Meldet das Auto im Stand nichts, sende nichts – der letzte Zustand bleibt mit seinem Alter stehen.

## Größere Lieferungen
- **gzip:** jeder `POST` darf `Content-Encoding: gzip` senden. Die Grenzen zählen die **entpackte** Größe (eine kleine Datei kann nicht aufquellen); eine kaputte Datei antwortet `400 invalid_gzip`.
- **Spur (Fahrten)** – `POST /api/v1/vehicles/<id>/track`, bis zu 500 Punkte je Anfrage, je Auto bleiben die neuesten 50 000:
  ```
  {"points": [{"ts": "2026-11-15T08:00:00Z", "lat": 52.5, "lon": 13.4, "speed_kmh": 30}]}
  ```
  `ts` ist optional (Standard: jetzt); die Uhr des Autos kann ungesetzt sein, sende die Zeit, die du kennst. Der neueste Punkt wird auch zur aktuellen Position und Geschwindigkeit des Autos. Zurücklesen mit `GET …/track?since=<ISO-Zeit>&limit=200`. **Fahrten:** eine Folge von Punkten ohne Lücke über zehn Minuten wird zur Fahrt im Fahrtenbuch (Datum, Zeiten, Start-/Zielort, Strecke, Route), sobald zehn Minuten nichts Neues kam; Folgen unter 0,3 km oder 3 Punkten fallen weg. Das Plugin muss dafür nichts tun.
- **Rohsignale** – `POST /api/v1/vehicles/<id>/signals` mit `{"signals": {"kombi.odo_km": 52340, "pc.override": true, "alter.name": null}}`. Für Werte ohne eigenes Feld oben (Flags, Diagnose, alles Autospezifische). Namen: Kleinbuchstaben, Ziffern, `_` und `.`, bis 64 Zeichen; Werte werden als Text gespeichert (bis 2000 Zeichen); `null` entfernt einen; höchstens 300 je Auto. Die App **speichert und zeigt** sie nur (Seite *Debug & Log*) und deutet sie nicht. Zurücklesen mit `GET …/signals`.
- **Ereignisse** – `POST /api/v1/vehicles/<id>/events` mit `{"events": [{"type": "speed_sign", "ts": "2026-11-15T08:00:00Z", "text": "50", "value": 50, "lat": 52.5, "lon": 13.4}]}`: alles mit Zeit und vielleicht einem Ort (gelesene Verkehrszeichen, überfahrene Ortsgrenzen, Warnungen). `type` besteht aus Kleinbuchstaben, Ziffern, `_` und `.` (bis 40); `text` bis 200 Zeichen, `value` eine Zahl, `lat`/`lon` nur zusammen; bis 200 je Anfrage, je Auto bleiben die neuesten 2000. Zurücklesen mit `GET …/events?type=speed_sign&since=<ISO-Zeit>&limit=200`.
- **Tankung** – `POST /api/v1/vehicles/<id>/refuel` mit `{"date": "2026-11-15", "odometer_km": 52340, "amount": 41.5, "price_total": 72.3, "full_tank": true}` (alles optional; `amount` in Litern oder kWh). Nutze es, wenn das Auto merkt, dass der Tank gesprungen ist. Es wird ein Eintrag im Tankbuch, markiert mit `api:<Plugin-Name>`; gibt es für diesen Tag und Kilometerstand (±5 km) schon einen Eintrag, wird nichts angelegt. Erfinde nie eine Menge - lass sie weg, wenn du sie nicht kennst; ein Mensch ergänzt den Eintrag.
- **Einträge einer Integrationsseite** – `POST /api/v1/vehicles/<id>/modules/<Integration>/<Seite>` (die Integration muss installiert sein und laufen) mit `{"rows": [{"values": {...}}, {"id": 5, "values": {...}}], "delete": [7]}`: ein Eintrag ohne `id` wird angelegt, einer mit `id` geändert (Felder mit *once* behalten ihren ersten Wert), `delete` entfernt Einträge. Die Werte werden genau wie im Formular geprüft; ein falscher Wert lehnt die ganze Anfrage ab (`422`). Höchstens 500 Einträge je Anfrage. So liefert ein Plugin zum Beispiel die Steuergeräte der Integration *Coding*.


## Zum Fahrzeug hin: ein Schalter (erster Schritt)
Alles oben fließt **vom** Plugin **zu** Car Assistant. Nur ein kleiner Satz Schalter fließt in die andere Richtung: Sie werden im Dashboard gesetzt, das Plugin **liest** sie nur. Der erste ist **Debug**:
```
GET /api/v1/vehicles/<id>/control   →   {"ok": true, "control": {"debug": false, "interval_s": 120}}
```
Jedes `POST …/data` antwortet mit demselben `control`-Objekt; ein Plugin, das regelmäßig meldet, muss also nicht extra abfragen. Der Schalter wird von einer Person im Dashboard gesetzt (*Auto → Weiteres → Integrationen & Plugins → Debug & Protokoll*). Dieselbe Seite setzt `interval_s` (30, 60, 120, 180 oder 300; Standard 120): wie oft die Person das Plugin gern melden hätte. Es ist eine Bitte - ein Plugin darf während der Fahrt schneller und beim Parken langsamer melden.

Solange **Debug an** ist, soll das Plugin seine Log-Zeilen senden:
```
POST /api/v1/vehicles/<id>/logs
{"lines": [{"level": "debug", "message": "CAN-Frame 0x3C0 dekodiert"}, "reine Textzeilen gehen auch"]}
```
`level` ist `debug`, `info`, `warn` oder `error` (Standard `info`), `ts` ist optional (ISO-Zeit), `message` bis 500 Zeichen, bis zu 50 Zeilen pro Aufruf. **Ist Debug aus, lautet die Antwort `409 debug_off` und nichts wird gespeichert** – ein Plugin darf dann keine Logs senden. Das Dashboard behält die neuesten Zeilen **je Plugin** (Standard 1000; *Einstellungen → System → Plugin-Protokolle* stellt es ein, die ältesten gehen zuerst), zeigt sie auf der Seite *Debug & Protokoll* (Filter je Plugin) und löscht sie, wenn das Plugin entfernt wird.

## Zurücklesen
```
GET /api/v1/vehicles/<id>/data   →   {"ok": true, "data": {...}, "updated": {"doors": "2026-11-13T18:00:00+00:00", ...}}
```
Dieselbe Form wie der POST-Body plus Ankunftszeit jedes Werts – zum Testen eines Plugins.

## Weitere Endpunkte
- `GET /api/v1` – prüft das Token; liefert `version`, `connector` und die erlaubten `fields`.
- `GET /api/v1/vehicles` – das Fahrzeug, das dieses Token nutzen darf.

## Antworten und Fehler
Erfolg: `{"ok": true, "result": {"odometer_km": "stored", …}}`. Fehler haben die Form `{"error": "<code>", "message": "…"}`: `401` Token fehlt/ungültig, `403` Token gilt nicht für dieses Fahrzeug, `404` Fahrzeug unbekannt, `400` Body ist kein JSON, `413` Body zu groß, `422` ungültiger Wert (die Meldung nennt das Feld).

## Gute Praxis für Plugins
- Bei Änderung senden, nicht öfter als alle paar Sekunden. Unveränderte Werte nicht endlos wiederholen.
- Nur senden, was das Auto wirklich meldet. Nie geratene oder erfundene Werte.
- Die Signale deines Autos auf die Standardnamen oben abbilden; fahrzeugspezifische Details bleiben im Plugin.
- Ein Plugin pro Auto; bei einem bekannt gewordenen Token *Neues Token* nutzen.

## Beispiel
[`docs/examples/push_data.py`](examples/push_data.py) – nur Python-Standardbibliothek. Dasselbe geht mit `curl`, Node, einem Home-Assistant-`rest_command` oder einem Mikrocontroller.

## Stabilität und Kompatibilität (ein Versprechen an alle, die Plugins schreiben)
Menschen schreiben eigene Plugins und Integrationen, deshalb gilt: **was heute funktioniert, funktioniert weiter**. Die Regeln:

- **`/api/v1` ist eingefroren.** Innerhalb von `v1` ändern sich bestehende Felder, ihre Bedeutung und die Antworten bestehender Endpunkte nicht so, dass ein Plugin kaputtgeht. Es kommen nur **Ergänzungen** dazu: neue optionale Felder in Anfragen, neue Schlüssel in Antworten, neue Endpunkte, neue erlaubte Werte. Ein Plugin muss **Schlüssel in Antworten, die es nicht kennt, ignorieren**.
- **Erst nachsehen, dann senden.** `GET /api/v1` liefert `version`, `api` und `fields` (was dieses Car Assistant annimmt). Ein älteres Car Assistant beantwortet ein unbekanntes Feld mit `422 unknown_field`; ein Plugin, das ein neueres Feld nutzen will, prüft also zuerst, ob es in `fields` steht (Beispiel: `measured_at`).
- **Nichts wird still geändert oder entfernt.** Eine Funktion, die sich ändern, ersetzt werden oder wegfallen soll, wird zuerst als **veraltet angekündigt**: im Changelog, in diesen Dokumenten (ein Hinweis *Veraltet* mit dem Datum der Entfernung und dem, was man stattdessen nutzt) und – wo es um eine Anfrage geht – mit den Antwort-Headern `Deprecation: true` und `Sunset: <Datum>`. Der Ersatz gibt es **zum Zeitpunkt** der Ankündigung.
- **Frist.** Eine veraltete Funktion funktioniert nach der Ankündigung **für eine genannte Zeit** unverändert weiter und wird erst danach entfernt. **Feste Fristen legen wir mit dem offiziellen Release 1.0 fest** (solange Car Assistant in Beta ist, 0.x, kündigen wir jede solche Änderung im Changelog an und lassen den alten Weg so lange wie vernünftig möglich weiterlaufen, versprechen aber noch keine feste Zeit). Einzige Ausnahme sind Sicherheitskorrekturen (kürzer, mit Nennung des Grundes).
- **Brechende Änderungen** kommen nur in einer **neuen API-Version** (`/api/v2`); wie lange `v1` danach verfügbar bleibt, wird ebenfalls mit 1.0 festgelegt.
- **Die Paketdatei (`plugin.json`)** folgt denselben Regeln: neue Schlüssel sind optional, alte funktionieren weiter; Schlüssel, die ein älteres Car Assistant nicht kennt, werden ignoriert, ein Paket kann also mehrere Versionen bedienen.
- **Sicherungen:** jedes ältere Sicherungsformat bleibt wiederherstellbar ([Sicherung](backup.de.md)).
- **Beta (0.x):** wir halten uns an die Grundsätze schon jetzt (nichts still, nur Ergänzungen, erst ankündigen), damit Plugins, die heute entstehen, bei 1.0 nicht neu geschrieben werden müssen. Die festen Fristen folgen mit 1.0.

**Aktuell veraltet:** nichts.

*Für die Maintainer:* jede Änderung an der API oder der Paketdatei wird vor dem Zusammenführen gegen diese Liste geprüft (siehe `CLAUDE.md`).

- `GET /api/v1/vehicles/<id>/modules/<integration>/<page>` – die Einträge einer Seite einer installierten, laufenden [Integration](integrations.de.md) dieses Autos (zum Beispiel die Sender des Webradios), in ihrer Reihenfolge. `secret`-Felder (Zugangscodes) sind nie darin enthalten.
