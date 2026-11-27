# Sicherheitsrichtlinie

[🇬🇧 English](https://github.com/Matze89x/ha-car-assistant/blob/main/SECURITY.md) · 🇩🇪 Deutsch

Car Assistant entsteht in der Freizeit einer einzelnen Person. Sicherheitsmeldungen werden ernst genommen und zuerst gelesen.

## Eine Schwachstelle melden

**Bitte eröffne kein öffentliches Issue für ein Sicherheitsproblem.** Nutze stattdessen die private Meldung von GitHub: Öffne den Reiter **Security** dieses Repositorys und wähle **Report a vulnerability**. Beschreibe, was du gefunden hast, wie man es nachstellt und welche Version du benutzt (*Einstellungen → Über*). Du bekommst so schnell wie möglich eine Antwort, meist innerhalb weniger Tage.

## Unterstützte Versionen

Nur die neueste Version bekommt Korrekturen. Bitte aktualisiere zuerst und prüfe, ob das Problem noch da ist.

## Was dazugehört

- Hineinkommen ohne Anmeldung oder Zugriff auf Daten eines anderen Autos oder Benutzers.
- Ein normaler Benutzer tut, was nur ein Administrator darf (Sicherung, Wiederherstellung, Systemeinstellungen, Quellen, Tokens).
- Die Plugin-API nimmt ein falsches Token an, oder ein Token erreicht ein Auto, zu dem es nicht gehört.
- Ein Paket, ein Dienst oder eine hochgeladene Datei bricht aus seinen Grenzen aus (liest die Datenbank oder das Home-Assistant-Token, schreibt außerhalb seines Ordners).
- Cross-Site-Scripting oder Cross-Site-Request-Forgery in den Seiten der App.

## Wie Car Assistant dich schützt (kurz)

- In Home Assistant braucht das Panel in der Seitenleiste keine Anmeldung. Der Direktzugriff braucht einen Port **und** einen Benutzer (Passwort, optional ein Passkey); nach 5 falschen Versuchen wird eine Adresse 15 Minuten gesperrt. Von außen immer HTTPS benutzen.
- Die Plugin-API akzeptiert ein Token je Auto und sonst nichts.
- Pakete werden gelesen, nicht ausgeführt - mit **einer Ausnahme: ein Dienst**, der fremder Code ist. Er läuft nur aus einer von dir hinzugefügten Quelle, nur nachdem du freigegeben hast, was er tut, als eigenes Programm ohne Rechte und mit Grenzen, und sieht nie die Datenbank oder das Home-Assistant-Token. Gib nur Dienste aus Quellen frei, denen du vertraust.
- Nichts wird von allein aus dem Internet geholt (Karte, Spritpreise und Quellen sind freiwillig).

Mehr: [Plugins und Dienste](../plugins.de.md) · [Sicherung](../backup.de.md).
