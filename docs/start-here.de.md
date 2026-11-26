# Hier anfangen - deine erste Integration oder dein erstes Plugin

[🇬🇧 English](start-here.md) · 🇩🇪 Deutsch

Du musst nicht wissen, wie Car Assistant innen funktioniert. Diese Seite führt dich in etwa zehn Minuten von Null zu einem Paket, das in einem **echten Car Assistant auf deinem Computer** läuft - und danach zu einer *Quelle*, die andere hinzufügen können. Die Einzelheiten stehen auf den anderen Seiten; diese hier sagt dir, welche du wann liest.

## 1. Was willst du bauen?

| Ich will ... | Dann baue ich eine/ein ... | Code? | Weiter bei |
|---|---|---|---|
| eigene Listen, Notizen, Erinnerungen oder einen Plan in Car Assistant (Tankstellen, Teile, eine Aufgabenliste fürs Auto) | **Integration** | keinen - nur eine Beschreibung (`plugin.json`) | [Abschnitt 3](#3-deine-erste-integration-ohne-code) |
| Werte von einem Webdienst, der **JSON** antwortet (ein Token oder eine Anmeldung beim Anbieter) | **Plugin mit Connector** | keinen - eine Beschreibung von Adressen und Pfaden | [Connectors](plugins.de.md#verbindungen-ohne-code-connector) |
| Informationen von einem Webdienst oder Cloud-Konto, bei dem ich mich anmelde, einer App, einem Gerät - wenn das mehr braucht | **Plugin mit Dienst** | ein kleines Python-Programm | [Abschnitt 4](#4-dein-erstes-plugin-mit-dienst) |
| Werte von meinem eigenen Skript oder einer Box im Auto ab und zu schicken | **Plugin ohne Dienst** | dein Skript: eine HTTP-Anfrage | [Abschnitt 5](#5-ein-plugin-ohne-dienst-dein-eigenes-skript) |
| ein ganzes Werkzeug mit eigenen Seiten in der App | Integration mit Dienst | ein kleines Programm | [Plugin-Anleitung, Abschnitt 5](plugin-guide.de.md#5-ein-eigener-dienst) |

Unsicher? Fang mit der ersten Zeile an: Eine Integration kann nichts kaputt machen, weil nichts davon läuft.

## 2. Wie alles zusammenpasst

```
du und deine Familie  -->  Car Assistant     die App: Seiten, Daten, Backups, Benachrichtigungen
                                ^
                                |  eine Tür: die Plugin-API (ein Token, docs/api.de.md)
                                |
                           ein Plugin     -->  das AUSSEN: ein Auto, ein Cloud-Konto, ein Webdienst, ein Gerät
```

- Die App spricht nie selbst mit einem Auto oder Webdienst. Das macht ein **Plugin** - und reicht der App über die **Plugin-API** weiter, was sie braucht, sonst nichts.
- Eine **Integration** ist nur die Beschreibung von Seiten, Erinnerungen und Plänen. Sie hat kein Token und ruft keine API auf; Car Assistant zeichnet sie und speichert die Einträge je Auto.
- Eine **Quelle** ist ein Repository (GitHub, öffentlich oder privat) mit den Ordnern `integrations/` und `plugins/`. Die Leute fügen die Quelle in der App hinzu und installieren daraus - siehe [sources.de.md](sources.de.md).
- Ein Paket mit **Dienst** ist ein Programm, das im Add-on läuft. Es ist fremder Code, deshalb muss ein Administrator es erst lesen und freigeben ([plugins.de.md](plugins.de.md#plugins-mit-dienst)).

## Was du brauchst

- Eine Kopie dieses Repositorys, Python 3.12 und die Voraussetzungen der App: `pip install -r carassistant/requirements.txt`.
- Sonst nichts. Du brauchst kein Home Assistant, um ein Paket auszuprobieren: Das Werkzeug unten startet einen echten Car Assistant mit vorläufigen Daten und löscht sie, wenn du es beendest.

Alle Befehle laufen im Ordner des Repositorys. `my-source` ist ein beliebiger Ordner: Er wird deine Quelle.

## 3. Deine erste Integration (ohne Code)

```
python tools/new_plugin.py my-notes --kind integration --out my-source
python tools/plugin_dev.py my-source/integrations/my-notes
```

Der erste Befehl legt den Ordner `my-source/integrations/my-notes/` an, mit einer `plugin.json` (eine Seite „Notes“ mit Titel, Notiz und einem Schalter *Done*), und schreibt die Zeile dafür in `my-source/integrations/index.json`. Der zweite startet Car Assistant mit der schon installierten Integration und druckt die Adressen: Öffne **ihre Seite**. Lege eine Notiz an - sie wird für das Auto „Dev car“ gespeichert.

Jetzt ändere etwas: `plugin.json` öffnen, ein Feld umbenennen oder eins hinzufügen (die Feldtypen stehen in [integrations.de.md](integrations.de.md)), speichern. Das Werkzeug merkt es, startet neu, und du lädst die Seite neu. `Strg-C` beendet es.

## 4. Dein erstes Plugin mit Dienst

```
python tools/new_plugin.py my-plugin --out my-source
python tools/plugin_dev.py my-source/plugins/my-plugin --set user=max --set password=secret
```

Das legt `my-source/plugins/my-plugin/` an, mit einer `plugin.json`, einem Programm `service/main.py` und der Hilfsbibliothek `service/carassistant_sdk.py`. Das Werkzeug installiert es, **gibt den Dienst für dich frei** (es ist dein Computer und dein Code) und zeigt, was passiert - die Protokollzeilen des Dienstes und jeden Aufruf, den er an die Plugin-API macht:

```
  log  10:21:07 info  Service started (process 4711, port 52114, restarts so far 0)
  log  10:21:07 info  [info] sent odometer_km
  api  10:21:07 POST /data -> 200  odometer_km
```

`--set key=value` füllt eine Einstellung und schließt die Einrichtung für dich ab. Ohne das wartet das Plugin, und du gehst die Einrichtung im Browser durch wie ein Mensch: *Einrichten* auf seiner Kachel. Um alles in einer Sekunde zu sehen - für ein Skript oder einen eigenen Test - hänge `--once` an: Das Werkzeug endet, sobald das Plugin etwas geliefert hat (Exit-Code 0).

### Mach es zu deinem

Öffne `service/main.py`. Zwei Stellen sagen `TODO`: `login()` (beim Webdienst anmelden) und `fetch()` (ihn nach dem Auto fragen und zurückgeben, was du weißt). Alles andere ist schon da:

| Du schreibst | Was passiert |
|---|---|
| `ca.settings()` | was die Person auf der Einstellungsseite deines Plugins eingetragen hat |
| `ca.Http()` | ein Client für Webdienste: JSON hin und zurück, Cookies für eine Sitzung, ein paar Wiederholungen; wirft `ca.HttpError` bei einer Fehlerantwort |
| `ca.State()` | eine kleine Datei im Datenordner für das, was der Dienst sich merken muss (eine Sitzung, ein erhaltenes Token) |
| `api.send(odometer_km=1234, ...)` | gibt Car Assistant Werte über die Plugin-API - die Namen stehen in [api.de.md](api.de.md) |
| `ca.log("...")` | eine Zeile für die Protokollseite deines Plugins (nie ein Passwort oder Token) |
| `@ca.route("POST", "/my-plugin/check")` | eine Route deines Dienstes - diese hier ist der Schritt *Anmeldung prüfen* des Einrichtungsablaufs |
| `return ca.passed("Angemeldet.")`, `ca.failed("Kennwort falsch.")`, `ca.ask("code", message="Ein Code wurde per SMS geschickt.")` | die Antworten einer `check`-Route; `ask` bringt den Schritt mit einer einmaligen Eingabe für einen Code zurück ([plugins.de.md](plugins.de.md#der-einrichten-ablauf-setupflow)) |
| `api.bearer()` | das Zugriffstoken der Anmeldung der Person bei einem Anbieter (OAuth 2.0), immer frisch - siehe unten |
| `ca.run(poll, every=60)` | ruft `poll()` alle 60 Sekunden auf; ein fehlgeschlagener Aufruf wird protokolliert und später wiederholt, er beendet den Dienst nie |

Die Einstellungen, die die Person sieht (ein Benutzername, ein Passwort, ein Schalter ...), beschreibst du in `plugin.json` unter `settings`; die Schritte der Einrichtung unter `setup.flow` (beides steht in [plugins.de.md](plugins.de.md)). `service.connects` nennt die Webadressen, mit denen dein Programm spricht: Sie stehen auf der Freigabeseite, damit die Leute wissen, was sie freigeben.

### Anmelden bei einem Anbieter (OAuth 2.0)

Für einen Webdienst, der die Leute auf einer eigenen Seite anmeldet (die meisten Auto-Clouds tun das), leg das Plugin mit `--login oauth` an:

```
python tools/new_plugin.py my-plugin --login oauth --out my-source
```

Die Einrichtung hat dann einen Schritt vom Typ `oauth`: Die Person registriert beim Anbieter eine App, trägt deren Client-ID ein und meldet sich an; **Car Assistant verwahrt die Tokens und erneuert sie**, dein Dienst ruft nur `api.bearer()` für das aktuelle auf. Solange sich niemand angemeldet hat, wartet das Plugin (`waiting for the login` im Protokoll); eine abgelaufene Anmeldung zeigt *Neu anmelden* auf der Kachel. Die Einzelheiten - die zwei Wege, wie der Browser zurückkommt, was wie sicher verwahrt wird - stehen in [plugins.de.md](plugins.de.md#der-einrichten-ablauf-setupflow). Eine Anmeldung mit einem Code aus einer SMS oder einer Authenticator-App braucht kein OAuth: Ein `check`-Schritt mit einer einmaligen `ask`-Eingabe macht das.

Speichere eine Datei, und das Werkzeug packt und startet das Plugin neu. Die Protokollseite des Plugins in der App (*Logs* auf seiner Kachel) zeigt dieselben Zeilen bei eingeschaltetem Debug-Schalter - das Werkzeug schaltet ihn für dich ein.

## 5. Ein Plugin ohne Dienst: dein eigenes Skript

Wenn eine Box im Auto oder ein Skript von dir eine HTTP-Anfrage schicken kann, brauchst du kein Programm in Car Assistant:

```
python tools/new_plugin.py my-device --no-service --out my-source
python tools/plugin_dev.py my-source/plugins/my-device
```

Das Werkzeug druckt die Adresse der Plugin-API, die Nummer des Autos und ein **Token** sowie einen `curl`-Befehl zum Kopieren:

```
  Plugin API       http://127.0.0.1:52114/api/v1/vehicles/1/...   token: ca_...
                   try: curl -H 'Authorization: Bearer ca_...' -H 'Content-Type: application/json' \
                             -d '{"odometer_km": 1000}' http://127.0.0.1:52114/api/v1/vehicles/1/data
```

Führ ihn aus: Der Aufruf erscheint im Werkzeug als `api ... POST /data -> 200`. Ein Skript von dir macht dasselbe - siehe `docs/examples/push_data.py` und die Liste der Felder in [api.de.md](api.de.md). In der echten App findet ein Plugin ohne Dienst sein Token auf seiner Einstellungsseite.

## 6. Prüfen und veröffentlichen

1. `python tools/check_plugin.py my-source/plugins/my-plugin` - die Prüfung, die die App beim Lesen eines Pakets macht. Sie nennt Tippfehler bei Schlüsseln, falsche Icons, fehlende Dateien. Solange das Zip fehlt, sagt sie dir das.
2. Ein Plugin **mit Dienst** wird als `package.zip` ausgeliefert: `python tools/build_plugin_package.py my-source my-plugin` baut es (jedes Mal gleich) und schreibt seine Prüfsumme in die Liste der Quelle.
3. `python tools/check_source.py my-source` - die ganze Quelle, so wie die App sie liest. Fehler enden mit Exit-Code 1; Hinweise nicht.
4. Leg `my-source` in ein GitHub-Repository (öffentlich, oder privat mit Zugangsschlüssel). In der App: *Plugins* (oder *Integrationen*) *→ Quellen*: die Adresse des Repositorys eintragen. Dann *Hinzufügen → Liste aktualisieren*, dein Paket antippen, installieren. Ein Dienst wartet auf die Freigabe: *Verwaltung → Prüfen und freigeben*.
5. Eine neue Version: `version` in `plugin.json` und in der Liste erhöhen, das Zip neu bauen, pushen. Die Leute drücken *Nach Updates suchen*.

Alles steht in [sources.de.md](sources.de.md); ein Repository kann sich auch jede Woche selbst prüfen ([docs/examples/source-ci.yml](examples/source-ci.yml)).

## Wenn etwas nicht funktioniert

| Du siehst | Probier |
|---|---|
| `the package is not accepted: ...` | das Werkzeug liest das Paket wie die App: Der Text nennt, was nicht stimmt. `tools/check_plugin.py` sagt mehr. |
| der Dienst startet, aber nichts kommt an | schau in die `log`-Zeilen: Eine Zeile `poll failed (1): ...` nennt den Grund. Ein `404` vom Webdienst heißt falsche Adresse, `401` eine falsche Anmeldung. |
| `Login failed: ...` beim Schritt *Anmeldung prüfen* | die Antwort deiner `check`-Route: `{"ok": false, "message": "..."}` ist, was die Person liest. Schreib nie ein Passwort hinein. |
| das Protokoll sagt `unreachable` | der Dienst erreicht die Plugin-API nicht: Die App läuft nicht - etwa wenn du `main.py` von Hand startest. Starte es über das Werkzeug oder die App. |
| die App sagt, der Dienst wartet auf Freigabe | in der echten App gibt ein Administrator ihn unter *Verwaltung → Prüfen und freigeben* frei. Das Werkzeug macht es für dich. |
| ein Plugin erscheint nach dem Pushen nicht in der App | *Liste aktualisieren* unter *Hinzufügen*; die Liste der Quelle (`index.json`) muss es nennen, und sein Ordner muss genauso heißen wie seine `id`. |

## Begriffe

| Begriff | Bedeutung |
|---|---|
| **Add-on** | Car Assistant selbst, in Home Assistant (oder, zum Ausprobieren, vom Werkzeug auf deinem Computer gestartet) |
| **Integration** | ein Extra, in `plugin.json` beschrieben: Seiten, Erinnerungen, Pläne. Kein Code, kein Token |
| **Plugin** | eine Verbindung nach außen. Es bekommt ein Token und spricht über die Plugin-API mit der App |
| **Dienst** | das Programm eines Plugins, im Add-on laufend. Braucht die Freigabe eines Administrators |
| **Plugin-API** | die eine Tür von einem Plugin zur App: `POST /api/v1/vehicles/<id>/data` und ein paar mehr ([api.de.md](api.de.md)) |
| **Paket** | der Ordner einer Integration oder eines Plugins: `plugin.json`, und bei einem Dienst seine Dateien und das `package.zip` |
| **Quelle** | ein Repository mit `integrations/` und `plugins/` und je einer Liste (`index.json`) |
| **Token** | der Schlüssel eines Plugins für die Plugin-API. Eins je Plugin und Auto |
| **Einrichtungsablauf** | die Schritte, die eine Person beim ersten Mal durchgeht (Text, Anmeldung, Prüfung, Token, Dateien) |
| **Kachel** | die Karte eines Pakets in der Liste, mit ihren Knöpfen |

## Wie es weitergeht

- [plugin-guide.de.md](plugin-guide.de.md) - der ganze Weg auf einer Seite, zum Nachschlagen.
- [plugins.de.md](plugins.de.md) - jeder Schlüssel der `plugin.json`: Einstellungen, Einrichtungsablauf, Dienste, Dateien, Kacheln.
- [integrations.de.md](integrations.de.md) - Seiten, Erinnerungen, Pläne.
- [api.de.md](api.de.md) - alle Felder und Wege, Werte zu senden.
- [examples/](examples/README.de.md) - kleine, vollständige Ausgangspunkte.
