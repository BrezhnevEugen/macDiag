import React from 'react';
import { Sidebar, AppBar } from './shell.jsx';
import { Overview, Live, Dtc, Modules, Coding, Flash, Refs, Dict } from './screens.jsx';
import { apiGet } from './api.js';
// macDiag Modern — app: theming state, navigation, persistence.
const PAGES = {
  overview: { title: "Обзор", subtitle: "Состояние автомобиля и блоков управления" },
  live:     { title: "Live data", subtitle: "Потоковые измерения по ЭБУ" },
  dtc:      { title: "Ошибки (DTC)", subtitle: "Чтение и сброс кодов неисправностей" },
  modules:  { title: "Модули", subtitle: "Каталог ЭБУ и параметры шины" },
  coding:   { title: "Кодирование", subtitle: "Variant coding по доменам CBF" },
  flash:    { title: "Программирование", subtitle: "ПО блоков · дампы прошивок · каталог CFF" },
  refs:     { title: "Справка", subtitle: "Ссылки по CAN/сети и проверенные факты" },
  dict:     { title: "Словарь", subtitle: "Переводы измерений и процедур" },
};

function ModernApp() {
  const get = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
  const [theme, setTheme] = React.useState(() => get("mac.theme", "dark"));
  const [dir, setDir] = React.useState(() => get("mac.dir", "workshop"));
  const [lang, setLang] = React.useState(() => get("mac.lang", "ru"));
  const [tab, setTab] = React.useState("overview");
  const [mode, setMode] = React.useState("sim");          // 'sim' (эмулятор) | 'hw' (адаптер)
  const [connected, setConnected] = React.useState(false);
  const [voltage, setVoltage] = React.useState(null);
  const [adapter, setAdapter] = React.useState(null);
  const [profile, setProfile] = React.useState(null);
  const [profiles, setProfiles] = React.useState([]);
  const [busy, setBusy] = React.useState(false);
  const [drawer, setDrawer] = React.useState(false);
  const [dtcModule, setDtcModule] = React.useState(null);
  const [err, setErr] = React.useState("");

  React.useEffect(() => { try { localStorage.setItem("mac.theme", theme); } catch { return undefined; } }, [theme]);
  React.useEffect(() => { try { localStorage.setItem("mac.dir", dir); } catch { return undefined; } }, [dir]);
  React.useEffect(() => { try { localStorage.setItem("mac.lang", lang); } catch { return undefined; } }, [lang]);
  React.useEffect(() => { if (!err) return; const t = setTimeout(() => setErr(""), 6000); return () => clearTimeout(t); }, [err]);

  const applyStatus = React.useCallback((s) => {
    if (!s) return;
    if (s.mode) setMode(s.mode);
    setConnected(!!s.connected);
    setVoltage(s.voltage ?? null);
    if ("adapter" in s) setAdapter(s.adapter ?? null);
    if ("profile" in s) setProfile(s.profile ?? null);
  }, []);
  // Parse the body even on a non-2xx response — these endpoints return a
  // structured {mode, connected, error} that we must reflect, not swallow.
  async function call(path) {
    try {
      const r = await fetch(path, { method: "POST" });
      const data = await r.json().catch(() => null);
      return { ok: r.ok, data };
    } catch (e) { return { ok: false, data: null, error: String(e) }; }
  }
  const refreshStatus = React.useCallback(async () => {
    try { applyStatus(await apiGet("/api/status")); } catch { return undefined; }
  }, [applyStatus]);
  const refreshProfiles = React.useCallback(async () => {
    try {
      const data = await apiGet("/api/profiles");
      setProfiles(data.profiles || []);
      if (data.active) setProfile(data.active);
    } catch { return undefined; }
  }, []);
  React.useEffect(() => { void refreshStatus(); void refreshProfiles(); }, [refreshStatus, refreshProfiles]);

  const NO_BACKEND = "Бэкенд недоступен — запущен ли uvicorn на :8000? (терминал 1)";
  const errFrom = (ok, data, error, fallback) =>
    (data && data.error) || (!data ? NO_BACKEND : (error || fallback));
  // эмулятор/адаптер — POST /api/mode switches the backend and (re)connects
  async function switchMode(m) {
    if (m === mode || busy) return;
    setBusy(true); setErr("");
    const { ok, data, error } = await call(`/api/mode?mode=${m}`);
    applyStatus(data);
    if (!ok || (data && data.error)) setErr(errFrom(ok, data, error, "не удалось переключить режим"));
    setBusy(false);
  }
  async function toggleConnect() {
    setBusy(true); setErr("");
    const { ok, data, error } = await call(connected ? "/api/disconnect" : "/api/connect");
    applyStatus(data);
    if (!ok || (data && data.error)) setErr(errFrom(ok, data, error, "ошибка подключения"));
    setBusy(false);
  }
  async function selfTestAdapter() {
    setBusy(true); setErr("");
    try {
      const { ok, data, error } = await call("/api/adapter/self-test");
      applyStatus(data);
      if (!ok || (data && data.error)) {
        const message = errFrom(ok, data, error, "самотест адаптера не удался");
        setErr(message);
        throw new Error(message);
      }
      return data;
    } finally {
      setBusy(false);
    }
  }
  async function switchProfile(name) {
    if (connected || busy || name === profile?.id) return;
    setBusy(true); setErr("");
    const { ok, data, error } = await call(`/api/profile?name=${encodeURIComponent(name)}`);
    applyStatus(data);
    if (data?.profiles) setProfiles(data.profiles);
    if (!ok || (data && data.error)) setErr(errFrom(ok, data, error, "не удалось сменить профиль"));
    setBusy(false);
  }
  function openDtc(name) { setDtcModule(name); setTab("dtc"); }

  const page = PAGES[tab];

  return (
    <div id="mac" data-theme={theme} data-dir={dir}>
      <Sidebar active={tab} onNav={(id) => { setTab(id); setDtcModule(null); }}
        connected={connected} voltage={voltage} mode={mode} profile={profile} profiles={profiles}
        busy={busy} onProfile={switchProfile} open={drawer} onClose={() => setDrawer(false)} />
      <div className="mac-main">
        <AppBar title={page.title} subtitle={page.subtitle}
          theme={theme} setTheme={setTheme} dir={dir} setDir={setDir}
          mode={mode} onMode={switchMode} lang={lang} onLang={setLang}
          connected={connected} voltage={voltage} busy={busy} onConnect={toggleConnect} onMenu={() => setDrawer(true)} />
        <div className="mac-content">
          {tab === "overview" && <Overview connected={connected} adapter={adapter}
            onAdapterSelfTest={selfTestAdapter} onOpenDtc={openDtc} />}
          {tab === "live" && <Live connected={connected} />}
          {tab === "dtc" && <Dtc connected={connected} initialModule={dtcModule} />}
          {tab === "modules" && <Modules />}
          {tab === "coding" && <Coding connected={connected} />}
          {tab === "flash" && <Flash connected={connected} />}
          {tab === "refs" && <Refs />}
          {tab === "dict" && <Dict lang={lang} />}
        </div>
      </div>
      {err && (
        <div onClick={() => setErr("")} role="alert"
          style={{ position: "fixed", left: "50%", bottom: 24, transform: "translateX(-50%)",
            background: "var(--danger-surface, #2a1416)", border: "1px solid var(--danger-border, #4a1f22)",
            color: "var(--danger)", padding: "10px 16px", borderRadius: 10, fontSize: 13, zIndex: 1000,
            maxWidth: "80vw", cursor: "pointer" }}>
          ⚠ {err}
        </div>
      )}
    </div>
  );
}

export default ModernApp;
