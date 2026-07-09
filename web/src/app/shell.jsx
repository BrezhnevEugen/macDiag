import { Icon } from './icons.jsx';
// macDiag Modern — responsive shell: sidebar nav + sticky app bar + global controls.

const NAV = [
  { id: "overview", label: "Обзор", icon: "gauge" },
  { id: "live", label: "Live data", icon: "activity" },
  { id: "dtc", label: "Ошибки", icon: "alert" },
  { id: "modules", label: "Модули", icon: "cpu" },
  { id: "coding", label: "Кодирование", icon: "sliders" },
  { id: "flash", label: "Программирование", icon: "drive" },
  { id: "refs", label: "Справка", icon: "book" },
  { id: "dict", label: "Словарь", icon: "globe" },
];

function Sidebar({ active, onNav, connected, voltage, mode, profile, profiles,
                   busy, onProfile, open, onClose }) {
  const src = mode === "hw" ? "Openport 2.0" : "Эмулятор";
  const sub = connected
    ? `${src}${voltage != null ? ` · ${voltage} В` : ""}`
    : `${src} · не подключено`;
  return (
    <>
      <div className={"mac-scrim" + (open ? " show" : "")} onClick={onClose}></div>
      <aside className={"mac-side" + (open ? " open" : "")}>
        <div className="mac-side-inner">
          <div className="mac-brand">
            <span className="mac-logo"><Icon name="car" size={20} /></span>
            <span>
              <span className="mac-wordmark">macDiag</span>
              <span className="mac-tagline">Диагностика Mercedes-Benz</span>
            </span>
          </div>

          <nav className="mac-nav">
            {NAV.map((n) => (
              <button key={n.id} className={"mac-navitem" + (active === n.id ? " active" : "")}
                onClick={() => { onNav(n.id); onClose(); }}>
                <Icon name={n.icon} size={18} />
                <span>{n.label}</span>
                {n.id === "dtc" && <span className="mac-navbadge">3</span>}
              </button>
            ))}
          </nav>

          <div className="mac-side-foot">
            {profiles.length > 0 && (
              <label className="mac-conn-text" style={{ display: "block", marginBottom: 12 }}>
                <small>Профиль автомобиля</small>
                <select className="mac-select" value={profile?.id || ""}
                  disabled={connected || busy} onChange={(e) => onProfile?.(e.target.value)}>
                  {profile && !profiles.some((item) => item.id === profile.id) && (
                    <option value={profile.id}>{profile.label || profile.id} (external)</option>
                  )}
                  {profiles.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
                </select>
              </label>
            )}
            <div className="mac-conn-card">
              <span className={"mac-statusdot " + (connected ? "on" : "off")}></span>
              <span className="mac-conn-text">
                <b>{connected ? "Подключено" : "Не подключено"}</b>
                <small>{sub}</small>
              </span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

const LANGS = ["ru", "en", "de"];

function AppBar({ title, subtitle, theme, setTheme, dir, setDir, mode, onMode,
                 lang, onLang, connected, busy, onConnect, onMenu }) {
  return (
    <header className="mac-appbar">
      <button className="mac-iconbtn mac-menu" onClick={onMenu} aria-label="Меню"><Icon name="menu" size={20} /></button>
      <div className="mac-titlewrap">
        <h1 className="mac-title">{title}</h1>
        {subtitle && <span className="mac-subtitle">{subtitle}</span>}
      </div>

      <div className="mac-appbar-actions">
        <div className="mac-segctl" role="group" aria-label="Источник данных" title="Эмулятор или реальный адаптер">
          <button className={mode === "sim" ? "on" : ""} onClick={() => onMode && onMode("sim")} disabled={busy}>Эмулятор</button>
          <button className={mode === "hw" ? "on" : ""} onClick={() => onMode && onMode("hw")} disabled={busy}>Адаптер</button>
        </div>
        <div className="mac-segctl" role="group" aria-label="Направление">
          <button className={dir === "cockpit" ? "on" : ""} onClick={() => setDir("cockpit")}>Cockpit</button>
          <button className={dir === "workshop" ? "on" : ""} onClick={() => setDir("workshop")}>Workshop</button>
        </div>
        <div className="mac-segctl" role="group" aria-label="Язык">
          {LANGS.map((l) => (
            <button key={l} className={lang === l ? "on" : ""} onClick={() => onLang && onLang(l)}>{l.toUpperCase()}</button>
          ))}
        </div>
        <button className="mac-iconbtn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label="Тема" title="Светлая / тёмная">
          <Icon name={theme === "dark" ? "sun" : "moon"} size={18} />
        </button>
        <button className={"mac-connbtn" + (connected ? " ghost" : "")} onClick={onConnect} disabled={busy}>
          {busy ? <span className="mac-spin"></span> : <Icon name="power" size={16} />}
          <span className="mac-connbtn-label">{connected ? "Отключить" : "Подключить"}</span>
        </button>
      </div>
    </header>
  );
}

export { Sidebar, AppBar, NAV };
