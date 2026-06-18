// macDiag UI kit — fake but plausible diagnostic data.
// CAN IDs taken from the real comparam tables documented in the repo README.
export const macDiagData = {
  vehicle: { vin: "WDD2211781A123456", model: "S 350 (W221) · 2008", chassis: "W221" },
  adapter: "Openport 2.0 · J2534 · 64-bit",
  bus: "CAN-C 500 kbit/s · CAN-B 83.3 kbit/s (через ZGW)",
  voltage: "13.9",
  modules: [
    { name: "EZS164", part: "A 164 540 84 45", proto: "kwp", tx: "0x4E0", rx: "0x5FF", bus: "83.3k", chassis: "X164", faults: 0, group: "body" },
    { name: "KI164",  part: "A 164 540 12 11", proto: "uds", tx: "0x5B4", rx: "0x4F4", bus: "83.3k", chassis: "X164", faults: 0, group: "info" },
    { name: "SAMV164",part: "A 164 540 55 01", proto: "kwp", tx: "0x662", rx: "0x4E2", bus: "83.3k", chassis: "X164", faults: 1, group: "body" },
    { name: "ME97",   part: "A 273 153 09 79", proto: "uds", tx: "0x7E0", rx: "0x7E8", bus: "500k",  chassis: "W221", faults: 0, group: "powertrain" },
    { name: "ESP9MFA",part: "A 164 431 03 12", proto: "kwp", tx: "0x632", rx: "0x486", bus: "500k",  chassis: "X164", faults: 2, group: "chassis" },
    { name: "TCM164", part: "A 034 545 84 32", proto: "uds", tx: "0x7E1", rx: "0x7E9", bus: "500k",  chassis: "X164", faults: 0, group: "powertrain" },
    { name: "AIRMATIC",part: "A 221 320 03 89", proto: "kwp", tx: "0x612", rx: "0x4A2", bus: "500k", chassis: "W221", faults: 0, group: "chassis" },
    { name: "SRS",    part: "A 164 901 08 04", proto: "kwp", tx: "0x608", rx: "0x4C2", bus: "500k",  chassis: "X164", faults: 0, group: "body" },
  ],
  metrics: [
    { label: "Напряжение АКБ", value: "13.9", unit: "В" },
    { label: "Обороты", value: "812", unit: "об/мин", hint: "холостой ход" },
    { label: "Темп. ОЖ", value: "88", unit: "°C" },
    { label: "Найдено ЭБУ", value: "8", hint: "из 18 опрошенных" },
  ],
  dtc: {
    ESP9MFA: [
      { code: "C1525", status: "активна", desc: "Датчик угла поворота руля — нет сигнала", raw: "C1 52 5A 2E" },
      { code: "B1535", status: "сохранена", desc: "Шина CAN — потеря связи с ЭБУ ESP", raw: "B1 53 50 24" },
    ],
    SAMV164: [
      { code: "B1078", status: "сохранена", desc: "Лампа левой фары — обрыв цепи", raw: "B1 07 80 22" },
    ],
  },
  gauges: [
    { label: "Давление наддива во впускном коллекторе", value: "1182", unit: "мбар", sub: "лимит 900–1450" },
    { label: "Расход воздуха (MAF)", value: "23.4", unit: "г/с", sub: "лимит 4–62" },
    { label: "Угол опережения зажигания", value: "12.5", unit: "°", sub: "—" },
    { label: "Лямбда (банк 1)", value: "0.99", unit: "λ", sub: "0.8–1.2" },
    { label: "Температура масла", value: "94", unit: "°C", sub: "лимит ≤ 130" },
    { label: "Положение дросселя", value: "14", unit: "%", sub: "0–100" },
  ],
  coding: {
    domain: "VCD_Aktuelle_Menueeinstellungen",
    lid: "0x03",
    string: "A2 14 00 6C 01 0F 80",
    params: [
      { name: "Vmax Winterreifen", bit: "0.0–0.7", value: "210 км/ч", options: ["190 км/ч","210 км/ч","240 км/ч","270 км/ч"] },
      { name: "Uhrverstellung (часы)", bit: "1.0–1.1", value: "12h", options: ["12h","24h"] },
      { name: "Тип двигателя", bit: "1.2–1.4", value: "OM642 (CDI)", options: ["M272","M273","OM642 (CDI)"] },
      { name: "Сервисный интервал", bit: "2.0–2.3", value: "ASSYST PLUS", options: ["фикс. 15 000","ASSYST PLUS"] },
      { name: "Язык комбинации", bit: "3.0–3.3", value: "Русский", options: ["Deutsch","English","Русский","Français"] },
    ],
  },
  flash: {
    versions: {
      module: "ME97", part: "A 273 153 09 79", sw: "0034 / 12",
      hw: "A 273 153 07 79", boot: "BL 4.2", cff: "ME97_0034.cff", state: "OK",
    },
    library: [
      { name: "ME97_0034_stock.cff", ecu: "ME97", ver: "0034/12", size: "1.82 МБ", date: "2009-03-11", status: "stock" },
      { name: "ME97_0036_upd.cff",   ecu: "ME97", ver: "0036/04", size: "1.84 МБ", date: "2011-08-22", status: "update" },
      { name: "CRD3_0521.cff",       ecu: "CRD3", ver: "0521/02", size: "2.31 МБ", date: "2010-05-04", status: "stock" },
      { name: "TCM164_0212.cff",     ecu: "TCM164", ver: "0212/07", size: "0.96 МБ", date: "2009-09-30", status: "stock" },
      { name: "EZS164_0140.cff",     ecu: "EZS164", ver: "0140/01", size: "0.42 МБ", date: "2008-12-19", status: "external" },
    ],
    dumps: [
      { name: "ME97_full_2026-06-18.bin", ecu: "ME97", size: "2.00 МБ", date: "сегодня · 11:40", note: "полный дамп перед кодированием" },
      { name: "ESP9MFA_app_2026-06-12.bin", ecu: "ESP9MFA", size: "0.51 МБ", date: "12 июн · 09:14", note: "только Applikation" },
      { name: "KI164_eeprom_2026-05-30.bin", ecu: "KI164", size: "64 КБ", date: "30 мая · 16:02", note: "EEPROM (пробег/VIN)" },
    ],
  },
};
