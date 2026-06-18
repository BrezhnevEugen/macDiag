import React from 'react';
import { Icon } from './icons.jsx';
import { macDiagData } from './data.js';
// macDiag Modern — screen content. Uses modern class-based layout + shared data.
const Ic = Icon;
const D = () => macDiagData;

function SectionHead({ title, meta }) {
  return (
    <div className="mac-sec-head">
      <h2>{title}</h2>
      <span className="mac-sec-rule"></span>
      {meta && <span className="mac-sec-meta">{meta}</span>}
    </div>
  );
}

function ConnectGate({ children }) {
  return <div className="mac-empty">Подключись к авто, чтобы продолжить. Нажми «Подключить» вверху.</div>;
}

const METRIC_ICONS = ["zap", "activity", "gauge", "cpu"];

// DAS-style functional groups for the ECU scan list.
const ECU_GROUPS = [
  { id: "powertrain", label: "Двигатель и трансмиссия", icon: "activity" },
  { id: "chassis",    label: "Шасси и тормоза",         icon: "gauge" },
  { id: "body",       label: "Кузов, доступ и безопасность", icon: "cpu" },
  { id: "info",       label: "Информация и комбинация",  icon: "sliders" },
];

function EcuGroups({ modules, onOpenDtc }) {
  return (
    <>
      {ECU_GROUPS.map((g) => {
        const items = modules.filter((m) => m.group === g.id);
        if (!items.length) return null;
        const faults = items.reduce((s, m) => s + (m.faults > 0 ? m.faults : 0), 0);
        return (
          <div className="mac-ecu-group" key={g.id}>
            <div className="mac-ecu-grouphead">
              <span className="gi"><Ic name={g.icon} size={15} /></span>
              <h3>{g.label}</h3>
              <span className="gc">{items.length} ЭБУ{faults ? ` · ${faults} ошиб.` : ""}</span>
              <span className="grule"></span>
            </div>
            <div className="mac-ecu-grid">
              {items.map((m) => (
                <button key={m.name} className="mac-ecu" onClick={() => m.faults > 0 && onOpenDtc(m.name)}>
                  <div className="mac-ecu-top">
                    <span className="mac-statusdot on sm"></span>
                    <span className="mac-ecu-name">{m.name}</span>
                    <span className={"mac-proto " + m.proto}>{m.proto}</span>
                    {m.faults > 0 && <span className="mac-faults">{m.faults}</span>}
                  </div>
                  <div className="mac-ecu-meta">{m.part} · {m.bus}</div>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </>
  );
}

// live sparkline: smooth polyline + soft area fill, autoscaled to the series.
function Sparkline({ points, w = 150, h = 38 }) {
  if (!points || points.length < 2) return null;
  const min = Math.min(...points), max = Math.max(...points);
  const span = max - min || 1;
  const pad = span * 0.18;
  const lo = min - pad, hi = max + pad, range = hi - lo || 1;
  const step = w / (points.length - 1);
  const xy = points.map((p, i) => [i * step, h - ((p - lo) / range) * h]);
  const line = xy.map(([x, y], i) => (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1)).join(" ");
  const area = line + ` L${w} ${h} L0 ${h} Z`;
  const id = "sg" + Math.round(xy[0][1] * 1000) + points.length;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: "block", marginTop: 10 }}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${id})`} />
      <path d={line} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      <circle cx={xy[xy.length - 1][0]} cy={xy[xy.length - 1][1]} r="2.6" fill="var(--accent)" />
    </svg>
  );
}

function Overview({ connected, onOpenDtc }) {
  const data = D();
  const [scanned, setScanned] = React.useState(false);
  const [scanning, setScanning] = React.useState(false);
  React.useEffect(() => { if (!connected) setScanned(false); }, [connected]);
  function scan() { setScanning(true); setTimeout(() => { setScanning(false); setScanned(true); }, 850); }

  if (!connected) return <ConnectGate />;

  return (
    <>
      <div className="mac-section">
        <div className="mac-veh mac-panel">
          <div className="mac-veh-art"><Ic name="car" size={40} /></div>
          <div className="mac-veh-info">
            <div className="vmodel">{data.vehicle.model}</div>
            <div className="vvin">{data.vehicle.vin}</div>
            <div className="vrow">
              <span className="mac-chip">{data.vehicle.chassis}</span>
              <span className="mac-chip">{data.adapter}</span>
              <span className="mac-chip">{data.bus}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="mac-section">
        <SectionHead title="Состояние" meta="обновлено только что" />
        <div className="mac-metric-grid">
          {data.metrics.map((m, i) => (
            <div className="mac-metric" key={i}>
              <div className="mac-metric-top">{m.label}<span className="mac-metric-ic"><Ic name={METRIC_ICONS[i % 4]} size={16} /></span></div>
              <div className="mac-metric-val">{m.value}{m.unit && <small>{m.unit}</small>}</div>
              {m.hint && <div className="mac-metric-sub">{m.hint}</div>}
            </div>
          ))}
        </div>
      </div>

      <div className="mac-section">
        <div className="mac-sec-head">
          <h2>Блоки управления</h2>
          <span className="mac-sec-rule"></span>
          <button className="mac-btn" onClick={scan} disabled={scanning}>
            {scanning ? <span className="mac-spin"></span> : <Ic name="zap" size={15} />}
            {scanning ? "Сканирую…" : "Сканировать"}
          </button>
        </div>
        {scanned ? (
          <EcuGroups modules={data.modules} onOpenDtc={onOpenDtc} />
        ) : (
          <div className="mac-empty">Нажми «Сканировать», чтобы опросить все ЭБУ шасси {data.vehicle.chassis}.</div>
        )}
      </div>
    </>
  );
}

function Live({ connected }) {
  const data = D();
  const [run, setRun] = React.useState(false);
  // one decimal-aware numeric series per gauge
  const seeds = React.useMemo(() => data.gauges.map((g) => {
    const base = parseFloat(g.value);
    const decimals = (g.value.split(".")[1] || "").length;
    const amp = Math.max(Math.abs(base) * 0.06, decimals ? 0.05 : 1);
    return { base, decimals, amp, series: Array.from({ length: 26 }, (_, i) => base + Math.sin(i / 2.4) * amp * (0.5 + Math.random() * 0.5)) };
  }), []);
  const [series, setSeries] = React.useState(() => seeds.map((s) => s.series));

  React.useEffect(() => {
    if (!run) return;
    const t = setInterval(() => {
      setSeries((prev) => prev.map((arr, gi) => {
        const s = seeds[gi];
        const last = arr[arr.length - 1];
        let next = last + (Math.random() - 0.5) * s.amp * 1.4 + (s.base - last) * 0.12;
        return [...arr.slice(1), next];
      }));
    }, 1100);
    return () => clearInterval(t);
  }, [run]);

  if (!connected) return <ConnectGate />;
  const fmt = (v, d) => v.toFixed(d);

  return (
    <>
      <div className="mac-toolbar">
        <label className="mac-field"><span>ЭБУ</span>
          <select className="mac-select" defaultValue="ME97" style={{ minWidth: 150 }}><option>ME97</option><option>CRD3</option><option>ESP9MFA</option></select></label>
        <label className="mac-field"><span>Группа измерений</span>
          <select className="mac-select" defaultValue="boost" style={{ minWidth: 300 }}><option value="boost">Überprüfung des Ladedrucksystems</option></select></label>
        <button className={"mac-btn" + (run ? " danger" : "")} onClick={() => setRun((r) => !r)}>
          <Ic name={run ? "x" : "activity"} size={15} />{run ? "Остановить" : "Запустить"}
        </button>
        {run && <span className="mac-chip" style={{ alignSelf: "center", display: "inline-flex", alignItems: "center", gap: 6 }}><span className="mac-statusdot on sm"></span>поток · 1 Гц</span>}
      </div>
      {run ? (
        <div className="mac-gauge-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
          {data.gauges.map((g, i) => (
            <div className="mac-gauge" key={i}>
              <div className="mac-gauge-lbl">{g.label}</div>
              <div className="mac-gauge-val">{fmt(series[i][series[i].length - 1], seeds[i].decimals)}<small>{g.unit}</small></div>
              <Sparkline points={series[i]} />
              <div className="mac-gauge-sub">{g.sub}</div>
            </div>
          ))}
        </div>
      ) : <div className="mac-empty">Выбери ЭБУ и группу измерений, затем «Запустить» — пойдёт живой поток с графиками.</div>}
    </>
  );
}

// generic-but-plausible diagnostic hints, keyed by DTC class letter.
function dtcHints(code) {
  const k = (code[0] || "").toUpperCase();
  const map = {
    B: { causes: ["Обрыв или короткое в цепи компонента", "Окисление контактов разъёма", "Неисправен сам компонент (лампа/привод)", "Повреждение проводки в жгуте"],
         steps: ["Проверь разъём и контакты модуля", "Прозвони цепь компонента на обрыв/КЗ", "Замени неисправный компонент", "Сбрось код и проверь повторно"] },
    C: { causes: ["Нет сигнала с датчика", "Загрязнение/смещение датчика", "Ошибка калибровки", "Проблема питания датчика"],
         steps: ["Проверь установку и зазор датчика", "Считай live-данные датчика", "Выполни калибровку (если требуется)", "Сбрось код и проверь на ходу (на стенде)"] },
    P: { causes: ["Подсос воздуха / негерметичность", "Загрязнение или износ компонента", "Отклонение топливоподачи", "Сбой исполнительного механизма"],
         steps: ["Проверь патрубки и герметичность", "Сними freeze-frame и сравни с лимитами", "Проверь исполнительный механизм актуатором", "Сбрось и проверь под нагрузкой"] },
    U: { causes: ["Потеря связи по шине CAN", "Повреждение CAN-проводки", "Неисправен один из ЭБУ на шине", "Проблема питания/массы модуля"],
         steps: ["Проверь питание и массу модуля", "Замерь сопротивление шины CAN (~60 Ом)", "Опроси шлюз и соседние ЭБУ", "Сбрось и перепроверь связь"] },
  };
  return map[k] || map.B;
}

function DtcDetail({ row, module, onBack }) {
  const data = D();
  const mod = data.modules.find((m) => m.name === module) || {};
  const hints = dtcHints(row.code);
  const active = row.status === "активна";
  const frame = [
    { l: "Обороты", v: "812", u: "об/мин" },
    { l: "Темп. ОЖ", v: "88", u: "°C" },
    { l: "Напряжение", v: "13.9", u: "В" },
    { l: "Пробег", v: "184 320", u: "км" },
  ];
  return (
    <div className="mac-panel">
      <div className="mac-dtc-head">
        <span className="mac-dtc-code">{row.code}</span>
        <span className="mac-sevdot"><i style={{ background: active ? "var(--danger)" : "var(--warn)" }}></i>{row.status}</span>
        <span className={"mac-proto " + (mod.proto || "uds")}>{(mod.proto || "uds")}</span>
        <span className="mac-chip">{module}</span>
        <span className="mac-dtc-actions">
          <button className="mac-btn ghost" onClick={onBack}><Ic name="chevron" size={15} style={{ transform: "rotate(180deg)" }} />Назад</button>
          <button className="mac-btn danger"><Ic name="refresh" size={15} />Сбросить код</button>
        </span>
      </div>
      <p style={{ fontSize: 15, color: "var(--txt)", margin: "10px 0 2px", fontWeight: 500 }}>{row.desc}</p>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--muted)" }}>raw: {row.raw} · TX {mod.tx} · RX {mod.rx} · {mod.bus}</div>

      <div className="mac-subcard" style={{ marginTop: 20 }}>
        <h3>Условия фиксации (freeze frame)</h3>
        <div className="mac-mini-grid">
          {frame.map((f, i) => <div className="mac-mini" key={i}><div className="l">{f.l}</div><div className="v">{f.v}<small>{f.u}</small></div></div>)}
        </div>
      </div>

      <div className="mac-detail-grid">
        <div className="mac-subcard">
          <h3>Возможные причины</h3>
          <ul className="mac-list causes">{hints.causes.map((c, i) => <li key={i}><span className="mk"></span>{c}</li>)}</ul>
        </div>
        <div className="mac-subcard">
          <h3>Рекомендуемые шаги</h3>
          <ul className="mac-list steps">{hints.steps.map((s, i) => <li key={i}><span className="mk">{i + 1}</span>{s}</li>)}</ul>
        </div>
      </div>
    </div>
  );
}

function Dtc({ connected, initialModule }) {
  const data = D();
  const withFaults = data.modules.filter((m) => m.faults > 0);
  const [mod, setMod] = React.useState(initialModule || (withFaults[0] && withFaults[0].name) || "ESP9MFA");
  const [read, setRead] = React.useState(!!initialModule);
  const [sel, setSel] = React.useState(null);
  React.useEffect(() => { if (initialModule) { setMod(initialModule); setRead(true); setSel(null); } }, [initialModule]);
  const rows = (read && data.dtc[mod]) || [];
  if (!connected) return <ConnectGate />;

  if (sel) return <DtcDetail row={sel} module={mod} onBack={() => setSel(null)} />;

  return (
    <>
      <div className="mac-toolbar">
        <label className="mac-field"><span>Модуль</span>
          <select className="mac-select" value={mod} onChange={(e) => { setMod(e.target.value); setRead(false); }} style={{ minWidth: 170 }}>
            {data.modules.map((m) => <option key={m.name} value={m.name}>{m.name}</option>)}
          </select></label>
        <button className="mac-btn" onClick={() => setRead(true)}><Ic name="download" size={15} />Считать ошибки</button>
        <button className="mac-btn danger" disabled={!read || rows.length === 0}><Ic name="refresh" size={15} />Сбросить</button>
      </div>
      {read && rows.length > 0 && (
        <>
          <div className="mac-table-wrap">
            <table className="mac-table">
              <thead><tr><th>Код</th><th>Статус</th><th>Описание</th><th>raw</th><th></th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="clickable" onClick={() => setSel(r)}>
                    <td><code>{r.code}</code></td>
                    <td><span className="mac-sevdot"><i style={{ background: r.status === "активна" ? "var(--danger)" : "var(--warn)" }}></i>{r.status}</span></td>
                    <td>{r.desc}</td>
                    <td><code style={{ color: "var(--muted)" }}>{r.raw}</code></td>
                    <td style={{ textAlign: "right", color: "var(--muted)" }}><Ic name="chevron" size={16} style={{ verticalAlign: "middle" }} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mac-empty" style={{ marginTop: 12 }}>Нажми на строку ошибки, чтобы открыть карточку с условиями фиксации и диагностикой.</p>
        </>
      )}
      {read && rows.length === 0 && <div className="mac-banner ok"><Ic name="gauge" size={18} />Ошибок в модуле {mod} не найдено.</div>}
      {!read && <div className="mac-empty">Выбери модуль и нажми «Считать ошибки».</div>}
    </>
  );
}

function Modules() {
  const data = D();
  const [chassis, setChassis] = React.useState("");
  const [q, setQ] = React.useState("");
  const rows = data.modules.filter((m) => (!chassis || m.chassis === chassis) && (!q || m.name.toLowerCase().includes(q.toLowerCase())));
  return (
    <>
      <div className="mac-toolbar">
        <label className="mac-field"><span>Шасси</span>
          <select className="mac-select" value={chassis} onChange={(e) => setChassis(e.target.value)}>
            <option value="">Все шасси</option><option value="W221">W221 (S-Class)</option><option value="X164">X164 (GL-Class)</option>
          </select></label>
        <label className="mac-field" style={{ flex: 1, minWidth: 200 }}><span>Поиск</span>
          <input className="mac-input" placeholder="имя ЭБУ…" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <span className="mac-chip" style={{ alignSelf: "center" }}>{rows.length} ЭБУ</span>
      </div>
      <div className="mac-table-wrap">
        <table className="mac-table">
          <thead><tr><th>Модуль</th><th>Прот.</th><th>TX</th><th>RX</th><th>Шина</th><th>Шасси</th><th>Деталь</th></tr></thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.name}>
                <td style={{ fontWeight: 600 }}>{m.name}</td>
                <td><span className={"mac-proto " + m.proto}>{m.proto}</span></td>
                <td><code>{m.tx}</code></td><td><code>{m.rx}</code></td>
                <td>{m.bus}</td><td style={{ color: "var(--muted)" }}>{m.chassis}</td>
                <td><code style={{ color: "var(--txt-2)" }}>{m.part}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mac-empty" style={{ marginTop: 14 }}>Реальные CAN ID из comparam-таблиц Caesar (CBF Vediamo). Кузовные модули X164 на 83.3k — через шлюз ZGW.</p>
    </>
  );
}

function Coding({ connected }) {
  const data = D();
  const c = data.coding;
  const [decoded, setDecoded] = React.useState(false);
  const [params, setParams] = React.useState(c.params);
  function setOpt(i, v) { setParams((p) => p.map((row, idx) => idx === i ? { ...row, value: v } : row)); }
  return (
    <>
      <div className="mac-banner"><Ic name="alert" size={18} />Кодирование меняет настройки ЭБУ. Неверные значения могут вывести модуль из строя. Сначала прочитай текущее.</div>
      <div className="mac-toolbar">
        <label className="mac-field"><span>Модуль</span>
          <select className="mac-select" defaultValue="KI164" style={{ minWidth: 130 }}>{data.modules.map((m) => <option key={m.name}>{m.name}</option>)}</select></label>
        <label className="mac-field"><span>Домен</span>
          <select className="mac-select" defaultValue={c.domain} style={{ minWidth: 250 }}><option>{c.domain}</option></select></label>
        <label className="mac-field"><span>LID</span><input className="mac-input" defaultValue={c.lid} style={{ width: 84 }} /></label>
        <span className="mac-tb-actions">
          <button className="mac-btn" onClick={() => setDecoded(true)} disabled={!connected}><Ic name="download" size={15} />Прочитать с авто</button>
          <button className="mac-btn ghost" onClick={() => setDecoded(true)}>Декодировать</button>
          <button className="mac-btn danger" disabled={!decoded}><Ic name="upload" size={15} />Записать</button>
        </span>
      </div>
      {decoded ? (
        <div className="mac-table-wrap">
          <table className="mac-table">
            <thead><tr><th>Параметр</th><th>Бит</th><th>Значение</th></tr></thead>
            <tbody>
              {params.map((p, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{p.name}</td>
                  <td><code style={{ color: "var(--muted)" }}>{p.bit}</code></td>
                  <td><select className="mac-select" value={p.value} onChange={(e) => setOpt(i, e.target.value)} style={{ minWidth: 200 }}>{p.options.map((o) => <option key={o}>{o}</option>)}</select></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <div className="mac-empty">Выбери домен и нажми «Декодировать» — параметры покажутся списком с опциями. Текущая строка: <code style={{ fontFamily: "var(--font-mono)", color: "var(--accent-2)" }}>{c.string}</code></div>}
    </>
  );
}

// deterministic pseudo-bytes: a shared "base" image + per-file mutations,
// so two dumps look like near-identical firmware differing in a few bytes.
function hashStr(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
function rng(seed) { let s = seed >>> 0; return () => { s = (Math.imul(s, 1664525) + 1013904223) >>> 0; return s / 4294967296; }; }
function fileBytes(name, len) {
  const base = rng(0xBADC0DE); const out = new Array(len);
  for (let i = 0; i < len; i++) out[i] = Math.floor(base() * 256);
  const mut = rng(hashStr(name)); const n = 5 + Math.floor(mut() * 5);
  for (let i = 0; i < n; i++) { const p = Math.floor(mut() * len); out[p] = Math.floor(mut() * 256); }
  return out;
}
const hx = (n) => n.toString(16).toUpperCase().padStart(2, "0");
const asc = (n) => (n >= 32 && n < 127) ? String.fromCharCode(n) : ".";

function HexPane({ tag, name, bytes, diff, perRow = 16 }) {
  const rows = [];
  for (let r = 0; r * perRow < bytes.length; r++) {
    const off = r * perRow;
    const slice = bytes.slice(off, off + perRow);
    rows.push(
      <div className="mac-hex-row" key={r}>
        <span className="mac-hex-off">{off.toString(16).toUpperCase().padStart(4, "0")}</span>
        <span className="mac-hex-bytes">{slice.map((b, i) => <b key={i} className={diff.has(off + i) ? "df" : ""}>{hx(b)} </b>)}</span>
        <span className="mac-hex-ascii">{slice.map((b, i) => <b key={i} className={diff.has(off + i) ? "df" : ""}>{asc(b)}</b>)}</span>
      </div>
    );
  }
  return (
    <div className="mac-hex-pane">
      <div className="mac-hex-head"><span className="tag">{tag}</span><code>{name}</code></div>
      <div className="mac-hex-body">{rows}</div>
    </div>
  );
}

function CffViewer({ name }) {
  const r = rng(hashStr(name) ^ 0x5A17);
  const ecu = name.split(/[_\.]/)[0] || "ECU";
  const part = "A " + (160 + Math.floor(r() * 90)) + " " + (100 + Math.floor(r() * 800)) + " " + Math.floor(10 + r() * 80) + " " + Math.floor(10 + r() * 80);
  const sw = "00" + (30 + Math.floor(r() * 9)) + " / " + String(Math.floor(r() * 30)).padStart(2, "0");
  // segment sizes (KB) → proportional map
  const app = 1200 + Math.floor(r() * 900), par = 120 + Math.floor(r() * 260), boot = 48 + Math.floor(r() * 64);
  const total = app + par + boot;
  const fmtKB = (kb) => kb >= 1024 ? (kb / 1024).toFixed(2) + " МБ" : kb + " КБ";
  const crc = () => "0x" + Math.floor(r() * 0xFFFF).toString(16).toUpperCase().padStart(4, "0");
  const segs = [
    { key: "app",  cls: "mac-cff-seg-app",  dot: "var(--accent)", name: "Applikation",    addr: "0x80000", size: app,  ver: sw },
    { key: "par",  cls: "mac-cff-seg-par",  dot: "var(--ok)",     name: "Parameterdaten", addr: "0x9C000", size: par,  ver: "—" },
    { key: "boot", cls: "mac-cff-seg-boot", dot: "var(--warn)",   name: "Bootloader",     addr: "0xA0000", size: boot, ver: "BL 4.2" },
  ];
  return (
    <div className="mac-section" style={{ marginTop: 18 }}>
      <SectionHead title="CFF Viewer" meta="структура контейнера прошивки · read-only" />
      <div className="mac-panel">
        <div className="mac-cff-hdr">
          <div className="mac-mini"><div className="l">ЭБУ</div><div className="v">{ecu}</div></div>
          <div className="mac-mini"><div className="l">Номер детали</div><div className="v" style={{ fontSize: 14, fontFamily: "var(--font-mono)" }}>{part}</div></div>
          <div className="mac-mini"><div className="l">Версия ПО</div><div className="v">{sw}</div></div>
          <div className="mac-mini"><div className="l">Формат</div><div className="v" style={{ fontSize: 14 }}>CFF · Caesar</div></div>
          <div className="mac-mini"><div className="l">Образ</div><div className="v" style={{ fontSize: 13 }}>{fmtKB(total)}</div></div>
        </div>

        <div className="mac-cff-map">
          {segs.map((s) => <div key={s.key} className={s.cls} style={{ width: (s.size / total * 100) + "%" }}>{s.size / total > 0.12 ? s.name : ""}</div>)}
        </div>

        <table className="mac-table" style={{ border: "1px solid var(--line)", borderRadius: "var(--r-tile)", overflow: "hidden" }}>
          <thead><tr><th>Сегмент</th><th>Адрес</th><th>Размер</th><th>SW-версия</th><th>CRC</th></tr></thead>
          <tbody>
            {segs.map((s) => (
              <tr key={s.key}>
                <td><span className="mac-seg-dot" style={{ background: s.dot }}></span>{s.name}</td>
                <td><code>{s.addr}</code></td>
                <td>{fmtKB(s.size)}</td>
                <td>{s.ver}</td>
                <td><code style={{ color: "var(--muted)" }}>{crc()}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HexCompare({ dumps, initial, onClose }) {
  const names = dumps.map((d) => d.name);
  const [a, setA] = React.useState(initial || names[0]);
  const [b, setB] = React.useState(names[1] || names[0]);
  const LEN = 256;
  const ba = React.useMemo(() => fileBytes(a, LEN), [a]);
  const bb = React.useMemo(() => fileBytes(b, LEN), [b]);
  const diff = React.useMemo(() => { const s = new Set(); for (let i = 0; i < LEN; i++) if (ba[i] !== bb[i]) s.add(i); return s; }, [ba, bb]);
  return (
    <>
      <button className="mac-btn ghost" onClick={onClose} style={{ marginBottom: 14 }}><Ic name="chevron" size={15} style={{ transform: "rotate(180deg)" }} />Назад к дампам</button>
      <div className="mac-hex-bar">
        <label className="mac-field"><span>Файл A</span>
          <select className="mac-select" value={a} onChange={(e) => setA(e.target.value)} style={{ minWidth: 220 }}>{names.map((n) => <option key={n}>{n}</option>)}</select></label>
        <label className="mac-field"><span>Файл B</span>
          <select className="mac-select" value={b} onChange={(e) => setB(e.target.value)} style={{ minWidth: 220 }}>{names.map((n) => <option key={n}>{n}</option>)}</select></label>
        <span className="mac-diffcount" style={{ alignSelf: "center", marginLeft: "auto" }}>Различий: <b>{diff.size}</b> байт из {LEN}</span>
      </div>
      <div className="mac-hex-grid">
        <HexPane tag="A" name={a} bytes={ba} diff={diff} />
        <HexPane tag="B" name={b} bytes={bb} diff={diff} />
      </div>
      <CffViewer name={a} />
    </>
  );
}

function Flash({ connected }) {
  const data = D();
  const f = data.flash;
  const [mod, setMod] = React.useState("ME97");
  const [readVer, setReadVer] = React.useState(false);
  const [hex, setHex] = React.useState(null); // {a,b}
  const statusMeta = {
    stock:    { t: "сток",      c: "var(--txt-2)",   bg: "var(--panel-2)",     bd: "var(--line)" },
    update:   { t: "обновление",c: "var(--accent-2)",bg: "var(--uds-surface)", bd: "var(--accent-border)" },
    external: { t: "внешний диск", c: "var(--warn)", bg: "var(--warn-surface)",bd: "var(--warn-border)" },
  };
  if (!connected) return <ConnectGate />;
  if (hex) return <HexCompare dumps={f.dumps} initial={hex.a} onClose={() => { setHex(null); window.scrollTo(0, 0); }} />;
  const v = f.versions;
  return (
    <>
      <div className="mac-banner"><Ic name="alert" size={18} />Запись прошивки отключена намеренно. Неверный или прерванный флэш может вывести ЭБУ из строя — раздел работает в режиме чтения (версии, дампы, каталог).</div>

      <div className="mac-toolbar">
        <label className="mac-field"><span>Модуль</span>
          <select className="mac-select" value={mod} onChange={(e) => { setMod(e.target.value); setReadVer(false); }} style={{ minWidth: 150 }}>
            {data.modules.map((m) => <option key={m.name}>{m.name}</option>)}
          </select></label>
        <span className="mac-tb-actions">
          <button className="mac-btn" onClick={() => setReadVer(true)}><Ic name="download" size={15} />Считать версии ПО</button>
          <button className="mac-btn ghost"><Ic name="upload" size={15} />Сохранить дамп</button>
          <button className="mac-btn" disabled style={{ opacity: .5 }}><Ic name="drive" size={15} />Прошить (501)</button>
        </span>
      </div>

      {readVer && (
        <div className="mac-section">
          <SectionHead title="Текущее ПО блока" meta={mod} />
          <div className="mac-panel">
            <div className="mac-mini-grid">
              <div className="mac-mini"><div className="l">Версия ПО</div><div className="v">{v.sw}</div></div>
              <div className="mac-mini"><div className="l">Номер детали (SW)</div><div className="v" style={{ fontSize: 14, fontFamily: "var(--font-mono)" }}>{v.part}</div></div>
              <div className="mac-mini"><div className="l">Hardware</div><div className="v" style={{ fontSize: 14, fontFamily: "var(--font-mono)" }}>{v.hw}</div></div>
              <div className="mac-mini"><div className="l">Bootloader</div><div className="v">{v.boot}</div></div>
              <div className="mac-mini"><div className="l">CFF-образ</div><div className="v" style={{ fontSize: 13, fontFamily: "var(--font-mono)" }}>{v.cff}</div></div>
              <div className="mac-mini"><div className="l">Статус</div><div className="v" style={{ color: "var(--ok)" }}>{v.state}</div></div>
            </div>
          </div>
        </div>
      )}

      <div className="mac-section">
        <SectionHead title="Каталог прошивок (CFF)" meta="чтение метаданных · скачивание образа" />
        <div className="mac-table-wrap">
          <table className="mac-table">
            <thead><tr><th>Образ</th><th>ЭБУ</th><th>Версия</th><th>Размер</th><th>Дата</th><th>Статус</th><th></th></tr></thead>
            <tbody>
              {f.library.map((r) => {
                const s = statusMeta[r.status];
                return (
                  <tr key={r.name}>
                    <td><code>{r.name}</code></td>
                    <td style={{ fontWeight: 600 }}>{r.ecu}</td>
                    <td><code style={{ color: "var(--muted)" }}>{r.ver}</code></td>
                    <td>{r.size}</td>
                    <td style={{ color: "var(--muted)" }}>{r.date}</td>
                    <td><span style={{ fontSize: 11, fontWeight: 600, padding: "2px 9px", borderRadius: "var(--r-code)", color: s.c, background: s.bg, border: "1px solid " + s.bd }}>{s.t}</span></td>
                    <td style={{ textAlign: "right" }}>
                      <button className="mac-btn ghost" style={{ height: 32, padding: "0 12px", fontSize: 12.5 }}><Ic name="download" size={14} />Скачать</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="mac-section">
        <SectionHead title="Дампы прошивок" meta={`${f.dumps.length} сохранено локально`} />
        <div style={{ margin: "-6px 0 14px" }}>
          <button className="mac-btn ghost" onClick={() => { setHex({ a: f.dumps[0].name }); window.scrollTo(0, 0); }}><Ic name="search" size={15} />Сравнить дампы в hex</button>
        </div>
        <div className="mac-ecu-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))" }}>
          {f.dumps.map((d) => (
            <div className="mac-panel" key={d.name} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                <span className="gi" style={{ width: 28, height: 28, borderRadius: 8, display: "grid", placeItems: "center", background: "var(--uds-surface)", color: "var(--accent-2)", flex: "none" }}><Ic name="drive" size={15} /></span>
                <code style={{ fontSize: 12.5, color: "var(--txt)", overflowWrap: "anywhere" }}>{d.name}</code>
              </div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span className="mac-chip">{d.ecu}</span><span className="mac-chip">{d.size}</span><span className="mac-chip">{d.date}</span>
              </div>
              <div style={{ fontSize: 12.5, color: "var(--muted)" }}>{d.note}</div>
              <div style={{ display: "flex", gap: 8, marginTop: 2 }}>
                <button className="mac-btn ghost" style={{ height: 32, padding: "0 12px", fontSize: 12.5 }}><Ic name="download" size={14} />Экспорт</button>
                <button className="mac-btn ghost" style={{ height: 32, padding: "0 12px", fontSize: 12.5 }} onClick={() => { setHex({ a: d.name }); window.scrollTo(0, 0); }}><Ic name="search" size={14} />Открыть hex</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

export { Overview, Live, Dtc, Modules, Coding, Flash };
