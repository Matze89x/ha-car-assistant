# Screenshots

[🇬🇧 English](screenshots.md) · 🇩🇪 Deutsch

So sieht Car Assistant im Einsatz aus. Alle Bilder zeigen ein **Demo-Auto mit ausgedachten Daten** (ein Diesel und ein Elektroauto mit zwei Jahren Historie und ein Kleinwagen mit wenig Daten); kein echtes Fahrzeug, keine echten Orte. Das Demo-Auto kannst du selbst anlegen: *Fahrzeug hinzufügen → Demo-Auto*.

## Dashboard

Das Auto auf einen Blick: der Kilometerstand (mit dem Knopf *Stand ändern*), Reichweite, Meldungen des Autos, nächste Hauptuntersuchung, offene Punkte und Widgets wie letzte Fahrt, Tanken und Verbrauch.

![Dashboard](screenshots/de/dashboard.png)

### Standort auf einer echten Karte

Unter den Fahrzeugdaten zeigt die **Standort-Karte**, wo das Auto geparkt ist (oder dass es fährt), auf einer Karte in den Farben deines Designs, dazu drei Links, um den Ort in Waze, Google Maps oder Apple Maps zu öffnen. Die Kartenkacheln kommen nur von OpenStreetMap, wenn du es erlaubst (*Einstellungen → System*); vorher wird nichts geladen.

![Dashboard mit der Standort-Karte](screenshots/de/dashboard-map.png)

## Dashboard (Elektro)

Dieselbe Seite für ein Elektroauto: Laden, Akku und Reichweite statt Tank.

![Dashboard (Elektro)](screenshots/de/dashboard-ev.png)

## Schnell eintragen: der Kilometerstand per Foto

Tippe auf den Kilometerstand im Dashboard: Er dreht sich zu einem Eingabefeld um. Zahl tippen oder auf die Kamera tippen und den unteren Teil des Tachos fotografieren - der Server liest die Zahl (Tageszähler und Skalenzahlen werden ignoriert), zeigt sie zum Prüfen und speichert erst mit dem Pfeil. Kein Plugin nötig.

![Der umgedrehte Kilometerstand, ein Foto vom Tacho wurde gelesen](screenshots/de/odometer-photo.png)

## Schnell eintragen: eine Tankung vom Beleg

*Tanken → Plus* (oder *Ergänzen* auf der Karte eines vom Auto erkannten Tankens): oben im Formular jeder Tankung stehen *Scannen* (die Kamera) und *Datei laden* (ein Foto aus der Mediathek oder ein PDF-Beleg). Datum, Tankstelle, Sorte, Menge, Preis je Einheit, Betrag und - wenn der Beleg ihn aufdruckt - der Kilometerstand werden eingetragen und markiert; Menge × Preis = Betrag wird geprüft. Gespeichert wird erst mit *Speichern*.

![Ein Tankbeleg wurde gelesen: das Formular ist ausgefüllt](screenshots/de/fuel-scan.png)

## Tankungen aus einer anderen App importieren

*Tanken → die Pfeile oben rechts → CSV importieren*: Wähle die CSV-Datei von Fuelio (oder einer anderen App), prüfe, welche Spalte was ist - Car Assistant hat an den Namen geraten und zeigt neben jeder Wahl einen Beispielwert - und sieh dir an, was geschrieben wird, bevor du *Importieren* drückst.

![Die Spalten der Datei den Punkten einer Tankung zugeordnet](screenshots/de/import-columns.png)

![Die Prüfung vor dem Import](screenshots/de/import-check.png)

## Tanken

Alle Tankungen nach Monaten mit Verbrauch und Preisen - jede ist ein Kassenbon: oben Datum und Tankstelle, in einer Zeile die Menge und ihr Preis, darunter die Einzelheiten; tippe darauf, um sie zu korrigieren oder einen Beleg noch einmal zu scannen. Springt der Tankstand des Autos, bittet eine **Mitteilungskarte** *Tanken erkannt* mit einem Knopf um den Beleg; sie verschwindet, wenn der Eintrag gespeichert ist, nach drei Fahrten oder nach drei Tagen. Die **Tankstellensuche** oben ist bewusst einfach: Das Auto bestimmt den Kraftstoff, der Umkreis sind 15 km, jede Tankstelle ist eine Zeile mit Name, Entfernung und Preis, die günstigste ist grün markiert.

![Tanken](screenshots/de/fuel.png)

## Laden (Elektroautos)

Bei einem Elektroauto ist die Tank-Seite die Seite **Laden**: die Ladevorgänge nach Monat und darüber die **Ladesäulensuche** – rund um das Auto oder rund um dich, mit Steckern und Leistung, sortiert nach Entfernung oder Leistung und gefiltert nach *mindestens 22 / 50 / 150 kW* und nach Stecker (CCS, Typ 2, CHAdeMO, NACS). Vor dem Suchen wird nichts abgefragt, und es geht nichts woandershin als zur gewählten Quelle ([Ladepunkt-Anbieter](charge-providers.de.md)). Ob eine Ladesäule *gerade jetzt* frei ist, weiß keine offene Quelle; deshalb sagt die Seite es nicht. Die Ladesäulen im Bild sind erfunden.

![Laden: die Suche nach Ladesäulen](screenshots/de/charging.png)

## Alle Anbindungen der Plugins

*Plugins → Anbindungen*: eine zoombare Karte mit den Plugins links, **jedem Kanal der Plugin-API** in der Mitte - auch den offenen (hohle Ringe) - und rechts, wo es ankommt. Mit dem Mausrad zoomen, ziehen zum Verschieben; ein Klick auf ein Plugin, einen Kanal, einen Ort oder eine Linie öffnet darunter die Erklärung, die Anbindungen, den Rohwert und die letzten Werte mit Datum und Uhrzeit.

![Die Anbindungskarte mit einem geöffneten Kanal](screenshots/de/connections-map.png)

## Kostensicht

Was das Auto im gewählten Zeitraum kostet: die Summe, der Anteil von Tanken, Service, Umbauten, Teilen und Fixkosten, ein Diagramm je Zeitraum und eine Liste jedes Eintrags mit Preis. Die Seite hat drei Reiter: *Übersicht*, *Fixkosten* und *Rechnungen*.

![Kostensicht](screenshots/de/report.png)

## Rechnungen

Der dritte Reiter der Kostenseite: eine Rechnung *Fotografieren* oder ein PDF, ein Bild oder einen Scan *Hochladen* (bis zu zehn Dateien auf einmal). Car Assistant liest sie auf diesem Server - nichts wird verschickt - und zeigt, was es gefunden hat: Datum, Summe (Netto + MwSt = Summe wird geprüft), Absender, Rechnungsnummer, Kilometerstand und welche Art Kosten es ist. *Prüfen und buchen* öffnet das ganz normale Formular eines Service-, Teile-, Umbau-, Fixkosten- oder Tankeintrags, ausgefüllt; gebucht wird erst mit Speichern.

![Rechnungen](screenshots/de/invoices.png)

![Eine Rechnung: was gelesen wurde und die Wege, sie zu buchen](screenshots/de/invoice.png)

## Fahrten und Fahrten-Auswertung

Oben die Auswertung (30 Tage, 90 Tage, Jahr, Alle): Fahrten nach Art und Länge, eine Heatmap aus Wochentag und Tageszeit und der Fahrstil; darunter die Km-Zähler und die Fahrten nach Monaten.

![Fahrten](screenshots/de/trips.png)

### Eine Fahrt auf der Karte

Tippe auf eine Fahrt, und ihre Karte öffnet sich mit Strecke, Dauer, Durchschnittstempo, einer Schätzung von Verbrauch und Kosten und der **Route auf einer Karte in voller Breite** – nach Tempo eingefärbt von blau (langsam) über grün und gelb bis rot (ab 130 km/h), Start und Ziel markiert. *Route als GPX* exportiert sie. Ein Link kann eine Fahrt direkt öffnen: `…/e/trips?open=<id>`.

![Eine Fahrt auf der Karte](screenshots/de/trip-map.png)

## Service

Wartung mit Kilometerstand, Kosten und Notizen; tippe auf eine Karte, um sie zu bearbeiten. *Service*, *Zusatzarbeiten*, *Teile* und *Umbauten* sind ein Eintrag unter *Weiteres* mit einer Leiste aus Reitern - wie *Kosten* (Übersicht, Fixkosten, Rechnungen) und *Dokumente & Handbuch*.

![Service](screenshots/de/service.png)

## Zusatzarbeiten und Termine

Arbeiten mit Intervall, Fortschritt und *Zurücksetzen*; Termine mit ihrem Countdown.

![Zusatzarbeiten](screenshots/de/tasks.png)

![Termine](screenshots/de/appointments.png)

## Teile, Reifen und Dokumente

![Teile](screenshots/de/parts.png)

![Reifen](screenshots/de/tires.png)

Reifen haben einen Tab je Jahreszeit; der Satz trägt seinen Namen als Überschrift und, wenn er am Auto ist, ein Schild-Symbol. Umbauten sind Karten nach Jahr, hinzugefügt mit dem Plus-Knopf.

![Umbauten](screenshots/de/mods.png)

## Eine Hinweis-Kachel auf jeder Seite

Unter jedem Seitenkopf sitzt dieselbe Kachel: die Einleitung der Seite mit einem ⓘ – und die Meldungen der App: *Gespeichert* (grün), Warnungen (gelb) und Fehler (rot), immer an derselben Stelle und in den Farben deines Designs.

![Die Hinweis-Kachel](screenshots/de/notice.png)

![Dokumente](screenshots/de/documents.png)

## Sicherheit

Türen, Fenster und Verriegelung, wie das Auto sie meldet.

![Sicherheit](screenshots/de/security.png)

## Fahrzeugpass

Alles zum Auto in Gruppen, die FIN mit Kopierknopf und die Ausstattung.

![Fahrzeugpass](screenshots/de/passport.png)

## Weiteres, Plugins und Über

![Weiteres](screenshots/de/more.png)

![Plugins](screenshots/de/plugins.png)

![Über](screenshots/de/about.png)

## Coding: die Steuergeräte

*Weiteres → Coding* (die Integration *Coding*): eine Karte je Steuergerät mit Adresse, Name, Teilenummern und der Codierung als Bytes. Die Werks-Codierung wird einmal geschrieben; die aktuelle wird Byte für Byte verglichen, und ein geändertes Byte zeigt, was es war. Öffne ein Steuergerät, dann ist sein erstes Byte schon gewählt; tippe ein geändertes Byte an, und es öffnet sich als acht Bits (Werk und neu) mit einer Notiz je Bit – und Bits, die zusammengehören, lassen sich zu einer Gruppe mit einem Namen verbinden. Die Steuergeräte im Bild sind erfunden.

![Die Coding-Seite: ein geändertes Byte als acht Bits](screenshots/de/coding.png)

## Einstellungen: Benutzer, Auto, System

Die Einstellungen haben drei Reiter. **Auto** betrifft das Auto unter dem Titel (Icon, Foto und Video, Design, Home-Assistant-Entitäten, Sicherung); **Benutzer** betrifft dich (Login, deine Geräte und Benachrichtigungen, ein Startlink je Auto für eine Web-App); **System** betrifft die ganze App (Sprache, Einheiten, Design, Sensoren, MCP-Zugang, Quellen, Adresse, Sicherung).

![Einstellungen: Benutzer](screenshots/de/settings-user.png)

![Einstellungen: Auto](screenshots/de/settings-car.png)

![Einstellungen: System](screenshots/de/settings-system.png)

## Designs

Das klassische Rot und die Designs mit eigener Farbe (hell, dunkel, automatisch) - für die ganze App oder nur für ein Auto.

| Klassisch rot | Hell | Dunkel | Automatisch |
|---|---|---|---|
| <img src="screenshots/de/design-classic.png" alt="Klassisch rot" width="220"> | <img src="screenshots/de/design-light.png" alt="Hell" width="220"> | <img src="screenshots/de/design-dark.png" alt="Dunkel" width="220"> | <img src="screenshots/de/design-auto.png" alt="Automatisch" width="220"> |

## Auf dem Handy

Auf dem Handy wird die Seitenleiste zu einer Leiste unten (Home, bis zu vier Seiten deiner Wahl, Weiteres); die Karten stapeln sich in einer Spalte.

| Dashboard | Tanken | Fahrten |
|---|---|---|
| <img src="screenshots/de/mobile-dashboard.png" alt="Dashboard" width="260"> | <img src="screenshots/de/mobile-fuel.png" alt="Tanken" width="260"> | <img src="screenshots/de/mobile-trips.png" alt="Fahrten" width="260"> |

| Kostensicht | Weiteres | Einstellungen: Auto |
|---|---|---|
| <img src="screenshots/de/mobile-report.png" alt="Kostensicht" width="260"> | <img src="screenshots/de/mobile-more.png" alt="Weiteres" width="260"> | <img src="screenshots/de/mobile-settings-car.png" alt="Einstellungen: Auto" width="260"> |

| Eine Fahrt auf der Karte | Reifen | Eine Rechnung |
|---|---|---|
| <img src="screenshots/de/mobile-trip-map.png" alt="Eine Fahrt auf der Karte" width="260"> | <img src="screenshots/de/mobile-tires.png" alt="Reifen" width="260"> | <img src="screenshots/de/mobile-invoice.png" alt="Eine Rechnung" width="260"> |

Mehr: [Benutzerhandbuch](guide.de.md) · [Installation](install.de.md) · [MCP-Zugriff](mcp.de.md)
