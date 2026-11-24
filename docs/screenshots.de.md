# Screenshots

[🇬🇧 English](screenshots.md) · 🇩🇪 Deutsch

So sieht Car Assistant im Einsatz aus. Alle Bilder zeigen ein **Demo-Auto mit ausgedachten Daten** (ein Diesel und ein Elektroauto mit zwei Jahren Historie); kein echtes Fahrzeug, keine echten Orte. Das Demo-Auto kannst du selbst anlegen: *Fahrzeug hinzufügen → Demo-Auto*.

## Dashboard

Das Auto auf einen Blick: der Kilometerstand (mit dem Knopf *Stand ändern*), Reichweite, Meldungen des Autos, nächste Hauptuntersuchung, offene Punkte und Widgets wie letzte Fahrt, Tanken und Verbrauch.

![Dashboard](screenshots/de/dashboard.png)

### Standort auf einer echten Karte

Unter den Fahrzeugdaten zeigt die **Standort-Karte**, wo das Auto geparkt ist (oder dass es fährt), auf einer Karte in den Farben deines Designs, dazu drei Links, um den Ort in Waze, Google Maps oder Apple Maps zu öffnen. Die Kartenkacheln kommen nur von OpenStreetMap, wenn du es erlaubst (*Einstellungen → System*); vorher wird nichts geladen.

![Dashboard mit der Standort-Karte](screenshots/de/dashboard-map.png)

## Dashboard (Elektro)

Dieselbe Seite für ein Elektroauto: Laden, Akku und Reichweite statt Tank.

![Dashboard (Elektro)](screenshots/de/dashboard-ev.png)

## Tanken

Alle Tankungen nach Monaten mit Verbrauch und Preisen. Die **Tankstellensuche** oben ist bewusst einfach: Das Auto bestimmt den Kraftstoff, der Umkreis sind 15 km, jede Tankstelle ist eine Zeile mit Name, Entfernung und Preis, die günstigste ist grün markiert.

![Tanken](screenshots/de/fuel.png)

## Kostensicht

Was das Auto im gewählten Zeitraum kostet: die Summe, der Anteil von Tanken, Service, Umbauten und Teilen, ein Diagramm je Zeitraum und eine Liste jedes Eintrags mit Preis.

![Kostensicht](screenshots/de/report.png)

## Fahrten und Fahrten-Auswertung

Oben die Auswertung (30 Tage, 90 Tage, Jahr, Alle): Fahrten nach Art und Länge, eine Heatmap aus Wochentag und Tageszeit und der Fahrstil; darunter die Km-Zähler und die Fahrten nach Monaten.

![Fahrten](screenshots/de/trips.png)

### Eine Fahrt auf der Karte

Tippe auf eine Fahrt, und ihre Karte öffnet sich mit Strecke, Dauer, Durchschnittstempo, einer Schätzung von Verbrauch und Kosten und der **Route auf einer Karte in voller Breite** – nach Tempo eingefärbt von blau (langsam) über grün und gelb bis rot (ab 130 km/h), Start und Ziel markiert. *Route als GPX* exportiert sie. Ein Link kann eine Fahrt direkt öffnen: `…/e/trips?open=<id>`.

![Eine Fahrt auf der Karte](screenshots/de/trip-map.png)

## Service

Wartung mit Kilometerstand, Kosten und Notizen; tippe auf eine Karte, um sie zu bearbeiten.

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

| Eine Fahrt auf der Karte | Reifen |
|---|---|
| <img src="screenshots/de/mobile-trip-map.png" alt="Eine Fahrt auf der Karte" width="260"> | <img src="screenshots/de/mobile-tires.png" alt="Reifen" width="260"> |

Mehr: [Benutzerhandbuch](guide.de.md) · [Installation](install.de.md) · [MCP-Zugriff](mcp.de.md)
