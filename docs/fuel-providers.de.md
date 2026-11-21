# Spritpreis-Anbieter

[🇬🇧 English](fuel-providers.md) · 🇩🇪 Deutsch

Spritpreise sind von Land zu Land verschieden, deshalb hat Car Assistant keinen eingebauten Preisdienst für „die Welt“. Stattdessen gibt es eine **offene Schnittstelle**: Ein Anbieter ist **eine JSON-Datei**, die der App sagt, wo ein offener HTTP/JSON-Dienst liegt, wie man ihn nach den Tankstellen um einen Punkt fragt und welches Feld der Antwort was ist. Eine Datei wird nur gelesen, nie ausgeführt; es werden nur `https`-Adressen benutzt; es wird nichts angefragt, solange niemand nach Tankstellen sucht.

Eingebaut: **Tankerkönig** (Deutschland, braucht deinen eigenen kostenlosen Key unter *System*), **OpenStreetMap** (Tankstellen überall, keine Preise) und die mitgelieferten Dateien in `carassistant/app/carassistant/fuelproviders/` (heute Frankreich). **Eigene Dateien** kommen in den Ordner `fuelproviders/` im Datenordner der App (`/data/fuelproviders/` in Home Assistant); sie gehen einer mitgelieferten Datei mit gleicher `id` vor. Zuerst wird der Anbieter für das Land deines Home Assistant gewählt.

## Die Datei

Das Beispiel steht in der [englischen Fassung](fuel-providers.md). Die Felder:

- `id` (a-z, 0-9, `-`, `_`; nicht `osm` oder `tankerkoenig`), `name`, `countries` (ISO-Kürzel: dort wird der Anbieter zuerst angeboten), `license` und `attribution` (**steht neben den Preisen – halte ein, was der Dateninhaber verlangt**).
- `url` (https), `method` (`GET` oder `POST`), `params`, `headers`: Werte dürfen `{lat}`, `{lon}`, `{radius_km}`, `{radius_m}` und `{key}` enthalten.
- `key`: `{"param": "apikey", "url": "https://wo-man-einen-bekommt"}` oder `{"header": "X-Key", ...}`. Die Person trägt einen eigenen Key unter *System* ein (es gibt keinen eingebauten); ohne ihn wird nichts angefragt.
- `items`: wo die Liste der Tankstellen in der Antwort steht (Punkt-Pfad, leer = die Antwort selbst). `fields`: Punkt-Pfade (`geom.lat`) oder Vorlagen mit Feldern in Klammern (`{street} {number}`) für `lat`, `lon`, `name`, `brand`, `address`, `open` (true/false).
- `prices`: welches Feld den Preis von `e5`, `e10`, `diesel` enthält. `price_scale` multipliziert Preise (Standard 1). `max_radius_km` (1–100).

Die Antwort eines Anbieters wird fünf Minuten je Gebiet behalten. Bitte beachte die Bedingungen des Dienstes, auf den du eine Datei richtest.

Pakete aus Quellen (wie Plugins) für Anbieter können folgen; das Dateiformat bleibt gleich.
