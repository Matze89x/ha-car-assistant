# Adding a language

🇬🇧 English · [🇩🇪 Deutsch](translating.de.md)

A language is **one file**: `carassistant/app/carassistant/locales/<code>.json` (for example `fr.json`, `es.json`, `pt-br.json`). Nothing else has to change – the language appears in the first-start question and under *Settings → Language* by itself.

```json
{
  "_name": "Français",
  "_date": "%d/%m/%Y",
  "_dir": "ltr",
  "nav.home": "Accueil",
  "nav.more": "Plus"
}
```

- `_name` – the language's name in itself (shown in the lists). `_date` – date format ([strftime](https://strftime.org)). `_dir` – `ltr` (default) or `rtl` for right-to-left scripts.
- All other keys are the texts. Take the keys and the English texts from `EN` in `carassistant/app/carassistant/i18n.py`; keep placeholders such as `{n}` or `{name}` exactly as they are.
- **You do not have to translate everything.** A missing key falls back to English, so a partial translation already works.
- The code is lower-case, 2–3 letters, optionally with a region (`pt-br`).

Check your file with `pytest tests/test_i18n.py`: it verifies that every key exists in English and that the placeholders match.
