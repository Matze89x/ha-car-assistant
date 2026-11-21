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
| Radius | `--r-s` `--r-m` `--r-l` | 8 / 12 / 16 px – small (inputs inside cards, chips), medium (buttons, tiles, fields), large (cards, lists) |
| Circles | `999px` | **only** for icon buttons, pills, badges, switches, the tab bar's outer shape follows `--r-l + 5px` |
| Spacing | `--sp-edge` `--sp-col` `--sp-top` `--sp-head` `--sp-block` | 14 / 14 / 18 / 16 / 20 px – edge, column gap, first element from the top, below the page header, between blocks |
| Heights | `--head-h` `--lab-h` | 44 px page header row, 25 px small group label |
| Fonts | Space Grotesk, Space Mono | Mono for plates, codes, sizes, numbers in forms |
| Icons | Material Design Icons only | `icons.py`, rendered with `icon('name', size)`; no emojis, no other sets |

Nested radii: inner = outer − padding (a 32 px chip in a 16 px list row with 8–12 px padding has 8 px).

**Fixed scales - nothing in between.** Type: 10 / 11 / 12 / 13 / 14 / 15 / 16 / 18 / 20 / 24 / 32 px (labels 11, body 15, buttons 15, fields 16, card titles 18, page title 24). Corners only as `--r-s`, `--r-m`, `--r-l` or `999px`. Controls: fields 48 px, buttons 44 px (small 32 px), icon buttons 40 px.

**Light buttons, one line (standing rule).** Every secondary action - save inside a panel, delete, cancel, add, edit - is a *light* button (`.ghost-btn` / outlined, `.danger` is outlined red, never a filled block), and a row of buttons always stays on ONE line (`flex-wrap: nowrap`, labels short). Only the single main action of a page may be `.primary`.

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

Next to the *More* list the first element of the page starts on the same line as the first card of the list.

## 4. Components

| Component | Class / macro | Notes |
|---|---|---|
| Card | `.card` | glass, `--r-l`, 18 px padding, no coloured bar |
| Home widget | `widget()` macro → `.wd`, `.wd-slot` | one uniform tile: icon chip, title, value (`.wd-v`), sub line (`.wd-s`); size `s` (half row) or `m` (full row); a template in `templates/widgets/` renders nothing when there is no data |
| List row (More, settings) | `.mgroup` > `.mi` | icon chip `.mi-ic.c1…c7`, title `.mi-t`, hint `.mi-v`, chevron |
| Icon chip | `.mi-ic.cN` | 32 px, gradient per colour; colours are part of the module (`CHIP` in `nav_web.py`) |
| Buttons | `button`, `.button`, `.primary`, `.danger`, `.small` | one glass system (translucent fill, light top edge): 44 px / `--r-m`; `.primary` = red glass (the one main action), `.danger` / `.warn` = red outline, `.small` = 36 px / `--r-s`; `.ghost-btn` on a link, label or button has the same look; only theme tokens are used, so every design (also your own theme file) recolours it |
| Icon button (circle) | `.icon-btn` (+ `.back-btn`, `.cur-switch`, `.round-del`, `.wd-eye`, `.wd-grip`, `.vsw-x`) | 40 px circle (36 / 34 for small ones) – one rule |
| Add bar | `details.add-card` | collapsed "+ Add" bar above a list; the form opens inside |
| Empty state | `.card.empty-state` | icon, one sentence that says what to do |
| Fields | `input`, `select`, `textarea`, `.tf-field` / `.tf-l` | uppercase 11 px label above, 48 px fields, example values as placeholders (neutral, never a brand) |
| Choice tiles | `.season-pick` / `.sp` | big selectable tiles with an icon instead of a drop-down for 2–4 options |
| Switch | `.switch` | on = accent |
| Chips / badges | `.badge`, `.pos-chip`, `.schip` | pills (`999px`), status colours only |
| Info page | `.about-hero`, `.about-stats`, `.about-car` | hero card (logo, name, version), figure tiles, then one card per car with rows (icon chip, name, small text, badges) – see the About page |
| Car picture / video | `.hero-car.soft`, `.hero-media` | photos and videos fade out on all sides; a video plays once and rests on its last frame (`static/media.js`); library page `media.html` with thumbnails, "in use" badge, delete x |
| Pager | `nav.pager` | long lists show 50 records per page with Previous / Next and the total |
| Dialog | `dialog.vsw` (+ `#cdlg` for confirmations) | blurred backdrop, `--r-l` card; destructive actions always ask (`data-confirm`, `data-confirm-ok`) |
| 404 / errors | `error.html` | big gradient number, one sentence, two buttons |

## 5. Behaviour rules

- **Per vehicle.** Anything that belongs to a car lives under that car; only Account, Vehicles, Settings and System services are global. Vehicles are addressed by name (`/v/<name>/…`).
- **Only show what exists.** No data → no tile, no empty row, no placeholder box. A lone `-` in a text field counts as empty.
- **Destructive actions** use the confirmation dialog and say what is lost.
- **Manual now, plugin later.** Values that a plugin will deliver (range, tank level, doors, position …) are shown only when they arrive via the Plugin API; the manual entry stays as the fallback and uses the same fields.
- **Nothing online by default.** External services are opt-in and explained.
- **Texts** go into `EN` and `DE` in `i18n.py`; templates never build keys by concatenation.
- **No inline scripts or styles that need a script** (strict CSP). Behaviour lives in `static/*.js`.

## 6. Checklist for a new page or component

1. Is there already a component for it? Use it.
2. Tokens only – no hard-coded colours, radii or spacing.
3. `page_head`, correct spacing, works at 375 / 800 / 1100 / 1280 px.
4. Empty state, one item, many items, very long text.
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
