# Mitmachen

[🇬🇧 English](CONTRIBUTING.md) · 🇩🇪 Deutsch

Danke, dass du helfen willst. Car Assistant entsteht in der Freizeit, deshalb sind kleine, klar abgegrenzte Änderungen nach den Regeln unten am leichtesten zu prüfen.

## Ideen, Fehler und Fragen

Sei freundlich: siehe den [Verhaltenskodex](CODE_OF_CONDUCT.de.md). Fragen und Ideen, die keine Fehler sind, gehören in die *Discussions*.

- Öffne ein **Issue** mit der passenden Vorlage. Bei einem Fehler: die Version (*Einstellungen → Über*), was du getan hast, was du erwartet hast und was passiert ist.
- Ein Sicherheitsproblem ist **kein** Issue: siehe [SECURITY.de.md](SECURITY.de.md).
- Dein eigenes Plugin oder deine eigene Integration liegt in deinem eigenen Repository und wird als *Quelle* hinzugefügt - siehe die [Plugin-Anleitung](docs/plugin-guide.de.md) und die [Beispiele](docs/examples/README.de.md). Ein Plugin für ein bestimmtes Auto oder Gerät gehört nicht in dieses Repository.

## Starten und testen

```
pip install -r carassistant/requirements.txt pytest ruff httpx pyyaml
CARASSISTANT_DATA=/tmp/cd CARASSISTANT_DEV=1 CARASSISTANT_PORT=8123 PYTHONPATH=carassistant/app python -m carassistant
```

Vor jedem Pull Request (die CI macht dasselbe):

```
ruff check . && ruff format --check . && pytest -q
```

## Die Regeln

- **Nichts Privates** in Code, Docs, Tests oder Bildern: keine Namen, Adressen, Tokens, Marken oder Fahrzeugdaten. Nimm neutrale Werte (`car.example.com`, `Example`, `AB-CD 123`).
- **Alles zu einem Auto gehört zu diesem Auto.** Die App spricht nie selbst mit einem Auto; das macht ein Plugin über die [Plugin-API](docs/api.de.md).
- **Texte und Sprache:** neue Texte kommen in `EN` und `DE` in `i18n.py`; Dokumente gibt es auf Englisch **und** Deutsch, gegenseitig verlinkt (ein Test prüft es).
- **Design:** lies zuerst das [Design-Handbuch](docs/design.de.md). Farben nur als Tokens, eine Definition je Baustein, keine Inline-Skripte.
- **Einheiten:** Werte werden in Basiseinheiten gespeichert (km, Liter, bar, °C) und nur in den gewählten Einheiten angezeigt; nie „km“, „€“ oder „L“ fest einbauen.
- **Version:** Beitragende ändern die Version und die Änderungsprotokolle **nicht**. Die Maintainer bündeln angenommene Änderungen zu einer Version (zum Beispiel `0.5.1 Beta`) und schreiben sie mit `tools/release.py` - siehe [Pflege](docs/maintaining.de.md).
- Schreibe einen Test für das, was du änderst.
- **Mit einem KI-Assistenten (zum Beispiel Claude Code) erstellt?** Willkommen - kreuze das Kästchen im Pull Request an, prüfe jede Zeile selbst und halte Privates aus Prompts und aus dem Code heraus. Du bist verantwortlich für das, was du einreichst.

## Lizenz

Mit deinem Beitrag stimmst du zu, dass deine Arbeit unter der [GNU General Public License v3.0](LICENSE) veröffentlicht wird.
