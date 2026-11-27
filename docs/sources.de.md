# Quellen und Pakete

[🇬🇧 English](sources.md) · 🇩🇪 Deutsch

Eine **Quelle** ist ein Ort, aus dem Pakete (Integrationen und Plugins) angeboten werden: ein GitHub-Repository oder eine beliebige https-Adresse, die dieselben Dateien liefert. Die Liste der Quellen ist **eine Liste für den ganzen Server** (*Integrationen / Plugins → Quellen*). *Hinzufügen* und *Verwalten* gelten je Fahrzeug.

Von einer Quelle wird nichts von selbst abgerufen – nur wenn du sie hinzufügst, *Aktualisieren* tippst, ein Paket öffnest, installierst oder aktualisierst. Gelesen werden nur Beschreibungen, **aus einem Paket wird nichts ausgeführt** - außer dem Dienst eines Plugins, das du selbst freigegeben hast ([plugins.de.md](plugins.de.md#plugins-mit-dienst)). Ein solches Paket ist ein lesbarer Ordner plus `package.zip`, und der Index nennt seine `sha256`.

## Ordnerregel

```
index.json                  (optional, reserviert)
integrations/
  index.json                die Liste aller Integrationen dieser Quelle
  <id>/plugin.json          ein Ordner je Integration – der Ordnername ist die id
plugins/
  index.json                die Liste aller Plugins dieser Quelle
  <id>/plugin.json          ein Ordner je Plugin
```

Der erste Ordner trennt Integrationen und Plugins. Eine Quelle kann beliebig viele Pakete anbieten (ein Index wird bis 200 Einträge gelesen).

### `index.json` (eine je Art)

```json
{
  "packages": [
    { "id": "example-plugin", "name": "Example plugin", "description": "Kurzer Text", "version": "1" }
  ]
}
```

- `id` – Kleinbuchstaben, Ziffern, `-`, `_` (2–41 Zeichen); **muss dem Ordnernamen entsprechen**.
- `name`, `description`, `version` – erscheinen unter *Hinzufügen*; eine höhere `version` als die installierte bietet ein **Update** an. `icon` (optional) – ein Name aus dem Icon-Satz ([icons.de.md](icons.de.md)): das Icon der Kachel, noch vor der Installation. Nimm dasselbe `icon` in der `plugin.json` des Pakets.
- Versionen werden als Zahlen verglichen (`1.10` ist neuer als `1.9`).

### `plugin.json`

Die Beschreibung eines Pakets, siehe [plugins.de.md](plugins.de.md) (id, name, version, description, author, homepage, settings). Der Ordner bestimmt die Art (Integration oder Plugin); `id` muss dem Ordnernamen entsprechen.

## Fehlersuche

- Das Paket erscheint nicht: *Liste aktualisieren* unter *Hinzufügen* drücken (von selbst wird nichts gelesen, außer du schaltest die tägliche Prüfung unter *Einstellungen → System → Paket-Updates* ein). Eine Quelle ist ein Repository für Integrationen und Plugins zugleich; es darf `integrations/`, `plugins/` oder beides enthalten – ein fehlender Ordner ist in Ordnung. Die `index.json` der Art muss das Paket auflisten.
- Jedes Paket liegt in einem Ordner mit genau seiner `id` (`plugins/<id>/plugin.json`). Eine id nutzt nur Kleinbuchstaben, Ziffern, `-` und `_` (2-41 Zeichen); alles andere wird ausgelassen, der Grund steht an der Quelle.
- Ein privates Repository braucht einen Token (Lesezugriff auf Inhalte).
- Der Index darf `{"packages": [...]}` oder eine nackte Liste sein. Eine Wurzel-`index.json` mit `{"name": "..."}` gibt der Quelle ihren Namen.

## Ablauf

1. **Quellen** – Adresse eines Repositorys eintragen; ein privates Repository braucht einen *Zugangsschlüssel* (ein Token mit Leserecht), der auf dem Server bleibt.
2. **Hinzufügen** (je Fahrzeug) – die Pakete aller Quellen, eines antippen zeigt die Beschreibung, dann *Installieren*.
3. **Verwalten** (je Fahrzeug) – Einstellungen, *Nach Updates suchen* (liest die Quellen und markiert Kacheln mit neuerer Version) und *Update* auf so einer Kachel, *Start / Stopp* (nur Plugins; Integrationen haben kein An/Aus), *Deinstallieren*.

Ein Paket, das **ohne Quelle** installiert wurde (aus einer Datei), zeigt auf seiner Karte *ohne Quelle* und steht unter *Hinzufügen* als *Installiert · ohne Quelle* – es wird nicht ein zweites Mal angeboten. Bietet eine Quelle eine **neuere** Version davon an, bekommt es ein *Update* wie jedes andere und gehört danach zu dieser Quelle (Einstellungen, Token und Zustand bleiben). Bietet eine Quelle **genau dieselbe** Version an, zeigt die Karte einen hellen Knopf *Mit Quelle verknüpfen*: er verknüpft das Paket nur mit dieser Quelle (seine nächsten Updates kommen von dort) - sonst ändert sich nichts, es wird nichts geladen. Eine Quelle mit älterer Version ändert nichts.

**GitHub und sein Limit.** Eine öffentliche GitHub-Quelle wird von `raw.githubusercontent.com` gelesen, das kein solches Kontingent hat. Die **API** von GitHub erlaubt nur 60 anonyme Anfragen pro Stunde und Internetadresse – für alle hinter dieser Adresse – und wird für eine Quelle mit Zugangsschlüssel benutzt (der Schlüssel hebt das Limit auf 5000) sowie von anderen Add-ons und Werkzeugen in deinem Netz. Car Assistant behält jede gelesene Datei samt dem ETag, den der Server nannte: noch einmal fragen kostet nichts (der Server antwortet „nicht verändert“), eine Datei, die vor weniger als zehn Minuten gelesen wurde, wird nicht erneut erfragt, und ist das Limit erreicht oder die Verbindung weg, zeigt die Liste, was vorher bekannt war, und sagt das (*die Quelle hat nicht geantwortet ... die Liste ist so, wie sie vorher bekannt war*) – am Zugangsschlüssel liegt es nicht; später noch einmal versuchen.

Eine Quelle lässt sich nur löschen, wenn **kein daraus installiertes Paket** mehr vorhanden ist.

## Eine Quelle aktuell halten

Deine eigenen Plugins und Integrationen gehören in eine **Quelle** für sich - ein Repository mit einem Ordner je Paket - und **nicht** in einen Fork der App: Ein Fork mit deinen Paketen läuft bei jedem Release von der App weg und muss von Hand nachgezogen werden. Eine Quelle bleibt von der App unabhängig, und die App behält sie im Blick:

- `python tools/check_source.py <Ordner der Quelle>` liest jedes Paket so, wie **diese** Version der App es liest (dieselbe Prüfung wie `tools/check_plugin.py`), vergleicht die Verzeichnisse mit den Ordnern (IDs, Versionen, Prüfsummen) und schaut sich die Fahrzeugdateien an. Fehler enden mit Exit-Code 1, Hinweise (ein Tippfehler in einem Schlüssel, ein fehlendes Symbol oder eine fehlende Übersetzung) werden nur ausgegeben.
- Der wiederverwendbare Workflow `.github/workflows/check-source.yml` im Repository der App führt sie auf einer Quelle aus. Kopiere [`docs/examples/source-ci.yml`](https://github.com/Matze89x/ha-car-assistant/blob/main/docs/examples/source-ci.yml) nach `.github/workflows/check.yml` deiner Quelle: Bei jeder Änderung **und jeden Montag** wird die ganze Quelle gegen die neueste App geprüft, du hörst also von einem Paket, das nicht mehr passt, ohne nachsehen zu müssen. Die Prüfung liegt in der App, ist also immer so neu wie die App; eine private Quelle kann sie ebenfalls nutzen. Um gegen eine feste Version zu prüfen, füge `with: {app-ref: v0.5.24}` hinzu.
- Eine Quelle für alles, was zusammengehört (die öffentliche für Pakete, die jeder nutzen darf, eine **private** für Persönliches und Autospezifisches - nie öffentlich), ein Ordner je Paket. Ein Paket, das zu einem eigenen Projekt wächst (eigener Verlauf, eigene Releases und Hilfen), darf in ein eigenes Repository ziehen; die Quelle führt es dann nur auf.

## Werkseinstellung

Nach einem frischen Start ist die erste Quelle das Paket-Repository des Projekts, [ha-car-assistant-sources](https://github.com/Matze89x/ha-car-assistant-sources) – dort stehen auch die Anleitungen für eigene Pakete. Sie lässt sich löschen (wenn nichts daraus installiert ist) und mit *Standardquelle wiederherstellen* zurückholen.

### Die Standardquelle kommt mit der App

Eine Kopie der Standardquelle – ihre Pakete und die beiden Demo-Autos – kommt **mit jeder Version der App** (`carassistant/app/carassistant/stdsource/`, gemacht von `tools/sync_stdsource.py`, in der Developer-App und im Release gleichermaßen). Bis du bei ihr *Liste aktualisieren* drückst, werden Liste und Pakete von dort gelesen: ein frischer Start und *Nur mal ansehen* brauchen keine Verbindung und kein Kontingent. *Liste aktualisieren* fragt GitHub (eine unveränderte Datei kostet nichts); was es findet, gilt von da an. Eine neuere Version der App bringt eine neuere Kopie, und ihre Liste zeigt wieder diese Kopie, bis du sie aktualisierst. Scheitert die Aktualisierung (Limit, kein Netz), bleibt die Liste, wie sie war, und die Quelle sagt es.
