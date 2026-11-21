# Sicherungen

[🇬🇧 English](backup.md) · 🇩🇪 Deutsch

Car Assistant hat zwei getrennte Sicherungen. Jede lässt sich einzeln anlegen und wiederherstellen.

## 1. Fahrzeug-Sicherung (ein Auto)

Das Dateiformat steht in [vehicle-file.de.md](vehicle-file.de.md) - es ist auch der Weg, ein Auto aus einem anderen Programm zu importieren.

*Einstellungen → Auto → Sichern & verwalten* lädt eine Zip mit allem, was **nur zu diesem Auto** gehört:

- das Fahrzeug und alle seine Listen (Service, Tanken / Laden, Fahrten mit Strecke, Termine, Aufgaben, Reifen, Umbauten, Teile, Zähler, Dokumente, Fotos und Videos), seine Live-Werte
- das **Handbuch** samt Seitenbildern, wenn es als Paket importiert wurde (siehe [manual-package.de.md](manual-package.de.md); die Bilder vergrößern die Datei, bis zur Grenze von 500 MB)
- seine Einstellungen (Navigation, Home-Widgets, ausgeblendete Funktionen)
- seine **Anbindungs-Token** (der Fingerabdruck, den der Server speichert – ein Plugin funktioniert danach mit seinem bisherigen Token weiter)
- seine **Integrationen und Plugins mit ihren Einstellungen** – aber **nicht die Pakete selbst**

*Fahrzeug hinzufügen → Fahrzeug aus einer Sicherung wiederherstellen* legt aus so einer Datei ein **neues** Fahrzeug an (gleicher Name bekommt eine Nummer). Danach gilt:

- Integrationen und Plugins sind **ausgeschaltet** – schalte sie bewusst ein;
- ein noch nicht installiertes Paket erscheint unter Plugins / Integrationen als *braucht das Paket*. Bietet eine Quelle es an, gibt es einen Knopf *Installieren*; fehlt die Quelle, steht dort, welche Adresse du zuerst unter *Quellen* eintragen musst;
- ein Token, das dieses System schon kennt (eine Kopie neben dem Original), wird nicht doppelt angelegt: richte das Plugin dann für ein neues neu ein.

Die Datei enthält Plugin-Einstellungen, darin können Passwörter stehen: bewahre sie sicher auf.

## 2. System-Sicherung (alles)

*Einstellungen → System → Sichern* ist die ganze Datenbank mit allen Dateien: jedes Fahrzeug, die **Benutzer** und die Einstellungen. Die Datei enthält auch gespeicherte **Zugangscodes** und die Passwort-Prüfwerte aller Benutzer: sicher aufbewahren. Das Wiederherstellen ersetzt alles (eine Sicherheitskopie des jetzigen Stands bleibt erhalten).

## Kompatibilität

Jede Sicherung trägt eine `format`-Nummer. **Ab Version 1.0 spielt ein neueres Car Assistant jedes ältere Format ein**; eine Sicherung aus einer neueren App wird mit dem Hinweis abgelehnt, zu aktualisieren. Der Leser ignoriert unbekannte Spalten und füllt fehlende mit ihrem Standardwert, kleine Änderungen machen eine alte Datei also nicht kaputt. Vor 1.0 darf sich das Format noch ändern.

Die Demo-Autos der [Quellen-Repo](https://github.com/Matze89x/ha-car-assistant-sources) sind auf diese Weise gemachte Fahrzeug-Sicherungen (`tools/make_demo_vehicles.py`); zum Auffrischen: wiederherstellen, anpassen und die Sicherung neu herunterladen.
