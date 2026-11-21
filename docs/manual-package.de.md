# Handbuch-Paket

[🇬🇧 English](manual-package.md) · 🇩🇪 Deutsch

Neben PDF, EPUB und Textdateien kann das Handbuch eines Autos als **Paket** importiert werden: eine Zip-Datei mit Seitenbildern, sodass die Seiten wie das gedruckte Buch aussehen. *Handbuch → Handbuch importieren* (oder *Neu importieren*) nimmt sie wie jede andere Datei.

## Einfachste Form

Ein Zip mit **nur nummerierten Seitenbildern** genügt: `001.avif`, `002.avif`, ... oben, in einem Ordner oder in `p/`. Der Titel kommt vom Dateinamen, der Seitenversatz ist 0, es gibt ein Kapitel. `meta.json` und `index.json.gz` kann man später für Kapitel, Versatz und Suche ergänzen.

## Voller Aufbau

Das Zip darf alles auf oberster Ebene oder in einem Ordner enthalten:

| Datei | Bedeutung |
|---|---|
| `meta.json` | optional (ohne: Titel vom Dateinamen, Versatz 0, ein Kapitel): `title`, `pages` (Seitenzahl), `offset` (gedruckte Seitenzahl + Versatz = Seite der Datei; Umschlag und Vorspann stehen vorn), `chapters` |
| `p/001.avif` ... | nötig (in `p/` oder, in der einfachen Form, neben den anderen Dateien): die Seitenbilder, eines je Seite (AVIF, JPEG, PNG oder WebP, je bis 8 MB; der Typ wird am Inhalt erkannt, nicht am Namen) |
| `t/003.json.gz` ... | optional, eine je Seite mit Verweisen: `{"x": [[137, 120, 300, 380, 330], ...]}` - jeder Eintrag ist `[gedruckte Seite, links, oben, rechts, unten]` eines Verweises wie „Seite 137“ auf dem Bild, die vier Werte in **Tausendsteln** der Bildbreite und -höhe (0-1000). Der Leser legt eine antippbare Fläche darüber: dezent rot immer, kräftig beim Überfahren, Antippen springt zu dieser Seite (gedruckte Seite + Versatz). Weitere Schlüssel in der Datei werden ignoriert. |
| `index.json.gz` | optional: eine gzip-komprimierte Liste `[{"p": 1, "t": "Text der Seite 1"}, ...]` - der Text jeder Seite für die Suche und die Ansicht *Text* |

`chapters` ist ein Baum: `[{"t": "Titel", "p": 10, "g": "Teil", "c": [{"t": "Abschnitt", "p": 12}]}]` - `p` ist die Seite der Datei, `g` (optional, nur oberste Ebene) der Teil, zu dem das Kapitel gehört, `c` die Abschnitte darunter. Seitenverweise im Text („Seite 137“) nennen die **gedruckte** Seite; die App addiert den `offset`, um zum richtigen Bild zu springen.

Höchstens 3000 Seiten und 400 MB (entpackt).

## Wie es gespeichert wird

Text, Kapitel und Versatz stehen in der Datenbank, die Bilder als Dateien im eigenen Datenordner des Autos. Bilder werden nur an angemeldete Personen ausgeliefert. Beide Sicherungen nehmen sie mit: die [Fahrzeug-Sicherung](backup.de.md) und die System-Sicherung. Nichts wird irgendwohin gesendet. Handbücher sind meist urheberrechtlich geschützt: importiere nur, was du nutzen darfst, und halte das Paket privat.

Im Leser schalten *Seitenbild* und *Text* die Ansicht um (die Wahl wird je Person gemerkt). Suchtreffer werden im Text markiert.
