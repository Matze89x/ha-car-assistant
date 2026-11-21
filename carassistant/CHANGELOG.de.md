# Changelog

[🇬🇧 English](https://github.com/Matze89x/ha-car-assistant/blob/main/carassistant/CHANGELOG.md) · 🇩🇪 Deutsch

Versionierung: `RELEASE.FEATURES.FEHLER` – die erste Zahl zählt Releases (sie wird mit dem ersten offiziellen Release zu `1`), die mittlere Feature-Versionen, die letzte Fehlerkorrekturen. Die Stufe (Alpha, Beta) steht neben der Version.

## 0.5.0 Beta
- **0.5.0 Beta:** die Beta-Phase beginnt - die öffentliche Testversion. Neu seit der Alpha: Einstellungen in drei Ebenen (Benutzer, Auto, System), Benachrichtigungen und Web-Apps je Auto, MCP-Zugriff für Claude (ein Schalter, ein Schlüssel), die Fahrten-Auswertung und die Kostenseite, das eigene Design und Icon eines Autos. Dokumentation und Screenshots aller Seiten sind mit dieser Version erneuert; bitte ausprobieren und melden, was dir auffällt (siehe CONTRIBUTING).

## 0.4.20 Alpha
- **Web-App, Abstand oben 30 px** (eine Zahl: --app-gap).

## 0.4.19 Alpha
- **Web-App, Abstand oben 28 px:** die weiche Unschärfe, die iOS über die Statusleiste legt, berührte bei 18 px noch die Oberkante von Titel und Kennzeichen; die Seite hält jetzt 28 px (eine Zahl: --app-gap).

## 0.4.18 Alpha
- **Web-App, Abstand oben wieder auf einem sicheren Wert:** die Seite hält wieder 18 px Abstand unter der Statusleiste (es waren 4 px, und sie fiel in die weiche Unschärfe, die iOS über den Bereich der Statusleiste legt). Der leere Streifen unter dem Titel bleibt entfernt. Der Abstand ist eine einzige Zahl im Stylesheet (--app-gap), falls noch ein Schritt nötig ist.

## 0.4.17 Alpha
- **Connector, sicher und einfach:** die Schlüssel-Seite sagt jetzt genau, welchen Eintrag man in Claude wählt (*Benutzerdefinierten Konnektor hinzufügen* / *Add custom connector*, nicht einen der fertigen) und dass der Dialog nur zwei Felder hat, Name und URL. Neue Wahl in der MCP-Kachel: *Schlüssel in der Adresse erlauben* (an = einfachster Weg, nur Name und Adresse; aus = der Schlüssel muss in einem Authorization-Header kommen und bleibt aus Proxy-Protokollen). Die App selbst schreibt nie ein Zugriffsprotokoll, der Schlüssel steht also nie in ihrem eigenen Log.

## 0.4.16 Alpha
- **Connector-Anleitung, einfacher:** die Schlüssel-Seite führt jetzt mit dem einfachsten Weg - Name und die Adresse, die den Schlüssel schon enthält, alles andere bleibt leer. Der Header-Weg (schlichte Adresse plus Authorization-Header) steht als zweite Kachel und ist als der sicherere für Dialoge mit einem Request-Header-Feld gekennzeichnet.

## 0.4.15 Alpha
- **Web-App, kein leerer Streifen oben:** in einer installierten Web-App (Home-Bildschirm) beginnt jede Seite jetzt direkt unter der Statusleiste - der zusätzliche Abstand über dem Titel entfällt, und ein Titel ohne zweite Zeile (der Autoname ist dort ausgeblendet) ist nur noch so hoch wie der Titel selbst. Vorher hatte ich nur den Autonamen und das Wechselzeichen entfernt; das hier ist der fehlende Teil.

## 0.4.14 Alpha
- **MCP, einfacher: ein Schalter, ein Schlüssel.** Die Stufe (Aus / Lesen / Lesen und schreiben) ist die einzige Einstellung und gilt für das ganze System; es gibt einen Zugriffsschlüssel - einmal *Zugriffsschlüssel erstellen*, später *Schlüssel erneuern* (ein neuer entsteht, der alte gilt sofort nicht mehr) oder *Löschen*. Die Stufe je Schlüssel und die Schlüsselliste entfallen; ein vorhandener Schlüssel funktioniert weiter, bis du ihn erneuerst.

## 0.4.13 Alpha
- **Werte zum Kopieren als Felder:** die Seite des Zugriffsschlüssels (Schlüssel, Name, Adresse, Header-Name und -Wert) und die Kachel *Web-App für ein Auto* zeigen jeden Wert in einem schreibgeschützten Feld mit eigenem *Kopieren*-Button - ein Tipp markiert alles. Die Web-App-Adressen sind jetzt deine eigene https-Adresse (nie der Pfad des Home-Assistant-Panels); ohne gespeicherte Adresse sagt die Kachel, dass sie zuerst gespeichert werden muss. Die Schlüssel-Seite erklärt außerdem Schritt für Schritt, wie man den Connector in Claude hinzufügt, und bietet den Schlüssel in der Adresse für Connector-Dialoge ohne Header-Feld an.

## 0.4.12 Alpha
- **MCP-Kachel, ordentlicher:** die Stufe, die Adresse für den Client, die Zugriffsschlüssel (mit Zähler), ein gerahmtes Formular *Neuer Schlüssel* und die letzten Aufrufe sind eigene Blöcke mit gleichem Abstand und feiner Linie dazwischen; die Adresse steht in einem eigenen Kasten.

## 0.4.11 Alpha
- **MCP, um Daten von überall zu vervollständigen:** ein neues Werkzeug *data_gaps* listet, was bei einem Fahrzeug fehlt (leere Fahrzeugfelder, Tankungen ohne Kilometerstand / Menge / Preis, Service ohne Kosten oder Kilometerstand, nie erledigte Aufgaben, Fahrten ohne Orte), damit Claude dich nach den Werten fragen und sie eintragen kann. Die Suche eines MCP-Clients nach einem OAuth-Server bekommt jetzt ein schlichtes 404 statt der Anmeldeseite. Die MCP-Seite erklärt, wie man es als Connector im Claude-Konto hinzufügt (Web-Chat, Desktop, Handy).

## 0.4.10 Alpha
- **Fahrten-Auswertung (Seite Fahrten):** eine neue Kachel mit Auswahl 30 Tage / 90 Tage / Jahr / Alle: Anzahl der Fahrten, Strecke, je Fahrt, Fahrzeit, Durchschnittstempo und die längste Fahrt; der Anteil Arbeitsweg / Privat / Geschäftlich; wie lang die Fahrten sind (Längenklassen in den angezeigten Einheiten); wann du fährst (Wochentag × Tageszeit als Heatmap); und der Fahrstil über alle aufgezeichneten Fahrten mit Zeitstempeln - starkes Bremsen je 100 km, Durchschnittstempo in Bewegung, Stillstandsanteil, Spitze.

## 0.4.9 Alpha
- **Benachrichtigungen je Auto (Einstellungen → Auto):** das Einschalten für ein Gerät geschieht jetzt im Reiter *Auto* jedes Autos - das iPhone / iPad / der Computer, den du benutzt, wird für dieses Auto eingeschaltet (ein Gerät kann mehrere Autos bedienen, und die Web-App eines Autos funktioniert genauso). *Benutzer* zeigt deine Geräte mit den Autos, die sie bedienen, und lässt sie entfernen; die Testnachricht wird im Reiter des Autos an dessen Geräte geschickt. **MCP:** die Stufe hat jetzt einen eigenen *Speichern*-Button.

## 0.4.8 Alpha
- **Home-Video verschwindet nicht mehr (iPhone):** wenn du Home verlässt, solange das Video noch läuft, und zurückkommst, zeigte die Seite bis zum erneuten Laden des Videos einen leeren Kasten. Jetzt wird ein Bild des Moments festgehalten und sofort gezeigt, und das Video läuft von dort weiter (ein Video, das schon zu Ende war, bleibt wie bisher auf seinem letzten Bild stehen).

## 0.4.7 Alpha
- **Web-App, mehr Platz oben:** in der eigenen Web-App eines Autos entfällt auf allen Seiten die Zeile mit dem Autonamen unter dem Seitentitel, jede Seite beginnt direkter (sie wiederholte nur, was die App ohnehin ist). Im normalen Browser ändert sich nichts.

## 0.4.6 Alpha
- **Weiteres, enger auf dem Handy:** der leere Streifen zwischen dem Titel *Weiteres* und der ersten Liste entfällt.

## 0.4.5 Alpha
- **Web-App, ruhiger:** in einer installierten Web-App (Home-Bildschirm) ist das kleine *Auto wechseln*-Zeichen neben dem Autonamen überall ausgeblendet - jedes Auto hat seine eigene Web-App; die Kachel *Diese App zeigt nur …* ganz unten unter Weiteres entfällt. Der Weg zurück zu allen Autos bleibt unter Einstellungen → Benutzer, in der Kachel *Web-App für ein Auto*, und erscheint nur, solange das Gerät ein Auto zeigt.

## 0.4.4 Alpha
- **Auto-Reiter und Sensoren, aufgeräumt:** Foto und Video brauchen keinen Speichern-Button mehr - die Wahl, was Home zeigt oder das Foto des Autos, wird sofort gespeichert; die drei Auswahlen des Video-Hintergrunds umbrechen ihre Erklärung in der Kachel, statt herauszulaufen (Handy: untereinander). In der Kachel *Sensoren in Home Assistant* (System): Speichern in eigener Zeile, darunter ein kurzer Text zu jeder der zwei Aktionen und dann eine Zeile mit den Buttons *Neu einlesen* (Home Assistant zur App: verknüpfte Sensoren wie Kilometerstand, Tank, Position) und *Neu senden* (App zu Home Assistant: alle Auto-Sensoren; ausgegraut, solange die MQTT-Sensoren aus sind).

## 0.4.3 Alpha
- **Einstellungen aufgeräumt:** das allgemeine App-Icon ist fest (keine Icon-Kachel mehr unter System), das Icon des Autos ist eine eigene Kachel ganz oben im Reiter Auto (vor Foto und Video); *Verknüpfte Sensoren neu einlesen* (und *Sensoren neu senden*) sind in die Kachel *Sensoren in Home Assistant* gewandert, die Kachel *Daten aktualisieren* entfällt; der Satz über die eine Farbe für alle ist am Farbrad entfernt.

## 0.4.2 Alpha
- **Einstellungen in drei Ebenen - Benutzer, Auto, System:** die Reiter heißen jetzt *Benutzer* (was persönlich ist), *Auto* (alles, was zu einem Auto gehört) und *System* (die ganze App). *Design* und *Region* sind Kacheln von System. Der neue Reiter *Auto* gilt für das Auto unter dem Titel (wechseln mit dem Schalter neben dem Namen) und enthält: Foto und Video (aus dem Fahrzeugpass verschoben), das eigene Design des Autos mit eigenem Farbrad, das Icon des Autos, die Home-Assistant-Entitäten, Benachrichtigungen für dieses Auto sowie Sichern / Archivieren / Löschen (als klare Zeilen neu angeordnet). Unter *Benutzer* wählst du je Auto, ob du überhaupt benachrichtigt werden willst, und wie; welche Ereignisse du zu einem Auto bekommst, stellst du auf dessen Auto-Reiter ein. Der Fahrzeugpass trägt kein Design, keine Entitäten, kein Foto und keine Sicherung mehr. Nebenbei behoben: eine Meldung nach dem Speichern ging bei Seitenadressen mit Anker verloren.

## 0.4.1 Alpha
- **Changelog-Links funktionieren in Home Assistant:** der Sprachlink und die Doku-Links in beiden Änderungsprotokollen sind jetzt vollständige Adressen, weil der Update-Dialog von Home Assistant das Protokoll ohne das Repository zeigt und die relativen Links in eine nicht öffnbare Seite verwandelt hat. Ein Test hält das so. Der Versionshinweis oben beschreibt das neue Schema.

## 0.4.0 Alpha
- **0.4.0 Alpha:** die App ist jetzt in der Alpha-Phase. Version und Stufe stehen in einer einzigen Datei (`release.json`) und werden mit `tools/release.py` überall eingetragen. Schema: Release.Features.Fehler – ein neues Feature erhöht die mittlere Zahl, eine Fehlerkorrektur die letzte. Die Seiten-Dokumentation und neue Screenshots folgen mit der Beta.
- **MCP-Zugriff (Einstellungen → System):** Claude Code (oder ein anderer MCP-Client) kann die Einträge deiner Autos lesen - und mit der höchsten Stufe korrigieren. Standardmäßig aus und nur mit Benutzer, gespeicherter externer https-Adresse und offenem Port einschaltbar; eigene Zugriffsschlüssel je Client (einmal angezeigt, als Hash gespeichert) mit der Stufe Lesen oder Lesen + Schreiben, die nie über der Stufe des Servers liegt; kein Weg über das Home-Assistant-Panel oder andere Webseiten; falsche Schlüssel werden ausgebremst und gesperrt, Aufrufe sind begrenzt und protokolliert. Werkzeuge: App-Info, Fahrzeuge, Fahrzeugdaten, Einträge, Kosten, Plugin-Logs, Eintrag anlegen / ändern / löschen. Siehe `docs/mcp.de.md`.

## 0.3.585
- **Links mit Anker bleiben an ihrer Stelle:** auf der Auswertung springen die Kategorie-Links der Ausgabenliste (Alle / Tanken / Service / Umbauten / Teile) nicht mehr nach oben – die Liste bleibt im Bild. Das gilt ebenso für jeden anderen Link mit Anker.

## 0.3.584
- **Web-App für ein Auto:** unter Einstellungen → Benutzer gibt es „Web-App für ein Auto“ mit einem Startlink je Auto. Diesen Link auf den Home-Bildschirm legen: Die App öffnet direkt dieses Auto und zeigt nur dieses – ohne Fahrzeugwechsel und ohne Liste der anderen (unter Weiteres holt ein Button auf diesem Gerät alle Autos zurück). Der Gültigkeitsbereich der Web-App ist jetzt die ganze App, so dass kein Link mehr den kleinen In-App-Browser des Handys öffnet – das war die seltsame, nicht klickbare Seite nach dem Fahrzeugwechsel.
- **Benachrichtigungen führen zur richtigen Seite:** eine Meldung zu einem Thema öffnet diese Seite des Autos (Termine, Aufgaben, Reifen, Fahrten); zu mehreren Themen die Übersicht des Autos. Ein Gerät, das die Benachrichtigungen in der Web-App eines Autos eingeschaltet hat, bekommt nur die Meldungen dieses Autos (weiterhin je Person und je Auto in der Auswahl); die anderen bekommen wie bisher alle.
- **Demo-Autos:** deutlich mehr Daten in jedem Bereich (Service, Termine, Umbauten, Teile, Dokumente), und jede Art Meldung hat je Auto etwas zu sagen – Tank oder Akku niedrig, ein weicher Reifen, eine offene Tür oder Heckklappe, eine Fahrzeugwarnung, ein anstehender Service, fällige Aufgaben und Termine, eine gerade beendete Fahrt.

## 0.3.583
- **Die Auswertung ist jetzt die Kostenseite:** oben das ausgegebene Geld im gewählten Zeitraum (Tage / Wochen / Monate) mit dem Durchschnitt je Zeitraum, allen Kosten je 100 km und dem teuersten Eintrag; „Wohin das Geld geht“ teilt es in Tanken, Service, Umbauten und Teile auf (Kategorie antippen = filtern); unter dem Kostendiagramm eine Liste jedes Eintrags mit Preis – Tankungen, Service, Umbauten und Teile –, nach Monaten gruppiert mit Zwischensumme, nach Kategorie filterbar, jede Zeile führt zur zugehörigen Seite. Verbrauchs-, Preis- und Kilometerdiagramm folgen darunter.

## 0.3.582
- **Dashboard-Widgets, neuer Look:** jede Kachel bekommt eine Tönung und eine Farblinie in ihrer eigenen Farbe und größere Zahlen; kleine Diagramme zeigen den Verlauf – Verbrauch und Preis je Tankung als Sparklines, die letzten sieben Tage Fahrt als Mini-Balken mit der Wochensumme; die Verbrauchskachel zeigt, wie die letzte Füllung zum Durchschnitt liegt; der nächste Termin zeigt einen großen Countdown in Tagen; die Service-Kachel einen Fortschrittsbalken der als Nächstes fälligen Arbeit; „Braucht Aufmerksamkeit“ als saubere Liste (Titel oben, Details klein darunter, auf breiten Bildschirmen zwei Spalten).

## 0.3.581
- **Buttons überall oben rechts:** die Fahrzeug-Bearbeiten-Seite hat ihr Speichern im Seitenkopf (die zusätzlichen Speichern-Leisten in den Gruppen entfallen), die Umbauten-Seite ihr Hinzufügen im Kopf (das neben dem Feld entfällt). Speichern führt zurück zur Ansicht.

## 0.3.580
- **Reifen, eine Bearbeiten-Seite:** die Seite öffnet auf Sommer; die Tabs sind immer Sommer / Winter / Ganzjahr im gewohnten Design (ohne Punkte). Der Reifendruck steht oben in der Satz-Kachel als „Reifendruck“: der vom Auto gemessene Wert, der empfohlene in Klammern. Bearbeiten ist eine Seite mit einem Speichern (oben rechts) für Drücke, alle Sätze, den montierten Satz und das Entfernen von Sätzen – kein Abbrechen, kein Hinzufügen; ein leerer Satz je Saison ist immer da.
- **Fahrzeugpass:** die zwei Spalten sind wieder sauber getrennt (eine breite Zeile verschiebt die Trennlinie nicht mehr); eine einzelne Kachel bekommt eine leere daneben.
- **Dokumente:** der Hochladen-Button im Kopf ist der einzige und funktioniert – er öffnet die Dateiauswahl und lädt sofort hoch, die Kategorie wird aus dem Dateinamen erraten (beim Tippen eines Titels wurde das Formular zu früh abgeschickt).
- **Zusatzarbeiten:** Feld, „Zurücksetzen“ und Bearbeiten in einer Zeile am unteren Rand der Kachel, handytauglich.
- **Integrationsseiten:** die Kopfleiste läuft über die ganze Breite, ihr Inhalt hält die Maximalbreite von Car Assistant.

## 0.3.579
- **Auswertung:** Neues Diagramm „Preis je Einheit“ (Preis pro Liter / kWh über die Zeit, mit Trendlinie), mit demselben Filter.

## 0.3.578
- **Reifen:** Der empfohlene Reifendruck steht jetzt in der Kachel des Reifensatzes (normal und beladen, vorne und hinten in einer Kachel). Speichern der Drücke führt direkt zur Seite zurück; im Bearbeiten-Modus heißt der Kopf-Button jetzt „Abbrechen“ statt eines zusätzlichen „Fertig“.

## 0.3.577
- **Video auf der Startseite, jetzt richtig:** Ist das Video zu Ende gelaufen, wird sein letztes Bild als Bild gemerkt; kommst du zu Home zurück, erscheint dieses Bild sofort und das Video wird weder neu geladen noch gestartet (am Handy verschwand es, wenn es neu geladen und angesprungen werden musste). Ein Tipp spielt es noch einmal ab.

## 0.3.576
- **Navigationsliste (Weiteres → Integrationen):** Kein Drag & Drop mehr – der Griff in jeder Zeile ist weg, das Symbol sitzt sauber am Rand der Zeile, und nur noch die Pfeile verschieben eine Seite nach oben und unten. Leichter, und am Handy ist nichts mehr im Weg.

## 0.3.575
- **Auswertung erweitert:** Kosten je Zeitraum als gestapelte Balken (Tanken, Service, Umbauten, Teile, mit Summen), Kilometer je Zeitraum und eine gestrichelte Trendlinie (Durchschnitt aus 5) im Verbrauchsdiagramm. Alles folgt dem Filter Tage / Wochen / Monate.

## 0.3.574
- **Reifen:** Die Ansicht nutzt die volle Breite – jeder Wert (Achsgrößen, DOT, Lagerort, Drücke) steht in einer eigenen Zeile statt in zwei Spalten.

## 0.3.573
- **Schonender für GPU/CPU:** Der endlos pulsierende Punkt und das große Leuchten laufender Plugin-Kacheln sind weg (sie zeichneten alle Kacheln ständig neu), der grüne Start-Button hat keinen großen Schatten mehr und die Seitenleiste weichzeichnet weniger (12 px, ohne Farbverstärkung). Sieht gleich aus, kostet deutlich weniger – besonders auf den Seiten Integrationen und Plugins.

## 0.3.572
- **Fahrzeugpass:** Korrektur – die Auswahlkacheln (Kraftstoff, Energie-Ansicht) schoben lange Namen wie „Autogas (LPG)“ am Handy über den Kartenrand; die Namen brechen jetzt innerhalb der Kachel um.

## 0.3.571
- **Video auf der Startseite:** Es läuft einmal pro Besuch; kommst du zu Home zurück, steht es am letzten Bild, statt neu zu starten oder zu verschwinden. Ein Tipp darauf spielt es noch einmal ab.

## 0.3.570
- **Dashboard:** „Braucht Aufmerksamkeit“ zeigt die vier dringendsten Punkte und „+n weitere“ als Link zu den Aufgaben; das Widget bleibt kompakt.

## 0.3.569
- **Google-Suche als Hilfe (standardmäßig aus):** Unter *Einstellungen → System* kannst du neben den Fahrzeugfeldern, die man nicht auswendig kennt (Variante, Motorkennbuchstabe, Ölspezifikation, HSN/TSN und mehr), eine Lupe einschalten. Ein Klick öffnet in einem neuen Tab eine Google-Suche zu deinem Fahrzeug und dem Feld (z. B. „… 2.0 TDI - Motoröl-Spezifikation“). Die App sendet selbst nichts.

## 0.3.568
- **Über-Seite:** linksbündig und kompakter, in breiten Fenstern zweispaltig (links die App, Bibliotheken und Danksagungen, rechts was je Fahrzeug installiert ist); am Handy einspaltig.
- **Dashboard:** Der Inhalt hat dieselbe feste Breite wie die anderen Seiten.

## 0.3.567
- **Buttons:** Korrektur – der engere Symbol-Abstand aus 0.3.564 traf auch runde Buttons ohne Text (ungleicher Abstand links). Er gilt jetzt nur noch für Buttons mit sichtbarem Text und überschreibt nie die runden Kopf-Buttons.

## 0.3.566
- **Standort-Widget:** Unter „Hier steht dein Auto“ steht jetzt der Ort (wie bei den Fahrten) und klein darunter die Straße – einmal pro Stelle abgefragt, wenn die Karteninfo an ist. Die Karte ist niedriger, näher herangezoomt mit dem Auto in der Mitte, und die Markierung ist ein Auto in der Akzentfarbe.

## 0.3.565
- **Navigation wie bei einer One-Page-App neu gebaut:** Die Leiste (unten am Handy, seitlich im breiten Fenster) bleibt beim Seitenwechsel in der Seite; nur der Inhalt wird getauscht und die Leiste ändert lediglich den aktiven Eintrag, die Markierung gleitet also genau einmal. Kein Überblenden der ganzen Seite mehr (das ließ die Leiste aufblitzen), keine Ebenen, kein zweites Gleiten.

## 0.3.564
- **Buttons, ein System:** Die Kopf-Buttons aller Listenseiten (Hinzufügen) und der Reifen-Seite (Bearbeiten farbig, Fertig schlicht) sehen jetzt aus wie bei den Integrationen – Symbol plus Text im breiten Fenster, rundes Symbol am Handy. Buttons mit Symbol und Text haben auf der Symbolseite weniger Innenabstand.

## 0.3.563
- **Fahrzeugpass:** Korrektur – ein Auto mit Erstzulassung, aber ohne TÜV-Termin lieferte einen Serverfehler (500), weil das geschätzte HU-Datum als Datumsobjekt statt als Text übergeben wurde.

## 0.3.562
- **Auswertung:** Der Zeitraum-Filter nutzt die üblichen Tabs (Tage / Wochen / Monate), die Anzahl der Zeiträume steht als Auswahl rechts daneben, alles in einer Zeile.

## 0.3.561
- **Weiteres:** Am Tablet und im breiten Fenster öffnet sich gleich der Fahrzeugpass (kein leerer „Wähle eine Seite“-Bildschirm mehr); am Handy bleibt die Liste. Die Versionszeile unten in Weiteres ist entfernt.

## 0.3.560
- **Mobile Navigation:** Das Gleiten der Markierung nutzt keine eigenen Browser-Ebenen mehr (sie wurden beim Bewegen als eckige Bilder mit verzerrtem Rand um das runde Feld gezeichnet). Die Markierung gleitet jetzt einfach in der echten Leiste vom alten zum neuen Eintrag; die Ebenen-Tricks für Leiste und Einträge sind entfernt.

## 0.3.559
- **Integrationen-Seite leichter:** Die Symbolauswahl der Navigationsliste steckt nicht mehr in jeder Zeile (die Seite hatte 270 KB mit über 500 Symbolen, jetzt etwa ein Viertel); sie erscheint beim Öffnen eines Symbols.

## 0.3.558
- **Benachrichtigungen pro Auto:** unter *Einstellungen → Benutzer → Benachrichtigungen* wählst du ein Auto (Tabs, wenn es mehrere gibt) und legst die Ereignisse für genau dieses Auto fest. Solange du nichts wählst, gilt deine bisherige Auswahl.
- **„Fahrt beendet“ kommt sofort:** Der Check lief nur alle sechs Stunden, die Meldung kam daher spät oder gar nicht; eine beendete Fahrt wird jetzt gleich gemeldet.

## 0.3.557
- **Auswertung:** Korrektur – der neue Zeitraum-Filter hatte in 0.3.556 kaputte Links (Namenskonflikt); sie funktionieren jetzt.

## 0.3.556
- **Auswertung:** Gruppierung wählbar – Tage, Wochen oder Monate – und wie viele Zeiträume angezeigt werden (Tage standardmäßig 30, bis 365; Wochen 4, bis 52; Monate 6, bis 60). Das Diagramm folgt demselben Zeitfenster.

## 0.3.555
- **Reifen-Seite neu:** Sie ist jetzt eine saubere reine Ansicht mit größeren Kacheln – Tabs (Sommer/Winter/Ganzjahr) nur für Jahreszeiten mit Reifensatz oder Drücken, die Drücke als einfache Werte und „Gemessene Werte“ nur, wenn das Fahrzeug welche gemeldet hat. **Bearbeiten** (oben rechts, am Handy nur Symbol) öffnet die Formulare mit allen drei Jahreszeiten; **Fertig** führt zurück.

## 0.3.554
- **Dashboard:** Meldet das Fahrzeug keine Reichweite, wird sie aus dem Tanken geschätzt (Tankgröße ÷ Durchschnitt der letzten fünf Voll-zu-Voll-Intervalle, minus die km seit der letzten Volltankung) und als „≈ … geschätzt aus dem Tanken“ gekennzeichnet. Dafür braucht es die Tankgröße und zwei Volltankungen; der Wert des Fahrzeugs hat immer Vorrang; Elektroautos werden nicht geschätzt.

## 0.3.553
- **Tanken-Seite:** Die Additiv-Kachel oben ist weg (das Additiv behält seine eigene Seite und die Erinnerung im Dashboard). Das Additiv-Paket heißt jetzt *Additive* / *Additivzusatz* (Quelle, Version 4).

## 0.3.552
- **Aufklapp-Gruppen in zwei Spalten:** In der Ausstattung des Fahrzeugpasses ist jede Spalte ein eigener Stapel. Klappst du links eine Gruppe auf, rutschen die Gruppen rechts nicht mehr weit nach unten, sie bleiben alle an ihrem Platz. Auf dem Handy ist es wieder eine Liste in der ursprünglichen Reihenfolge.

## 0.3.551
- **Kopf-Knöpfe auf jeder Seite, Symbol + Text (auf dem Handy ein rundes Symbol), immer oben rechts:** *Dokumente*: ein Knopf *Daten hochladen* (der zweite entfällt); *Handbuch*: *Export*, *Ersetzen*, *Löschen* (mit Rückfrage, bevor alles entfernt wird); *Plugins* und *Integrationen*: *Nach Updates suchen* und *Hinzufügen*; der Reiter *Hinzufügen*: *Liste aktualisieren*; *Quellen*: *Quelle hinzufügen*.
- **Coding:** Die Liste ist auf jeder Breite EINSPALTIG; das gewählte Byte steht in einer Zeile, wie in einem Diagnosewerkzeug: links *Byte N*, daneben seine Bits zum Tippen (die zusätzliche Original-Zeile entfällt).

## 0.3.550
- **Web-App-Name:** *Car Assistant* wird beim Hinzufügen zum Home-Bildschirm nicht mehr zu *Car Assistan* gekürzt.
- **Navigation:** Ein zweites Tippen auf den Eintrag der aktuellen Seite scrollt nach oben, nichts lädt neu oder springt.
- **Fahrzeugpass:** In den Navigations-Einstellungen ist er der feste ERSTE Eintrag von *Weiteres* (nicht sortierbar, nicht ausblendbar), nicht mehr über Home.
- **Fahrten:** Eine Fahrt wird abgeschlossen, sobald die Zündung ausgeht (nicht erst zehn Minuten später), damit ihre Ortsnamen schon da sind, wenn du die Fahrten öffnest; Ortsnamen sind nur der **Ort** (keine Straße): von Ort zu Ort. Früher gemerkte Namen mit Straße werden zum Ort.

## 0.3.549
- **Einrichten auf der Kachel:** Ein Plugin mit Einrichtungsanleitung, das noch nicht eingerichtet ist, zeigt **Einrichten** als die eine Hauptaktion rechts auf seiner Kachel (danach weicht es *Aktualisieren* / *Öffnen*); die Anleitung bleibt auf der Einstellungsseite, ganz oben.

## 0.3.548
- **Einrichtung ganz oben:** Auf der Einstellungsseite eines Plugins, das eine Einrichtungsanleitung mitbringt, ist ihre Karte jetzt die erste (sie stand unter den Einstellungsfeldern).

## 0.3.547
- **Fahrtenkarte:** Die Karte einer Fahrt ist **quadratisch** (so breit wie hoch), und die Strecke sitzt in ihrer **Mitte**; sie ist bei dunklem Design dunkel und bei hellem hell (wie die Standort-Karte); darunter zeigt eine **Legende**, was die Farben bedeuten (eine Skala von langsam bis schnell in deiner Tempo-Einheit, Start und Ziel). Die Texte der Fahrtenkarte (Punkte, hartes Bremsen, Durchschnitt in Bewegung) erscheinen wieder.
- **Fahrstil:** Auf dem Handy wie bisher 2 mal 2, auf Tablet und Web **eine Spalte**.
- **Ortsnamen für ältere Fahrten:** Mit den Karteninfos an, bis zu 1500 der letzten Fahrten und 100 Abfragen je Durchlauf (der nächste Besuch macht weiter).

## 0.3.546
- **Karteninfos mit Ortsnamen:** Der Schalter unter *Einstellungen -> System* heißt jetzt *Karteninfos anzeigen (Karte und Ortsnamen)*. Eingeschaltet fragt die App auch einmal bei OpenStreetMap (Nominatim) nach Straße und Ort von Start und Ziel jeder Fahrt und schreibt den Namen statt der Koordinaten ins Fahrtenbuch; die Antworten werden behalten, ein von dir getippter Name bleibt unberührt, und solange der Schalter aus ist, wird nichts gefragt.

## 0.3.545
- **Updates behalten die Freigabe:** Ein Paket (Dienst, Dateien, Bundles), das du beim Installieren erlaubt hast, bleibt erlaubt, wenn du *Aktualisieren* drückst; die neue Beschreibung wird mit diesem Klick freigegeben. Nichts wird von allein aktualisiert, und ein Paket, das du nie freigegeben hast, bleibt ungeprüft. Keine zweite Freigabe nach einem Update mehr.
- **Coding, neues Layout:** Der Originalcode ist EINE Zeile (sie scrollt seitwärts); darunter stehen die aktuellen Bytes frei davon - nur ein geändertes Byte zeigt seinen alten Wert (*war 2A*); ein angetipptes Byte öffnet untereinander seine Original-Bits und seine aktuellen Bits (getippt oder angehakt) und die acht Bits, je mit einer **Notiz**; Bits, die zusammengehören, lassen sich **gruppieren** (ein Name und ein Wert als Zahl, wie im alten Dashboard); ein Punkt markiert Bytes mit Notizen. Alles lockerer. Den Originalwert kann ein Mensch jederzeit ändern (nur das Schreiben eines Plugins behält ihn).
- **Plugin-Kachel in EINER Zeile:** *Start/Stopp*, *Info* und *Einstellungen* links und die eine Hauptaktion rechts - *Aktualisieren*, wenn eine neuere Version angeboten wird (ihre Version als Marke im Kopf), sonst *Öffnen*. Das Menü *Mehr* entfällt: Die Einrichtungsanleitung, *In der Leiste zeigen* und *Deinstallieren* stehen auf der Einstellungsseite.

## 0.3.544
- **Eine Info-Seite je Plugin:** *Schnittstellen*, *Protokoll* und der Debug-Schalter sind jetzt eine Seite, *Mehr* -> *Info*: Überblick, was das Plugin anbietet und nutzt (Schnittstellen, Dateien), dann sein Protokoll mit dem Debug-Schalter; oben Sprunglinks, leere Schnittstellen-Gruppen entfallen. Die alten Adressen führen dorthin. Das Menü *Mehr* der Kachel hat nur noch *Einrichtung*, *In der Leiste zeigen*, *Info* und *Deinstallieren*.

## 0.3.543
- **Doku für Plugins:** Die Kurzanleitung nennt `setup` und `advanced` und verweist auf die ausführliche Beschreibung; die Seiten, die von den alten Kachel-Knöpfen (*Protokoll*, *Debug* ...) sprachen, sagen jetzt *Mehr*.

## 0.3.542
- **Einrichtung, aufgeräumt:** Schritt 2 hat EINEN Token-Kasten mit den beiden Möglichkeiten nebeneinander (vorhandenes Token weiter verwenden / neues erstellen; auf dem Handy untereinander) und darunter die Einstellungen; kurze Schrittnamen; in Schritt 3 steht die Anbindungsdatei in einer eigenen Zeile mit hellem *Herunterladen*-Knopf, und *Beenden* ist die eine Hauptaktion; überall dieselben Abstände und dieselbe Zeile *Zurück* / Hauptaktion.

## 0.3.541
- **Einrichtung, vorhandenes Token:** Hat die App noch kein Token, bietet Schritt 2 auch *Vorhandenes Token eintragen* an (eins, das schon in der Datei auf dem Gerät steht). Es muss wie ein Token von Car Assistant aussehen und darf nirgends sonst verwendet werden; gespeichert wird nur der Fingerabdruck, danach ist es fest - nur *Neues Token erstellen* ersetzt es.

## 0.3.540
- **Einrichtung in drei festen Schritten:** 1 Prüfen (Adresse und FIN nur lesend, *Weiter* gesperrt, bis beides da ist), 2 Token und Einstellungen (*Neues Token erstellen* oder - wenn eins existiert - seine Kennung und *Vorhandenes Token weiter verwenden*, verglichen mit dem Fingerabdruck; die Einstellungen mit zugeklappten erweiterten; *Weiter* speichert), 3 Dateien und Anleitung (die Anbindungsdatei, die Pakete, der Text, *Beenden*). Das Token wandert nur innerhalb der Seiten mit und wird nie gespeichert. Eine Einstellung darf `advanced` sein.

## 0.3.539
- **Weiteres, schmalere Liste:** Auf Tablet und Desktop ist die Liste links bei *Weiteres* etwa 310 px breit (310 bis 330 px) statt eines Anteils der Breite (etwa 380 px); die Seite bekommt den Rest.

## 0.3.538
- **Plugin-Karte aufgeräumt:** drei Knöpfe mit Worten - *Stopp/Start*, *Einstellungen*, *Mehr* - und die eine Hauptaktion *Öffnen* rechts. Alles andere (Einrichtung, Leiste, Schnittstellen, Protokoll, Debug, Deinstallieren) steht unter *Mehr*, jeweils mit einer Erklärzeile; keine Knöpfe nur mit Symbol, keine Hover-Hinweise.
- **Einrichtungsanleitung für Plugins:** Ein Manifest kann `setup` mitbringen (Schritte mit Text, Token, Anbindungsdatei und Downloads auf einer Seite, nach einer Prüfung, dass eine https-Adresse und die FIN da sind). `{vin}` ist ein neuer Platzhalter der Anbindungsdatei; ein Dienst findet `external_url` und `vehicle_vin` in `settings.json`.

## 0.3.537
- **Korrektur: Die Reihenfolge des Navigations-Editors gilt jetzt auch in *Weiteres*.** Die Leiste folgte der Reihenfolge, aber in *Weiteres* standen die Seiten von Integrationen (Coding, ...) immer hinter allen festen Seiten. Feste Seiten und Integrationsseiten sind jetzt eine Liste in der eingestellten Reihenfolge (je Auto).

## 0.3.536
- **Seiten von Integrationen: Datum und Zugangscodes.** Neuer Feldtyp `date` (Datumsauswahl, geprüft) und Seitenoption `order` (Liste nach einem Feld sortiert, z. B. ein Verlauf mit dem Neuesten zuerst); neuer Feldtyp `secret` für Zugangscodes: verborgen bis *Anzeigen*, ein leeres Feld behält den gespeicherten Code, nie im Suchtext, nie an ein Plugin gegeben, fehlt in der normalen Fahrzeugsicherung (*Sicherung mit Zugangscodes* erzeugt eine eigene Datei), und die System-Sicherung weist darauf hin, dass sie sie enthält. Eine zweite Liste ist einfach eine zweite Seite (siehe `docs/integrations.de.md`).

## 0.3.535
- **Eine Liste für die Seiten:** Die eigene Gruppe *Integrationen* im Navigations-Editor entfällt. Eine Integration mit Seite steht in derselben sortierbaren Liste wie die anderen Seiten, mit eigenem Schalter; eine später hinzugefügte reiht sich hinten ein. Ausschalten oder Entfernen nimmt sie aus der gespeicherten Reihenfolge, damit die anderen ihre Plätze behalten.
- **Coding:** Unter dem Byte-Raster zeigt ein gewähltes Byte eine Zeile mit zwei Fenstern (das Original, fest - und der neue Wert als Bits zum Tippen) und die Bit-Zeilen *Bit 0 ... Bit 7* mit Häkchen; jedes Häkchen ändert den neuen Wert im Feld der Zeile. Der Originalwert lässt sich jetzt jederzeit von dir ändern (nur das Schreiben eines Plugins behält ihn weiter).
- **Coding:** Jede Steuergerät-Zeile ist einzeilig (Adresse, Name, Zusatzzeile, geänderte Bytes; zu lang wird mit ... gekürzt), auch die Werte in einer Zeile.

## 0.3.534
- **FIN als Schlüssel:** Die FIN trägt ein Mensch in den Fahrzeugdaten ein. Ein Plugin kann `vin` über die Plugin-API senden, sie wird nur verglichen: Stimmt sie, zeigt die Seite *Vom Auto bestätigt*, eine andere FIN lehnt die Anfrage ab (`409 vin_mismatch`, nichts gespeichert). Ein Plugin schreibt sie nie.

## 0.3.533
- **Antippbare Seitenverweise auf dem Seitenbild:** Ein Paket kann die Position jedes „Seite 137“ einer Seite mitbringen (`t/NNN.json.gz`); der Leser legt eine dezent rote Fläche darüber (kräftig beim Überfahren), die mit dem Seitenversatz zur Seite springt. Optional und abwärtskompatibel (siehe `docs/manual-package.de.md`).
- **Doku:** Das Beispiel einer Integration ohne Code liegt jetzt im Ordner `example-stations` (Ordnername = Kennung, der Paket-Prüfer akzeptiert es).

## 0.3.532
- **Einfaches Handbuch-Paket:** Ein Zip mit nur nummerierten Seitenbildern (`001.avif`, ...) genügt; `meta.json` und der Textindex sind optional.

## 0.3.531
- **Handbuch mit Seitenbildern:** Ein Handbuch lässt sich als Paket importieren (Zip mit `meta.json`, Seitenbildern und optionalem Textindex); der Leser zeigt die Seite als Bild oder als Text, Kapitel können Abschnitte haben, und ein Verweis wie „Seite 137“ springt mit dem gespeicherten Seitenversatz auf die richtige Seite. Die Bilder gehören zum Auto und sind in der Fahrzeug- und der System-Sicherung enthalten (siehe `docs/manual-package.de.md`).

## 0.3.530
- **CI-Korrektur:** Die Design-Tests lasen die gespeicherte Akzentfarbe und scheiterten auf einem sauberen Stand (GitHub), weil keine Datenbank da war; jetzt bekommt jeder Test seine eigene leere Datenbank.

## 0.3.529
- **Mauszeiger wie in Home Assistant:** Ein normaler Pfeil über Seite und Text, eine Hand nur über Knöpfen, Links und anderem Anklickbaren, der Textcursor nur in Feldern, in die du tippst.

## 0.3.528
- **Fix, Benachrichtigungen:** Eine Benachrichtigung wurde nie gesendet: Die Absender-Adresse, die die Push-Bibliothek prüft, wurde abgelehnt, sodass jeder Versand abbrach, bevor etwas den Server verließ. Jetzt wird sie akzeptiert, und ein Test sendet eine an einen lokalen Testserver und prüft, was hinausgeht.

## 0.3.527
- **Häkchen-Felder:** Der Farbverlauf eines angehakten Feldes deckt jetzt das ganze Feld samt Rand ab, sodass oben und unten keine hellen Blitzer mehr erscheinen; der Leuchtring um angehakte Felder ist endgültig weg.

## 0.3.526
- **Konto-Karte:** *Passkey hinzufügen* sieht jetzt aus wie die anderen kleinen Knöpfe (*Ändern*, *Passcode festlegen*, *Benutzer hinzufügen*), und auf dem Handy zeigen diese Knöpfe nur noch ihr Symbol.

## 0.3.525
- Unter der Adresse in *Einstellungen -> System* steht ein Satz, dass Passkeys und Benachrichtigungen erst aktiviert werden, wenn eine Adresse gespeichert ist.

## 0.3.524
- **Fix, Benachrichtigungen:** Das Anmelden eines Geräts stürzte auf dem Server ab (der Textabruf hatte keine Sprache), sodass jedes Handy nach dem Erlauben mit einem allgemeinen Fehler endete. Jetzt wird das Gerät gespeichert, und ein Test deckt den ganzen Weg vom Schlüssel bis zur Karte ab.

## 0.3.523
- **Ein Platz für die Adresse:** Die externe Adresse steht nur noch unter *Einstellungen -> System* (sie wandert nicht mehr nach *Benutzer*, wenn ein Port gesetzt ist). Unter *Benutzer* erscheinen Passkeys und Benachrichtigungen erst, wenn diese Adresse gespeichert ist.

## 0.3.522
- **Systemseite:** Ohne Benutzer zeigt die externe Adresse nur den Hinweis und einen Link (kein totes Formular, kein doppelter Satz); der Broker-Host sagt nicht mehr zweimal "optional"; Felder untereinander haben einen klaren Abstand.

## 0.3.521
- **Benachrichtigungen:** Die Erlaubnis wird zuerst abgefragt, direkt beim Tippen (das iPhone lehnte sie nach anderem Warten ab); ein Fehler nennt jetzt den Schritt und den echten Grund; auf iPhone und iPad außerhalb der App vom Home-Bildschirm ersetzt eine klare Anleitung den Knopf.
- **Aufgeräumte Einstellungen:** Die Adresse steht nur noch einmal (das Feld), die Häkchen sitzen auf Höhe der ersten Textzeile und ohne Leuchtring.

## 0.3.520
- **Direktzugriff, kurz:** Die Zeile zeigt nur noch *An* (oder *Aus*) und dann *Port: 8099*; der lange Text entfällt.

## 0.3.519
- **Adresse mit festem `https://`:** In *Einstellungen -> System* tippst du nur noch den Host (`auto.example.com`); `https://` steht fest davor, `http://` wird abgelehnt. Das Feld ist ein Stück und passt auch aufs Handy.

## 0.3.518
- **Systemseite auf dem Handy:** Der Port des Direktzugriffs (zum Beispiel `:8099`) klebt nicht mehr direkt am Status; beide stehen nebeneinander und bei wenig Platz untereinander mit Abstand.

## 0.3.517
- **Sicherheits-Header überall:** Auch Abweisungen, die keine Seite erreichen (falsches API-Token, gesperrter Direktzugriff, Weiterleitung zur Anmeldung), tragen jetzt dieselben Header (`nosniff`, Referrer-Policy, Content-Security-Policy) wie jede andere Antwort.

## 0.3.516
- **Bereit für die Öffentlichkeit:** `SECURITY.de.md` (wie du eine Schwachstelle meldest, was die App schützt), `CONTRIBUTING.de.md` (Regeln, Tests), Formulare für Fehler und Ideen, eine Checkliste für Pull Requests und die Abzeichen für CI und Lizenz auf der Startseite. Die Installationsseite beginnt jetzt mit *Aus dem Repository installieren*; die lokale App ist die Alternative.
- **Aufgeräumt:** Zwei Doku-Beispiele nannten eine echte Fahrzeug-Dienstadresse und einen Marken-Begriff für das Fahrzeug-Display; sie sind jetzt neutral. Die internen Arbeitsnotizen und das Schutz-Skript sind nicht mehr Teil des Repositorys.

## 0.3.515
- **Sicherheitsprüfung der Wege von außen:** Ein angemeldeter Benutzer, der *kein* Administrator ist, konnte über die direkte Adresse die komplette System-Sicherung (alle Benutzer, Tokens und Autos) herunterladen oder darüber zurückspielen und systemweite Einstellungen ändern. Diese Wege - Sicherung, Wiederherstellung, Werksreset, externe Adresse, Karte, Spritpreis-Schlüssel, Protokolle, Quellen-Updates, Sprache, Einheiten, Design und Farbe - sind jetzt nur für Administratoren (in Home Assistant ändert sich nichts). Persönliche Einstellungen, Benachrichtigungen und Listengröße bleiben für alle offen. Ein Test deckt es ab.
- Eine GPX-Datei wird jetzt mit dem gehärteten XML-Parser gelesen (wie beim EPUB-Import).
- Der Knopf *Zurück zum Original* beim Design ist wieder weg (er war für Auto-Icons gedacht, die den Papierkorb daneben haben).

## 0.3.514
- **Das App-Icon ist fest, die Autos haben ihr eigenes:** Das Icon der App selbst lässt sich nicht mehr ersetzen - sein farbiger Rahmen folgt der Farbe deines Designs (Klassisch rot behält das originale Rot-zu-Grün). Jedes Auto behält sein eigenes Icon (Logo oder Foto), das denselben Rahmen in den Farben des Designs bekommt; es ist das Auto in *Weiteres* und das Favicon-, iPhone- und Web-App-Icon der Seiten dieses Autos. Ein Icon je Benutzer gibt es nicht.
- Das eigene Icon eines Autos lässt sich in *Einstellungen -> Design -> Icon* wieder entfernen (der Papierkorb daneben): Das Auto trägt dann wieder das Original-Icon.

## 0.3.513
- **Dein eigenes Icon bekommt den farbigen Rahmen:** Ein Logo oder Foto, das du für die App oder ein Auto hochlädst (Einstellungen -> Design -> Icon oder das Icon in *Weiteres*), kommt in den Rahmen des echten Icons - dunkle Kachel, runde Ecken, Rand von Rot nach Grün - und daraus macht die App jede Größe: Browser-Favicon, iPhone-Home-Bildschirm-Icon, Web-App- und Android-Icons. Dasselbe Icon steht in *Weiteres* und überall sonst, ein Auto kann also sein eigenes Markenlogo tragen.

## 0.3.512
- **Ein Klick für Pakete mit Code:** Die Seite eines Pakets mit Dienst, Dateien oder eigener Seite zeigt jetzt *Was dieses Paket tun wird* (Programm, Voraussetzungen, Adressen, auf denen es antwortet, womit es sich verbindet, Dateien) **bevor** etwas installiert wird, und ihr einer Knopf *Ich vertraue ihm - freigeben und installieren* installiert und gibt in einem Zug frei. Danach kommt kein zweiter Schritt. Das kann nur ein Administrator; ein Paket ohne Code behält das einfache *Installieren*. Ein späteres Update, das die Beschreibung ändert, braucht weiter eine neue Freigabe.
- **Erster Start:** Die erste Seite fragt jetzt nach der Sprache **und dem Design** (mit Farbkreis), bevor du auf *Weiter* tippst.
- Die Kachel *Auto* hat jetzt einen neutralen grauen Rand (der alte flackerte zwischen dunklen und hellen Designs).

## 0.3.511
- **Design-Seite:** *Deine Farbe* steht jetzt in der Karte *Farben*, direkt unter den Designs, und erscheint nur, solange *Hell*, *Dunkel* oder *Auto* gewählt ist. Die Designs heißen einfach *Hell*, *Dunkel* und *Auto* (*Klassisch rot* bleibt).

## 0.3.510
- **Weniger, klarere Designs:** *Klassisch rot* bleibt genau, wie es war. Die übrigen Designs (Ozean, Sonnenuntergang, Hellblau, Hell, Tag / Nacht) sind durch drei ersetzt, die deine Farbe nehmen: *Hell + Farbe*, *Dunkel + Farbe* und *Hell / Dunkel + Farbe* (folgt dem Gerät). Ein bisher gewähltes Design wandert zum nächsten und behält seine Farbe (auch je Auto und je Benutzer). Die Dateien eines eigenen Designs im Datenordner funktionieren weiter.

## 0.3.509
- **Fertige Farben:** Die Farbpunkte sind wieder echte Kreise (eine allgemeine Knopfhöhe hatte sie gestreckt) und auf Touch-Geräten (Handy, Tablet) größer. Der Farbkreis selbst geht mit Finger und Maus.

## 0.3.508
- **Deine eigene Farbe:** zwei neue Designs, *Dunkel + Farbe* und *Hell + Farbe*. Wähle eine beliebige Farbe auf einem Farbkreis (oder tippe einen Wert, oder nimm eine fertige): Die ganze App folgt sofort, und die Farbe gilt für alle. Aus der einen Farbe errechnet die App den Farbverlauf der Knöpfe, den hellen Ton für Schrift und die Schriftfarbe auf einem Knopf (weiß oder dunkel, je nachdem, was lesbar bleibt); die Helligkeit bleibt in einem Bereich, der zum Hintergrund passt. Grün, Gelb und Rot für erledigt, bald und überfällig ändern sich nie. Auch die Seiten, die ein Paket zeigt (Frames), übernehmen die Farbe.
- **Plugin-Quellen:** Die geschlossene Karte *Quelle hinzufügen* hatte einen zusätzlichen Streifen unter ihrer Zeile; jetzt ist der Abstand oben und unten gleich.
- In hellen Designs nutzt die letzte Trommel des Kilometerstands die Akzentfarbe mit lesbarer Schriftfarbe.

## 0.3.507
- **Aus der "Connector-API" wird die "Plugin-API"** in allen Texten, Seiten und Docs (die Adresse `/api/v1` und die Datei `docs/api.md` bleiben, damit nichts bricht). Die Seite zu Integrationen sagt jetzt klar: Eine Integration hat keine API und kein Token; nur ein Plugin bindet die Außenwelt an und nutzt die Plugin-API.

## 0.3.506
- **Startseite mit Dokumentations-Übersicht:** Das README listet jetzt jedes Dokument in drei Gruppen (benutzen / Eigenes anbinden / an der App mitbauen) mit je einer Zeile, und `docs/README.de.md` ist dieselbe Liste im Ordner. Englisch und Deutsch bleiben im Gleichschritt; ein Test schlägt an, wenn eine Seite kein deutsches Gegenstück hat oder auf der Startseite fehlt.

## 0.3.505
- **Architektur-Seite** (`docs/architecture.de.md`): drei Diagramme, die GitHub selbst zeichnet - das ganze System, der Weg eines Plugins von draußen bis auf die Seite und Quellen / Pakete / Dienste für Plugins und Integrationen - plus die Schritte, ein eigenes zu bauen.
- **Beispiele:** ein neues Beispiel einer Integration ohne Code (`docs/examples/integration-pages`) und eine Übersichtsseite aller Beispiele; ein Test sorgt dafür, dass jeder relative Link in den Docs und jedes Beispielpaket lesbar bleibt.
- **Hintergrund-Verbindungen geprüft:** Die Arbeitsschleife läuft weiter, wenn ein Job (MQTT-Senden, Erinnerungs-Prüfung) ausfällt; zwei neue Tests belegen das.

## 0.3.504
- **Dokumentations-Reiter des Add-ons neu geschrieben:** erste Schritte, was die App kann, jede Option, wer sie erreicht (Port und Benutzer), MQTT, Datenschutz (was nur online geht, wenn du es einschaltest), Dienste mit fremdem Code, Backup. Jeder Link ist jetzt eine volle Adresse (Home Assistant kann relative nicht öffnen). Doppelte Abschnitte sowie die alten Hinweise auf `external_url` / `access_password` sind weg.
- **Screenshot-Seite** (`docs/screenshots.de.md`, im README verlinkt): die App im Einsatz mit den Demo-Autos, Desktop und Handy, Bilder auf Deutsch und Englisch. Ein Test sorgt dafür, dass Links und Bilder nicht kaputtgehen.

## 0.3.503
- **Fahrzeugpass:** die Einheit stand doppelt (im Namen und im Wert); jetzt nur noch im Wert. Tankgröße und Ölmenge folgen den Einheiten aus *Einstellungen -> Region* (Gallonen bei US / UK).

## 0.3.502
- **Ruhiges Protokoll:** bei der Ausführlichkeit *warning* oder *error* schreibt das Add-on die Zeile „Starting Car Assistant“ nicht mehr. Die wenigen Zeilen des Start-Systems davor (s6) kommen vom Home-Assistant-Basisimage und lassen sich nicht abschalten.

## 0.3.501
- **Roadmap aufgeräumt:** Einheiten, Benachrichtigungen je Benutzer, Erinnerungen von Integrationen und Coding sind als erledigt markiert; was als Nächstes kommt, steht dabei.

## 0.3.500
- **Fahrten:** „Mehr laden“ hängte weitere Fahrten an die Km-Zähler an; behoben. Einen Km-Zähler legst du mit einem Plus in der Überschrift der Zähler an (das Feld öffnet sich direkt darunter); der Textknopf unter der Liste entfällt.

## 0.3.499
- **Fahrten:** Das Hinzufügen-Feld heißt *Fahrt manuell eintragen*, hat mehr Luft darunter und den Speichern-Knopf rechts. Eine Fahrt wird auf Plausibilität geprüft: nicht in der Zukunft, nicht mehr als 3000 je Fahrt, Endzeit nicht vor der Startzeit. Neue Km-Zähler bieten die Art *Steuer* nicht mehr an (bestehende behalten sie).

## 0.3.497
- **Home, erste Schritte:** *Auto verbinden* (ohne Klammertext) öffnet direkt die Plugins des Autos.

## 0.3.496
- **Tanken:** Der Knopf zur Auswertung im Kopf ist entfernt – die Auswertung hat ihren Platz in *Weiteres* (und kann abgeschaltet sein), im Kopf bleiben Export und Hinzufügen.

## 0.3.495
- **Benachrichtigungen nur mit https:** Der Schalter und der Testknopf für Browser-Benachrichtigungen erscheinen nur, wenn die Seite über ihre https-Adresse geöffnet ist; auf jeder anderen Adresse sagt die Karte, wohin man gehen muss (deine externe Adresse), statt etwas anzubieten, das nicht funktioniert.

## 0.3.494
- **Service und Teile:** Ein Zeitraum mit nur einer Karte zeigt sie über die ganze Zeile, statt die rechte Hälfte leer zu lassen.

## 0.3.493
- **Doku:** Die Plugin-Anleitung verweist auf Werkzeuge mit eigener Seite (`kind: "frame"`, auch für Integrationen mit Dienst).

## 0.3.492
- **MQTT-Sensoren in der Home-Assistant-Konfiguration des Add-ons:** *Sensoren in Home Assistant (MQTT)* ist jetzt eine Option unter Einstellungen -> Apps -> Car Assistant -> Konfiguration (einschalten, optional Adresse, Port, Benutzer und Passwort eines eigenen Brokers). Der Schalter in der App funktioniert weiter; was dort eingestellt ist, gilt.

## 0.3.491
- **MQTT-Sensoren in einem Zug einrichten:** Der Schalter *Sensoren in Home Assistant anlegen* ist immer da (Einstellungen -> System), und der erste eigene Broker, den du einträgst, schaltet die Sensoren ein - kein zweiter Besuch, um den Schalter zu finden.
- **Das Speichern der MQTT-Einstellungen schlägt nicht mehr fehl**, wenn der Broker nicht erreichbar ist (beim Ausschalten der Sensoren kam eine Fehlerseite).

## 0.3.490
- **Reifen wie jede andere Liste:** Die Sätze stehen zweispaltig (auf dem Handy einspaltig), ein Tipp auf einen Satz öffnet ihn zum Bearbeiten an Ort und Stelle (*Abbrechen*, *Löschen*, *Speichern* unter einer Linie, rechts), die Angaben passen in die halbe Karte und die Liste lädt in Blöcken mit der gewählten Größe. Reifendruck: eine Zeile je Beladung, links die Überschrift, daneben vorne und hinten.

## 0.3.486
- **Karte antippen = direkt bearbeiten:** Bei Service, Teilen, Terminen, Umbauten und Aufgaben macht ein Tipp auf die Karte aus den Feldern Eingaben; darunter, unter einer Linie, *Abbrechen*, *Löschen* und *Speichern* (rechts). Escape oder *Abbrechen* schließt wieder. Der Knopf *Bearbeiten* entfällt.

## 0.3.484
- **Fahrzeugpass:** Jedes *Speichern* im Bearbeiten-Modus speichert alles Geänderte und fällt zurück in die Ansicht des Passes. Die FIN steht in einer eingravierten Vertiefung - eine ungeteilte Zeile, passend skaliert, mit dem Kopieren-Knopf in der Vertiefung.
- **„Servicebuch" heißt jetzt einfach „Service"** (Reiter, Modul, Seitentitel).

## 0.3.481
- **Seiten von Paketen sind eigene Seiten (kein iframe):** Der Eintrag in *Weiteres* öffnet die Seite des Dienstes des Pakets als ganzes Fenster; Car Assistant setzt nur einen Kopf auf sein HTML – zurück nach *Weiteres*, der Name des Pakets und rechts seine Version (ohne Skript, nicht fixiert, im Design des Autos). Die Seite bekommt Sprache, Auto, Einheiten, Design und die Adressen der Design-Variablen, des Kits und der OpenStreetMap-Kacheln (`/tiles`). Ersetzt das eingebettete Frame aus 0.3.475.

## 0.3.480
- **Fahrten wie in einem Fahrtenbuch:** Eine Fahrtenkarte zeigt nur das Nötigste (Datum und Zeit, Strecke, Kilometer); antippen, und die ganze Fahrt klappt auf – Angaben, Karte, Tempo, Fahrstil, Bearbeiten. Oben drei Zahlen der letzten 30 Tage (Fahrten, Strecke, Fahrzeit).

## 0.3.479
- **Fahrten als Karten:** Jede Fahrt ist eine Karte (zwei Spalten, auf dem Handy eine) unter einer Überschrift je Zeitraum – *Heute*, *Gestern*, *Diese Woche*, *Letzte Woche*, dann der Monat – mit Kategorie, Dauer, Durchschnittstempo, Kilometerstand und Zweck; der Titel einer aufgezeichneten Fahrt öffnet Karte und Fahrstil. Die Suche geht über alle Fahrten, die nächsten laden beim Scrollen nach. Auch die Km-Zähler sind Karten. **Export** (Download-Symbol): alles, letzte 7 / 30 Tage, dieser oder letzter Monat, dieses oder letztes Jahr oder eigene Daten wählen, als PDF oder CSV; der GPX-Import steht ebenfalls dort.

## 0.3.477
- **Eine Integration darf einen Dienst tragen** (für Werkzeuge mit eigener Seite, z. B. einen Editor): dieselbe Freigabe wie beim Dienst eines Plugins, aber kein Token, kein `CA_API_URL` / `CA_API_TOKEN` und keine Connector-API. Ihre `frame`-Seiten und ihr Eintrag in *Weiteres* gibt es nur, solange der Dienst läuft; die Version des Pakets steht rechts im Kopf. Plugins mit Dienst können Frame-Seiten wie bisher zeigen.

## 0.3.476
- **Design-Vertrag:** Eine Seite (`docs/design-contract.de.md`) sagt, was in jedem Design, jeder Seite und jedem Paket gleich bleibt – Identität (Name, Slogan, Farben, Schriften, Logo, Banner), die Variablen, auf die sich alle verlassen können, die Regeln, die ein Design einhalten muss, die Bausteine und Seitenmuster. Tests halten es wahr: Jedes Design hat alle Variablen und ist lesbar (Kontrast 4,5 : 1 für Text, 3 : 1 für Akzent- und Statusfarben). Das Design *Sonnenuntergang* hat auf seinen orangen Buttons jetzt dunklen Text (Weiß war zu blass).

## 0.3.475
- **Frame-Seiten für Pakete mit Dienst:** Ein Paket kann eine Seite seines eigenen Dienstes in der App zeigen (`kind: "frame"`, docs/plugins.de.md): der übliche Kopf mit der Version des Pakets rechts, darunter die Seite, die mit ihrem Inhalt wächst, ein Eintrag in *Weiteres*, solange der Dienst läuft. Die Seite bekommt Sprache, Auto, Einheiten und Design; der Dienst bekommt `X-CA-Vehicle` / `X-CA-User` (keine Cookies), ändernde Anfragen brauchen `X-Requested-With: frame`. Das Design geht als Variablen (`/frame-theme.css`) und als kleines Kit (`/frame-kit.css`) mit, damit so eine Seite zu jedem Design passt. Die Freigabeseite sagt, dass das Paket eine Seite mit eigenem Code mitbringt.

## 0.3.474
- **Listen, ein Weg (Schritt 1):** Jeder wählt unter *Einstellungen → Benutzer → Listen*, wie viele Karten eine Liste auf einmal lädt – 10, 25 oder 50 (mit weniger lädt eine Seite schneller); die nächsten laden beim Scrollen nach. Servicebuch, Teile und Tanken setzen über jeden Zeitraum eine Überschrift (*Heute*, *Gestern*, *Diese Woche*, *Letzte Woche*, dann den Monat) und zeigen ihre Karten in zwei Spalten (auf dem Handy eine).

## 0.3.473
- **Paketseite, übersichtlicher:** Wer und was auf einen Blick (Art, Version, Autor, Quelle als Chips), die Beschreibung als ein Einleitungssatz mit *Mehr lesen* für den Rest, die Einstellungen als Zeilen – Name oben, Hilfetext darunter – mit Überschriften und Hinweisen, wo das Paket sie hat, ebenso die Dateien, und der Installieren-Button rechts.

## 0.3.472
- **Seite Tanken:** Die Tankungen sind wieder Karten (zwei Spalten, auf dem Handy eine) unter einer Überschrift je Monat, jeweils zehn – die nächsten zehn laden beim Scrollen nach; die Suche geht über alle. **Export** (das Download-Symbol): wählen, was exportiert wird – alles, letzte 7 oder 30 Tage, dieser oder letzter Monat, dieses oder letztes Jahr oder eigene Daten – als CSV oder PDF.

## 0.3.471
- **Kompaktere Karten:** Die dünne Trennlinie und der *Bearbeiten*-Button bleiben unten rechts, aber mit weniger Platz drumherum (etwa 14 px weniger Höhe je Karte).
- **Buttons heben sich besser ab:** Jeder Button und Icon-Button hat eine klarere Kante (neuer Design-Wert `--btn-edge`), die kleinen Icons in den Listen zeigen sie dauerhaft; das Icon ist weiß statt grau. Das *Bearbeiten* einer Karte ist ein richtiger kleiner Button, rechts am Kartenrand.
- **Kleine Icon-Buttons** (Stift und Kreuz in den Listen) zeigen dauerhaft Kontur und Fläche wie die anderen Buttons, nicht erst beim Berühren.
- **Bearbeiten:** Unter jeder Karte (Termine, Service, Teile, Reifen, Zusatzarbeiten) steht hinter dem Stift wieder das Wort *Bearbeiten* – ein einzelner Stift ging unter. Die kleinen Zeilen der Listen (Tanken, Umbauten, Fahrten) behalten nur den Stift.

## 0.3.464
- **Termine:** Der *.ics*-Button ist ein Export-Symbol (Pfeil nach unten, rund wie die anderen Icon-Buttons); die Beschriftung bleibt für Screenreader.

## 0.3.463
- **Zusatzarbeiten und Listenkarten (Design-Schritt):** Die Karten jeder Liste (Termine, Service, Teile, Zusatzarbeiten) haben denselben Innenabstand (18 px) und denselben Abstand (14 px) wie alle anderen Karten; die Zeile zum *Zurücksetzen* einer Arbeit hat ein kurzes festes Feld für den Kilometerstand und einen Stift zum Bearbeiten (wie jeder andere Eintrag) statt drei Punkten.

## 0.3.462
- **Seite Dokumente neu gebaut:** Statt einer Tabelle mit roten *Löschen*-Buttons eine Karte mit einer Zeile je Dokument – farbiger Chip für die Kategorie (Handbuch, Rechnung, Versicherung, Fahrzeugschein, Prüfbericht, Sonstiges), darunter Titel mit Kategorie, Datum und Größe, ein Löschen-Icon. Hochladen ist ein Button: Titel und Kategorie eintragen, Datei wählen, sie wird sofort hochgeladen. Leerer Zustand wie auf den anderen Seiten.

## 0.3.460
- **CSS aufgeräumt (Design-Schritt 3, Teil 2):** Ungenutzte Style-Regeln (etwa 50 Selektoren entfernter Funktionen wie dem alten Auto-Menü, Quellenzeilen und dem Ausstattungs-Kategorie-Editor) sind weg, benachbarte Regeln desselben Selektors sind zusammengeführt und 13 spätere Regeln in ihren früheren Zwilling verschoben – nachweislich ohne ein Ergebnis zu ändern. Geprüft durch Rendern von 26 Seiten in zwei Breiten (28.000 Elemente) vorher und nachher: kein Unterschied. `tools/css_tidy.py` erledigt den mechanischen Teil.

## 0.3.459
- **Eine abgeschaltete Funktion ist wirklich aus:** Sie löst keine Hinweise und Benachrichtigungen aus, zeigt nichts auf Home (HU, Reifen, nächster Service), legt keine Sensoren in Home Assistant an, und ihre Abfragen entfallen. Die Daten bleiben und sind wieder da, wenn du die Funktion einschaltest.

## 0.3.458
- **Home mit nur einem Namen:** Ohne Kennzeichen und Modellzeile bleibt deren Platz frei, Name, Auto und Kilometerstand sitzen also genau wie mit allen Angaben (vorher klebte das Auto am Namen).

## 0.3.456
- Einrichtung, Schritt 3: Die Einleitung sagt, was jetzt gilt – die empfohlenen Funktionen sind an, die anderen schaltest du bei Bedarf ein, jederzeit unter Weiteres → Integrationen (Englisch und Deutsch).

## 0.3.455
- **Einrichtung, Schritt 3:** Wieder eine Liste, ohne die Überschriften *Empfohlen* / *Bei Bedarf*: Die Funktionen, die die meisten brauchen, stehen oben und sind an, die anderen folgen darunter mit ausgeschalteten Schaltern.

## 0.3.454
- **Ein neues Auto startet mit dem, was die meisten brauchen:** Servicebuch, Termine, Tanken, Dokumente, Sicherheit und Auswertung sind an; Zusatzarbeiten, Reifen, Umbauten, Teile, Km-Zähler, Fahrten, Handbuch und Tankstellen sind aus, bis du sie brauchst (Weiteres → Integrationen, oder Schritt 3 der Einrichtung, der jetzt zwei Gruppen zeigt: *Empfohlen* und *Bei Bedarf*). Die Demo-Autos haben immer alles an.

## 0.3.453
- Schritt 3: Der Hinweis, dass sich die Funktionen später ändern lassen, steht jetzt in der Einleitungskarte oben; die Button-Zeile hat nur *Zurück* und *Weiter*.

## 0.3.452
- Schritt 3: Der Einleitungstext ist kurz und steht in einer Karte mit Info-Icon; der Hinweis neben den Buttons ist ebenfalls kürzer.
- **Buttons der Einrichtung:** Unter jedem Schritt steht *Zurück* links und die eine Haupt-Aktion (*Weiter* / *Speichern*) rechts, immer in einer Zeile; in Schritt 3 steht der Hinweis zum späteren Umschalten der Funktionen dazwischen (auf dem Handy über den Buttons).

## 0.3.450
- **Einrichtung, Schritt 3:** Auf einem breiten Bildschirm läuft die Liste der Funktionen in zwei Spalten.

## 0.3.449
- **Einrichtung, Schritt 3 (*Was braucht dieses Auto?*):** Jede Zeile ist wieder eine Zeile – Icon, Name mit kurzem Text, Schalter – statt mittig gestapelt und in Großbuchstaben.

## 0.3.448
- **Navigationsleiste (Handy und Tablet):** Beim Seitenwechsel war das Icon der neuen Seite kurz hellrot und wurde dann dunkelrot. Der gleitende Marker ist beim Wechsel eine eigene Ebene und lag über den Icons; jetzt ist jeder Eintrag der Leiste eine Ebene über dem Marker, das Icon hat die ganze Zeit dasselbe Rot.

## 0.3.447
- Intern: Eine lokale Sicherungsdatei der Einstellungen wird nicht mehr verfolgt und ist ausgeschlossen.

## 0.3.446
- **Navigation:** Das Icon der aktiven Seite blendet beim Wechsel nicht mehr von Grau über Hellrot zu Dunkelrot ein – es ist vom ersten Bild an im Akzent-Rot.
- **Icon-Buttons (Design-Schritt 4):** Wo ein Icon alles sagt, zeigt der Button nur das Icon – Löschen (Mülleimer), Speichern (Haken), Abbrechen (Kreuz), Zeile hinzufügen (+) und der Stift unter jeder Karte. Der Text bleibt für Screenreader erhalten, es gibt keine Hover-Tooltips. Die Texte der einen Haupt-Aktion und wichtiger Löschungen (Auto, Benutzer) bleiben.

## 0.3.444
- Intern: Das CSS-Hilfsprogramm besteht die Prüfung.

## 0.3.443
- **Fahrzeugpass:** Die gewählte Fahrzeugpass-Zeile in der Liste Weiteres ist nicht mehr rot, sondern wie jede andere gewählte Zeile markiert (hellerer Hintergrund).
- **CSS aufgeräumt (Design-Schritt 3, Teil 1):** 181 wirkungslose Angaben und 35 leere Regeln entfernt (eine spätere Regel desselben Selektors überschrieb sie immer), Farben, die als Hex-Wert in Regeln standen, kommen jetzt aus Tokens (`--on-dark`, `--black`, `--on-ok`, `--retro`, die Jahreszeit-Farben), an keiner Seite ändert sich etwas. Neues Hilfsprogramm `tools/css_tidy.py`.

## 0.3.441
- Die Auto-Zeichnung eines neuen Autos (noch ohne Foto) hält auf Home Abstand zu Name und Modellzeile.
- **Seitenaufbau (Design-Schritt 2):** Jeder Seitenkopf hat jetzt dieselbe Höhe (Titelzeile plus Zeile für den Autonamen), der Inhalt beginnt also auf jeder Seite auf derselben Linie – auch auf den Einstellungs-Seiten. Karten der Listen (Termine, Service, Teile …) nutzen denselben Abstand wie der Rest und halten *Bearbeiten* auf der untersten Linie. Die runden Icon-Buttons (Zurück, Plus, Wechseln …) haben denselben Glas-Look wie die anderen Buttons.

## 0.3.439
- **Ein Glas-Button überall (Design-Schritt 1):** Jeder Button – Speichern, Hinzufügen, Bearbeiten, Löschen, Links und Dateiauswahl – hat jetzt denselben durchscheinenden Glas-Look mit heller Kante: 44 px, oder `small` 36 px. Die eine Hauptaktion ist rotes Glas, Löschen ein roter Rand. Es werden nur Design-Werte benutzt, deshalb färben alle Designs (dunkel, hell, Frost, Ozean, Sonnenuntergang und eigene Theme-Dateien) die Buttons um; helle Designs bekommen eine hellere Kante.

## 0.3.438
- **Reifen: die frühere Ansicht ist zurück** (Karte „Empfohlener Reifendruck“ mit Reiter je Jahreszeit, eine Karte je Satz), mit den neueren Funktionen darin: Luftdruck voll beladen, eine eigene Hinterachse (Größe und Name) und die Hinterachse auf der Satz-Karte.

## 0.3.436
- **MQTT-Sensoren überarbeitet:** weiter standardmäßig aus, und der Schalter erscheint nur, wenn ein Broker gefunden ist (der von Home Assistant oder dein eigener). Eingeschaltet wird ein Auto zum Gerät mit deutlich mehr Sensoren – Zündung, Verriegelung, Türen, Fenster, Reifendruck, Batterie, Laden, Temperaturen, AdBlue, Service –, angelegt erst, wenn ein Plugin den Wert liefert; selten nützliche starten ausgeschaltet oder als Diagnose.
- **GPS-Position in Home Assistant:** Das Auto erscheint als Geräte-Tracker auf der Karte (mit Geschwindigkeit, Richtung und Zeit der Position).
- Nichts wird doppelt gesendet (nur Änderungen), *Sensoren neu senden* schickt alles noch einmal, und beim Ausschalten verschwinden die Sensoren wieder aus Home Assistant.

## 0.3.435
- **README-Einleitung neu formuliert:** sagt, was die App besonders macht – alle Dokumente und Daten eines Fahrzeugs an einem Ort, auch die Daten des Autos selbst.

## 0.3.434
- **Add-on-Logo:** *Car Assistant* in einer Zeile wie im Banner, darunter der grüne Slogan, der ganze Block senkrecht mittig zum Symbol.

## 0.3.433
- **Original-Logo in der Navigation:** Die Seitenleiste zeigt immer das Standard-Logo mit dem Slogan, nie das Symbol oder den Namen eines Autos. Das Auto (mit eigenem Symbol) gibt es nur in der Liste *Weiteres*.
- **Neues Banner und Add-on-Logo:** *DRIVE · LOG · GO* steht in der Schrift der App unter dem Namen, genau vom C bis zum t von *Car Assistant* gespannt; dasselbe Layout im README-Banner und im Home-Assistant-Logo.

## 0.3.432
- **Dokumentation auf den neuesten Stand gebracht:** Add-on-Beschreibung (keine Wiederherstellungscodes mehr, Km-Zähler und Tankstellen auf ihren Seiten), Plugin-Doku (die *Protokolle*-Seite jedes Plugins), das Fahrzeugdatei-Format (Ausstattung, Handbuch, Luftdruck voll beladen, Hinterachse).
- **Demo-Autos** (nur sie) bekommen ein eigenes Icon: das Bild des Demo-Autos auf dunkler Kachel (1024 px, die größtmögliche Icon-Größe, das Bild in seiner eigenen Pixelgröße), unter *Weiteres*, auf dem Home-Bildschirm und in den Listen.
- **Demo-Autos:** beide Demo-Autos (und die eingebaute Demo) haben erfundene Ausstattung in allen zwölf Bereichen mit jedem Status (Serie, Sonder, nachgerüstet, nicht verbaut), Codes und Notizen, dazu Luftdruck voll beladen und eine eigene Hinterachse.
- **Dokumentation:** das Benutzerhandbuch beschreibt die neuen Seiten, die Plugin-Doku beschreibt Seiten im Detail, Erinnerungen und Pläne; README und Roadmap sind aktuell.
- **Widgets der Startseite:** *Aufmerksamkeit*, *Fahrzeugdaten* und *Standort* sind jetzt immer eine ganze Zeile und lassen sich nicht mehr verkleinern (kein Größen-Griff); die Demo-Autos folgen dem.
- **Pläne für Erinnerungen (Additiv-Plan):** eine Erinnerung kann einen Wechsel tragen (zum Beispiel sauber – Additiv 1 – sauber – Additiv 2), der mit jeder Tankung weiterrückt; seine eigene Seite zeigt die nächste Tankung, den Wechsel, *Plan korrigieren* und den Verlauf mit *eingefüllt / nicht eingefüllt*. Die Erinnerung kann warten, bis die Reichweite knapp wird.
- **Integrationsseiten (Coding) wie im Original:** jeder Eintrag ist eine aufklappbare Zeile mit kurzem Code-Zeichen, Name, Untertitel und der Zahl geänderter Bytes; innen die Teilenummern, Notizen, das Byte-Raster (Original / aktuell, geänderte Bytes markiert, Byte antippen für seine Bits), der neue Wert und die Notizen zum Bearbeiten direkt dort, *Speichern* und *Neu = Original*; die übrigen Daten hinter *Daten bearbeiten*. Suche und *Nur geänderte* stehen oben.
- **Handbuch:** eine neue Seite *Handbuch* für jedes Auto: importiere eine PDF (mit Textebene), eine EPUB- oder eine Text- / Markdown-Datei; Kapitel gruppiert wie im Original, eine Suche mit markierten Treffern auf der Seite, „Weiterlesen“, antippbare „Seite 137“-Verweise und ein **EPUB-Export**. Die Datei bleibt auf deinem Server.
- **Zusatzarbeiten (früher Wartung) wie im Original:** oben der aktuelle Kilometerstand mit Status, je Arbeit eine Karte (Icon, Intervall, Fortschrittsbalken, zuletzt / nächste, ein Kilometerfeld mit *Zurücksetzen*, ein Menü zum Bearbeiten) und ein Knopf, der vorgegebene Arbeiten mit Richtwerten hinzufügt. *Wartung* heißt jetzt überall *Zusatzarbeiten*.
- **Reifen wie im Original:** eine Karte je Reifensatz (*Jetzt montiert* oder ein Knopf *Montieren*, ein Stift), der Luftdruck als große Kacheln für normale Nutzung und voll beladen (vorne / hinten), die Größen von Vorder- und Hinterachse (eine eigene Hinterachse ist möglich), Notizen. Der Stift öffnet die Satzdaten und den Luftdruck.
- **Umbauten wie im Original:** oben eine Schnell-Eingabe (*z. B. Dashcam eingebaut* + *Hinzufügen*), darunter eine schlichte Liste mit Punkt, Stift (Datum, Kilometerstand, Kosten, Notiz bearbeiten) und Kreuz (Löschen) je Eintrag, dazu eine Suche.
- **Protokolle je Plugin:** der Eintrag *Protokolle* unter Weiteres entfällt. Jedes Plugin und jede Integration hat eine eigene, einfache Protokollseite (Knopf *Protokolle* auf ihrer Karte): der Schalter für mehr Details, nur SEINE Zeilen, die Aufrufe (eingeklappt) und *Leeren*. Die alte gemeinsame Seite führt zu den Plugins.
- **Tanken + Tankstellen auf einer Seite:** *Tanken* enthält jetzt oben die Tankstellensuche (zugeklappt) und darunter die Tankungen, nach Monaten in aufklappbaren Bereichen gruppiert, mit schmalen Zeilen, Suche, einem Stift je Tankung (Bearbeiten, Löschen) und einem **+** zum Hinzufügen. Die eigene Seite *Tankstellen* entfällt (die alte Adresse führt hierher).
- **Fahrtenkarte wie im Original:** oben Uhrzeit und ein *Route*-Zeichen, die Strecke groß mit Dauer / Ø Tempo / Spitze, Verbrauchs-Chips (eine Schätzung aus Durchschnitt und Preis des Autos), die Routenkarte mit ihrer Punktezeile, die Kacheln *Fahrstil* (Beschleunigen, Bremsen mit kräftigen Bremsungen, Ø in Bewegung, Standzeit) aus den aufgezeichneten Positionen und der GPX-Download. Ohne aufgezeichnete Positionen kommen Dauer und Ø aus den eingetragenen Zeiten.
- **Fahrtenkarte:** tippe auf eine Fahrt, und ihre Karte öffnet sich – die Strecke groß, Dauer, Ø Tempo und Spitze sowie die Route auf der Karte, nach Tempo eingefärbt (Blau langsam bis Rot ab 130 km/h; ohne Karte gezeichnet, wenn Online-Karten aus sind), dazu der GPX-Download.
- **Fahrten + Km-Zähler auf einer Seite:** *Fahrten* enthält jetzt oben die Km-Zähler (Zeilen mit gefahrener Strecke, Bearbeiten, Hinzufügen, Löschen) und darunter die Fahrten, nach Monaten in aufklappbaren Bereichen gruppiert, mit schmalen Zeilen, Suche, einem Stift je Fahrt (Bearbeiten, Löschen) und einem **+**, um eine Fahrt von Hand nachzutragen. Export (PDF / CSV) und GPX-Import stehen in einem zugeklappten Bereich am Ende. Die eigene Seite *Km-Zähler* entfällt.
- **Fahrzeugkarte in Weiteres:** der Wechseln-Knopf erscheint nur noch, wenn es mehr als ein Auto gibt.
- **Kopf des Fahrzeugpasses:** oben Name, Kennzeichen und *Marke Modell Variante*, darunter eine Reihe Chips mit Baujahr, Kraftstoff, Leistung, Getriebe und Kilometerstand, dann die FIN. Diese Werte wiederholen sich nicht mehr als Kacheln in den Gruppen darunter.
- **Fahrzeugpass:** leere Felder werden nicht mehr als „–“-Kacheln gezeigt (nur was du eingetragen hast), die Schlüsselnummern sind aus dem Pass raus (bleiben im Formular), und die Gitterlinien sind sauber gezeichnet – eine Kachel, die allein steht, läuft über die volle Breite.
- **Fahrzeugpass:** ein gleichmäßiger Rhythmus - jeder Block beginnt 20 px unter dem vorigen, jede Überschrift sitzt 8 px über ihrem Inhalt.
- **Ausstattung:** die Überschrift ist bündig mit den anderen und zeigt die Anzahl der Merkmale daneben; die extra Zählzeile entfällt.
- **Fahrzeugpass:** *Notizen* stehen über der Ausstattung. Im Fahrzeugformular sind *Sichern* und *Verwalten* eine aufgeräumte Karte (Sicherung, Archivieren, Löschen als Zeilen mit kurzem Text und leichtem Knopf); der Archiv-Knopf heißt wieder *Wieder aktivieren*.
- **Ausstattung:** die Bereiche (Komfort, Sitze, Bedienelemente, Licht, Linien & Pakete, Interieur, Räder & Reifen, Technik & Sicherheit, Exterieur, Infotainment, Assistenzsysteme, Verglasung & Dach - zwölf, in jeder Sprache übersetzt) sind für jedes Auto derselbe feste Satz und immer da; sie lassen sich nur nach oben und unten sortieren (Pfeil-Knöpfe im Bereich). Niemand muss Bereiche anlegen oder bearbeiten, und es gibt keine fertige Merkmalsliste: jeder trägt seine Merkmale je Bereich selbst ein.
- **Knöpfe:** Nebenaktionen sind überall leichte, umrandete Knöpfe (Löschen rot umrandet, kein gefüllter Block), Knopfreihen bleiben einzeilig; nur die eine Hauptaktion einer Seite ist ein gefüllter Hauptknopf.
- **Ausstattung:** jeder Bereich hat *Merkmal hinzufügen*, ein **+** neben der Überschrift legt einen Bereich an; entfernt wird ein Merkmal im Bearbeiten-Formular. Die Chips *Nächste HU* und *Wartung* im Dashboard haben Icons bekommen, sie sind wie die oberen Chips aufgebaut (links links, rechts rechts, Icon in der Statusfarbe).
- **Fahrzeugpass:** ein Wert, der allein links steht (z. B. der Kilometerstand), läuft jetzt über die volle Breite; die Ausstattungszeilen sind schmaler.
- **Ausstattung wie im Original neu gebaut:** oben Suchfeld und Zähler, jeder Bereich ist eine zugeklappte Zeile (Icon, Name, *n von m*), die sich zu den Gruppen *Serie / Sonderausstattung / Nachgerüstet / Nicht verbaut* mit grünen, blauen und roten Zeichen öffnet. Jedes Merkmal hat rechts einen eigenen Bearbeiten-Knopf (Text, Code, Status und die Kategorie, in die es gehört - das verschiebt es). Die Legende steht unten in einer Zeile.
- **Fahrzeugkarte in Weiteres** ist jetzt EIN Block mit der Liste: das eigene Icon des Autos (das Home-Bildschirm-Icon dieses Autos, etwas größer) mit Name und Wechseln-Knopf oben, der Fahrzeugpass als zweite Zeile unter dem Namen (keine eigene Zeile), dann die Seiten. Tippe auf das Icon, um ein eigenes Bild für dieses Auto hochzuladen (mittig und vollflächig quadratisch zugeschnitten).

## 0.3.359
- **Fahrzeugpass:** die Fahrzeugkarte in *Weiteres* (und der Seitenliste) zeigt oben den Namen mit einem *Wechseln*-Knopf (bei nur einem Auto führt er zur Fahrzeugliste) und darunter den **Fahrzeugpass** als Zeile wie alle anderen; das Icon ist ein Auto von vorne. Dieselbe feste erste Zeile steht in *Navigation verwalten*. Die FIN steht oben im Fahrzeugpass mit Kopierknopf. Neue Liste **Ausstattungsmerkmale** (Kategorien mit Icon, Status Serie / Sonder / Nachgerüstet / Nicht verbaut mit grünem, blauem und rotem Zeichen, optionaler Code wie eine PR-Nummer, eine neutrale Startliste, Bearbeiten je Kategorie). Die Seiten-Icons in *Navigation verwalten* sehen jetzt exakt aus wie in *Weiteres*.

## 0.3.356
- **Navigation:** die erste Karte eines Autos unter *Weiteres* ist jetzt eine feste zweizeilige Karte: oben Fahrzeugname und Kennzeichen, darunter der **Fahrzeugpass** (früher *Fahrzeugdaten*). *Navigation verwalten* enthält jetzt den Ein-/Aus-Schalter jeder Seite und jeder Integration (die eigene Karte *Integrationen* entfällt); ausgeschaltete Seiten bleiben gelistet. Die Seiten-Icons sind farbige Glaskacheln, überall gleich.
- *Einstellungen > System* ist am Handy wieder einspaltig. *Meine Vorlieben* heißt jetzt *Persönliche Einstellungen*.

## 0.3.355
- **System-Seite aufgeräumt:** die Port-Zeile ist kurz (*Port: Aus / An, durch Benutzer geschützt*), die lange Anleitung „Wie mache ich es von außen erreichbar?“ ist weg (sie steht in der Doku; **Über → Hilfe** öffnet sie auf GitHub). Passkeys und Web-Push sind ausgegraut mit *Die externe URL muss gesetzt werden.*, bis eine externe URL existiert.
- **Eigenes Symbol:** jedes Bild (PNG, JPEG, WebP, GIF, BMP, TIFF) wird auf ein Quadrat aufgefüllt, ohne Beschnitt und ohne Verzerrung.
- *Fahrzeug aus einer Sicherung wiederherstellen* steht jetzt am Ende der Fahrzeugliste.
- Das eigene Design eines Autos gilt jetzt auch auf seiner *Mehr*-Seite.

## 0.3.354
- **Einstellungen → Benutzer neu gestaltet** im eigenen Look der App: eine kompakte Karte je Thema, Zeilen mit kleinem *Ändern*-Knopf statt Klappfeilen, die Abmelde-Knöpfe am Ende. Wiederherstellungscodes entfallen (ein vergessenes Passwort wird im Home-Assistant-Panel neu gesetzt). Der erklärende Text ist kurz und verschwindet, wenn du die Seite schon über den Port nutzt. Bei gesetztem Port liegen Status, Adresse und Sperr-Regeln, Design und Tipp-Rückmeldung unter Benutzer, ohne Port bleiben sie unter System. Checkboxen sind in der Farbe des Designs gezeichnet.

## 0.3.351
- *Einstellungen → Benutzer*: Der Status behauptet nicht mehr, der Direktzugriff sei aktiv, wenn kein Port gesetzt ist. Ohne Port steht dort, dass Car Assistant nur über Home Assistant erreichbar ist und der Login gilt, sobald ein Port gesetzt ist.

## 0.3.350
- Die Adresse des eingebauten Icons ändert sich mit jeder App-Version, damit ein Handy (und jeder Zwischenspeicher) nach einem Update das neue Icon holt statt das alte zu behalten.

## 0.3.349
- iPhone-Icon: Der Ring folgt jetzt genau der glatten Form, die iOS aus einem Home-Bildschirm-Icon ausschneidet; er ist überall gleich dick, die Ecken passen perfekt. (Alten Home-Bildschirm-Link löschen und neu setzen: iOS behält sonst das alte Icon.)

## 0.3.348
- **Das System und jedes Auto sind eigene Web-Apps:** Das Manifest jedes Autos hat eigenen Namen, eigenes Icon, eigene Farben (sein Design) und einen Geltungsbereich, der an den Seiten dieses Autos endet; so kann jedes Auto einzeln auf den iPhone-Home-Bildschirm. Innerhalb eines Autos oder des Systems wechseln die Seiten sofort; ein anderes Auto oder das System ist eine eigene Seite.

## 0.3.347
- **Icons für ein Handy, das nicht angemeldet ist:** Die zwei Adressen, die iOS von sich aus abfragt (`/apple-touch-icon.png`, `/apple-touch-icon-precomposed.png`), lagen hinter der Anmeldung, und die „Gesperrt“-Seite (Port gesetzt, noch kein Benutzer) nannte gar kein Icon. Beides behoben: Icons werden ohne Anmeldung geliefert (sie verraten nichts über die Autos) und jede Seite nennt sie. Die Seiten eines Autos nehmen weiter das eigene hochgeladene Icon dieses Autos.

## 0.3.346
- Anmelde-Sperre: Die Meldung nennt jetzt die echten Minuten aus der Einstellung (bei Passkey und Passwort-Wiederherstellung stand immer 15). Der Passkey-Ablauf (registrieren, anmelden, wiederholte oder gefälschte Antworten abgelehnt) ist mit einem Software-Authenticator getestet.

## 0.3.345
- **Neue App-Icons im neuen Look für jedes Gerät:** Der iPhone-Home-Bildschirm bekommt ein volles Quadrat (iOS rundet selbst ab, keine schwarzen Ecken), Android ein maskierbares Icon in der Sicherheitszone, Browser-Tabs ein scharfes SVG-Favicon. Jede Größe hat dieselbe Kontur und denselben Abstand zwischen Auto und Kontur. Eigene hochgeladene Icons funktionieren weiter (auch als maskierbar).

## 0.3.344
- Der Slogan „Drive · Log · Go“ steht überall im Grün der App (Seitenleiste, Über, Anmeldung, Sperrseite).

## 0.3.343
- Die Anmeldeseite hat denselben Look: sanftes Rot-Grün-Licht, Glaskarte, das Logo mit den bewegten Linien.

## 0.3.342
- Die Seite, die bei einem Direktaufruf ohne Benutzer erscheint, ist jetzt gestaltet: Logo mit den bewegten Linien, sanfter Rot-Grün-Verlauf, ein klares „Gesperrt“-Schild. Sie braucht keine Datei der App.

## 0.3.341
- Nirgends wird mehr ein Port vorgeschlagen (weder 8321 noch 8099): Die Texte sagen, dass jeder einen beliebigen freien Port in Home Assistant wählt.

## 0.3.340
- README (Englisch und Deutsch) auf den neuesten Stand gebracht: Plugins als Anbindung nach außen, Quellen und Plugin-Dienste, Reifendruck, Sicherungen, Demo, Port- und Benutzerregel, Link zur Plugin-Anleitung.

## 0.3.339
- Über-Seite: mehr Effekte - sehr feine Linien mit leuchtenden Rot-zu-Grün-Lichtstreifen, die zum Auto laufen, ein langsam atmendes Glühen dahinter und ein Glanz, der über den Ring gleitet (alles aus bei reduzierter Bewegung).

## 0.3.338
- Das Auto im Logo links oben ist wieder etwas kleiner (wie vorher).

## 0.3.337
- Über-Seite: Das Logo ist genau so breit wie der Name darunter; die Linien hinter dem Auto sind dünne Farbverläufe (Rot zu Grün), die ganz hinter dem Auto verschwinden, mit einem sanften Licht, das an ihnen entlangläuft.

## 0.3.336
- **Neues Logo als echte Vektorgrafik** (das Auto neu gezeichnet nach dem großen Original: scharf in jeder Größe): in der Seitenleiste und auf der Über-Seite, dort groß mit leichten rot-grünen Signalen, die hinter dem Auto an den Linien entlanglaufen (animiert, ausgeschaltet bei reduzierter Bewegung). GitHub-Logo, Add-on-Icon und Titelbild folgen demselben Look; `docs/logo.svg` ist die Quelle.

## 0.3.335
- Das Demo-Plugin der Standardquelle wird in der Plugin-Liste nicht mehr zur Auswahl angeboten (es gehört nur zu den beiden Demo-Autos, die es weiter selbst installieren). Die Demo-Autos haben jetzt alle Fahrzeugfelder gefüllt und empfohlene Reifendrücke.

## 0.3.334
- Die beiden Demo-Autos (Diesel, Elektro) starten mit lauter kleinen Home-Widgets. `tools/make_demo_vehicles.py` baut sie so.

## 0.3.333
- Die Logo-Kachel links oben hat mehr Kontur (der Ring wächst nach innen, die Größe bleibt gleich). Die Liste neben der Seite (*Weiteres*) zeigt keinen eigenen Zurück-Pfeil mehr.

## 0.3.332
- Die Hinweise unter *Einstellungen → System* sprechen nicht mehr von den entfernten App-Optionen (Option für die externe Adresse, Standard-Port 8321).

## 0.3.331
- **Sofortige Seitenwechsel:** Ein Klick auf einen Link der App lädt die nächste Seite im Hintergrund und tauscht sie ohne Neuladen des Browsers ein (nichts blitzt, Styles und Skripte bleiben geladen; der Browser blendet zwischen den Seiten über). Formulare, Downloads und die Anmeldung bleiben normale Seitenaufrufe. Jede Antwort trägt außerdem einen `Server-Timing`-Header, damit der Netzwerk-Tab des Browsers zeigt, wie lange die App selbst brauchte.

## 0.3.330
- **Schnellere Seiten:** Einstellungen werden einmal gelesen und kurz gemerkt (eine Seite öffnete etwa 30 Datenbankverbindungen, jetzt etwa 5), der Datenbankmodus wird einmal statt bei jeder Verbindung gesetzt. Auf breiten Bildschirmen entfällt der einfache Zurück-Pfeil zu *Weiteres*, weil die Liste neben der Seite steht.

## 0.3.329
- Auch die letzten Reste der entfernten App-Optionen (Benachrichtigungsdienst, Sprache, externe Adresse, MQTT-Schalter) sind aus dem Code raus; alles wird in der App eingestellt.

## 0.3.328
- **Konfiguration in Home Assistant: nur noch die Log-Stufe.** Sprache, Erinnerungen aufs Handy, MQTT-Sensoren und die externe Adresse stellst du in der App ein (Einstellungen / Integrationen), die Optionen entfallen. MQTT-Sensoren sind aus, bis du sie einschaltest.

## 0.3.327
- **Reifen:** Empfohlene Reifendrücke je Saison (Tabs Sommer / Winter / Ganzjahr, Vorder- und Hinterachse, änderbar); darunter die zuletzt vom Auto gemeldeten Drücke, wenn ein Plugin sie liefert (bis dahin ein roter Strich). Die Kachel „Eingelagert bei“ entfällt, wenn sie leer ist. In der Fahrzeug-Sicherung enthalten.

## 0.3.326
- **Seiten laden in Home Assistant schneller:** Die Antworten von Home Assistant und dem Supervisor (Währung und Land, eingestellter Port, Liste der Entitäten) werden kurz gemerkt, statt bei jedem Seitenaufruf neu abgefragt zu werden.

## 0.3.325
- **Konfiguration vereinfacht:** Die Option *Wer darf den Port öffnen* entfällt. Der Port ist standardmäßig leer; trage einen ein (Vorschlag 8321), um die Webseite von außen zu erreichen - das geht nur mit Benutzer (Name und Passwort). Standardwerte sind jetzt leer/aus, Log-Stufe `error`.

## 0.3.324
- `tools/check_plugin.py` läuft wieder mit einfachem Python (die Verschlüsselungs-Bibliothek wird nur geladen, wenn wirklich ein Geheimnis gespeichert wird).

## 0.3.323
- **Die Konfiguration in Home Assistant ist aufgeräumt:** Die Option für das alte gemeinsame Passwort ist weg (ein direkter Besuch braucht einen Benutzer der App, sonst nichts); die übrigen Optionen haben kurze, einfache Namen und Beschreibungen auf Deutsch und Englisch. Direktzugriff ganz ohne Benutzer zeigt die Seite, die es erklärt.

## 0.3.322
- **Werte-Kacheln auf Home:** Ein Plugin oder eine Integration kann kleine Kacheln auf die Home-Seite legen (`tiles` in `plugin.json`): Der Wert kommt aus einem gelieferten Rohsignal oder einer Standardzahl der API, mit Einheit und Nachkommastellen. Eine Kachel erscheint nur, solange das Plugin läuft und ein Wert da ist; sie lässt sich wie jedes Widget verschieben, in der Größe ändern und ausblenden.

## 0.3.321
- **Geheimnisse liegen verschlüsselt in der Datenbank:** Die Passwörter in den Einstellungen eines Plugins und der Zugangsschlüssel einer Quelle werden verschlüsselt gespeichert (Schlüssel in `secret.key` im Datenordner, nur für die App lesbar, nicht Teil einer Sicherung). Alte Klartext-Werte werden weiter gelesen und beim nächsten Speichern verschlüsselt.
- **Menüpunkt *Protokolle*** unter *Mehr* führt zur Seite mit Protokollen, Verkehr und Debug des Autos.
- Die öffentlichen Pakete (Coding, Webradio, Kraftstoff-Additiv) haben jetzt Icon, Beschreibungstext und Schnittstellen (Versionen in der Quellen-Repository erhöht).

## 0.3.320
- **Wer den Port öffnen darf:** Eine neue Add-on-Option *Wer darf den Port öffnen* - `home_assistant` (nur über das Home-Assistant-Panel), `home_network` (auch direkt aus deinem eigenen Netz, VPN-Bereiche eingeschlossen) oder `everywhere` (auch das Internet); Standard `everywhere`. Ein Benutzer muss sich immer anmelden, und ohne Benutzer bleibt der Direktzugriff gesperrt. Home Assistant kann einen Port nicht „nur ins Heimnetz“ veröffentlichen, deshalb schaut die App auf die Adresse, von der eine Verbindung kommt; hinter einem Reverse-Proxy oder Tunnel liest sie auch die weitergegebenen Adressen und zählt eine Anfrage als Internet, wenn eine davon öffentlich ist. Eine abgelehnte direkte Verbindung bekommt jetzt eine freundliche Seite, die sagt, warum, statt einer nackten Zeile. *Einstellungen → System* zeigt den Modus.
- **Die Konfiguration in Home Assistant ist verständlicher:** Die Optionen stehen in sinnvoller Reihenfolge mit klaren Namen und Beschreibungen (Deutsch und Englisch), das alte gemeinsame Passwort ist als solches gekennzeichnet, der Port hat eine Erklärung.

## 0.3.319
- **Dateien eines Pakets:** Ein Paket darf geprüfte Binärdateien mitbringen (`files`: `.jar .zip .bin .json .txt .md .pdf`, höchstens 10, je 8 MB, zusammen 20 MB, jede mit sha256 und Größe - auch in `plugins/index.json` genannt), die die App selbst ausliefert, ohne dass ein Dienst läuft. Sie liegen schreibgeschützt in einem eigenen Ordner, werden nie geöffnet oder ausgeführt und gehen nur an angemeldete Personen (`/plugins/<id>/files/<Name>`, `attachment`, `no-store`). Sie stehen mit Prüfsummen auf der Freigabe-Seite und der Paketseite; eine neue Version mit anderen Dateien braucht eine neue Freigabe; beim Entfernen des Plugins werden sie gelöscht. **Bundles** bauen auf Abruf ein Zip aus Dateien des Pakets (feste Reihenfolge und Zeiten, jedes Mal dieselben Bytes). Gezeigt als Gruppe *Dateien* auf *Schnittstellen* und der Einstellungsseite; `{file:Name}` in `docs` wird zum Link. `tools/build_plugin_package.py` und `tools/check_plugin.py` kennen sie.

## 0.3.318
- **Dateien zum Herunterladen:** Ein Plugin listet Dateien, die sein Dienst anbietet (`downloads` in der `plugin.json`, unter seinen Adressen); die App zeigt Knöpfe auf der Einstellungsseite und der Seite *Schnittstellen*. Nicht öffentliche Adressen funktionieren auch für eine angemeldete Person von außen (vorher: nur aus Home Assistant). Binäre Antworten und `Content-Disposition` gehen durch den Proxy (getestet).
- **Ein Plugin mit Dienst UND Anbindungsdatei hat ein Token** (vorher konnte die Datei keines bekommen): einmal beim Einrichten angezeigt, dasselbe geht an den Dienst; *Neues Token* erneuert beides und startet den Dienst neu; *Ich habe das Token schon* funktioniert auch dafür.
- **Neue Anleitung:** `docs/plugin-guide.de.md` - ein Plugin von Null bis in eine Quelle in acht Schritten (Ordner, plugin.json, Einstellungen, Connector-API, Dienst, Downloads, Schnittstellen, Prüfen und Veröffentlichen).

## 0.3.317
- **Ein Plugin ist eine Verbindung nach außen:** Die Docs und die Regeln sagen es jetzt klar - zu einem Auto, einem Webdienst, bei dem du dich anmeldest, einem Cloud-Konto, einem Gerät, zu allem. Die Zugangsdaten sind Einstellungen des Plugins (ein `password`-Feld); sie sind nicht Teil einer Fahrzeugsicherung. Ein Dienst kann die Hosts angeben, mit denen er spricht (`service.connects`), gezeigt auf der Freigabe-Seite (eine Änderung braucht eine neue Freigabe).

## 0.3.316
- **Schnittstellen-Seite je Paket:** Jede Kachel hat einen Knopf *Schnittstellen*: eine Seite mit allem, was ein Paket anbietet oder nutzt (sendet an die App, liest von der App, bietet selbst an, Einstellungen), angegeben in seiner `plugin.json` (`interfaces`, `docs`) und *gesehen* (wirklich genutzt: Adresse, Namen der Felder, wie oft, wann - nie Werte, immer vermerkt, mit dem Paket gelöscht). Die Adressen eines Dienstes, die Seiten einer Integration und die Anbindungsdatei werden von selbst aufgeführt. Außerdem behoben: Beim Entfernen eines Plugins wird auch sein beobachteter Verkehr gelöscht.

## 0.3.315
- **Vorhandenes Token für die Anbindungsdatei:** Auf der Einstellungsseite eines Plugins mit Anbindungsdatei gibt es neben *Neues Token* einen zweiten Weg: *Ich habe das Token schon*. Das eingegebene Token wird mit dem gespeicherten Fingerabdruck verglichen; stimmt es, wird die Anbindungsdatei mit diesem Token noch einmal heruntergeladen - es entsteht kein neues Token. Falsche Eingaben bekommen eine klare Meldung und ändern nichts; das Token wird nie angezeigt oder protokolliert; nur Administrator; fünf falsche Versuche in 15 Minuten stoppen weiteres Raten.

## 0.3.314
- **Zurück ist immer da:** Auf breiten Bildschirmen war der Zurück-Knopf auf jeder Seite unter *Mehr* ausgeblendet (die Liste links sollte ihn ersetzen). Jetzt erscheint er auf jeder Seite, die irgendwohin führt, bei jeder Bildschirmgröße. Die Protokollseite eines Plugins zeigt die Plugin-Auswahl immer, auch wenn es noch keine Zeilen hat.

## 0.3.313
- **Einstellungen von Plugins sind eine Seite, mit vielen weiteren Feldarten:** Das Pop-up ist weg (auch der Zugangsschlüssel einer Quelle). *Einstellungen* öffnet eine Seite mit festem *Zurück* zur *Verwaltung* (auch auf breiten Bildschirmen). Neue Feldarten, dargestellt wie die Einstellungen von Home Assistant: Schieberegler, Auswahlknöpfe (Radio), Kontrollkästchen-Gruppe (`multiselect`), URL, E-Mail, Uhrzeit, Datum, Farbe, Überschriften (`section`) und Texte (`info`), dazu `required`, `placeholder`, `unit` und `show_if` (ein Feld erscheint nur, solange eine andere Einstellung einen Wert hat). Falsche Eingaben werden benannt, und es wird nichts gespeichert, bis sie korrigiert sind. Ein Dienst bekommt typisierte Werte in `settings.json`. Bis zu 40 Felder.
- *Verwaltung* ist wieder einspaltig; die Knöpfe *Datei installieren* und *Quelle hinzufügen* stehen unter den Kacheln von *Hinzufügen*; *Quellen* zeigt das Formular zum Hinzufügen zuletzt und den Zugangsschlüssel als Knopf.
- Seiten, die irgendwohin führen, haben ein **festes Zurück** (ein Paket, die Quellen, Debug, Dienst-Freigabe, Fahrt, Bericht, Bibliothek, Widgets ...), nie eine Adresse aus einem Link.

## 0.3.312
- **Plugins und Integrationen als Kacheln:** Die drei Tabs sind klarer. *Hinzufügen* hat den Knopf *Liste aktualisieren*, *Verwaltung* hat *Nach Updates suchen* (sagt, was gefunden wurde), *Quellen* hat keinen Update-Knopf mehr. Pakete erscheinen als Kacheln mit Icon (aus dem Index der Quelle oder dem Plugin), Name, Kurztext und Zustand; „Datei installieren“ und „Quelle hinzufügen“ sind Kacheln am Ende. Neu (freiwillig): *Einstellungen → System → Paket-Updates* liest die Quellen einmal am Tag.
- **Protokolle je Plugin:** Jede Kachel hat *Protokoll* und einen eigenen *Debug*-Knopf (mehr Details nur für dieses Plugin, bis er ausgeschaltet wird); Protokolle bleiben 1, 7 oder 30 Tage (*Einstellungen → System*). Englischen Tab-Namen korrigiert (*Manage* bei beiden).
- **Reichweite und Tank:** Die Menge im Tank kann geliefert werden (`fuel_amount`); ein Elektroauto liest seinen Batteriestand für die Prozent; Liter / kWh erscheinen neben den Prozent auch ohne Reichweite.
- **Für Plugin-Autoren:** `tools/check_plugin.py` prüft ein Paket und nennt Tippfehler und falsche Icons; `docs/icons.de.md` listet die Icon-Namen.

## 0.3.311
- **Plugins und Dienste beobachten:** Die Seite *Debug & Log* hat eine Ansicht *Verkehr* (solange Debug an ist: jeder Aufruf eines Plugins an die API und jede Anfrage auf eine Adresse seines Dienstes - Zeit, Status, Adresse, Größe, Dauer, Feldnamen, nie Werte) und zeigt, was das Add-on mit einem Dienst tut (Installation, pip-Fehler, Start, Stopp, Absturz mit Exit-Code und Pause) - immer, als Zeilen im Log des Plugins, filterbar je Plugin und mit dem Plugin gelöscht.

## 0.3.310
- **Einstellungen → System sagt die Wahrheit zum Direktzugriff:** Es zeigte *Aus*, sobald die alte Passwort-Option leer war, auch bei gesetztem Port. Jetzt fragt es Home Assistant nach dem Port und sagt: aus (kein Port), an (durch deine Benutzer geschützt), an (altes Passwort), gesperrt (Port, aber noch kein Benutzer) oder unbekannt. Ein neuer Text erklärt, wo was eingestellt wird: der **Port nur in Home Assistant** (Apps → Car Assistant → Konfiguration → Netzwerk), die **externe Adresse hier oder in den App-Optionen** (die Option gilt zuerst). Die Passwort-Option ist als alt markiert - leer lassen und Benutzer nutzen. Die Konfigurationstexte in Home Assistant sagen dasselbe.

## 0.3.309
- **Plugin-Protokolle:** Log-Zeilen gehören jetzt zu ihrem Plugin (auch die Ausgabe des Dienstes eines Plugins). *Einstellungen → System → Plugin-Protokolle* legt fest, wie viele Zeilen jedes Plugin behalten darf (200 bis 20 000, Standard 1000; die ältesten gehen zuerst, ein gesprächiges Plugin verdrängt kein anderes) und kann alle löschen. Die Seite *Debug & Log* lässt sich je Plugin filtern und zeigt, wer eine Zeile geschrieben hat. Beim Entfernen eines Plugins werden alle seine Log-Zeilen gelöscht.

## 0.3.308
- **Plugins mit Dienst:** Ein Plugin aus einer Quelle darf ein eigenes Programm mitbringen, das im Add-on selbst läuft (kein zweiter Container). Strenge Regeln: nur lesbare Textdateien, sha256 des Index geprüft, ein Administrator gibt es auf einer Seite frei, die alles auflistet (eine geänderte Beschreibung braucht eine neue Freigabe), eigener Prozess, eigene virtuelle Umgebung und eigener unprivilegierter Benutzer mit Grenzen, saubere Umgebung (kein Home-Assistant-Token, keine Datenbank), die Connector-API als einzige Tür zur App. Öffentliche Adressen (zum Beispiel für das Auto) werden unverändert weitergereicht. Start / Stopp auf der Plugin-Karte; nach einem Absturz startet er mit wachsender Pause neu; Entfernen räumt alles auf. Neu: `tools/build_plugin_package.py` und das Beispiel `docs/examples/echo-service`. Siehe docs/plugins.de.md.

## 0.3.307
- **Anbindungsdatei für Plugins:** Die Beschreibung eines Plugins kann `connection_file` enthalten (Dateiname und Text-Vorlage mit `{token}`, `{vehicle}`, `{url}` und den Einstellungen als `{key}`). Wenn das Token angezeigt wird (Einrichten oder *Neues Token*), gibt es einen Download-Knopf: Die Datei enthält schon das Token und die Einstellungen des Plugins, ein Gerät im Auto braucht nur diese Datei neben sich. Zeilen mit leerem Wert entfallen. Nichts wird gespeichert oder ausgeführt. Der Standardwert einer Einstellung darf jetzt bis zu 200 Zeichen lang sein (vorher 60).

## 0.3.307
- **Connector-API:** Ereignisse (`/events`, zum Beispiel gelesene Verkehrszeichen oder überfahrene Ortsgrenzen, die neuesten 2000 bleiben), eine vom Plugin bemerkte Tankung (`/refuel`, kommt ins Tankbuch, Doppelte werden ignoriert) und der Sendetakt (`interval_s` in `control`, einstellbar auf der Seite *Debug & Log*).
- **Fahrzeugdatei:** Das Dateiformat ist beschrieben (`docs/vehicle-file.de.md`) und hat ein Beispielskript - der Weg, ein Auto aus einem anderen Programm zu holen.

## 0.3.306
- **Fahrten aus der Spur:** Positionen, die ein Plugin an `/track` schickt, werden von selbst zu Fahrten im Fahrtenbuch: Eine Fahrt endet nach zehn Minuten ohne Punkt; Datum, Zeiten, Start-/Zielort, Strecke und Route werden gefüllt (als aus der Spur entstanden markiert). Sehr kurze Strecken fallen weg.

## 0.3.305
- **Vorlieben je Benutzer:** Unter *Einstellungen → Benutzer → Meine Vorlieben* wählt jeder angemeldete Benutzer das Auto, das zuerst öffnet (oder wird gefragt); die Tipp-Rückmeldung wird jetzt ebenfalls je Benutzer gespeichert. Was nicht gesetzt ist, folgt den Systemeinstellungen.

## 0.3.304
- **Connector-API, mehr Anschlüsse:** gzip-Anfragen; ein Spur-Endpunkt für Fahrten (`/track`, viele Punkte, setzt auch die aktuelle Position); Rohsignale (`/signals`) für alles ohne Standardfeld, gezeigt auf der Debug-Seite; Plugins können Einträge einer Integrationsseite anlegen, ändern und löschen (`POST /modules/<Integration>/<Seite>`, zum Beispiel die Steuergeräte von Coding); neue Felder AdBlue-Stand/Reichweite, Ölstand/Warnung und das aktuelle Tempolimit (auch in den Fahrzeugdaten). Body-Grenze 20 kB. Siehe docs/api.de.md und docs/plugins.de.md.

## 0.3.303
- **Kleinigkeiten:** Runder Plus-Knopf (oben rechts) bei Integrationen, Plugins und Quellen; das Angebot *Typische Punkte anlegen* bei den Wartungsaufgaben entfällt (du trägst deine eigenen ein); ein Video bekommt ein gespeichertes Vorschaubild (der Browser nimmt es beim Hochladen auf), die Bibliothek lädt die Videos nicht mehr nur für Vorschaubilder. Das Vorschaubild ist Teil der Fahrzeugsicherung.

## 0.3.302
- Aufräumen: Das ungenutzte eingebaute Paketangebot (Code und Karte) ist entfernt.

## 0.3.301
- **Versteckte Widgets:** Ein ausgeschaltetes Widget (Auge) ist auf der Startseite wieder wirklich weg; es erscheint nur gedimmt, solange du bearbeitest.

## 0.3.300
- **Webradio und Kraftstoff-Additiv in der Liste:** Der eingebaute Webradio-Platzhalter entfällt – Webradio, Coding und Kraftstoff-Additiv kommen nur noch aus den Quellen (einmal *Alle Quellen aktualisieren* tippen). Ein früher aus einer Datei installiertes Paket wird von seiner Quelle übernommen, wenn du es von dort installierst; Einstellungen und Einträge bleiben.

## 0.3.299
- **Benachrichtigungen je Benutzer:** Unter *Einstellungen → Benutzer* wählt jeder angemeldete Benutzer seinen eigenen Home-Assistant-Benachrichtigungsdienst und welche Ereignisse er will: Wartung fällig, Termine, Erinnerungen von Integrationen (zum Beispiel Kraftstoff-Additiv), Meldungen des Autos, Türen oder Fenster offen – dazu ein Knopf *Test senden*. Alles ist optional; es wird nichts gesendet, bis ein Dienst eingetragen und ein Ereignis angekreuzt ist. Jeder Benutzer wird über einen Punkt nur alle paar Tage informiert. Der allgemeine Dienst aus den Add-on-Optionen funktioniert wie bisher.

## 0.3.298
- **Design je Auto:** In den Fahrzeugdaten kann ein Auto *Wie das System* oder ein eigenes Design (Farbthema) wählen. Es gilt auf den Seiten dieses Autos; überall sonst bleibt das Systemdesign.

## 0.3.297
- **Seiten von Integrationen:** ein Suchfeld (`"search": true` an einer Seite), der Filter *Nur geänderte* bei Seiten mit Hex-Vergleich, und ein Tipp auf ein Byte zeigt seine Bits (alt oben, neu unten, geänderte Bits markiert). *Coding* und *Webradio* nutzen die Suche (Version 2 im Quellen-Repository).

## 0.3.295
- **Erinnerungen und Dashboard-Widgets von Integrationen (erstes Beispiel: *Kraftstoff-Additiv*):** Eine Integration kann Erinnerungsregeln beschreiben – „wieder nach N Kilometern“ oder „nach N Tankungen“, mit den Zahlen aus ihren Einstellungen (Standardwerte für Einstellungen sind neu). Die App zählt aus Kilometerstand und Tank-Einträgen; *Erledigt* beginnt die Zählung neu. Eine laufende Integration mit Erinnerung bekommt eine Karte auf der Seite *Tanken* und ein Widget auf dem Dashboard (verschiebbar wie jedes Widget). Alles ist optional: Es passiert nichts, bis die Integration installiert ist und läuft. Das Paket *Kraftstoff-Additiv* liegt im Quellen-Repository.

## 0.3.294
- Die Startseite `/` (wo ein Auto gewählt wird) wählt kein Auto mehr vor: Die Seitenleiste nennt keins (Name und Slogan stehen dann mittig neben dem Logo), und die Leiste hat keine Auto-Seiten, bis du eins wählst.
- Seitenleiste: Unter dem Namen steht immer der Slogan *Drive · Log · Go*, darunter in einer eigenen festen Zeile das Auto, zu dem die Navigation gehört (mit dem Symbol zum Wechseln), damit beim Seitenwechsel nichts mehr hüpft; das Logo ist in der breiten Seitenleiste größer, damit die drei Zeilen daneben passen.

## 0.3.290
- *Auswertung* hat in den Menüs eine eigene Farbe (Türkis); Lila gehört jetzt nur noch den Integrationen und Plugins.

## 0.3.289
- **Eine Liste der Integrationen:** *Feste Integrationen* heißt jetzt einfach *Integrationen* und enthält auch die installierten Integrationen (Coding, Webradio, ...), jede mit ihrem Schalter: aus = gestoppt (Seite und Navigationseintrag weg), an = läuft. Die Karten mit den Einzelheiten (öffnen, Leiste, Einstellungen, entfernen) bleiben darunter.
- **Integrations-Seiten in der Navigationsleiste:** Eine laufende Integration mit Seiten lässt sich in die Leiste legen (Knopf *In der Leiste zeigen* an ihrer Karte unter *Verwalten* oder im Editor *Navigation*) und wieder herausnehmen; in der Leiste zeigt sie ihr eigenes Symbol und ihren Namen, sonst steht sie in *Weiteres*. Die Karte einer Integration zeigt ihr eigenes Symbol und den übersetzten Namen, einen Knopf *Öffnen* und *Einstellungen* nur, wenn es welche gibt; die Knöpfe der Integrations- und Plugin-Karten sind nur Symbole (der Name steht im Tooltip).

## 0.3.286
- **Integrationen können Seiten beschreiben (Seiten-Module):** Ein Paket kann Seiten mit typisierten Feldern (Text, Zahl, Ja/Nein, Auswahl, Web-Adresse, Hex), ein Symbol, Übersetzungen und – für Hex-Werte – einen Byte-für-Byte-Vergleich mit einem einmal geschriebenen Original mitbringen. Die App zeichnet und speichert sie je Auto (Teil der Fahrzeugsicherung); eine laufende Integration erscheint in *Weiteres*, eine gestoppte verschwindet. Ein Plugin des Autos liest die Einträge über `GET /api/v1/vehicles/<id>/modules/<integration>/<page>`. Offizielle Beispiele im Quellen-Repository: *Coding* und *Webradio*. Siehe `docs/integrations.de.md`.

## 0.3.284
- **Paketseiten:** Die Links zu einem Paket und zur Quellen-Seite tragen keine `?back=`-Adresse mehr; *Zurück* ergibt sich aus der Seite selbst. (Beim Öffnen einer Paketseite kam bei einer Einrichtung in Home Assistant ein *400 Bad Request*.)
- **Ein Video ohne Foto:** Ein erstes Video lässt sich ohne Foto hochladen; Autoauswahl und Listen zeigen dann das Standardauto, bis ein Foto da ist.

## 0.3.283
- **Foto und Video als Schieber:** Die Bibliothek im Foto-/Video-Fenster (Dashboard und Fahrzeugdaten) sind nicht mehr fünf kleine Spalten, sondern eine Reihe größerer Bilder, die du nach links und rechts schiebst, um das richtige zu wählen oder zu löschen. *Speichern* steht ganz am Ende der Seite. Die Bilder füllen ihre Kachel komplett aus (keine Balken oben und unten). Bis zu **10** Dateien pro Auto statt 5.
- **Dashboard-Symbol:** Der Reiter und die Einträge „Dashboard“ nutzen einen Tacho statt des Hauses.
- **Widgets mit einer Zeile mehr:** *Service* zeigt, wie weit es bis zum nächsten Service ist (oder wie lange er überfällig ist), *Tanken / Laden* den Preis der letzten Füllung, *Letzte Fahrt* die Dauer (wenn Start- und Endzeit bekannt sind) und *Sicherheit* die erste offene Tür oder das erste offene Fenster.

## 0.3.277
- **Hinzufügen-Knopf oben rechts:** Auf den Listenseiten (Servicebuch, Tanken, Fahrten, Zähler, Teile, Aufgaben, Termine, Reifen, Dokumente) ist *Hinzufügen* jetzt nur noch ein runder Plus-Knopf oben rechts im Seitenkopf, immer der letzte ganz rechts; er öffnet das Formular (und schließt es wieder). Die zusätzliche Karte *Hinzufügen* über der Liste entfällt. *Typische Punkte anlegen* (Aufgaben) ist aus dem Seitenkopf verschwunden: Es erscheint in der leeren Aufgabenliste.

## 0.3.275
- Widgets: weniger Innenabstand in den Kacheln (10 / 12 px statt 14 / 16 px, 8 px zwischen Titel und Wert, ein kleineres Symbol mit 28 px); der Abstand zwischen den Kacheln bleibt.

## 0.3.273
- Live-Updates: Meldet das Auto einen neuen Kilometerstand, zählen die Walzen einfach weiter, ohne den Hereinroll-Effekt (der Effekt läuft nur beim Öffnen der Seite).

## 0.3.272
- Video-Vorschaubilder im Foto-/Video-Fenster zeigen die Mitte des Videos statt des ersten Bildes (vom Browser erzeugt, es wird nichts gespeichert oder verändert).

## 0.3.271
- **Foto-/Video-Fenster:** Es ist jetzt eine eigene Seite über der ganzen Fläche (kein Fenster im Fenster) im eigenen Hintergrund des Themes, in hellen und dunklen Themes lesbar; die Karten scrollen wie auf jeder Seite, der Schließen-Knopf bleibt oben rechts, und *Speichern* steht als Letztes ganz unten.

## 0.3.265
- **Große Fotos werden komprimiert statt abgelehnt:** JPEG- und WebP-Fotos ab 2 MB werden beim Speichern verkleinert (auf 1920 px skaliert, aufgerichtet, Metadaten entfernt, Qualität schrittweise gesenkt, bis sie unter 10 MB liegen); dafür wird ein Foto bis 40 MB angenommen. Kleinere Fotos, jedes PNG und alle Videos bleiben genau so, wie sie hochgeladen wurden. JPEGs werden verkleinert gelesen, deshalb braucht selbst ein 100-MP-Foto wenig Speicher. Außerdem überlappen bei einem Video-Bild die Wartungs-/Prüf-Kästchen den Kilometerstand darunter nicht mehr.

## 0.3.263
- **Widget-Einstellungen:** Beim Bearbeiten der Seite bekommt jedes Widget mit Einstellungen einen Stift-Knopf neben dem Auge. Er öffnet ein kleines Fenster mit den Einstellungen (Kilometerstand: *Aussehen* – Walzen oder Kachel); Änderungen gelten und speichern sofort. Der Mechanismus ist allgemein, so können später weitere Widgets Einstellungen anbieten.

## 0.3.262
- **Kilometerstand als Widget in zwei Ausführungen, beide in der normalen Kachel, die Walzen über die volle Breite mit der Einheit auf der Grundlinie der Ziffern in derselben Zeile (die Walzen passen sich der Größe des Widgets an; die Service-Zeile gehört nur unter das Autobild, nicht ins Widget):** Sobald das Auto eine Reichweite meldet (sie steht dann unter dem Auto), wandert der Kilometerstand in die Widgets. Beim Bearbeiten der Seite wechselt ein Knopf am Widget zwischen *Walzen* (frei, mit Fortschrittslinie, breit) und *Kachel* (mit Rahmen, klein); die Wahl wird je Auto gespeichert und steht auch in der Widget-Liste (Bearbeiten-Seite).

## 0.3.255
- Kilometer-Walzen: Die letzten drei Einheiten ticken jetzt schon während des Hereinrollens hoch (nach etwa einer Sekunde statt zwei fertig), und das Hereinrollen selbst ist etwas langsamer und weicher.

## 0.3.254
- Die Kilometer-Walzen spielen nach dem Hereinrollen die letzten drei Einheiten durch (z. B. 179.997 -> 180.000), ein paar Textwechsel in etwa einer Sekunde; aus bei *Bewegung reduzieren*. Die Walzen folgen den Server-Einheiten (Meilen als Meilen).

## 0.3.253
- Kilometer-Walzen mit dünner Fortschrittslinie und "noch X km bis zum nächsten Service" darunter (die nach Kilometern zuerst fällige Aufgabe; "überfällig seit", wenn sie überschritten ist). Ohne Rahmen.

## 0.3.252
- **Kilometerstand als Walzen:** Der Kilometerstand auf dem Dashboard sieht jetzt aus wie ein echtes Zählwerk: eine dunkle Glas-Zelle je Ziffer, die letzte Ziffer in der Akzentfarbe, mit kurzem Hochrollen beim Öffnen (aus bei *Bewegung reduzieren*).

## 0.3.251
- Dashboard-Bild mit Foto: Ein einzelnes Kästchen in seiner Zeile sitzt mittig (und ragt weiter ins Bild); mehr Luft zwischen den Kästchen und der Modellzeile darüber sowie zwischen den Kästchen und dem Kilometerstand darunter. Geprüft mit 0, 1 und 2 Kästchen oben und unten.

## 0.3.250
- Dashboard-Bild: Die Status-Kästchen über und unter dem Foto ragen wieder ins Bild hinein, mit Glaseffekt (die Korrektur aus 0.3.244 hatte das entfernt). Das Foto verdeckt weiterhin weder Namen noch Modellzeile, wenn kein Kästchen darüber steht, und die Kilometerstand-Karte dockt unter einem Foto nicht mehr in die Kästchen.

## 0.3.249
- Behoben: Der Knopf *Foto / Video bearbeiten* auf dem Dashboard-Bild sprang beim Draufdrücken nach rechts (der Druck-Effekt ersetzte seine Zentrierung). Er ist jetzt ohne Transform zentriert.

## 0.3.248
- **Fotos werden beim Hochladen verkleinert:** JPEG- und WebP-Fotos werden aufgerichtet, auf höchstens 1920 px an der längeren Seite verkleinert und beim Speichern von Metadaten (GPS-Position, Kamera) befreit. PNG-Bilder (Freisteller mit Transparenz) und Videos bleiben unverändert.

## 0.3.247
- Das Symbol *Auto wechseln* neben einem Autonamen (Seitentitel, Dashboard und jetzt auch in der Seitenleiste unter dem Logo) ist nur noch das Symbol, ohne runden Knopf.

## 0.3.246
- Ab zwei Autos steht der Knopf *Auto wechseln* jetzt auf jeder Seite direkt neben dem Autonamen unter dem Seitentitel (nicht nur auf dem Dashboard).

## 0.3.245
- Der Projekt-Slogan **Drive · Log · Go** (in jeder Sprache gleich): unter dem Namen in der Seitenleiste, wenn kein Auto gewählt ist, auf der Über-Seite sowie in den READMEs und der Add-on-Beschreibung.

## 0.3.244
- **Startseite mit Foto:** Ein undurchsichtiges Foto liegt nicht mehr über der Modellzeile unter dem Namen, und die Wartungs-/Prüf-Kästchen darunter überlappen die Kilometerstand-Karte nicht mehr (die Überlappung gibt es nur bei freigestellten Bildern und dem Standardauto).

## 0.3.243
- Das Logo führt immer zur Startseite `/` (keine eigene Adresse): bei einem Auto das Dashboard, bei mehreren die Auswahl.

## 0.3.242
- **Startseite mit wenig Daten:** Ein neues Auto zeigt eine Liste *Los geht's* (Kilometerstand, erste Tankung, Service-Eintrag, Auto verbinden) statt einer leeren Seite; eine einzelne kleine Kachel, die allein in ihrer Zeile stünde, nutzt jetzt die ganze Zeile; die Tank-Kachel zeigt ohne Menge keine einsame Einheit mehr.

## 0.3.241
- Die Fahrzeugliste beim Start (ab zwei Autos) ist nur noch eine Auswahl. Hinzufügen, Wiederherstellen, Sichern und Löschen gibt es nur noch unter **Weiteres → Fahrzeuge**; der Fahrzeugwechsler hat keine Kachel *Fahrzeug hinzufügen* mehr. Ganz ohne Auto bietet die Startseite weiter *Fahrzeug hinzufügen* an.

## 0.3.240
- **Eine Quelle, beide Arten:** Eine Quelle (ein Repository) gilt jetzt immer für Integrationen und Plugins zugleich – sie steht in beiden Reitern, wird für `integrations/` und `plugins/` in einem Zug gelesen und als Ganzes gelöscht. Bestehende Quellen wurden in beide Listen eingetragen.

## 0.3.239
- **Fahrzeugliste** (bei mehreren Autos) ist jetzt nur noch eine Auswahl: kein Plus oben, kein Wiederherstellen-Feld, keine Herunterladen-/Löschen-Knöpfe auf den Karten und kein Hinweis unten. Hinzufügen, Wiederherstellen, Sichern und Löschen gibt es im Fahrzeugwechsler, unter *Fahrzeug hinzufügen* und auf der Bearbeiten-Seite des Fahrzeugs. Bei einem Auto landest du weiter direkt auf dessen Dashboard.

## 0.3.238
- **Quellen:** Eine Quelle ohne eigenen Namen bekommt einen sauberen Namen (`Besitzer/Repository` bei GitHub oder der Name aus ihrer Wurzel-`index.json`) statt „github.com“. Ein Haken trägt sie in beide Listen ein (Integrationen und Plugins). Die Index-Dateien werden toleranter gelesen (`{"packages": [...]}`, eine nackte Liste, der Schlüssel der Art); ausgelassene Einträge (z. B. ungültige id) werden an der Quelle mit Grund angezeigt. Die Seite *Hinzufügen* listet jetzt alles, was die Quellen anbieten, bereits Installiertes markiert, dazu die Schaltfläche *Aktualisieren* und ein Hinweis.
- Fahrzeugformular und Fahrzeugdaten: **HSN / TSN** stehen jetzt direkt neben *Typ / Bauart*.

## 0.3.237
- **Einheiten überall:** Strecken, Mengen und Preise je Menge werden jetzt in allen Listen und Formularen (Service, Tanken, Fahrten, Zähler, Teile, Aufgaben), im Fahrzeugformular (Kilometerstand, Reichweiten-Stufen), in der Auswertung (mpg, Meilen), in Fälligkeitstexten und Benachrichtigungen sowie in der Tankstellensuche (Umkreis und Entfernungen) in den Einheiten aus *Einstellungen → Region* EINGEGEBEN und angezeigt. Gespeichert wird weiter in km / Litern / Preis je Liter; ein Wert, der unverändert gespeichert wird, bleibt gleich. Elektroautos behalten kWh und Geld.

## 0.3.236
- **Einstellungen → System** überarbeitet, kompakter: eine Karte *System* (Version, Daten, Home Assistant, MQTT, Erinnerungen) mit eingeklappten Test-Werkzeugen; *Schutz der Anmeldung* mit den zwei Auswahlen nebeneinander; *Online-Dienste* (Karte, Spritpreise) in einer Karte; *Sicherung* mit eingeklapptem Wiederherstellen und Zurücksetzen.
- Neu: **Externe Adresse (URL)** – trage die Adresse ein, unter der du die App von außen erreichst (eine in der App-Option von Home Assistant gesetzte Adresse gilt zuerst und wird nur angezeigt). Das Feld ist gesperrt, bis ein Benutzer existiert, mit Grund und Link (sonst könnte jeder im Internet deine Autos lesen); eine kurze Anleitung erklärt den Port in Home Assistant, den Benutzer, den HTTPS-Reverse-Proxy und wo die Adresse einzutragen ist.

## 0.3.234
- Einstellungsfenster: zuerst die Felder, dann das Token, und *Speichern* ganz am Ende – es speichert alles im Fenster auf einmal und schließt es. Was du speicherst, bleibt im Plugin (je Auto) und ist Teil der Fahrzeug-Sicherung (auch lange Notizen); nur das Paket selbst nicht.

## 0.3.233
- Karten von Plugins und Integrationen haben genau drei Knöpfe: *Start / Stopp*, *Einstellungen*, *Deinstallieren*. *Einstellungen* öffnet ein Fenster mit allem, was das Plugin ändern lässt (Text, Textfeld, Passwort, Häkchen, Zahl, Auswahl – je mit optionalem Hilfetext), und seinem Anbindungs-Token; die Werte werden erst nach *Speichern* mit dem Plugin abgelegt ([docs/plugins.de.md](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/plugins.de.md)).

## 0.3.232
- Plugin-Karten am Handy: Die vier Knöpfe sind nur Symbole, gleich breit in einer Zeile (die Beschriftungen bleiben als Tooltip und für Screenreader), nichts überlappt mehr auf schmalen Bildschirmen; die Quellenzeile bricht um, statt abgeschnitten zu werden.

## 0.3.231
- Die Plugin-Karten zeigen, von wem das Paket ist und aus welcher Quelle es kommt (*von Matze89x · aus Car Assistant* oder *eigener Upload*). Die Debug-Karte unten bei Plugins ist weg: Debug wandert in das Plugin, das es anbietet.

## 0.3.226
- Karten von Plugins und Integrationen überarbeitet: Icon, Name und eine Status-Anzeige (grün und pulsierend, solange es läuft), die Beschreibung, die Einstellungen und EINE Zeile mit Knöpfen – *Start / Stopp* als echter Knopf (grün *Starten*, schlicht *Stoppen*), *Speichern*, *Neues Token*, *Deinstallieren* (am Handy nur Symbole).

## 0.3.225
- Die Navigation bleibt auf der ersten Seite *Fahrzeug hinzufügen* sichtbar (sie war dort ausgeblendet); nur die eigenen `/setup`-Seiten der Führung haben keine.

## 0.3.224
- Über: Der Schlusstext sagt jetzt, was die App ist – praktisch, handlich, nur mit den Funktionen, die man wirklich braucht.

## 0.3.223
- Korrektur: Nach der Werkseinstellung ist die Standardquelle wieder da, wie bei einer frischen Installation (sie fehlte); sie lässt sich wieder entfernen, wenn nichts daraus installiert ist.

## 0.3.222
- *Erst mal nur umsehen?* ist der einzige Zugang zu den Demo-Autos (keine zweite Liste mit denselben Autos). Es erscheint nur, solange die Standardquelle in deiner Liste steht: Entfernst du sie, verschwindet der Eintrag – ohne Verbindung gibt es keine Demo.

## 0.3.221
- **Erst mal umsehen, richtig:** *Fahrzeug hinzufügen → Erst mal umsehen* fragt einmal (es geht online), liest die Standardquelle, stellt daraus das Demo-Auto wieder her, installiert das Plugin *Demo connector* aus dieser Quelle und schaltet es ein. Ein allgemeiner Szenario-Abspieler schickt dann alle 5 Sekunden einen Bericht durch die normale Schnittstelle (`/api/v1`, mit dem Token des Plugins): parken, einsteigen, fahren (Position, Kilometerstand und Füllstand ändern sich), anhalten, aussteigen, manchmal ein Fehler; ein Elektroauto lädt, wenn die Batterie niedrig ist. Gespielt wird nur ein Plugin, das aus einer Quelle installiert wurde, nie ein hochgeladenes. *Start / Stop* auf der Plugin-Karte stellt das Auto still – es wird nichts gesendet und sein Token wird abgelehnt. Der eingebaute Demo-Code ist weg; die erfundenen Daten liegen in `tools/demo_data.py`, die zwei Demo-Autos in der Quellen-Repo.
- *Fahrzeug hinzufügen* bietet die Autos deiner Quellen an (`vehicles/index.json`, `vehicles/<id>.zip`) und stellt sie wie eine hochgeladene Sicherung wieder her; das Wiederherstellen steht auch beim allerersten Start da.
- Eine Fahrzeug-Sicherung trägt jetzt auch das eigene App-Icon des Autos und seinen Debug-Schalter.
- Zurück führt auf die Seite, von der du kommst, wenn du *Quellen* oder ein Paket aus *Hinzufügen* öffnest.

## 0.3.220
- Auto wechseln und die Rückfrage-Fenster haben eine eigene deckende Fläche, damit sie auch bei den hellen Designs lesbar sind (dunkle Schrift auf dunklem Schleier).

## 0.3.219
- Beim Wiederherstellen einer Fahrzeug-Sicherung eines Autos, das schon da ist (gleiche Kennung oder gleicher Name), wird zuerst gefragt: *Daten ersetzen* (das Auto behält seine Adresse; zuvor wird eine Kopie seines Stands gesichert), *Als Kopie anlegen* (Name und Adresse bekommen eine Nummer) oder abbrechen.

## 0.3.218
- Der Knopf *Sichern* an den Fahrzeugkarten ist ein voller grüner Kreis wie der rote Papierkorb daneben (er war kaum zu sehen).

## 0.3.217
- Die Seite *Fahrzeuge* hat an jedem Auto einen Knopf *Sichern* und eine Zeile *Fahrzeug aus einer Sicherung wiederherstellen*.

## 0.3.215
- *Tankbuch* heißt wieder *Tanken* (und *Ladeprotokoll* bei Elektroautos *Laden*). Ist die Funktion Tankstellen an, stehen die Tankstellen in der Nähe mit Preisen oben auf der Seite Tanken (Suche rund ums Auto oder um dich, online erst nach dem Tippen auf Suchen); darunter folgt der Verlauf der Tankvorgänge.

## 0.3.214
- **Fahrzeug-Sicherung:** *Fahrzeugdaten → Dieses Fahrzeug sichern* lädt alles von EINEM Auto (Daten, Dateien, Einstellungen, Anbindungs-Token, die Einstellungen seiner Integrationen und Plugins – nicht die Pakete); *Fahrzeug hinzufügen → Wiederherstellen* legt daraus ein neues Fahrzeug an. Integrationen und Plugins kommen ausgeschaltet zurück; ein fehlendes Paket steht als *braucht das Paket* mit *Installieren*-Knopf oder dem Hinweis, welche Quelle zuerst nötig ist. Sicherungen tragen eine Formatnummer; ab 1.0 bleibt jedes ältere Format einspielbar ([docs/backup.de.md](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/backup.de.md)). Die System-Sicherung (mit Benutzern) ist getrennt und hat jetzt auch eine Formatnummer.
- Zwei Demo-Fahrzeuge (Diesel, Elektro) als Fahrzeug-Sicherungen für die Quellen-Repo (`tools/make_demo_vehicles.py`).

## 0.3.213
- *Hinzufügen* bei Integrationen und Plugins endet mit einer Zeile *Quelle hinzufügen*, die zum Reiter Quellen führt.

## 0.3.212
- Die „Im Aufbau“-Hinweise sind von den Hinzufügen-Seiten bei Integrationen und Plugins verschwunden.

## 0.3.211
- Quellen im Reiter: *Integrationen* und *Plugins* haben je einen eigenen Reiter *Quellen* mit eigener Liste (serverweit, für jedes Fahrzeug). Dieselbe Adresse kann in beiden Listen stehen; sie aus einer Liste zu nehmen geht nicht, solange etwas dieser Art daraus installiert ist.
- Korrektur: Der Update-Hinweis erschien auf jeder Karte (ein Namenskonflikt in der Vorlage).

## 0.3.210
- Quellen, richtig: Eine Quelle ist ein GitHub-Repository (oder eine https-Adresse) mit fester Ordnerregel – `integrations/` und `plugins/`, je mit einer `index.json` (id, name, description, version) und einem Ordner je Paket mit seiner `plugin.json` ([docs/sources.de.md](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/sources.de.md)). Es wird nichts von selbst abgerufen: nur bei *Aktualisieren*, Hinzufügen, Öffnen, Installieren oder Aktualisieren.
- *Hinzufügen* (je Fahrzeug) listet die Pakete aller Quellen; eines antippen zum Lesen, dann *Installieren*. Installierte Pakete stehen unter *Verwalten*: Einstellungen, *Aktualisieren* bei neuerer Version der Quelle, *Aktiv* an/aus (das Token eines ausgeschalteten Plugins wird abgelehnt), *Deinstallieren*.
- Eine Quelle lässt sich nur löschen, wenn nichts daraus Installiertes mehr da ist. Private Repositorys: optionaler Zugangsschlüssel (nur lesen), liegt auf dem Server und wird nie angezeigt.
- Werkseinstellung: Die erste Quelle ist das Paket-Repository des Projekts `ha-car-assistant-sources` (*Standardquelle wiederherstellen* holt sie zurück).

## 0.3.206
- Home-Bildschirm-Icon (eingebaut): ein volles Quadrat mit dünnem rot-grünem Ring knapp innerhalb der Ecken, die iOS ausschneidet – statt eines gerahmten Bilds mit breitem schwarzem Rand. Favicon und Seitenleisten-Logo bleiben unverändert.

## 0.3.205
- iOS-Home-Bildschirm: Das 180-px-Icon hat gar keine Transparenz mehr (iOS malt sie schwarz), die Seite nennt seine Größe, und die zwei Adressen, die iOS von selbst abfragt (`/apple-touch-icon.png`, `-precomposed`), werden beantwortet.

## 0.3.204
- Quellen sind eine Liste für den ganzen Server: Der Tab *Quellen* bei Integrationen und Plugins öffnet sie für jedes Fahrzeug (Hinzufügen per https-Adresse, Entfernen mit Rückfrage). Gespeichert wird nur die Adresse, es wird nichts abgerufen. *Hinzufügen* und *Verwalten* bleiben je Fahrzeug.
- Lange Listen laden beim Scrollen 5 Einträge auf einmal (auf jeder Breite; es lädt weiter, bis der Bildschirm voll ist).

## 0.3.199
- Tipp-Rückmeldung: Der unsichtbare Schalter ist ganz durchsichtig und auf die runde Form des Tabs zugeschnitten.

## 0.3.198
- Tipp-Rückmeldung, dritter Versuch: Über jedem Tab (und dem Knopf *Ausprobieren*) liegt jetzt ein unsichtbarer System-Schalter, den der Finger selbst umlegt – neuere iOS-Versionen ignorieren Haptik, die per Skript ausgelöst wird.
- Korrektur: Das Nachladen langer Listen war in 0.3.191 versehentlich aus dem Skript gefallen – wiederhergestellt, ein Test bewacht jetzt die Funktionen des Skripts.

## 0.3.197
- Über: Geschichte und Schlusssatz sind ein kurzer Text; der Kaffee-Hinweis ist kürzer.

## 0.3.196
- Über: Die Geschichte besteht jetzt aus zwei kurzen Sätzen.

## 0.3.195
- Über: die Geschichte hinter der App (Freizeitprojekt, teils allein, teils mit Claude Code, mit Liebe zum Detail und praktischem Nutzen).

## 0.3.193
- Auto wechseln: Fotos laufen randlos bis in die runden Ecken der Karte und verlaufen weich in die Karte; das Standardauto bleibt mittig.

## 0.3.192
- Abstände bei mehrzeiligen Werten: Das Label steht an der ersten Zeile (System), Einheiten wie *L/100 km* brechen nicht mehr auseinander.

## 0.3.191
- Die Tipp-Rückmeldung löst jetzt aus dem echten Klick auf das Label des versteckten Schalters aus (so funktioniert es auf iOS); Knopf *Ausprobieren* unter Einstellungen → Design.
- Korrekturen: Status-Badges auf System überlappen nicht mehr, Abstand über dem Währungsfeld bei Region.

## 0.3.190
- Lange Listen (Service, Tanken, Fahrten, Termine, Aufgaben, Reifen, Teile, Zähler, Dokumente) zeigen 10 Einträge und laden beim Scrollen die nächsten 10 nach; die Anzahl steht als „10 von 134 Einträgen“. Ohne Skript bleibt der Weiter-Knopf.

## 0.3.189
- Tipp-Rückmeldung: Auf dem iPhone (iOS 17.4+) gibt die untere Leiste einen sanften Tipp wie die Tastatur. Schalter unter Einstellungen → Design, standardmäßig an; andere Geräte tun nichts.

## 0.3.188
- Ein Knopf, eine Definition: Jeder Knopf (auch in Formularen, System und Reifen) ist 44 px / 15 px / Radius 12 aus einer einzigen Regel; die verstreuten Überschreibungen sind weg. Reifenkarten haben den normalen Karten-Innenabstand.
- Schrift und Ecken folgen einer festen Skala (Radien nur als Token, Schriftgrößen in den Stufen 10 / 11 / 12 / 13 / 14 / 15 / 16 / 18 / 20 / 24 / 32).
- Je ein Muster: Der *Bearbeiten*-Link jedes Eintrags (Stift + Text, auch bei Reifen), ein Stil für Faktenlisten (Seite System), Auswertungs-Karten wie alle anderen betitelt, der Navigations-Hinweis sagt nichts mehr doppelt, Plugin-Versionen stehen als `v1`.
- Schneller und kleiner: Das Standard-Autobild ist ein 35-KB-WebP statt 256-KB-PNG, das Seitenleisten-Logo 9 KB statt 25 KB, ungenutzte Stilregeln entfernt.

## 0.3.186
- Überall eine Größe: Felder 48 px, Haupt- und Löschknöpfe 44 px mit gleicher Schriftgröße und gleichem Radius auf jeder Seite.

## 0.3.185
- Design-Prüfung aller Seiten in Handy-, Tablet- und Desktop-Breite: nur die System-Seite wurde breiter als der Bildschirm (ein langes Status-Abzeichen) – behoben.
- *Foto und Video* heißt überall gleich; neues Benutzerhandbuch (docs/guide.de.md).

## 0.3.184
- Seitenwechsel: zurück zur kurzen Überblendung (lief 80 Versionen ohne weißen Moment), jetzt über einem einfarbigen Grund in der Themenfarbe. Die Variante aus 0.3.178 ließ die alte Seite verschwinden, bevor die neue gezeichnet war – ein weißer Blitz.

## 0.3.183
- **System-Seite in einer gut lesbaren Spalte** (zwei nur auf sehr breiten Bildschirmen); doppelte Zeilen entfernt.
- **Über:** ein neuer Schlusstext – mit Liebe zum Detail gemacht, kostenlos und ohne Abo (EN und DE).

## 0.3.182
- **Integrationen: beide Listen bleiben live synchron.** Schaltest du eine feste Integration unten aus, verschwindet ihre Seite sofort aus *Navigation verwalten* (an: kommt wieder); die Reihenfolge oben sortiert weiter die Liste unten.

## 0.3.181
- **Foto und Video hat ein Speichern wie jeder andere Kasten.** Die zwei Auswahlen (Startseite / Foto des Autos) werden gewählt und zusammen gespeichert; Hinzufügen und Löschen von Dateien wirken weiter sofort. Der Hinweis „wird sofort gespeichert“ entfällt.

## 0.3.180
- Datums- und Zeitfelder rutschen auf dem iPhone nicht mehr aus dem Bild (Servicebuch, Von/Bis, jedes Datum).
- Der Kilometerstand hat unter dem Bild genug Luft, wenn dort keine Kästchen stehen.
- Autowechsel: Der blaue Fokusrahmen des Schließen-Knopfs wird nicht mehr oben abgeschnitten.

## 0.3.179
- **Spritpreise (Tankerkönig) in Einstellungen → System** als optionale, eigene Karte mit deinem eigenen Key. Es ist keine Integration mehr, es gibt keine Add-on-Option und keine Umgebungsvariable dafür: nichts ist eingebaut, ohne deinen Key geht nichts an den Dienst.

## 0.3.178
- Seitenwechsel: Die alte Seite bleibt, bis die neue bereit ist, und wird sofort auf einem einfarbigen Grund ersetzt – keine Überblendung der ganzen Seite mehr (deren additive Mischung kann auf Glasflächen hell/weiß aufblitzen).

## 0.3.177
- Korrektur: Die Seitenleiste sprang auf Seiten ohne Auto um eine Zeile (die Versionszeile war dort entfernt worden); der Titel behält jetzt immer seine zweite Zeile, das Umschalten der Seiten flackert nicht mehr.

## 0.3.176
- Bodenschein unter dem Auto nur beim Standard-Auto und bei PNG-Fotos – nie hinter JPEG-Fotos oder Videos.
- Korrektur: Ein Foto auf der Startseite zeigt jetzt das *für die Startseite* gewählte (es zeigte das Foto der Autoauswahl).

## 0.3.175
- **Höchstens 5 Dateien pro Auto, Fotos und Videos zusammen** – die älteste fällt heraus (das letzte Foto nie). Die Raster zeigen immer fünf Kacheln pro Zeile, die Seite bleibt kompakt.

## 0.3.174
- Foto-und-Video-Fenster aufgeräumt: vier gleiche Kästen (Hinzufügen, Startseite, Foto des Autos, Video-Hintergrund) mit gleichem Innenabstand und saubere kleine Löschknöpfe auf den Kacheln.

## 0.3.173
- Nur Code-Formatierung.

## 0.3.172
- Dashboard-Bearbeitungsmodus: Der Knopf auf dem Bild heißt *Video oder Foto bearbeiten* und sitzt genau in dessen Mitte.

## 0.3.171
- Der Speichern-Knopf jedes Kastens beginnt genau dort, wo seine Felder beginnen (er war eingerückt).

## 0.3.170
- Speichern-Knöpfe sind wieder normale Knöpfe (nicht volle Breite), linksbündig wie auf den anderen Seiten; Löschen steht daneben, gleich hoch.

## 0.3.169
- Foto und Video: keine doppelte Einrückung mehr – der Inhalt schließt mit den anderen Kästen ab.

## 0.3.168
- **Jeder Kasten im Fahrzeugformular hat sein eigenes Speichern** (der Kasten bleibt danach offen); Foto und Video speichert weiter sofort. Medien-Kacheln und die beiden Auswahlen sind gerahmte Kästen, Videos eingeschlossen.

## 0.3.167
- **Foto und Video steht zwischen *Energie* und *Papiere & Optik*** und hat zwei Auswahlen: *Für die Startseite* (Fotos und Videos zusammen) und *Als Foto des Autos* (nur Fotos – Autoauswahl, Listen, überall wo ein Standbild gebraucht wird). Ein Video braucht weiterhin zuerst ein Foto.
- **Mehr Fahrzeugdaten:** *Erstzulassung* (daraus wird die nächste HU geschätzt – erste nach 3 Jahren, danach alle 2 – bis du einen Termin einträgst), *Motoröl*-Spezifikation und -Menge, *Sitzplätze* und *zulässiges Gesamtgewicht*.

## 0.3.166
- **Fahrzeug-Bearbeiten aufgeräumt:** alle Gruppen starten zugeklappt; *Foto und Video* ist eine eigene Gruppe, die sofort speichert (steht dabei); ein Speichern für das Formular; kompakte Kraftstoff-Auswahl ohne leere Zeile.
- **Ein Feld *Notizen*** statt zwei: *Leuchtmittel & Ersatzteile* wurde in *Notizen* übernommen (vorhandene Texte werden angehängt, die alte Spalte fällt aus der Datenbank).
- **Archivieren erklärt:** Die Verwalten-Karte sagt, was Archivieren und Löschen tun; archivierte Autos stehen ausgegraut ganz unten auf der Seite Fahrzeuge mit „Wieder aktivieren“.

## 0.3.165
- **Foto und Video ist ein eigener Bereich** auf der Fahrzeug-Bearbeiten-Seite (dasselbe Feld wie im Dashboard-Editor).
- **Ein Auto behält immer ein gewähltes Foto; ein Video ist optional obendrauf.** Beides bleibt gewählt (Listen und die Autoauswahl zeigen das Foto, das Dashboard spielt das Video). Ein Video braucht zuerst ein Foto; das gewählte Video nochmal antippen schaltet es aus.
- Fahrzeugdaten-Seite: Die Variante hat eine eigene Zeile (sie klebte am Modell); die 12-V-Batterie des Demo-Autos enthält keinen Traktionsbatterie-Text mehr.

## 0.3.164
- Das Fahrzeugfoto füllt die volle Breite des Dashboards und behält seine Proportionen; die Höhe passt sich an (kein leerer Rand an den Seiten, nichts abgeschnitten).

## 0.3.163
- Schmale Seitenleiste: Das Logo ist so breit wie die Navigationskacheln, und die Kacheln sind ebenfalls quadratisch.

## 0.3.162
- Seitenleiste: Das Logo schließt jetzt exakt mit der linken Kante der Navigation ab.

## 0.3.161
- Seitenleiste: Logo linksbündig mit dem Titel direkt daneben; die Version steht nicht mehr unter dem Titel (sie ist unten). Das Dashboard zeigt den Fahrzeugwechsel-Knopf wieder neben dem Autonamen.

## 0.3.160
- Korrektur: Rand des Reifen-Icons nutzt die Themenfarbe (helle Designs).

## 0.3.159
- **Eine Aktionsleiste in jedem Formular:** *Speichern* füllt die Zeile, *Löschen* steht direkt daneben, beide gleich hoch – unten in jedem Bearbeiten-Formular (Einträge, Reifensätze, Fahrzeug, Integrationen, Debug, Konto).
- **Reifen:** eine Spalte, jahreszeitlich getönte Karten mit leuchtendem Icon und größeren Angaben.
- **Feste Integrationen folgen der Navigationsreihenfolge** und sortieren sich live mit, wenn du oben eine Seite verschiebst.

## 0.3.158
- **Navigationsreihenfolge gilt sofort in Weiteres:** Die Reihenfolge unter Integrationen -> Verwaltung bestimmt jetzt auch die Reihenfolge in Weiteres, sofort. Der Editor endet mit zwei festen Zeilen, *Integrationen* und *Plugins*, optisch wie die anderen, aber mit ausgegrauten, nicht klickbaren Pfeilen.

## 0.3.143
- **Einstellungen sind vier Tabs:** *Design* (Farben, App-Icon, Karte), *Region*, *Navigation*, *System* – oben eine Umschaltleiste statt einer Liste (der erste Tab ist die Startseite).
- **Region: Einheiten und Währung.** Neben der Sprache gibt es ein Standard-System (*Metrisch*, *US*, *UK*) und eine Währung, und jedes Fahrzeug kann eigene haben (ein Auto in einem anderen Land). Gespeichert wird weiter alles in Basiseinheiten, du kannst also hin- und herwechseln. Bisher in den gewählten Einheiten: Home (Reichweite, Kilometerstand, letzte Fahrt, letztes Tanken, Verbrauch), die Fahrzeugkarten, die Fahrzeugdaten und die Fahrtenseite. **Listen, Eingabeformulare und der Bericht zeigen und nehmen noch km / Liter – sie folgen als Nächstes.**
- **Weiteres enthält nur, was die Leiste nicht hat:** die Gruppe „Dieses Fahrzeug“ listet jede Seite, die nicht schon in der unteren Leiste steht, mit ihrem eigenen Namen; Einträge der Leiste werden dort nicht mehr wiederholt.

## 0.3.142
- Einstellungen: der Schalter *Karte* ist in *Design* gewandert (die Karte folgt ohnehin dem Design); die Liste heißt jetzt Design, Region, Navigation, System.

## 0.3.141
- **Das kleine Mülleimer-Icon auf den Fahrzeugkarten entfällt** (ohne Text kaum lesbar). Ein Fahrzeug löschen geht über einen deutlich roten Knopf „Fahrzeug löschen“ auf der Bearbeiten-Seite des Fahrzeugs (archivierte Fahrzeuge behalten einen Text-Knopf in ihrer Liste).
- **Fahrzeugkarten sind leichter zu lesen:** statt „Termine: in 19 T“ und losen Chips gibt es zwei beschriftete Zeilen mit Icon – *Nächste HU* (Datum und wie bald) und *Wartung* (überfällig / bald fällig / alles in Ordnung) –, mit denselben Worten wie die Kästen auf Home. Eine Zeile erscheint nur, wenn es etwas zu sagen gibt.

## 0.3.140
- **Löschen-Knöpfe sind in jedem Design deutlich rot:** sie nutzten die Akzentfarbe des Designs (bei *Hellblau* blau, in roten Designs kaum zu sehen); jetzt nutzen sie das Gefahren-Rot des Designs (Tönung, kräftiger Rand, fetter Text; ebenso die runden Löschen-Knöpfe der Fahrzeugliste).

## 0.3.139
- **Die Einstellungen sind jetzt eine kurze Liste** statt einer endlosen Seite: *Design* (Farben und App-Icon), *Region* (Sprache – Einheiten und Währung sind hier geplant), *Navigation*, *Karte* und *System* (Status, Systemdienste, Backup, Werkseinstellungen). Jeder Eintrag öffnet eine eigene Seite; *Über* ist nur noch ein eigener Eintrag in Weiteres. Der Kaffee-Link der alten Einstellungsseite entfällt (um Unterstützung wird nur auf der Über-Seite gebeten). Navigation hat ein eigenes Icon (Menü).

## 0.3.138
- Der Bodenschein unter dem Standard-Auto ist etwas kräftiger und sitzt direkt unter dem Auto.

## 0.3.137
- Home: die vier Kästen schweben jetzt – sie ragen 12 px ins Bild und bleiben 12 px vom linken und rechten Bildrand entfernt (derselbe Abstand), hängen also nicht mehr am Raster. Gleich bei Foto, Standard-Auto und Video.

## 0.3.134
- Home: die vier Kästen (oben Zündung und Türen, unten HU und Wartung) ragen sichtbarer ins Bild – etwa 7 % der Bildbreite bei Fotos und Videos, 5 % beim Standard-Auto – und lassen das Bild durch ihr Glas scheinen. Geprüft mit freigestelltem Auto, breitem Foto, Frontansicht auf Weiß und einem Video.

## 0.3.133
- Home: weniger Luft ums Standard-Auto (das Auto füllt jetzt 84 % seines Bildes statt 70 %), die alten zusätzlichen Ränder ums Bild entfallen; die Überlappung der Kästen ist kleiner (Standard-Auto 4 %).

## 0.3.132
- Home: die vier Kästen ragen immer ein Stück ins Bild, im Verhältnis zu dessen Größe (Standard-Auto 7 %, Video 5 %, Foto 3 % der Breite – das Standard-Auto hat dafür freie Fläche im Bild). Der Bodenschein des Standard-Autos sitzt direkt unter dem Auto.

## 0.3.131
- Das Standard-Auto-Bild trägt seine freie Fläche jetzt im Bild selbst (das Auto ist kleiner auf einer gleich großen Fläche, ringsum 15 % frei) und nutzt die volle Breite; Fotos bekommen den Radius einer Karte.

## 0.3.129
- Home: ein hochgeladenes Foto nutzt die **volle Breite**, die die Seite anbietet (links und rechts so viel wie möglich); nur das freigestellte Standard-Auto behält seine Luft ringsum.

## 0.3.128
- Fotos mit eigenem Hintergrund (nicht freigestellt) bekommen abgerundete Ecken wie eine Karte.

## 0.3.127
- **Ein geändertes Foto erscheint sofort:** die Adresse des Bildes trägt jetzt den Namen der gewählten Datei, der Browser zeigt also nach einem Wechsel nicht mehr eine Stunde lang das vorherige Foto.

## 0.3.126
- Home-Video: sein erstes Bild erscheint, sobald es geladen ist – es gibt nie eine leere Fläche oder ein Foto vor dem Start des Videos. Ein Foto springt nur ein, wenn das Video nicht abgespielt werden kann.

## 0.3.125
- Home: Fotos und das Standard-Auto haben **keinen Verlauf** mehr (nur Videos gehen in die Seite über) und sitzen mit mehr Luft ringsum, damit die Kästen nicht am Bild kleben.

## 0.3.124
- Home: das Standard-Auto und Fotos bekommen Luft auf allen vier Seiten (sie waren über die volle Breite gezogen und die Kästen berührten sie); nur ein Video reicht leicht unter die Kästen.

## 0.3.123
- Home-Kästen: jeder nimmt nur den Platz, den er braucht (nie so hoch wie sein Nachbar), und sie ragen ein paar Pixel in den ausgeblendeten Rand des Bildes – das Auto selbst bleibt frei; weiterhin Glas.

## 0.3.122
- **Home: die vier Kästen sitzen in den Ecken um das Bild – bei Foto, Standard-Auto und Video gleich.** Darüber: Zündung (links) und Türen & Fenster (rechts); darunter: Nächste HU (links) und Wartung (rechts). Kompakte Glas-Kästen mit linksbündigem Text (der rechte jedes Paars rechtsbündig), nicht mehr gestreckt. Jeder erscheint nur mit Daten; hat eine Reihe nur einen Kasten, steht er mittig. Das Bild nimmt die volle angebotene Breite, das Video behält seinen weichen Verlauf.

## 0.3.119
- **Video: die Kästen halten Abstand zum Auto.** Sie ragen nicht mehr ins Bild (0.3.116 ließ sie das Auto berühren), sondern stehen mit deutlichem Abstand darüber. Mit einem echten Auto-Video getestet: der Verlauf oben, unten und an den Seiten geht ohne sichtbaren Rahmen in die Seite über, und nichts verdeckt das Auto. (0.3.117 / 0.3.118: längere Verläufe an den Rändern, Kästen wurden von einem allgemeinen Versatz nach unten geschoben – behoben.)

## 0.3.116
- **Video: Glas-Kästen ragen ein Stück ins Bild.** Die zwei Kästen und Zündung / Türen sind wieder Glas (unscharf, durchscheinend) und überlappen den oberen Rand des Videos ein paar Pixel; das Video behält seine natürliche Breite.

## 0.3.115
- **Video-Verlauf ist zurück („Angleichen“):** der eigene Hintergrund des Videos wird aus seinen Randfarben als Band über die ganze Breite nachgebaut, das oben und unten in die Seite ausblendet, und das Video blendet an den Seiten aus – so geht es wie im Original-Dashboard in die Seite über. Der Aufbau bleibt wie in 0.3.114 (natürliche Breite, Kästen darüber, Reichweite darunter).
- **Kein Bild hinter einem laufenden Video:** das Foto wird weder hinter noch vor dem Video gezeigt; es springt nur ein, wenn das Video nicht abgespielt werden kann.

## 0.3.114
- **Video auf Home wie im Original-Dashboard** (Korrektur zu 0.3.113): das Video nimmt die Breite, die die Seite anbietet – nicht mehr –, behält seine Proportionen und blendet weich in die Seite aus. Nichts liegt mehr darauf: die zwei Kästen und Zündung / Türen & Fenster stehen darüber (Zündung links, Türen rechts), die Reichweite darunter. Die Kästen „Nächste HU“ / „Wartung“ verschwinden weiterhin, wenn sie leer wären.

## 0.3.113
- **Video auf Home, volle Breite und dahinter:** ein Video füllt jetzt die ganze Breite (ein Stück über den Bildschirmrand hinaus, damit nichts davon fehlt), ohne Verlauf oder Schatten drumherum. Kennzeichen, Name, die zwei Kästen, Zündung / Türen und die Reichweite liegen davor, und das Bild reicht nach oben hinter sie und nach unten hinter die Reichweite – ein hohes Video schiebt die Seite nicht mehr nach unten. Auf einem breiten Bildschirm bleibt es in seiner Spalte. Fotos behalten ihre weichen Kanten.
- Die Hintergrund-Auswahl für Videos heißt jetzt *Original* (wie aufgenommen), *Schwarz* (Schwarz verschwindet) und *Transparent*; der alte Aufbau aus den Randfarben („Angleichen“) entfällt.

## 0.3.111
- **Karte folgt dem Design:** bei einem hellen Design (Hell, Hellblau oder Tag / Nacht am Tag) startet die Standort-Karte hell und ist auf die Farben des Designs abgestimmt (bei Hellblau ein Hauch Blau); bei einem dunklen Design startet sie dunkel. Der Sonne-/Mond-Knopf übersteuert das weiterhin und wird gemerkt. Vorher erzwangen helle Designs eine helle Karte und der Knopf tat dort nichts.

## 0.3.110
- **Über-Seite mittig:** Titel, Abschnittsüberschriften, die Fahrzeugkarten mit ihren Plugin-Zeilen, die Quellenangaben und der Autor-Kasten sind jetzt alle zentriert.

## 0.3.109
- **Eigene Identität:** die Über-Seite und die READMEs beschreiben Car Assistant nicht mehr als „Home Assistant für dein Auto“. Es ist ein eigenständiges Logbuch und Dashboard; Home Assistant ist nur der Ort, an dem es läuft.

## 0.3.108
- **Karte zeigt „Access blocked“ – behoben:** OpenStreetMap weist Kachel-Anfragen ohne erkennbaren Referer oder User-Agent ab – genau das sendet ein Browser in der Home-Assistant-App (wir hatten dem Browser außerdem gesagt, keinen Referer zu senden). Jetzt holt Car Assistant die Kacheln selbst: es gibt sich zu erkennen (`CarAssistant/<Version> (+Projektadresse)`), nutzt höchstens zwei Verbindungen, behält jede Kachel eine Woche auf der Platte (Zwischenspeicher auf 200 MB begrenzt, eine veraltete Kachel wird genutzt, wenn kein Internet da ist) und der Browser spricht nur noch mit der App. Nebenbei sieht OpenStreetMap weder dein Handy noch deine Home-Assistant-Adresse mehr, und die Seite braucht keine Ausnahme für fremde Hosts mehr (strengere Content-Security-Policy). Weiterhin standardmäßig aus.

## 0.3.107
- Roadmap und Arbeitsnotizen: Einheiten (Meilen, Gallonen, mpg, °F, psi) und Währungen je Fahrzeug sind geplant; neuer Code hält Werte in Basiseinheiten und vermeidet fest eingebaute „km“, „€“ und „L“.

## 0.3.106
- **„Webseite bearbeiten“ auf Home:** der Knopf unten (vorher *Widgets bearbeiten*) öffnet jetzt ein Fenster mit allem: *Widgets anordnen* (verschieben, Größe ändern, ausblenden) und *Foto & Video* (hochladen, wählen was Home zeigt, löschen, Hintergrund des Videos). Nach einem Upload oder Löschen öffnet sich das Fenster wieder. Der Link *Fotos & Videos* im Fahrzeugformular entfällt; das Foto-Feld dort funktioniert weiter.
- **Behoben:** der „Angleichen“-Hintergrund eines Videos ragte über den Bildschirm hinaus und machte die Seite breiter als das Handy (herausgezoomt / seitwärts scrollbar). Er wird jetzt abgeschnitten.

## 0.3.104
- **Nächste HU und Wartung nur, wenn es etwas zu zeigen gibt:** die zwei Kästen über dem Auto erscheinen nur, wenn das Auto einen HU-Termin bzw. Wartungsaufgaben hat (und die Seite eingeschaltet ist). Ohne beides verschwinden sie und der Platz über dem Auto wird freigegeben.

## 0.3.103
- **Kopfbereich von Home einzeilig:** Marke · Modell · Baujahr und „gerade eben“ stehen jetzt nebeneinander statt in zwei Zeilen (nur auf einem wirklich schmalen Bildschirm wird umgebrochen).

## 0.3.102
- **Fotos und Videos je Fahrzeug.** Fahrzeug → Bearbeiten → *Fotos & Videos*: PNG, JPG, WebP, MP4, MOV oder WebM hochladen (Fotos bis 10 MB, Videos bis 40 MB); der Typ wird am Inhalt der Datei erkannt, nicht am Namen. Jedes Auto behält seine letzten 5 Fotos und 5 Videos – der 6. Upload löscht das älteste samt Datei. Bild antippen zeigt es auf Home, mit dem x löschen.
- **Ein Video läuft einmal**, wenn Home zu sehen ist, und bleibt dann auf dem letzten Bild stehen (auch nach Verlassen und Zurückkommen); antippen spielt es nochmal. Es pausiert, solange es verdeckt ist, und fällt aufs Foto zurück, wenn es nicht läuft (Stromsparmodus, Fehler, „Bewegung reduzieren“). Wähle, wie sein Hintergrund in die Seite übergeht: *Angleichen* (Farben vom Rand des Videos, empfohlen), *Schwarz* oder *Transparent* (Video mit echter Transparenz).
- **Weiche Kanten:** Fotos und Videos blenden an allen Seiten in den Hintergrund aus statt in einem harten Rahmen zu enden.
- Vorhandene Fotos wandern automatisch in die Bibliothek. Videos werden in Teilen ausgeliefert (das braucht das iPhone).

## 0.3.100
- **Demo-Autos melden alle 5 Sekunden** (vorher 10), Änderungen erscheinen auf Home schneller.

## 0.3.99
- **Navigations-Markierung glitt beim Seitenwechsel doppelt:** die Markierung rutschte per Skript an ihren Platz, zusätzlich zum Überblenden des Browsers – es sah aus, als käme eine zweite Leiste und glitte nochmal. Jetzt macht es ein einziger Mechanismus: wo der Browser animierte Seitenwechsel kennt, ist die Markierung eine eigene Ebene und gleitet einmal vom alten zum neuen Eintrag (das Skript bleibt nur als Ersatz für ältere Browser).

## 0.3.98
- **Langes Drücken öffnet nie von selbst eine Seite:** wer ein Navigations-Icon, ein Widget oder eine Listenzeile gedrückt hielt, bekam in der Home-Assistant-App die Link-Vorschau des Systems („401: Unauthorized“) und das Menü Öffnen / Kopieren / Teilen. Links verhalten sich auf Touchscreens jetzt wie Knöpfe: keine Vorschau, kein Menü, kein Ziehen des Links.
- **Langes Drücken auf ein Widget öffnet den Widget-Editor** (wie auf dem Home-Bildschirm eines Handys, mit kurzem Vibrieren): sofort verschieben, Größe ändern oder ausblenden; das Loslassen öffnet das Widget nicht.

## 0.3.97
- **Doppelte Navigationsleiste nach einem Seitenwechsel (Handy):** beim Überblenden wurden die alte und die neue Leiste übereinander gezeigt, und das Glas verlor seine Unschärfe, solange es nur ein Bild war. Die Leiste (und die Seitenleiste am Tablet) ist jetzt eine eigene Ebene: die alte Kopie verschwindet, sobald die neue Seite fertig ist, und nichts wird überblendet.
- Versionierte Dateien werden ein Jahr zwischengespeichert, eine Style-Änderung kommt daher immer mit neuer Versionsnummer (die Seitenadresse trägt sie).

## 0.3.96
- **Deutlich schneller bei vielen Daten** (getestet mit 15 Autos und je Tausenden Einträgen; jede Seite antwortet jetzt in etwa 0,1 s oder schneller):
  - Die Wartungsprüfung liest nicht mehr für jede Aufgabe das ganze Serviceheft neu (Startseite einer großen Garage: 1,8 s → 0,08 s).
  - Lange Listen zeigen 50 Einträge je Seite (Zurück / Weiter, Gesamtzahl) statt alles auf einmal (Tankliste: 2,7 s und 4 MB → 0,1 s).
  - Eine Strecke mit zigtausend GPS-Punkten wurde in quadratischer Zeit gezeichnet (35 s) und ist jetzt sofort da; das Bild nutzt höchstens 1.500 Punkte, die GPX-Datei behält alle.
  - Ein Plugin, das alle paar Sekunden meldet, erzeugt jetzt eine Kilometerstand-Zeile pro Tag statt einer pro Kilometer.
  - Indizes für jede Fahrzeug-Tabelle, gzip für Seiten und Styles (eine Seite schrumpft auf etwa ein Fünftel), lange Zwischenspeicherung versionierter Dateien, tägliche Datenbankpflege, sicherere SQLite-Einstellungen (`synchronous=NORMAL`, Wartezeit, Cache).
- **Elektroautos sagen „Ladestationen“** statt „Tankstellen“ (eine Integration für Ladepunkte folgt noch).
- Doppelte Style-Regeln zwischen `app.css` und `pc-core.css` zusammengeführt; das Design-Handbuch hat ein Kapitel zu Geschwindigkeit/Datenmenge und Einträge für die Über-Seite und den Seitenwechsel.

## 0.3.95
- **Neue Seite „Über“** (Weiteres → Allgemein): Version, Datenbank- und Dateigröße, Anzahl Fahrzeuge und Einträge und je Fahrzeug, welche Plugins und Integrationen installiert sind – mit Version, Autor und wann ein Plugin zuletzt Daten geschickt hat –, dazu die Dienste der App, die verwendeten Bibliotheken, die Quellenangaben und ein kurzer Hinweis zum Autor mit optionalem Kaffee-Link. Nur diese Seite bittet um Unterstützung.
- Das Demo-Plugin nennt jetzt seinen Autor.

## 0.3.94
- **Logo in der Seitenleiste:** das Auto ist das Originalbild, freigestellt (transparenter Hintergrund, gleiche Pixel, gleiche Stelle); der Rahmen ist neu gebaut: so groß und so rund wie ein Navigationseintrag, mit dünnem Rand, der dem Theme folgt (Akzent zu Grün), statt des dicken eingebackenen. Ein hochgeladenes Icon wird ganz gezeigt. Klick: bei einem Fahrzeug zurück zum Dashboard, bei mehreren zur Liste aller Fahrzeuge.

## 0.3.93
- **Tanken oder Laden – pro Fahrzeug.** Jedes Fahrzeug hat eine „Energie-Ansicht“ (automatisch / Tanken / Laden; Fahrzeugformular → Energie). Elektroautos sagen standardmäßig *Laden* (Ladeprotokoll, Ladepunkt, Energie in kWh, Ladezustand), alles andere *Tanken*; ein Plug-in-Hybrid lässt sich von Hand umstellen. Es ändern sich nur die Wörter, und zwar für jedes Fahrzeug einzeln.
- **Warnstufen pro Fahrzeug.** Lege fest, ab wann Balken und Symbol unter dem Auto gelb und rot werden – nach Füllstand (Standard 25 % / 10 %) und/oder nach Reichweite in km. Der schlechtere Wert zählt.
- **Demo-E-Auto:** ein zweites Demo-Auto (elektrisch), das bei leerer Batterie einsteckt und lädt – Laden, eingesteckt, Leistung, Restminuten, Limit – alles über die Plugin-Schnittstelle.
- **Doku:** was ein Plugin ist (jede Verbindung zu einem Auto, der einzige Weg, und was dahinter stecken kann) in der Plugin-Doku und in `CLAUDE.md`.

## 0.3.92
- **Was das Auto meldet, zählt mit:** die eigenen Meldungen des Autos und ein vom Auto gemeldeter Service, der in 30 Tagen / 1.000 km fällig oder überfällig ist, zählen jetzt in der Kachel „Sicherheit“ und im Warnpunkt auf dem Sicherheits-Tab und erscheinen auf der Sicherheits-Seite („Fahrzeugmeldungen“) und im gleichnamigen Home-Widget.

## 0.3.91
- **Connector-API: die typischen Fahrzeugsignale.** Neue Lesefelder: Kühlmittel- und Öltemperatur, Innenraum- und Solltemperatur, Klima an/aus, Fahrtrichtung, Verbrauch, der eigene Service des Autos (Tage / km), eingesteckt, Ladelimit und Restminuten, Feststellbremse und Licht (Abblend-, Fernlicht, Warnblinker, Standlicht). Sie erscheinen im Widget „Fahrzeugdaten live“ auf Home, wenn ein Plugin sie sendet.

## 0.3.90
- **Mehr Lesefelder in der Connector-API:** `speed_kmh`, `outside_temp_c`, `battery_12v_v`, `battery_pct`, `charging`, `charge_power_kw`, `tyre_pressure_bar` (pro Rad) – auf Home in einem Widget „Fahrzeugdaten live“, das nur erscheint, wenn ein Plugin davon etwas sendet.
- **Erste Schnittstelle zum Fahrzeug hin: Debug.** Eine Person schaltet Debug pro Fahrzeug ein oder aus (Integrationen & Plugins → Debug & Protokoll). Das Plugin liest den Schalter (`GET /control`, auch in jeder Daten-Antwort) und sendet, solange er an ist, Log-Zeilen (`POST /logs`); ist er aus, werden sie abgelehnt (`409`) und nichts wird gespeichert. Die Seite *Debug & Protokoll* zeigt die neuesten 1000 Zeilen. Das Plugin des Demo-Autos macht genau das.
- API-Dokumentation erweitert (EN und DE).

## 0.3.89
- **Home zeigt live, was das Auto meldet.** Home und Sicherheit aktualisieren sich von selbst (ohne Neuladen) für jedes Fahrzeug, das Daten von einem Plugin bekommt oder ein Connector-Token hat – Türen, Fenster, Reichweite, Tankstand, Position, Zündung, Verriegelung.
- **Neu: Meldungen vom Auto.** Die Connector-API nimmt `warnings` an (`{"code": "Text"}`, `null` entfernt einen Code), zum Beispiel eine Reifendruck- oder Motorwarnung; Home zeigt sie im Widget „Fahrzeugmeldungen“, solange sie aktiv sind.
- **Das Demo-Auto spricht jetzt über die echte Schnittstelle:** alle 10 Sekunden sendet es per POST an `/api/v1/vehicles/<id>/data` mit eigenem Token – wie ein Plugin im Auto – dazu ab und zu eine Fahrzeugmeldung, die kommt und wieder geht.

## 0.3.88
- **Demo-Auto: mehr Geschehen, weniger Schreiben.** Im Stand öffnen und schließen sich Türen und Fenster aller Art zufällig; beim Fahren ändern sich bei jeder Meldung Position, Kilometerstand, Reichweite und Tankstand. Der Kilometerstand hat pro Fahrt einen Eintrag, der beim Fahren aktualisiert wird, statt bei jeder Meldung einen neuen.

## 0.3.87
- **Demo-Auto: nur was ein Connector sendet, ohne Neuladen.** Das Demo-Auto meldet jetzt nur, was ein echtes Plugin senden kann (Position, Kilometerstand, Tankstand, Reichweite, Zündung, Türen, Fenster, Verriegelung) – es legt keine Fahrten oder Tankbuch-Einträge mehr an. Home und Sicherheit aktualisieren nur die geänderten Teile statt neu zu laden, die Navigation blitzt also nicht mehr und „Gespeichert“ kommt nicht ständig zurück.

## 0.3.86
- **Demo-Auto wie ein verbundenes Auto:** neue Werte alle 10 Sekunden, und das Auto hat jetzt einen „Demo connector“ mit eigenem Token, dessen „zuletzt genutzt“ bei jeder Meldung aktualisiert wird – das Auto führt es unter „Integrationen & Plugins“ als eingerichtetes Plugin – es sieht aus, als wäre ein Plugin installiert und liefert Daten.

## 0.3.85
- **Demo-Auto sendet Live-Daten:** das Demo-Auto verhält sich jetzt wie ein verbundenes Auto – alle paar Sekunden entriegelt es, öffnet eine Tür, startet, fährt eine Strecke (Position, Kilometerstand, Tankstand und Reichweite ändern sich), hält an, speichert die Fahrt (mit Strecke), tankt bei wenig Sprit, verriegelt wieder und öffnet ab und zu ein Fenster. Die Daten laufen über denselben Weg wie bei einem echten Connector (`connectors.ingest`), und Home und Sicherheit laden sich selbst neu, wenn sich etwas ändert – ideal, um jedes Widget live zu sehen. Das machen nur Demo-Autos.

## 0.3.84
- **Farben in jedem Theme:** der Warnpunkt auf einem Tab hatte einen festen dunklen Ring (falsch bei hellen Themes), außerdem waren einige Grüntöne, das „bald“-Gelb und Fokus-/Zieh-Umrisse feste Farben – alles folgt jetzt den Theme-Werten.

## 0.3.83
- **Flackern zwischen Seiten:** eine Bildschirmaufnahme aus der Home-Assistant-App zeigte bei dunklen Themes bei jedem Seitenwechsel ein weißes Einzelbild. Seiten wechseln jetzt mit kurzer Überblendung (`@view-transition`), die die alte Seite stehen lässt, bis die neue bereit ist (braucht ein aktuelles iOS / einen aktuellen Browser; ältere verhalten sich wie bisher).

## 0.3.82
- **„Gespeichert“ schwebt:** die grüne Bestätigung schiebt die Seite nicht mehr unter die Home-Assistant-Kopfleiste (das quetschte den Inhalt), sondern schwebt oben und blendet nach ein paar Sekunden aus. Fehlermeldungen bleiben mit sauberem Abstand in der Seite.

## 0.3.81
- **Kein Flackern mehr in der Home-Assistant-App:** die Ränder für „eingebettet“ werden vor dem ersten Zeichnen gesetzt (ein winziges Skript im Seitenkopf statt eines verzögerten), und das Theme Tag / Nacht lädt seine hellen Farben als normales blockierendes Stylesheet statt per `@import`.

## 0.3.80
- **Tag-/Nacht-Farben:** neues Theme „Tag / Nacht“ (Einstellungen → Farben): der originale rote Look, der automatisch dem Gerät folgt – hell am Tag, dunkel in der Nacht – auf jedem Gerät, das sein Erscheinungsbild umschaltet.

## 0.3.79
- **Listen auf dem Handy:** Serviceheft, Tanken, Fahrten, Termine, Wartungsplan, Teile usw. laufen nicht mehr aus dem Bild – jeder Eintrag ist eine kleine Karte mit Beschriftung über den Werten. Der Wartungsplan zeigt „zuletzt erledigt“ nicht mehr doppelt; „Typische Punkte anlegen“ wird auf kleinen Bildschirmen zum Icon.

## 0.3.78
- **Helle Farben:** zwei neue Themes, „Hell“ (roter Akzent) und „Hellblau“, unter Einstellungen → Farben. Die ganze App folgt (Karten, Tab-Leiste, Chips, Karte ohne dunklen Filter), ebenso die Browserfarben (`color-scheme`, Statusleiste). Eine Theme-Datei kennzeichnet sich mit `/* scheme: light */` in der ersten Zeile als hell.

## 0.3.77
- **Demo-Auto:** auf der Seite „Neues Fahrzeug“ legt „Demo-Auto anlegen“ ein erfundenes Fahrzeug mit zwei Jahren Daten in allen Bereichen an (Service, Tanken, Fahrten mit Strecke, Termine in allen Zuständen, Aufgaben, Teile, Reifen, Zähler, Live-Werte), um die ganze App auszuprobieren.
- **Home-Assistant-Mobil:** in der App entfallen die zusätzlichen Ränder oben und unten, die Seiten verschenken keinen Platz mehr und wirken nicht mehr gequetscht.

## 0.3.76
- **Erster Start:** zuerst eine Sprach-Auswahl als Dropdown; die Wahl lädt die Seite in dieser Sprache neu (Willkommenstext, Hinweis, dass man es später in den Einstellungen ändern kann, und der Weiter-Knopf).
- **Fahrzeug anlegen / bearbeiten:** Icon-Karten statt eines langen Formulars - *Dein Fahrzeug* (Name, Kennzeichen, Baujahr, Marke, Modell, Kraftstoff als große Icon-Kacheln, Kilometerstand, Foto, Wartungsvorschläge) ist immer offen; Identifikation, Technik, Energie, Papiere und die Home-Assistant-Verknüpfung sind einklappbare Gruppen, beim Anlegen geschlossen. Ein kurzes Willkommensbanner erklärt, dass nur der Name nötig ist.
- **Farbauswahl:** die Theme-Namen bleiben innerhalb ihrer Kacheln.

## 0.3.75
- **Weiteres hat vier Oberbegriffe** (Fahrzeug, Wartung, Fahrten & Tanken, Sicherheit) statt einem Dutzend Einzelseiten. Jede Oberbegriff-Seite zeigt eine Umschaltleiste zwischen ihren Seiten (Fahrzeug: Daten · Dokumente · Reifen; Wartung: Termine · Plan · Servicebuch · Teile · Umbauten; Fahrten & Tanken: Fahrten · Tanken · Kilometer · Auswertung). Adressen und Funktionen sind unverändert; für ein Fahrzeug ausgeblendete Funktionen fehlen in der Leiste.

## 0.3.74
- **Fahrzeugdaten, Reihenfolge und Logik:** Identität (Marke, Modell, Baujahr, Herstelldatum, Typ, Kilometerstand, FIN zuletzt als breite Kachel), Technik (Motor, die beiden Kennbuchstaben nebeneinander, Antrieb und Getriebe nebeneinander, Karosserie), Energie, Papiere (Kennzeichen, HSN/TSN, Farbe und Farbcode als getrennte Kacheln, Schlüsselnummern breit). Das Formular folgt derselben Reihenfolge; der Name nimmt die ganze Zeile.

## 0.3.73
- **Fahrzeugdaten in zwei Spalten,** auch auf dem Handy: jeder Wert ist eine kompakte Kachel (kleine Beschriftung mit Icon darüber, Wert darunter); lange Werte (FIN, Motor, Schlüsselnummern) nehmen die ganze Zeile.

## 0.3.72
- **Fahrzeugdaten:** Tankgröße, Akkukapazität und 12-V-Batterie sind drei getrennte Felder in einer eigenen Gruppe *Energie* (Kraftstoff, Tankgröße in L, Akkukapazität in kWh, 12-V-Batterie). Die Reichweiten-Zeile auf Home zeigt die verbleibenden Liter (bei Elektroautos kWh).

## 0.3.71
- **Farben sind Tokens:** jede Akzent- und Statusfarbe im CSS ist ein Token (`--accent`, `--accent-rgb`, `--ok-rgb` ...). Ein **Theme** ist eine kleine CSS-Datei in `static/themes/`, die nur diese Tokens überschreibt - Aufbau und Funktionen bleiben gleich (Einstellungen → Farben; *Ozean* und *Sonnenuntergang* liegen als Beispiele bei). Ein Test verhindert, dass feste Farben wieder einschleichen.
- **Ein Knopf-System:** eine einzige Definition (Radius `--r-m`, moderner roter Verlauf für primär, rot umrandet für danger) und eine Regel für runde Icon-Knöpfe; alte doppelte Karten-, Knopf- und Tabellenregeln entfernt.
- **Design-Handbuch** in `docs/design.md` (EN) und `docs/design.de.md` (DE): Tokens, Breakpoints, Bausteine, Verhaltensregeln und eine Checkliste.
- **Seitenköpfe:** eine ruhigere Titelgröße auf allen Seiten; der Titel schrumpft, bevor er den Aktionsknopf aus dem Bildschirm schiebt.

## 0.3.70
- **Reifen:** jeder Satz ist eine Karte (Saison-Icon, Montiert-Marke, Kacheln für Größe, Saison, DOT und Lagerort, Notizen, Montieren-Knopf) - auf breiten Bildschirmen zwei nebeneinander. Das Eingabeformular ist modern: eine Saison-Auswahl mit Icons, große Felder mit Beispielwerten und ein klarer Speichern-Knopf.

## 0.3.69
- **Mitgelieferte Funktionen pro Fahrzeug ausblenden:** unter *Erweiterungen* jedes Fahrzeugs eine Liste der mitgelieferten Funktionen (Reifen, Teile, Dokumente, ...) mit je einem Schalter. Eine ausgeblendete Funktion verschwindet nur bei diesem Fahrzeug aus Navigation, Home, Weiteres und den Warnpunkten; andere Fahrzeuge behalten sie. Die systemweiten Schalter bleiben unter Einstellungen → Systemdienste.

## 0.3.68
- **Listenseiten** (Service, Fahrten, Tanken, Termine, Wartung, Reifen, Teile, Umbauten, Zähler): das Eingabeformular ist hinter einer klaren „+ Hinzufügen“-Leiste eingeklappt, eine leere Liste zeigt einen richtigen Leerzustand statt einer losen Zeile.

## 0.3.67
- **Live-Bearbeitung der Home-Widgets:** *Widgets bearbeiten* macht Home selbst zum Editor. Ein Widget am Griff greifen: es wird mit weißer Kontur angehoben, ein weißer gestrichelter Rahmen zeigt, wo es landet, die anderen rutschen zur Seite (die Seite scrollt, wenn man es nah am oberen oder unteren Rand hält). Den roten Balken am rechten Rand ziehen, um es klein oder breit zu machen, auf das Auge tippen, um es auszublenden. Alles wird sofort gespeichert; ausgeblendete Widgets bleiben beim Bearbeiten sichtbar (abgedunkelt). Die eigene Editor-Seite bleibt als Rückfall.

## 0.3.66
- **Home-Widgets:** die gemischten Kacheln und Karten sind jetzt einheitliche Widgets in einem Zwei-Spalten-Raster (klein = halbe Zeile, breit = ganze Zeile; Zeilen sind immer gleich hoch). Widgets ohne Daten erscheinen nicht („Braucht Aufmerksamkeit“ nur, wenn etwas fällig ist).
- **Widgets bearbeiten** (Knopf unten auf Home): anzeigen oder ausblenden, klein oder breit, nach oben und unten verschieben - pro Fahrzeug gespeichert - und ein „+“-Eintrag, der zu den Integrationen des Fahrzeugs führt, woher weitere Widgets kommen werden. Das Kilometerstand-Formular auf Home entfällt (dafür gibt es die Kilometerstand-Seite).
- Die Versionszeile ganz unten erscheint jetzt nur noch in *Weiteres*.

## 0.3.65
- **Home-Hero, nur Kilometerstand:** das Icon ist ein Kilometerzähler (kein Tacho) und grün.

## 0.3.64
- **Home-Hero, nur Kilometerstand:** Beschriftung etwas tiefer und näher an der Zahl.

## 0.3.63
- **Home-Hero, nur Kilometerstand:** am Auto angedockt (der Schein unter dem Auto liegt hinter der Beschriftung), darunter der übliche Blockabstand.

## 0.3.62
- **Home-Hero, nur Kilometerstand:** ohne Kasten - kleine Beschriftung mit Tacho-Icon und darunter die große Zahl, zentriert unter dem Auto.

## 0.3.61
- **Home-Hero, Reichweite:** unter dem Balken „noch ca. 38,1 L im Tank · Reichweite laut Fahrzeug“ (Liter nur, wenn die Tankgröße eingetragen ist) und „zuletzt: 13.11. 16:04“ - statt „gerade eben“.
- **Home-Hero, nur Kilometerstand:** in einer Glaskarte mit Tacho-Icon (und dem Tankstand mit Zapfsäulen-Icon, wenn bekannt).

## 0.3.60
- **Home-Hero:** Die große Zahl unter dem Auto ist die vom Auto gemeldete *Reichweite* mit Tankstand (Zapfsäulen-Icon, bernsteinfarben bei fast leerem Tank) und der Zeit der letzten Meldung. Ohne Reichweite ist es der Kilometerstand; die Kilometerstand-Kachel erscheint nur, wenn die Reichweite die große Zahl ist, damit nichts doppelt steht.
- Unter dem Namen: die Modellzeile und eine eigene Zeile „letztes Signal“ mit dem grünen Punkt (nur, wenn das Auto etwas gemeldet hat).

## 0.3.59
- **Home auf Tablet / Desktop:** Auto-Spalte und Karten-Spalte sind 50 / 50 geteilt.

## 0.3.58
- **Home auf Tablet / Desktop:** die Spalte mit dem Auto ist nicht mehr gequetscht - die breite Seitenleiste mit Beschriftung beginnt jetzt bei 1280 px (darunter nur Icons), und Home nutzt denselben Rand (14 px), Spaltenabstand (14 px) und dieselbe Oberkante (18 px) wie *Weiteres*.

## 0.3.57
- **Fahrzeug löschen:** Papierkorb-Knopf auf jeder Karte in *Fahrzeuge* (auch bei archivierten) mit einem Bestätigungsdialog in der App, der auflistet, was gelöscht wird; alles, was zum Fahrzeug gehört, wird entfernt (Daten, Dateien, Foto, Tokens, Anbindungen), andere Fahrzeuge bleiben unberührt.
- **Fahrzeuge-Seite:** gleichmäßige Abstände zwischen den Karten und das Autobild auf jeder Karte.

## 0.3.56
- **Neue 404-Seite:** große 404 mit Farbverlauf und einem Auto auf bewegter Straße, ein kurzer Hinweis (umbenannte Fahrzeuge haben eine neue Adresse), die angeforderte Adresse und Knöpfe zu Übersicht und Fahrzeuge.

## 0.3.55
- **Home ohne Modellzeile:** mehr Luft zwischen Name und den Chips HU / Wartung, und das Auto sitzt näher an den Chips.

## 0.3.54
- **Home auf dem Handy:** Der obere Rand des Heros (Kennzeichen oder Name) liegt 18 px vom oberen Rand, wie der Kopf jeder anderen Seite (vorher 14 px).

## 0.3.53
- **Kein Kennzeichen, kein Kennzeichen-Chip:** ohne Kennzeichen zeigt Home oben nichts an (der gestrichelte Platzhalter entfällt).
- Ein einzelner Strich in einem Textfeld (Kennzeichen, Marke, …) gilt als leer und wird nicht gespeichert.

## 0.3.52
- **Handy:** Der Hauptknopf im Seitenkopf (Bearbeiten, Fahrzeug hinzufügen) ist ein reiner Icon-Kreis und wird am rechten Rand nicht mehr abgeschnitten.

## 0.3.51
- **Fahrzeugdaten:** *Bearbeiten* ist ein Knopf oben rechts im Seitenkopf (statt eines kleinen Stifts in der Karte).

## 0.3.50
- **Weiteres:** der Eintrag heißt jetzt *Fahrzeugdaten*.
- **Fahrzeugdaten-Formular** ist wie die Seite selbst gruppiert (Fahrzeug, Technik, Papiere & Optik, Sonstiges) und zeigt neutrale Beispielwerte als Platzhalter.

## 0.3.49
- **Zurück-Knopf auf dem Handy:** die rote Zeile „‹ Weiteres“ ist durch einen runden Glas-Knopf mit Pfeil vor dem Seitentitel ersetzt (spart eine Zeile, passt zu den anderen runden Knöpfen).

## 0.3.48
- **Tab-Leiste auf dem Handy folgt den Radius-Werten:** äußerer Radius = Radius der Kachel + Innenabstand, dadurch sind Leiste und markierter Tab wieder konzentrisch.

## 0.3.47
- **Auto wechseln in Weiteres belässt dich in Weiteres:** du landest in der Weiteres-Liste (oder auf derselben Seite) des anderen Autos statt auf dessen Startseite.

## 0.3.46
- **Überall auf derselben Linie:** Der Seitentitel steht auf jeder Seite in einer festen 44-px-Zeile, und neben der Weiteres-Liste beginnt die erste Karte der Seite exakt auf derselben Linie wie die erste Karte der Liste (geprüft bei Fahrzeugdaten, Fahrzeuge, Dokumente, Reifen, Termine, Einstellungen, Integrationen).

## 0.3.45
- **Auto-wechseln-Icon ist ein echter Kreis** (40 × 40 px, rundum 9 px zum Kartenrand): die globale Button-Regel hatte es verzogen.

## 0.3.44
- **Überall weniger runde Ecken:** Radius-Werte verkleinert (Karten 22 → 16 px, mittel 16 → 12 px, klein 12 → 8 px); runde Chips und die schwebende Tab-Leiste bleiben rund.

## 0.3.43
- **Feste Abstands-Werte** (`--sp-edge`, `--sp-col`, `--sp-top`, `--sp-head`, `--sp-block`, `--head-h` in `pc-core.css`): Rand, Spaltenabstand, Oberkante und Kopfhöhe sind einmal festgelegt und werden vom Seitenlayout benutzt, damit Liste und Seite auf demselben Raster liegen (14 px zu den Rändern, 14 px zwischen den Spalten, Kopf 18 px vom oberen Rand).

## 0.3.42
- **Tablet / Desktop:** Der Seitenkopf neben der Weiteres-Liste und der Titel *Weiteres* stehen auf genau derselben Linie, 18 px vom oberen Rand wie der Kopf jeder anderen Seite.

## 0.3.41
- **Tablet / Desktop:** Die Seite neben der Weiteres-Liste füllt ihre Spalte mit demselben Seitenabstand wie die Liste links (sie war geschrumpft und zentriert).

## 0.3.40
- **Tablet:** Die Weiteres-Liste klebt nicht mehr an der Seitenleiste (Seitenabstand) und ist zwischen 1000 und 1100 px schmaler und kompakter.

## 0.3.39
- **Weiteres näher am Original:** Liste + Seite nebeneinander erst ab 1000 px (darunter die einfache Liste in voller Breite), Listenspalte 340–390 px mit der Überschrift *Weiteres* oben, Schriftgrößen der Liste wie im Original. *Auto wechseln* gibt es nur noch in Weiteres, als Icon neben dem aktuellen Auto und nur bei mehr als einem Auto (kein Kennzeichen, kein Knopf in Seitenköpfen oder im Hero).

## 0.3.38
- **Die Seiten der Ersteinrichtung haben keine Navigation:** Sprach- und Zugangsseite zeigen keine Seitenleiste, Tab-Leiste und keinen „‹ Weiteres“-Link mehr.

## 0.3.37
- **Weiteres ist für beliebig viele Autos geordnet:** oben das aktuelle Auto mit *Wechseln*, darunter alles, was zu diesem Auto gehört (Seiten, *Erweiterungen* = seine Integrationen und Plugins), ganz unten *Allgemein* mit Konto & Login, Fahrzeuge und Einstellungen, die immer da sind. Die globale Seite „Dienste“ heißt jetzt „Systemdienste“ und ist über die Einstellungen erreichbar.

## 0.3.36
- **Konto & Login ist eine eigene Seite** (Weiteres → App → Konto & Login), getrennt von den Einstellungen.

## 0.3.35
- Der gewählte Eintrag in der Weiteres-Liste ist nur noch etwas heller; seine Icons behalten ihre Farbe (kein Rot).

## 0.3.34
- **Fehlerbehebung: Auf Tablets und Desktops fehlte die Weiteres-Liste auf der Weiteres-Seite selbst.** Sie steht jetzt links neben der Seite, wie auf allen Seiten unter Weiteres.

## 0.3.33
- Projekt-Hinweise für Mitwirkende (`CLAUDE.md`) und die Bild-Skripte (`tools/`). Keine Änderung an der App.

## 0.3.32
- Start-Tests: `run.sh` läuft unter den Regeln für ungesetzte Variablen mit jeder Kombination optionaler Optionen, und der echte Server wird auf einem frischen Datenordner gestartet (Migrationen, `/healthz`, erste Seite). Der Startfehler aus 0.3.30 wäre aufgefallen.

## 0.3.31
- **Fehlerbehebung: Das Add-on startete in 0.3.30 nicht** („CARASSISTANT_LANGUAGE: unbound variable“ in `run.sh`). Die optionale Option `language` wird jetzt sicher behandelt, und ein Test prüft, dass `run.sh` nie eine möglicherweise ungesetzte Variable liest.

## 0.3.30
- **Lesbare Fahrzeug-Adressen:** `/v/mein-golf` statt `/v/1` (Umlaute aufgelöst, Leerzeichen werden Bindestriche, bei gleichen Namen kommt eine Zahl dazu; ein umbenanntes Auto bekommt die neue Adresse; alte Adressen mit Nummer funktionieren weiter).
- **Auto-Wechsler:** Ein Wechsel-Knopf neben dem Namen öffnet ein dunkles Overlay mit allen Autos (Bild, Name, Kennzeichen). Es ersetzt die obere Leiste, die bei mehr als einem Auto jede Seite nach unten schob.
- **Kennzeichen** als neutraler Chip, der zu jedem Land passt; bis eins eingetragen ist, steht ein gestrichelter Platzhalter da.
- **Tablet / Desktop:** „Weiteres“ ist eine zweite Navigation links (mit „Auto wechseln“), die gewählte Seite öffnet sich rechts. Das Handy bleibt unverändert.
- **Sprachen sind erweiterbar:** Eine Sprache ist eine Datei `locales/<code>.json` (siehe `docs/translating.de.md`); sie erscheint von selbst in der Frage beim ersten Start und in den Einstellungen, mit eigenem Datumsformat und eigener Schreibrichtung. Die Add-on-Option `language` ist jetzt optional.
- Die Überblendung zwischen den Seiten ist entfernt (sie ließ Seiten hell aufblitzen).

## 0.3.29
- Nach dem ersten Fahrzeug leitet die App ohne Query-String auf die Zugriffsfrage weiter (Versuch, ein „400: Bad Request“ des Home-Assistant-Proxys nach dem ersten Auto zu vermeiden).
- Die Sprachauswahl beim ersten Start ist immer englisch, auch die Navigation, bis du Deutsch wählst.

## 0.3.28
- Add-on-Seite in Home Assistant: nur Englisch, ohne Bild und ohne Links (dort nicht nutzbar).
- CI repariert: Die Tests finden ihren Importpfad in der pyproject (die CI ruft `pytest` direkt auf), und `pyyaml` wird installiert.

## 0.3.27
- **Integrationen und Plugins pro Auto:** *Auto → Weiteres → Integrationen*. Paket hochladen (`plugin.json` oder Zip; nur die Beschreibung wird gelesen, nichts ausgeführt), einrichten, Einstellungen ändern, Token eines Plugins ersetzen oder entfernen. Optionale Extras (z. B. Webradio) werden angeboten, nie von allein hinzugefügt. Die globale Seite heißt jetzt „Dienste“ (Tankerkönig, MQTT, Benachrichtigungen).
- **Ein Verbindungs-Token gehört zu genau einem Auto** („alle Fahrzeuge“ entfällt).
- **Connector API:** neue Felder `doors`, `windows` (namensweise zusammengeführt, `null` entfernt) und `locked`, dazu `GET /api/v1/vehicles/<id>/data` zum Zurücklesen. Vollständige Entwickler-Doku (EN/DE) in `docs/api*.md` und `docs/plugins*.md`.
- **Sicherheits-Seite:** Verriegelungs-Banner, Zusammenfassung und Listen für Türen/Fenster mit Alter; offene Türen und Fenster zählen als offene Punkte und färben den Punkt am Sicherheits-Tab.
- **Der erste Start fragt nach der Sprache** (English oder Deutsch); sie lässt sich weiter in den Einstellungen ändern.
- **Jede Seite außer Home hat denselben Kopf:** Icon, Titel (und Name des Autos), Aktionen rechts; der Auto-Kopf mit Kennzeichen und Kilometerstand erscheint nur auf Home.
- **Einstellungen → Auf Werkseinstellungen zurücksetzen:** löscht nach Eintippen von RESET alle Daten und hochgeladenen Dateien; die App startet wie neu (zum Testen und für einen Neustart).
- **Favicon:** für kleine Größen zugeschnitten, dazu `/favicon.ico`; neues App-Icon, Add-on-Logo und Banner überall.
- Standard-Autobild für Fahrzeuge ohne Foto, Home-Layout mit schwebenden HU-/Wartungs-Chips.

## 0.3.26
- **Fehlerbehebung: Beim Anlegen eines Fahrzeugs konnte „400 Bad Request“ kommen.** Von Hand getippte Werte werden jetzt verstanden: Leistung als `110`, `110 kW` oder `150 PS`, Hubraum als `1968`, `1.968`, `2.0` oder `1,6 l`, eine FIN mit Leerzeichen oder Bindestrichen, das Herstelldatum als `03.05.2020`. Ein abgelehntes Formular zeigt weiterhin, was falsch war, behält deine Eingaben und legt nie ein Fahrzeug an.
- **Fehlerbehebung: Die Startseite ist Home.** Die Navigation markierte auf der Startseite ohne Fahrzeug *Weiteres* (und zeigte „‹ Weiteres“).
- **Fehlerbehebung: In der schmalen Sidebar (Tablet) sitzt das Logo jetzt exakt mittig über den Icons.**
- Die beiden Hauptschriften werden vorab geladen, das verringert das Flackern beim Seitenwechsel.
- **Startseite:** „Fahrzeug hinzufügen“ erscheint nur noch einmal (es stand doppelt da, solange noch kein Fahrzeug existierte). Der Fahrzeug-Wechsler oben rechts erscheint weiterhin nur bei mehr als einem Fahrzeug.
- **Neues App-Icon, Add-on-Logo und Banner**, freigestellt mit transparentem Hintergrund und auf die Farben der Seite abgestimmt (Akzentrot zu Status-Grün, das Blau-Schwarz der Seite, Schrift Space Grotesk).

## 0.3.25
- Aufräumen: neutrale Formulierungen im Changelog und in Code-Kommentaren, neutraler Benutzername in einem Test. Keine funktionale Änderung.

## 0.3.24
- **Die Standort-Karte ist jetzt standardmäßig aus.** Car Assistant lädt nichts aus dem Internet, bis du die Karte unter Einstellungen → Karte einschaltest. Der Kachel-Host ist in der Content-Security-Policy nur erlaubt, solange die Karte an ist. Ohne Karte zeigt die Seite die Koordinaten und die Navigations-Buttons.

## 0.3.23
- **Status auf Home:** zwei Plaketten am Autobild – **Zündung** (an/aus) und **Türen & Fenster** (geschlossen / eine offen / n offen). Sie erscheinen nur, wenn Daten vorliegen.
- **Standort-Karte** auf Home: letzte bekannte Position, „Geparkt seit“, „Letztes Signal“, eine Karte und Navigations-Buttons (Waze, Google Maps, Apple Maps). Die Karte ist Leaflet (mitgeliefert) mit OpenStreetMap-Kacheln, standardmäßig dunkel mit Sonne/Mond-Umschalter. **Einstellungen → Karte** schaltet die Kacheln ab (sonst sieht OpenStreetMap deine IP-Adresse und den Kartenausschnitt); die Position erscheint dann als Koordinaten.
- Connector API: neues Feld `ignition` (true/false).
- Die Content-Security-Policy erlaubt nun Bilder von `*.tile.openstreetmap.org` und sonst nichts Neues; das Karten-Skript liegt in einer eigenen Datei (keine Inline-Skripte).

## 0.3.22
- **Sidebar korrigiert:** Der Glas-Kasten um die Navigationsliste ist weg. Die Glaskapsel gehört nur zur Handy-Leiste; in der Sidebar steht die Liste wieder flach, nur der aktive Eintrag ist hervorgehoben. Logo (46 px, kleine Rundung), Sidebar-Breite (84 px), Untertitel-Schrift und Status-Punkt haben wieder die vorgesehenen Werte, die späten Überschreibungen, die davon abwichen, sind entfernt. Ein Test verhindert, dass der Kasten zurückkommt.

## 0.3.21
- **Punkte auf den Tabs:** Ein Tab bekommt einen kleinen Punkt, wenn die Seite dahinter einen offenen Punkt hat (überfällig oder bald fällig): Sicherheit bei jedem offenen Punkt, Service und Wartung bei fälliger Wartung, Termine bei fälligen Terminen. Weiteres bekommt nur dann einen Punkt, wenn der Punkt auf einer nach Weiteres verschobenen Seite liegt. Funktioniert in der unteren Leiste und in der schmalen und breiten Sidebar; Screenreader sagen „braucht Aufmerksamkeit“ an.

## 0.3.20
- **Fahrzeugdaten**-Seite vervollständigt: Hero-Karte mit Kennzeichen-Chip und Motorzeile, drei Gruppen (Fahrzeug, Technik, Papiere & Optik) auf breiten Bildschirmen in zwei Spalten, auf dem Handy in einer. Neue optionale Felder: Herstelldatum, Typ, Motor, Leistung, Hubraum, Motor- und Getriebe-Kennbuchstabe, Antrieb, Getriebe, Karosserie, Batterie, Farbcode, HSN/TSN, Schlüsselnummern und ein Notizfeld für Leuchtmittel und Ersatzteile.
- Grüne Plaketten zeigen die Herkunft eines Werts: **vom Auto** (von einer Integration oder einem Plugin geliefert) und **aus FIN** (Modelljahr aus der FIN, solange kein Jahr eingetragen ist).
- Entwicklung: Die README nennt jetzt die fehlende Test-Abhängigkeit (`pyyaml`).

## 0.3.19
- Navigations-Einstellungen: keine Dropdowns mehr. Alle Seiten per Ziehen am Griff oder mit den Pfeilen anordnen; die ersten vier sind die Leiste, der Rest wandert nach Weiteres. Aus der Leiste genommene Seiten stehen oben in Weiteres.

## 0.3.18
- Neue **Fahrzeugdaten**-Seite: gruppierte Liste (Label links, Wert rechts in Space Mono, Plakette „vom Auto“); der Stift öffnet das Bearbeiten-Formular.

## 0.3.17
- Seiten, die über Weiteres geöffnet werden, haben oben einen Zurück-Button „‹ Weiteres“.

## 0.3.16
- Neue Optik: transparentes Glas (das rote Licht scheint durch die Kacheln), Kacheln, Tab-Leiste und Weiteres-Seite. Icons sind wieder das Material-Design-Icons-Set.

## 0.3.15
- Neue Navigation: Home (fest), vier frei wählbare Seiten mit eigenen Icons (Einstellungen → Navigation), Weiteres (fest). Leiste nur mit Icons; Beschriftung nur in der breiten Seitenleiste.
- Neue Seiten: **Weiteres** (gruppiertes Menü mit farbigen Icon-Kacheln) und **Sicherheit**. Kacheln auf Home erscheinen nur, wenn Daten vorliegen.
- Alle Icons sind jetzt Material Design Icons (Apache-2.0). Seitenleiste: App-Icon mittig über den Navigations-Icons.

## 0.3.14
- Fundament für die Community: **Connector-API** (`/api/v1`). Integrationen und Plugins verbinden sich mit einem Token (*Integrationen → Verbindungen*) und senden Kilometerstand, Tankfüllung, Reichweite und Position mit einer HTTP-Anfrage. Es läuft kein fremder Code in der App. Doku, Beispielskript und Tests ergänzt.

## 0.3.13
- Lizenz: GNU GPL v3.0 (`LICENSE`); Lizenztexte von Material Design Icons (Apache-2.0) und den Schriften (OFL 1.1) unter `licenses/` ergänzt.

## 0.3.12
- Seitenleiste: Das App-Icon richtet sich jetzt exakt an den Navigationspunkten aus (gleiche Breite, zentriert). Quellenangaben für Icons und Schriften in README und Einstellungen.

## 0.3.11
- Kein weißes Aufblitzen mehr beim Wechsel zwischen Seiten: dunkles Farbschema und seitenübergreifender Übergang (die alte Seite bleibt, bis die nächste bereit ist).

## 0.3.10
- Dokumentation aktualisiert (Login, Passkeys, Icons); Button „Repository zu meinem Home Assistant hinzufügen“ in README und Installationsanleitung; Ko-fi-Link (README, Einstellungen, GitHub-Sponsor-Button).

## 0.3.9
- Navigation: auf den Seiten eines Autos zeigt die untere Kapsel die Tabs des Autos plus ein „Mehr“-Menü (weitere Tabs, Fahrzeuge, Tankstellen, Integrationen, Einstellungen); die Tab-Leiste unter dem Auto entfällt.
- Behebt den ungestylten/weißen Start in Home Assistant: sofort dunkler Hintergrund, Stylesheet und Skript sind versioniert und werden immer neu geprüft.

## 0.3.8
- Logo: „Car“ über „Assistant“, in der Schrift der App (Space Grotesk).

## 0.3.7
- Login für den direkten (externen) Zugriff: Benutzer, Passwörter, Passkeys (WebAuthn) und einmalige Wiederherstellungscodes. Innerhalb von Home Assistant ist kein Login nötig; der Direktzugriff bleibt gesperrt, bis ein Konto existiert.
- Nach dem ersten Fahrzeug fragt ein kurzer Einrichtungsschritt, ob die App vorerst ohne Login bleibt oder von außen erreichbar ist (dann Konto nötig).
- Neue Karte *Konto & Login* in den Einstellungen.

## 0.3.6
- Icon für die ganze App oder je Auto unter Einstellungen → Icon austauschbar; es wird überall verwendet. Jedes Auto hat ein eigenes Web-App-Manifest (je Auto eine Home-Bildschirm-App).

## 0.3.5
- Banner in den README-Dateien ergänzt.

## 0.3.4
- Neues App-Icon mit dicker Rot-Grün-Verlaufskontur, überall verwendet (Seitenleiste, Favicon, Home Assistant, GitHub-Banner).

## 0.3.3
- Die Icons verwenden jetzt die Material-Design-Icon-Pfade unverändert.

## 0.3.2
- Neues Design: gefüllte Material-Icons, grüne Status-Chips und Segment-Reiter, Überblick-Kacheln mit Icon-Quadraten und Farbverläufen, große helle Kilometer-Anzeige, zweispaltiges Home auf breiten Bildschirmen.

## 0.3.1
- Neue Navigation: Seitenleiste am Desktop, schwebende Glas-Tableiste am Handy, Fahrzeug-Karte und Pillen-Tabs mit Icons.
- Neues flaches App-Icon, Logo und Banner (ohne Verläufe).

## 0.3.0
- Die Oberfläche ist jetzt standardmäßig auch über den Host-Port 8321 erreichbar (ändern oder ausschalten unter Konfiguration → Netzwerk). Ohne `access_password` bleibt der Port gesperrt; die Seitenleiste funktioniert wie bisher. Die Einstellungen zeigen den veröffentlichten Port.

## 0.2.2
- Fix: Die App startete nicht („Ungültige Konfiguration – expected a URL“), wegen des leeren Standardwerts bei der optionalen `external_url`.

## 0.2.1
- Erste Version als eigenständige Home-Assistant-App (Ingress).
- Fahrzeuge: Servicebuch, Termine, Wartung, Reifen, Umbauten, Teile, Kraftstoff (Tank-zu-Tank-Statistik), eigene Km-Zähler, Fahrten (GPX/CSV), Dokumente.
- Modulare Oberfläche: Module und Integrationen lassen sich ein-/ausschalten; Menü „Auto wechseln“ für mehrere Autos.
- MQTT-Discovery (automatischer Broker, ohne Passwort), Benachrichtigungen, ICS-Kalender, PDF-Bericht, Backup/Restore, Tankstellen (Tankerkönig/OpenStreetMap).
- Optionaler Direktzugriff: Port, Passwortschutz, CSRF-Schutz, `external_url`.
- Dunkles Design mit Icons; Englisch und Deutsch.
