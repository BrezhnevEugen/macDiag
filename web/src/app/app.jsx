import React from 'react';
import { Sidebar, AppBar } from './shell.jsx';
import { Overview, Live, Dtc, Modules, Coding, Flash } from './screens.jsx';
import { apiGet, apiPost } from './api.js';
// macDiag Modern — app: theming state, navigation, persistence.
const PAGES = {
  overview: { title: "Обзор", subtitle: "Состояние автомобиля и блоков управления" },
  live:     { title: "Live data", subtitle: "Потоковые измерения по ЭБУ" },
  dtc:      { title: "Ошибки (DTC)", subtitle: "Чтение и сброс кодов неисправностей" },
  modules:  { title: "Модули", subtitle: "Каталог ЭБУ и параметры шины" },
  coding:   { title: "Кодирование", subtitle: "Variant coding по доменам CBF" },
  flash:    { title: "Программирование", subtitle: "ПО блоков · дампы прошивок · каталог CFF" },
};

function ModernApp() {
  const get = (k, d) => { try { return localStorage.getItem(k) || d; } catch (e) { return d; } };
  const [theme, setTheme] = React.useState(() => get("mac.theme", "dark"));
  const [dir, setDir] = React.useState(() => get("mac.dir", "workshop"));
  const [tab, setTab] = React.useState("overview");
  const [mode, setMode] = React.useState("sim");          // 'sim' (эмулятор) | 'hw' (адаптер)
  const [connected, setConnected] = React.useState(false);
  const [voltage, setVoltage] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [drawer, setDrawer] = React.useState(false);
  const [dtcModule, setDtcModule] = React.useState(null);

  React.useEffect(() => { try { localStorage.setItem("mac.theme", theme); } catch (e) {} }, [theme]);
  React.useEffect(() => { try { localStorage.setItem("mac.dir", dir); } catch (e) {} }, [dir]);

  const applyStatus = (s) => {
    if (!s) return;
    if (s.mode) setMode(s.mode);
    setConnected(!!s.connected);
    setVoltage(s.voltage ?? null);
  };
  async function refreshStatus() { try { applyStatus(await apiGet("/api/status")); } catch (e) {} }
  React.useEffect(() => { refreshStatus(); }, []);

  // эмулятор/адаптер — POST /api/mode switches the backend and (re)connects
  async function switchMode(m) {
    if (m === mode || busy) return;
    setBusy(true);
    try { applyStatus(await apiPost(`/api/mode?mode=${m}`)); }
    catch (e) {} finally { setBusy(false); }
  }
  async function toggleConnect() {
    setBusy(true);
    try { applyStatus(await apiPost(connected ? "/api/disconnect" : "/api/connect")); }
    catch (e) {} finally { setBusy(false); refreshStatus(); }
  }
  function openDtc(name) { setDtcModule(name); setTab("dtc"); }

  const page = PAGES[tab];

  return (
    <div id="mac" data-theme={theme} data-dir={dir}>
      <Sidebar active={tab} onNav={(id) => { setTab(id); setDtcModule(null); }}
        connected={connected} voltage={voltage} mode={mode} open={drawer} onClose={() => setDrawer(false)} />
      <div className="mac-main">
        <AppBar title={page.title} subtitle={page.subtitle}
          theme={theme} setTheme={setTheme} dir={dir} setDir={setDir}
          mode={mode} onMode={switchMode}
          connected={connected} voltage={voltage} busy={busy} onConnect={toggleConnect} onMenu={() => setDrawer(true)} />
        <div className="mac-content">
          {tab === "overview" && <Overview connected={connected} onOpenDtc={openDtc} />}
          {tab === "live" && <Live connected={connected} />}
          {tab === "dtc" && <Dtc connected={connected} initialModule={dtcModule} />}
          {tab === "modules" && <Modules />}
          {tab === "coding" && <Coding connected={connected} />}
          {tab === "flash" && <Flash connected={connected} />}
        </div>
      </div>
    </div>
  );
}

export default ModernApp;
