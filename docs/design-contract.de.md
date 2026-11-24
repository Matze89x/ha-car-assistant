# Design-Vertrag

[🇬🇧 English](design-contract.md) · 🇩🇪 Deutsch

Was in jedem Design, auf jeder Seite und in jedem Paket gleich bleibt – die *Corporate Identity* und das *Corporate Design* von Car Assistant an einer Stelle. Wie man Seiten baut, steht im [Design-Handbuch](design.de.md); diese Seite ist das Versprechen: **worauf sich ein Design, eine Seite der App und eine Seite eines Pakets verlassen können.** Tests halten es wahr (`tests/test_design_contract.py`).

## 1. Identität
| | |
|---|---|
| Name und Slogan | **Car Assistant** – **Drive · Log · Go** (in jeder Sprache, in Grafiken in Großbuchstaben) |
| Farben | Rot `#e2001a` (Akzent, das Logo), Grün `#4ade80` (ok, das andere Ende des Logos), Dunkel `#0d1016` (Hintergrund) |
| Schriften | Space Grotesk (Text), Space Mono (Zahlen, Kennzeichen, Codes) – selbst mitgeliefert |
| Icons | nur Material Design Icons (`icons.py`), ein Icon je Funktion |
| Logo | das Auto in einem abgerundeten Quadrat mit Rand von Rot zu Grün (`docs/logo.svg`) |
| Banner, Add-on-Logo | der Name in einer Zeile, darunter **DRIVE · LOG · GO** vom C bis zum t des Namens, der Block senkrecht mittig zum Logo (`tools/make_banner.py` baut beide) |
| Ton | kurz, freundlich, ohne Fachwörter; eine Haupt-Aktion je Seite; ein Text nur, wo ein Icon nicht reicht |

## 2. Variablen (der Vertrag für Designs und Pakete)
Jedes Design – und jede Seite, die ein Paket zeigt (`kind: "frame"`, [Plugins](plugins.de.md)) – kann sich auf diese CSS-Variablen verlassen:

| Gruppe | Variablen |
|---|---|
| Flächen | `--bg` `--card` `--card2` `--line` `--line2` |
| Text | `--text` `--muted` `--dim` `--strong` |
| Akzent | `--accent` `--accent-rgb` `--accent-hi` `--accent-text` |
| Status | `--ok` `--soon` `--overdue` `--ok-rgb` `--soon-rgb` `--overdue-rgb` `--ok-bg` `--soon-bg` `--overdue-bg` |
| Glas und Buttons | `--fg-rgb` `--glass` `--glass2` `--glass-b` `--btn-edge` `--btn-hi` |
| Form | `--r-s` `--r-m` `--r-l` (8 / 12 / 16 px) |
| Abstände | `--sp-edge` `--sp-col` `--sp-block` (14 / 14 / 20 px) |

Für eine helle Ebene `rgba(var(--fg-rgb), .07)` statt Weiß oder Schwarz – helle Designs drehen `--fg-rgb` um. Eine Farbe nie als Hex-Wert in eine Regel schreiben; sie kommt aus einer Variablen.

## 3. Designs (Themes)
Ein Design ist eine Datei `static/themes/<Name>.css` mit der Regel `:root[data-theme="<Name>"] { ... }`; sie setzt nur die Variablen, die vom dunklen Grund (`default`) abweichen. Ein helles Design setzt zusätzlich `color-scheme: light`, die Flächen, `--fg-rgb`, die Glas-Werte und die Statusfarben. Was jedes Design einhalten muss (für alle getestet):
- die Variablen aus Abschnitt 2 sind da (aus dem Grund oder dem Design),
- Text auf Hintergrund und auf Karten: Kontrast mindestens **4,5 : 1**; `--muted` auf Karten **4,5 : 1**; `--dim` **3 : 1** auf Karten und auf dem Hintergrund (die Abschnittsbeschriftungen stehen auf der Seite),
- Akzent, `--ok`, `--soon` und `--overdue` auf einer Karte: mindestens **3 : 1**; `--accent-text` auf `--accent`: mindestens **3 : 1**.

Vorhanden: *Klassisch rot* (dunkel, der Standard) sowie *Hell*, *Dunkel* und *Auto* (folgt dem Gerät), jeweils mit einer eigenen Farbe - die Farbe ist ein Wert, den du auf einem Farbkreis wählst (siehe Design-Handbuch). Ein Design je Auto überschreibt das des Servers. Eine eigene Theme-Datei im Datenordner funktioniert genauso.

## 4. Bausteine (je eine Definition)
| Baustein | Klasse | Regel |
|---|---|---|
| Button | `button`, `.button`, `.ghost-btn` | Glas, 44 px; `.small` 36 px; `.primary` (rotes Glas) ist die eine Haupt-Aktion einer Seite, rechts angedockt; `.danger` ist ein roter Rand |
| Icon-Button | `.icon-btn`, `.ib`, `.eq-i` | rund oder quadratisch, immer mit Kontur; der Text bleibt für Screenreader (`.sr`), keine Hover-Tooltips |
| Karte | `.card` | Glas, 18 px innen, `--r-l`, 14 px zwischen Karten |
| Eintragskarte | `.rec` in `.rec-grid` | Datum, Titel, Angaben, eine dünne Trennlinie und ein kleiner *Bearbeiten*-Button rechts; zwei Spalten auf breitem Bildschirm, eine auf dem Handy |
| Liste | `.rec-grid` + `.rec-month` | ein Stapel von 10 / 25 / 50 Karten (Wahl der Person), der nächste lädt beim Scrollen, eine Überschrift je Zeitraum (Heute, Gestern, Diese Woche, Letzte Woche, dann der Monat) |
| Seitenkopf | `page_head()` | Zurück, Icon, Titel, Autoname, Aktionen rechts; auf jeder Seite gleich hoch |
| Formularfelder | `input` `select` `textarea` | 48 px, Text 16 px, Ecken 8 px |
| Chip, Badge | `.chip`, `.badge` | Pillen; `.ok` `.soon` `.overdue` nur für Status |
| Buttons der Einrichtung | `.step-nav` | *Zurück* links, die eine Haupt-Aktion rechts, eine Zeile |

## 5. Seitenmuster
- **Listenseite** (Service, Teile, Tanken, Termine …): Kopf mit Hinzufügen-Button rechts, ein Suchfeld, die Karten unter Zeitraum-Überschriften, der nächste Stapel beim Scrollen.
- **Einstellungs-Seite:** Kopf, Reiter, Karten mit Überschrift (18 px) und Hinweis (14 px).
- **Schritt der Einrichtung:** Schrittleiste, eine Karte mit der Erklärung, die Auswahl, `.step-nav`.
- **Paketseite** (`kind: "frame"`): der übliche Kopf mit der Version des Pakets rechts, darunter die eigene Seite des Pakets, die das Kit (`/frame-kit.css`) nutzt und so zum Design passt.

## 6. Regeln, die immer gelten
Leichte Buttons, **eine Zeile**; eine Haupt-Aktion je Seite; Einstellungen, die etwas Sichtbares ändern, wirken sofort (kein Speichern-Button); kein Inline-Skript (die CSP verbietet es); jeder Text auf Englisch und Deutsch; **Schalter stehen immer am rechten Ende ihrer Zeile, wie beim iPhone** (die App zeichnet jeden Schalter; ein Plugin kann keinen verschieben); eine abgeschaltete Funktion zeigt nichts und löst nichts aus.
