# Architektur: wie alles zusammenhängt

[🇬🇧 English](architecture.md) · 🇩🇪 Deutsch

Drei Bilder, vom Großen zum Kleinen. GitHub zeichnet sie direkt aus dem Text (Mermaid); mit dem Pfeil-Symbol oben rechts im Bild kannst du zoomen.

## 1. Das ganze System

Car Assistant ist **eine** App in Home Assistant. Alles, was nach außen spricht (ein Auto, eine Cloud, ein Webdienst), ist ein **Plugin** und redet nur über die Plugin-API mit der App.

```mermaid
flowchart TD
  you["Du: Browser oder Handy"]
  ha["Home Assistant: Panel in der Seitenleiste (Ingress)"]
  direct["Direktzugriff: Port + Benutzer, HTTPS über Proxy"]
  app["Car Assistant (FastAPI + SQLite)"]
  pages["Seiten und Listen je Auto"]
  api["Plugin-API /api/v1 (Token je Auto)"]
  worker["Hintergrund: Erinnerungen, Benachrichtigungen, Aufräumen"]
  mqtt["MQTT-Broker -> Sensoren und Standort in Home Assistant"]
  notify["Home-Assistant-Notify-Dienst und Web-Push"]
  plugin["Plugin: verbindet etwas von außen"]
  outside["Auto, Cloud, Webdienst, Gerät"]
  you --> ha --> app
  you --> direct --> app
  app --> pages
  app --> api
  app --> worker
  worker --> notify
  app --> mqtt
  plugin -->|token| api
  plugin --> outside
```

## 2. Ein Plugin: von draußen bis auf die Seite

Ein Plugin kennt nur die Plugin-API. Es liest draußen, schickt Werte an die App, und die App zeigt nur, was ein Plugin geliefert hat - nichts wird erfunden.

```mermaid
flowchart LR
  car["Auto / Cloud / Webdienst"]
  plugin["Plugin (eigener Code, eigener Ort)"]
  api["POST /api/v1/vehicles/ID/data"]
  db[("Datenbank: aktuelle Werte, Verlauf, Protokoll")]
  home["Home: Kacheln, Standort, Warnpunkte"]
  more["Sicherheit, Fahrten, Fahrzeugdaten"]
  rem["Erinnerungen und Benachrichtigungen"]
  mqtt["MQTT-Sensoren in Home Assistant"]
  car --> plugin
  plugin -->|"Bearer-Token, nur dieses Auto"| api
  api --> db
  db --> home
  db --> more
  db --> rem
  db --> mqtt
```

Die Schnittstelle ist in der [Plugin-API](api.de.md) beschrieben, der Aufbau eines Plugins in der [Plugin-Anleitung](plugin-guide.de.md) und in [Plugins](plugins.de.md).

## 3. Quellen, Pakete und Dienste (Plugins und Integrationen)

Plugins und Integrationen sind **Pakete**: ein lesbarer Ordner mit `plugin.json`. Sie kommen aus *Quellen*, die du selbst hinzufügst. Nur ein Paket mit einem **Dienst** führt Code aus, und erst nach deiner Freigabe.

```mermaid
flowchart TD
  src["Quelle: GitHub-Repository oder https-Adresse mit index.json"]
  pkg["Paket: plugin.json, Dateien, package.zip (sha256 geprüft)"]
  user["Du: hinzufügen, installieren, freigeben"]
  plug["Plugin: Token, Plugin-API, nur dieses Auto"]
  integ["Integration: Seiten, Erinnerungen, Kacheln, kein Token"]
  svc["Dienst (optional, fremder Code): eigener Prozess, eigener Benutzer, Grenzen"]
  proxy["Proxy der App: nur angemeldete Personen, Routen aus dem Paket"]
  page["Eigene Seite des Dienstes in Weiteres"]
  src --> pkg
  user --> pkg
  pkg --> plug
  pkg --> integ
  pkg -.->|"nur nach Freigabe"| svc
  svc --> proxy --> page
  plug --> svc
  integ --> svc
```

Der Dienst bekommt weder das Home-Assistant-Token noch die Datenbank; eine Integration bekommt kein Token und ruft die Plugin-API nie auf. Die Regeln stehen in [Quellen](sources.de.md), [Integrationen](integrations.de.md) und [Plugins](plugins.de.md#plugins-mit-dienst).

## Dein eigenes bauen

1. Lies die [Plugin-Anleitung](plugin-guide.de.md) und die [Plugin-API](api.de.md).
2. Schau dir die Beispiele in [docs/examples](examples/README.md) an: ein Dienst mit Seite, ein Skript, das Werte schickt, und ein Skript, das eine Fahrzeugdatei schreibt.
3. Lege dein Paket in ein Repository mit `index.json` ([Quellen](sources.de.md)), füge es als Quelle hinzu und installiere es.
