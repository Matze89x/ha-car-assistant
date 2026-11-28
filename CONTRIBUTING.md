# Contributing

🇬🇧 English · [🇩🇪 Deutsch](docs/community/contributing.de.md)

Thank you for wanting to help. Car Assistant is made in spare time, so small, focused changes that follow the rules below are the easiest to review.

## Ideas, bugs and questions

Be friendly: see the [code of conduct](CODE_OF_CONDUCT.md). Questions and ideas that are not bugs belong in *Discussions*.

- Open an **issue** with the template that fits. For a bug: the version (*Settings → About*), what you did, what you expected and what happened.
- A security problem is **not** an issue: see [SECURITY.md](SECURITY.md).
- Your own plugin or integration lives in your own repository and is added as a *source* - see the [plugin guide](docs/plugin-guide.md) and the [examples](docs/examples/README.md). A plugin for one specific car or device does not belong into this repository.

## Run it and test it

```
pip install -r carassistant/requirements.txt pytest ruff httpx pyyaml
CARASSISTANT_DATA=/tmp/cd CARASSISTANT_DEV=1 CARASSISTANT_PORT=8123 PYTHONPATH=carassistant/app python -m carassistant
```

Before every pull request (the CI does the same):

```
ruff check . && ruff format --check . && pytest -q
```

**Against a real Home Assistant (optional).** The tests of the Home Assistant plugin run against a made-up one (`tools/fake_ha.py`). To try the odometer and the trips with real helpers, a real state machine and the real WebSocket, set up a test Home Assistant once (needs Python 3.14 or newer; about five minutes, outside the repository):

```
python tools/real_ha.py setup      # once
python tools/real_ha.py start
pytest tests/test_real_ha.py -q    # skipped while no test Home Assistant answers
python tools/real_ha.py stop
```

## The rules

- **Nothing private** in code, docs, tests or pictures: no names, addresses, tokens, brands or car data. Use neutral values (`car.example.com`, `Example`, `AB-CD 123`).
- **Everything about a car is per car.** The app never talks to a car itself; a plugin does, through the [Plugin API](docs/api.md).
- **Text and language:** new texts go into `EN` and `DE` in `i18n.py`; documents exist in English **and** German, linked to each other (a test checks it).
- **Design:** read the [design handbook](docs/design.md) first. Colours only as tokens, one definition per component, no inline scripts.
- **Units:** values are stored in base units (km, litres, bar, °C) and only shown in the chosen units; never hard-wire "km", "€" or "L".
- **Version:** contributors do **not** change the version or the changelogs. The maintainers bundle accepted changes into a version (for example `0.5.1 Beta`) and write it with `tools/release.py` - see [Maintaining](docs/maintaining.md).
- Add a test for what you change.
- **Made with an AI assistant (for example Claude Code)?** Welcome - tick the box in the pull request, check every line yourself, and keep private data out of prompts and of the code. You are responsible for what you send in.

## License

By contributing you agree that your work is released under the [GNU General Public License v3.0](LICENSE).
