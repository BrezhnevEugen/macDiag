# macDiag

Веб-интерфейс для диагностики Mercedes-Benz **W221** (S-класс) и **X164** (GL-класс)
через **OBD-II** с адаптером **Tactrix Openport 2.0**.

Поддержка: чтение/сброс DTC, live-данные (PID), опрос модулей ЭБУ, кодирование
(WriteDataByIdentifier). Запускается **в режиме симулятора без железа** — можно
сразу посмотреть интерфейс, а потом переключиться на реальный кабель.

## Почему backend, а не «браузер напрямую»

Openport 2.0 — это устройство **SAE J2534 PassThru**, а не ELM327. Оно не
эмулирует COM-порт с AT-командами, а работает через драйвер J2534 (libusb).
Поэтому **Web Serial / Web Bluetooth API из браузера к нему подключиться не могут**.
Нужен нативный хост-процесс, который грузит драйвер J2534 и отдаёт данные в
браузер по HTTP/WebSocket. Это и делает backend на Python (FastAPI).

```
Браузер (React SPA)  ──HTTP/WS──►  FastAPI backend  ──J2534 (ctypes)──►  Openport 2.0  ──CAN──►  авто
```

## Архитектура

```
backend/
  main.py            FastAPI: REST + WebSocket, отдаёт фронтенд
  j2534/
    passthru.py      J2534 ctypes-обёртка + SIM-симулятор (один интерфейс)
    uds.py           UDS (ISO 14229) + OBD сервисы: DTC, PID, DID, кодирование
  mb/
    modules.py       карта модулей W221/X164 (CAN TX/RX, протокол)
    pids.py          стандартные OBD PID с декодерами
    dtc.py           описания кодов ошибок
web/
  src/               React SPA: Live / DTC / Модули / Кодирование / Flash
  package.json       Vite build и lint
  dist/              production-сборка; отдаётся FastAPI
```

## Docker (рекомендуется)

Образ содержит **только код + стартовый seed** (готовая база на 169 ЭБУ и 18 CBF
курируемых модулей). Реальные данные живут в монтируемом томе `./data`, поэтому
их можно **расширять без пересборки образа**.

```bash
# один раз подготовить seed (он gitignored — это данные MB), указав папку с CBF:
tools/prepare_seed.sh ~/Downloads/Vediamo/VediamoData

docker compose up --build       # http://localhost:8000
```

На первом старте entrypoint наполняет `./data` из seed: `ecu_db.sqlite` (каталог
169 ЭБУ), `cbf/` (18 модулей для variant coding). Дальше работают каталог,
модули, DTC, live, seed-key и кодирование — из коробки, без твоей папки Vediamo.
Если нужен StarFinder, его `.asar`-архивы лежат рядом с проектом в
`./data/starfinder`; Docker монтирует эту папку read-only.
Дополнительное сырьё Vediamo для будущих импортёров (`.mwg`, `.vsb`, `.mak`,
`.ini`, `.pdf`, `.jar` и т.п.) хранится в `./data/vediamo_raw`; текущий backend
напрямую его не сканирует, а использует собранную локальную базу
`./data/measurements.sqlite`.
Мелкие справочники, таблицы, ETN/кодировочные архивы и прочее сырьё с внешнего
`dist` сложены в `./data/dist_raw`. Прошивки и flash-контейнеры (`.cff`,
`.smr-d/.smr-f`, `.bin` и архивы с flash/CFF) внутрь проекта не копируем: для них
есть локальный индекс `./data/dist_raw/firmware_external_index.tsv` с путями на
внешнем диске.

### Расширение данных (добавляем блоки позже)

Данные — в `./data`, образ трогать не надо:

```bash
# 1) докинуть CBF в библиотеку тома (только .cbf, НЕ флэш-файлы!)
cp /путь/к/новым/*.cbf ./data/cbf/

# 2) пересобрать каталог из всех CBF в томе
docker compose exec macdiag python tools/build_ecu_db.py --dir /data/cbf --out /data/ecu_db.sqlite

# 3) (опц.) обновить seed-key базу
docker compose exec macdiag python tools/fetch_unlock_db.py
#    или положить файл руками: ./data/unlock_db.json
```

Чтобы сразу получить **полный** каталог по своей библиотеке — скопируй в
`./data/cbf/` все свои CBF (из `VediamoData` и `CBF Для кодирования`) и пересобери.

> ⚠ Реальное железо (Openport) в Docker на macOS **не работает** — нет проброса
> USB. Контейнер = симулятор + работа с данными (каталог, кодирование, seed-key).
> Для живого авто запускай нативно (`MACDIAG_MODE=hw`).

## Что класть в данные (а что НЕ нужно)

Для основной диагностической базы macDiag использует **CBF-файлы**. Из тяжёлой
библиотеки Vediamo (бывает ~10 ГБ) для работы с ЭБУ нужны прежде всего они:

| Папка | Размер | Нужно macDiag? |
|------|--------|----------------|
| `CFF Для программирования` | ~6.8 ГБ | ❌ флэш-образы, не используются |
| `SMR-D, SMR-F` | ~350 МБ | ❌ флэш-контейнеры |
| `CBF Для кодирования` | ~700 МБ (1067 шт.) | ✅ CBF — бери эти |
| `VediamoData/*.cbf` | ~376 МБ (171 шт.) | ✅ CBF — и эти |

То есть в `./data/cbf` имеет смысл класть только `*.cbf` (суммарно ~1 ГБ или
нужное подмножество), а многогигабайтные CFF/SMR не трогать.

Дополнительные локальные папки данных:

- `./data/starfinder` — `.asar`-архивы StarFinder, используются media-провайдером.
- `./data/vediamo_raw` — сырьё Vediamo для пересборки локальных импортных баз.
- `./data/measurements.sqlite` — собранная база групп измерений/процедур из
  `.vsg/.mwg`; runtime читает её первой. В ней уже есть `localization_key`
  для групп/параметров, таблица `translations` под словарь, CBF request metadata
  и `service_outputs` с найденными `PRES_*` output-presentation qualifier.
  Schema v14 хранит грубо определённый raw type/byte length, unit/formula из
  очевидных `PRES_CM_*` qualifier names, линейные conversion records из CBF
  (`factor/offset`, например `x * 0.01 - 50`) и range-linear records
  (`min/max + factor/offset`, например CEPC battery voltage), а также
  классифицирует enum-records с CTF labels/value-map, `bool`, `BCD`, `block` и
  `hexdump` presentations.
- `./data/dist_raw` — мелкое сырьё с внешнего `dist`: документы, таблицы,
  ETN/CDI/BMREF, DWF-чертежи и выбранные reference/coding-архивы.
- `./data/dist_raw/firmware_external_index.tsv` — список прошивок, которые
  оставлены на внешнем диске.

## Запуск (симулятор, нативно)

```bash
cd macDiag
pip install -r backend/requirements.txt
# production UI, который затем отдаёт FastAPI на :8000
(cd web && npm ci && npm run build)
python -m uvicorn backend.main:app --port 8000
# открыть http://localhost:8000
```

Для разработки UI запускай Vite отдельно: `cd web && npm run dev`, затем открой
`http://localhost:5173`. Vite проксирует `/api` и `/ws` к FastAPI на `:8000`.
Docker сам собирает этот же React-клиент; Node.js в финальный образ не попадает.

По умолчанию `MACDIAG_MODE=sim` — backend отвечает правдоподобными данными
(VIN, RPM, температуры, ошибки двигателя P0170/P0300) без подключения к авто.

## Подключение Openport 2.0 (macOS)

Официального J2534-драйвера под macOS у Tactrix нет, но есть open-source драйвер
на **libusb**, который собирается в `.dylib`. Наша ctypes-обёртка
(`backend/j2534/passthru.py`) грузит его и говорит с кабелем по SAE J2534-1.

```bash
# 1. собрать драйвер (libusb + сборка из github.com/dschultzca/j2534)
tools/build_driver_macos.sh          # -> driver/libj2534.dylib

# 2. запустить backend в режиме железа
MACDIAG_MODE=hw python3 -m uvicorn backend.main:app --port 8000
#   путь к драйверу подхватится из ./driver, или задай явно:
#   MACDIAG_MODE=hw MACDIAG_DRIVER=/usr/local/lib/libj2534.dylib python3 -m uvicorn ...
```

Подключи кабель к OBD-разъёму и нажми **«Подключить»** в шапке. Бэкенд откроет
устройство и прочитает **напряжение АКБ** — если показывает ~12–14 В, связь и
шина живые. Дальше — DTC, live, кодирование как обычно.

**Тип `unsigned long`.** J2534 на Windows 32-битный, а собранный под 64-бит Mac
`.dylib` может быть 64-битным. По умолчанию обёртка 32-бит; если напряжение/данные
выглядят мусором — переключи: `MACDIAG_J2534_INT=64`.

**Если не подключается:**
- `cannot load J2534 driver` — нет `.dylib` или не та архитектура (нужен arm64 на
  Apple Silicon): пересобери `tools/build_driver_macos.sh`.
- `PassThruOpen failed` / устройство не найдено — кабель не виден libusb: проверь
  `system_profiler SPUSBDataType | grep -i openport`, отключи мешающие драйверы.
- напряжение `0`/мусор — смени `MACDIAG_J2534_INT`, проверь питание пина 16 OBD.
- мультишина: кузовные ЭБУ X164 на 83.3k достаются через шлюз — это норм, выбирай
  модуль, baudrate подставится из CBF.

> Docker на macOS для железа не годится — нет проброса USB. Для авто запускай
> нативно. Docker — для симулятора и работы с данными.

## Запуск с реальным Openport 2.0 (Windows/Linux)

1. Установи драйвер J2534 для Openport:
   - **Windows**: пакет Tactrix «OpenPort 2.0 J2534» (даёт `op20pt32.dll`).
   - **Linux**: собери `libj2534.so` из
     [dschultzca/j2534](https://github.com/dschultzca/j2534) или
     [NikolaKozina/j2534](https://github.com/NikolaKozina/j2534) (нужен libusb ≥ 1.0.8).
   - **macOS**: нативного драйвера нет — запускай backend в Linux/Windows-VM,
     либо оставайся в режиме симулятора.
2. Запусти в режиме железа:

```bash
MACDIAG_MODE=hw python -m uvicorn backend.main:app --port 8000
# при необходимости укажи путь к драйверу:
MACDIAG_MODE=hw MACDIAG_DRIVER=/usr/local/lib/libj2534.so python -m uvicorn backend.main:app
```

## API

| Метод | Путь | Назначение |
|------|------|-----------|
| GET  | `/api/status` | режим, статус подключения и профиль транспорта |
| POST | `/api/connect` `/api/disconnect` | управление сессией |
| GET  | `/api/adapter/status` | возможности и кэшированное состояние транспорта без ECU-запросов |
| POST | `/api/adapter/self-test` | самотест адаптера и ISO-TP канала без запроса к ЭБУ |
| GET  | `/api/profiles` | активный и packaged-профили автомобилей |
| POST | `/api/profile?name=w221-x164` | смена packaged-профиля до подключения адаптера |
| GET  | `/api/modules?chassis=W221` | список pickable-модулей |
| GET  | `/api/catalog?chassis=X164` | полный каталог ЭБУ из Vediamo CBF |
| GET  | `/api/dtc?module=esp` | чтение ошибок |
| POST | `/api/dtc/clear?module=esp` | сброс ошибок; на hardware требует `MACDIAG_ENABLE_WRITES=1` |
| GET  | `/api/identify?module=ezs` | VIN / part number / SW |
| POST | `/api/security/unlock?module=esp` | Security Access (0x27) seed→key |
| POST | `/api/coding/write` | запись DID (кодирование, с авто-0x27); на hardware требует opt-in |
| WS   | `/ws/live` | поток live-данных |

## Транспорт: UDS и KWP2000

Клиент выбирается автоматически по полю `protocol` модуля в `mb/modules.py`:

- `uds` — ISO 14229 (двигатель ME/CDI, 722.9, IC, VG): сервисы 0x22/0x19/0x2E.
- `kwp` — KWP2000-over-CAN (EZS, ESP, SRS, SAM, AIRMATIC): сервисы 0x21/0x18/0x3B.

Оба используют один ISO-TP транспорт через J2534, framing одинаковый — отличаются
только ID сервисов.

## Security Access (0x27)

Запись в защищённые модули требует разблокировки: `request seed → вычислить key →
send key`.

**Реальные алгоритмы (UnlockECU).** `mb/unlock.py` — порт провайдеров seed→key из
проекта [UnlockECU](https://github.com/jglim/UnlockECU) (MIT, реверс-инжиниринг,
без проприетарных блобов). Определения ЭБУ (провайдер + константы + длины
seed/key) берутся из `unlock_db.json` — это `db.json` из UnlockECU:

```bash
python tools/fetch_unlock_db.py     # скачать базу определений (~1.4MB, MIT)
```

Портированные провайдеры (22): семейство Daimler (`DaimlerStandardSecurityAlgo`,
`…Mod`, `…RefG`), Powertrain (`PowertrainSecurityAlgo`, `…2`, `…3`, `…NFZ`,
`PowertrainDelphiSecurityAlgo`, `PowertrainBoschContiSecurityAlgo1`, `…2`), VGS для
АКПП (`VGSSecurityAlgo`, `…2Bytes`, `…Ext`), щитки (`IC172Algo1`, `IC172Algo2`,
`IC204`, `KI221Algo1`, `KI221Algo2`, `KIAlgo1`, `KI203Algo`),
`ESPSecurityAlgoLevel1`, `XorAlgo` — покрывает практически все кластеры MB этого
поколения. Проверяемые алгоритмы (VGS, ESP, Daimler/RefG, KI221Algo2) сверены с
эталонным расчётом до бита. `GET /api/security/info` показывает, какой провайдер
применим к ЭБУ и портирован ли он.

Поток `/api/security/unlock`: берёт реальный алгоритм из базы по имени ЭБУ; если
определения/портирования нет — откатывается на заглушку симулятора (`mb/seedkey.py`),
чтобы демо работало без железа. Провайдеры, которых ещё нет в `PROVIDERS`,
возвращают «не портирован» вместо неверного ключа.

### Откуда берётся реальный seed-key и проверка покрытия

1. **db.json (UnlockECU)** — первичный источник: реверс-инжиниренные провайдер +
   константы. Покрывает большинство ЭБУ W221/X164. `python tools/fetch_unlock_db.py`.
2. **Security-DLL Mercedes** (в установке Vediamo/DTS/Xentry) — оригинал, из
   которого реверсили db.json. Для непокрытых ЭБУ алгоритм там; UnlockECU умеет
   звать оригинальную DLL напрямую.
3. **SMR-D/SMR-F — НЕ содержат seed-key** (проверено на реальных файлах): это
   флэш-контейнеры, внутри только метка `EXCLUDE-AUDIENCE: offlinekeycalc`.
   Источником ключей не являются.

Проверить покрытие под свои ЭБУ:

```bash
python tools/fetch_unlock_db.py
python tools/check_unlock_coverage.py                  # вся база
python tools/check_unlock_coverage.py EZS164 KI164 ESP9MFA ME97 CRD3 TCM164
```

Статусы: `✓ готов` (в db.json + провайдер портирован), `△ есть, провайдер не
портирован`, `— нет в db.json`.

## Данные Vediamo (CBF)

Карта модулей построена из **реальных CBF-файлов Vediamo**, а не из догадок.
`tools/parse_cbf.py` извлекает из каждого CBF: имя ЭБУ, диагностический протокол
(из communication-template), номера деталей MB, варианты, скорости шины, имена
COMPARAM и job'ов. Результат — `backend/mb/vediamo_catalog.json` (69 ЭБУ для
W221/X164), который `modules.py` накладывает на pickable-список.

### Общая база ЭБУ (подтягиваем нужные)

Вместо хардкода — единая база всех блоков из всей библиотеки CBF (любые шасси:
X164, W221, W251, C216 …). Приложение тянет из неё только нужное по имени,
шасси, протоколу или поиску.

```bash
# собрать общую базу из всей папки Vediamo (SQLite + FTS-поиск)
python tools/build_ecu_db.py --dir "/path/to/VediamoData" --out backend/mb/ecu_db.sqlite

# посмотреть один CBF
python tools/parse_cbf.py EZS164.cbf
```

Запросы к базе через API:

| Путь | Назначение |
|------|-----------|
| `GET /api/db/stats` | сводка: всего ЭБУ, по протоколам, по шасси |
| `GET /api/catalog?chassis=W221` | все блоки шасси |
| `GET /api/catalog?q=ESP&protocol=uds` | поиск + фильтр |
| `GET /api/catalog/EZS164` | детали ЭБУ (job'ы, comparam'ы, детали, варианты) |

База **не коммитится в git** (`.gitignore`) — это производная от проприетарных
данных MB. Собирай локально из своей папки Vediamo. Если базы нет, приложение
работает на симуляторе и bundled JSON-подмножестве.

### Реальные CAN ID из comparam-таблиц Caesar

`tools/caesar_comparam.py` — частичная реализация формата Caesar (порт нужного
пути из CaesarSuite, MIT): `CFFHeader → ECU → ECUInterface → ECUVariant →
ComParameter`. Достаёт **настоящие значения**:

```
CP_REQUEST_CANIDENTIFIER    request id  (tester → ECU)
CP_RESPONSE_CANIDENTIFIER   response id (ECU → tester)
CP_GLOBAL_REQUEST_CANIDENTIFIER  функциональный/broadcast id
CP_BAUDRATE                 скорость шины
```

Эти ID попадают в базу (`can_request/response/global`, `baudrate`) и
используются в `modules.py` с пометкой `id_source: "cbf"`. Догадки по стандартной
адресации остаются только как fallback из активного профиля
(`id_source: "profile"`, помечены `?`). Сам профиль по умолчанию лежит в
`backend/mb/profiles/w221_x164.json`; для другой машины задай
`MACDIAG_PROFILE_PATH=/путь/к/профилю.json`. Значения из CBF всегда имеют
приоритет (`id_source: "cbf"`).

Профиль хранит не только aliases/адреса, но и безопасные gateway-probe jobs,
captured simulator trace, demo DTC и simulator identity. Поэтому добавление
другой машины не требует редактировать Python: положи валидный JSON в
`backend/mb/profiles/` (его можно выбрать в UI до подключения), либо укажи
внешний путь через `MACDIAG_PROFILE_PATH` при старте backend.
146 из 169 ЭБУ отдали реальные ID. Пример (X164):

```
EZS164  req 0x4E0  resp 0x5FF  baud 83.3k    KI164   req 0x5B4  resp 0x4F4  83.3k
SAMV164 req 0x662  resp 0x4E2  83.3k         ME97    req 0x7E0  resp 0x7E8  500k
ESP9MFA req 0x632  resp 0x486  500k          TCM164  req 0x7E1  resp 0x7E9  500k
```

**Мультишинность.** Видно, что кузовные модули X164 (EZS, KI, SAM, KLA) висят на
внутреннем CAN **83.3 кбод**, а силовые/шасси — на **500 кбод**. OBD-разъём
напрямую отдаёт 500k; до 83.3k-модулей идём через центральный шлюз (ZGW).
`Session` открывает по каналу на каждую скорость и выбирает нужный по `baudrate`
модуля.

Важно: шасси определяется по упоминаниям `BR221/W221/BR164/W164` внутри CBF и по
имени ЭБУ — **не** по префиксу номера детали, т.к. у MB номера деталей
перехлёстываются между Baureihen.

## Variant coding (кодировка по именам)

`tools/caesar_vc.py` парсит из CBF VC-домены → фрагменты (параметры кодирования:
бит-позиция, длина, имя) → субфрагменты (enum-опции значение→метка), с резолвом
имён через CTF-таблицу строк. `mb/varcoding.py` отдаёт это в API, декодирует
строку кодирования в именованные опции и собирает обратно.

Нужны CBF-файлы (из библиотеки Vediamo, в репозиторий не кладём). Укажи папку:

```bash
export MACDIAG_CBF_DIR="/path/to/VediamoData"
```

| Путь | Назначение |
|------|-----------|
| `GET /api/coding/domains?module=ki` | список VC-доменов ЭБУ |
| `POST /api/coding/decode` | строка кодирования → именованные опции |
| `POST /api/coding/encode` | сменить опцию фрагмента → новая строка |
| `GET /api/coding/read` | прочитать строку с авто (по `lid`) и декодировать |
| `POST /api/coding/apply` | записать изменённую строку в ЭБУ (после 0x27) |

Полный цикл на авто: «Прочитать с авто» (`RVC_…_Lesen`) → правка опций → «Записать
в ЭБУ» (`WVC_…_Schreiben` после Security Access). В симуляторе цикл работает
полностью (хранит кодировки).

На реальном адаптере изменяющие операции (`DTC clear`, `coding/apply`,
`coding/write`) заблокированы сервером по умолчанию. После проверки VIN,
питания и backup запусти backend с явным opt-in:

```bash
MACDIAG_MODE=hw MACDIAG_ENABLE_WRITES=1 python -m uvicorn backend.main:app --port 8000
```

**LID и уровень доступа извлекаются из CBF автоматически.** `tools/caesar_vc.py`
парсит `DiagService` каждого домена и достаёт байты запроса (`RequestBytes`) — там
зашиты сервис и идентификатор: `RVC_…_Lesen` → `0x21 <lid>` (KWP) или `0x22 <did>`
(UDS), `WVC_…_Schreiben` → `0x3B <lid>` / `0x2E <did>`, плюс `SecurityAccessLevel`.
Поэтому в API `lid`/`level` опциональны — подставляются из CBF; поле «LID» в UI
заполняется само и нужно только для ручного переопределения.

Во вкладке «Кодирование» внизу: выбрать домен → «Декодировать» → параметры
показываются списком с выпадающими опциями; смена опции пересобирает строку.
На авто строка читается сервисом домена `RVC_…_Lesen` и пишется `WVC_…_Schreiben`
(после Security Access). Пример (KI164): домен `VCD_Aktuelle_Menueeinstellungen`
с параметрами вроде «Vmax Winterreifen», «Uhrverstellung», выбор типа двигателя.

Оговорка: длина части фрагментов берётся из presentation-таблиц (помечены `~`) —
для них длину стоит перепроверить.

## Группы измерений и сервисные процедуры (.vsg/.mwg)

Порядок следующих работ зафиксирован в [`docs/ROADMAP.md`](docs/ROADMAP.md).

Vediamo `.vsg` (Service Group) — XML с готовыми наборами диагностических job'ов
(алиасы, единицы, лимиты, value-map). `tools/parse_vsg.py` парсит их,
`mb/measurements.py` индексирует по ЭБУ и делит на **измерительные группы**
(live-дашборды из `DT_`/`ADJ_`) и **сервисные процедуры** (с `RT_`/актуаторами).
Ecoute `.mwg` из `./data/vediamo_raw` тоже подключены: INI-файлы читаются через
`tools/parse_mwg.py`, а `.mwg`, которые на самом деле XML, автоматически идут
через тот же парсер `.vsg`. Для `.mwg` обычно есть реальные job names, но чаще
нет единиц/лимитов — значения в симуляторе всё равно отображаются как dashboard.

Runtime не обязан сканировать raw-файлы. Нормальный поток такой:

```bash
python3 tools/build_measure_db.py \
  --vsg-dir data/vsg \
  --mwg-dir data/vediamo_raw \
  --cbf-dir data/cbf \
  --references-json data/references/safari_bookmarks_2026-06-17/can_bookmarks.json \
  --can-examples-json resources/can_examples.json \
  --out data/measurements.sqlite
```

После этого backend читает `MACDIAG_MEASURE_DB` (`/data/measurements.sqlite` в
Docker). Если базы нет, остаётся fallback на raw-каталоги `MACDIAG_VSG_DIR` и
`MACDIAG_MWG_DIR`, чтобы разработка не ломалась.

Если передан `--cbf-dir`, генератор дополнительно парсит CBF по импортированным
ЭБУ и сохраняет локальный каталог `DiagService` в таблицу `diag_services`:
`request_hex`, `sid`, `identifier`, `sec_level`, имя и описание из CBF.
Связь импортного `services.job` с CBF хранится отдельно в
`diag_service_matches`: `exact` для строгого совпадения и `normalized` только
для проверенных правил. Сейчас включено узкое read-only правило для `DT_` job:
`IO0/IOF/IOD -> IOC`, например `DT_IO0352... -> DT_IOC352...`; candidate обязан
быть read request `21/22`. Быстро посмотреть покрытие и оставшиеся кандидаты
можно так:

```bash
python3 tools/measure_diag_coverage.py CRD3_DEV CEPC_MFA
python3 tools/measure_unmatched_jobs.py CRD3_DEV --limit 40
```

`measure_unmatched_jobs.py` не меняет базу автоматически. Он строит отчет по
job'ам, которые всё еще не покрыты `diag_service_matches`, и ранжирует
кандидатов из локального CBF-каталога. Это рабочий список для следующих
проверенных правил, а не автоподмена.

На железе `read_values()` дополнительно применяет read-only guard перед каждым
`raw_request`: сейчас отправляются только `DT_` job с SID `21/22`. Найденный в
CBF request с `2E/2F/30/31/...` остаётся в базе для анализа, но Live data его не
отправляет; в ответе параметра будет `read_status: "blocked"` и причина.

Если передан `--references-json`, генератор импортирует справочные ссылки в
таблицу `reference_links`: URL, заголовок, домен, теги, папки Safari, источники и
`vehicle_hints` вроде `W164`, `X164`, `E211`. Сейчас это используется для
CAN/Mercedes network ссылок из Safari export; дальше этот слой можно привязать к
модели, ECU, gateway, адаптеру и экранам разъемов.

Если передан `--can-examples-json`, генератор импортирует проверенные пассивные
CAN-факты в `can_examples`: скорость шины, CAN ID, DLC, пример payload,
направление ECU -> ECU, смысл payload и source URL. Первый seed покрывает
bench-сценарий W211/E211 EIS ↔ cluster на медленной CAN `83.333 kbit/s`
(`0x058`, `0x09E`, `0x000`). Эти данные нужны как справка при замене кластера;
приложение не добавляет write/workflow действий для изменения пробега.

В базе рядом с нормализованными группами и job'ами хранится
`localization_key`. Отдельная таблица `translations(localization_key, lang,
text, context)` сейчас заполняется языком `source`: это исходные названия и
контекст из `.vsg/.mwg`. Позже туда можно добавлять `ru`/`en`/`de` и другие
языки без потери связи с исходным диагностическим смыслом.

Словарь пополняется отдельным инструментом:

```bash
python3 tools/manage_measure_translations.py export \
  --lang ru \
  --out data/translations/measurements_ru.csv

# опционально: заполнить понятные русские строки из локального glossary
python3 tools/seed_measure_ru_translations.py

# заполнить колонку translation, не трогая localization_key/source_text/context

python3 tools/manage_measure_translations.py import \
  --lang ru \
  --input data/translations/measurements_ru.csv

python3 tools/manage_measure_translations.py stats --lang ru
```

Runtime использует перевод только если он есть для запрошенного `lang`; иначе
остаётся текущая эвристическая подпись из `glossary`.

| Путь | Назначение |
|------|-----------|
| `GET /api/measure/ecus` | ЭБУ, у которых есть группы |
| `GET /api/measure/groups?module=CRD3_DEV` | измерительные + сервисные группы ЭБУ + CBF coverage |
| `GET /api/measure/group?path=…` | состав группы (job/alias/unit/limits + `req`/`sid`/`identifier`, если найден CBF service) |
| `GET /api/measure/read?path=…` | текущие значения параметров |

Во вкладке **Live data**: выбор ЭБУ → группа измерений → дашборд с именованными
параметрами (напр. «Überprüfung des Ladedrucksystems»: давление наддива,
момент, обороты…), плюс отдельный список сервисных процедур (DPF-регенерация,
обучение дросселя и т.п.). На симуляторе значения синтезируются в пределах
лимитов. Реальное чтение физических величин — следующая итерация (нужен разбор
output-presentation из CBF для масштабирования).

Каталог `.vsg` лежит в `MACDIAG_VSG_DIR`; raw `.mwg` лежат в `MACDIAG_MWG_DIR`,
но Docker по умолчанию использует уже собранную `MACDIAG_MEASURE_DB`.

## Флэш (перепрошивка) — каркас, read-only

Размечено под будущую итерацию. Сейчас **только чтение**: каталог CFF-образов,
чтение версий ЭБУ, идентификация. Запись прошивки **не реализована намеренно**
(`/api/flash/program` → 501) — неверный/прерванный флэш может убить ЭБУ.

- `tools/parse_cff.py` — метаданные CFF (ЭБУ, номер детали, сегменты
  Applikation/Parameterdaten/Bootloader, адреса, SW-версии) — read-only.
- `backend/mb/flash.py` — каталог CFF из `MACDIAG_CFF_DIR`, чтение версий с авто,
  `program()` бросает `NotImplementedError`.
- API: `GET /api/flash/library`, `GET /api/flash/cff/{name}`,
  `GET /api/flash/versions?module=`, `POST /api/flash/program` (501).

Итерация 2 (отдельно): полная flash-последовательность (programming session →
security access → erase → RequestDownload/TransferData/TransferExit → проверка
CRC/подписи) — только с жёсткими защитами и обкаткой на стенде.

## ⚠ Безопасность

- Кодирование/адаптации (`/api/coding/write`) меняют настройки ЭБУ. Неверные
  значения могут вывести модуль из строя. Перед каждой записью backend
  **автоматически читает и журналирует** текущее значение DID в
  `data/coding_backups.jsonl` (`GET /api/coding/backups`) — по нему можно
  откатиться вручную. В React-вкладке «Кодирование» кнопка «Журнал backups»
  показывает последние записи с ECU, доменом, DID/LID и парами old/new.
  Но это страховка, а не замена осторожности.
- В `MACDIAG_MODE=hw` backend сам блокирует DTC clear и coding-записи, пока не
  задано `MACDIAG_ENABLE_WRITES=1`. Это намеренная серверная защита, не зависящая
  от того, какой UI или HTTP-клиент отправил запрос.
- Адреса модулей в `backend/mb/modules.py` — типовые для этих шасси. Реальные
  TX/RX/протокол зависят от года, рестайлинга (W221 до/после 2009) и комплектации.
  Всегда сверяйся с VIN и подтверждай связь перед записью.
- Не диагностируй на ходу.

## Дальнейшие шаги

- Добавить KWP2000-over-CAN транспорт для модулей с `protocol: "kwp"`.
- Security Access (UDS 0x27) для модулей, требующих разблокировки перед кодированием.
- Расширить таблицы PID/DID под конкретные ЭБУ (ME9.7, CDI, 722.9, AIRMATIC).
- Полноценный ISO-TP в SIM-режиме для длинных ответов.
```
