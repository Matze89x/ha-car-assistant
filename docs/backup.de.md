# Sicherungen

[🇬🇧 English](backup.md) · 🇩🇪 Deutsch

Car Assistant hat zwei getrennte Sicherungen. Jede lässt sich einzeln anlegen und wiederherstellen.

## Zugangsdaten und die Passphrase

Eine Sicherungsdatei ist dazu gemacht, mitgenommen zu werden – auf ein anderes System, in einen Cloud-Ordner, zu einem Bekannten –, deshalb enthält sie **ohne Passphrase kein Geheimnis**: kein gemerktes Anbindungs-Token, kein Passwort eines Plugins, keinen Zugangsschlüssel einer Quelle, keinen Zugangscode einer Integrationsseite.

Mit einer **Passphrase** (mindestens 8 Zeichen, beim Sichern gewählt, nie gespeichert) liegen sie alle in einem Block der Datei, `secrets.enc`. Der Block ist mit einem Schlüssel verschlüsselt, der aus der Passphrase abgeleitet wird (scrypt mit frischem Zufallssalz), und beglaubigt: eine falsche Passphrase oder ein veränderter Block wird erkannt, und ohne die Passphrase liest ihn niemand. Die Passphrase wird in ein Formular getippt – sie ist nie Teil einer Adresse, eines Protokolls oder der Datei.

- Eine Datei mit Zugangsdaten fragt beim Wiederherstellen nach ihrer Passphrase. Eine falsche stoppt, bevor etwas angefasst wird. *Ohne die Zugangsdaten wiederherstellen* bringt alles andere zurück und lässt Tokens, Passwörter, Schlüssel und Codes leer.
- Eine vergessene Passphrase verliert nur die Zugangsdaten (Plugins neu einrichten, Passwörter neu eintragen); die Daten sind ohnehin in der Datei.
- Die Sicherheitskopie, die Car Assistant vor dem Ersetzen eines Autos oder des ganzen Systems anlegt, bleibt auf diesem System und hält ihre Zugangsdaten mit dem Schlüssel dieses Systems versiegelt: das Zurücknehmen eines Ersetzens braucht dort keine Passphrase.

## 1. Fahrzeug-Sicherung (ein Auto)

Das Dateiformat steht in [vehicle-file.de.md](vehicle-file.de.md) - es ist auch der Weg, ein Auto aus einem anderen Programm zu importieren.

*Einstellungen → Auto → Sichern & verwalten* lädt eine Zip mit allem, was **nur zu diesem Auto** gehört:

- das Fahrzeug und alle seine Listen (Service, Tanken und Laden, **Ladevorgänge**, Fahrten mit Strecke und Zusammenfassungen, Termine, Aufgaben, Reifen, Umbauten, Teile, Zähler, Dokumente, Fotos und Videos), seine Live-Werte und die Ereignisse, Positionen und Signale, die seine Plugins gemeldet haben
- das **Handbuch** samt Seitenbildern, wenn es als Paket importiert wurde (siehe [manual-package.de.md](manual-package.de.md); die Bilder vergrößern die Datei, bis zur Grenze von 500 MB)
- **jede Einstellung dieses Autos** (Navigation, Home-Widgets, ausgeblendete Funktionen, der Strompreis zu Hause, ...)
- seine **Anbindungs-Token** (der Fingerabdruck, den der Server speichert – ein Plugin funktioniert danach mit seinem bisherigen Token weiter); mit Passphrase auch das gemerkte Token selbst, damit die Einrichtung es wieder anbieten kann
- seine **Integrationen und Plugins** mit ihren Einstellungen und Einträgen, **woher jedes kam** (seine Quelle, Version und Prüfsumme) und ob es lief – aber **nicht die Pakete selbst**; mit Passphrase auch die Passwörter der Plugins, die Zugangsschlüssel ihrer Quellen und die Zugangscodes der Integrationsseiten

*Fahrzeug hinzufügen → Fahrzeug aus einer Sicherung wiederherstellen* legt aus so einer Datei ein **neues** Fahrzeug an (gleicher Name bekommt eine Nummer); ein Auto, das schon da ist, wird ersetzt oder kopiert, wie du wählst. Danach gilt:

- Integrationen und Plugins sind **ausgeschaltet** – schalte sie bewusst ein;
- ein noch nicht installiertes Paket erscheint unter Plugins / Integrationen als *braucht das Paket*. Bietet eine Quelle es an, gibt es einen Knopf *Installieren*; fehlt die Quelle, steht dort, welche Adresse du zuerst unter *Quellen* eintragen musst;
- ein Token, das dieses System schon kennt (eine Kopie neben dem Original), wird nicht doppelt angelegt: richte das Plugin dann für ein neues neu ein.

## 2. System-Sicherung (alles)

*Einstellungen → System → Sichern* ist die ganze Datenbank mit allen Dateien: jedes Fahrzeug, die **Benutzer** und die Einstellungen. Mit Passphrase verlassen die Zugangsdaten der Datenbank – die gemerkten Tokens, die Passwörter der Plugins, die Zugangsschlüssel der Quellen, die Zugangscodes und der Push-Schlüssel – die Kopie und reisen im verschlüsselten Block mit; eine Wiederherstellung auf einem **anderen System** bringt sie dann zurück (mit dem Schlüssel jenes Systems versiegelt). Ohne bleiben sie mit dem Schlüssel dieses Systems versiegelt und sind anderswo nutzlos. Die Passwort-Prüfwerte aller Benutzer sind in beiden Fällen in der Datei: sicher aufbewahren. Das Wiederherstellen ersetzt alles (eine Sicherheitskopie des jetzigen Stands bleibt erhalten).

## Kompatibilität

Jede Sicherung trägt eine `format`-Nummer (jetzt **2**; die System-Sicherung dazu die Nummer ihres Datenbank-Schemas `schema`). **Ein neueres Car Assistant spielt jedes ältere Format ein** – ab sofort, nicht erst ab 1.0:

- die *goldenen Dateien* in [`tests/fixtures/backups/`](../tests/fixtures/backups/README.md) – eine Sicherung jedes Formats, das es je gab, vom Code dieses Formats gemacht und nie verändert – spielt die Testsuite bei jeder Änderung ein; ein neues Format bringt seine goldene Datei zuerst mit, sonst scheitern die Tests;
- eine ältere Datenbank bringen die Migrationen auf den neuen Stand; der Leser ignoriert unbekannte Spalten und füllt fehlende mit ihrem Standardwert, kleine Änderungen machen eine alte Datei also nicht kaputt;
- eine Sicherung aus einer **neueren** App wird mit dem Hinweis abgelehnt, zu aktualisieren;
- nichts von einem Auto geht verloren, wenn die App wächst: jede Tabelle der Datenbank gehört entweder zur Fahrzeug-Sicherung oder steht in `vehiclebackup.py` als ausgelassen, mit Grund (Protokolle und Verkehrsansichten der Plugins, die Personen und Geräte des ganzen Systems) – für eine neue Tabelle, die in keiner Liste steht, scheitert ein Test –, und ebenso jede Einstellung, die der Code je Auto hält.

Was sich geändert hat: **Format 2** (0.5.37) – Ladevorgänge, Fahrtzusammenfassungen, Ereignisse, Positionen und Signale eines Autos, jede Einstellung eines Autos (der Strompreis zu Hause fehlte), woher jedes Paket kam, und der Block der Zugangsdaten; **Format 1** – das erste.

Die Demo-Autos der [Quellen-Repo](https://github.com/Matze89x/ha-car-assistant-sources) sind auf diese Weise gemachte Fahrzeug-Sicherungen (`tools/make_demo_vehicles.py`); zum Auffrischen: wiederherstellen, anpassen und die Sicherung neu herunterladen.
