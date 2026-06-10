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
Браузер (HTML/JS)  ──HTTP/WS──►  FastAPI backend  ──J2534 (ctypes)──►  Openport 2.0  ──CAN──►  авто
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
frontend/
  index.html         SPA: вкладки Live / DTC / Модули / Кодирование
  app.js, style.css
```

## Запуск (симулятор)

```bash
cd macDiag
pip install -r backend/requirements.txt
python -m uvicorn backend.main:app --port 8000
# открыть http://localhost:8000
```

По умолчанию `MACDIAG_MODE=sim` — backend отвечает правдоподобными данными
(VIN, RPM, температуры, две ошибки B1535/C1525) без подключения к авто.

## Запуск с реальным Openport 2.0

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
| GET  | `/api/status` | режим, статус подключения |
| POST | `/api/connect` `/api/disconnect` | управление сессией |
| GET  | `/api/modules?chassis=W221` | список модулей |
| GET  | `/api/dtc?module=esp` | чтение ошибок |
| POST | `/api/dtc/clear?module=esp` | сброс ошибок |
| GET  | `/api/identify?module=ezs` | VIN / part number / SW |
| POST | `/api/coding/write` | запись DID (кодирование) |
| WS   | `/ws/live` | поток live-данных |

## ⚠ Безопасность

- Кодирование/адаптации (`/api/coding/write`) меняют настройки ЭБУ. Неверные
  значения могут вывести модуль из строя. Перед записью **читай и сохраняй**
  текущее значение DID.
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
