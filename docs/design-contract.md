# Design contract

🇬🇧 English · [🇩🇪 Deutsch](design-contract.de.md)

What stays the same in every design, on every page and in every package - the *corporate identity* and *corporate design* of Car Assistant in one place. The details of building pages are in the [design handbook](design.md); this page is the promise: **what a theme, a page of the app and a page of a package can rely on.** Tests keep it true (`tests/test_design_contract.py`).

## 1. Identity
| | |
|---|---|
| Name and slogan | **Car Assistant** - **Drive · Log · Go** (in every language, capitals in graphics) |
| Colours | red `#e2001a` (accent, the logo), green `#4ade80` (ok, the logo's other end), dark `#0d1016` (background) |
| Fonts | Space Grotesk (text), Space Mono (numbers, plates, codes) - self-hosted |
| Icons | Material Design Icons only (`icons.py`), one icon per function |
| Logo | the car in a rounded square with a red-to-green edge (`docs/logo.svg`) |
| Banner, add-on logo | the name in one line, **DRIVE · LOG · GO** below it from the C to the t of the name, the block vertically centred on the logo (`tools/make_banner.py` builds both) |
| Voice | short, friendly, no jargon; one main action per page; a text only where an icon is not enough |

## 2. Variables (the contract for themes and packages)
Every design - and every page a package shows (`kind: "frame"`, [plugins](plugins.md)) - can rely on these custom properties:

| Group | Variables |
|---|---|
| Surfaces | `--bg` `--card` `--card2` `--line` `--line2` |
| Text | `--text` `--muted` `--dim` `--strong` |
| Accent | `--accent` `--accent-rgb` `--accent-hi` `--accent-text` |
| Status | `--ok` `--soon` `--overdue` `--ok-rgb` `--soon-rgb` `--overdue-rgb` `--ok-bg` `--soon-bg` `--overdue-bg` |
| Glass and buttons | `--fg-rgb` `--glass` `--glass2` `--glass-b` `--btn-edge` `--btn-hi` |
| Shape | `--r-s` `--r-m` `--r-l` (8 / 12 / 16 px) |
| Spacing | `--sp-edge` `--sp-col` `--sp-block` (14 / 14 / 20 px) |

Use `rgba(var(--fg-rgb), .07)` for a light layer instead of white or black - light designs flip `--fg-rgb`. Never write a colour as a hex value inside a rule; it comes from a variable.

## 3. Designs (themes)
A design is one file in `static/themes/<name>.css` with the rule `:root[data-theme="<name>"] { ... }`; it sets only the variables that differ from the dark base (`default`). A light design also sets `color-scheme: light`, the surfaces, `--fg-rgb`, the glass values and the status colours. What every design must keep (tested for all of them):
- the variables of section 2 are there (from the base or the theme),
- text on the background and on cards: contrast at least **4.5 : 1**; `--muted` on cards **4.5 : 1**; `--dim` **3 : 1** on cards and on the background (the section labels stand on the page),
- the accent, `--ok`, `--soon` and `--overdue` on a card: at least **3 : 1**; `--accent-text` on `--accent`: at least **3 : 1**.

Available: *Classic red* (dark, the default) and *Light*, *Dark* and *Auto* (follows the device), each with a colour of your own - the colour is one value you pick on a colour wheel (see the design handbook). Setting a design per car overrides the server's. A theme file of your own in the data folder works the same way.

## 4. Components (one definition each)
| Component | Class | Rule |
|---|---|---|
| Button | `button`, `.button`, `.ghost-btn` | glass, 44 px; `.small` 36 px; `.primary` (red glass) is the one main action of a page, docked right; `.danger` is a red outline |
| Icon button | `.icon-btn`, `.ib`, `.eq-i` | round or square, always with an outline; the text stays for screen readers (`.sr`), no hover tooltips |
| Card | `.card` | glass, 18 px inside, `--r-l`, 14 px between cards |
| Record card | `.rec` in `.rec-grid` | date, title, facts, a thin divider and a small *Edit* button docked right; two columns on a wide screen, one on a phone |
| List | `.rec-grid` + `.rec-month` | a batch of 10 / 25 / 50 cards (the person's choice), the next batch loads while scrolling, a heading per period (Today, Yesterday, This week, Last week, then the month) |
| Page header | `page_head()` | back, icon, title, car name, actions on the right; the same height on every page |
| Form fields | `input` `select` `textarea` | 48 px, 16 px text, 8 px corners |
| Chip, badge | `.chip`, `.badge` | pills; `.ok` `.soon` `.overdue` only for status |
| Guide buttons | `.step-nav` | *Back* left, the one main action right, one line |

## 5. Page patterns
- **List page** (service, parts, fuel, appointments ...): header with the add button at the right, a search field, the cards under period headings, the next batch on scroll.
- **Settings page:** header, tabs, cards with a heading (18 px) and a hint (14 px).
- **Guide step:** step bar, a card with the explanation, the choices, `.step-nav`.
- **Package page** (`kind: "frame"`): the usual header with the package's version on the right, the package's own page below it, using the kit (`/frame-kit.css`) so it matches the design.

## 6. Rules that always apply
Light buttons, **one line**; one main action per page; settings that change something visible apply at once (no Save button); no inline script (the CSP forbids it); every text in English and German; **switches always sit at the right end of their row, like on an iPhone** (the app draws every switch; a plugin cannot move one); a switched-off function shows nothing, raises nothing.
