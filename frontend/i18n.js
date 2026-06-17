// macDiag UI localization (ru / en / de).
// Keys are the Russian source strings; ru returns the key unchanged.
// app.js wraps dynamic strings in t(); static markup uses data-i18n / data-i18n-ph.

const I18N = {
  // ---- errors / toast ----
  "Ошибка запроса: ": { en: "Request failed: ", de: "Anfrage fehlgeschlagen: " },
  "Live: ": { en: "Live: ", de: "Live: " },
  "Live-поток: ошибка соединения": { en: "Live stream: connection error", de: "Live-Stream: Verbindungsfehler" },

  // ---- header / tabs ----
  "Эмулятор": { en: "Simulator", de: "Simulator" },
  "Железо": { en: "Hardware", de: "Hardware" },
  "не подключено": { en: "not connected", de: "nicht verbunden" },
  "Подключить": { en: "Connect", de: "Verbinden" },
  "Отключить": { en: "Disconnect", de: "Trennen" },
  "подключено": { en: "connected", de: "verbunden" },
  "Обзор": { en: "Overview", de: "Übersicht" },
  "Live data": { en: "Live data", de: "Live-Daten" },
  "Ошибки": { en: "Faults", de: "Fehler" },
  "Модули": { en: "Modules", de: "Module" },
  "Кодирование": { en: "Coding", de: "Codierung" },
  "Справка": { en: "References", de: "Referenzen" },
  "Словарь": { en: "Dictionary", de: "Wörterbuch" },

  // ---- overview ----
  "автомобиль": { en: "vehicle", de: "Fahrzeug" },
  "адаптер": { en: "adapter", de: "Adapter" },
  "шина": { en: "bus", de: "Bus" },
  "Прочитать VIN": { en: "Read VIN", de: "VIN lesen" },
  "Блоки управления": { en: "Control units", de: "Steuergeräte" },
  "Все шасси": { en: "All chassis", de: "Alle Baureihen" },
  "⚡ Сканировать": { en: "⚡ Scan", de: "⚡ Scannen" },
  "В": { en: "V", de: "V" },
  "режим: ": { en: "mode: ", de: "Modus: " },
  "● подключено": { en: "● connected", de: "● verbunden" },
  "нажми «Подключить»": { en: 'click "Connect"', de: "„Verbinden“ klicken" },
  "OBD питание есть": { en: "OBD power present", de: "OBD-Strom vorhanden" },
  "нет питания OBD": { en: "no OBD power", de: "kein OBD-Strom" },
  "VIN не прочитан — нажми «Прочитать VIN»": { en: 'VIN not read — click "Read VIN"', de: "VIN nicht gelesen — „VIN lesen“ klicken" },
  "год: ": { en: "year: ", de: "Baujahr: " },
  "из ": { en: "from ", de: "aus " },
  "чтение VIN…": { en: "reading VIN…", de: "VIN wird gelesen…" },
  "сканирую…": { en: "scanning…", de: "Scannen…" },
  "ЭБУ онлайн": { en: "ECUs online", de: "Steuergeräte online" },
  "ошибок (DTC)": { en: "faults (DTC)", de: "Fehler (DTC)" },
  "протокол": { en: "protocol", de: "Protokoll" },
  "нет ответа": { en: "no response", de: "keine Antwort" },
  "DTC": { en: "DTC", de: "DTC" },
  "запуск эмулятора…": { en: "starting simulator…", de: "Simulator startet…" },
  "подключение к железу…": { en: "connecting to hardware…", de: "Verbindung zur Hardware…" },
  "подключение…": { en: "connecting…", de: "Verbindung…" },
  "ошибка подключения": { en: "connection error", de: "Verbindungsfehler" },
  "эмулятор": { en: "simulator", de: "Simulator" },
  "железо": { en: "hardware", de: "Hardware" },
  "Не удалось переключить на ": { en: "Failed to switch to ", de: "Umschalten fehlgeschlagen auf " },
  "Не удалось подключиться:": { en: "Failed to connect:", de: "Verbindung fehlgeschlagen:" },
  "неизвестно": { en: "unknown", de: "unbekannt" },
  "В режиме железа нужен драйвер J2534 (libj2534.dylib) и MACDIAG_MODE=hw. См. README.":
    { en: "Hardware mode needs the J2534 driver (libj2534.dylib) and MACDIAG_MODE=hw. See README.",
      de: "Der Hardware-Modus benötigt den J2534-Treiber (libj2534.dylib) und MACDIAG_MODE=hw. Siehe README." },

  // ---- live / measurements ----
  "▶ Старт потока (двигатель / OBD)": { en: "▶ Start stream (engine / OBD)", de: "▶ Stream starten (Motor / OBD)" },
  "■ Стоп": { en: "■ Stop", de: "■ Stopp" },
  "Группы измерений по ЭБУ": { en: "Measurement groups by ECU", de: "Messwertgruppen nach Steuergerät" },
  "ЭБУ": { en: "ECU", de: "Steuergerät" },
  "— выбери —": { en: "— select —", de: "— wählen —" },
  "Группа": { en: "Group", de: "Gruppe" },
  "▶ Авто": { en: "▶ Auto", de: "▶ Auto" },
  "Выбери ЭБУ и группу измерений.": { en: "Select an ECU and a measurement group.", de: "Steuergerät und Messwertgruppe wählen." },
  "Сервисные процедуры": { en: "Service procedures", de: "Serviceprozeduren" },
  "— выбери процедуру —": { en: "— select a procedure —", de: "— Prozedur wählen —" },
  "— выбери ЭБУ —": { en: "— select an ECU —", de: "— Steuergerät wählen —" },
  "группы измерений недоступны": { en: "measurement groups unavailable", de: "Messwertgruppen nicht verfügbar" },
  "нет измерительных групп": { en: "no measurement groups", de: "keine Messwertgruppen" },
  "шаг.": { en: "steps", de: "Schritte" },
  "загрузка…": { en: "loading…", de: "lädt…" },
  "Что:": { en: "What:", de: "Was:" },
  "Когда:": { en: "When:", de: "Wann:" },
  "Как:": { en: "How:", de: "Wie:" },
  "Шаги": { en: "Steps", de: "Schritte" },
  "нет актуаторных шагов": { en: "no actuator steps", de: "keine Aktuatorschritte" },
  "Параметры": { en: "Parameters", de: "Parameter" },
  "▶ Открыть в дашборде (наблюдать значения)": { en: "▶ Open in dashboard (watch values)", de: "▶ Im Dashboard öffnen (Werte beobachten)" },
  "Шаги (актуаторы):": { en: "Steps (actuators):", de: "Schritte (Aktuatoren):" },
  "норма": { en: "normal", de: "Soll" },
  "CBF coverage": { en: "CBF coverage", de: "CBF-Abdeckung" },
  "строк с request": { en: "rows with request", de: "Zeilen mit Request" },
  "job без request": { en: "jobs without request", de: "Jobs ohne Request" },
  "нормализовано": { en: "normalized", de: "normalisiert" },
  "выход": { en: "output", de: "Ausgabe" },
  "тип": { en: "type", de: "Typ" },
  "единицы": { en: "units", de: "Einheiten" },
  "формула": { en: "formula", de: "Formel" },
  "нет импортированных job для этого ЭБУ": { en: "no imported jobs for this ECU", de: "keine importierten Jobs für dieses Steuergerät" },
  "запрос заблокирован": { en: "request blocked", de: "Request blockiert" },
  "ошибка чтения": { en: "read error", de: "Lesefehler" },

  // ---- dictionary ----
  "Язык": { en: "Language", de: "Sprache" },
  "Тип": { en: "Type", de: "Typ" },
  "Все": { en: "All", de: "Alle" },
  "Группы": { en: "Groups", de: "Gruppen" },
  "Не переведено": { en: "Missing", de: "Nicht übersetzt" },
  "Переведено": { en: "Translated", de: "Übersetzt" },
  "поиск по ключу, исходнику, контексту…": { en: "search key, source, context…", de: "Schlüssel, Quelle, Kontext suchen…" },
  "Обновить": { en: "Refresh", de: "Aktualisieren" },
  "Назад": { en: "Back", de: "Zurück" },
  "Вперёд": { en: "Next", de: "Weiter" },
  "Исходник": { en: "Source", de: "Quelle" },
  "Перевод": { en: "Translation", de: "Übersetzung" },
  "Действие": { en: "Action", de: "Aktion" },
  "Строки не найдены.": { en: "No rows found.", de: "Keine Einträge gefunden." },
  "переведено": { en: "translated", de: "übersetzt" },
  "осталось": { en: "missing", de: "fehlend" },
  "покрытие": { en: "coverage", de: "Abdeckung" },
  "показать готовые": { en: "show translated", de: "übersetzte anzeigen" },
  "показать без перевода": { en: "show missing", de: "fehlende anzeigen" },
  "показать все": { en: "show all", de: "alle anzeigen" },
  "Группа": { en: "Group", de: "Gruppe" },
  "Параметр": { en: "Parameter", de: "Parameter" },
  "Сохранить": { en: "Save", de: "Speichern" },
  "изменено": { en: "changed", de: "geändert" },
  "сохранение…": { en: "saving…", de: "speichert…" },
  "сохранено": { en: "saved", de: "gespeichert" },

  // ---- references ----
  "поиск по CAN, gateway, W164…": { en: "search CAN, gateway, W164…", de: "CAN, Gateway, W164 suchen…" },
  "Все теги": { en: "All tags", de: "Alle Tags" },
  "Все кузова": { en: "All bodies", de: "Alle Baureihen" },
  "Ссылки не найдены.": { en: "No links found.", de: "Keine Links gefunden." },
  "ссылок": { en: "links", de: "Links" },
  "Mercedes network": { en: "Mercedes network", de: "Mercedes-Netzwerk" },
  "CAN": { en: "CAN", de: "CAN" },
  "адаптеры": { en: "adapters", de: "Adapter" },
  "Проверенные CAN факты": { en: "Reviewed CAN facts", de: "Geprüfte CAN-Fakten" },
  "CAN факты не найдены.": { en: "No CAN facts found.", de: "Keine CAN-Fakten gefunden." },
  "фактов": { en: "facts", de: "Fakten" },
  "CAN ID": { en: "CAN ID", de: "CAN-ID" },
  "кузовов": { en: "bodies", de: "Baureihen" },
  "Источник": { en: "Source", de: "Quelle" },

  // ---- DTC ----
  "Считать ошибки": { en: "Read faults", de: "Fehler lesen" },
  "Сбросить": { en: "Clear", de: "Löschen" },
  "Код": { en: "Code", de: "Code" },
  "Статус": { en: "Status", de: "Status" },
  "Описание": { en: "Description", de: "Beschreibung" },
  "raw": { en: "raw", de: "raw" },
  "Ошибок не найдено.": { en: "No faults found.", de: "Keine Fehler gefunden." },
  "Блок ответил: ошибок нет": { en: "ECU answered: no faults", de: "Steuergerät antwortete: keine Fehler" },
  "Нет ответа от блока": { en: "No response from the ECU", de: "Keine Antwort vom Steuergerät" },
  "Блок на связи, но не отдаёт ошибки": { en: "ECU is on the bus but won't report faults", de: "Steuergerät am Bus, meldet aber keine Fehler" },
  "Ошибка адаптера": { en: "Adapter error", de: "Adapterfehler" },
  "на связи": { en: "on the bus", de: "am Bus" },
  "нет DTC-сервиса": { en: "no DTC service", de: "kein DTC-Dienst" },
  "часть блоков не опрошена (ошибка адаптера)": { en: "some ECUs not probed (adapter error)", de: "einige Steuergeräte nicht abgefragt (Adapterfehler)" },
  "Лог обмена": { en: "Traffic log", de: "Datenverkehr-Log" },
  "авто": { en: "auto", de: "auto" },
  "Копировать": { en: "Copy", de: "Kopieren" },
  "Очистить": { en: "Clear", de: "Leeren" },
  "скопировано": { en: "copied", de: "kopiert" },
  "Опросить шлюз": { en: "Query gateway", de: "Gateway abfragen" },
  "опрос шлюза…": { en: "querying gateway…", de: "Gateway-Abfrage…" },
  "комплектация (из шлюза)": { en: "configuration (from gateway)", de: "Konfiguration (vom Gateway)" },
  "блоки по конфигурации": { en: "ECUs per configuration", de: "Steuergeräte laut Konfiguration" },
  "блоки CAN-B по конфигурации": { en: "CAN-B ECUs per configuration", de: "CAN-B Steuergeräte laut Konfiguration" },
  "блоки CAN-B фактически": { en: "CAN-B ECUs actually visible", de: "CAN-B Steuergeräte tatsächlich sichtbar" },
  "декодировано": { en: "decoded", de: "dekodiert" },
  "расхождение": { en: "difference", de: "Abweichung" },
  "только CAN-Ist": { en: "CAN-Ist only", de: "nur CAN-Ist" },
  "только CAN-Soll": { en: "CAN-Soll only", de: "nur CAN-Soll" },
  "из шлюза": { en: "from gateway", de: "vom Gateway" },
  "ещё не опрошен": { en: "not probed yet", de: "noch nicht abgefragt" },
  "Шлюз дал блоков: ": { en: "Gateway reported ECUs: ", de: "Gateway meldete Steuergeräte: " },
  "CAN-B из шлюза: ": { en: "CAN-B from gateway: ", de: "CAN-B vom Gateway: " },
  "с CAN id: ": { en: "with CAN id: ", de: "mit CAN-ID: " },
  "Шлюз не вернул установленные блоки": { en: "Gateway returned no installed ECUs", de: "Gateway meldete keine verbauten Steuergeräte" },
  "CAN-B конфигурация не вернула блоки": { en: "CAN-B configuration returned no ECUs", de: "CAN-B Konfiguration meldete keine Steuergeräte" },
  "Нажми на код ошибки, чтобы провалиться в диагностику.": { en: "Click a fault code to drill into diagnostics.", de: "Auf einen Fehlercode klicken, um in die Diagnose einzutauchen." },
  "Связанные группы измерений": { en: "Linked measurement groups", de: "Verknüpfte Messwertgruppen" },
  "Связанные процедуры": { en: "Linked procedures", de: "Verknüpfte Prozeduren" },
  "Схемы диагностики": { en: "Diagnostic schematics", de: "Diagnoseschemata" },
  "Материалы StarFinder": { en: "StarFinder materials", de: "StarFinder-Materialien" },
  "Документы": { en: "Documents", de: "Dokumente" },
  "Изображения": { en: "Images", de: "Bilder" },
  "Открыть": { en: "Open", de: "Öffnen" },
  "Закрыть": { en: "Close", de: "Schließen" },
  "StarFinder не подключён — задай MACDIAG_STARFINDER_DIR и перезапусти backend.": { en: "StarFinder not connected — set MACDIAG_STARFINDER_DIR and restart the backend.", de: "StarFinder nicht verbunden — MACDIAG_STARFINDER_DIR setzen und Backend neu starten." },
  "Выбери модуль в списке сверху — распиновка привязана к блоку.": { en: "Select a module above — the pinout is tied to the ECU.", de: "Modul oben wählen — die Steckerbelegung ist an das Steuergerät gebunden." },
  "Для этого блока распиновка пока не привязана.": { en: "No pinout mapped for this ECU yet.", de: "Für dieses Steuergerät ist noch keine Steckerbelegung hinterlegt." },
  "Ошибка:": { en: "Error:", de: "Fehler:" },
  "Ошибка: ": { en: "Error: ", de: "Fehler: " },
  "Сбросить коды ошибок в выбранном модуле?": { en: "Clear fault codes in the selected module?", de: "Fehlercodes im gewählten Modul löschen?" },
  "Ошибки сброшены": { en: "Faults cleared", de: "Fehler gelöscht" },

  // ---- modules ----
  "Модуль": { en: "Module", de: "Modul" },
  "Прот.": { en: "Prot.", de: "Prot." },
  "Шина": { en: "Bus", de: "Bus" },
  "Деталь": { en: "Part", de: "Teil" },
  "Шасси": { en: "Chassis", de: "Baureihe" },
  "Полный каталог ЭБУ из Vediamo (CBF)": { en: "Full ECU catalog from Vediamo (CBF)", de: "Vollständiger Steuergeräte-Katalog aus Vediamo (CBF)" },
  "поиск по имени ЭБУ…": { en: "search by ECU name…", de: "Suche nach Steuergerätename…" },
  "из": { en: "of", de: "von" },
  "— выбери модуль —": { en: "— select a module —", de: "— Modul wählen —" },
  "Нет модулей для этого шасси": { en: "No modules for this chassis", de: "Keine Module für diese Baureihe" },
  "Бэкенд недоступен": { en: "Backend unavailable", de: "Backend nicht verfügbar" },
  ". Запусти uvicorn backend.main:app": { en: ". Run uvicorn backend.main:app", de: ". uvicorn backend.main:app starten" },
  "из Vediamo CBF": { en: "from Vediamo CBF", de: "aus Vediamo CBF" },
  "стандартная адресация, требует проверки": { en: "standard addressing, needs verification", de: "Standardadressierung, zu prüfen" },
  "нет CAN id в CBF": { en: "no CAN id in CBF", de: "keine CAN-ID im CBF" },
  "ID": { en: "ID", de: "ID" },
  "Код ": { en: "Code ", de: "Code " },

  // ---- coding ----
  "⚠ Кодирование меняет настройки ЭБУ. Неверные значения могут вывести модуль из строя. Сначала прочитай текущее.":
    { en: "⚠ Coding changes ECU settings. Wrong values may disable the module. Read the current value first.",
      de: "⚠ Die Codierung ändert Steuergeräte-Einstellungen. Falsche Werte können das Modul unbrauchbar machen. Zuerst den aktuellen Wert lesen." },
  "— нажми «Домены» —": { en: '— click "Domains" —', de: "— „Domänen“ klicken —" },
  "Домены": { en: "Domains", de: "Domänen" },
  "LID (авто из CBF)": { en: "LID (auto from CBF)", de: "LID (auto aus CBF)" },
  "из CBF": { en: "from CBF", de: "aus CBF" },
  "⤓ Прочитать с авто": { en: "⤓ Read from car", de: "⤓ Vom Auto lesen" },
  "или строка hex вручную": { en: "or hex string manually", de: "oder Hex-String manuell" },
  "Декодировать": { en: "Decode", de: "Decodieren" },
  "⤒ Записать": { en: "⤒ Write", de: "⤒ Schreiben" },
  "Текущая строка:": { en: "Current string:", de: "Aktueller String:" },
  "Параметр": { en: "Parameter", de: "Parameter" },
  "Бит": { en: "Bit", de: "Bit" },
  "Значение": { en: "Value", de: "Wert" },
  "Расширенное · ручная запись DID": { en: "Advanced · manual DID write", de: "Erweitert · manuelles DID-Schreiben" },
  "DID (hex)": { en: "DID (hex)", de: "DID (hex)" },
  "напр. F198": { en: "e.g. F198", de: "z.B. F198" },
  "Значение (hex)": { en: "Value (hex)", de: "Wert (hex)" },
  "напр. 01A2": { en: "e.g. 01A2", de: "z.B. 01A2" },
  "Уровень": { en: "Level", de: "Stufe" },
  "🔓 Разблокировать": { en: "🔓 Unlock", de: "🔓 Entsperren" },
  "Записать DID": { en: "Write DID", de: "DID schreiben" },
  "CBF недоступны (MACDIAG_CBF_DIR)": { en: "CBF unavailable (MACDIAG_CBF_DIR)", de: "CBF nicht verfügbar (MACDIAG_CBF_DIR)" },
  "парам.": { en: "params", de: "Param." },
  "Выбери домен": { en: "Select a domain", de: "Domäne wählen" },
  "Записать значение в ЭБУ? Это может изменить поведение модуля.": { en: "Write value to ECU? This may change module behavior.", de: "Wert ins Steuergerät schreiben? Das kann das Modulverhalten ändern." },
  "OK: значение записано.": { en: "OK: value written.", de: "OK: Wert geschrieben." },
  " (после 0x27)": { en: " (after 0x27)", de: " (nach 0x27)" },
  "Записать строку кодирования в ЭБУ? При необходимости будет выполнена разблокировка 0x27.":
    { en: "Write coding string to ECU? Security unlock 0x27 will be performed if required.",
      de: "Codier-String ins Steuergerät schreiben? Bei Bedarf wird 0x27-Entsperrung ausgeführt." },
  "✓ Записано через ": { en: "✓ Written via ", de: "✓ Geschrieben über " },
  "разблокировка=": { en: "unlock=", de: "Entsperrung=" },
  "Ошибка записи: ": { en: "Write error: ", de: "Schreibfehler: " },
  "Сначала декодируй/прочитай домен": { en: "Decode/read a domain first", de: "Zuerst Domäne decodieren/lesen" },
  "🔓 Разблокировано · L": { en: "🔓 Unlocked · L", de: "🔓 Entsperrt · L" },
  "алгоритм=": { en: "algorithm=", de: "Algorithmus=" },
  "Уровни ЭБУ: ": { en: "ECU levels: ", de: "Steuergerät-Stufen: " },
  "нет в БД": { en: "not in DB", de: "nicht in DB" },
  "Ошибка разблокировки: ": { en: "Unlock error: ", de: "Entsperrfehler: " },

  // ---- footer ----
  "режим переключается в шапке (Эмулятор / Железо)": { en: "mode is switched in the header (Simulator / Hardware)", de: "Modus wird oben umgeschaltet (Simulator / Hardware)" },
};

let LANG = localStorage.getItem("macdiag_lang") || "ru";
window.LANG = LANG;

function t(key) {
  if (key == null) return key;
  if (LANG === "ru") return key;
  const e = I18N[key];
  return (e && e[LANG]) != null ? e[LANG] : key;
}
window.t = t;

function applyI18n() {
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.placeholder = t(el.getAttribute("data-i18n-ph"));
  });
  document.querySelectorAll("#langSeg button").forEach((b) =>
    b.classList.toggle("active", b.dataset.lang === LANG));
}
window.applyI18n = applyI18n;

function setLang(l) {
  if (l === LANG) return;
  LANG = l; window.LANG = l;
  localStorage.setItem("macdiag_lang", l);
  applyI18n();
  if (typeof window.onLangChange === "function") window.onLangChange();
}

document.querySelectorAll("#langSeg button").forEach((b) =>
  (b.onclick = () => setLang(b.dataset.lang)));

applyI18n();
