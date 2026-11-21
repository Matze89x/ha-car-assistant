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

`RELEASE.FEATURES.FEHLER` plus die Stufe (Alpha / Beta): Die erste Zahl zählt Releases, die zweite Features, die dritte Fehlerkorrekturen. Nur `release.json` hält den Wert; `tools/release.py` schreibt ihn überall hin. Siehe [CONTRIBUTING](../CONTRIBUTING.de.md).

## Die Developer-App

`carassistant-dev/` ist eine zweite App im selben Repository (*Car Assistant Developer*, Slug `carassistant_dev`, eigene Daten). Ihr Dockerfile lädt beim Bauen den Zweig `dev` herunter. Ihre Version ist die nächste Version plus ein Zähler (`0.5.1.3`) in `release.json` (`dev`): `python tools/release.py dev` für jeden Schritt, der als Update ankommen soll (`dev 0.5.2` beginnt eine neue Basis bei `.1`). Der Store liest die App-Liste aus `main`: nach `git push origin dev` also `tools/publish_dev.sh` ausführen, das legt nur den Ordner `carassistant-dev/` auf `main` (die veröffentlichte App dort bleibt unberührt). Geht ein Release nach `main` (`dev` mergen, `python tools/release.py set 0.5.1`), sofort die nächste Basis setzen: `python tools/release.py dev 0.5.2`.

## Labels und Automatik

- Die Labels stehen in `.github/labels.yml`; *Actions → Sync labels → Run workflow* legt sie an.
- `.github/CODEOWNERS` lässt jeden Pull Request auf den Maintainer warten.
- `.github/dependabot.yml` schlägt Bibliotheks-Updates vor; `.github/workflows/ci.yml` lässt die Tests bei jedem Push und Pull Request laufen.

## Einstellungen des Repositorys (einmalig)

Eine kurze Liste steht in der Checkliste des Maintainers: eine Regel für `main` (Pull Request, CI muss grün sein, Code-Owner-Prüfung, kein Force-Push), Freigabe in *Actions* für Erstbeitragende und ein Nur-Lese-Token, *Discussions* an, private Meldung von Sicherheitslücken, Dependabot-Warnungen, Secret Scanning mit Push Protection.
