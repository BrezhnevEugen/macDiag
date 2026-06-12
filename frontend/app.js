const $ = (s) => document.querySelector(s);

// global busy spinner: shows during any data read, after a short delay so
// fast responses don't flash. Background polls pass quiet=true.
let _busy = 0, _spinT = null;
function _showSpin(on) { const el = document.getElementById("busy"); if (el) el.style.display = on ? "inline-block" : "none"; }
function _busyDelta(d) {
  _busy = Math.max(0, _busy + d);
  if (_busy > 0) { if (!_spinT) _spinT = setTimeout(() => _showSpin(true), 180); }
  else { clearTimeout(_spinT); _spinT = null; _showSpin(false); }
}
const api = (p, opt, quiet) => {
  if (!quiet) _busyDelta(1);
  return fetch(p, opt).then((r) => r.json()).finally(() => { if (!quiet) _busyDelta(-1); });
};

// ---- tabs ----
document.querySelectorAll(".tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("#" + b.dataset.tab).classList.add("active");
    if (b.dataset.tab === "overview") loadOverview();
  };
});

// ---- cross-tab navigation (module is the central object) ----
function goTab(tab) {
  document.querySelector(`.tabs button[data-tab="${tab}"]`).click();
}
function ensureOption(sel, value, label) {
  const el = $(sel);
  if (![...el.options].some((o) => o.value === value)) {
    const o = document.createElement("option");
    o.value = value; o.textContent = label || value; el.appendChild(o);
  }
  el.value = value;
}
function goModule(modId, action, label) {
  if (action === "dtc") {
    goTab("dtc"); ensureOption("#dtcModule", modId, label); $("#dtcRead").click();
  } else if (action === "coding") {
    goTab("coding"); ensureOption("#codeModule", modId, label);
  } else if (action === "id") {
    identify(modId);
  }
}

// ---- overview / dashboard ----
async function loadOverview() {
  const v = await api("/api/vehicle/info");
  const a = v.adapter;
  $("#ovAdapter").innerHTML = v.connected
    ? `<div class="kv">${v.voltage ?? "—"} <small>${t("В")}</small></div>` +
      `<div class="dim">${t("режим: ")}${v.mode}${a ? " · fw " + (a.api || a.firmware || "") : ""}</div>` +
      `<div class="dim ok">${t("● подключено")}</div>`
    : `<div class="kv bad">${t("не подключено")}</div><div class="dim">${t("нажми «Подключить»")}</div>`;
  $("#ovBus").innerHTML = v.connected
    ? `<div class="kv">${v.voltage && v.voltage > 11 ? t("OBD питание есть") : t("нет питания OBD")}</div>` +
      `<div class="dim">ISO15765 · auto-baudrate ${t("из CBF")}</div>`
    : `<div class="dim">—</div>`;
  renderVehicle(v);
}
function renderVehicle(v) {
  if (!v.vin) {
    $("#ovVehicle").innerHTML = v.connected
      ? `<div class="dim">${t("VIN не прочитан — нажми «Прочитать VIN»")}</div>` +
        (v.vin_detail ? `<div class="dim" style="margin-top:4px; color:var(--warn)">${v.vin_detail}</div>` : "")
      : '<div class="dim">—</div>';
    return;
  }
  const d = v.decode || {};
  $("#ovVehicle").innerHTML =
    `<div class="kv" style="font-size:16px">${v.vin}</div>` +
    `<div class="dim">${d.maker || ""}</div>` +
    `<div class="dim">${d.year ? t("год: ") + d.year + " · " : ""}WMI ${d.wmi || "?"} · VDS ${d.vds || "?"}` +
    `${v.vin_source ? " · " + t("из ") + v.vin_source : ""}</div>`;
}
$("#ovReadVin").onclick = async () => {
  $("#ovVehicle").innerHTML = `<div class="dim">${t("чтение VIN…")}</div>`;
  renderVehicle(await api("/api/vehicle/info"));
};
function ovMetric(label, value, cls) {
  return `<div class="metric"><div class="m-lbl">${label}</div><div class="m-val ${cls || ""}">${value}</div></div>`;
}
const SCAN_DOT = { online: "var(--ok)", present: "var(--uds)", silent: "var(--muted)", adapter_error: "var(--danger)" };
function scanCard(m) {
  const px = (x) => (typeof x === "number" ? "0x" + x.toString(16).toUpperCase() : "");
  const st = m.state || (m.online ? "online" : "silent");
  const el = document.createElement("div");
  el.className = "ecucard" + (st === "online" || st === "present" ? "" : " off");
  let meta;
  if (st === "online") meta = `${m.cbf || ""} · <span class="proto ${m.protocol}">${m.protocol.toUpperCase()}</span> · ${px(m.tx)}`;
  else if (st === "present") meta = `${t("на связи")} · ${t("нет DTC-сервиса")}`;
  else if (st === "adapter_error") meta = `<span class="bad">${t("Ошибка адаптера")}</span>`;
  else meta = t("нет ответа");
  el.innerHTML =
    `<div class="top"><span class="sdot" style="background:${SCAN_DOT[st] || "var(--muted)"}"></span>` +
    `<span class="nm">${m.name}</span>` +
    `${st === "online" && m.dtc ? `<span class="faults">${m.dtc} DTC</span>` : ""}</div>` +
    `<div class="meta">${meta}</div>`;
  if (st === "online" || st === "present") el.onclick = () => goModule(m.id, "dtc", m.name);
  return el;
}
function scanMetrics(online, count, total, protos) {
  $("#ovMetrics").innerHTML =
    ovMetric(t("ЭБУ онлайн"), `${online} <span style="font-size:13px;color:var(--muted)">/ ${count}</span>`) +
    ovMetric(t("ошибок (DTC)"), total, total ? "bad" : "ok") +
    ovMetric(t("протокол"), protos || "—");
}
let _scanES = null;
$("#ovScan").onclick = () => {
  const ch = $("#ovChassis").value;
  if (_scanES) { _scanES.close(); _scanES = null; }
  $("#ovScanStat").textContent = t("сканирую…");
  const grid = $("#ovScanGrid"); grid.innerHTML = "";
  let count = 0, protos = "—";
  const es = new EventSource("/api/vehicle/scan/stream" + (ch ? "?chassis=" + ch : ""));
  _scanES = es;
  es.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "start") {
      count = msg.count; protos = (msg.protocols || []).join(" / ") || "—";
      scanMetrics(0, count, 0, protos);
    } else if (msg.type === "module") {
      grid.appendChild(scanCard(msg.module));
      scanMetrics(msg.online, count, msg.total_dtc, protos);
    } else if (msg.type === "done") {
      es.close(); _scanES = null;
      $("#ovScanStat").innerHTML = msg.adapter_error
        ? `<span class="bad">⚠ ${t("часть блоков не опрошена (ошибка адаптера)")}</span>` : "";
    }
  };
  es.onerror = () => {
    es.close(); _scanES = null;
    if (!grid.children.length) $("#ovScanStat").innerHTML = `<span class="bad">${t("Ошибка адаптера")}</span>`;
    else $("#ovScanStat").textContent = "";
  };
};

$("#ovGw") && ($("#ovGw").onclick = async () => {
  $("#ovScanStat").textContent = t("опрос шлюза…");
  const info = await api("/api/gateway/info");
  $("#ovScanStat").textContent = "";
  renderGateway(info);
});
let _gw = null;
function renderGateway(info) {
  const box = $("#gwInfo");
  if (!info || info.error) { box.innerHTML = info && info.error ? `<div class="warn">⚠ ${info.error}</div>` : ""; return; }
  _gw = info;
  // auto-select the detected chassis everywhere + show engine on the vehicle card
  if (info.chassis_token) {
    ["#ovChassis", "#chassis"].forEach((s) => {
      const el = $(s);
      if (el && [...el.options].some((o) => o.value === info.chassis_token)) el.value = info.chassis_token;
    });
  }
  if (info.engine) {
    const v = $("#ovVehicle");
    if (v) v.innerHTML = `<div class="kv" style="font-size:16px">${info.engine}</div>` +
      `<div class="dim">${[info.chassis, info.body].filter(Boolean).join(" · ")}</div>`;
  }
  const present = (info.options || []).filter((o) => /vorhanden|aktiv|erlaubt/i.test(o.value) && !/nicht/i.test(o.value));
  const ecus = (info.ecus || []).filter((e) => e.present);
  box.innerHTML =
    `<div class="card"><div class="clabel">${t("комплектация (из шлюза)")}</div>` +
    `<div class="kv" style="font-size:18px">${info.engine || "—"}</div>` +
    `<div class="dim">${[info.chassis, info.body].filter(Boolean).join(" · ")}</div>` +
    (present.length ? `<div class="chips" style="margin-top:10px">` +
      present.map((o) => `<span class="chip">${o.name.replace(/^SA:\s*/, "")}</span>`).join("") + `</div>` : "") +
    (ecus.length ? `<div class="clabel" style="margin-top:12px">${t("блоки по конфигурации")}</div>` +
      `<div class="chips">` + ecus.map((e) => `<span class="chip">${e.name}</span>`).join("") + `</div>` : "") +
    `</div>`;
}

// ---- connection ----
document.querySelectorAll(".seg button[data-mode]").forEach((b) => {
  b.onclick = async () => {
    const m = b.dataset.mode;
    $("#connText").textContent = m === "sim" ? t("запуск эмулятора…") : t("подключение к железу…");
    const r = await api("/api/mode?mode=" + m, { method: "POST" });
    if (r.error) alert(t("Не удалось переключить на ") + (m === "sim" ? t("эмулятор") : t("железо")) + ":\n" + r.error);
    refreshStatus(); loadOverview();
  };
});

async function refreshStatus() {
  const s = await api("/api/status", undefined, true);
  $("#mode").textContent = s.mode;
  $("#modeSim").classList.toggle("active", s.mode === "sim");
  $("#modeHw").classList.toggle("active", s.mode === "hw");
  $("#dot").className = "dot " + (s.connected ? "on" : "off");
  const volt = s.voltage != null ? ` · ${s.voltage} ${t("В")}` : "";
  $("#connText").textContent = (s.connected ? t("подключено") : t("не подключено")) + volt;
  $("#connBtn").textContent = s.connected ? t("Отключить") : t("Подключить");
  $("#connBtn").dataset.connected = s.connected;
}
$("#connBtn").onclick = async () => {
  const connected = $("#connBtn").dataset.connected === "true";
  if (connected) {
    await api("/api/disconnect", { method: "POST" });
  } else {
    $("#connText").textContent = t("подключение…");
    const r = await api("/api/connect", { method: "POST" });
    if (!r.connected) {
      $("#connText").textContent = t("ошибка подключения");
      alert(t("Не удалось подключиться:") + "\n\n" + (r.error || t("неизвестно")) +
        "\n\n" + t("В режиме железа нужен драйвер J2534 (libj2534.dylib) и MACDIAG_MODE=hw. См. README."));
    } else if (r.warning) {
      alert("⚠ " + r.warning);
    }
  }
  refreshStatus();
  loadOverview();
};

// ---- modules dropdowns ----
async function loadModules(chassis = "") {
  const tb = $("#modTable tbody");
  let modules = [];
  try {
    const r = await api("/api/modules" + (chassis ? "?chassis=" + chassis : ""));
    modules = r.modules || [];
  } catch (e) {
    tb.innerHTML = `<tr><td colspan="7" class="muted">${t("Бэкенд недоступен")} (${e})${t(". Запусти uvicorn backend.main:app")}</td></tr>`;
    return;
  }
  // table
  tb.innerHTML = "";
  if (!modules.length) {
    tb.innerHTML = `<tr><td colspan="7" class="muted">${t("Нет модулей для этого шасси")}</td></tr>`;
  }
  modules.forEach((m) => {
    const tr = document.createElement("tr");
    const part = (m.part_numbers && m.part_numbers[0]) || "—";
    const baud = m.baudrate ? (m.baudrate / 1000).toFixed(m.baudrate % 1000 ? 1 : 0) + "k" : "—";
    const src = m.id_source === "cbf"
      ? ` <span class="muted" title="${t("из Vediamo CBF")}">✓</span>`
      : ` <span class="muted" title="${t("стандартная адресация, требует проверки")}">?</span>`;
    tr.innerHTML = `<td>${m.name}</td><td><code>${m.cbf || ""}</code></td>
      <td><code>0x${m.tx.toString(16).toUpperCase()}</code>${src}</td>
      <td><code>0x${m.rx.toString(16).toUpperCase()}</code></td>
      <td><span class="proto ${m.protocol}">${m.protocol.toUpperCase()}</span></td>
      <td class="muted">${baud}</td>
      <td class="muted">${part}</td>
      <td style="white-space:nowrap">
        <button class="linkbtn" data-act="id" data-id="${m.id}">${t("ID")}</button>
        <button class="linkbtn" data-act="dtc" data-id="${m.id}" data-name="${m.name}">${t("Ошибки")}</button>
        <button class="linkbtn" data-act="coding" data-id="${m.id}" data-name="${m.name}">${t("Код")}</button>
      </td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll("button[data-act]").forEach((b) =>
    (b.onclick = () => goModule(b.dataset.id, b.dataset.act, b.dataset.name)));
  loadCatalog($("#chassis").value);
  // dropdowns
  ["#dtcModule", "#codeModule"].forEach((sel) => {
    const el = $(sel);
    el.innerHTML = `<option value="" disabled selected>${t("— выбери модуль —")}</option>`;
    modules.forEach((m) => {
      const o = document.createElement("option");
      o.value = m.id; o.textContent = `${m.name}  ·  0x${m.tx.toString(16).toUpperCase()}`;
      el.appendChild(o);
    });
  });
}
$("#chassis").onchange = (e) => loadModules(e.target.value);

let _catalog = [];
async function loadCatalog(chassis = "") {
  const r = await api("/api/catalog" + (chassis ? "?chassis=" + chassis : ""));
  _catalog = r.ecus || [];
  renderCatalog($("#catSearch").value);
}
function renderCatalog(filter = "") {
  const f = filter.trim().toLowerCase();
  const rows = _catalog.filter((e) => !f || (e.ecu || "").toLowerCase().includes(f));
  $("#catCount").textContent = `${rows.length} ${t("из")} ${_catalog.length}`;
  const tb = $("#catTable tbody");
  tb.innerHTML = "";
  const hx = (x) => (typeof x === "number" ? "0x" + x.toString(16).toUpperCase() : "—");
  rows.forEach((e) => {
    const tr = document.createElement("tr");
    const baud = e.baudrate ? (e.baudrate / 1000).toFixed(e.baudrate % 1000 ? 1 : 0) + "k" : "—";
    const act = e.can_request
      ? `<button class="linkbtn" data-dtc="${e.ecu}">DTC</button> <button class="linkbtn" data-id="${e.ecu}">${t("ID")}</button>`
      : `<span class="muted" title="${t("нет CAN id в CBF")}">—</span>`;
    tr.innerHTML = `<td><code>${e.ecu}</code></td><td>${(e.protocol || "").toUpperCase()}</td>
      <td><code>${hx(e.can_request)}</code></td><td><code>${hx(e.can_response)}</code></td>
      <td class="muted">${baud}</td><td>${(e.chassis || []).join(", ")}</td>
      <td class="muted">${(e.part_numbers && e.part_numbers[0]) || "—"}</td><td>${act}</td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll("button[data-dtc]").forEach((b) => (b.onclick = () => dtcForEcu(b.dataset.dtc)));
  tb.querySelectorAll("button[data-id]").forEach((b) => (b.onclick = () => identify(b.dataset.id)));
}

async function dtcForEcu(ecu) {
  document.querySelector('.tabs button[data-tab="dtc"]').click();
  const sel = $("#dtcModule");
  if (![...sel.options].some((o) => o.value === ecu)) {
    const o = document.createElement("option");
    o.value = ecu; o.textContent = ecu; sel.appendChild(o);
  }
  sel.value = ecu;
  $("#dtcRead").click();
}
$("#catSearch").oninput = (e) => renderCatalog(e.target.value);

async function identify(id) {
  const r = await api("/api/identify?module=" + encodeURIComponent(id));
  const box = $("#modInfo");
  box.classList.remove("hidden");
  if (r.error) { box.innerHTML = `<b>${t("Ошибка:")}</b> ${r.error}`; return; }
  box.innerHTML = "<b>" + id + "</b><br>" +
    Object.entries(r.info).map(([k, v]) => `${k}: <code>${v ?? "—"}</code>`).join("<br>");
}

// ---- DTC ----
$("#dtcRead").onclick = async () => {
  const mod = $("#dtcModule").value;
  const r = await api("/api/dtc?lang=" + (window.LANG || "ru") + (mod ? "&module=" + mod : ""));
  const tb = $("#dtcTable tbody");
  tb.innerHTML = "";
  $("#dtcDrill").innerHTML = "";
  const note = $("#dtcEmpty");
  note.classList.remove("hidden");
  const via = r.via ? " · " + r.via : "";
  if (r.status === "adapter_error") {
    note.innerHTML = `<span class="bad">⚠ ${t("Ошибка адаптера")}: ${r.detail || ""}</span>`; return;
  }
  if (r.status === "no_response") {
    note.innerHTML = `<span class="bad">✗ ${t("Нет ответа от блока")}</span>`; return;
  }
  if (r.status === "present") {
    note.innerHTML = `<span style="color:var(--warn)">● ${t("Блок на связи, но не отдаёт ошибки")} (${r.detail || ""})</span>`; return;
  }
  if (!r.dtcs || !r.dtcs.length) {
    note.innerHTML = `<span class="ok">✓ ${t("Блок ответил: ошибок нет")}${via}</span>`; return;
  }
  note.classList.add("hidden");
  r.dtcs.forEach((d) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><button class="linkbtn dtc-code" data-code="${d.code}"><code>${d.code}</code></button></td><td>${d.status}</td>
      <td>${d.description || ""}</td><td><code>${d.raw}</code></td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll(".dtc-code").forEach((b) => (b.onclick = () => drillDtc(b.dataset.code)));
};

// explain why no real StarFinder pinout is shown
function sfHint(sf) {
  if (!sf || sf.images > 0) return "";
  let msg;
  if (!sf.configured) msg = t("StarFinder не подключён — задай MACDIAG_STARFINDER_DIR и перезапусти backend.");
  else if (!sf.module_selected) msg = t("Выбери модуль в списке сверху — распиновка привязана к блоку.");
  else if (!sf.mapped) msg = t("Для этого блока распиновка пока не привязана.");
  else return "";
  return `<div class="dim" style="margin-top:12px">ℹ ${msg}</div>`;
}

// ---- DAS-style drill-down ----
async function drillDtc(code) {
  const mod = $("#dtcModule").value;
  const box = $("#dtcDrill");
  box.innerHTML = `<div class="card"><div class="dim">${t("загрузка…")}</div></div>`;
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const c = await api("/api/diag/context?code=" + encodeURIComponent(code) +
    (mod ? "&module=" + encodeURIComponent(mod) : "") + "&lang=" + (window.LANG || "ru"));
  const L = c.labels || {};
  const li = (arr) => (arr || []).map((x) => `<li>${x}</li>`).join("");
  const steps = (c.checks || []).map((s, i) =>
    `${i ? '<span class="arrow">→</span>' : ""}<span class="step">${i + 1}. ${s}</span>`).join("");
  const lk = c.linked || { measurement: [], service: [] };
  const grpChip = (g) => `<button class="chip linkbtn" data-grp="${g.path}">${g.title}</button>`;
  const imgs = (c.media || []).filter((m) => m.kind !== "doc");
  const docs = (c.media || []).filter((m) => m.kind === "doc");
  const media = imgs.map((m) =>
    `<figure style="margin:0 0 14px"><figcaption class="dim" style="margin:6px 0">${m.title}</figcaption>` +
    `<img src="${m.src}" alt="${m.title}" style="width:100%; display:block; border:1px solid var(--line); border-radius:10px; background:var(--bg)"></figure>`).join("");
  const docsHtml = docs.length
    ? `<h3>${t("Описание")} (StarFinder)</h3><div class="chips">` +
      docs.map((d) => `<a class="chip" href="${d.src}" target="_blank" rel="noopener" style="text-decoration:none">📄 ${d.title}</a>`).join("") + `</div>`
    : "";
  const comp = (c.component && c.component.name)
    ? `<div class="dim" style="margin-top:4px">${t("ЭБУ")}: <code>${c.component.code}</code> · ${c.component.name}</div>` : "";
  box.innerHTML =
    `<div class="card">` +
    `<div style="display:flex; justify-content:space-between; align-items:start; gap:12px">` +
    `<div><b style="font-size:15px"><code>${c.code}</code> — ${c.description}</b>` +
    `<div class="dim" style="margin-top:4px">${L.area || ""}: ${c.area || ""}</div>` + comp + `</div>` +
    `<button class="ghost" id="drillClose">${t("Закрыть")}</button></div>` +
    `<h3 style="margin-top:16px">${L.causes || ""}</h3><ul style="margin:0; padding-left:20px">${li(c.causes)}</ul>` +
    `<h3>${L.checks || ""}</h3><div class="flow">${steps}</div>` +
    ((lk.measurement && lk.measurement.length) ?
      `<h3>${t("Связанные группы измерений")}</h3><div class="chips">${lk.measurement.map(grpChip).join("")}</div>` : "") +
    ((lk.service && lk.service.length) ?
      `<h3>${t("Связанные процедуры")}</h3><div class="chips">${lk.service.map(grpChip).join("")}</div>` : "") +
    docsHtml +
    (media ? `<div style="margin-top:16px">${media}</div>` : "") +
    sfHint(c.starfinder) +
    `</div>`;
  $("#drillClose").onclick = () => (box.innerHTML = "");
  box.querySelectorAll("button[data-grp]").forEach((b) =>
    (b.onclick = () => openGroup(b.dataset.grp)));
}
$("#dtcClear").onclick = async () => {
  if (!confirm(t("Сбросить коды ошибок в выбранном модуле?"))) return;
  const mod = $("#dtcModule").value;
  const r = await api("/api/dtc/clear" + (mod ? "?module=" + mod : ""), { method: "POST" });
  alert(r.error ? t("Ошибка: ") + r.error : t("Ошибки сброшены"));
  $("#dtcRead").click();
};

// ---- live data (WebSocket) ----
let ws = null;
$("#liveStart").onclick = () => {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/live`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.error) { console.warn(msg.error); return; }
    renderGauges(msg.frame);
  };
  ws.onclose = () => { $("#liveStart").disabled = false; $("#liveStop").disabled = true; };
  $("#liveStart").disabled = true; $("#liveStop").disabled = false;
};
$("#liveStop").onclick = () => ws && ws.close();

function renderGauges(frame) {
  const g = $("#pidGauges");
  frame.forEach((p) => {
    let el = document.getElementById("g" + p.pid);
    if (!el) {
      el = document.createElement("div");
      el.className = "gauge"; el.id = "g" + p.pid;
      el.innerHTML = `<div class="label"></div><div class="vrow"><span class="value"></span><span class="unit"></span></div>`;
      g.appendChild(el);
    }
    el.querySelector(".label").textContent = p.label;
    el.querySelector(".value").textContent = p.value;
    el.querySelector(".unit").textContent = p.unit;
  });
}

// ---- coding ----
$("#codeUnlock").onclick = async () => {
  const mod = $("#codeModule").value;
  const lvl = $("#codeLevel").value;
  const q = `?module=${encodeURIComponent(mod)}&level=${lvl}`;
  const info = await api("/api/security/info" + q);
  const r = await api("/api/security/unlock" + q, { method: "POST" });
  const levels = (info.levels || []).map((l) => `L${l.level}:${l.provider || "—"}${l.ported ? "✓" : ""}`).join(", ");
  $("#codeOut").textContent = r.unlocked
    ? `${t("🔓 Разблокировано · L")}${r.level} (seed sub=0x${(r.seed_subfn || 0).toString(16)}, key sub=0x${(r.key_subfn || 0).toString(16)})\n` +
      `seed=${r.seed} · ${t("алгоритм=")}${r.algo}${r.provider ? " (" + r.provider + ")" : ""}\n` +
      `${t("Уровни ЭБУ: ")}${levels || t("нет в БД")}`
    : t("Ошибка разблокировки: ") + (r.error || t("неизвестно"));
};
$("#codeWrite").onclick = async () => {
  if (!confirm(t("Записать значение в ЭБУ? Это может изменить поведение модуля."))) return;
  const r = await api("/api/coding/write", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      module: $("#codeModule").value || null,
      did: parseInt($("#codeDid").value, 16),
      value_hex: $("#codeVal").value.replace(/\s/g, ""),
      unlock: true,
    }),
  });
  $("#codeOut").textContent = r.ok
    ? t("OK: значение записано.") + (r.security ? t(" (после 0x27)") : "")
    : t("Ошибка: ") + (r.error || t("неизвестно"));
};

// ---- measurement groups from .vsg ----
let measTimer = null;
async function initMeas() {
  const r = await api("/api/measure/ecus");
  const sel = $("#measEcu");
  if (!r.available) { sel.innerHTML = `<option>${t(".vsg недоступны")}</option>`; return; }
  sel.innerHTML = `<option value="">${t("— выбери ЭБУ —")}</option>` +
    r.ecus.map((e) => `<option>${e}</option>`).join("");
}
$("#measEcu") && ($("#measEcu").onchange = async () => {
  const ecu = $("#measEcu").value;
  const gsel = $("#measGroup");
  gsel.innerHTML = "";
  $("#svcDetails").innerHTML = "";
  if (!ecu) return;
  const g = await api("/api/measure/groups?module=" + encodeURIComponent(ecu) + "&lang=" + (window.LANG || "ru"));
  gsel.innerHTML = g.measurement.map((m) =>
    `<option value="${m.path}">${m.title} (${m.count})  ·  ${m.auto ? "CBF" : ".vsg"}</option>`).join("")
    || `<option value="">${t("нет измерительных групп")}</option>`;
  // service procedures -> select
  $("#svcSelect").innerHTML = `<option value="">${t("— выбери процедуру —")} (${g.service.length})</option>` +
    g.service.map((s) => `<option value="${s.path}">${s.title} · ${s.steps} ${t("шаг.")}</option>`).join("");
  // immediately show the first group's cards for the newly selected ECU
  const first = gsel.options[0] && gsel.options[0].value;
  if (first) { gsel.value = first; openGroup(first); }
  else { $("#gauges").innerHTML = ""; $("#measDesc").classList.add("hidden"); $("#measEmpty").classList.remove("hidden"); }
});
$("#measGroup") && ($("#measGroup").onchange = () => openGroup($("#measGroup").value));

// service procedure select -> show description + contents below
$("#svcSelect") && ($("#svcSelect").onchange = async () => {
  const path = $("#svcSelect").value;
  const box = $("#svcDetails");
  if (!path) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="dim">${t("загрузка…")}</div>`;
  const g = await api("/api/measure/group?path=" + encodeURIComponent(path) + "&lang=" + (window.LANG || "ru"));
  const d = g.description || {};
  const routines = (g.services || []).filter((s) => s.kind === "routine");
  const params = (g.services || []).filter((s) => s.kind !== "routine");
  const li = (arr) => arr.map((s) => `<span class="chip">${s.label || s.job}</span>`).join("");
  const flow = routines.map((s, i) =>
    `${i ? '<span class="arrow">→</span>' : ""}<span class="step">${s.label || s.job}</span>`).join("");
  box.innerHTML =
    `<div class="card"><b>${d.title || g.title}</b>` +
    (d.what ? `<div class="muted" style="margin-top:6px"><b>${t("Что:")}</b> ${d.what}<br><b>${t("Когда:")}</b> ${d.when}<br><b>${t("Как:")}</b> ${d.how}</div>` : "") +
    (d.warn ? `<div class="warn" style="margin-top:10px">⚠ ${d.warn}</div>` : "") +
    `<div style="margin-top:14px; font-size:13px"><b>${t("Шаги")} (${routines.length})</b>` +
    `<div class="flow">${flow || `<span class="muted">${t("нет актуаторных шагов")}</span>`}</div></div>` +
    `<div style="margin-top:14px; font-size:13px"><b>${t("Параметры")} (${params.length})</b><div class="chips">${li(params)}</div></div>` +
    `<div style="margin-top:14px"><button id="svcOpen">${t("▶ Открыть в дашборде (наблюдать значения)")}</button></div></div>`;
  $("#svcOpen").onclick = () => openGroup(path);
});
async function openGroup(path) {
  if (!path) return;
  if (measTimer) { clearInterval(measTimer); measTimer = null; $("#measAuto").textContent = t("▶ Авто"); }
  document.querySelector('.tabs button[data-tab="live"]').click();
  $("#measEmpty").classList.add("hidden");
  $("#gauges").innerHTML = "";
  const g = await api("/api/measure/group?path=" + encodeURIComponent(path) + "&lang=" + (window.LANG || "ru"));
  // remember selection so «Авто» streams this group
  if (![...$("#measGroup").options].some((o) => o.value === path)) {
    const o = document.createElement("option");
    o.value = path; o.textContent = g.title || path; $("#measGroup").appendChild(o);
  }
  $("#measGroup").value = path;
  const box = $("#measDesc");
  if (g.description) {
    const d = g.description;
    const steps = (g.services || []).filter((s) => s.kind === "routine");
    const stepList = steps.length
      ? `<div class="muted" style="margin-top:8px"><b>${t("Шаги (актуаторы):")}</b> ` +
        steps.map((s) => s.label || s.job).join(" · ") + "</div>" : "";
    box.innerHTML = `<b>${d.title}</b><div class="muted" style="margin-top:6px">` +
      `<b>${t("Что:")}</b> ${d.what}<br><b>${t("Когда:")}</b> ${d.when}<br><b>${t("Как:")}</b> ${d.how}</div>` +
      (d.warn ? `<div class="warn" style="margin-top:10px">⚠ ${d.warn}</div>` : "") + stepList;
    box.classList.remove("hidden");
  } else {
    box.classList.add("hidden");
  }
  await refreshMeas(path);
  $("#measAuto").disabled = false;
}
$("#measLoad") && ($("#measLoad").onclick = () => openGroup($("#measGroup").value));
async function refreshMeas(path) {
  const r = await api("/api/measure/read?path=" + encodeURIComponent(path), undefined, true);
  const g = $("#gauges");
  r.values.forEach((p) => {
    let el = document.getElementById("m_" + p.job);
    if (!el) {
      el = document.createElement("div");
      el.className = "gauge"; el.id = "m_" + p.job;
      el.title = p.job + (p.note ? "\n(" + p.note + ")" : "");
      el.innerHTML = `<div class="label"></div><div class="vrow"><span class="value"></span><span class="unit"></span></div><div class="sub muted"></div>`;
      g.appendChild(el);
    }
    el.querySelector(".label").textContent = p.label;
    el.querySelector(".value").textContent = p.value;
    el.querySelector(".unit").textContent = " " + (p.unit || "");
    // reference range (norm) for comparison — only for numeric params with a unit
    const ref = (p.unit && p.low != null && p.high != null && p.high !== p.low)
      ? `${t("норма")} ${p.low}–${p.high} ${p.unit}` : "";
    el.querySelector(".sub").textContent = ref;
  });
}
$("#measAuto").onclick = () => {
  if (measTimer) { clearInterval(measTimer); measTimer = null; $("#measAuto").textContent = t("▶ Авто"); return; }
  const path = $("#measGroup").value;
  if (!path) return;
  $("#measAuto").textContent = t("■ Стоп");
  measTimer = setInterval(() => refreshMeas(path), 500);
};

// ---- variant coding ----
let vcState = { coding: "", domain: "", dump: 0 };
$("#vcLoad").onclick = async () => {
  const mod = $("#codeModule").value;
  const r = await api("/api/coding/domains" + (mod ? "?module=" + mod : ""));
  const sel = $("#vcDomain");
  if (!r.available) { sel.innerHTML = `<option>${t("CBF недоступны (MACDIAG_CBF_DIR)")}</option>`; return; }
  sel.innerHTML = r.domains.map((d) => `<option value="${d.domain}" data-dump="${d.dump_size}" data-rlid="${d.read_lid || ""}" data-wlid="${d.write_lid || ""}" data-sec="${d.sec_level || 0}">${d.domain} (${d.fragment_count} ${t("парам.")}, ${d.dump_size}B, LID ${d.read_lid || "?"})</option>`).join("");
  sel.onchange = () => {
    const o = sel.selectedOptions[0];
    if (o) $("#vcLid").value = o.dataset.rlid || "";
  };
  sel.onchange();
};
$("#vcDecode").onclick = async () => {
  const mod = $("#codeModule").value;
  const opt = $("#vcDomain").selectedOptions[0];
  if (!opt || !opt.value) return;
  const dump = parseInt(opt.dataset.dump || "0");
  let coding = $("#vcCoding").value.replace(/\s/g, "");
  if (!coding) coding = "00".repeat(dump);
  const r = await api("/api/coding/decode", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module: mod || null, domain: opt.value, coding_hex: coding }),
  });
  if (r.error) { alert(r.error); return; }
  vcState = { coding: r.coding, domain: opt.value, dump };
  renderVC(r.fragments);
};
function renderVC(frags) {
  $("#vcCurrent").textContent = vcState.coding;
  const tb = $("#vcTable tbody");
  tb.innerHTML = "";
  frags.forEach((f) => {
    const tr = document.createElement("tr");
    let valCell;
    if (f.options && f.options.length > 1) {
      valCell = `<select data-frag="${encodeURIComponent(f.name)}">` +
        f.options.map((o) => `<option${o === f.current ? " selected" : ""}>${o}</option>`).join("") +
        `</select>`;
    } else {
      valCell = `<span class="muted">${f.current ?? f.value ?? "—"}</span>`;
    }
    tr.innerHTML = `<td>${f.name}${f.approx ? ' <span class="muted" title="длина приблизительна">~</span>' : ""}</td>
      <td class="muted">${f.byte_bit_pos}+${f.bit_length}</td><td>${valCell}</td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll("select[data-frag]").forEach((s) => (s.onchange = () => changeVC(s)));
}
async function changeVC(sel) {
  const frag = decodeURIComponent(sel.dataset.frag);
  const mod = $("#codeModule").value;
  const r = await api("/api/coding/encode", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module: mod || null, domain: vcState.domain, coding_hex: vcState.coding, fragment: frag, option: sel.value }),
  });
  if (r.error) { alert(r.error); return; }
  vcState.coding = r.coding_hex;
  $("#vcCurrent").textContent = r.coding_hex;
}
$("#vcRead").onclick = async () => {
  const mod = $("#codeModule").value;
  const opt = $("#vcDomain").selectedOptions[0];
  if (!opt || !opt.value) { alert(t("Выбери домен")); return; }
  const lid = $("#vcLid").value.trim();   // optional override; CBF LID used if empty
  const q = `?module=${encodeURIComponent(mod)}&domain=${encodeURIComponent(opt.value)}` + (lid ? `&lid=${encodeURIComponent(lid)}` : "");
  const r = await api("/api/coding/read" + q);
  if (r.error) { alert(r.error); return; }
  vcState = { coding: r.coding, domain: opt.value, dump: parseInt(opt.dataset.dump || "0") };
  $("#vcCoding").value = r.coding;
  renderVC(r.fragments);
};
$("#vcApply").onclick = async () => {
  if (!vcState.domain) { alert(t("Сначала декодируй/прочитай домен")); return; }
  if (!confirm(t("Записать строку кодирования в ЭБУ? При необходимости будет выполнена разблокировка 0x27."))) return;
  const mod = $("#codeModule").value;
  const lid = $("#vcLid").value.trim();   // optional override
  const r = await api("/api/coding/apply", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ module: mod || null, domain: vcState.domain, coding_hex: vcState.coding, lid: lid || null, unlock: true }),
  });
  $("#codeOut").textContent = r.ok
    ? `${t("✓ Записано через ")}${r.write_service} · ${t("разблокировка=")}${(r.security || {}).algo || "—"}`
    : t("Ошибка записи: ") + (r.error || t("неизвестно"));
};

// re-fetch language-dependent content when the UI language changes
window.onLangChange = () => {
  $("#measGroup").innerHTML = "";
  $("#svcDetails").innerHTML = "";
  $("#gauges").innerHTML = "";
  $("#measDesc").classList.add("hidden");
  refreshStatus();
  loadModules($("#chassis").value);
  initMeas();
  loadOverview();
};

// ---- debug traffic log ----
let _dbgOpen = false;
function dbgFmt(e) {
  const ts = new Date(e.ts * 1000).toLocaleTimeString();
  if (e.kind === "error") return `<span class="err">${ts}  ⚠ ${e.fn} status ${e.status} ${e.msg || ""}</span>`;
  const proto = ((e.kind || "") + "   ").slice(0, 3).toUpperCase();
  let tail, cls;
  if (e.timeout) { tail = "… timeout"; cls = "to"; }
  else if (e.nrc) { tail = "✗ NRC " + e.nrc; cls = "nrc"; }
  else { tail = "✓ " + (e.resp || ""); cls = "ok"; }
  const rx = e.rx ? " [" + e.rx + "]" : "";
  return `${ts}  ${proto}  ${e.tx} → ${e.req}${rx}  ${e.ms}ms  <span class="${cls}">${tail}</span>`;
}
function dbgPlain(e) {
  const ts = new Date(e.ts * 1000).toLocaleTimeString();
  if (e.kind === "error") return `${ts}  ERROR ${e.fn} status ${e.status} ${e.msg || ""}`;
  const tail = e.timeout ? "timeout" : e.nrc ? "NRC " + e.nrc : "OK " + (e.resp || "");
  return `${ts}  ${(e.kind || "").toUpperCase()}  ${e.tx} -> ${e.req}${e.rx ? " [" + e.rx + "]" : ""}  ${e.ms}ms  ${tail}`;
}
async function dbgRefresh() {
  const r = await api("/api/log", undefined, true);
  const e = r.entries || [];
  $("#dbgLog").innerHTML = e.map(dbgFmt).join("\n");
  $("#dbgCount").textContent = e.length;
  const el = $("#dbgLog"); el.scrollTop = el.scrollHeight;
}
$("#dbgToggle").onclick = () => {
  _dbgOpen = !_dbgOpen;
  $("#dbgLog").classList.toggle("hidden", !_dbgOpen);
  if (_dbgOpen) dbgRefresh();
};
$("#dbgCopy").onclick = async () => {
  const r = await api("/api/log", undefined, true);
  const text = (r.entries || []).map(dbgPlain).join("\n");
  try { await navigator.clipboard.writeText(text); $("#dbgCount").textContent = t("скопировано"); } catch (_) {}
};
$("#dbgClear").onclick = async () => { await api("/api/log/clear", { method: "POST" }, true); dbgRefresh(); };
setInterval(() => { if (_dbgOpen && $("#dbgAuto").checked) dbgRefresh(); }, 1000);

// ---- init ----
refreshStatus();
loadModules();
initMeas();
loadOverview();
setInterval(refreshStatus, 5000);
