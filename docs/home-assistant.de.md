# Das Home-Assistant-Plugin

[🇬🇧 English](home-assistant.md) · 🇩🇪 Deutsch

Dein Home Assistant weiß wahrscheinlich schon viel über dein Auto: die Integration des Herstellers, einen Tracker, einen Reifensensor, **eine Wallbox**, die es lädt. Das Home-Assistant-Plugin bringt diese Entitäten in Car Assistant - **für jedes Fahrzeug einzeln**. Für jede Schnittstelle der [Plugin-API](api.de.md) (Kilometerstand, Tank, Batterie, Ladeleistung, Türen, Reifen, Position ...) wählst du die Entität aus Home Assistant, die sie liefert; die App liest sie, rechnet die Einheit um und behält sie wie jeden anderen Wert des Fahrzeugs.

- **Je Fahrzeug.** Jedes Fahrzeug hat seine eigene Installation des Plugins und seine eigene Auswahl. Die Wallbox in der Garage gehört zu dem Auto, das dort lädt - du entscheidest für jedes Fahrzeug, welche Schnittstelle woher kommt.
- **Live.** Änderungen kommen sofort an, ohne dass jemand immer wieder nachfragt (siehe [Live und Nachfragen](#live-und-nachfragen)).
- **Sauber.** Einheiten werden umgerechnet, ein Ja / Nein wird nach der Art der Entität verstanden, jeder Wert trägt die Zeit, die Home Assistant nennt, und eine Schnittstelle kann bei einem Fahrzeug nur von **einem** Plugin kommen ([Eine Schnittstelle, ein Plugin](#eine-schnittstelle-ein-plugin)).
- **Für alle.** Das Paket ist eine einfache `plugin.json` mit einem Schlüssel, `bridge`; sie führt keinen Code aus. Siehe [Für Paket-Autoren](#für-paket-autoren).

Es arbeitet im **Home-Assistant-Add-on** (die App spricht über den Supervisor mit Home Assistant). Nur Administratoren wählen die Entitäten: Die Entitäten von Home Assistant gehören dem System, nicht dem Fahrzeug.

## Einrichten

1. *Fahrzeug → Weiteres → Plugins → Hinzufügen* und **Home Assistant** aus deiner Quelle nehmen (oder das Beispiel [`examples/home-assistant/plugin.json`](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/examples/home-assistant/plugin.json) hochladen).
2. Die Einstellungen öffnen. Die Seite listet die Schnittstellen in Gruppen: *Fahrzeug*, *Kraftstoff und Reichweite*, *Batterie und Laden*, *Wallbox*, *Türen, Fenster und Schloss*, *Position*, *Reifen*, *Temperaturen und Klima*, *Service und Warnungen*.
3. In das Feld einer Schnittstelle klicken: Es öffnet sich eine Liste **wahrscheinlicher Entitäten**. Zum Eingrenzen tippen, eine anklicken.
4. Die Zeile unter dem Feld sagt, **was die Entität jetzt liefert** (`64 %`, `7,4 kW aus 7400 W`, `Verriegelt`). Speichern.

Ab dann fließen die Werte; die Kachel des Plugins und seine Seite *Protokoll* sagen, was es tut.

## Eine Entität wählen

Die Liste ist auf die Schnittstelle zugeschnitten, in die du klickst: Entitäten der passenden Art stehen vorn (ein Schloss für *Verriegelt*, ein Sensor mit der Geräteklasse *Entfernung* oder einer Längeneinheit für *Reichweite*), danach der Rest. Was du tippst, wird in **Name, ID, Gerät und Bereich** gesucht - *Garage* findet also alles von der Wallbox in der Garage, wie in Home Assistant selbst. *Alle Entitäten zeigen* hebt den Filter nach Art auf. Jede Zeile zeigt Name, ID, Gerät und Bereich und den aktuellen Zustand.

Die Zeile unter einem gewählten Feld wird live geprüft: *Diese Entität gibt es in Home Assistant nicht*, *Die Einheit „l“ passt nicht*, *Gerade nicht verfügbar* sagen sofort, was nicht stimmt.

## Live und Nachfragen

Car Assistant hält eine **Live-Verbindung** zu Home Assistant (dessen WebSocket-Schnittstelle, über den Supervisor, wie der REST-Zugang). Sie verfolgt **genau die Entitäten, die du gewählt hast** - sonst nichts aus deinem Home Assistant - und eine Änderung kommt sofort an; ein Schwall von Änderungen wird höchstens einmal pro Sekunde zu einer Lesung. Solange sie steht, sagt die Seite: *Live-Verbindung zu Home Assistant: Änderungen kommen sofort an.*

Fällt die Verbindung aus (Home Assistant startet neu, das Netz hakt), baut die App sie mit wachsenden Pausen (1 bis 60 Sekunden) wieder auf, schaut danach noch einmal alles an (damit nichts verpasst wird, was inzwischen geschah) und **fragt Home Assistant in der Zwischenzeit**, alle *Mindestens nachsehen alle* Sekunden (die Einstellung des Plugins, Standard 30). Ohne die Bibliothek oder außerhalb des Add-ons gibt es einfach keine Live-Verbindung, und das Plugin fragt. Steht die Verbindung, setzt die Einstellung nur ein Sicherheitsnetz: Home Assistant wird alle fünf Minuten noch einmal angesehen (oder seltener, wenn du eine längere Zeit einstellst), damit nichts lange falsch bleibt.

## Was unterwegs geschieht

- **Einheiten.** Eine Zahl wird in die Einheit umgerechnet, die die Plugin-API führt: Meilen, Fuß, Meter - km/h, mph, m/s, Knoten - W, kW, MW - psi, kPa, hPa, mbar, mmHg, inHg - Gallonen, Milliliter, kWh - °F, K - mV - Stunden, Sekunden, Tage - km/l, mpg, Wh/km, mi/kWh. Eine Einheit, die nicht passt (Liter für einen Prozentwert), wird **nicht geraten**: Die Zeile sagt es, und du kannst in den Optionen die Einheit oder *Unverändert* wählen.
- **Datum und Uhrzeit.** Für *Restzeit Laden* und *Tage bis zum Service* geht auch eine Entität, die eine Zeit oder ein Datum enthält: Genommen werden die Minuten oder Tage bis dahin.
- **Die Zeit der Messung.** Jeder Wert trägt die Zeit, die Home Assistant nennt (`last_reported` / `last_updated`), als `measured_at`. Liefern zwei Quellen dasselbe Feld, gewinnt die **neuere Messung**; eine ältere ersetzt nie eine neuere.
- **Nur, was sich geändert hat**, wird gesendet. Eine Entität, die *nicht verfügbar* oder *unbekannt* ist, wird übersprungen (der letzte Wert bleibt, mit seinem Alter) - ein schlafendes Auto ist kein Fehler. Einen Wert, den die Plugin-API ablehnen würde (ein Tankstand von 250 %), lehnt sie nur für diese Zeile ab; die anderen laufen weiter.
- **Der Kilometerstand** wächst nur, wie überall in Car Assistant: Ein Stand, der niedriger ist als der höchste bekannte (auch ein Tank- oder Serviceeintrag mit höherem Stand zählt als bekannt), wird nicht genommen und einmal im Protokoll des Plugins vermerkt; er zählt wieder, sobald er höher ist. Es muss nichts ausgelöst werden: Sobald eine Entität für den Kilometerstand gewählt ist, kommt jede Änderung von selbst, und das Dashboard zeigt den Stand an, statt ihn zur Eingabe anzubieten.

### Ja und Nein

Ein Ja / Nein wird danach gelesen, was die Entität ist: ein **Schloss** (`locked`), ein **Binärsensor** nach seiner Geräteklasse (*Tür*, *Fenster* oder *Öffnung* heißt offen; *Stecker* heißt eingesteckt; *Batterie lädt* heißt lädt; bei der Klasse *Schloss* meint Home Assistant `an` = entriegelt - das wird für dich umgedreht), eine **Abdeckung** (`open`, `opening`, `closing` = offen), eine **Klima**-Entität (alles außer `off` = an), ein **Schalter** oder **Licht** oder ein Status-**Text** (`locked`, `plugged_in`, `Charging` ...). Eine Entität, die von etwas anderem handelt als die Schnittstelle (ein Türsensor für *Verriegelt*), wird mit einem Hinweis abgelehnt.

Wo die Entität es nicht in Worten sagt, die Car Assistant kennt, helfen die Optionen der Zeile: **Zustände, die Ja bedeuten** (bei einem Wallbox-Statussensor: `Preparing, Charging, SuspendedEV` für *Eingesteckt*, `Charging` für *Lädt* - jeder andere Zustand ist Nein), **Ja über** (eine Ladeleistung über 0 heißt lädt) und **Umkehren**.

### Position, Reifen, Türen, Warnungen

- **Position.** Wähle einen *Tracker* oder eine *Person* (oder irgendeine Entität mit `latitude` und `longitude`) oder - weiter unten in der Gruppe - zwei Sensoren, einen für jede Hälfte. Eine Position von 0, 0 (kein Fix) wird nicht genommen.
- **Fahrten aus einem Tracker.** Unter *Optionen* der Positions-Zeile hält *Fahrten dieses Trackers aufzeichnen* jede Bewegung des Trackers als Punkt der Strecke fest, und eine beendete Fahrt wird zu einer Fahrt im Fahrtenbuch - mit Strecke, Entfernung und Zeiten, genau wie eine Fahrt, die ein Plugin als Track schickt. Es ist aus, bis du es einschaltest (eine Strecke ist mehr als die letzte Position). Ein Punkt wird nur gehalten, wenn das Auto mindestens 40 m vom letzten entfernt ist (ein parkender Tracker zittert um ein paar Meter), nicht, solange eine Zündungs-Entität gewählt ist und „aus“ sagt, und nicht bei einem Fix, den der Tracker selbst als ungenau meldet (`gps_accuracy` über 100 m). Eine Fahrt endet, wenn zehn Minuten nichts Neues kam oder die Zündung ausgeht; eine unter 300 m oder mit weniger als drei Punkten fällt weg. **Wie fein die Strecke ist, hängt davon ab, wie oft der Tracker meldet:** Eine Handy-App, die jede oder jede zweite Minute meldet, gibt gute Fahrten, eine Auto-Integration, die alle zehn Minuten meldet, gibt keine. Die Strecke bleibt auf diesem Server.
- **Reifen.** Vier Schnittstellen, eine je Rad; der Druck wird in bar umgerechnet.
- **Türen, Fenster, Lichter, Warnungen** sind Listen: eine Zeile je Tür (`front_left`, `trunk` ...), mit einem Namen, den du wählst, und der Entität. Eine Warnung zeigt ihren Text (den Namen der Entität oder den Text, den du eintippst), solange ihre Entität an ist, und verschwindet, wenn sie aus ist.

### Optionen einer Zeile

Selten nötig, eingeklappt, bis du eine Entität gewählt hast: **Attribut** (dieses Attribut der Entität statt ihres Zustands lesen - die Temperatur einer Klima-Entität, den Kurs eines Trackers), **Einheit**, **Faktor** und **Versatz** (`Wert × Faktor + Versatz`, zuletzt angewendet), **Zustände, die Ja bedeuten**, **Ja über**, **Umkehren** und bei einer Warnung der **Angezeigte Text**.

### Eine Wallbox

Die Gruppe **Wallbox** bringt, was eine Wallbox außer ihrer Leistung weiß. Alles darin ist freiwillig - binde, was dein Home Assistant hat:

| Schnittstelle | Eine Entität aus ... | Wofür |
|---|---|---|
| *Zustand der Wallbox* | ein Statussensor oder ein Helfer, der das Wort hält (`sensor`, `select`, `input_select`, `text`, `input_text`) | ein Wort für das, was die Wallbox tut: **Kein Auto, Angesteckt, Wartet, Lädt, Fertig, Störung** |
| *Energie dieser Ladung*, *Zähler der Wallbox* | `sensor`, `number`, `input_number` (Wh, kWh, MWh) | die genaue Energie: eine fertige Ladung kann damit gebucht werden |
| *Dauer dieser Ladung*, *Spannung*, *Strom*, *Genutzte Phasen*, *Temperatur der Wallbox* | `sensor`, `number`, `input_number` | die Zahlen der Wallbox-Karte |
| *Eingestellter Maximalstrom* | `sensor`, `number`, `input_number`, `select`, `input_select` | das Limit an der Wallbox (6, 10, 16 A ...) |
| *Modus*, *Störung* | `sensor`, `select`, `input_select`, `text`, `input_text`; eine Störung auch `binary_sensor`, `switch`, `input_boolean` | der Modus im eigenen Wort der Wallbox; was los ist (ein Text - `none` heißt nichts - oder ein Ja / Nein der Klasse *Problem*) |

**Die Wörter.** Die üblichen Wörter gängiger Wallboxen werden ohne jede Einrichtung verstanden: OCPP (`Available`, `Preparing`, `Charging`, `SuspendedEV`, `SuspendedEVSE`, `Finishing`, `Faulted`), go-e (`Idle`, `Charging`, `WaitCar`, `Complete`, `Error`), Easee (`disconnected`, `awaiting_start`, `charging`, `completed`, `error`), die Zustände A bis F der IEC 61851 und einfache Wörter (`plugged in`, `paused`, `charge complete`, `fault` ...), einige davon deutsch. Groß- und Kleinschreibung, Leerzeichen, Striche und Punkte spielen keine Rolle. Ein unbekanntes Wort steht an der Zeile (*„Zapfen“ ist kein bekanntes Wort einer Wallbox - nenne es in den Optionen*); unter **Optionen** nennst du die Wörter DEINER Wallbox für jeden Zustand, durch Komma getrennt - sie gelten zuerst, auch vor einem üblichen Wort.

**Ein Wort, drei Schnittstellen.** *Zustand der Wallbox* macht auch *Lädt* und *Angesteckt* des Autos (eine Störung sagt nichts über das Kabel) - es sei denn, du bindest diese beiden an eigene Entitäten. Das Plugin nimmt dem Auto dann beide Schnittstellen, wie jede Schnittstelle, die es füllt.

Helfer und Vorlagen sind Entitäten wie alle anderen: ein `input_select` für den Modus, ein `input_number` für das Limit, ein Vorlagen-Sensor oder ein `utility_meter` für die Energie. Car Assistant liest, was Home Assistant als Zustand nennt (oder das Attribut, das du wählst); es wertet selbst nichts aus. Ein Sensor, der *nicht verfügbar* oder *unbekannt* ist, lässt den letzten Wert stehen.

## Sonderfälle: Home Assistant das Denken überlassen

Jedes Auto, jede Wallbox und jede Integration ist ein wenig anders. Die Optionen einer Zeile decken ab, was eine einzelne Entität anders sagen kann (Einheit, Faktor, Attribut, Ja-Wörter); alles, was **Logik** braucht, gehört dorthin, wo es zu Hause ist: in Home Assistant selbst. Ein Template-Sensor oder ein Helfer ist eine Entität mehr, und das Plugin liest sie wie jede andere. Vier Rezepte, die immer wieder vorkommen:

- **Der Tank in Litern, die Schnittstelle will Prozent.** Kein Template nötig: wähle bei der **Einheit** der Zeile *Unverändert* und trage als **Faktor** `100 ÷ Tankgröße` ein (`1,818` bei 55 Litern). Dasselbe gilt für eine Batterie in kWh (`100 ÷ Kapazität`).
- **Eine Wallbox, zwei Autos.** Ein Helfer (*Einstellungen → Geräte & Dienste → Helfer → Auswahlliste*, etwa `input_select.wallbox_car`) sagt, welches Auto angesteckt ist; jedes Auto bekommt ein eigenes Paar Template-Entitäten, und das Plugin dieses Autos liest diese statt der Wallbox selbst:

  ```yaml
  template:
    - binary_sensor:
        - name: "Auto A lädt"
          device_class: battery_charging
          state: "{{ is_state('sensor.wallbox_status', 'charging') and is_state('input_select.wallbox_car', 'Auto A') }}"
        - name: "Auto A angesteckt"
          device_class: plug
          state: "{{ states('sensor.wallbox_status') in ['preparing', 'charging', 'suspended_ev'] and is_state('input_select.wallbox_car', 'Auto A') }}"
  ```

- **Zwei Quellen für einen Wert** (die Integration des Herstellers schläft, ein Tracker nie): ein Template-Sensor nimmt die erste, die da ist.

  ```yaml
  template:
    - sensor:
        - name: "Reichweite beste"
          device_class: distance
          unit_of_measurement: "km"
          state: >
            {% set a = states('sensor.auto_reichweite') %}
            {{ a if a not in ['unknown', 'unavailable'] else states('sensor.auto_reichweite_schaetzung') }}
  ```

- **Eine Zahl mit Einheit im Text** (`"12,5 km"`): das Plugin will eine Zahl, also schneidet ein Template die Einheit ab: `{{ states('sensor.fahrt_text').split(' ')[0] | replace(',', '.') | float(0) }}`.

Das Plugin liest nur, was Home Assistant als Wert meldet; es wertet selbst nie Templates aus, ein Template kann also nichts in Car Assistant ausführen.

## Eine Schnittstelle, ein Plugin

Eine Schnittstelle, die du hier wählst, **gehört diesem Plugin** für dieses Fahrzeug: Solange es an ist, füllt keine andere Quelle des Fahrzeugs sie - weder ein anderes Plugin noch ein Connector noch die älteren Home-Assistant-Felder des Fahrzeugformulars. Was eine solche Quelle sendet, wird mit `ignored (taken by Home Assistant)` beantwortet und nicht gespeichert; ein Wert des Fahrzeugs hat also immer genau **einen Ursprung**.

- Die Schnittstelle wird beim **Speichern** belegt. Belegt ein anderes Plugin des Fahrzeugs eine der gewählten Schnittstellen, wird nichts gespeichert und die Seite nennt es; in der Zeile steht *Belegt durch ...*.
- Das Plugin **auszuschalten** gibt alles frei, was es belegt (mit dem Einschalten kommt es zurück); ein Plugin, dessen Schnittstellen ein anderes belegt, lässt sich nicht einschalten, bis das geklärt ist. Entfernen gibt sie endgültig zurück.
- Auch andere Plugins können Schnittstellen für sich beanspruchen (`claims` in ihrer `plugin.json`); die Seite *Schnittstellen* eines Pakets listet sie.

Die Regel berührt nie die anderen Fahrzeuge und zwingt kein Plugin, das nicht darum bittet: Ein Plugin, das ein Feld sendet, das niemand belegt hat, ist einfach eine der Quellen, und die neuere Messung gewinnt.

## Mehrere Fahrzeuge, eine Wallbox

Installiere das Plugin bei jedem Fahrzeug und wähle, was dieses Fahrzeug bekommt: die Wallbox, die das Familienauto lädt, als *Lädt*, *Eingesteckt* und *Ladeleistung* dieses Autos, die eigene Integration des Herstellers für Kilometerstand und Reifen. Ein anderes Fahrzeug behält seine eigenen Entitäten. Eine Wallbox, die schon in Home Assistant ist, braucht nichts weiter.

## Sicherung

Die Auswahl gehört zum Fahrzeug: Sie steckt in der [Sicherung des Fahrzeugs](backup.de.md) (und in der Sicherung des ganzen Systems). Nach dem Wiederherstellen ist das Plugin aus, wie jedes wiederhergestellte Plugin; Einschalten belegt seine Schnittstellen wieder. Eine Datei, die nicht von Car Assistant stammt, wird Zeile für Zeile geprüft - eine Entität oder Option, die nicht gültig ist, bleibt weg.

## Für Paket-Autoren

Ein Paket, das dies anbietet, ist eine `plugin.json` ohne Dienst und ohne Connector, mit dem Schlüssel `bridge`:

```json
{ "id": "home-assistant", "kind": "plugin", "name": "Home Assistant", "version": "1.0.0",
  "bridge": { "type": "home_assistant" },
  "settings": [ { "key": "every", "type": "select", "label": "Mindestens nachsehen alle", "default": "30",
                  "options": [ { "value": "10", "label": "10 s" }, { "value": "30", "label": "30 s" }, { "value": "300", "label": "5 min" } ] } ] }
```

| Schlüssel | Bedeutung |
|---|---|
| `type` | `home_assistant` (bisher der einzige) |
| `slots` | optional: nur diese Schnittstellen werden angeboten, nach Schlüssel - zum Beispiel `["charging", "plugged", "charge_power_kw"]` für ein *Wallbox*-Paket |
| `groups` | optional: nur diese Gruppen (`vehicle`, `fuel`, `battery`, `wallbox`, `access`, `position`, `tyres`, `climate`, `service`); `slots` gewinnt, wenn beides steht |
| `every` | optional: der Standard von *Mindestens nachsehen alle*, 10 bis 3600 Sekunden (Standard 30) |
| Einstellung `every` | optional: Deklariert das Paket eine Einstellung mit dem Schlüssel `every`, zeigt die Seite sie, und die Wahl der Person zählt |

Das Paket **nennt nie eine Entität** und sieht nie das Home-Assistant-Token: Der Administrator wählt die Entitäten, die App liest sie. Ein Paket mit `bridge` hat kein Token (niemand ruft die Plugin-API auf; die App tut es). `bridge` und ein `service` oder `connector` schließen sich aus. Prüfen mit `python tools/check_plugin.py <Ordner>`.

Jedes andere Plugin kann mit `"claims": ["fuel_level_pct", "range_km"]` Schnittstellen für sich beanspruchen (Felder der [Plugin-API](api.de.md); nicht `measured_at`; nicht für ein Paket mit `bridge`, das nimmt, was gewählt wird). Ein Plugin, dessen Schnittstellen ein anderes belegt, wird installiert, bleibt aber aus, bis das geklärt ist.

## Grenzen

- Es **liest**. Befehle an das Auto (verriegeln, laden, Klima) über Dienste von Home Assistant sind ein späterer Schritt.
- Es braucht das Home-Assistant-Add-on; in einer Entwicklungsumgebung antwortet Car Assistant *Home Assistant ist nicht erreichbar*, und nichts wird gelesen.
- Ein Wert des Fahrzeugs kann nur aus Entitäten eines einzigen Home Assistant kommen.

## Zusehen

Die Seite **Protokoll** des Plugins (das Protokoll für einen Tag einschalten) sagt, was es liest und was nicht stimmt - einmal für jede Störung, nicht bei jedem Versuch: *die Einheit „l“ passt nicht*, *die Entität gibt es nicht*, *Home Assistant ist nicht erreichbar; neuer Versuch*, *Home Assistant ist wieder erreichbar*, *Home Assistant meldet weniger als den Kilometerstand, den Car Assistant schon kennt*. Die Seite seiner Einstellungen zeigt live, ob die Verbindung steht und was jede Entität liefert. Dieselben Zeilen stehen auch im Protokoll des Add-ons in Home Assistant (siehe [die Protokolle](logs.de.md)).
