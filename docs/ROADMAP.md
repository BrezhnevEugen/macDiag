# macDiag roadmap

Зафиксировано: 2026-06-16.

Этот план не включает локализацию. Локализация идет отдельным слоем поверх уже
нормализованных данных.

## Текущее состояние

- Сырье StarFinder/Vediamo/dist лежит рядом с проектом в `data/`.
- `.mwg/.vsg` импортируются в локальную `data/measurements.sqlite`.
- Backend сначала читает `MACDIAG_MEASURE_DB`, raw-файлы являются fallback.
- Live data UI уже показывает группы измерений и сервисные процедуры.
- StarFinder media подключен к диагностическому контексту.
- Прошивки остаются снаружи проекта; внутри есть только индекс внешних файлов.
- Safari export с CAN/Mercedes network ссылками скопирован в `data/references/`;
  карта и дальнейшие шаги зафиксированы в `docs/CAN_REFERENCES.md`.

## Главная линия работ

Цель: превратить импортированные группы `.mwg/.vsg` из списка job-имен в реальные
диагностические dashboards, которые читают ЭБУ и показывают физические значения.

## Этап 1. Связать measurement jobs с CBF DiagService

Что делаем:

- Для каждого `services.job` ищем одноименный `DiagService` в CBF соответствующего
  ЭБУ.
- Сохраняем в нашу базу request bytes, SID/LID/DID, security level и описание из CBF.
- Добавляем таблицу/поля для нормализованного каталога диагностических сервисов.
- Runtime читает request bytes из `measurements.sqlite`, а не парсит CBF на каждый
  запрос.

Критерий готовности:

- Для выбранного ECU видно процент покрытия: сколько job из `.mwg/.vsg` найдено в CBF.
- `GET /api/measure/group` отдает для каждого найденного job `req`, `sid`,
  `identifier`, `sec_level`, `diag_description`.
- На hardware `read_values()` может отправить реальный request bytes без обращения к
  raw CBF.

## Этап 2. Разобрать output-presentation из CBF

Что делаем:

- Найти и распарсить выходные параметры `DiagService`: raw bytes, тип данных,
  длина, порядок байт, signed/unsigned.
- Извлечь scaling/формулы, единицы измерения, enum/value maps и статусные значения.
- Сохранить это в нормализованные таблицы `service_outputs` и `value_maps`.
- Добавить fallback: если scaling неизвестен, показывать raw значение и помечать
  источник как `raw`.

Критерий готовности:

- Для типовых `DT_` jobs backend возвращает физические значения: bar, deg C, rpm,
  %, g, mg/stroke и т.п.
- В UI видно источник значения: `scaled`, `enum`, `raw`.
- Тесты покрывают минимум несколько UDS/KWP ответов с известным expected value.

## Этап 3. Реальный Live data pipeline

Что делаем:

- Для группы измерений пакетно читать реальные параметры с ЭБУ.
- Ограничить частоту polling и не запускать небезопасные routine/action jobs в
  live-read.
- Добавить ошибки чтения на уровне отдельного параметра, чтобы один проблемный job
  не ломал весь dashboard.
- Улучшить simulator: использовать те же request/response/scaling paths, что и
  hardware.

Критерий готовности:

- Live dashboard работает на реальном ЭБУ для хотя бы одного дизельного блока.
- Неизвестные/непрочитанные параметры видны как `N/A` с причиной.
- Debug log показывает request/response по каждому параметру.

## Этап 4. DTC -> диагностический контекст

Что делаем:

- Связать DTC с релевантными группами измерений, процедурами, StarFinder media и
  документами.
- Построить простую ранжировку: код ошибки, ECU, job names, ключевые термины,
  StarFinder/DWF/doc совпадения.
- На экране ошибки показывать рекомендуемые проверки.

Критерий готовности:

- Клик по DTC дает список полезных групп/параметров, а не просто общий набор ECU.
- StarFinder картинки и документы открываются из этого контекста.

## Этап 5. dist_raw -> собственная база схем/разъемов

Что делаем:

- Разобрать мелкое сырье из `data/dist_raw`: ETN/CDI/BMREF/DWF/таблицы/доки.
- Вытащить связи: ECU -> connector -> pin -> signal -> wire -> component.
- Сохранить это в нашу SQLite-базу, не ссылаться на внешний диск для мелких данных.
- Импортировать CAN/Mercedes reference links из Safari export как локальный
  справочный слой `reference_links`, чтобы связать общую топологию CAN,
  gateway/J2534/OpenPort/Xentry/Vediamo материалы с моделью, ECU и будущими
  экранами разъемов.

Критерий готовности:

- По ECU можно открыть разъемы, пины и связанные схемы.
- По DTC/параметру можно показать релевантный пин/цепь, если связь найдена.

## Этап 6. Сервисные процедуры

Что делаем:

- Разделить наблюдаемые data/adapt jobs и исполняемые routine/action jobs.
- Сделать безопасный runner для `RT_`, `FN_`, `ON_`, `OFF_`, `ST_`.
- Для записывающих процедур добавить подтверждения, режим hardware-only,
  журнал действий и защиту от случайного запуска.

Критерий готовности:

- Сервисные процедуры не запускаются из live polling.
- Любой write/routine шаг требует явного действия пользователя и пишется в audit log.

## Этап 7. Flash/read-only catalog

Что делаем:

- Оставить прошивки на внешнем диске или отдельном хранилище.
- Внутри проекта держать индекс: ECU, part number, software, версия, путь, размер.
- Добавить поиск/сравнение версий.

Критерий готовности:

- Можно найти подходящие CFF/SMR/flash-файлы по ECU/part/software.
- Никакой записи/прошивки на этом этапе.

## Ближайший следующий шаг

Начать с этапа 1:

1. [x] Расширить `tools/build_measure_db.py`, чтобы он при наличии `data/cbf`
   строил mapping `job -> CBF DiagService`.
2. [x] Добавить в `measurements.sqlite` request metadata для services.
3. [x] Обновить `backend/mb/measurements.py`, чтобы `get_group()` отдавал
   request metadata из DB.
4. [x] Добавить coverage-команду/тест: сколько `.mwg/.vsg` jobs реально найдено
   в CBF.

Состояние после первого инкремента этапа 1:

- `measurements.sqlite` schema v3 содержала таблицу `diag_services`.
- `GET /api/measure/group` возвращает для найденных job `req`, `sid`,
  `identifier`, `sec_level`, `diag_description`.
- `GET /api/measure/groups` возвращает `coverage` по выбранному ECU.
- `tools/measure_diag_coverage.py` показывает покрытие из локальной DB.

Состояние после второго инкремента этапа 1:

- Во вкладке Live data показывается CBF coverage для выбранного ЭБУ.
- `diag_services` хранит полный локальный каталог CBF DiagService по
  импортированным ЭБУ, а не только exact-match строки.
- `tools/measure_unmatched_jobs.py` показывает unmatched job'ы и кандидатов из
  CBF-каталога без автоматической подмены в runtime.
- На текущей локальной базе `CRD3_DEV`: 1888 строк измерений, 1338 exact-match
  строк, 550 unmatched строк, 178 distinct unmatched job; из них 120 имеют
  strong candidate после нормализации имен вроде `IO0352 -> IOC352`.

Состояние после третьего инкремента этапа 1:

- `measurements.sqlite` schema v4 содержит `diag_service_matches`:
  `services.job -> diag_services.qualifier` с `match_kind`, `rule`,
  `confidence`.
- Включено первое reviewed normalization rule: только read-only `DT_` job,
  только `IO0/IOF/IOD -> IOC`, только если CBF candidate имеет read request
  `21/22`.
- Backend/API и coverage используют `diag_service_matches`; service item
  дополнительно отдает `diag_qualifier`, `diag_match_kind`,
  `diag_match_rule`.
- На текущей локальной базе `CRD3_DEV`: 1888 строк измерений, 1338 exact-match,
  350 normalized, 200 unmatched, coverage 89.4%.

Состояние после четвертого инкремента этапа 1:

- Hardware `read_values()` имеет последний read-only guard перед
  `client.raw_request()`.
- На hardware отправляются только `DT_` job с SID `21/22`; request `2E/2F/30/31`
  и прочие остаются в базе, но не уходят на адаптер из Live data.
- API values возвращает `read_status`, `read_reason`, `read_req`, `read_sid`;
  UI показывает, если запрос был заблокирован.
- На текущей локальной базе из 22577 matched rows безопасно для hardware polling
  20546 rows; для `CRD3_DEV` из 1688 matched rows безопасно 1499.

Состояние после первого инкремента этапа 2:

- `measurements.sqlite` schema v5 содержит таблицу `service_outputs`.
- CBF parser вытаскивает inline `PRES_*` qualifier из `DiagService` и сохраняет
  его рядом с нашим `diag_services` каталогом.
- Для части `PRES_*` грубо определяются `raw_type` и `byte_len`
  (`UBYTE/UWORD/ULONG/...`, ASCII/bytes/hexdump); формулы и единицы ещё не
  разобраны.
- `GET /api/measure/group` отдает `output_presentation`, `output_raw_type`,
  `output_byte_len` и `value_source=raw` для найденных service outputs.
- `tools/measure_diag_coverage.py` показывает output/rawtype coverage. На текущей
  локальной базе: `CRD3_DEV` имеет 1619 output rows из 1688 matched rows, из них
  1256 с raw type; `CEPC_MFA` имеет 527 output rows из 545 matched rows.

Состояние после второго инкремента этапа 2:

- `measurements.sqlite` schema v6 сохраняет unit/formula из очевидных
  `PRES_CM_*` qualifier names: например `BIN7_BAR_UWORD -> x / 128, bar`.
- Это явно помечено как `source=cbf_diag_inline+presentation_name`, чтобы не
  смешивать эвристику с будущим полным Caesar presentation parser.
- Hardware `read_values()` применяет только простые проверяемые формулы `x` и
  `x / N`; неизвестные формулы остаются `raw`.
- `GET /api/measure/groups` и `tools/measure_diag_coverage.py` показывают
  `unit_rows` и `formula_rows`.
- На текущей локальной базе: всего `service_outputs` 189343, `raw_type` 124438,
  `unit` 30109, `formula` 10515. Для `CRD3_DEV`: 573 unit rows и 105 formula
  rows среди 1688 matched rows.

Состояние после третьего инкремента этапа 2:

- `measurements.sqlite` schema v7 сохраняет линейные Caesar presentation records,
  найденные рядом со вторым `PRES_*` блоком: `kind=4`, `method=0x30`,
  `factor`, `offset`.
- Для таких записей `source=cbf_diag_inline+cbf_presentation_record`, чтобы
  отличать реальные conversion records от qualifier-name эвристики.
- Hardware `read_values()` применяет строго распознанные формулы `x`, `x / N`,
  `x * F` и `x * F +/- O` без `eval`.
- Примеры из `CRD3_DEV`: `PRES_5017_IN_Engine_cycle_speed_UWORD -> x * 0.25`,
  `PRES_6043_P_T_Dpf_soot_mass_ULONG -> x * 0.01 - 50`.
- На текущей локальной базе: всего `service_outputs` 189343, `raw_type` 124438,
  `unit` 30109, `formula` 84626, из них 76311 от `cbf_presentation_record`.
  Для `CRD3_DEV`: 573 unit rows и 596 formula rows среди 1688 matched rows.

Состояние после четвертого инкремента этапа 2:

- `measurements.sqlite` schema v8 классифицирует non-scalar presentation names:
  `PRES_bool_1bit`, `PRES_bool_1bit_inverted`, `PRES_BCD_N`,
  `PRES_BLK*`, `PRES_HexDump_N`.
- Runtime decode добавил безопасные одиночные случаи: bool formulas
  `x != 0` / `x == 0`, BCD payload, ASCII payload; block/hexdump остаются hex.
- На текущей локальной базе: `raw_type` 124957, `formula` 85955; всего найдено
  `block` 278, `bool` 93, `bcd` 1236, `hexdump` 4505 service outputs.
- Для `CEPC_MFA`: rawtype coverage вырос с 10 до 459 rows, formula coverage до
  252 rows среди 545 matched rows; оставшиеся основные типы - кастомные
  `PRES_Tsl...`, `PRES_GLPS...`, `PRES_IN_Battery_voltage` и полноценный разбор
  `PRES_BLK*` таблиц.

Состояние после пятого инкремента этапа 2:

- `measurements.sqlite` schema v11 расширяет `presentation_meta()` для простых
  DOP/CM/name-based presentations без полного Caesar layout parser.
- Добавлено распознавание `NByteDump`, `NByteBcd`,
  `DOP_IDENTICAL_UINT/INT_*_Bytes`, `PRES_CM_*_BIN/DEC_*_<byte_len>`,
  `Session_Type_7Bit`, `Bit_ja/Bit_True/...`, а также unit tokens
  `Volt/Volts`, `Cels/Celsius`, `hPa`.
- Глобально `service_outputs`: `raw_type` вырос до 147304, `unit` до 38698,
  `formula` до 92068. Для `CRD3_DEV`: rawtype 1360, formula 697 среди 1688
  matched rows.
- Для `CEPC_MFA` этот инкремент почти не меняет покрытие (`rawtype` 461,
  `formula` 252), потому что остаток теперь в основном кастомные application
  presentations: `PRES_TslPosnSnsrVolt_Volt_App`, `PRES_APP_DATASET_DC_APV`,
  `PRES_GLPS_Adap_Mode`, `PRES_GLZP_Err_Mode_App`, `PRES_IN_Battery_voltage`.

Состояние после шестого инкремента этапа 2:

- `measurements.sqlite` schema v13 распознает Caesar range-linear presentation
  records: `kind=4`, `method=0x33`, `min_raw/max_raw`, `factor`, `offset`, а
  также compact enum records (`kind=8/12/...`, `method == kind + 0x0E`).
- Для `method=0x33` parser выводит `raw_type/byte_len` из диапазона raw-значений
  и сохраняет `source=cbf_diag_inline+cbf_presentation_range_record`.
- Для enum-record parser выводит `raw_type/byte_len`, `scale_kind=enum` и
  намеренно не проставляет formula, пока не сохраняем labels/value-map.
- Добавлен unit token `Voltage -> V`.
- Примеры из `CEPC_MFA`: `PRES_IN_Battery_voltage -> x * 0.0078125 V`,
  `PRES_TslPosnSnsrVolt_Volt_App -> x * 0.001221 V`,
  `PRES_GLPS_Adap_Mode -> ubyte enum`.
- Глобально `service_outputs`: `raw_type` вырос до 157336, `unit` до 38907,
  `formula` стало 94234 после снятия небезопасных bool formulas с enum-record.
  Для `CEPC_MFA`: rawtype 508, formula 137 среди 545 matched rows.
- Следующий слой для enum - сохранить labels/value-map; `PRES_BLK*` таблицы
  остаются отдельной layout-задачей.

Состояние после седьмого инкремента этапа 2:

- `measurements.sqlite` schema v14 добавляет `service_outputs.value_map_json`.
- Compact enum records теперь сохраняют CTF labels/value-map. Пример:
  `PRES_GLPS_Adap_Mode -> [{0: Nein}, {1: Ja}]`,
  `PRES_DTM_Gen_Mode_T -> Diagnosemodus aus/ein`.
- Backend/API отдает `output_value_map` для параметров и помечает такие значения
  как `value_source=enum`; hardware decode может заменить raw integer на label.
- На текущей локальной базе: `output_value_maps=11704`, `raw_type=157336`,
  `unit=38907`, `formula=94215` после снятия ложных scalar formulas с
  `PRES_BLK*`. Для `CEPC_MFA`: rawtype 508, formula 134 среди 545 matched rows.
- `PRES_BLK*` теперь намеренно остаются `raw_type=block`, `scale_kind=block`,
  пока не разобран настоящий DiagService response-field layout.

Состояние после восьмого инкремента этапа 2:

- `measurements.sqlite` schema v15. `service_outputs` получил колонки
  `bit_pos`, `bit_len`, `byte_offset`, `bit_offset` — реальное положение
  output-поля внутри ответа ЭБУ.
- Новый `_diag_output_layout()` читает inline Caesar output-field layout сразу
  за request bytes в блоке `DiagService` (`entry_count=1`, `kind 8/10`,
  marker `0x00832750`) и достает `bit_pos/bit_len`. Сейчас offset проставлен у
  188473 из 189343 `service_outputs` строк.
- Layout-based raw type: для линейных presentations ширина поля берется из
  layout (`prefer layout width`), одиночные single-bit CBF outputs декодируются
  как bool.
- Сильно расширены `presentation_meta()` и `_presentation_semantic_unit()`:
  - byte-dump варианты (`HEX_DUMP_N`, `N BYTE DUMP`,
    `IDENTICAL_HEX_DISPLAY_FOR_N_BYTES/BITS`, `IDENTICAL_BYTEFIELD_N_BYTES`),
    nibble-поля, `IDENTICAL_UINT/INT_DEC/HEX_N_BYTES`;
  - named single-bit enum (`Bit_Ja/Yes/True/Aktiv/...`), 1-bit bool, и common
    enum-пары (`Nein/Ja`, `Aus/Ein`, `Off/On`, `False/True`, ...);
  - семантические единицы по именам/немецким токенам: `count` (CNTR/CTR),
    `Nm` (torque/Drehmoment), `%` (Tastverhaeltnis/duty), `rpm`, `bar`
    (Rail/Druck), `V` (Volt/Spannung), `km` (Odometer/Kilometerstand),
    `mg/stroke` (Airmass/Luftmasse), `mg` (Injmass/Kraftstoffmenge),
    `day`/`month`, `K`/`deg C` (Temp/Kelv), `mA`/`A` (Strom/Current) с
    формулами `x * 0.1`, timing `_Nms/_Ns`, `FCTR_N -> x / N`.
- Глобально `service_outputs`: `raw_type` вырос со 157336 до 172098, `unit` с
  38907 до 56680, `formula` 94749, `value_map` 11704.
- Для `CRD3_DEV`: rawtype 1525, unit 619, formula 671 среди 1688 matched rows;
  для `CEPC_MFA`: rawtype 508, unit 35, formula 134 среди 545 matched rows.
- `PRES_BLK*` по-прежнему остаются `block`: теперь у них есть field offset, но
  не разобран многострочный layout.

Состояние после девятого инкремента этапа 2 (исправление ширины чтения):

- При разборе `PRES_BLK*` выяснилось, что block-сервисы делят один большой DID
  (например `22 01 05` у `CEPC_MFA` -> ~790 байт, 222 поля по 16 бит),
  а `bit_pos/byte_offset/bit_offset` дают реальное положение каждого поля.
- При этом `bit_len` из output-field layout оказался **константой**: dword по
  смещению `+20` всегда `0x00100000`, поэтому чтение на `+22` всегда давало
  `0x10 = 16`. То есть `service_outputs.bit_len` не несет ширину поля.
- Это был баг: backend `_layout_data()` резал ответ ровно на 2 байта (`bit_len`),
  игнорируя настоящий `byte_len`. В итоге ~42k однобайтовых полей читались как
  2 байта (значение портилось соседним байтом), а ~8.8k четырехбайтовых
  обрезались до 2 байт.
- Исправлено: `_layout_payload_bit_len()` берет ширину из presentation
  `byte_len` для всех типов и падает обратно на `bit_len` (2 байта) только если
  ширина неизвестна. DB-перестройка не требуется — `byte_len` уже хранится
  корректно по строкам. Добавлен regression-тест на 1- и 4-байтовые поля.
- `bit_pos/byte_offset/bit_offset` остаются достоверными; `bit_len` колонка
  фактически бесполезна и кандидат на удаление в следующей миграции схемы.
- Корректность `byte_len` проверяется по самому CBF: внутри одного DID шаг до
  следующего поля должен равняться `byte_len`. `tools/measure_layout_check.py`
  считает это совпадение (на локальной базе 79541/83886 = 94.8% по 4685 чистым
  DID), а `tests/test_measure_db.py` держит порог `>= 90%` (тест пропускается,
  если проприетарной базы нет). Это и доказывает, что ширина — `byte_len`, а не
  константный `bit_len=16`.

Состояние после десятого инкремента этапа 2 (знаковые типы):

- `_raw_value()` декодировал все целые через `int.from_bytes(..., "big")` без
  знака, поэтому `sbyte/sword/slong` (в т.ч. ~38k `sword`) читались как
  unsigned — отрицательные значения (например температуры ниже нуля) были
  неверны.
- Исправлено: signed-декодирование по `output_raw_type`
  (`sbyte/sword/slong`). Unsigned-типы не затронуты. Добавлен regression-тест.

Состояние после справочного CAN-инкремента:

- `measurements.sqlite` schema v10 содержит таблицы `reference_links` и
  `can_examples`.
- `tools/build_measure_db.py --references-json ...` импортирует фильтрованный
  Safari export с CAN/Mercedes network ссылками: URL, title, domain, tags,
  Safari folders/sources и `vehicle_hints_json` (`W164`, `X164`, `E211`).
- `tools/build_measure_db.py --can-examples-json resources/can_examples.json`
  импортирует проверенные пассивные CAN-факты для bench-сценариев: body,
  bus speed, CAN ID, DLC, sample payload, ECU direction, payload meaning,
  safety note и source URL.
- Первый seed покрывает W211/E211 EIS <-> instrument cluster на slow CAN
  `83.333 kbit/s`: `0x058`, `0x09E`, `0x000`, фильтры `Mask=7FF`; это нужно
  как справка при замене кластера, без write/workflow действий.
- Документ `docs/CAN_REFERENCES.md` фиксирует локальный export, ключевые ссылки
  по общей сети Mercedes/CAN gateway/J2534/OpenPort/Xentry/Vediamo и команду
  пересборки индекса.

Следующий инкремент этапа 1:

1. [x] Показать CBF coverage в Live data UI рядом с выбором ECU/группы.
2. [x] Разобрать unmatched jobs по топ-ECU: разные имена, алиасы, варианты CBF,
   service aliases.
3. [x] Подготовить reviewed alias/normalization layer для strong candidates,
   начиная с `IO0/IOF/IOD -> IOC` на read-only `DT_` job.
4. [x] Подготовить безопасный список read-only job prefixes для будущего hardware
   polling.

Следующий крупный шаг:

- Продолжить этап 2: разобрать полноценный многострочный layout для `PRES_BLK*`
  таблиц (`EngSpd/GearState`, `EngTrq/GearState`, fuel/travel/start counters).
  Single-field offset уже извлекается (`bit_pos/bit_len`), но для блоков нужно
  распарсить набор полей и их presentations, чтобы они перестали быть просто hex.
- Добить остаток кастомных application presentations (`PRES_Tsl...`,
  `PRES_GLPS...`, `PRES_APP_DATASET_*`), которые не покрываются именными
  эвристиками и compact-record'ами.
- По справочному слою: пополнять `can_examples` проверенными фактами из W164/X164
  topology pages и привязать их к сценариям замены кластера/bench-проверки.
