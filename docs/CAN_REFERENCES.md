# CAN and Mercedes Network References

Зафиксировано: 2026-06-17.

Safari export copied into the project:

- Original zip: `data/references/safari_bookmarks_2026-06-17/original/safari_bookmarks_2026-06-17.zip`
- Extracted HTML: `data/references/safari_bookmarks_2026-06-17/extracted/`
- Filtered JSON: `data/references/safari_bookmarks_2026-06-17/can_bookmarks.json`
- Human-readable index: `data/references/safari_bookmarks_2026-06-17/can_bookmarks.md`

`data/` is intentionally ignored by git, so the project keeps the local source
material without committing proprietary/raw data. The reproducible extractor is
`tools/extract_safari_bookmarks.py`.

Regenerate the filtered index:

```bash
python3 tools/extract_safari_bookmarks.py data/references/safari_bookmarks_2026-06-17/extracted
```

## Snapshot

The current export has 707 bookmarks. The CAN/diagnostic filter currently finds
34 useful links.

Tag counts:

- `can`: 10
- `xentry`: 10
- `openport`: 8
- `j2534`: 4
- `gateway`: 3
- `mercedes-network`: 3
- `can-hardware`: 3
- `vediamo`: 3

## Important Links To Review First

Mercedes network/topology:

- `Mercedes-Benz W164. Общая сеть обмена данными`
- `Mercedes-Benz W164 | Общая сеть обмена данными | Мерседес W164`
- `CAN Gateway Mercedes E 211 — CAN Hacker`
- `Mercedes Benz CAN шина — CAN Hacker`
- `Mercedes Benz 211 кузов, CAN шина, панель приборов — CAN Hacker`

CAN hardware/tools:

- `GitHub - autowp/arduino-canhacker: CanHacker (lawicel) CAN adapter on Arduino + MCP2515`
- `mcp2515 со скоростью 83.333`
- `CAN Hacker 3.0 (CH3.X)`
- `CanHacker — Яндекс.Диск`
- `Контроллер Canny 3tiny`

Diagnostic stack:

- `Mercedes Star Diagnosis (DAS Xentry) c помощью Tactrix OpenPort 2.0 [J2534]`
- `FAQ - Xentry Pass Thru 2020.3.3`
- `Full Installation & Activation Xentry Diagnostics ... OpenPort2`
- `OPEN-PORT 2.0 RUSSIA`
- `Openport2China.xlsx`

Vediamo/CBF examples:

- `Кодировка Агилити Режима на Mercedes W164, X164 / 7G - Cbf VGSNAG2`
- `Два способа активации режима Agility ... CBF VGS4nag2 vs SeedCalc`
- `Mercedes W164 активация режимов Agility ... Vediamo`

## Content Review Notes

Проверено вручную 2026-06-17:

- `CAN Gateway Mercedes E 211 — CAN Hacker` - полезная техническая статья.
  В ней есть конкретные CAN ID (`0x058`, `0x09E`, `0x000`), скорость
  `83.333 kbit/s`, пример двухканального gateway между EIS/замком и приборной
  панелью W211, фильтры `Mask=7FF`, а также структура payload с идентификацией
  и пробегом. Это стоит разбирать дальше в отдельную таблицу CAN examples.
- `Mercedes Benz CAN шина — CAN Hacker` - короткая вводная заметка. Полезна как
  подтверждение медленной Mercedes CAN `83.333 kbit/s`, но сама по себе почти не
  дает структуры данных.
- `Mercedes-Benz W164. Общая сеть обмена данными` и зеркало
  `Mercedes-Benz W164 | Общая сеть обмена данными | Мерседес W164` - по
  заголовку и контексту это важные страницы для топологии W164/X164, но одну из
  них браузер не отдал нормальным текстом. Их надо открыть/сохранить отдельно и
  извлечь структуру сети вручную или отдельным парсером.

Вывод: в Safari export есть стоящая информация, но не все 34 ссылки одинаково
ценны. `reference_links` хранит список и фильтры, а `can_examples` хранит уже
проверенные факты: CAN speed, CAN ID, ECU pair, payload meaning, vehicle body,
source URL. Это нужно для bench-сценариев вроде замены кластера, но хранится как
пассивная справка без write/workflow действий.

## How This Feeds macDiag

`tools/build_measure_db.py` imports this filtered JSON into
`measurements.sqlite` schema v10 as `reference_links`. Reviewed CAN facts are
imported from `resources/can_examples.json` into `can_examples`.

Build/import command:

```bash
python3 tools/build_measure_db.py \
  --vsg-dir data/vsg \
  --mwg-dir data/vediamo_raw \
  --cbf-dir data/cbf \
  --references-json data/references/safari_bookmarks_2026-06-17/can_bookmarks.json \
  --can-examples-json resources/can_examples.json \
  --out data/measurements.sqlite
```

The `reference_links` table stores:

- `url`, `title`, `domain`
- `tags_json`: `can`, `mercedes-network`, `gateway`, `j2534`, `openport`, `xentry`, `vediamo`, etc.
- `vehicle_hints_json`: detected body/model hints like `W164`, `X164`, `W211`, `E211`
- `folders_json`, `sources_json`, `attrs_json`
- `source_file`: path to the imported JSON

The `can_examples` table stores reviewed passive facts:

- `vehicle`, `body`, `bus`, `speed_kbit_s`
- `can_id`, `dlc`, `data_hex`
- `source_node`, `target_node`, `direction`
- `payload_meaning`, `tags_json`, `confidence`
- `safety_note`, `notes`, `source_url`

Current reviewed seed:

- W211/E211 slow CAN between EIS and instrument cluster at `83.333 kbit/s`
- frame `0x09E`, DLC 7, cluster -> EIS, sample data `00 81 D9 B3 2C 05 E8`
- frame `0x058`, DLC 7, EIS -> cluster, sample data `00 81 D9 B3 2C 05 E8`
- frame `0x000` as IGN-ON/system-enable context in the bench example
- allowlist filters `0x058` and `0x09E` with mask `0x7FF`

Expected use in the app:

- attach Mercedes network/topology references to body/model context;
- attach J2534/OpenPort/Xentry/Vediamo references to adapter/setup help;
- later connect topology pages to ECU, gateway, connector, and pin views once
  `dist_raw`/StarFinder data is normalized.

Do not depend on live Safari bookmarks anymore. The copied export under `data/`
is now the local source for this slice.
