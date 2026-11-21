# Beispiele

[🇬🇧 English](README.md) · 🇩🇪 Deutsch

Kleine, vollständige Ausgangspunkte. Kopiere eines, ändere die Namen und baue dein eigenes. Wie die Teile zusammenhängen, zeigt [architecture.de.md](../architecture.de.md).

| Beispiel | Was es zeigt | Lesen |
|---|---|---|
| [push_data.py](push_data.py) | Ein **Plugin-Skript**: liest Werte (ersetze `read_car()`) und schickt sie mit einer HTTP-Anfrage. Nur Standardbibliothek. | [Plugin-API](../api.de.md) |
| [echo-service/](echo-service) | Ein **Plugin mit Dienst**: ein eigenes kleines Programm, das auf einer Adresse antwortet (`/echo/ping`), mit einer Einstellung. | [Plugins](../plugins.de.md#plugins-mit-dienst) |
| [example-stations/](example-stations) | Eine **Integration ohne Code**: eine Seite mit typisierten Feldern, die Car Assistant zeichnet und je Auto speichert. | [Integrationen](../integrations.de.md) |
| [make_vehicle_file.py](make_vehicle_file.py) | Schreibt eine **Fahrzeugdatei**, um ein Auto aus einem anderen Programm zu übernehmen. | [Fahrzeugdatei](../vehicle-file.de.md) |

Prüfe ein Paket, bevor du es teilst: `python tools/check_plugin.py <Ordner>`. Alles hier nutzt neutrale Werte (`car.example.com`, `Example`); ein Test sorgt dafür, dass die App diese Beispiele lesen kann.
