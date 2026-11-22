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
3. **Verwalten** (je Fahrzeug) – Einstellungen, *Nach Updates suchen* (liest die Quellen und markiert Kacheln mit neuerer Version) und *Update* auf so einer Kachel, *Start / Stopp* (nur Plugins; Integrationen haben kein An/Aus), *Deinstallieren*; die Listen lassen sich sortieren.

Antwortet GitHub mit „403“, weil sein Stundenlimit für anonyme Anfragen (60 pro Adresse) verbraucht ist, sagt die App das – am Zugangsschlüssel liegt es nicht; später noch einmal versuchen.

Eine Quelle lässt sich nur löschen, wenn **kein daraus installiertes Paket** mehr vorhanden ist.

## Werkseinstellung

Nach einem frischen Start ist die erste Quelle das Paket-Repository des Projekts, [ha-car-assistant-sources](https://github.com/Matze89x/ha-car-assistant-sources) – dort stehen auch die Anleitungen für eigene Pakete. Sie lässt sich löschen (wenn nichts daraus installiert ist) und mit *Standardquelle wiederherstellen* zurückholen.
