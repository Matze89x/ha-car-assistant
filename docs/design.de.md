# Design-Handbuch

[🇬🇧 English](design.md) · 🇩🇪 Deutsch

Das Versprechen, auf das sich jedes Design und jedes Paket verlassen kann: [Design-Vertrag](design-contract.de.md).

Ein Aussehen, überall. Bevor du eine Seite baust oder änderst, lies das hier und nutze, was es schon gibt. **Ein Baustein hat genau eine Definition** – brauchen zwei Seiten dasselbe, nehmen sie dieselbe Klasse. Keine Regel kopieren, um sie „ein bisschen anzupassen“; die gemeinsame Regel ändern.

Wo es liegt: Werte und Grundbausteine in `static/app.css`, die Glas-Schicht und Seitenmuster in `static/pc-core.css` (lädt zuletzt), Icons in `icons.py`, Texte in `i18n.py`.

## 1. Werte (Tokens)

| Was | Token | Wert |
|---|---|---|
| Hintergrund | `--bg` | `#0d1016` |
| Text / gedämpft / blass | `--text` `--muted` `--dim` | `#f2f3f5` `#9ba1ac` `#6b7280` |
| Akzent (rot) | `--accent` | `#e2001a` – Hauptaktionen, aktive Zustände, das Logo |
| OK / bald / überfällig | `--ok` `--soon` `--overdue` | `#4ade80` `#fbbf24` `#f87171` – nur für Status |
| Glas | `--glass` `--glass2` `--glass-b` | durchscheinende Flächen und ihr 1-px-Rand |
| Button-Lichtkante | `--btn-hi` (`--hi-rgb`) | die helle Oberkante in jedem Glas-Button; eine Theme-Datei darf sie setzen (optional, hat einen Standardwert) |
| Überlagerungen auf Glas | `--fg-rgb` `--panel-rgb` `--panel-deep-rgb` `--strong` | `rgba(var(--fg-rgb), .07)` statt Weiß/Schwarz; helle Themes drehen sie um (ein helles Theme beginnt mit `/* scheme: light */`) |
| Radius | `--r-s` `--r-m` `--r-l`, `--r-surface` (= `--r-l`) | 8 / 12 / 16 px – klein (Felder in Karten, Chips), mittel (Knöpfe, Felder, Zeilen in einer Karte), **groß (alles, was auf einer Seite für sich steht: Karten, Listen, Hinweise, Tab-Leisten, Klappgruppen)** - Nachbarn auf einer Seite haben immer dieselbe Ecke |
| Kreise | `999px` | **nur** für Icon-Knöpfe, Pillen, Marken, Schalter; die Tab-Leiste folgt `--r-l + 5px` |
| Abstände | `--sp-edge` `--sp-col` `--sp-top` `--sp-head` `--sp-block` | 14 / 14 / 18 / 16 / 20 px – Rand, Spaltenabstand, erstes Element von oben, unter dem Seitenkopf, zwischen Blöcken |
| Höhen | `--head-h` `--lab-h` | 44 px Seitenkopf-Zeile, 25 px kleine Gruppenbeschriftung |
| Hinweise | `.notice-slot` `.notice.info/.ok/.warn/.err` | EIN Platz unter dem Seitenkopf (`page_head` legt den Platz an): die Einleitung der Seite (Info), „Gespeichert“-Meldungen, Warnungen und Fehler, immer dieselbe durchscheinende Kachel mit Symbol davor und der Farbe der Art. Altes `.flash`-Markup verschiebt `notices.js` dorthin; neuer Code nutzt `.notice`. |
| Abschnittsbeschriftungen | `--sp-label-top` `--sp-label-bottom` `--sp-label-x` | 28 / 10 / 6 px – Luft über einer kleinen Abschnittsbeschriftung (Fahrzeugpass, Tankmonate, Zusatzarbeiten ...), Abstand zur Kachel darunter. Jede Beschriftung nutzt diese Werte, keine Seite hat eigene Zahlen. |
| Aktionen im Seitenkopf | `.page-head .actions` | auf jedem Bildschirm (Handy, Tablet, Web) nur runde 40-px-Symbolknöpfe ohne Text, mittig zur Titelzeile; der Name steht in `aria-label` / `title`. Kein Zurück-Knopf neben der Mehr-Liste auf breiten Bildschirmen. |
| Schriften | Space Grotesk, Space Mono | Mono für Kennzeichen, Codes, Größen, Zahlen in Formularen |
| Icons | nur Material Design Icons | `icons.py`, mit `icon('name', size)`; keine Emojis, keine anderen Sets |

Verschachtelte Radien: innen = außen − Innenabstand (eine 32-px-Kachel in einer 16-px-Listenzeile mit 8–12 px Abstand hat 8 px).

**Feste Stufen – nichts dazwischen.** Schrift: 10 / 11 / 12 / 13 / 14 / 15 / 16 / 18 / 20 / 24 / 32 px (Labels 11, Text 15, Knöpfe 15, Felder 16, Kartentitel 18, Seitentitel 24). Ecken nur als `--r-s`, `--r-m`, `--r-l` oder `999px`. Bedienelemente: Felder 48 px, Knöpfe 44 px (klein 32 px), Icon-Knöpfe 40 px.

**Leichte Knöpfe, eine Zeile (feste Regel).** Jede Nebenaktion – Speichern in einem Feld, Löschen, Abbrechen, Hinzufügen, Bearbeiten – ist ein *leichter* Knopf (`.ghost-btn` / umrandet, `.danger` ist rot umrandet, nie ein gefüllter Block), und eine Reihe von Knöpfen bleibt IMMER in EINER Zeile (`flex-wrap: nowrap`, kurze Beschriftung). Nur die eine Hauptaktion einer Seite darf `.primary` sein.

**Ein Knopf, eine Regel** (`app.css`): keine Seite, Karte oder Maske überschreibt Höhe, Abstand oder Schriftgröße – sie wählt nur `.primary`, `.danger` oder `.small`. Der **Bearbeiten**-Link eines Eintrags ist immer `.rec-edit` (Stift-Icon + *Bearbeiten*).

## 2. Breakpoints

| Breite | Aufbau |
|---|---|
| < 760 px | Handy: Tab-Leiste unten (schwebend, Glas), eine Spalte |
| ≥ 760 px | Seitenleiste (nur Icons), Seiten wie zuvor |
| ≥ 1000 px | *Weiteres* wird zweite Navigation: Liste links (300–340 px, ab 1100 px 340–390 px), Seite rechts; Home hat zwei gleich breite Spalten |
| ≥ 1280 px | die Seitenleiste zeigt Beschriftungen |

Jede Seite bei 375, ~800, 1100 und 1280 px prüfen, mit allen Feldern gefüllt **und** nur mit dem Namen.

## 3. Seitenmuster

Jede Seite außer Home beginnt mit `page_head(icon, title)` (Makro in `_macros.html`): Icon + Titel + Autoname, eine 44-px-Zeile, 18 px vom oberen Rand. Aktionen stehen rechts (`{% call page_head(...) %}…{% endcall %}`); auf dem Handy wird die Hauptaktion zum Icon-Kreis (Beschriftung in `<span class="lbl">`). Der Zurück-Knopf steht auf dem Handy *im* Kopf (`.back-btn`); ab 1000 px ersetzt die Liste links ihn.

Die Führungsseiten der Ersteinrichtung (`/setup/*`) haben gar keine Navigation; die erste Seite *Fahrzeug hinzufügen* behält sie.

Neben der *Weiteres*-Liste beginnt das erste Element der Seite auf derselben Linie wie die erste Karte der Liste.

## 4. Bausteine

| Baustein | Klasse / Makro | Hinweise |
|---|---|---|
| Karte | `.card` | Glas, `--r-l`, 18 px Innenabstand, kein farbiger Balken |
| Home-Widget | `widget()`-Makro → `.wd`, `.wd-slot` | eine einheitliche Kachel: Icon-Chip und Titel links, rechts eine kleine Notiz (`meta`, z. B. das letzte Signal) oder der Pfeil, Wert (`.wd-v`), höchstens eine Zeile (`.wd-s`); Status-Chips rechts, Text links; Diagramme werden nie verzerrt (runder Punkt, runde Balken); Unterzeile (`.wd-s`); Größe `s` (halbe Zeile) oder `m` (ganze Zeile); eine Vorlage in `templates/widgets/` zeigt nichts, wenn es keine Daten gibt |
| Listenzeile (Weiteres, Einstellungen) | `.mgroup` > `.mi` | Icon-Chip `.mi-ic.c1…c7`, Titel `.mi-t`, Hinweis `.mi-v`, Pfeil |
| Icon-Chip | `.mi-ic.cN` | 32 px, Verlauf je Farbe; die Farben gehören zum Modul (`CHIP` in `nav_web.py`) |
| Knöpfe | `button`, `.button`, `.primary`, `.danger`, `.small` | ein Glas-System (durchscheinende Fläche, helle Oberkante): 44 px / `--r-m`; `.primary` = rotes Glas (die eine Hauptaktion), `.danger` / `.warn` = roter Rand, `.small` = 36 px / `--r-s`; `.ghost-btn` an Link, Label oder Button sieht gleich aus; es werden nur Theme-Werte benutzt, jedes Design (auch eine eigene Theme-Datei) färbt ihn um |
| Icon-Knopf (Kreis) | `.icon-btn` (+ `.back-btn`, `.cur-switch`, `.round-del`, `.wd-eye`, `.wd-grip`, `.vsw-x`) | 40-px-Kreis (36 / 34 für kleine) – eine Regel |
| Hinzufügen-Leiste | `details.add-card` | eingeklappte „+ Hinzufügen“-Leiste über einer Liste; das Formular öffnet sich darin |
| Leerzustand | `.card.empty-state` | Icon, ein Satz, der sagt, was zu tun ist |
| Felder | `input`, `select`, `textarea`, `.tf-field` / `.tf-l` | Beschriftung 11 px Großbuchstaben darüber, 48-px-Felder, Beispielwerte als Platzhalter (neutral, nie eine Marke) |
| Auswahl-Kacheln | `.season-pick` / `.sp` | große wählbare Kacheln mit Icon statt Dropdown bei 2–4 Optionen |
| Schalter | `.switch`, Makro `switch_row()` | an = Akzent; jede An/Aus-Einstellung ist eine Schalter-Zeile mit Linie oben und unten (zwei Zeilen teilen sich eine Linie; nie eine zweite Linie über einer Button-Leiste) Eine Schalter-Zeile hat keinen äußeren Abstand: Eine Regel für untereinander stehende Beschriftungen muss `.sw-row` ausnehmen (ein Test prüft das), damit jede Zeile mittig zwischen ihren zwei Linien steht. |
| Name + Slogan | `.brand-lock`, `.sb-brand`, `.about-id` | immer EINE Einheit: Slogan halb so groß, exakt so breit wie der Name (Seitenleiste: füllt die Leiste), überall gleicher Abstand |
| Datum und Uhrzeit | `regional.py` | angezeigt wie unter Einstellungen → System → Datum & Uhrzeit; gespeichert ISO / 24 h |
| Chips / Marken | `.badge`, `.pos-chip`, `.schip` | Pillen (`999px`), nur Statusfarben |
| Info-Seite | `.about-hero`, `.about-stats`, `.about-car` | Kopfkarte (Logo, Name, Version), Zahlenkacheln, dann je Auto eine Karte mit Zeilen (Icon-Chip, Name, Kleintext, Badges) – siehe Seite „Über“ |
| Auto-Bild / Video | `.hero-car.soft`, `.hero-media` | Fotos und Videos blenden an allen Seiten aus; ein Video läuft einmal und bleibt auf dem letzten Bild stehen (`static/media.js`); Bibliothek `media.html` mit Vorschau, Badge „In Benutzung“, Löschen-x |
| Seitenwechsel | `nav.pager` | lange Listen zeigen 50 Einträge je Seite mit Zurück / Weiter und der Gesamtzahl |
| Dialog | `dialog.vsw` (+ `#cdlg` für Rückfragen) | unscharfer Hintergrund, `--r-l`-Karte; zerstörende Aktionen fragen immer (`data-confirm`, `data-confirm-ok`) |
| 404 / Fehler | `error.html` | große Zahl mit Verlauf, ein Satz, zwei Knöpfe |

## 4a. Farben, die nicht der Akzent sind

Jede Farbe, die nicht die des Designs ist, kommt aus einer Stelle, dem `:root`-Block in `pc-core.css`: die sieben Chip-Farben der Module (`--chip-1` … `--chip-7`), Start und Ziel einer Route (`--map-start`, `--map-end`) und die vierte Diagrammfarbe `--chart-4`. Die letzte folgt dem Design: `themes.accent_css()` wählt aus wenigen Kandidaten den Farbton, der am weitesten vom Akzent, vom Grün für „in Ordnung“ und vom Bernstein für „bald“ entfernt ist, damit ein Diagramm nie zwei ähnliche Farben zeigt. Schreibe keine Hex-Farbe in eine Regel.

## 4b. Die festen Bausteine (je eine Definition, überall genutzt)

Alles auf jeder Seite besteht aus dieser kurzen Liste. Eine neue Seite nutzt sie; ein neuer Look für etwas Vorhandenes ist eine Änderung der einen Definition, nie eine zweite Klasse.

| Baustein | Einsatz | Definiert in |
|---|---|---|
| **Seitenkopf** | `page_head()`: Symbol + Titel, darunter der Name des Autos, rechts runde Symbolknöpfe (ohne Text), mittig zum ganzen Kopf | `_macros.html`, `.page-head` |
| **Hinweis-Kachel** | `.notice` (Info / Gespeichert / Warnung / Fehler) im Platz unter dem Kopf; die Einleitung der Seite ist die erste Kachel | `notices.py` (Server), `.notice-slot` |
| **Tab-Leiste (Text + Symbol)** | `.seg-tabs`: zwischen Ansichten oder Seiten wechseln (Verwaltung / Hinzufügen / Quellen, Jahreszeiten, Zeiträume ...). Vor jedem Tab ein Symbol | `.seg-tabs` |
| **Symbol-Schalter (rund)** | `.seg-icons`: zwei oder drei Optionen nur als Symbole (Preis / Entfernung ...) | `.seg-icons` |
| **Sortiergriff** | `.grip`: eine Leiste links in einer Zeile, so hoch wie die Zeile, mit derselben Kontur und den Punkten darin. Zeilen, die man ordnen darf, stehen als `[data-sort-item]` in einem `[data-sortable]`-Container; die Leiste ziehen (Maus oder Finger) oder auf ihr die Pfeiltasten drücken. Optional `data-sort-post="<url>"` sendet `order=<data-sort-id>,...`; das Ereignis `sortchange` meldet es der Seite. Zeilen, die nicht verschoben werden können, tragen dieselbe Leiste ohne Punkte (mit Schloss, wenn sie fest sind), damit der linke Rand in jeder Zeile gleich ist. **Pfeilknöpfe nach oben / unten werden nie zum Sortieren benutzt.** | `.grip`, `[data-sort-item]`, `app.js` (SORTING) |
| **Navigation** | `.tabbar` (untere Leiste / Seitenleiste) und die *Weiteres*-Liste – keine Tab-Leiste | `base.html`, `.tabbar`, `.mgroup` |
| **Abschnittsbeschriftung** | `.vd-group-h`, `.rec-month`: 28 px darüber, 10 px zur Kachel darunter | `--sp-label-*` |
| **Karte / Kachel** | `.card`, `.wd` (Widget, Pfeil oben rechts, wenn es ein Link ist), `.rec` (Listenkarte) | `.card`, `.wd`, `.rec` |
| **Knöpfe** | `.button` (+ `.primary`, `.danger`, `.small`), `.icon-btn` (rund); unten rechts in der Karte, eine Zeile | `.button`, `.icon-btn` |
| **Felder / Schalter** | `input`, `select`, `textarea`; jede Ja/Nein-Wahl ist eine `switch_row()` (Text links, Ja / Nein, der runde Schalter rechts) - kein loses Kontrollkästchen | `app.css`, `_macros.html` |
| **Kilometer-Zählwerk** | `odo_plate()`: der dunkle Zählwerk-Kasten mit der Beschriftung darüber; die Ziffern laufen durch, ein Tipp dreht ihn zur Eingabe um (die Rückseite IST das Eingabefeld). `.odo-static` (fest, nichts zum Umdrehen), solange ein Plugin den Kilometerstand meldet, und als Widget-Look *Zählwerk* | `_macros.html`, `.odo-flip` |
| **Karte (Map)** | `.tp-map` / `.pos-map`: volle Breite, 16:9; die Kacheln kommen von unserer eigenen Kachel-Adresse | `.pos-map` |

Ein Test (`tests/test_design_rules.py`) verweigert eine dritte Art von Tab-Leiste. Plugin-Seiten (`kind: "frame"`) bekommen denselben Look aus dem `kit`-Stylesheet (siehe [Plugins](plugins.de.md)).

## 5. Verhaltensregeln

- **Pro Fahrzeug.** Alles, was zu einem Auto gehört, liegt unter diesem Auto; nur Konto, Fahrzeuge, Einstellungen und Systemdienste sind global. Fahrzeuge werden über den Namen angesprochen (`/v/<name>/…`).
- **Nur zeigen, was es gibt.** Keine Daten → keine Kachel, keine leere Zeile, kein Platzhalter-Kasten. Ein einzelner `-` in einem Textfeld gilt als leer.
- **Zerstörende Aktionen** nutzen den Bestätigungsdialog und sagen, was verloren geht.
- **Jetzt manuell, später Plugin.** Werte, die ein Plugin liefern wird (Reichweite, Tankstand, Türen, Position …), erscheinen nur, wenn sie über die Plugin-API kommen; die manuelle Eingabe bleibt der Rückfall und nutzt dieselben Felder.
- **Standardmäßig nichts online.** Externe Dienste sind opt-in und werden erklärt.
- **Texte** kommen in `EN` und `DE` in `i18n.py`; Vorlagen setzen Schlüssel nie zusammen.
- **Keine Inline-Skripte oder Stile, die ein Skript brauchen** (strenge CSP). Verhalten liegt in `static/*.js`.

## 6. Checkliste für eine neue Seite oder einen Baustein

1. Gibt es dafür schon einen Baustein? Den nutzen.
2. Nur Tokens – keine festen Farben, Radien oder Abstände. Ein Block, der auf einer Seite für sich steht, bekommt die EINE Ecke `--r-surface`, indem er in die Liste der einen Regel am Ende von `pc-core.css` kommt (kein eigener Radius); sonst schlägt ein Test fehl. Sein erster Block beginnt auf einer Linie mit der ersten Karte der *Weiteres*-Liste.
3. `page_head`, richtige Abstände, funktioniert bei 375 / 800 / 1100 / 1280 px.
4. Leerzustand (die Karte mit Symbol und einem hilfreichen Satz: `.card.empty-state`, nie eine nackte Textzeile), ein Eintrag, viele Einträge, sehr langer Text.
5. EN- und DE-Texte; Icon aus `icons.py`.
6. Ein Test (`tests/`) für das Verhalten, eine Zeile in beiden Changelogs, Version hoch.

## 7. Bekannte Doppelungen (technische Schuld)

`app.css` trägt noch die älteren „einfachen“ Regeln, die `pc-core.css` überschreibt (`.mgroup`, `.mi`, `.tile`, `.table-wrap`, `.tiles`, `.vhome …`). Wer eine davon anfasst, führt sie zu einer Definition zusammen und löscht die andere.

## 8. Geschwindigkeit und Datenmenge

Jede Seite bleibt schnell – auch mit 15 Autos und Tausenden Einträgen je Auto (gemessen: jede Seite unter ca. 110 ms).

- **Listen sind seitenweise** (`entities.PAGE_SIZE`, 50). Nie alle Zeilen einer Tabelle ausgeben.
- **Keine Abfrage in einer Schleife.** Einmal je Seite lesen (`summary.service_index`, gruppierte Zählungen in `about.py`) und wiederverwenden.
- **Indizes** für alles, was je Fahrzeug gelesen oder gelöscht wird (`migrations_11.sql`); eine neue Fahrzeug-Tabelle bekommt ihren Index in der eigenen Migration.
- **Automatische Messwerte werden ausgedünnt** – ein Plugin, das alle paar Sekunden meldet, erzeugt eine Kilometerstand-Zeile pro Tag (`summary.record_odometer`); Strecken werden mit höchstens `charts.MAX_ROUTE_POINTS` Punkten gezeichnet.
- **Antworten sind gzip-komprimiert**; `/static/…?v=<Version>` wird ein Jahr zwischengespeichert, eine geänderte Datei braucht also eine neue Versionsnummer.
- Datenbank-Pflege (`PRAGMA optimize`, Log kürzen) läuft täglich im Worker.

### Dunkel / Hell mit eigener Farbe
Neben *Klassisch rot* gibt es *Hell*, *Dunkel* und *Auto* (*Einstellungen → System → Design*); wählst du eines davon, erscheint direkt darunter *Deine Farbe*. Eine Farbe vom Farbkreis wird für den ganzen Server gespeichert (`ui.accent`); `themes.accent_css()` errechnet daraus die Akzent-Familie - `--accent`, `--accent-rgb`, `--accent-hi`, `--accent-top`, `--accent-bot`, die beiden Hover-Werte und `--accent-text` (weiß oder dunkel, je nachdem, was auf dem Knopf lesbar bleibt). Die Helligkeit bleibt in einem Bereich, der zum Hintergrund passt, und `--ok` / `--soon` / `--overdue` werden nie angefasst. Die Seite trägt das Ergebnis in `<style id="accent-custom">`, Frames bekommen es in `/frame-theme.css`. Baue neue Bausteine nur aus den Tokens, dann folgen sie der Farbe von selbst; nimm für Schrift auf Akzentflächen `--accent-text`, nie ein festes Weiß.

## 9. Die Design-Methode (eine Art, jede Seite zu bauen)

Eine Seite besteht nur aus diesen Teilen – `tests/test_design_rules.py` prüft die mechanischen Regeln:

1. **Kopf:** jede Seite beginnt mit `page_head(icon, title)` (Ausnahmen: Home, die 404-Seite und die erste Sprachseite).
2. **Farben nur als Tokens** (Abschnitt 1); keine Inline-Stile außer der Breite eines Balkens; ein Baustein hat eine Definition (Abschnitt 4).
3. **Reiter (`.seg-tabs`)** nur für echte Unterbereiche eines Themas: *Einstellungen* (Benutzer, Design, Region, System), *Integrationen* und *Plugins* eines Fahrzeugs. Seiten eines Fahrzeugs haben keine Reiterleisten – sie werden über die Leiste oder Weiteres erreicht.
4. **Listen von Einträgen = Karten** (`.rec-grid` / `.rec`): Titel, wichtigste Angaben in zwei Spalten, *Bearbeiten* darunter eingeklappt. Keine breiten Tabellen; auf jeder Breite, auch auf dem Handy.
5. **Einstellungen wirken sofort.** Ein Einstellungsformular trägt `data-live` (oder `data-theme-live`) und hat **keinen Speichern-Knopf**: es speichert bei der Änderung; `data-reload` lädt danach neu (Sprache). Eine sichtbare Änderung (Design, Navigation) erscheint sofort. Nur echte Aktionen (Hochladen, Zurücksetzen, Löschen, Anlegen) haben Knöpfe – **primär** für die eine Hauptaktion, sonst schlicht.
6. **Zerstörendes = rot und mit Rückfrage:** `.danger` (oder der runde rote Mülleimer auf einer Karte) im Gefahren-Rot des Designs, immer mit `data-confirm`.
7. **Erst die Ebene:** serverbezogen, benutzerbezogen oder fahrzeugbezogen (siehe CLAUDE.md) entscheidet, *wo* eine Einstellung liegt: in den Einstellungs-Reitern, im Login oder auf den Seiten des Fahrzeugs.
8. **Styles werden ein Jahr zwischengespeichert:** jede Änderung an einer `.css` / `.js` braucht eine neue Versionsnummer.
