# Eine Sprache hinzufügen

[🇬🇧 English](translating.md) · 🇩🇪 Deutsch

Eine Sprache ist **eine Datei**: `carassistant/app/carassistant/locales/<code>.json` (zum Beispiel `fr.json`, `es.json`, `pt-br.json`). Sonst muss nichts geändert werden – die Sprache erscheint von selbst in der Frage beim ersten Start und unter *Einstellungen → Sprache*.

```json
{
  "_name": "Français",
  "_date": "%d/%m/%Y",
  "_dir": "ltr",
  "nav.home": "Accueil",
  "nav.more": "Plus"
}
```

- `_name` – der Name der Sprache in ihr selbst (erscheint in den Listen). `_date` – Datumsformat ([strftime](https://strftime.org)). `_dir` – `ltr` (Standard) oder `rtl` für Schriften von rechts nach links.
- Alle anderen Schlüssel sind die Texte. Schlüssel und englische Texte findest du in `EN` in `carassistant/app/carassistant/i18n.py`; Platzhalter wie `{n}` oder `{name}` bleiben genau so stehen.
- **Du musst nicht alles übersetzen.** Fehlt ein Schlüssel, gilt Englisch; eine teilweise Übersetzung funktioniert also schon.
- Der Code besteht aus 2–3 Kleinbuchstaben, optional mit Region (`pt-br`).

Prüfe deine Datei mit `pytest tests/test_i18n.py`: Es wird geprüft, dass jeder Schlüssel auch auf Englisch existiert und die Platzhalter übereinstimmen.
