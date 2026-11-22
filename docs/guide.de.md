# Benutzerhandbuch

[🇬🇧 English](guide.md) · 🇩🇪 Deutsch

Car Assistant ist ein Fahrtenbuch und Dashboard für deine Autos. Das meiste erklärt sich auf der Seite selbst; hier die kurze Tour.

## Die drei Ebenen
Jede Einstellung liegt auf genau einer Ebene, du weißt also immer, wo du suchen musst. *Einstellungen* hat drei Reiter - zuerst das Auto, dann du, dann die ganze App:
- **Auto** – nur das Auto, das unter dem Titel steht (wechsle es mit dem Zeichen neben seinem Namen): Foto, Video, Design und Icon, Home-Assistant-Entitäten, Sicherung, Archivieren und Löschen.
- **Benutzer** – du: dein Login (Name, Passwort, Passcode, Passkeys), deine Geräte und alle deine Benachrichtigungen (eine Liste für jedes Auto), das Start-Auto und die Startlinks für eine [Web-App je Auto](#eine-web-app-je-auto).
- **System** – die ganze App, für jedes Auto und jede Person: eine Karte **Region**: Sprache, Datum und Uhrzeit (Reihenfolge des Datums, 12 / 24 Stunden), **Zeitzone** (automatisch = die von Home Assistant; Sommer-/Winterzeit folgt) sowie Einheiten und Währung, Design, Karte und Spritpreise, Sensoren in Home Assistant, [MCP-Zugriff](mcp.de.md), Quellen und Updates (auf Wunsch einmal am Tag ein Blick auf ein neues Car Assistant und auf Paket-Updates – der Punkt am Fuß der Seitenleiste wird gelb, wenn etwas neu ist), Protokolle, die Adresse der App, Sicherung von allem.

## Erster Start
Eine kurze Einführung fragt nach der Sprache, dann nach deinem ersten Auto (oder einem Demo-Auto) und danach, welche Funktionen du möchtest. Alles lässt sich später ändern.

## Dashboard
*Webseite bearbeiten* lässt dich Widgets verschieben, ausblenden und in der Größe ändern, *Video oder Foto bearbeiten* öffnet das Bild-Fenster.

## Fahrzeugdaten
*Weiteres → Fahrzeugdaten* zeigt alles zum Auto; der Stift öffnet das Formular. Das Formular ist in Kästen geteilt (*Dein Fahrzeug, Identifikation, Technik, Energie, Papiere*) und hat ein **Speichern** im Seitenkopf. Foto, Video, Design, Icon, Home-Assistant-Entitäten und Sicherung stehen nicht auf dieser Seite: Sie sind im Reiter **Auto** der Einstellungen.

## Einstellungen eines Autos
*Einstellungen → Auto* (das Auto unter dem Titel):
- **Icon** – das eigene Icon des Autos für Weiteres, den Browser-Tab und den Home-Bildschirm.
- **Foto und Video** – bis zu **10 Dateien pro Auto**, Fotos und Videos zusammen; beim elften Hinzufügen fällt die älteste heraus. Zwei Auswahlen, sofort gespeichert: *Für die Startseite* (ein Foto oder ein Video) und *Als Foto des Autos* (für die Autoauswahl und alle Listen). Ein Video braucht zuerst ein Foto.
- **Design** – das eigene Design des Autos mit eigenem Farbrad; *Wie das System* folgt dem Design von System.
- **Home-Assistant-Entitäten** – optionale Entitäten, die Kilometerstand, Tankstand, Reichweite und Position liefern (hier gibt es ein **Speichern**).
- **Sichern & verwalten** – dieses Auto sichern, archivieren oder löschen.

## Seiten eines Autos
**Fahrzeugpass** (*Weiteres → erste Zeile des Autos*). Der Kopf zeigt Name, Kennzeichen, *Marke Modell Variante*, die Fakten, die man ständig braucht, als Chips (Baujahr, Kraftstoff, Leistung, Getriebe, Kilometerstand) und die FIN mit Kopierknopf. Darunter: die Daten in Gruppen (nur was du eingetragen hast), die Notizen und die Liste **Ausstattungsmerkmale**. Die Ausstattung hat zwölf feste Bereiche (Komfort, Sitze, Bedienelemente, Licht, Linien & Pakete, Interieur, Räder & Reifen, Technik & Sicherheit, Exterieur, Infotainment, Assistenzsysteme, Verglasung & Dach); du kannst sie nur nach oben und unten sortieren. Jedes Merkmal hat einen Status – Serie, Sonderausstattung, nachgerüstet (blauer Haken) oder nicht verbaut (rotes Kreuz) – und einen optionalen Code wie eine PR-Nummer; der Stift bearbeitet ein Merkmal und verschiebt es auch in einen anderen Bereich.

**Fahrten** enthält oben die **Km-Zähler** (ein Zähler misst die Strecke zwischen einem Startstand und dem heutigen Kilometerstand oder einem Endstand, zum Beispiel fürs Steuerjahr) und darunter die Fahrten, nach Monaten. Tippe auf eine Fahrt für ihre Karte: Strecke, Dauer, Ø Tempo und Spitze, Verbrauchs-Chips (eine Schätzung aus dem Durchschnitt des Autos), die Route auf der Karte nach Tempo eingefärbt und der Fahrstil (braucht aufgezeichnete Positionen; von Hand eingetragene Fahrten zeigen Dauer und Ø aus den Zeiten). *Export* schreibt PDF oder CSV, *Import* liest eine GPX-Datei. Die **Fahrten-Auswertung** oben auf der Seite (30 Tage, 90 Tage, Jahr, Alle) zeigt Anzahl und Länge der Fahrten, ihren Anteil nach Art, ein Balkendiagramm der Fahrtlängen, eine Heatmap aus Wochentag und Tageszeit und den Fahrstil über alle aufgezeichneten Fahrten (starkes Bremsen je 100 km, Ø Tempo in Bewegung, Stillstand, Spitze).

**Kostensicht** ist die Kostenseite: das ausgegebene Geld im gewählten Zeitraum (Tage, Wochen oder Monate), der Anteil von Tanken, Service, Umbauten und Teilen, ein Diagramm je Zeitraum und eine Liste jedes Eintrags mit Preis - tippe auf eine Kategorie, um zu filtern. Darunter folgen Verbrauch, Preis je Liter und Kilometer.

**Tanken** enthält oben die **Tankstellensuche** (zugeklappt) und darunter die Tankungen, nach Monaten. **Reifen** hat oben die Karte *Empfohlener Reifendruck* (ein Reiter je Jahreszeit, mit normalem und voll beladenem Luftdruck sowie dem letzten Messwert des Autos) und darunter eine Karte je Satz (aktuell montiert, Größe, Vorder- und Hinterachse). **Zusatzarbeiten** zeigt den Kilometerstand und eine Karte je Arbeit (das Symbol passt zur Arbeit) mit Intervall, Fortschrittsbalken und *zuletzt* / *nächste*; vorgegebene Arbeiten gibt es nicht, weil jedes Auto anders ist. *Bearbeiten* (unten rechts in der Karte) öffnet *Jetzt erledigt – bei Kilometerstand* mit *Zurücksetzen* oben und darunter das Formular. **Umbauten** sind Karten, nach Jahr gruppiert mit der Summe des Jahres, und eine Schnell-Eingabe. **Termine** stehen in einer kompakten Spalte mit je einem *Bearbeiten*-Knopf; die Gruppen *Kommende* und *Abgeschlossene Termine* erscheinen nur, wenn es solche gibt (abgeschlossen = als erledigt markiert); das Datum kann ein Monat oder ein Tag sein, geschrieben wie unter Einstellungen → System → Datum & Uhrzeit eingestellt. **Teile & Einkäufe** sehen aus wie Kassenzettel (Datum und Shop, Teil und Preis, Details). **Dokumente** sind Karten mit *Öffnen* und *Bearbeiten*: Titel, Kategorie, Datum des Dokuments, gültig bis (ein Badge zeigt, wann es abläuft) und Notiz. Das **Handbuch** importiert eine PDF (mit Textebene), eine EPUB-, eine Text- / Markdown-Datei oder ein [Paket mit Seitenbildern](manual-package.de.md), zeigt die Seiten als Bild oder Text, listet die Kapitel, durchsucht, merkt sich, wo du aufgehört hast, und exportiert eine EPUB – die Datei bleibt auf deinem Server.

**Widgets.** Jedes Widget sieht gleich aus: Symbol und Titel links, rechts eine kleine Notiz (das letzte Signal des Autos) oder der Pfeil, dann der Wert und höchstens eine Zeile; Status-Chips stehen rechts, der Text links. *Fahrzeugdaten live* zeigt eine schlanke Zeile je Wert; *Standort* zeigt den Ort, ob das Auto hier steht oder fährt, die Karte und drei Navigations-Links.

**Protokolle** gehören zu jedem Plugin und jeder Integration: *Info* auf ihrer Karte zeigt ihr Protokoll (der Schalter für mehr Details, ihre Zeilen, die Aufrufe).

**Widgets der Startseite.** *Aufmerksamkeit*, *Fahrzeugdaten* und *Standort* sind immer eine ganze Zeile; alle anderen können klein oder eine ganze Zeile sein.

**Knöpfe.** Nebenaktionen sind leichte, umrandete Knöpfe, eine Knopfreihe bleibt einzeilig; nur die eine Hauptaktion einer Seite ist ein gefüllter Knopf.

## Navigation
Die Seitenleiste zeigt Name und Slogan als eine Einheit (gleich breit, die Größe folgt der Leiste). Der Punkt am Fuß ist grün, wenn alles aktuell ist, und gelb, wenn Car Assistant oder ein Paket ein Update hat (beim Darüberfahren steht der Grund; auf breiten Bildschirmen erscheinen darüber die Zeilen *System vX* / *Plugins n Updates*).

*Weiteres → Integrationen → Navigation verwalten*: Die ersten vier Seiten stehen in der Leiste, der Rest unter *Weiteres*, in derselben Reihenfolge. Integrationen und Plugins stehen immer am Ende. Schaltest du eine feste Integration aus, verschwindet ihre Seite aus der Navigation; die Listen bleiben synchron.

## Benachrichtigungen
Benachrichtigungen sind **ein System pro Person** unter *Einstellungen → Benutzer* – unter *Auto* oder *System* wird dazu nichts eingestellt. Dort schaltest du sie auf dem iPhone, iPad oder Computer ein, den du gerade benutzt (oder trägst den Namen deines Home-Assistant-Benachrichtigungsdienstes ein, wenn kein Port gesetzt ist) und siehst deine Geräte. Darunter **wählst du ein Auto** und schaltest jede Art von Meldung mit runden Schaltern ein oder aus (*Ja* / *Nein*); die Auswahl *Neue Autos* ist das, womit ein später hinzugefügtes Auto startet. Ein neues Auto erscheint von selbst in der Liste, ein entferntes verschwindet. *Allgemein* enthält Meldungen, die nicht zu einem Auto gehören (zum Beispiel eine neue Version eines installierten Plugins). Dieselben Worte gehen an eine Person nur einmal, und gleiche Meldungen ersetzen sich auf einem Gerät.

## Eine Web-App je Auto
*Einstellungen → Benutzer → Web-App für ein Auto* listet je Auto einen Startlink. Öffne den Link eines Autos in Safari, tippe auf *Teilen* und *Zum Home-Bildschirm*: Die App öffnet direkt dieses Auto und zeigt nur dieses - ohne Fahrzeugwechsel und ohne Liste der anderen. Sie braucht deine eigene https-Adresse (*Einstellungen → System*).

## Claude und MCP
Mit dem **MCP-Zugriff** unter *Einstellungen → System* lässt du Claude von überall deine Einträge lesen - und, wenn du es erlaubst, korrigieren: siehe [MCP-Zugriff](mcp.de.md).

## Archivieren und löschen
*Einstellungen → Auto → Sichern & verwalten*. **Archivieren** blendet das Auto aus der Autoauswahl und vom Dashboard aus; es steht ausgegraut ganz unten auf der Seite *Fahrzeuge*, wo **Wieder aktivieren** es zurückholt. **Löschen** entfernt das Auto samt aller Daten endgültig.

## Optionale Dienste (standardmäßig aus)
Nichts verlässt deinen Server, wenn du es nicht unter *Einstellungen* einschaltest:
- **Karteninfos** (*System*): zeigt die Standort-Karte mit OpenStreetMap-Kacheln, über die App geladen, **und** benennt Start und Ziel jeder Fahrt (aus einer Offline-Liste der Städte der Welt; mit eingetragener Adresse für Ortsnamen: von diesem Nominatim-kompatiblen Server), sodass das Fahrtenbuch Namen statt Koordinaten zeigt. Die Karte ist standardmäßig aus. Die Ortsnamen brauchen kein Internet; eine Adresse für Ortsnamen (ein Nominatim-kompatibler Server, nur https) ist optional, wird dann nur bei eingeschalteten Karteninfos gefragt und liefert auch die Straße des Autos.
- **Spritpreise**: werden auf der Tanken-Seite mit dem Zahnrad oben eingestellt (Preisquellen je Land, deine eigenen Keys, Startwerte) – für Deutschland brauchst du **deinen eigenen** kostenlosen Key von tankerkoenig.de, es gibt keinen eingebauten Key. **Tanken** wird am Tankstand erkannt: springt er um 15 Punkte oder mehr, erscheint ein unfertiger Tank-Eintrag mit einem Knopf *Ergänzen* (nur Menge und Preis vom Beleg fehlen), und du kannst unter *Einstellungen → Benutzer* darüber benachrichtigt werden. Bei Autos mit Batterie geht dasselbe für das **Laden**: Beginnt das Auto zu laden, eröffnet die App einen Ladevorgang (Zeit, Batteriestand, höchste Leistung) und legt am Ende einen unfertigen Eintrag an (Energie und Preis von der Rechnung fehlen; eine ungefähre Energie schätzt sie aus der Batteriegröße) und listet die Ladevorgänge auf der Seite. Ergänzt du den Eintrag von der Rechnung, zeigt der Ladevorgang die echte Energie, die Kosten, den Preis je kWh und den **Ladeverlust** (abgerechnet gegenüber dem, was in der Batterie ankam), und eine Zusammenfassung der letzten 90 Tage addiert Ladevorgänge, Energie, Kosten, Durchschnittspreis und Spitzenleistung sowie schnelles gegenüber langsamem Laden.

## Backup
*Einstellungen → System* lädt ein Backup von allem herunter und spielt es zurück; *Einstellungen → Auto → Sichern & verwalten* sichert ein einzelnes Auto (siehe [Sicherungen](backup.de.md)).
