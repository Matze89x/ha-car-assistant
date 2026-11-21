# MCP-Zugriff (Claude Code)

[🇬🇧 English](mcp.md) · 🇩🇪 Deutsch

Mit dem MCP-Zugriff kann **Claude Code** (oder ein anderer MCP-Client) in dein Car Assistant schauen und - wenn du es erlaubst - Einträge korrigieren. Gedacht ist es, um Fehler gemeinsam mit Claude zu finden und zu beheben: *„Warum ist der Verbrauch des Diesels so niedrig?“*, *„Korrigiere das Datum dieses Service-Eintrags“*.

Es ist **standardmäßig aus** und immer unter deiner Kontrolle.

## Was zuerst nötig ist

MCP lässt sich nur einschalten, wenn alle drei Dinge da sind (die Karte in den Einstellungen sagt dir, was fehlt):

1. Ein **Benutzer** existiert (Einstellungen → Benutzer).
2. Deine **externe https-Adresse** ist gespeichert (Einstellungen → System → Adresse dieser App).
3. Der **Port der App ist offen** (Home Assistant: Reiter *Netzwerk* der App).

Fällt später eines davon weg (Adresse entfernt, Port geschlossen), ist MCP sofort wieder aus.

## Einschalten

1. Öffne *Einstellungen → System → MCP-Zugriff*.
2. Wähle die **Stufe**:
   - **Aus** - nichts funktioniert (Standard; die Adresse antwortet nicht einmal).
   - **Lesen** - der Client kann alles unten Beschriebene ansehen, aber nichts ändern.
   - **Lesen und schreiben** - der Client darf zusätzlich Einträge der Autos anlegen, ändern und löschen.
3. Erstelle den **Zugriffsschlüssel** (ein Schlüssel für alles). Die Stufe oben entscheidet, was er darf - eine zweite Einstellung gibt es nicht.
4. Kopiere den Schlüssel **jetzt** - er wird nur einmal angezeigt, gespeichert wird nur ein Hash. Ist er weg oder geleakt, tippe auf **Schlüssel erneuern**: Es entsteht ein neuer, und der alte gilt sofort nicht mehr (ändere ihn dann auch in Claude).

## Claude Code verbinden

Claude Code fügt den Server mit einem Befehl hinzu (die Schlüssel-Seite zeigt ihn mit deiner Adresse und dem Schlüssel schon ausgefüllt):

```bash
claude mcp add --transport http car-assistant https://car.example.com/mcp --header "Authorization: Bearer cam_..."
```

Frage dann Claude Code etwas wie *„Liste meine Fahrzeuge auf“*. Die Adresse ist deine externe https-Adresse plus `/mcp`.

## Von überall nutzen: ein Connector in deinem Claude-Konto

Ein *eigener Connector* gehört zu deinem Claude-Konto, ist also im Web-Chat, in der Desktop-App und auf dem Handy da - und du kannst von dort aus Claude deine Daten vervollständigen lassen.

1. Öffne in Claude **Customize → Connectors → Hinzufügen → Benutzerdefinierten Konnektor hinzufügen** (englisch: *Add custom connector*; Team-Konten: Organisationseinstellungen → Connectors).
2. Gib die Adresse `https://deine-adresse/mcp` ein - **ohne Port** wie `:8443` (dorthin verbindet sich Claude nicht), und der Server muss aus dem Internet erreichbar sein.
3. Am einfachsten: nimm die Adresse **mit dem Schlüssel** von der Schlüssel-Seite (`https://deine-adresse/mcp/cam_...`) und lass alles andere leer. Sicherer, wenn dein Dialog *Request headers* hat: nimm die schlichte Adresse und füge den Header `Authorization` mit dem Wert `Bearer cam_...` hinzu. Es gibt kein OAuth: die App nutzt den festen Schlüssel.
4. Speichern und den Connector in einem Chat einschalten. Frage zum Beispiel: *„Sieh dir meine Fahrzeuge an und sag mir, welche Daten fehlen“* - Claude ruft `data_gaps` auf und fragt dich nach den Werten.

Die Request headers lassen sich später nicht ändern: für einen neuen Schlüssel den Connector entfernen und neu hinzufügen.

## Was der Client kann

| Werkzeug | Braucht | Was es tut |
|---|---|---|
| `app_info` | Lesen | Version, Stufe, Größe, die Arten von Einträgen |
| `list_vehicles` | Lesen | alle Fahrzeuge mit Kurzname, Name, Kraftstoff, Kilometerstand |
| `get_vehicle` | Lesen | alle Daten eines Fahrzeugs, Live-Werte, was Aufmerksamkeit braucht, Anzahl der Einträge |
| `list_entries` | Lesen | die Einträge einer Art (Service, Tanken, Termine, Aufgaben, Reifen, Umbauten, Teile, Fahrten, Zähler), neueste zuerst, seitenweise |
| `get_costs` | Lesen | Kosten je Tag / Woche / Monat und jeder Eintrag mit Preis |
| `data_gaps` | Lesen | was noch fehlt: leere Fahrzeugfelder, Tankungen ohne Kilometerstand / Menge / Preis, Service ohne Kosten oder Kilometerstand, nie erledigte Aufgaben, Fahrten ohne Orte |
| `get_logs` | Lesen | die neuesten Log-Zeilen der Plugins - nützlich, wenn etwas nicht läuft |
| `list_plugins` | Lesen | Plugins und Integrationen eines Fahrzeugs: Name, Version, an / aus, eingerichtet, Einstellungen (Geheimnisse verborgen) |
| `list_documents` | Lesen | die Dokumente eines Fahrzeugs (Titel, Kategorie, Größe - nicht die Dateien) |
| `get_charging` | Lesen | Ladevorgänge eines Elektroautos |
| `get_tyres` | Lesen | empfohlene Reifendrücke und Reifensätze |
| `get_settings` | Lesen | Sprache, Einheiten, Währung und wie viele Fahrzeuge / Plugins / Integrationen es gibt |
| `add_entry` | Schreiben | einen Eintrag anlegen (falsche Werte werden mit Grund abgelehnt) |
| `update_entry` | Schreiben | nur die genannten Felder eines Eintrags ändern |
| `delete_entry` | Schreiben | einen Eintrag löschen (nicht rückgängig zu machen) |

Werte sind in Basiseinheiten (km, Liter oder kWh, bar, °C, Geld als reine Zahl), unabhängig von den Einheiten, die du zur Anzeige gewählt hast.

## Was nie geht

- Einstellungen, Benutzer, Passwörter, Schlüssel, Plugins, Quellen oder die Adresse der App ändern;
- Geheimnisse zeigen (Passwörter, Tokens, Zugriffsschlüssel, die externe Adresse);
- aus dem Home-Assistant-Panel, von einer anderen Webseite (der `Origin` wird geprüft) oder ohne Schlüssel genutzt werden.

## Sicherheit

- **Nur https**, und nur solange alle Voraussetzungen erfüllt sind.
- Es gibt **einen Schlüssel**, der nur als **Hash** gespeichert wird; Erneuern oder Löschen sperrt alle Clients sofort aus.
- Falsche Schlüssel werden ausgebremst, und die Adresse wird nach zu vielen Versuchen eine Zeit lang gesperrt; jeder Schlüssel ist auf 120 Aufrufe pro Minute begrenzt.
- **Alles, was ein Schlüssel tut, wird protokolliert** (die letzten Aufrufe stehen auf der Karte in den Einstellungen).
- Schreibzugriff ändert echte Daten. **Mach vorher eine Sicherung** (Einstellungen → System) und nimm *Lesen*, solange Claude nichts korrigieren soll.
- Behandle einen Schlüssel wie ein Passwort. Nicht in ein Repository, einen Chat oder einen Screenshot.

## Wenn es nicht klappt

| Anzeichen | Wahrscheinlicher Grund |
|---|---|
| `404` | MCP ist aus, oder eine Voraussetzung fehlt (siehe Karte), oder du hast die Adresse des Home-Assistant-Panels genommen |
| `401` | falscher oder gelöschter Schlüssel |
| `403` | die Anfrage kam von einer Webseite (ein `Origin`, der nicht deine Adresse ist) |
| `429` | zu viele falsche Schlüssel von dieser Adresse (15 Minuten warten) oder mehr als 120 Aufrufe pro Minute |
| Schreiben wird abgelehnt | der Schlüssel oder die Stufe des Servers ist *Lesen* |
