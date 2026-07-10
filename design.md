# macDiag — Design System

A dark, dense, technical UI for an OBD-II / UDS diagnostic tool for Mercedes-Benz
cars across the whole CBF library (~69 chassis, from the A-Class through E/S,
coupes, roadsters, SUVs and vans — no single platform is privileged). The
aesthetic is an instrument-panel-meets-developer-tool:
GitHub-dark palette, calm neutrals, a single blue accent, and semantic status
colors (green/amber/red) reserved for vehicle/connection state. Information
density is high; chrome is minimal; monospace is used for codes and raw data.

Extracted from the live product (`frontend/style.css`). Source of truth.

## Brand & voice

- **Product**: macDiag — web OBD-II/UDS diagnostics over a Tactrix Openport 2.0.
- **Tone**: precise, terse, engineer-facing. No marketing gloss. Russian-first UI
  with EN/DE technical terms preserved.
- **Feel**: a quiet workshop terminal. Dark, flat, sharp 1px borders, no shadows,
  subtle hover states, fast.

## Color tokens

Dark theme only (GitHub-dark derived).

| Token | Hex | Use |
|---|---|---|
| `bg` | `#0d1117` | App background, inset wells, code blocks |
| `panel` | `#161b22` | Cards, gauges, inputs, raised surfaces |
| `panel2` | `#1c222b` | Secondary surface, hover, chips |
| `line` | `#2a2f37` | Primary 1px borders |
| `line2` | `#21262d` | Hairline dividers (table rows, header, tabs) |
| `txt` | `#e6edf3` | Primary text |
| `txt2` | `#adbac7` | Secondary text, headings |
| `muted` | `#8b949e` | Labels, captions, hints |
| `accent` | `#1f6feb` | Primary action, focus, active tab/segment |
| `accent2` | `#388bfd` | Links, code, inline emphasis |
| `ok` | `#3fb950` | Connected / no faults / online |
| `danger` | `#f85149` | Disconnected / fault / destructive |
| `warn` | `#d29922` | Caution / present-but-no-data / DTC badge |
| `uds` | `#388bfd` | Protocol tag: UDS |
| `kwp` | `#d29922` | Protocol tag: KWP |

**Semantic surface tints** (border + translucent fill, always paired):
- success: fill `#11271a`, border `#1f4a2c`
- danger: fill `#2a1416`, border `#4a1f22`
- warn: fill `rgba(210,153,34,.12)`, border `#4a3a12`
- accent-soft: `color-mix(in srgb, accent 14%, panel2)` (selected chip)

## Typography

- **Sans (UI)**: `-apple-system, "SF Pro Text", "Segoe UI", Roboto, sans-serif`
- **Mono (codes/data)**: `ui-monospace, "SF Mono", Menlo, monospace`
- Base: `14px / 1.5`.

| Role | Size | Weight | Color | Notes |
|---|---|---|---|---|
| Brand | 18px | 500 | txt | letter-spacing .2px |
| Section heading `h3` | 14px | 500 | txt2 | margin 22px top / 10px bottom |
| Card label | 11px | 400 | muted | UPPERCASE, letter-spacing .5px |
| Big value (`kv`, metric, gauge value) | 22–24px | 500 | txt | right-aligned in gauges |
| Body | 14px | 400 | txt | |
| Secondary / hint (`dim`, `muted`) | 12px | 400 | muted | |
| Caption / sub | 10–11px | 400 | muted | ellipsis on overflow |
| Code / raw hex | 12px | 400 | accent2 | mono |
| Table header | 11px | 500 | muted | UPPERCASE, letter-spacing .5px |

## Shape, spacing, motion

- **Radius**: 6px (small wells/cells) · 8px (buttons, inputs, small cards) ·
  10px (cards, gauges, ECU cards) · 12px (primary card) · 14px (chips) ·
  20px (pills, badges) · 50% (status dots, spinner).
- **Borders**: 1px solid `line` everywhere; dividers use `line2`. No shadows.
- **Spacing**: grid/flex gaps 6–16px; control padding `8px 14px`; card padding
  `14px 16px`; page padding `18px 24px`.
- **Motion**: hover `filter: brightness(1.08)`; active `transform: scale(.985)`;
  focus → border becomes `accent`; spinner 0.6s linear; toast 0.2s slide+fade.
- **Layout**: responsive auto-fill grids (`minmax(150–280px, 1fr)`); the overview
  splits into a left ~30% identity sidebar + right work area, collapsing to one
  column under 860px.

## Components

### Buttons
- **Primary**: bg `accent`, text `#fff`, radius 8px, padding `8px 14px`, 13px.
  Hover brightens, active scales down, disabled `opacity .4`.
- **Ghost**: transparent, 1px `line` border, text `txt2`; hover fills `panel2`.
- **Danger**: bg `danger`.
- **Link button**: no bg, text `accent2`, underline on hover.
- **Segmented control** (`seg`): inline group, 1px `line`, rounded 8px; active
  segment bg `accent`/white; used for sim↔hw mode.

### Inputs & selects
- bg `panel`, 1px `line`, radius 8px, padding `8px 10px`, 13px. Focus → border
  `accent`, no outline. Textarea inherits font, vertical resize.

### Card
- bg `panel`, 1px `line`, radius 12px, padding `14px 16px`. Optional UPPERCASE
  `clabel` (muted) on top, big `kv` value below, `dim` sub-line.
- `cards3`: responsive grid of equal cards (`minmax(230px,1fr)`).

### Pills & badges (status)
- **Badge**: 11px UPPERCASE, 1px `line`, radius 20px, muted (e.g. "SIM").
- **Pill**: dot + label, radius 20px; `.on` = green tint, `.off` = red tint.
  Used for connection/OBD-power state.
- **Status dot**: 8px circle, `muted`/`ok`/`danger`.
- **Protocol tag** (`proto`): tiny rounded tag, 11px/500 — `uds` blue-on-#11233b,
  `kwp` amber-on-#2e2410.

### Tabs
- Horizontal, bottom-border container (`line2`). Buttons are text-only `muted`;
  hover → `txt2`; active → `txt` with a 2px `accent` bottom border.

### Metric strip
- Auto-fit grid of `metric` tiles: bg `panel`, radius 10px; muted label, 22px
  value, muted hint. Used for "ECUs online / DTC count / protocol".

### Gauge tile (live value)
- bg `panel`, 1px `line`, radius 10px, padding `12px 13px`. 2-line clamped label
  (left), big right-aligned `value` + muted `unit`, tiny `sub` (норма/status).
- **Load-collective block**: full-width strip (`grid-column: 1/-1`) holding a
  wrapping row of small mono `bcell` cells (inset `bg`, 1px `line`, radius 5px).

### ECU card (scan grid)
- Auto-fill grid (`minmax(220px,1fr)`). Card with a status dot + name + meta
  (protocol tag, CAN id); `.off` dims; a `faults` badge (amber on #2e2410) shows
  DTC count. Hover → accent border. Clickable → drill into the ECU.

### Chips & flow
- **Chip**: 11px, `txt2` on `panel2`, 1px `line`, radius 14px. `.hot` = relevant
  match: `txt`, accent border, accent-soft fill (used to highlight DTC-relevant
  groups).
- **Flow step**: 12px `step` on `panel2` with an `accent` border, joined by muted
  `→` arrows — a guided check-list.

### Tables
- Full-width, collapsed borders, `line2` row dividers. UPPERCASE muted headers.
  Row hover tint `panel`. Code cells in mono `accent2`. Collapses to stacked
  cards on narrow screens (dictionary view).

### Coverage banner
- Inline pill-row: big bold number + muted label + detail; tinted by state
  (`ok`/`warn`/`bad`) using the semantic surface tints.

### Diagnostic media
- Schematic/photo grid of 200px figures (caption bar + image on white well),
  click → full-screen lightbox over an 78%-black backdrop.

### Toast
- Fixed bottom-center, danger-tinted, slide-up + fade; transient network errors.

### Debug drawer
- Sticky bottom panel: a bar + a mono log (`bg` well, 11.5px) with colored lines
  (`ok` green, `nrc` amber, `err` red, `to` muted) for request/response traffic.

## Pages & screens (what each does)

The app is a single-page tool with a top header and 9 tabs. The mental model is
a workshop session: connect the adapter → identify the car → look at state →
read live values → chase faults → (rarely) code.

**Header (always visible).** Brand "macDiag"; a sim↔hw segmented control (the
emulator vs the real Tactrix Openport); a connection pill with a status dot and
battery voltage; a busy spinner. State, not navigation.

1. **Обзор — Overview (home).** Identify the car and see overall state at a
   glance. Two columns:
   - *Left ~30% identity:* a vehicle silhouette/photo (by chassis), the VIN
     (auto-read on connect), model/engine/equipment decoded from the gateway,
     plus adapter (voltage, mode) and bus (OBD power, ISO15765) cards.
   - *Right quick-poll:* the auto-detected chassis as a chip (manual dropdown,
     grouped by model family, only as a fallback); "Опросить шлюз" + "⚡
     Сканировать"; a metric strip (ECUs online / DTC total / protocol); and a
     grid of ECU cards (status dot, protocol tag, CAN id, fault count) — click
     one to drill into its faults.

2. **Live data.** Watch real, scaled physical values. Group selection comes
   first (ЭБУ → measurement group); selected group renders as gauge tiles with
   units, a norm range, and the read source (scaled/enum/raw or N/A + reason).
   Load-collective tables render as one wide strip of cells. Below: a generic
   engine/OBD PID stream (start/stop), then runnable service procedures.

3. **Ошибки — Faults (DTC).** Pick a module, read its trouble codes
   (code · status · description · raw). Click a code for a DAS-style drill-down:
   probable causes, a step check-list (flow), the **measurement groups most
   relevant to that fault** (ranked, highlighted) plus the rest, and real
   StarFinder/WIS schematics & documents (open in a lightbox).

4. **Модули — Modules.** The full ECU catalog parsed from the CBF library across
   chassis: name, protocol, CAN request/response ids. Filter/search; jump to a
   module's faults, coding, or identification.

5. **Кодирование — Coding.** Variant coding (engineer-only): read an ECU's
   configuration, decode it into named option fragments, change one option, and
   write it back — with a backup of the current value and explicit confirmation.

6. **Программирование — Programming.** Read-only software-version and CFF
   catalogue/inspection surface. Flash writing remains intentionally disabled.

7. **Журнал — Audit.** Read-only append-only history of ECU-changing operations:
   success, error, and server-blocked DTC clear / coding attempts, with target,
   identifiers, security level, backup status, and error reason.

8. **Справка — References.** A local knowledge layer: searchable CAN / Mercedes
   network bookmarks, and verified passive **CAN bus examples** (bus speed, CAN
   id, sample payload, meaning, safety note) for bench/replacement scenarios.

9. **Словарь — Dictionary.** A translation editor to curate RU/EN/DE labels for
   jobs and measurement groups — the localization layer over the normalized data.

## Operational logic — faults · coding · programming

These three flows are the dangerous/expert end of the app. The UI must make the
read→understand→act path obvious and the risk legible: read-only is the default,
every write is explicit, reversible, and logged.

### Faults (DTC) — read & guided diagnosis
- **Read.** Pick a module → query its fault memory (UDS `0x19` / KWP `0x18`).
  Each row: code · status · description · raw bytes. The whole read is one
  request; the panel shows the *outcome*, not progress.
- **States to render distinctly:** `ok` (answered — list may be empty = "no
  faults"), `present` (on the bus but won't report — NRC), `no_response`,
  `adapter_error`. Empty-but-ok is a success (green), not an error.
- **Drill-down** (click a code): probable causes → a check-list flow → the
  **measurement groups ranked by relevance to this fault** (highlighted "hot"
  chips first, rest after) → StarFinder/WIS schematics & docs in a lightbox.
  The drill turns a code into "what to look at next", linking straight into Live
  data for the relevant group.
- **Clear** is a separate destructive action (danger button): it erases stored
  faults and must read as consequential, never adjacent to a benign control.

### Variant coding — read · decode · change · write (with a net)
- **Read.** List coding domains → read the ECU's coding DID → decode it into
  named **option fragments**, each showing the current value among its choices.
  Reading is always safe.
- **Change.** The user picks one option in one fragment; the new coding bytes are
  computed locally (the chosen option's stored bit-pattern is written into the
  fragment — no free-form byte editing).
- **Write = explicit + backed up + logged.** A write (`POST /api/coding/apply`)
  first **reads and records the current value to a backup journal**, then writes
  the new coding (`2E`/WriteDataByIdentifier), acquiring security access if the
  service requires it. The backup is non-blocking but always attempted; a
  rollback journal (`/api/coding/backups`, newest-first) is available for manual
  restore. Surface the backup + security level in the result.
- **Posture.** Coding is engineer-only. The button is deliberate ("apply"), the
  result shows what changed, the LID, the security level used, and the backup id.

### Programming (flashing) — read-only today, full write is coming
- **Today (concept/scaffold):** identify and **catalogue CFF flash images**
  (part number, software, version, size) and read an ECU's identification DIDs
  (current part number / software version) over diagnostics, so you can *compare*
  what's installed vs. what's available. No writes yet.
- **Planned — full ECU programming (flash write).** This is a deliberate next
  phase, not a permanent limitation. The flash mode will be a guarded,
  hardware-only, audited, single-purpose flow: battery/voltage + diagnostic
  session preconditions, a clear progress/verify/resume path, and a hard
  confirmation — because an interrupted flash can brick an ECU. Design it as an
  isolated "programming" mode distinct from everyday diagnostics, so the UI can
  grow into real writing without ever making it feel casual.

## Principles

1. **Dark, flat, 1px.** No shadows or gradients except the faint vehicle-image
   well. Depth comes from `bg < panel < panel2`.
2. **One accent.** Blue (`accent`) marks the single primary action / focus /
   active state. Don't introduce new hues for emphasis — use weight and the
   neutral ramp.
3. **Color = state, not decoration.** Green/amber/red mean connection or fault
   state only. Always pair a tint with its border.
4. **Mono for machine data.** Codes, CAN ids, hex payloads, raw responses.
5. **Density over whitespace.** Compact paddings, auto-fill grids, terse labels.
   UPPERCASE muted labels caption every value.
6. **Responsive by collapse.** Multi-column grids and the overview split fold
   into a single column on small screens; nothing is hidden.
