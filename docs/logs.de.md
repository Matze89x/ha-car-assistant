# Die Protokolle

[🇬🇧 English](logs.md) · 🇩🇪 Deutsch

Car Assistant führt **zwei Protokolle**. Sie sagen Verschiedenes, und in jedem schaust du nach seiner eigenen Art von Ärger.

| | Das Protokoll des Add-ons | Die Seite *Protokoll* eines Plugins |
|---|---|---|
| **Wo** | Home Assistant: *Einstellungen → Apps → Car Assistant → Protokoll* (oder *Einstellungen → System → Protokolle*, dann die App wählen) | In der App: die Kachel eines Plugins → *Protokoll* |
| **Was es sagt** | Die App selbst: wie sie startet, was sie nicht erreicht, was schiefging - und eine Stufe tiefer, was sie tut | Was EIN Plugin für EIN Fahrzeug tut: Lesungen, Läufe, Befehle, Anmeldungen, das Leben seines Dienstes |
| **Wie viel** | Die Option `log_level` der App (Reiter *Konfiguration*, siehe unten) | Probleme immer; die Zeilen mit Einzelheiten nur, solange der Schalter *Debug* dieses Plugins an ist (er schaltet sich nach einigen Tagen selbst aus) |
| **Aufbewahrt** | Von Home Assistant | Von der App: die neuesten Zeilen jedes Plugins; wie lange: *Einstellungen → System* |

## Die Stufen des Add-on-Protokolls

| `log_level` | Was du siehst |
|---|---|
| `error` | Nur Fehler: etwas ging kaputt - ein Durchlauf einer Aufgabe, der Dienst eines Plugins, der von selbst stehen blieb, eine Anmeldung, die scheiterte - mit den Einzelheiten, die ein Entwickler braucht. |
| `warning` (Standard) | Fehler und Warnungen: Home Assistant oder der MQTT-Broker ist nicht erreichbar, eine Benachrichtigung ging nicht hinaus, ein Plugin hat Ärger mit einer seiner Entitäten, eine Quelle oder ein Anbieter antwortete schlecht. Dieselbe Warnung steht in fünf Minuten einmal; die nächste sagt *repeated 12x in the last 6 min*. |
| `info` | Dazu, was die App tut: der Start, eine Datenbank, die weitergezogen ist, die Live-Verbindung zu Home Assistant, MQTT, das Lesen der Quellen, die Suche nach einer neueren Version, Sicherungen und die Zeilen, die die App für Plugins schreibt (eine Lesung begonnen, ein Befehl gesendet, eine Anmeldung, ein Dienst gestartet). |
| `debug` | Dazu eine Zeile für jede Seite, die aufgerufen wird (`GET /v/{vid}/fuel -> 200 (31 ms)`), und eine für jede Lieferung von Werten (`data from Home Assistant for vehicle 1: odometer_km: stored`). |

Ändere sie unter *Einstellungen → Apps → Car Assistant → Konfiguration*, speichere und starte die App neu. `info` und `debug` sind zum Suchen eines Problems da: Stell danach wieder auf `warning`. Eine App, die vor dieser Seite eingerichtet wurde, behält die Stufe, mit der sie gespeichert wurde (`error` war damals der Standard).

Eine Zeile sieht so aus (die Texte sind Englisch):

```text
2026-11-27 12:03:10 DEBUG   carassistant.http: GET /v/{vid}/fuel -> 200 (31 ms)
2026-11-27 12:03:11 DEBUG   carassistant.connectors: data from Home Assistant for vehicle 1: odometer_km: stored
2026-11-27 12:05:00 WARNING carassistant.plugins: [car 1] home-assistant: Home Assistant cannot be reached; trying again
```

Die Zeilen, die mit `[car 1] home-assistant` beginnen, sind die Zeilen, die die App auf die Seite *Protokoll* dieses Plugins schreibt - hier auch gesagt, damit ein Ort die ganze Geschichte erzählt. Was ein Plugin selbst sendet oder ausgibt, bleibt auf seiner eigenen Seite.

## Was nie darin steht

Das Add-on-Protokoll ist das, was Leute in ein Forum kopieren. Es ist deshalb so geschrieben, dass man es kopieren kann - auf jeder Stufe:

- **Kein Token, Passwort oder Schlüssel.**
- **Kein Wert des Fahrzeugs** (Position, Kilometerstand, Tankstand ...): Eine Lieferung nennt die Felder und was aus jedem wurde (*stored*, *ignored*), nie die Zahlen.
- **Keine Adresse mit Nummern oder einem Token darin, keine Abfrage, kein Inhalt.** Eine Anfrage heißt nach dem *Muster* ihrer Route (`/v/{vid}/fuel`), nicht nach dem, was gefragt wurde. Die Prüfungen des Wächters und die Dateien der eigenen Stile und Skripte der App fehlen.
- **Kein Name einer Person.** Ein Befehl sagt, was gesendet wurde, nicht wer die Taste drückte - das steht auf der Seite *Protokoll* des Plugins.
- **Kein freier Text eines Plugins.** Was ein Plugin an die App sendet oder ausgibt, bleibt auf seiner eigenen Seite *Protokoll*.

Die Bibliotheken, die die App benutzt, kommen erst ab Warnung zu Wort, gleich welche Stufe gilt: `debug` zeigt die App und nicht ihre Teile.

Lies trotzdem, was du kopierst, bevor du es postest.
