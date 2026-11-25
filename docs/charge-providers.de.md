# Ladepunkt-Anbieter

🇬🇧 [English](charge-providers.md) · 🇩🇪 Deutsch

Elektroautos finden Ladepunkte rund ums Auto (oder um dich) auf der Seite **Laden** des Fahrzeugs: mit Steckern und Leistung, sortiert nach Entfernung oder Leistung, gefiltert nach *mindestens 22 / 50 / 150 kW* und nach Stecker (*CCS, Typ 2, CHAdeMO, NACS*). Nichts wird abgefragt, bevor du auf Suchen drückst, und nichts geht woandershin als an die Quelle, die du gewählt hast.

**Was sie nicht sagen kann: ob ein Ladepunkt gerade frei ist.** Keine offene Quelle liefert das verlässlich (Open Charge Map hat einen von Nutzern gepflegten Status, OpenStreetMap keinen; die Live-Daten, die die Betreiber in der EU veröffentlichen müssen, gehen an nationale Zugangspunkte, in einem Format, das von Land zu Land verschieden ist). Die Seite sagt das und zeigt nichts, was sie nicht weiß.

## Quellen

| Quelle | Schlüssel | Daten | Lizenz |
|---|---|---|---|
| **OpenStreetMap** (eingebaut, die Voreinstellung) | keiner | Position, Name, Betreiber, Stecker und Leistung, soweit die Karte sie kennt (`amenity=charging_station`, `socket:*`), Gebühr, Öffnungszeiten, Zugang | ODbL - *© OpenStreetMap-Mitwirkende* steht unter der Liste. Abgefragt über die öffentliche Overpass-Schnittstelle, eine Anfrage je Gebiet alle fünf Minuten, mit erkennbarer Kennung |
| **Open Charge Map** (als Datei mitgeliefert) | ein kostenloser Schlüssel **von dir** (openchargemap.org -> Profil -> *my apps*) | weltweites Register: Stecker, Leistung, Betreiber, Anzahl, Nutzungskosten, Status | Die Daten haben **gemischte Lizenzen**. Car Assistant fragt nur Daten mit offener Lizenz ab (`opendata=true`) und nennt den **Datenlieferanten jedes Ladepunkts** darunter. Beiträge von Personen stehen unter CC BY 4.0 |

Es gibt keinen eingebauten Schlüssel: Du trägst deinen unter dem Zahnrad auf der Seite Laden ein. Ohne ihn wird bei Open Charge Map nichts abgefragt.

## Eine eigene Quelle (eine JSON-Datei)

Wie die Spritpreis-Anbieter ([fuel-providers.de.md](fuel-providers.de.md)) ist eine Quelle **eine JSON-Datei** - Daten, nie Code - in `<Datenordner>/chargeproviders/`. Die mitgelieferte `chargeproviders/ocm.json` ist das Vorbild; das Beispiel steht in der [englischen Fassung](charge-providers.md). Die Felder:

- `id` (`a-z`, `0-9`, `-`, `_`; nicht `osm`), `name`, `countries` (ISO-Codes: dort wird die Quelle zuerst angeboten), `license` und `attribution` (**stehen bei den Ergebnissen - halte ein, was der Datenhalter verlangt**).
- `url` (nur https), `method` (`GET` oder `POST`), `params`, `headers`: Werte dürfen `{lat}`, `{lon}`, `{radius_km}`, `{radius_m}` und `{key}` enthalten.
- `key`: `{"param": "apikey", "url": "..."}` oder `{"header": "X-Key", "url": "..."}`. Die Person trägt einen eigenen Schlüssel ein; ohne ihn wird nichts abgefragt und die Seite sagt es. Der Schlüssel geht in einem Header oder Parameter hinaus, liegt nur auf dem Server und wird nie protokolliert.
- `items`: wo die Liste in der Antwort steht (Punktpfad, leer = die Antwort selbst). `fields`: Punktpfade (`position.lat`) oder Vorlagen mit Feldern in Klammern (`{street} {number}`); nur `lat` und `lon` sind Pflicht. `provider` nennt den Datenlieferanten eines Ladepunkts (steht darunter), `operational` ist ein Wahr-/Falsch-Feld.
- `connections`: `path` ist die Liste der Stecker eines Ladepunkts, `type` der Name des Steckers (die Wörter werden auf *CCS, Typ 2, CHAdeMO, NACS, Typ 1, Haushalt, sonstige* abgebildet), `kw` die Leistung und `count` wie viele es davon gibt.
- `max_radius_km` (1 bis 100). Die Antwort wird fünf Minuten je Gebiet behalten.

Eine Datei, die nicht benutzt werden kann (nicht https, keine Koordinaten, vergebene id), wird mit einem Hinweis im Protokoll übergangen. **Bitte halte die Bedingungen des Dienstes ein, auf den du eine Datei richtest** - vor allem seine Lizenz und was er genannt haben will. Dateien für andere Regionen können als Beispiele in diesem Repository geteilt werden.

## Noch nicht dabei

- **Ladesäulenregister der Bundesnetzagentur** (Deutschland, CC BY 4.0, eine CSV von rund 50 MB mit täglichem Webdienst) und andere nationale Register: Sie sind Listen, keine „frag rund um einen Punkt"-Dienste, und passen deshalb nicht in eine Anbieter-Datei. Ein Länderpaket, das offline gelesen wird, kann folgen.
- **Live-Belegung** von den nationalen Zugangspunkten der EU (DATEX II): kommt je Land dazu, sobald ein Zugang ohne Vertrag nutzbar ist.
