import React from 'react';
import { Icon } from './icons.jsx';
import { apiGet, apiPost } from './api.js';
// macDiag Modern — screen content. Uses modern class-based layout + shared data.
const Ic = Icon;

function SectionHead({ title, meta }) {
  return (
    <div className="mac-sec-head">
      <h2>{title}</h2>
      <span className="mac-sec-rule"></span>
      {meta && <span className="mac-sec-meta">{meta}</span>}
    </div>
  );
}

function ConnectGate() {
  return <div className="mac-empty">Подключись к авто, чтобы продолжить. Нажми «Подключить» вверху.</div>;
}

const METRIC_ICONS = ["zap", "activity", "gauge", "cpu"];

// DAS-style functional groups for the ECU scan list (the backend tags each
// scanned module with a `group`; "other" catches anything unclassified).
const ECU_GROUPS = [
  { id: "powertrain", label: "Двигатель и трансмиссия", icon: "activity" },
  { id: "chassis",    label: "Шасси и тормоза",         icon: "gauge" },
  { id: "body",       label: "Кузов, доступ и безопасность", icon: "cpu" },
  { id: "info",       label: "Информация и комбинация",  icon: "sliders" },
  { id: "other",      label: "Прочие блоки",             icon: "cpu" },
];

function EcuCard({ m, onOpenDtc }) {
  const id = m.tx != null ? "0x" + Number(m.tx).toString(16).toUpperCase() : "—";
  const dot = m.online || m.state === "present" ? "on" : "off";
  return (
    <button className={"mac-ecu" + (m.dtc > 0 ? " hasfault" : "")} onClick={() => m.dtc > 0 && onOpenDtc(m.id)} title={m.detail || m.name}>
      <div className="mac-ecu-top">
        <span className={"mac-statusdot sm " + dot}></span>
        <span className="mac-ecu-name">{m.ecu}</span>
        <span className={"mac-proto " + m.protocol}>{m.protocol}</span>
        {m.dtc > 0 && <span className="mac-faults">{m.dtc}</span>}
      </div>
      <div className="mac-ecu-meta">{m.name}</div>
      <div className="mac-ecu-meta">{id} · {m.cbf || "—"}</div>
    </button>
  );
}

// Group the real /api/vehicle/scan modules by their backend `group` tag.
function EcuList({ modules, onOpenDtc }) {
  return (
    <>
      {ECU_GROUPS.map((g) => {
        const items = modules.filter((m) => (m.group || "other") === g.id);
        if (!items.length) return null;
        const faults = items.reduce((s, m) => s + (m.dtc > 0 ? m.dtc : 0), 0);
        return (
          <div className="mac-ecu-group" key={g.id}>
            <div className="mac-ecu-grouphead">
              <span className="gi"><Ic name={g.icon} size={15} /></span>
              <h3>{g.label}</h3>
              <span className="gc">{items.length} ЭБУ{faults ? ` · ${faults} ошиб.` : ""}</span>
              <span className="grule"></span>
            </div>
            <div className="mac-ecu-grid">
              {items.map((m) => <EcuCard key={m.ecu + "-" + m.tx} m={m} onOpenDtc={onOpenDtc} />)}
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

function Overview({ connected, adapter, onAdapterSelfTest, onOpenDtc }) {
  const [veh, setVeh] = React.useState(null);     // identity from vehicle/info + gateway/info
  const [scan, setScan] = React.useState(null);   // result of /api/vehicle/scan
  const [scanning, setScanning] = React.useState(false);
  const [err, setErr] = React.useState("");
  const [adapterCheck, setAdapterCheck] = React.useState(null);

  // On connect, pull real VIN + gateway identity (engine/chassis) in parallel.
  React.useEffect(() => {
    if (!connected) { setVeh(null); setScan(null); setErr(""); return; }
    let alive = true;
    (async () => {
      const [info, gw] = await Promise.all([
        apiGet("/api/vehicle/info").catch(() => null),
        apiGet("/api/gateway/info").catch(() => null),
      ]);
      if (!alive) return;
      const token = gw?.chassis_token || "";
      setVeh({
        vin: info?.vin || null,
        vinDetail: info?.vin_detail || null,
        model: ("Mercedes-Benz " + (token || gw?.chassis || "")).trim(),
        chassis: token || gw?.chassis || "",
        engine: (gw?.engine || "").split(/[ /]/)[0] || "",
        voltage: info?.voltage ?? null,
        adapter: info?.adapter?.firmware || info?.adapter?.dll || null,
        // real fitted ECUs as reported by the car's gateway (no hardcoded list)
        modules: (gw?.modules || []).filter((m) => m && m.ecu).map((m) => m.ecu),
      });
    })();
    return () => { alive = false; };
  }, [connected]);

  async function doScan() {
    setScanning(true); setErr("");
    try {
      // probe exactly what the car's gateway reports as fitted — no hardcoded list
      const mods = veh?.modules || [];
      const path = mods.length
        ? "/api/vehicle/scan?modules=" + encodeURIComponent(mods.join(","))
        : "/api/vehicle/scan" + (veh?.chassis ? "?chassis=" + encodeURIComponent(veh.chassis) : "");
      setScan(await apiGet(path));
    } catch (e) { setErr("Скан не удался: " + String(e)); }
    setScanning(false);
  }

  async function selfTestAdapter() {
    if (!onAdapterSelfTest) return;
    setAdapterCheck(null);
    try {
      setAdapterCheck(await onAdapterSelfTest());
    } catch {
      setAdapterCheck({ ok: false, error: "Самотест не завершился" });
    }
  }

  if (!connected) return <ConnectGate />;

  const v = veh || {};
  const metrics = [
    { label: "Напряжение", value: v.voltage != null ? v.voltage : "—", unit: v.voltage != null ? " В" : "" },
    { label: "ЭБУ онлайн", value: scan ? `${scan.online}/${scan.modules.length}` : "—" },
    { label: "Ошибок (DTC)", value: scan ? scan.total_dtc : "—" },
    { label: "Протоколы", value: scan && scan.protocols?.length ? scan.protocols.join(" · ") : "—" },
  ];

  return (
    <>
      <div className="mac-section">
        <div className="mac-veh mac-panel">
          <div className="mac-veh-art"><Ic name="car" size={40} /></div>
          <div className="mac-veh-info">
            <div className="vmodel">{v.model || "Mercedes-Benz"}</div>
            <div className="vvin">{v.vin || (v.vinDetail ? "VIN не прочитан — " + v.vinDetail : "—")}</div>
            <div className="vrow">
              {v.chassis && <span className="mac-chip">{v.chassis}</span>}
              {v.engine && <span className="mac-chip">{v.engine}</span>}
              {v.adapter && <span className="mac-chip">{v.adapter}</span>}
            </div>
          </div>
        </div>
      </div>

      <div className="mac-section">
        <SectionHead title="Состояние" meta={scan ? "по результату скана" : "до скана"} />
        <div className="mac-metric-grid">
          {metrics.map((m, i) => (
            <div className="mac-metric" key={i}>
              <div className="mac-metric-top">{m.label}<span className="mac-metric-ic"><Ic name={METRIC_ICONS[i % 4]} size={16} /></span></div>
              <div className="mac-metric-val">{m.value}{m.unit && <small>{m.unit}</small>}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="mac-section">
        <div className="mac-sec-head">
          <h2>Адаптер</h2>
          <span className="mac-sec-rule"></span>
          <span className="mac-sec-meta">{adapter?.kind || "не определён"}</span>
          <button className="mac-btn" onClick={selfTestAdapter} disabled={!onAdapterSelfTest}>
            <Ic name="activity" size={15} /> Самотест
          </button>
        </div>
        <div className="mac-veh mac-panel">
          <div className="mac-veh-art"><Ic name="cpu" size={36} /></div>
          <div className="mac-veh-info">
            <div className="vmodel">{adapter?.label || "Транспорт не выбран"}</div>
            <div className="vvin">
              {adapter?.driver || "Драйвер не требуется в режиме симулятора"}
            </div>
            <div className="vrow">
              {(adapter?.capabilities?.protocols || []).map((protocol) => (
                <span className="mac-chip" key={protocol}>{protocol}</span>
              ))}
              {adapter?.capabilities?.supports_flow_control_filter && (
                <span className="mac-chip">ISO-TP flow control</span>
              )}
            </div>
          </div>
        </div>
        {adapterCheck?.error && (
          <div className="mac-empty" style={{ color: "var(--danger)" }}>{adapterCheck.error}</div>
        )}
        {adapterCheck?.checks?.length > 0 && (
          <div className="mac-veh mac-panel">
            <div className="mac-veh-info">
              {adapterCheck.checks.map((check) => (
                <div className="vrow" key={check.id}>
                  <span className="mac-chip">{check.status === "ok" ? "✓" : "!"} {check.label}</span>
                  <span className="mac-ecu-meta">{check.detail}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mac-section">
        <div className="mac-sec-head">
          <h2>Блоки управления</h2>
          <span className="mac-sec-rule"></span>
          {scan && <span className="mac-sec-meta">{scan.modules.length} ЭБУ · {scan.online} онлайн · {scan.total_dtc} ошиб.</span>}
          <button className="mac-btn" onClick={doScan} disabled={scanning}>
            {scanning ? <span className="mac-spin"></span> : <Ic name="zap" size={15} />}
            {scanning ? "Сканирую…" : scan ? "Пересканировать" : "Сканировать"}
          </button>
        </div>
        {err && <div className="mac-empty" style={{ color: "var(--danger)" }}>{err}</div>}
        {scan?.adapter_error && <div className="mac-empty" style={{ color: "var(--warn)" }}>{scan.adapter_error}</div>}
        {scan ? (
          <EcuList modules={scan.modules} onOpenDtc={onOpenDtc} />
        ) : !err ? (
          <div className="mac-empty">Нажми «Сканировать», чтобы опросить все ЭБУ{v.chassis ? ` шасси ${v.chassis}` : ""}.</div>
        ) : null}
      </div>
    </>
  );
}

function Live({ connected }) {
  const [ecus, setEcus] = React.useState([]);
  const [ecu, setEcu] = React.useState("");
  const [groups, setGroups] = React.useState([]);
  const [path, setPath] = React.useState("");
  const [run, setRun] = React.useState(false);
  const [vals, setVals] = React.useState([]);
  const [history, setHistory] = React.useState({});   // job -> number[]

  React.useEffect(() => { apiGet("/api/measure/ecus").then((d) => setEcus(d.ecus || [])).catch(() => {}); }, []);
  // measurement dashboards for the selected ECU
  React.useEffect(() => {
    setGroups([]); setPath(""); setRun(false);
    if (!ecu) return;
    apiGet(`/api/measure/groups?module=${encodeURIComponent(ecu)}`)
      .then((g) => { const m = g.measurement || []; setGroups(m); if (m[0]) setPath(m[0].path); })
      .catch(() => {});
  }, [ecu]);

  const tick = React.useCallback(async () => {
    if (!path || !ecu) return;
    try {
      const r = await apiGet(`/api/measure/read?path=${encodeURIComponent(path)}&module=${encodeURIComponent(ecu)}&lang=ru`);
      const vs = r.values || [];
      setHistory((current) => {
        const next = { ...current };
        vs.forEach((v) => {
          if (typeof v.value === "number") next[v.job] = [...(next[v.job] || []).slice(-25), v.value];
        });
        return next;
      });
      setVals(vs);
    } catch { setVals([]); }
  }, [path, ecu]);

  React.useEffect(() => {
    if (!run) return;
    setHistory({});
    void tick();
    const t = setInterval(tick, 1100);
    return () => clearInterval(t);
  }, [run, tick]);

  if (!connected) return <ConnectGate />;
  const numeric = vals.filter((v) => typeof v.value === "number");
  return (
    <>
      <div className="mac-toolbar">
        <label className="mac-field"><span>ЭБУ</span>
          <select className="mac-select" value={ecu} onChange={(e) => setEcu(e.target.value)} style={{ minWidth: 150 }}>
            <option value="">— выбери —</option>
            {ecus.map((e) => <option key={e} value={e}>{e}</option>)}
          </select></label>
        <label className="mac-field"><span>Группа измерений</span>
          <select className="mac-select" value={path} onChange={(e) => { setPath(e.target.value); setRun(false); }} style={{ minWidth: 300 }} disabled={!groups.length}>
            {!groups.length && <option value="">— нет групп —</option>}
            {groups.map((g) => <option key={g.path} value={g.path}>{g.title || g.raw_title}</option>)}
          </select></label>
        <button className={"mac-btn" + (run ? " danger" : "")} onClick={() => setRun((r) => !r)} disabled={!path}>
          <Ic name={run ? "x" : "activity"} size={15} />{run ? "Остановить" : "Запустить"}
        </button>
        {run && <span className="mac-chip" style={{ alignSelf: "center", display: "inline-flex", alignItems: "center", gap: 6 }}><span className="mac-statusdot on sm"></span>поток · ~1 Гц</span>}
      </div>
      {!run ? <div className="mac-empty">Выбери ЭБУ и группу, затем «Запустить» — пойдёт живой поток (в эмуляторе значения синтезируются).</div>
        : numeric.length === 0 ? <div className="mac-empty">В этой группе нет читаемых числовых параметров (сервисные процедуры или без read-запроса).</div>
        : (
          <div className="mac-gauge-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
            {numeric.map((g) => (
              <div className="mac-gauge" key={g.job}>
                <div className="mac-gauge-lbl">{g.label}</div>
                <div className="mac-gauge-val">{g.value}<small>{g.unit}</small></div>
                <Sparkline points={history[g.job] || [g.value]} />
                <div className="mac-gauge-sub">{g.low != null && g.high != null ? `${g.low} … ${g.high}` : (g.note || "")}</div>
              </div>
            ))}
          </div>
        )}
    </>
  );
}

const MSTATUS = {
  simulated: "live (эмулятор)", hw_ok: "live", missing_request: "нет запроса",
  blocked: "сервисная процедура", na: "не прочитано", error: "ошибка чтения",
};

// Reads and displays the live values of one measurement group (/api/measure/read).
// "Произвести" re-reads; "Авто" polls every second for a live feel.
function MeasureRunner({ path, module, title, onClose }) {
  const [vals, setVals] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [auto, setAuto] = React.useState(false);
  const read = React.useCallback(async () => {
    setLoading(true);
    try {
      const r = await apiGet(`/api/measure/read?path=${encodeURIComponent(path)}&module=${encodeURIComponent(module)}&lang=ru`);
      setVals(r.values || []);
    } catch { setVals([]); }
    setLoading(false);
  }, [path, module]);
  React.useEffect(() => { read(); }, [read]);
  React.useEffect(() => {
    if (!auto) return;
    const id = setInterval(read, 1000);
    return () => clearInterval(id);
  }, [auto, read]);
  const live = (vals || []).filter((v) => v.value !== null).length;

  return (
    <div className="mac-subcard" style={{ marginTop: 16 }}>
      <div className="mac-sec-head" style={{ margin: "0 0 12px" }}>
        <h3 style={{ margin: 0 }}>Измерение · {title}</h3>
        <span className="mac-sec-rule"></span>
        {vals && <span className="mac-sec-meta">{live}/{vals.length} читается</span>}
        <button className={"mac-btn" + (auto ? " danger" : "")} onClick={() => setAuto((a) => !a)}>
          <Ic name="activity" size={15} />{auto ? "Стоп" : "Авто"}
        </button>
        <button className="mac-btn" onClick={read} disabled={loading}>
          {loading ? <span className="mac-spin"></span> : <Ic name="refresh" size={15} />}Произвести
        </button>
        <button className="mac-btn ghost" onClick={onClose}><Ic name="x" size={15} />Закрыть</button>
      </div>
      {!vals ? <div className="mac-empty">Чтение…</div>
        : vals.length === 0 ? <div className="mac-empty">В группе нет параметров данных (только процедуры).</div>
        : (
          <div className="mac-table-wrap">
            <table className="mac-table">
              <thead><tr><th>Параметр</th><th>Значение</th><th>Диапазон</th><th>Статус</th></tr></thead>
              <tbody>
                {vals.map((v, i) => (
                  <tr key={i}>
                    <td>{v.label}</td>
                    <td>{v.value !== null
                      ? <b>{v.value}{v.unit ? " " + v.unit : ""}</b>
                      : <span style={{ color: "var(--muted)" }}>—</span>}</td>
                    <td style={{ color: "var(--muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                      {v.low != null && v.high != null ? `${v.low} … ${v.high}` : "—"}</td>
                    <td><span style={{ fontSize: 11, color: v.value !== null ? "var(--ok)" : "var(--muted)" }}>
                      {MSTATUS[v.read_status] || v.read_status || ""}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}

function DtcDetail({ row, moduleId, moduleLabel, onBack, onClear, canWrite }) {
  const [ctx, setCtx] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  React.useEffect(() => {
    let alive = true; setLoading(true);
    apiGet(`/api/diag/context?code=${encodeURIComponent(row.code)}&module=${encodeURIComponent(moduleId)}&lang=ru`)
      .then((c) => { if (alive) { setCtx(c); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [row.code, moduleId]);
  const [openGroup, setOpenGroup] = React.useState(null);
  React.useEffect(() => { setOpenGroup(null); }, [row.code]);
  const causes = ctx?.causes || [];
  const checks = ctx?.checks || [];
  const linked = ctx?.linked?.measurement || [];
  return (
    <div className="mac-panel">
      <div className="mac-dtc-head">
        <span className="mac-dtc-code">{row.code}</span>
        <span className="mac-sevdot"><i style={{ background: "var(--danger)" }}></i>{row.status}</span>
        <span className="mac-chip">{moduleLabel}</span>
        <span className="mac-dtc-actions">
          <button className="mac-btn ghost" onClick={onBack}><Ic name="chevron" size={15} style={{ transform: "rotate(180deg)" }} />Назад</button>
          <button className="mac-btn danger" onClick={onClear} disabled={!canWrite}
            title={canWrite ? "" : "Сброс заблокирован сервером в режиме hardware"}>
            <Ic name="refresh" size={15} />Сбросить память DTC
          </button>
        </span>
      </div>
      <p style={{ fontSize: 15, color: "var(--txt)", margin: "10px 0 2px", fontWeight: 500 }}>{row.description || ctx?.description}</p>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--muted)" }}>raw: {row.raw}{ctx?.area ? " · " + ctx.area : ""}</div>

      {loading ? <div className="mac-empty" style={{ marginTop: 16 }}>Загружаю контекст…</div> : (
        <>
          <div className="mac-detail-grid">
            <div className="mac-subcard">
              <h3>Возможные причины</h3>
              <ul className="mac-list causes">{causes.map((c, i) => <li key={i}><span className="mk"></span>{c}</li>)}</ul>
            </div>
            <div className="mac-subcard">
              <h3>Рекомендуемые проверки</h3>
              <ul className="mac-list steps">{checks.map((s, i) => <li key={i}><span className="mk">{i + 1}</span>{s}</li>)}</ul>
            </div>
          </div>
          {linked.length > 0 && (
            <div className="mac-subcard" style={{ marginTop: 16 }}>
              <h3>Связанные измерения <small style={{ color: "var(--muted)", fontWeight: 400 }}>· нажми, чтобы произвести</small></h3>
              <div className="mac-mini-grid">
                {linked.slice(0, 6).map((g, i) => (
                  <div className={"mac-mini clickable" + (openGroup?.path === g.path ? " on" : "")} key={i}
                    role="button" tabIndex={0}
                    onClick={() => setOpenGroup((cur) => (cur?.path === g.path ? null : g))}>
                    <div className="l">{g.title || g.raw_title}</div>
                    <div className="v" style={{ fontSize: 13 }}>{g.count}<small>пар.</small></div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {(ctx?.media || []).length > 0 && (
            <div className="mac-subcard" style={{ marginTop: 16 }}>
              <h3>Схемы и распиновки <small style={{ color: "var(--muted)", fontWeight: 400 }}>· StarFinder + генерируемые</small></h3>
              <div className="mac-mini-grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}>
                {ctx.media.map((m, i) => (
                  <a key={i} href={m.src} target="_blank" rel="noreferrer" className="mac-mini clickable" style={{ display: "block", textDecoration: "none" }}>
                    <img src={m.src} alt={m.title} loading="lazy"
                      style={{ width: "100%", borderRadius: 6, background: "#fff", display: "block", minHeight: 60, objectFit: "contain", maxHeight: 260 }} />
                    <div className="l" style={{ marginTop: 6 }}>{m.title}{m.provider ? ` · ${m.provider}` : ""}</div>
                  </a>
                ))}
              </div>
            </div>
          )}
          {openGroup && (
            <MeasureRunner path={openGroup.path} module={moduleId}
              title={openGroup.title || openGroup.raw_title} onClose={() => setOpenGroup(null)} />
          )}
        </>
      )}
    </div>
  );
}

function DtcClearConfirm({ moduleLabel, count, loading, onConfirm, onCancel }) {
  return (
    <div className="mac-panel" style={{ marginTop: 14, borderColor: "var(--danger)" }}>
      <div style={{ fontWeight: 650, marginBottom: 8 }}>Подтвердить сброс памяти неисправностей</div>
      <div style={{ color: "var(--txt-2)", fontSize: 13, lineHeight: 1.55 }}>
        Будет очищена <b>вся память DTC</b> блока <b>{moduleLabel}</b>, а не только открытый код.
        Сейчас считано кодов: <b>{count}</b>. После операции macDiag повторно прочитает блок.
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <button className="mac-btn danger" onClick={onConfirm} disabled={loading}>
          {loading ? <span className="mac-spin"></span> : <Ic name="refresh" size={15} />}
          Да, стереть все DTC
        </button>
        <button className="mac-btn ghost" onClick={onCancel} disabled={loading}>Отмена</button>
      </div>
    </div>
  );
}

function Dtc({ connected, initialModule, writeSafety }) {
  const [mods, setMods] = React.useState([]);    // [{id,ecu,dtc,state,protocol}]
  const [mod, setMod] = React.useState(initialModule || "");
  const [data, setData] = React.useState(null);  // /api/dtc response
  const [loading, setLoading] = React.useState(false);
  const [sel, setSel] = React.useState(null);
  const [confirmClear, setConfirmClear] = React.useState(false);

  async function read(target) {
    const t = target || mod;
    if (!t) return;
    setLoading(true); setSel(null); setConfirmClear(false);
    try { setData(await apiGet(`/api/dtc?module=${encodeURIComponent(t)}&lang=ru`)); }
    catch (e) { setData({ status: "error", detail: String(e), dtcs: [] }); }
    setLoading(false);
  }
  // module list comes from a real scan
  React.useEffect(() => {
    if (!connected) { setMods([]); setData(null); return; }
    apiGet("/api/vehicle/scan").then((s) => {
      const list = (s.modules || []).filter((m) => m.state !== "silent");
      setMods(list);
      setMod((cur) => cur || initialModule || (list.find((m) => m.dtc > 0) || list[0] || {}).id || "");
    }).catch(() => {});
  }, [connected, initialModule]);
  // drill-in from Overview just selects the module; the effect below reads it
  React.useEffect(() => { if (initialModule) setMod(initialModule); }, [initialModule]);
  // auto-read whenever the selected module changes (manual pick, drill, or default)
  React.useEffect(() => { if (connected && mod) read(mod); }, [mod, connected]);  // eslint-disable-line react-hooks/exhaustive-deps

  async function clear() {
    if (!mod || !canWrite) return;
    setLoading(true); setConfirmClear(false);
    try {
      await apiPost(`/api/dtc/clear?module=${encodeURIComponent(mod)}`);
    } catch (e) {
      setData({ status: "error", detail: "Сброс не выполнен: " + String(e.message || e), dtcs: [] });
      setLoading(false);
      return;
    }
    await read(mod);
  }

  if (!connected) return <ConnectGate />;
  const canWrite = Boolean(writeSafety?.enabled);
  const rows = data?.dtcs || [];
  const modLabel = (mods.find((m) => m.id === mod) || {}).ecu || mod;
  const requestClear = () => { if (canWrite && rows.length > 0) setConfirmClear(true); };
  if (sel) return (
    <>
      <DtcDetail row={sel} moduleId={mod} moduleLabel={modLabel}
        onBack={() => { setSel(null); setConfirmClear(false); }} onClear={requestClear} canWrite={canWrite} />
      {confirmClear && <DtcClearConfirm moduleLabel={modLabel} count={rows.length}
        loading={loading} onConfirm={clear} onCancel={() => setConfirmClear(false)} />}
    </>
  );

  return (
    <>
      <div className="mac-toolbar">
        <label className="mac-field"><span>Модуль</span>
          <select className="mac-select" value={mod} onChange={(e) => { setMod(e.target.value); setData(null); }} style={{ minWidth: 200 }}>
            {mods.length === 0 && <option value="">— подключись и сканируй —</option>}
            {mods.map((m) => <option key={m.id} value={m.id}>{m.ecu}{m.dtc > 0 ? ` (${m.dtc})` : ""}</option>)}
          </select></label>
        <button className="mac-btn" onClick={() => read()} disabled={loading || !mod}>
          {loading ? <span className="mac-spin"></span> : <Ic name="download" size={15} />}Считать ошибки
        </button>
        <button className="mac-btn danger" onClick={requestClear}
          disabled={loading || rows.length === 0 || !canWrite}
          title={canWrite ? "" : "Сброс заблокирован сервером в режиме hardware"}>
          <Ic name="refresh" size={15} />Сбросить
        </button>
      </div>
      {!canWrite && <div className="mac-empty" style={{ color: "var(--warn)" }}>
        Сброс DTC заблокирован сервером. Для реального адаптера нужен запуск с MACDIAG_ENABLE_WRITES=1.
      </div>}
      {confirmClear && <DtcClearConfirm moduleLabel={modLabel} count={rows.length}
        loading={loading} onConfirm={clear} onCancel={() => setConfirmClear(false)} />}
      {data && rows.length > 0 && (
        <>
          <div className="mac-table-wrap">
            <table className="mac-table">
              <thead><tr><th>Код</th><th>Статус</th><th>Описание</th><th>raw</th><th></th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="clickable" onClick={() => setSel(r)}>
                    <td><code>{r.code}</code></td>
                    <td><span className="mac-sevdot"><i style={{ background: "var(--danger)" }}></i>{r.status}</span></td>
                    <td>{r.description}</td>
                    <td><code style={{ color: "var(--muted)" }}>{r.raw}</code></td>
                    <td style={{ textAlign: "right", color: "var(--muted)" }}><Ic name="chevron" size={16} style={{ verticalAlign: "middle" }} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mac-empty" style={{ marginTop: 12 }}>Нажми на строку, чтобы открыть причины, проверки и связанные измерения.</p>
        </>
      )}
      {data && rows.length === 0 && data.status !== "error" && (
        <div className="mac-banner ok"><Ic name="gauge" size={18} />
          {data.status === "ok" ? `Ошибок в модуле ${modLabel} не найдено.`
            : data.status === "present" ? `${modLabel}: на шине, но не отдаёт DTC (отрицательный ответ).`
            : `${modLabel}: нет ответа от блока.`}
        </div>
      )}
      {data && data.status === "error" && <div className="mac-empty" style={{ color: "var(--danger)" }}>Ошибка чтения: {data.detail}</div>}
      {!data && !loading && <div className="mac-empty">Выбери модуль и нажми «Считать ошибки».</div>}
    </>
  );
}

function Modules() {
  const [mods, setMods] = React.useState(null);
  const [chassis, setChassis] = React.useState("");
  const [q, setQ] = React.useState("");
  React.useEffect(() => { apiGet("/api/modules").then((d) => setMods(d.modules || [])).catch(() => setMods([])); }, []);
  const all = React.useMemo(() => mods || [], [mods]);
  const chassisList = React.useMemo(() => {
    const s = new Set(); all.forEach((m) => (m.chassis || []).forEach((c) => s.add(c))); return [...s].sort();
  }, [all]);
  const rows = all.filter((m) =>
    (!chassis || (m.chassis || []).includes(chassis)) &&
    (!q || `${m.cbf} ${m.name} ${m.id}`.toLowerCase().includes(q.toLowerCase())));
  const hex = (n) => (n != null ? "0x" + Number(n).toString(16).toUpperCase() : "—");
  return (
    <>
      <div className="mac-toolbar">
        <label className="mac-field"><span>Шасси</span>
          <select className="mac-select" value={chassis} onChange={(e) => setChassis(e.target.value)}>
            <option value="">Все шасси</option>
            {chassisList.map((c) => <option key={c} value={c}>{c}</option>)}
          </select></label>
        <label className="mac-field" style={{ flex: 1, minWidth: 200 }}><span>Поиск</span>
          <input className="mac-input" placeholder="имя ЭБУ…" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <span className="mac-chip" style={{ alignSelf: "center" }}>{rows.length} ЭБУ</span>
      </div>
      {mods === null ? <div className="mac-empty">Загрузка каталога…</div> : (
        <div className="mac-table-wrap">
          <table className="mac-table">
            <thead><tr><th>Модуль</th><th>CBF</th><th>Прот.</th><th>TX</th><th>RX</th><th>Шасси</th></tr></thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id}>
                  <td style={{ fontWeight: 600 }}>{m.name}</td>
                  <td><code>{m.cbf}</code></td>
                  <td><span className={"mac-proto " + (m.protocol || "")}>{m.protocol}</span></td>
                  <td><code>{hex(m.tx)}</code></td><td><code>{hex(m.rx)}</code></td>
                  <td style={{ color: "var(--muted)" }}>{(m.chassis || []).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mac-empty" style={{ marginTop: 14 }}>Реальные CAN ID из CBF (Caesar/Vediamo) — курированный быстрый список ({all.length} ЭБУ). Полный каталог по шасси доступен через БД.</p>
    </>
  );
}

function Coding({ connected, writeSafety }) {
  const [mods, setMods] = React.useState([]);
  const [mod, setMod] = React.useState("");
  const [domains, setDomains] = React.useState([]);
  const [domain, setDomain] = React.useState("");
  const [res, setRes] = React.useState(null);    // /api/coding/read result
  const [originalCoding, setOriginalCoding] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [editing, setEditing] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [writeResult, setWriteResult] = React.useState(null);
  const [showBackups, setShowBackups] = React.useState(false);
  const [backups, setBackups] = React.useState(null);
  const [backupLoading, setBackupLoading] = React.useState(false);
  const [backupErr, setBackupErr] = React.useState("");
  const [err, setErr] = React.useState("");

  React.useEffect(() => { apiGet("/api/modules").then((d) => setMods(d.modules || [])).catch(() => {}); }, []);
  // load variant-coding domains when the module changes
  React.useEffect(() => {
    setDomains([]); setDomain(""); setRes(null); setOriginalCoding("");
    setConfirming(false); setWriteResult(null); setErr("");
    if (!mod) return;
    apiGet(`/api/coding/domains?module=${encodeURIComponent(mod)}`)
      .then((d) => { const dl = d.domains || []; setDomains(dl); if (dl[0]) setDomain(dl[0].domain); })
      .catch(() => setDomains([]));
  }, [mod]);

  React.useEffect(() => {
    setRes(null); setOriginalCoding(""); setConfirming(false); setWriteResult(null); setErr("");
  }, [domain]);

  async function read() {
    if (!mod || !domain) return;
    setLoading(true); setErr(""); setRes(null); setConfirming(false); setWriteResult(null);
    try {
      const next = await apiGet(`/api/coding/read?module=${encodeURIComponent(mod)}&domain=${encodeURIComponent(domain)}`);
      setRes(next); setOriginalCoding(next.coding || "");
    }
    catch (e) { setErr("Не удалось прочитать: " + String(e)); }
    setLoading(false);
  }

  async function changeFragment(fragment, option) {
    if (!res?.coding || !option || option === fragment.current) return;
    setEditing(fragment.name); setErr(""); setWriteResult(null); setConfirming(false);
    try {
      const encoded = await apiPost("/api/coding/encode", {
        module: mod, domain, coding_hex: res.coding,
        fragment: fragment.name, option,
      });
      const decoded = await apiPost("/api/coding/decode", {
        module: mod, domain, coding_hex: encoded.coding_hex,
      });
      setRes({ ...decoded, lid: res.lid, read_service: res.read_service });
    } catch (e) {
      setErr("Не удалось изменить параметр: " + String(e));
    }
    setEditing("");
  }

  async function loadBackups() {
    setBackupLoading(true); setBackupErr("");
    try { setBackups(await apiGet("/api/coding/backups?limit=20")); }
    catch (e) { setBackupErr("Не удалось загрузить журнал: " + String(e)); }
    setBackupLoading(false);
  }

  async function toggleBackups() {
    if (showBackups) { setShowBackups(false); return; }
    setShowBackups(true);
    await loadBackups();
  }

  async function applyCoding() {
    if (!res?.coding || !canWrite || res.coding === originalCoding) return;
    setSaving(true); setErr(""); setWriteResult(null);
    try {
      const result = await apiPost("/api/coding/apply", {
        module: mod, domain, coding_hex: res.coding, unlock: true,
      });
      setWriteResult(result); setOriginalCoding(res.coding); setConfirming(false);
      if (showBackups) await loadBackups();
    } catch (e) {
      setErr("Запись не выполнена: " + String(e));
    }
    setSaving(false);
  }

  const [xml, setXml] = React.useState(null);   // CxF-style structure dump
  React.useEffect(() => { setXml(null); }, [mod]);
  async function toggleXml() {
    if (xml !== null) { setXml(null); return; }
    setXml("");
    try { const r = await fetch(`/api/coding/xml?module=${encodeURIComponent(mod)}`); setXml(await r.text()); }
    catch (e) { setXml("<!-- ошибка: " + String(e) + " -->"); }
  }
  function downloadXml() {
    const blob = new Blob([xml || ""], { type: "application/xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = (mod || "cbf") + ".coding.xml"; a.click();
    URL.revokeObjectURL(a.href);
  }

  if (!connected) return <ConnectGate />;
  const frags = res?.fragments || [];
  const canWrite = Boolean(writeSafety?.enabled);
  const dirty = Boolean(res?.coding && originalCoding && res.coding !== originalCoding);
  const gateHint = writeSafety == null
    ? "Сервер ещё не сообщил режим записи"
    : `Запись заблокирована сервером. Нужен ${writeSafety.environment}=1 после проверки VIN и питания`;
  return (
    <>
      <div className={"mac-banner" + (canWrite ? " ok" : "")}><Ic name="alert" size={18} />
        {canWrite
          ? "Кодирование разрешено сервером. Изменение применяется только после отдельного подтверждения; перед записью сохраняется текущая строка."
          : `${gateHint}. Чтение и декодирование остаются доступны.`}
      </div>
      <div className="mac-toolbar">
        <label className="mac-field"><span>Модуль</span>
          <select className="mac-select" value={mod} onChange={(e) => setMod(e.target.value)} style={{ minWidth: 140 }}>
            <option value="">— выбери —</option>
            {mods.map((m) => <option key={m.id} value={m.id}>{m.cbf}</option>)}
          </select></label>
        <label className="mac-field"><span>Домен (variant coding)</span>
          <select className="mac-select" value={domain} onChange={(e) => setDomain(e.target.value)} style={{ minWidth: 300 }} disabled={!domains.length}>
            {!domains.length && <option value="">— нет доменов —</option>}
            {domains.map((d) => <option key={d.domain} value={d.domain}>{d.domain}</option>)}
          </select></label>
        <span className="mac-tb-actions">
          <button className="mac-btn" onClick={read} disabled={!mod || !domain || loading}>
            {loading ? <span className="mac-spin"></span> : <Ic name="download" size={15} />}Прочитать с авто
          </button>
          <button className={"mac-btn" + (xml !== null ? " ghost" : "")} onClick={toggleXml} disabled={!mod}>
            <Ic name="book" size={15} />{xml !== null ? "Скрыть XML" : "CxF XML"}
          </button>
          <button className={"mac-btn" + (showBackups ? " ghost" : "")} onClick={toggleBackups}
            disabled={backupLoading}>
            {backupLoading ? <span className="mac-spin"></span> : <Ic name="refresh" size={15} />}
            {showBackups ? "Скрыть backups" : "Журнал backups"}
          </button>
          <button className="mac-btn danger" onClick={() => setConfirming(true)}
            disabled={!canWrite || !dirty || loading || Boolean(editing) || saving}
            title={!canWrite ? gateHint : (!dirty ? "Сначала измени именованный параметр" : "Проверить изменения перед записью")}>
            <Ic name="upload" size={15} />Записать
          </button>
        </span>
      </div>
      {xml !== null && (
        <div className="mac-panel" style={{ marginBottom: 14 }}>
          <div className="mac-hex-bar">
            <span className="mac-sec-meta">CBF-кодирование по тегам · домены → фрагменты → биты → опции</span>
            <button className="mac-btn ghost" style={{ marginLeft: "auto" }} onClick={downloadXml} disabled={!xml}>
              <Ic name="download" size={14} />Скачать .xml
            </button>
          </div>
          <pre style={{ margin: 0, maxHeight: 360, overflow: "auto", fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.5, color: "var(--txt-2)", whiteSpace: "pre" }}>
            {xml === "" ? "загрузка…" : xml}
          </pre>
        </div>
      )}
      {showBackups && (
        <div className="mac-panel" style={{ marginBottom: 14 }}>
          <div className="mac-hex-bar">
            <span style={{ fontWeight: 650 }}>Журнал pre-write backup</span>
            <span className="mac-sec-meta">последние {backups?.entries?.length || 0} записей</span>
            <button className="mac-btn ghost" style={{ marginLeft: "auto" }} onClick={loadBackups}
              disabled={backupLoading}>
              {backupLoading ? <span className="mac-spin"></span> : <Ic name="refresh" size={14} />}Обновить
            </button>
          </div>
          {backups?.path && <div style={{ color: "var(--muted)", fontSize: 12, margin: "8px 0 12px" }}>
            Файл: <code>{backups.path}</code>
          </div>}
          {backupErr && <div className="mac-empty" style={{ color: "var(--danger)" }}>{backupErr}</div>}
          {!backupErr && backups && backups.entries.length === 0 && (
            <div className="mac-empty">Журнал пуст — записи появятся после первой операции кодирования.</div>
          )}
          {backups?.entries?.length > 0 && (
            <div className="mac-table-wrap">
              <table className="mac-table">
                <thead><tr><th>Время</th><th>ЭБУ / домен</th><th>DID/LID</th><th>До записи</th><th>Целевое</th><th>Состояние</th></tr></thead>
                <tbody>
                  {backups.entries.map((entry, i) => (
                    <tr key={`${entry.ts}-${i}`}>
                      <td style={{ whiteSpace: "nowrap", color: "var(--muted)", fontSize: 12 }}>
                        {entry.ts ? new Date(entry.ts * 1000).toLocaleString("ru-RU") : "—"}
                      </td>
                      <td><b>{entry.ecu || entry.module || "—"}</b><br />
                        <span style={{ color: "var(--muted)", fontSize: 12 }}>{entry.domain || "ручная запись"}</span>
                      </td>
                      <td><code>{entry.did || "—"}</code></td>
                      <td><code style={{ wordBreak: "break-all" }}>{entry.old || "—"}</code></td>
                      <td><code style={{ wordBreak: "break-all" }}>{entry.new || "—"}</code></td>
                      <td>{entry.read_error
                        ? <span style={{ color: "var(--warn)" }} title={entry.read_error}>backup без чтения: {entry.read_error}</span>
                        : <span style={{ color: "var(--ok)" }}>сохранено</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      {err && <div className="mac-empty" style={{ color: "var(--danger)" }}>{err}</div>}
      {confirming && dirty && (
        <div className="mac-panel" style={{ marginBottom: 14, borderColor: "var(--danger)" }}>
          <div style={{ fontWeight: 650, marginBottom: 8 }}>Подтвердить запись кодировки</div>
          <div style={{ color: "var(--txt-2)", fontSize: 13, lineHeight: 1.55 }}>
            ЭБУ: <b>{mod}</b> · домен: <b>{domain}</b><br />
            Было: <code>{originalCoding}</code><br />
            Станет: <code>{res.coding}</code><br />
            Перед записью backend прочитает текущее значение, сохранит backup и выполнит Security Access.
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="mac-btn danger" onClick={applyCoding} disabled={saving}>
              {saving ? <span className="mac-spin"></span> : <Ic name="upload" size={15} />}
              Да, записать в ЭБУ
            </button>
            <button className="mac-btn ghost" onClick={() => setConfirming(false)} disabled={saving}>Отмена</button>
          </div>
        </div>
      )}
      {writeResult?.ok && (
        <div className="mac-banner ok" style={{ marginBottom: 14 }}><Ic name="check" size={18} />
          Запись выполнена: {writeResult.write_service || domain}, LID {writeResult.lid || "—"}.
          Backup {writeResult.backup?.saved ? "сохранён" : "не сохранён"}; Security Access {writeResult.security?.unlocked ? "подтверждён" : "не потребовался или не подтверждён"}.
        </div>
      )}
      {res ? (
        <>
          <div style={{ margin: "4px 2px 12px", fontFamily: "var(--font-mono)", fontSize: 12.5, color: "var(--muted)" }}>
            строка: <code style={{ color: "var(--accent-2)" }}>{res.coding}</code> · {res.dump_size} Б · LID {res.lid} · {frags.length} парам.
            {dirty && <span style={{ color: "var(--warn)", marginLeft: 8 }}>изменена, не записана</span>}
          </div>
          <div className="mac-table-wrap">
            <table className="mac-table">
              <thead><tr><th>Параметр</th><th>Бит</th><th>Текущее</th><th>Опции</th></tr></thead>
              <tbody>
                {frags.map((p, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{p.name}</td>
                    <td><code style={{ color: "var(--muted)" }}>@{p.byte_bit_pos}/{p.bit_length}b</code></td>
                    <td><b>{p.current ?? (p.options && p.options[p.value]) ?? p.value}</b></td>
                    <td>
                      {p.options?.length ? (
                        <select className="mac-select" value={p.current || ""}
                          onChange={(e) => changeFragment(p, e.target.value)}
                          disabled={Boolean(editing) || saving} style={{ minWidth: 180 }}>
                          {!p.current && <option value="">— значение {p.value ?? "не распознано"} —</option>}
                          {p.options.map((option) => <option key={option} value={option}>{option}</option>)}
                        </select>
                      ) : <span style={{ color: "var(--muted)", fontSize: 12.5 }}>нет именованных опций</span>}
                      {editing === p.name && <span className="mac-spin" style={{ marginLeft: 8 }}></span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : !err && <div className="mac-empty">Выбери модуль и домен, нажми «Прочитать» — покажу строку кодирования и декодированные параметры.</div>}
    </>
  );
}

const _clean = (s) => {
  if (typeof s !== "string") return s;
  return Array.from(s, (char) => {
    const code = char.charCodeAt(0);
    return code >= 32 && code !== 127 ? char : "";
  }).join("").trim();
};

function hexToBytes(hx) { const o = []; for (let i = 0; i + 1 < hx.length; i += 2) o.push(parseInt(hx.substr(i, 2), 16)); return o; }
const _hx = (n) => n.toString(16).toUpperCase().padStart(2, "0");
const _asc = (n) => (n >= 32 && n < 127) ? String.fromCharCode(n) : ".";

// Hex viewer over the REAL bytes of a CFF file (/api/flash/cff/{name}/hex), paged.
function HexViewer({ name, jump }) {
  const PAGE = 512, PER = 16;
  const [offset, setOffset] = React.useState(0);
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  React.useEffect(() => { if (jump != null) setOffset(jump - (jump % PER)); }, [jump]);
  React.useEffect(() => {
    let alive = true; setLoading(true);
    apiGet(`/api/flash/cff/${encodeURIComponent(name)}/hex?offset=${offset}&length=${PAGE}`)
      .then((d) => { if (alive) { setData(d); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [name, offset]);
  if (!data) return <div className="mac-empty">{loading ? "Чтение байтов…" : "—"}</div>;
  const bytes = hexToBytes(data.hex);
  const rows = [];
  for (let r = 0; r * PER < bytes.length; r++) {
    const off = r * PER, slice = bytes.slice(off, off + PER);
    rows.push(
      <div className="mac-hex-row" key={r}>
        <span className="mac-hex-off">{(data.offset + off).toString(16).toUpperCase().padStart(6, "0")}</span>
        <span className="mac-hex-bytes">{slice.map((b, i) => <b key={i}>{_hx(b)} </b>)}</span>
        <span className="mac-hex-ascii">{slice.map((b, i) => <b key={i}>{_asc(b)}</b>)}</span>
      </div>
    );
  }
  const pages = Math.max(1, Math.ceil(data.total / PAGE)), page = Math.floor(data.offset / PAGE);
  return (
    <div className="mac-section" style={{ marginTop: 16 }}>
      <div className="mac-hex-bar">
        <span className="mac-sec-meta">смещение 0x{data.offset.toString(16).toUpperCase()} · {data.total} Б всего</span>
        <span style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button className="mac-btn ghost" onClick={() => setOffset(Math.max(0, offset - PAGE))} disabled={offset === 0}><Ic name="chevron" size={14} style={{ transform: "rotate(180deg)" }} />Назад</button>
          <span className="mac-chip" style={{ alignSelf: "center" }}>стр. {page + 1}/{pages}</span>
          <button className="mac-btn ghost" onClick={() => setOffset(offset + PAGE)} disabled={offset + PAGE >= data.total}>Вперёд<Ic name="chevron" size={14} /></button>
        </span>
      </div>
      <div className="mac-hex-pane">
        <div className="mac-hex-head"><span className="tag">HEX</span><code>{name}.cff</code></div>
        <div className="mac-hex-body">{rows}</div>
      </div>
    </div>
  );
}

// Real CFF container parse (/api/flash/cff/{name}): header + data blocks + segments.
function CffViewer({ name, onJump }) {
  const [info, setInfo] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [xml, setXml] = React.useState(null);   // null=hidden, ""=loading, text=shown
  React.useEffect(() => {
    let alive = true; setLoading(true); setXml(null);
    apiGet(`/api/flash/cff/${encodeURIComponent(name)}`)
      .then((d) => { if (alive) { setInfo(d); setLoading(false); } })
      .catch(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [name]);
  async function toggleXml() {
    if (xml !== null) { setXml(null); return; }
    setXml("");
    try { const r = await fetch(`/api/flash/cff/${encodeURIComponent(name)}/xml`); setXml(await r.text()); }
    catch (e) { setXml("<!-- ошибка: " + String(e) + " -->"); }
  }
  function downloadXml() {
    const blob = new Blob([xml || ""], { type: "application/xml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name + ".cff.xml"; a.click();
    URL.revokeObjectURL(a.href);
  }
  if (loading) return <div className="mac-empty">Парсинг CFF…</div>;
  if (!info) return <div className="mac-empty" style={{ color: "var(--danger)" }}>Не удалось разобрать CFF.</div>;
  const fl = info.flash || {};
  const blocks = fl.blocks || [];
  const fmtSize = (n) => (n >= 1024 ? (n / 1024).toFixed(1) + " КБ" : n + " Б");
  const meta = [
    ["ЭБУ", info.ecu], ["Имя", fl.flash_name], ["Автор", fl.file_author],
    ["Дата", (fl.file_creation_time || "").slice(0, 10)], ["Инструмент", fl.authoring_tool_version],
    ["CFF", info.header?.CFF], ["Размер", fmtSize(fl.size || info.size || 0)],
  ].filter(([, v]) => v);
  return (
    <div className="mac-section">
      <div className="mac-sec-head">
        <h2>CFF Viewer</h2>
        <span className="mac-sec-rule"></span>
        <span className="mac-sec-meta">реальный разбор контейнера · read-only</span>
        <button className={"mac-btn" + (xml !== null ? " ghost" : "")} onClick={toggleXml}>
          <Ic name="book" size={15} />{xml !== null ? "Скрыть XML" : "CxF XML"}
        </button>
      </div>
      {xml !== null && (
        <div className="mac-panel" style={{ marginBottom: 14 }}>
          <div className="mac-hex-bar">
            <span className="mac-sec-meta">CFF разложен по тегам</span>
            <button className="mac-btn ghost" style={{ marginLeft: "auto" }} onClick={downloadXml} disabled={!xml}>
              <Ic name="download" size={14} />Скачать .xml
            </button>
          </div>
          <pre style={{ margin: 0, maxHeight: 360, overflow: "auto", fontFamily: "var(--font-mono)", fontSize: 12, lineHeight: 1.5, color: "var(--txt-2)", whiteSpace: "pre" }}>
            {xml === "" ? "загрузка…" : xml}
          </pre>
        </div>
      )}
      <div className="mac-panel">
        <div className="mac-cff-hdr">
          {meta.map(([l, v]) => <div className="mac-mini" key={l}><div className="l">{l}</div><div className="v" style={{ fontSize: 13, fontFamily: "var(--font-mono)" }}>{v}</div></div>)}
        </div>
        {info.part_numbers?.length > 0 && <div style={{ margin: "4px 2px", fontSize: 12.5, color: "var(--muted)" }}>Парт-номера: <code>{info.part_numbers.join(", ")}</code></div>}
        {fl.error && <div className="mac-empty" style={{ color: "var(--warn)" }}>Бинарный разбор недоступен: {fl.error}</div>}
        {blocks.map((b, bi) => (
          <div key={bi} style={{ marginTop: 14 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Блок: <code>{b.qualifier}</code> · {b.segments.length} сегм.</div>
            {b.segments.length > 0 ? (
              <table className="mac-table" style={{ border: "1px solid var(--line)", borderRadius: "var(--r-tile)", overflow: "hidden" }}>
                <thead><tr><th>Сегмент</th><th>Загр. адрес</th><th>Размер</th><th>Смещение в файле</th><th></th></tr></thead>
                <tbody>
                  {b.segments.map((s, si) => (
                    <tr key={si}>
                      <td><span className="mac-seg-dot" style={{ background: s.in_bounds ? "var(--accent)" : "var(--warn)" }}></span>{s.name}</td>
                      <td><code>0x{s.from_address.toString(16).toUpperCase().padStart(8, "0")}</code></td>
                      <td>{fmtSize(s.length)}</td>
                      <td><code style={{ color: "var(--muted)" }}>0x{s.file_offset.toString(16).toUpperCase()}</code></td>
                      <td style={{ textAlign: "right" }}><button className="mac-btn ghost" style={{ height: 30, padding: "0 10px", fontSize: 12 }} onClick={() => onJump(s.file_offset)} disabled={!s.in_bounds}><Ic name="search" size={13} />Hex</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <div className="mac-empty">Сегментов нет (только метаданные / late-data).</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

function Flash({ connected }) {
  const [mods, setMods] = React.useState([]);
  const [mod, setMod] = React.useState("");
  const [ver, setVer] = React.useState(null);     // /api/flash/versions
  const [verLoading, setVerLoading] = React.useState(false);
  const [lib, setLib] = React.useState(null);      // /api/flash/library images
  const [q, setQ] = React.useState("");
  const [openCff, setOpenCff] = React.useState(null);   // CFF name being viewed
  const [jump, setJump] = React.useState(null);         // hex viewer jump offset

  React.useEffect(() => { apiGet("/api/modules").then((d) => setMods(d.modules || [])).catch(() => {}); }, []);
  React.useEffect(() => { apiGet("/api/flash/library").then((d) => setLib(d.images || [])).catch(() => setLib([])); }, []);

  async function readVersions() {
    if (!mod) return;
    setVerLoading(true); setVer(null);
    try { setVer(await apiGet(`/api/flash/versions?module=${encodeURIComponent(mod)}`)); }
    catch (e) { setVer({ error: String(e) }); }
    setVerLoading(false);
  }

  if (!connected) return <ConnectGate />;
  const images = (lib || []).filter((r) =>
    !q || `${r.name} ${r.ecu} ${(r.part_numbers || []).join(" ")}`.toLowerCase().includes(q.toLowerCase()));
  const verRows = ver && !ver.error ? Object.entries(ver.versions || {}) : [];

  if (openCff) return (
    <>
      <button className="mac-btn ghost" onClick={() => { setOpenCff(null); setJump(null); }} style={{ marginBottom: 14 }}>
        <Ic name="chevron" size={15} style={{ transform: "rotate(180deg)" }} />Назад к каталогу
      </button>
      <CffViewer name={openCff} onJump={setJump} />
      <HexViewer name={openCff} jump={jump} />
    </>
  );

  return (
    <>
      <div className="mac-banner"><Ic name="alert" size={18} />Запись прошивки отключена намеренно. Неверный или прерванный флэш может вывести ЭБУ из строя — раздел работает в режиме чтения (версии ПО, каталог CFF, hex-просмотр).</div>

      <div className="mac-toolbar">
        <label className="mac-field"><span>Модуль</span>
          <select className="mac-select" value={mod} onChange={(e) => { setMod(e.target.value); setVer(null); }} style={{ minWidth: 150 }}>
            <option value="">— выбери —</option>
            {mods.map((m) => <option key={m.id} value={m.id}>{m.cbf}</option>)}
          </select></label>
        <span className="mac-tb-actions">
          <button className="mac-btn" onClick={readVersions} disabled={!mod || verLoading}>
            {verLoading ? <span className="mac-spin"></span> : <Ic name="download" size={15} />}Считать версии ПО
          </button>
          <button className="mac-btn danger" disabled title="Прошивка отключена (read-only)"><Ic name="drive" size={15} />Прошить</button>
        </span>
      </div>

      {ver && ver.error && <div className="mac-empty" style={{ color: "var(--danger)" }}>Ошибка чтения версий: {ver.error}</div>}
      {verRows.length > 0 && (
        <div className="mac-section">
          <SectionHead title="Текущее ПО блока" meta={ver.module} />
          <div className="mac-panel">
            <div className="mac-mini-grid">
              {verRows.map(([k, v]) => (
                <div className="mac-mini" key={k}>
                  <div className="l">{k}</div>
                  <div className="v" style={{ fontSize: 14, fontFamily: "var(--font-mono)" }}>{_clean(v) || "—"}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="mac-section">
        <div className="mac-toolbar" style={{ marginBottom: 12 }}>
          <SectionHead title="Каталог прошивок (CFF)" meta={lib === null ? "загрузка…" : `${images.length} / ${lib.length} образов`} />
          <label className="mac-field" style={{ flex: 1, minWidth: 200 }}><span>Поиск</span>
            <input className="mac-input" placeholder="имя образа, ЭБУ, парт-номер…" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        </div>
        <div className="mac-table-wrap">
          <table className="mac-table">
            <thead><tr><th>Образ</th><th>ЭБУ</th><th>Парт-номера</th><th>Шасси</th><th></th></tr></thead>
            <tbody>
              {images.slice(0, 100).map((r) => (
                <tr key={r.name} className="clickable" onClick={() => { setOpenCff(r.name); setJump(null); }}>
                  <td><code>{r.name}</code></td>
                  <td style={{ fontWeight: 600 }}>{r.ecu}</td>
                  <td><code style={{ color: "var(--muted)" }}>{(r.part_numbers || []).join(", ") || "—"}</code></td>
                  <td style={{ color: "var(--muted)" }}>{r.chassis_hint || "—"}</td>
                  <td style={{ textAlign: "right", color: "var(--muted)" }}><Ic name="search" size={14} style={{ verticalAlign: "middle" }} /> разобрать</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {images.length > 100 && <p className="mac-empty" style={{ marginTop: 10 }}>Показаны первые 100 — уточни поиск, чтобы сузить.</p>}
      </div>
    </>
  );
}

// ---- Журнал ECU-changing операций -----------------------------------------
const AUDIT_OP = {
  dtc_clear: "DTC clear",
  coding_apply: "Variant coding",
  coding_write: "Coding DID",
};
const AUDIT_OUTCOME = {
  success: { label: "Выполнено", color: "var(--ok)" },
  error: { label: "Ошибка", color: "var(--danger)" },
  blocked: { label: "Заблокировано", color: "var(--warn)" },
};

function Audit() {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState("");
  const [outcome, setOutcome] = React.useState("all");
  const [operation, setOperation] = React.useState("all");
  const [q, setQ] = React.useState("");

  const load = React.useCallback(async () => {
    setLoading(true); setErr("");
    try { setData(await apiGet("/api/audit/actions?limit=200")); }
    catch (e) { setErr("Не удалось загрузить audit log: " + String(e)); }
    setLoading(false);
  }, []);
  React.useEffect(() => { void load(); }, [load]);

  const entries = data?.entries || [];
  const operations = [...new Set(entries.map((entry) => entry.operation).filter(Boolean))].sort();
  const query = q.trim().toLowerCase();
  const rows = entries.filter((entry) => {
    if (outcome !== "all" && entry.outcome !== outcome) return false;
    if (operation !== "all" && entry.operation !== operation) return false;
    if (!query) return true;
    return [entry.operation, entry.outcome, entry.module, entry.ecu, entry.domain,
      entry.did, entry.error, entry.reason].filter(Boolean).join(" ").toLowerCase().includes(query);
  });
  const counts = entries.reduce((acc, entry) => {
    acc[entry.outcome] = (acc[entry.outcome] || 0) + 1;
    return acc;
  }, {});

  return (
    <>
      <div className="mac-toolbar">
        <label className="mac-field"><span>Результат</span>
          <select className="mac-select" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="all">Все</option><option value="success">Выполнено</option>
            <option value="error">Ошибки</option><option value="blocked">Заблокировано</option>
          </select></label>
        <label className="mac-field"><span>Операция</span>
          <select className="mac-select" value={operation} onChange={(e) => setOperation(e.target.value)}>
            <option value="all">Все операции</option>
            {operations.map((op) => <option key={op} value={op}>{AUDIT_OP[op] || op}</option>)}
          </select></label>
        <label className="mac-field" style={{ flex: 1, minWidth: 220 }}><span>Поиск</span>
          <input className="mac-input" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="ЭБУ, домен, DID, ошибка…" /></label>
        <button className="mac-btn" onClick={load} disabled={loading}>
          {loading ? <span className="mac-spin"></span> : <Ic name="refresh" size={15} />}Обновить
        </button>
      </div>

      <div className="mac-mini-grid" style={{ marginBottom: 16 }}>
        {Object.entries(AUDIT_OUTCOME).map(([key, spec]) => (
          <div className="mac-mini" key={key}>
            <div className="l">{spec.label}</div>
            <div className="v" style={{ color: spec.color }}>{counts[key] || 0}</div>
          </div>
        ))}
        <div className="mac-mini"><div className="l">Показано</div><div className="v">{rows.length}</div></div>
      </div>

      {data?.path && <div style={{ color: "var(--muted)", fontSize: 12, marginBottom: 12 }}>
        Append-only файл: <code>{data.path}</code>
      </div>}
      {err && <div className="mac-empty" style={{ color: "var(--danger)" }}>{err}</div>}
      {!err && data && entries.length === 0 && (
        <div className="mac-empty">Журнал пуст — события появятся после DTC clear или coding-записи.</div>
      )}
      {!err && entries.length > 0 && rows.length === 0 && (
        <div className="mac-empty">По выбранным фильтрам событий нет.</div>
      )}
      {rows.length > 0 && (
        <div className="mac-table-wrap">
          <table className="mac-table">
            <thead><tr><th>Время</th><th>Результат</th><th>Операция</th><th>Цель</th><th>Детали</th><th>Режим</th></tr></thead>
            <tbody>
              {rows.map((entry, i) => {
                const state = AUDIT_OUTCOME[entry.outcome] || { label: entry.outcome || "—", color: "var(--muted)" };
                const details = [
                  entry.did && `ID ${entry.did}`,
                  entry.value_bytes != null && `${entry.value_bytes} Б`,
                  entry.security_level != null && `Security L${entry.security_level}`,
                  entry.backup_saved === true && "backup сохранён",
                  entry.reason,
                  entry.error,
                ].filter(Boolean);
                return (
                  <tr key={`${entry.ts}-${entry.operation}-${i}`}>
                    <td style={{ whiteSpace: "nowrap", color: "var(--muted)", fontSize: 12 }}>
                      {entry.ts ? new Date(entry.ts * 1000).toLocaleString("ru-RU") : "—"}
                    </td>
                    <td><span className="mac-sevdot"><i style={{ background: state.color }}></i>{state.label}</span></td>
                    <td style={{ fontWeight: 600 }}>{AUDIT_OP[entry.operation] || entry.operation}</td>
                    <td>{entry.ecu || entry.module || "—"}<br />
                      {entry.domain && <span style={{ color: "var(--muted)", fontSize: 12 }}>{entry.domain}</span>}
                    </td>
                    <td style={{ color: entry.error ? "var(--danger)" : "var(--txt-2)", maxWidth: 430 }}>
                      {details.join(" · ") || "—"}
                    </td>
                    <td><span className="mac-chip">{entry.mode || "—"}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

// ---- Справка (references / library) -----------------------------------------
function SearchBox({ value, onChange, placeholder }) {
  return (
    <div style={{ position: "relative", maxWidth: 440, marginBottom: 14 }}>
      <span style={{ position: "absolute", left: 11, top: 9, color: "var(--muted)" }}><Ic name="search" size={16} /></span>
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
        style={{ width: "100%", padding: "8px 12px 8px 34px", background: "var(--panel)", color: "var(--txt)",
          border: "1px solid var(--line)", borderRadius: "var(--r-ctrl)", fontSize: 13, fontFamily: "var(--font-ui)" }} />
    </div>
  );
}

function Refs() {
  const [refs, setRefs] = React.useState(null);
  const [can, setCan] = React.useState(null);
  const [q, setQ] = React.useState("");
  React.useEffect(() => {
    apiGet(`/api/references?limit=200${q ? "&q=" + encodeURIComponent(q) : ""}`).then(setRefs).catch(() => setRefs({ rows: [] }));
  }, [q]);
  React.useEffect(() => { apiGet("/api/can/examples").then(setCan).catch(() => setCan({ rows: [] })); }, []);
  const rrows = (refs && refs.rows) || [];
  const crows = (can && can.rows) || [];
  return (
    <div>
      <SectionHead title="Справка — ссылки и CAN-факты" meta={`${rrows.length} ссылок · ${crows.length} CAN`} />
      <SearchBox value={q} onChange={setQ} placeholder="поиск по CAN, gateway, сети…" />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
        {rrows.map((r, i) => (
          <a key={i} href={r.url} target="_blank" rel="noreferrer"
            style={{ display: "block", background: "var(--panel)", border: "1px solid var(--line)",
              borderRadius: "var(--r-card)", padding: "12px 14px", textDecoration: "none", color: "var(--txt)" }}>
            <div style={{ fontSize: 13, fontWeight: 500, lineHeight: 1.35 }}>{r.title}</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)", marginTop: 6 }}>{r.domain}</div>
          </a>
        ))}
      </div>
      {crows.length > 0 && (
        <>
          <SectionHead title="Проверенные CAN-факты" />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(310px, 1fr))", gap: 10 }}>
            {crows.map((c, i) => (
              <div key={i} style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "var(--r-card)", padding: "12px 14px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <b style={{ fontFamily: "var(--font-mono)", color: "var(--accent-2)", fontSize: 16 }}>{c.can_id || "—"}</b>
                  <span style={{ color: "var(--muted)", fontSize: 12 }}>{c.bus}</span>
                </div>
                <div style={{ color: "var(--txt-2)", fontSize: 12.5, marginTop: 6 }}>{[c.vehicle, c.payload_meaning || c.source_title].filter(Boolean).join(" · ")}</div>
                {c.data_hex && <code style={{ display: "block", marginTop: 6, fontSize: 12 }}>{c.data_hex}</code>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ---- Словарь (translation dictionary) ---------------------------------------
const _thS = { textAlign: "left", padding: "9px 12px", color: "var(--muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: ".5px", borderBottom: "1px solid var(--line-2)" };
const _tdS = { padding: "9px 12px", verticalAlign: "top", fontSize: 13 };

function Dict({ lang }) {
  const [data, setData] = React.useState(null);
  const [q, setQ] = React.useState("");
  React.useEffect(() => {
    apiGet(`/api/measure/translations?lang=${lang || "ru"}&limit=100${q ? "&q=" + encodeURIComponent(q) : ""}`)
      .then(setData).catch(() => setData({ rows: [] }));
  }, [q, lang]);
  const rows = (data && data.rows) || [];
  return (
    <div>
      <SectionHead title="Словарь — переводы (RU / EN / DE)" meta={`${rows.length} строк · ${(lang || "ru").toUpperCase()}`} />
      <SearchBox value={q} onChange={setQ} placeholder="поиск по тексту…" />
      <div style={{ background: "var(--panel)", border: "1px solid var(--line)", borderRadius: "var(--r-card)", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead><tr><th style={_thS}>Исходный текст</th><th style={_thS}>Перевод</th><th style={{ ..._thS, width: 96 }}>Тип</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} style={{ borderTop: "1px solid var(--line-2)" }}>
                <td style={_tdS}>{r.source_text}</td>
                <td style={{ ..._tdS, color: r.translation ? "var(--txt)" : "var(--muted)" }}>{r.translation || "—"}</td>
                <td style={{ ..._tdS, color: "var(--muted)" }}>{r.kind}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export { Overview, Live, Dtc, Modules, Coding, Flash, Audit, Refs, Dict };
