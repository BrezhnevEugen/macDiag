import React from 'react';
import { Icon } from './icons.jsx';
// macDiag Modern — responsive shell: sidebar nav + sticky app bar + global controls.

const NAV = [
  { id: "overview", label: "Обзор", icon: "gauge" },
  { id: "live", label: "Live data", icon: "activity" },
  { id: "dtc", label: "Ошибки", icon: "alert" },
  { id: "modules", label: "Модули", icon: "cpu" },
  { id: "coding", label: "Кодирование", icon: "sliders" },
  { id: "flash", label: "Программирование", icon: "drive" },
];

function Sidebar({ active, onNav, connected, voltage, open, onClose }) {
  return (
    <>
      <div className={"mac-scrim" + (open ? " show" : "")} onClick={onClose}></div>
      <aside className={"mac-side" + (open ? " open" : "")}>
        <div className="mac-side-inner">
          <div className="mac-brand">
            <span className="mac-logo"><Icon name="car" size={20} /></span>
            <span>
              <span className="mac-wordmark">macDiag</span>
              <span className="mac-tagline">W221 · X164 диагностика</span>
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
            <div className="mac-conn-card">
              <span className={"mac-statusdot " + (connected ? "on" : "off")}></span>
              <span className="mac-conn-text">
                <b>{connected ? "Подключено" : "Не подключено"}</b>
                <small>{connected ? `Openport 2.0 · ${voltage} В` : "симулятор готов"}</small>
              </span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}

function AppBar({ title, subtitle, theme, setTheme, dir, setDir, connected, busy, onConnect, onMenu }) {
  return (
    <header className="mac-appbar">
      <button className="mac-iconbtn mac-menu" onClick={onMenu} aria-label="Меню"><Icon name="menu" size={20} /></button>
      <div className="mac-titlewrap">
        <h1 className="mac-title">{title}</h1>
        {subtitle && <span className="mac-subtitle">{subtitle}</span>}
      </div>

      <div className="mac-appbar-actions">
        <div className="mac-segctl" role="group" aria-label="Направление">
          <button className={dir === "cockpit" ? "on" : ""} onClick={() => setDir("cockpit")}>Cockpit</button>
          <button className={dir === "workshop" ? "on" : ""} onClick={() => setDir("workshop")}>Workshop</button>
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
