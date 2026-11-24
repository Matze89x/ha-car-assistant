# Pflege: von der Meldung zur Version

[🇬🇧 English](maintaining.md) · 🇩🇪 Deutsch

Wie Meldungen und Beiträge zur nächsten Version werden. Beitragende ändern nie die Version - die Maintainer bündeln sie.

## Der Weg einer Änderung

1. **Meldung oder Pull Request** kommt an (ein Issue mit Vorlage oder ein Pull Request aus einem Fork - auch einer, der mit einem KI-Assistenten entstanden ist).
2. **Sichten:** Es bekommt das Label `needs-triage`, dann `accepted`, `needs-info`, `needs-decision` oder `wontfix`. Fragen und Ideen gehören in die *Discussions*.
3. **Bündeln:** Angenommene Arbeit kommt in einen **Meilenstein**, der wie die nächste Version heißt, zum Beispiel `0.5.1 Beta`. Eine Fehler-Version sammelt etwa 4-5 Korrekturen oder kleine Verbesserungen.
4. **Mergen:** Die Pull Requests des Meilensteins kommen in `main` (die CI muss grün sein, der Code-Owner prüft).
5. **Version:** Der Maintainer führt je Bündel einmal `python tools/release.py fix "English line" "Deutsche Zeile"` aus (ein neues Feature: `feature`). Das zählt die Zahl hoch und schreibt sie überall hin und in beide Änderungsprotokolle.
6. **Tag und Release:** `git tag v0.5.1-beta`, dann *Releases → Draft a new release → Generate release notes* (nach Label sortiert, siehe `.github/release.yml`).

## Versionsnummern

`RELEASE.FEATURES.FEHLER` plus die Stufe (Alpha / Beta): Die erste Zahl zählt Releases, die zweite Features, die dritte Fehlerkorrekturen. Nur `release.json` hält den Wert; `tools/release.py` schreibt ihn überall hin. Siehe [CONTRIBUTING](community/contributing.de.md).

## Die Developer-App

`carassistant-dev/` ist eine zweite App im selben Repository (*Car Assistant Developer*, Slug `carassistant_dev`, eigene Daten). Ihr Dockerfile lädt beim Bauen den Zweig `dev` herunter. Ihre Version ist die nächste Version plus ein Zähler (`0.5.1.3`) in `release.json` (`dev`): `python tools/release.py dev` für jeden Schritt, der als Update ankommen soll (`dev 0.5.2` beginnt eine neue Basis bei `.1`). Der Store liest die App-Liste aus `main`: nach `git push origin dev` also `tools/publish_dev.sh` ausführen, das legt nur den Ordner `carassistant-dev/` auf `main` (die veröffentlichte App dort bleibt unberührt). Geht ein Release nach `main` (`dev` mergen, `python tools/release.py set 0.5.1`), sofort die nächste Basis setzen: `python tools/release.py dev 0.5.2`.

## Labels und Automatik

- Die Labels stehen in `.github/labels.yml`; *Actions → Sync labels → Run workflow* legt sie an.
- `.github/CODEOWNERS` lässt jeden Pull Request auf den Maintainer warten.
- `.github/dependabot.yml` schlägt Bibliotheks-Updates vor; `.github/workflows/ci.yml` lässt die Tests bei jedem Push und Pull Request laufen.

## Die Style-Sheets sauber halten

Das Aussehen der App steckt in zwei Dateien (`static/app.css`, darüber `static/pc-core.css`) und einer Regel: **eine Definition je Baustein** (siehe [design.de.md](design.de.md), „Die festen Bausteine“). Zwei kleine Werkzeuge halten sie ordentlich; lass sie ab und zu laufen und sieh danach jede Seite an (`python tools/make_screenshots.py`, vorher und nachher vergleichen):

- `python tools/css_tidy.py <datei.css> [--write]` entfernt Angaben, die eine spätere Regel mit demselben Selektor immer überschreibt.
- `python tools/css_prune.py <datei.css> [--write] [--list]` entfernt Selektoren, deren Klasse nirgends benutzt wird (Vorlagen, Skripte, Python); aus einem Präfix gebaute Klassen zählen als benutzt.

`tests/test_design_rules.py` bewacht den Rest: ausgeglichene Klammern (ein überzähliges `}` lässt den Browser still die nächste Regel überspringen), die Schriftgrößen-Skala, die Rundungen, eine Knopf-Regel, nur zwei Arten von Tab-Leisten.

## Die App im Browser und mit Übungsfotos prüfen

Vier kleine Werkzeuge in `tools/` (sie brauchen Google Chrome oder Chromium; das Foto-Werkzeug auch Tesseract) sehen sich die App an wie ein Mensch, auf einer vorübergehenden Installation mit ausgedachten Autos - von einer echten Installation wird nichts gelesen:

- `python tools/check_alignment.py` - öffnet jede Seite der *Weiteres*-Liste und misst, dass der erste Block, der Titel und der Abstand zur Liste auf einer Linie liegen (siehe [Design](design.de.md)); `tests/test_page_alignment.py` führt es aus.
- `python tools/check_headings.py` - öffnet jede Seite der *Weiteres*-Liste und prüft, dass jede allein stehende Überschrift die Abschnittsbeschriftung des [Design-Buchs](design.de.md) ist (11 px, Großbuchstaben, gedämpft, linksbündig); `tests/test_page_headings.py` führt es aus.
- `python tools/check_ui.py [--width 360] [--lang de]` - öffnet jede Seite (aufgeklappte Formulare inklusive) und misst die festen Regeln: kein Knopf bricht um, eine Knopfreihe ist eine Zeile und eine Höhe, eine Hauptaktion je Karte, Formularleisten unten rechts, Tippflächen ab 30 px, jeder Knopf hat einen Namen und jedes Feld eine Beschriftung; `tests/test_page_ui.py` führt Deutsch in Handybreite und Englisch breit aus.
- `python tools/perf_sweep.py [--cars 15] [--scale 1]` - baut eine temporäre Installation mit 15 Autos und tausenden Zeilen je Auto (Stände, Tankungen, Fahrten mit Punkten, Spur, Signalverlauf ...), öffnet jede erreichbare Seite und listet die langsamsten; es schlägt fehl, wenn eine Seite mehr als `--limit` ms braucht (110), `--profile SEITE` zeigt, wohin die Zeit einer Seite geht. Zuletzt gemessen: jede Seite unter 76 ms bei `--scale 1`, die Fahrten-Seiten etwa 280 ms bei der fünffachen Datenmenge.
- Ein rotes CI: das Log ist nur angemeldet lesbar, aber jeder fehlgeschlagene Test steht auch als *Annotation*, die die öffentliche API zeigt (`curl https://api.github.com/repos/<Besitzer>/<Repo>/check-runs/<id>/annotations`) - siehe `pytest_terminal_summary` in `tests/conftest.py`.
- `python tools/smoke_crawl.py` - geht durch alle Seiten (ein paar Minuten) und meldet einen Serverfehler, einen Skriptfehler, eine fehlgeschlagene Anfrage oder eine verletzte Regel der Content Security Policy; ein kurzer Gang läuft als `tests/test_smoke_crawl.py`.
- `python tools/ocr_bench.py` - liest jedes Foto des **Übungssatzes** (`tools/practice_photos.py`: ausgedachte Tachos und Tankbelege in mehreren Stilen und Sprachen, jedes mit seiner richtigen Antwort) wie es ist und so schlecht, wie ein Handy es machen kann (unscharf, dunkel, schief, klein, stark komprimiert, mit Spiegelung) und zählt die richtigen Antworten. Vor und nach einer Änderung des Lesens ausführen: Die Zahl darf nicht sinken (saubere Fotos: `tests/test_ocr_practice.py`). `python tools/practice_photos.py <Ordner>` schreibt die Fotos und ihre Antworten, zum Üben von Hand.
- `python tools/make_screenshots.py` - die Bilder der Dokumentation (siehe seine Beschreibung); `tools/cdp.py` ist der kleine DevTools-Client, den die Werkzeuge gemeinsam nutzen.

## Einstellungen des Repositorys (einmalig)

Eine kurze Liste steht in der Checkliste des Maintainers: eine Regel für `main` (Pull Request, CI muss grün sein, Code-Owner-Prüfung, kein Force-Push), Freigabe in *Actions* für Erstbeitragende und ein Nur-Lese-Token, *Discussions* an, private Meldung von Sicherheitslücken, Dependabot-Warnungen, Secret Scanning mit Push Protection.
