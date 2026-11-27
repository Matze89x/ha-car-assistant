# Design handbook

🇬🇧 English · [🇩🇪 Deutsch](design.de.md)

The promise every design and package can rely on: [Design contract](design-contract.md).

One look, everywhere. Before you build or change a page, read this and reuse what exists. **A component has exactly one definition** – if two pages need the same thing, they use the same class. Never copy a rule to "tweak it a little"; change the shared rule.

Where it lives: tokens and base components in `static/app.css`, the glass layer and page patterns in `static/pc-core.css` (loads last), icons in `icons.py`, texts in `i18n.py`.

## 1. Tokens

| What | Token | Value |
|---|---|---|
| Background | `--bg` | `#0d1016` |
| Text / muted / dim | `--text` `--muted` `--dim` | `#f2f3f5` `#9ba1ac` `#6b7280` |
| Accent (red) | `--accent` | `#e2001a` – primary actions, active states, the logo |
| OK / soon / overdue | `--ok` `--soon` `--overdue` | `#4ade80` `#fbbf24` `#f87171` – status only |
| Glass | `--glass` `--glass2` `--glass-b` | transparent surfaces and their 1 px border |
| Button highlight | `--btn-hi` (`--hi-rgb`) | the light top edge inside every glass button; a theme file may set it (optional, has a default) |
| Overlays on glass | `--fg-rgb` `--panel-rgb` `--panel-deep-rgb` `--strong` | `rgba(var(--fg-rgb), .07)` instead of white/black; light themes flip them (a light theme starts with `/* scheme: light */`) |
| Radius | `--r-s` `--r-m` `--r-l`, `--r-surface` (= `--r-l`) | 8 / 12 / 16 px – small (inputs inside cards, chips), medium (buttons, fields, rows inside a card), **large (everything that stands on its own on a page: cards, lists, notices, tab bars, folding groups)** - neighbours on a page always share one corner |
| Circles | `999px` | **only** for icon buttons, pills, badges, switches, the tab bar's outer shape follows `--r-l + 5px` |
| Spacing | `--sp-edge` `--sp-col` `--sp-top` `--sp-head` `--sp-block` | 14 / 14 / 18 / 16 / 20 px – edge, column gap, first element from the top, below the page header, between blocks |
| Sub-window spacing | `--sp-sub` `--sp-sub-pad-y` `--sp-sub-pad-x` `--sp-sub-label` | 10 / 10 / 12 / 8 px – between two sub-windows of a card, inside a sub-window (top / bottom, left / right), under its label |
| Heights | `--head-h` `--lab-h` | 44 px page header row, 25 px small group label |
| Notices | `.notice-slot` `.notice.info/.ok/.warn/.err` | ONE place under the page header (`page_head` makes the slot): the page introduction (info), "saved" messages, warnings and errors, always the same transparent tile with an icon in front and the tint of its kind. Old `.flash` markup is moved there by `notices.js`; new code uses `.notice`. |
| Section labels | `--sp-label-top` `--sp-label-bottom` `--sp-label-x` | 28 / 10 / 6 px – air above a small section label (vehicle passport, fuel months, tasks ...), how close it sits on the tile below. Every label takes these, no page has its own numbers. A heading that stands on its own on a page (outside a card) is always this label - left aligned, 11 px, upper case, dim; never centred, never another size (`python tools/check_headings.py` checks every page). The rules about buttons (one line, one height, one main action, bottom right, tap area, names) are measured on every page by `python tools/check_ui.py`. |
| Page header actions | `.page-head .actions` | on every screen (phone, tablet, web) only round 40 px icon buttons without text, centred on the title row; the name is in `aria-label` / `title`. No Back button next to the More list on wide screens. |
| Fonts | Space Grotesk, Space Mono | Mono for plates, codes, sizes, numbers in forms |
| Icons | Material Design Icons only | `icons.py`, rendered with `icon('name', size)`; no emojis, no other sets |

Nested radii: inner = outer − padding (a 32 px chip in a 16 px list row with 8–12 px padding has 8 px).

**Fixed scales - nothing in between.** Type: 10 / 11 / 12 / 13 / 14 / 15 / 16 / 18 / 20 / 24 / 32 px (labels 11, body 15, buttons 15, fields 16, card titles 18, page title 24). Corners only as `--r-s`, `--r-m`, `--r-l` or `999px`. Controls: fields 48 px, buttons 44 px (small 32 px), icon buttons 40 px.

**The space inside a card (standing rule).** The distance below the last thing in a card is the card's own padding and nothing more - the same as at its left. Whatever stands last adds no margin of its own, a line-separated row that is last ends with its content (`pc-core.css`, end of file); `python tools/check_ui.py` measures it on every page.

**Light buttons, one line (standing rule).** Every secondary action - save inside a panel, delete, cancel, add, edit - is a *light* button (`.ghost-btn` / outlined, `.danger` is outlined red, never a filled block), and a row of buttons always stays on ONE line (`flex-wrap: nowrap`, labels short). Only the single main action of a page may be `.primary`.

**The bar of a plugin tile (`.addon-bar`).** One line, bottom of the tile, always in the same order: *Uninstall* as a bin without text (`.ico-only`, the only button that is a symbol at every width), *Logs*, *Settings*, up to three buttons of the plugin itself (`buttons` in the manifest, [plugins.md](plugins.md#the-tile-of-a-plugin-and-its-buttons-buttons)), the one main button on the right. The bar is a size container (`container: abar`): the buttons lose their words by the width of the TILE (not the window; `fb0`-`fb3` = number of the plugin's own buttons), then they give way down to 32 px, and only with two or three own buttons on a tile narrower than 330 px does the main button become a symbol. Never wrap, never a second row, never a *More* menu.

**One button, one rule** (`app.css`): no page, card or form overrides its height, padding or type size - it only picks `.primary`, `.danger` or `.small`. The **edit** link of a record is always `.rec-edit` (pencil icon + *Edit*).

## 2. Breakpoints

| Width | Layout |
|---|---|
| < 760 px | phone: tab bar at the bottom (floating, glass), one column |
| ≥ 760 px | sidebar (icons only), pages as before |
| ≥ 1000 px | *More* becomes a second navigation: list left (300–340 px, 340–390 px from 1100), page right; Home is two equal columns |
| ≥ 1280 px | the sidebar shows labels |

Test every page at 375, ~800, 1100 and 1280 px, with all fields filled **and** with only the name.

## 3. Page pattern

Every page except Home starts with `page_head(icon, title)` (macro in `_macros.html`): icon + title + car name, a 44 px row, 18 px from the top. Actions go on the right (`{% call page_head(...) %}…{% endcall %}`); on phones the primary action collapses to an icon circle (wrap its label in `<span class="lbl">`). The back button on phones sits *in* the header (`.back-btn`); from 1000 px the list on the left replaces it.

First-start guide pages (`/setup/*`) have no navigation at all; the first *Add vehicle* page keeps it.

Next to the *More* list the first element of the page starts on the same line as the first card of the list - **on every page, at every width, with a message above or an empty page**. A card with a top margin of its own inside a grid cell (a column of the About page) breaks it: a margin inside a grid cell does not collapse. `python tools/check_alignment.py` measures every page of the *More* list in a headless Chrome (first block, title line, gap to the list) and `tests/test_page_alignment.py` runs it where Chrome is installed; run it after every change of a page header, a notice or a column.

## 4. Components

| Component | Class / macro | Notes |
|---|---|---|
| Card | `.card` | glass, `--r-l`, 18 px padding, no coloured bar |
| Home widget | `widget()` macro → `.wd`, `.wd-slot` | one uniform tile: icon chip and title left, a small note (`meta`, e.g. the last signal) or the arrow right, value (`.wd-v`), at most one sub line (`.wd-s`); status chips right, text left; charts are never stretched (round dot, round bars); size `s` (half row) or `m` (full row); a template in `templates/widgets/` renders nothing when there is no data |
| List row (More, settings) | `.mgroup` > `.mi` | icon chip `.mi-ic.c1…c7`, title `.mi-t`, hint `.mi-v`, chevron |
| Icon chip | `.mi-ic.cN` | 32 px, gradient per colour; colours are part of the module (`CHIP` in `nav_web.py`) |
| Buttons | `button`, `.button`, `.primary`, `.danger`, `.small` | one glass system (translucent fill, light top edge): 44 px / `--r-m`; `.primary` = red glass (the one main action), `.danger` / `.warn` = red outline, `.small` = 36 px / `--r-s`; `.ghost-btn` on a link, label or button has the same look; only theme tokens are used, so every design (also your own theme file) recolours it |
| Icon button (circle) | `.icon-btn` (+ `.back-btn`, `.cur-switch`, `.round-del`, `.wd-eye`, `.wd-grip`, `.vsw-x`) | 40 px circle (36 / 34 for small ones) – one rule |
| Add bar | `details.add-card` | collapsed "+ Add" bar above a list; the form opens inside |
| Empty state | `.card.empty-state` | icon, one sentence that says what to do |
| Fields | `input`, `select`, `textarea`, `.tf-field` / `.tf-l` | uppercase 11 px label above, 48 px fields, example values as placeholders (neutral, never a brand) |
| Choice tiles | `.season-pick` / `.sp` | big selectable tiles with an icon instead of a drop-down for 2–4 options |
| Switch | `.switch`, `switch_row()` macro | **always on the right** (see rule below); on = accent; every on/off setting is a switch row with a line above and below (two rows share one line; never a second line above a button bar) A switch row has no outer gap: a rule for stacked labels must exclude `.sw-row` (a test guards it), so every row is centred between its two lines. |
| Name + slogan | `.brand-lock`, `.sb-brand`, `.about-id` | always ONE unit: slogan half the size, exactly as wide as the name (side bar: fills the bar), same gap everywhere |
| Dates and times | `regional.py` | shown as set under Settings → System → Date & time; stored ISO / 24 h |
| Receipt card | `.rcpt` | a purchase (*Parts*) and a fill-up (*Fuel*) look like a till receipt - see 4d |
| Chips / badges | `.badge`, `.pos-chip`, `.schip` | pills (`999px`), status colours only |
| Info page | `.about-hero`, `.about-stats`, `.about-car` | hero card (logo, name, version), figure tiles, then one card per car with rows (icon chip, name, small text, badges) – see the About page |
| Car picture / video | `.hero-car.soft`, `.hero-media` | photos and videos fade out on all sides; a video plays once and rests on its last frame (`static/media.js`); library page `media.html` with thumbnails, "in use" badge, delete x |
| Pager | `nav.pager` | long lists show 50 records per page with Previous / Next and the total |
| Dialog | `dialog.vsw` (+ `#cdlg` for confirmations) | blurred backdrop, `--r-l` card; destructive actions always ask (`data-confirm`, `data-confirm-ok`) |
| 404 / errors | `error.html` | big gradient number, one sentence, two buttons |

## 4a. Colours that are not the accent

Every colour that is not the design's own comes from one place, the `:root` block of `pc-core.css`: the seven chip colours of the modules (`--chip-1` … `--chip-7`), start and end of a route (`--map-start`, `--map-end`) and the fourth chart colour `--chart-4`. The last one follows the design: `themes.accent_css()` picks, of a few candidates, the hue farthest from the accent, the green of "fine" and the amber of "soon", so a chart never shows two colours that look alike. Do not write a hex colour into a rule.

## 4b. The fixed building blocks (one definition each, used everywhere)

Everything on every page is built from this short list. A new page uses these; a new look for something that exists is a change of the one definition, never a second class.

| Block | Use | Where it is defined |
|---|---|---|
| **Page header** | `page_head()`: symbol + title, the car's name below, round icon buttons (no text) at the right, centred on the whole header | `_macros.html`, `.page-head` |
| **Notice tile** | `.notice` (info / saved / warning / error) in the slot under the header; the page introduction is the first tile | `notices.py` (server), `.notice-slot` |
| **Tab bar (text + symbol)** | `.seg-tabs`: switch between views or pages (Management / Add / Sources, seasons, periods, ...). A symbol in front of every tab | `.seg-tabs` |
| **Field with its functions** | `.fld` | the input and, at its right edge, icon actions inside the field (`.fld-act`: open, copy, change, scan a photo) - **the function sits in the field, not in a button next to it**. Locked fields (`disabled`) get a pencil that opens a popup; link and key fields get *copy* (and *open*). Use it whenever a field has a function of its own | `.fld`, `.fld-act`, `.fld.mono` (keys, tokens) |
| **Symbol switch (round)** | `.seg-icons`: two or three options as symbols only (price / distance ...) | `.seg-icons` |
| **Sort handle** | `.grip`: a strip on the left of a row, as high as the row, with the same contour and the dots in it. Rows that a person may put in order sit in a `[data-sortable]` container as `[data-sort-item]`; drag the strip (mouse or finger) or press the arrow keys on it. Optional `data-sort-post="<url>"` sends `order=<data-sort-id>,...`; the event `sortchange` tells the page. Rows that cannot move carry the same strip without dots (a lock when they are fixed), so the left edge is the same on every row. **Up / down arrow buttons are never used for sorting.** | `.grip`, `[data-sort-item]`, `app.js` (SORTING) |
| **Navigation** | `.tabbar` (bottom bar / side bar) and the *More* list - not a tab bar | `base.html`, `.tabbar`, `.mgroup` |
| **Section label** | `.vd-group-h`, `.rec-month`: 28 px above, 10 px to the tile below | `--sp-label-*` |
| **Card / tile** | `.card`, `.wd` (widget, the arrow top right when it is a link), `.rec` (list card) | `.card`, `.wd`, `.rec` |
| **Buttons** | `.button` (+ `.primary`, `.danger`, `.small`), `.icon-btn` (round); bottom right of a card, one line | `.button`, `.icon-btn` |
| **Receipt card** | `.rcpt` (`.rcpt-head`, `.rcpt-line` + `.rcpt-price`, `.rcpt-meta`, `.rcpt-acts`): a fill-up and a purchase as a till receipt (4d) | `.rcpt` |
| **Fields / switch** | `input`, `select`, `textarea`; every on / off choice is a `switch_row()` (text left, Yes / No, the round switch right) - no loose checkbox | `app.css`, `_macros.html` |
| **Odometer plate** | `odo_plate()`: the dark counter box with the label above; the digits roll down, a tap turns it over to the entry (the back IS the input box). `.odo-static` (fixed, nothing to turn) while a plugin reports the odometer and as the widget look *Counter box* | `_macros.html`, `.odo-flip` |
| **Map** | `.tp-map` / `.pos-map`: full width, 16:9; the tiles come from our own tile address | `.pos-map` |

A test (`tests/test_design_rules.py`) refuses a third kind of tab bar. Plugin pages (`kind: "frame"`) get the same look from the `kit` style sheet (see [plugins](plugins.md)).

## 4c. Card with sub-windows (standing rule)

A **card is a category** (its title is `h2`: symbol, name, a badge at the right if it has a state). When the content of a card falls into **two or more sub-areas** - a sign-in card with *Sign-in details*, *Passkeys* and *Users*; a notification card with *How you are told*, the messages per car and *General* - **every sub-area is a sub-window** inside the card, in this one look:

| Part | Class | Rule |
|---|---|---|
| Sub-window | `.sub-card` | framed, `--r-m` corners, the faint glass fill; **always** spaced by `--sp-sub`, padded by `--sp-sub-pad-y` (below the header band: its own height) / `--sp-sub-pad-x` - never a margin or padding of its own |
| Label = header band | `.sub-h` (an `h3`, always written with the macro `sub_h(icon, text)`) | the **header band** of the window: the full width of the window, 34 px high, at its top edge (the window has no padding on top then), in the colour of the contour (`--glass-b`) with the bright title colour; a **symbol in the main colour** (16 px, `--accent`) in front of the name, small, upper case; `--sp-sub-label` between the band and the content; names the area in one or two words. `tools/check_ui.py` measures band, width and padding |
| Order inside | | label, one short hint (`.hint`), the content, then the buttons **bottom right** (`.form-bar`); what is only an explanation stays in the hint |
| Several of one kind | `.seg-tabs` inside the window | one tab per car (or season, ...), the tab bar scrolls sideways when there are many; under the open tab only what that item really has |
| Buttons in a window | `.button.small` | **only** the standard small button (36 px, `--r-s`) - no pills or private buttons. An edit button in a row (`.ar-edit > button`) has words (*Change*) while the window is wide and only the pencil while it is narrow, so a row stays on one line; a button that **adds** something keeps its words everywhere |

- A card with **one** area has no sub-window: its content sits directly in the card.
- No loose sub-headings in a card (no `h3` with a divider line, no private `...-sec` / `...-h` classes): they were six different looks and are gone. A free heading *outside* a card is still the section label of 4b.
- **No box in a box:** inside a sub-window the rows are flat - a hairline between them, never another framed box.
- **Lines stand between things, never at the edges.** A list of rows (switches, fields, users) has its hairlines *between* the rows: **none directly under the label of the window** (or its hint or tab bar), **none after the last row at the bottom edge** of the window, none before a hint. Where *buttons* follow the list, one line separates them from it. `tools/check_ui.py` fails on a line at the top or the bottom edge. **A line never touches a field:** a switch row (it begins with its own line) right under a select or an input stands `--sp-field` (14 px) below it, like two fields do - `tools/check_ui.py` measures every line against the field above it. **Lines run through the whole window:** every hairline that separates the rows or parts of a card, a sub-window or a popup reaches from one edge of the window to the other - never only as wide as the text. The row reaches out by the padding of its window (`--bleed`: `--sp-card` in a card, `--sp-sub-pad-x` in a sub-window) and pads its content back in, so the text stays where it is; the mark of an open row fills it exactly from line to line, square, in the colour of the lines. `tools/check_ui.py` measures every line on every page against the edges of its window.
- **Nothing there yet:** a sub-window with no content shows the `.empty-state` of 4b in its compact form - the symbol in front of ONE centred sentence (*No passkey created yet.*), no dash, no empty row. The button that creates the first one follows bottom right and is called *Create* (`btn.create`, with the plus) - it keeps its word on a narrow screen (`.ar-new`).
- **One explanation per window.** At the top of a window (card or sub-window) stands ONE sentence with the info symbol: two are put together into one, or only the one that applies is shown (a notice that depends on the situation is part of that sentence's variant, not a second line). A state or a warning (*Needs an address under System*) is no explanation: it has its own line with the warning symbol. `tools/check_ui.py` fails on a second one.
- **A switch that ends its card** stands in the middle between the line above it and the card's edge: the same air above its text as below it (`tools/check_ui.py` measures it).
- The windows of a card follow the order a person needs them: the thing done most often first.
- Spacing is **measured**: `tools/check_ui.py` fails when two sub-windows one under the other are not `--sp-sub` apart or a sub-window's padding is not the token.

## 4d. The receipt card (a fill-up, a purchase)

A fill-up (*Fuel*) and a purchase (*Parts*) are shown as a **till receipt** - one card, one look, defined once (`.rcpt` in `pc-core.css`, built the same way in `fuel_page.html` and `_parts_list.html`). A fill-up is the receipt of a visit to the pump, so this look is fixed for it:

| Part | Class | Rule |
|---|---|---|
| Head | `.rcpt-head` | the date on the left, the station / shop on the right - Space Mono 12 px, muted |
| Line | `.rcpt-line` | a dashed line above it; on the left what it is (`h3`, bold: *42,8 L*, *Brake discs*), on the right **the price** `.rcpt-price` (Space Mono 15 px, bold). A noticed refuel that still waits for its receipt shows the status chip `.badge.soon` *To complete* in the place of the price |
| Details | `.rcpt-meta` | a dashed line above it; Space Mono 12 px, muted: price per unit, odometer, part number ...; a good state (*✓ Filled up completely*, *✓ Installed*) in the OK colour |
| Button | `.rcpt-acts` | *Edit* at the bottom right |
| Opened | `.rec-inline` | a tap on the card (or *Edit*) turns the **whole card into its form** - the receipt parts and the Edit button disappear. The bar at the bottom is always: **close** (✕) at the far left, then **delete** (bin), and **Save** at the right (words on a wide card, only symbols on a narrow one). A form of a fill-up starts with the **scan row**: *Scan* (the camera) on the left and *Load file* (a photo from the library or a PDF) on the right, above its fields; the odometer that is already there is never overwritten by a scan |

Rules: the price is always in the line, at the right - no second price look (no pill, no big figure). An empty value is empty, never `None` / `null`. What the car noticed on its own is marked in the entry's own data, never in the notes, and never shown to the person as text. A new look for a purchase or a fill-up is a change of `.rcpt`, not a new class.

## 5. Behaviour rules

- **Per vehicle.** Anything that belongs to a car lives under that car; only Account, Vehicles, Settings and System services are global. Vehicles are addressed by name (`/v/<name>/…`).
- **Only show what exists.** No data → no tile, no empty row, no placeholder box. A lone `-` in a text field counts as empty.
- **Switches are always on the right** - everywhere, like the settings of an iPhone (decided by the owner on 2026-11-24, not to be reopened). A switch is the last thing at the right end of its row: the text (and its hint) stands on the left, then Yes / No, then the switch. Never on the left, never loose inside a sentence, never reordered by a theme, a page or a plugin; a plugin cannot place a switch at all - its `bool` fields are drawn by the app. Every on / off choice is a `switch_row()` (or, in a list of functions, the same switch at the right end of the line). Two guards keep it: `tools/check_ui.py` measures every switch of every page in a real browser (*a switch is not at the right end of its row*), and a test in `tests/test_design_rules.py` forbids any style rule that orders, reverses or floats a switch row.
- **Destructive actions** use the confirmation dialog and say what is lost.
- **Manual now, plugin later.** Values that a plugin will deliver (range, tank level, doors, position …) are shown only when they arrive via the Plugin API; the manual entry stays as the fallback and uses the same fields.
- **Nothing online by default.** External services are opt-in and explained.
- **Texts** go into `EN` and `DE` in `i18n.py`; templates never build keys by concatenation.
- **No inline scripts or styles that need a script** (strict CSP). Behaviour lives in `static/*.js`.
- **Back and the marked entry.** On a page of ONE plugin or integration (settings, log, set-up) the header *Back* leads to the list it belongs to (*Plugins* or *Integrations*) and, on wide screens, that entry stays marked in the side bar on every page of the package. A page that has its own entry in *More* (such as Coding) marks that entry and leads *Back* to *More*.
- **Phones must not zoom.** Every text field is at least 16 px (iPhone Safari zooms into smaller text when it is touched); a grid that holds fields has `minmax(0, 1fr)` columns, so a field never pushes its box wider than the screen.

## 6. Checklist for a new page or component

1. Is there already a component for it? Use it.
2. Tokens only – no hard-coded colours, radii or spacing. A block that stands on its own on a page takes the ONE corner `--r-surface` by being added to the list in the single rule at the end of `pc-core.css` (no radius of its own); a test fails otherwise. Its first block starts level with the first card of the *More* list.
3. `page_head`, correct spacing, works at 375 / 800 / 1100 / 1280 px. On / off choices are switches at the right end of their row.
4. Empty state (the card with the symbol and one helpful sentence: `.card.empty-state`, never a bare line of text), one item, many items, very long text - and the opened state (an editor, a folded group, a chosen item) with such data, not only the empty demo.
5. EN and DE texts; icon from `icons.py`.
6. A test (`tests/`) for the behaviour, a line in both changelogs, version up.

## 7. Known duplicates to fold (technical debt)

`app.css` still carries the older "plain" rules that `pc-core.css` overrides (`.mgroup`, `.mi`, `.tile`, `.table-wrap`, `.tiles`, `.vhome …`). When you touch one of them, fold it into a single definition and delete the other.

## 8. Speed and data volume

Every page must stay fast with 15 cars and thousands of entries per car (measured: every page below ~110 ms).

- **Lists are paged** (`entities.PAGE_SIZE`, 50). Never render all rows of a table.
- **No query inside a loop.** Read once per page (`summary.service_index`, grouped counts in `about.py`) and reuse.
- **Indexes** for everything read or deleted per vehicle (`migrations_11.sql`); a new per-vehicle table gets one in its migration.
- **Automatic readings are thinned** – a plugin reporting every few seconds adds one odometer row per day (`summary.record_odometer`), tracks are drawn with at most `charts.MAX_ROUTE_POINTS` points.
- **Responses are gzip-compressed**; `/static/…?v=<version>` is cached for a year, so a changed file needs a new version number.
- Database housekeeping (`PRAGMA optimize`, log truncation) runs daily in the worker.

### Dark / light with your own colour
Besides *Classic red* there are *Light*, *Dark* and *Auto* (*Settings → System → Design*); picking one of them shows *Your colour* right below. One colour from the colour wheel is stored for the whole server (`ui.accent`); `themes.accent_css()` works out the accent family from it - `--accent`, `--accent-rgb`, `--accent-hi`, `--accent-top`, `--accent-bot`, the two hover values and `--accent-text` (white or dark, whichever stays readable on the button). The lightness is kept in a range that suits the background, and `--ok` / `--soon` / `--overdue` are never touched. The page carries the result in `<style id="accent-custom">`, frames get it in `/frame-theme.css`. Build new components only from the tokens and they follow the colour by themselves; use `--accent-text` for text on an accent surface, never a fixed white.

## 9. The design method (one way of building every page)

A page is built from these parts only - `tests/test_design_rules.py` checks the mechanical rules:

1. **Header:** every page starts with `page_head(icon, title)` (Home, the 404 page and the first language page are the only exceptions).
2. **Colours only as tokens** (section 1); no inline styles except the width of a bar; one definition per component (section 4).
3. **Tabs (`.seg-tabs`)** only for real sub-areas of one topic: *Settings* (User, Design, Region, System), *Integrations* and *Plugins* of a vehicle. Pages of a vehicle have no tab bars - they are reached from the bar or from More.
4. **Lists of records = cards** (`.rec-grid` / `.rec`): title, key facts in two columns, *Edit* folded below. No wide tables; on every width, also on a phone.
5. **Settings apply live.** A settings form carries `data-live` (or `data-theme-live`) and has **no Save button**: it saves on change; `data-reload` reloads afterwards (language). A change that is visible (design, navigation) is shown at once. Only real actions (upload, reset, delete, create) have buttons - **primary** for the one main action, plain for the rest.
6. **Destructive = red and asked first:** `.danger` (or the round red bin on a card) in the danger red of the design, always with `data-confirm`.
7. **Level first:** server-bound, user-bound or vehicle-bound (see CLAUDE.md) decides *where* a setting lives: Settings tabs, the login, or the vehicle's pages.
8. **Styles are cached for a year:** any change to a `.css` / `.js` file needs a new version number.
