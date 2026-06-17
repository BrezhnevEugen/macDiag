const $ = (s) => document.querySelector(s);

// escape server-sourced strings before inserting into innerHTML templates:
// CBF/ECU names, DTC texts and error messages may contain <, & or quotes
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// transient error toast (network/backend failures that have no place in the UI)
let _toastT = null;
function toast(msg) {
  let el = document.getElementById("toast");
  if (!el) { el = document.createElement("div"); el.id = "toast"; document.body.appendChild(el); }
  el.textContent = msg; el.classList.add("show");
  clearTimeout(_toastT); _toastT = setTimeout(() => el.classList.remove("show"), 4000);
}

function closeMediaLightbox() {
  const el = document.getElementById("mediaLightbox");
  if (el) el.classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function openMediaLightbox(src, title) {
  let el = document.getElementById("mediaLightbox");
  if (!el) {
    el = document.createElement("div");
    el.id = "mediaLightbox";
    el.className = "diag-lightbox hidden";
    el.innerHTML =
      `<div class="diag-lightbox-backdrop" data-close="1"></div>` +
      `<div class="diag-lightbox-panel" role="dialog" aria-modal="true">` +
      `<div class="diag-lightbox-bar"><div id="mediaLightboxTitle"></div>` +
      `<button class="ghost" id="mediaLightboxClose" type="button">${t("Закрыть")}</button></div>` +
      `<img id="mediaLightboxImg" alt=""></div>`;
    document.body.appendChild(el);
    $("#mediaLightboxClose").onclick = closeMediaLightbox;
    el.querySelector("[data-close]").onclick = closeMediaLightbox;
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") closeMediaLightbox();
    });
  }
  $("#mediaLightboxTitle").textContent = title || "";
  $("#mediaLightboxClose").textContent = t("Закрыть");
  const img = $("#mediaLightboxImg");
  img.src = src;
  img.alt = title || "";
  el.classList.remove("hidden");
  document.body.classList.add("modal-open");
}

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
  return fetch(p, opt)
    .then(async (r) => {
      const body = await r.json().catch(() => null);
      if (body === null) throw new Error("HTTP " + r.status);
      // FastAPI validation/HTTPException errors arrive as {detail}; expose them
      // through the {error} convention every caller already handles
      if (!r.ok && body.detail && !body.error)
        body.error = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      return body;
    })
    .catch((e) => {
      // network failure / dead backend: surface it instead of a silent hang
      if (!quiet) toast(t("Ошибка запроса: ") + (e.message || e));
      throw e;
    })
    .finally(() => { if (!quiet) _busyDelta(-1); });
};

// ---- tabs ----
document.querySelectorAll(".tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("#" + b.dataset.tab).classList.add("active");
    if (b.dataset.tab === "overview") loadOverview();
    if (b.dataset.tab === "dict") loadDict(true);
    if (b.dataset.tab === "refs") loadRefs(true);
    // don't keep polling measurements in the background when leaving Live
    if (b.dataset.tab !== "live" && measTimer) {
      clearInterval(measTimer); measTimer = null; $("#measAuto").textContent = t("▶ Авто");
    }
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
      `<div class="dim">${t("режим: ")}${esc(v.mode)}${a ? " · fw " + esc(a.api || a.firmware || "") : ""}</div>` +
      `<div class="dim ok">${t("● подключено")}</div>`
    : `<div class="kv bad">${t("не подключено")}</div><div class="dim">${t("нажми «Подключить»")}</div>`;
  $("#ovBus").innerHTML = v.connected
    ? `<div class="kv">${v.voltage && v.voltage > 11 ? t("OBD питание есть") : t("нет питания OBD")}</div>` +
      `<div class="dim">ISO15765 · auto-baudrate ${t("из CBF")}</div>`
    : `<div class="dim">—</div>`;
  renderVehicle(v);
  await populateChassis();
  if (!_gw) applyChassis(null, false);           // no detection yet: show the fallback chooser
  setCarImage($("#ovChassis") && $("#ovChassis").value);
  // Identity (engine/chassis/equipment + car image) comes from the gateway —
  // pull it once on connect so the card fills without a manual «Опросить шлюз».
  if (v.connected && !_gw) api("/api/gateway/info").then(renderGateway).catch(() => {});
}
$("#ovChassis") && ($("#ovChassis").onchange = () => setCarImage($("#ovChassis").value));
function carSvg(kind) {
  // Side-profile silhouette; stroke follows the theme, wheels filled via CSS.
  if (kind === "suv") {
    return `<svg viewBox="0 0 240 104" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round" stroke-linecap="round">
      <path d="M16 76 L20 48 C22 40 27 36 36 36 L60 36 L60 20 C60 16 63 14 68 14 L170 14 C178 14 184 17 188 25 L198 42 L214 48 C222 51 224 56 224 64 L224 76" fill="rgba(130,142,165,.16)"/>
      <path d="M72 36 L72 18 L118 18 L118 36 M126 36 L126 18 L168 18 C172 18 176 20 178 25 L186 36"/>
      <line x1="10" y1="76" x2="230" y2="76"/>
      <circle cx="70" cy="80" r="15"/><circle cx="178" cy="80" r="15"/>
    </svg>`;
  }
  return `<svg viewBox="0 0 240 104" fill="none" stroke="currentColor" stroke-width="3" stroke-linejoin="round" stroke-linecap="round">
    <path d="M14 78 L20 54 C22 47 27 44 35 44 L74 44 L96 24 C101 19 108 17 116 17 L150 17 C159 17 165 20 170 26 L184 44 L212 51 C220 53 224 58 224 66 L224 78" fill="rgba(130,142,165,.16)"/>
    <path d="M100 44 L114 26 L150 26 L166 44 Z M132 26 L132 44"/>
    <line x1="8" y1="78" x2="230" y2="78"/>
    <circle cx="68" cy="82" r="15"/><circle cx="176" cy="82" r="15"/>
  </svg>`;
}
const SUV_CHASSIS = new Set(["X164", "X166", "W251", "W164", "W463"]);
function setCarImage(chassis) {
  const box = document.getElementById("ovCarImg");
  if (!box) return;
  const c = (chassis || "").toUpperCase();
  box.innerHTML = carSvg(SUV_CHASSIS.has(c) ? "suv" : "sedan");
  if (!c) return;
  // optional: drop a real photo at frontend/img/<chassis>.jpg to override the silhouette
  const img = new Image();
  img.alt = c;
  img.onload = () => { box.innerHTML = ""; box.appendChild(img); };
  img.src = "img/" + c.toLowerCase() + ".jpg";
}
// Chassis is auto-detected from the gateway; the dropdown is a manual fallback.
const CHASSIS_LABEL = { X164: "X164 (GL)", W221: "W221 (S)", W251: "W251 (R)", C216: "C216 (CL)" };
let _chassisLoaded = false;
async function populateChassis() {
  if (_chassisLoaded) return;
  _chassisLoaded = true;
  try {
    const by = (await api("/api/db/stats")).by_chassis || {};
    const sel = $("#ovChassis");
    Object.entries(by).sort((a, b) => b[1] - a[1]).forEach(([c, n]) => {
      const o = document.createElement("option");
      o.value = c; o.textContent = `${CHASSIS_LABEL[c] || c} · ${n}`;
      sel.appendChild(o);
    });
  } catch (e) { /* keep the «Все шасси» fallback option */ }
}
function applyChassis(token, auto) {
  const det = $("#ovChassisDet"), sel = $("#ovChassis"), edit = $("#ovChassisEdit");
  if (auto && token) {
    if ([...sel.options].some((o) => o.value === token)) sel.value = token;
    det.textContent = (t("шасси: ") + (CHASSIS_LABEL[token] || token));
    det.classList.remove("hidden"); edit.classList.remove("hidden"); sel.classList.add("hidden");
  } else {
    det.classList.add("hidden"); edit.classList.add("hidden"); sel.classList.remove("hidden");
  }
}
$("#ovChassisEdit") && ($("#ovChassisEdit").onclick = () => {
  $("#ovChassis").classList.remove("hidden");
  $("#ovChassisEdit").classList.add("hidden");
});

function renderVehicle(v) {
  if (!v.vin) {
    $("#ovVehicle").innerHTML = v.connected
      ? `<div class="dim">${t("VIN не прочитан — нажми «Прочитать VIN»")}</div>` +
        (v.vin_detail ? `<div class="dim" style="margin-top:4px; color:var(--warn)">${esc(v.vin_detail)}</div>` : "")
      : '<div class="dim">—</div>';
    return;
  }
  const d = v.decode || {};
  $("#ovVehicle").innerHTML =
    `<div class="kv" style="font-size:16px">${esc(v.vin)}</div>` +
    `<div class="dim">${esc(d.maker || "")}</div>` +
    `<div class="dim">${d.year ? t("год: ") + d.year + " · " : ""}WMI ${esc(d.wmi || "?")} · VDS ${esc(d.vds || "?")}` +
    `${v.vin_source ? " · " + t("из ") + esc(v.vin_source) : ""}</div>`;
}
$("#ovReadVin").onclick = async () => {
  $("#ovVehicle").innerHTML = `<div class="dim">${t("чтение VIN…")}</div>`;
  renderVehicle(await api("/api/vehicle/info"));
};
function ovMetric(label, value, cls) {
  return `<div class="metric"><div class="m-lbl">${label}</div><div class="m-val ${cls || ""}">${value}</div></div>`;
}
const SCAN_DOT = {
  configured: "var(--warn)",
  online: "var(--ok)",
  present: "var(--uds)",
  silent: "var(--muted)",
  adapter_error: "var(--danger)",
};
function scanCard(m) {
  const px = (x) => (typeof x === "number" ? "0x" + x.toString(16).toUpperCase() : "");
  const st = m.state || (m.online ? "online" : "silent");
  const el = document.createElement("div");
  const canOpen = (st === "online" || st === "present" || st === "configured") && m.address_known !== false;
  el.className = "ecucard" + (canOpen ? "" : " off");
  let meta;
  const proto = m.protocol ? `<span class="proto ${esc(m.protocol)}">${esc(m.protocol.toUpperCase())}</span>` : "";
  if (st === "configured") {
    meta = m.address_known === false
      ? `${t("из шлюза")} · ${t("нет CAN id в CBF")}`
      : `${t("из шлюза")} · ${proto} · ${px(m.tx)} · ${t("ещё не опрошен")}`;
  } else if (st === "online") meta = `${esc(m.cbf || "")} · ${proto} · ${px(m.tx)}`;
  else if (st === "present") meta = `${t("на связи")} · ${t("нет DTC-сервиса")}`;
  else if (st === "adapter_error") meta = `<span class="bad">${t("Ошибка адаптера")}</span>`;
  else meta = t("нет ответа");
  el.innerHTML =
    `<div class="top"><span class="sdot" style="background:${SCAN_DOT[st] || "var(--muted)"}"></span>` +
    `<span class="nm">${esc(m.name)}</span>` +
    `${st === "online" && m.dtc ? `<span class="faults">${m.dtc} DTC</span>` : ""}</div>` +
    `<div class="meta">${meta}</div>`;
  if (canOpen) el.onclick = () => goModule(m.id, "dtc", m.name);
  return el;
}
function scanMetrics(online, count, total, protos) {
  $("#ovMetrics").innerHTML =
    ovMetric(t("ЭБУ онлайн"), `${online} <span style="font-size:13px;color:var(--muted)">/ ${count}</span>`) +
    ovMetric(t("ошибок (DTC)"), total, total ? "bad" : "ok") +
    ovMetric(t("протокол"), protos || "—");
}
let _scanES = null;
let _gatewayModules = null;
$("#ovScan").onclick = () => {
  const ch = $("#ovChassis").value;
  if (_scanES) { _scanES.close(); _scanES = null; }
  $("#ovScanStat").textContent = t("сканирую…");
  const grid = $("#ovScanGrid"); grid.innerHTML = "";
  let count = 0, protos = "—";
  const gwNames = (_gatewayModules || []).map((m) => m.ecu || m.id).filter(Boolean);
  const qs = gwNames.length
    ? "?modules=" + encodeURIComponent(gwNames.join(","))
    : (ch ? "?chassis=" + ch : "");
  const es = new EventSource("/api/vehicle/scan/stream" + qs);
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
  if (!info || info.error) { box.innerHTML = info && info.error ? `<div class="warn">⚠ ${esc(info.error)}</div>` : ""; return; }
  _gw = info;
  _gatewayModules = (info.modules || []).filter((m) => m.configured !== false);
  // auto-select the detected chassis everywhere + show engine on the vehicle card
  if (info.chassis_token) {
    const el = $("#chassis");
    if (el && [...el.options].some((o) => o.value === info.chassis_token)) el.value = info.chassis_token;
    applyChassis(info.chassis_token, true);       // auto-detected: hide the manual chooser
    setCarImage(info.chassis_token);
  }
  if (info.engine) {
    const v = $("#ovVehicle");
    if (v) v.innerHTML = `<div class="kv" style="font-size:16px">${esc(info.engine)}</div>` +
      `<div class="dim">${esc([info.chassis, info.body].filter(Boolean).join(" · "))}</div>`;
  }
  const present = (info.options || []).filter((o) => /vorhanden|aktiv|erlaubt/i.test(o.value) && !/nicht/i.test(o.value));
  const ecus = (info.ecus || []).filter((e) => e.present);
  const canIst = (info.can_ist || []).filter((e) => e.present);
  const compare = info.can_compare || {};
  const compareLine = [
    (compare.actual_only || []).length ? `${t("только CAN-Ist")}: ${(compare.actual_only || []).map(esc).join(", ")}` : "",
    (compare.configured_only || []).length ? `${t("только CAN-Soll")}: ${(compare.configured_only || []).map(esc).join(", ")}` : "",
  ].filter(Boolean).join(" · ");
  const raw = info.gateway_raw || {};
  const sources = (info.decoded_sources || []).map((s) => `${esc(s.label || s.domain)} (${esc(s.service)})`).join(", ");
  box.innerHTML =
    `<div class="card"><div class="clabel">${t("комплектация (из шлюза)")}</div>` +
    `<div class="kv" style="font-size:18px">${esc(info.engine || "—")}</div>` +
    `<div class="dim">${esc([info.chassis, info.body].filter(Boolean).join(" · "))}</div>` +
    (sources ? `<div class="dim">${t("декодировано")}: ${sources}</div>` : "") +
    (raw.can_ist_310800 ? `<div class="dim mono">CAN-Ist 310800: ${esc(raw.can_ist_310800)}</div>` : "") +
    (raw.can_soll_310700 ? `<div class="dim mono">CAN-Soll 310700: ${esc(raw.can_soll_310700)}</div>` : "") +
    (present.length ? `<div class="chips" style="margin-top:10px">` +
      present.map((o) => `<span class="chip">${esc(o.name.replace(/^SA:\s*/, ""))}</span>`).join("") + `</div>` : "") +
    (ecus.length ? `<div class="clabel" style="margin-top:12px">${t("блоки CAN-B по конфигурации")}</div>` +
      `<div class="chips">` + ecus.map((e) => `<span class="chip">${esc(e.name)}</span>`).join("") + `</div>` : "") +
    (canIst.length ? `<div class="clabel" style="margin-top:12px">${t("блоки CAN-B фактически")}</div>` +
      `<div class="chips">` + canIst.map((e) => `<span class="chip">${esc(e.name)}</span>`).join("") + `</div>` : "") +
    (compareLine ? `<div class="dim" style="margin-top:8px">${t("расхождение")}: ${compareLine}</div>` : "") +
    `</div>`;
  renderGatewayModuleState(_gatewayModules);
  renderModuleTable(_gatewayModules);
  setModuleDropdowns(_gatewayModules.filter((m) => m.address_known !== false));
}

function renderGatewayModuleState(modules) {
  const grid = $("#ovScanGrid");
  grid.innerHTML = "";
  modules.forEach((m) => grid.appendChild(scanCard({ ...m, state: "configured" })));
  const known = modules.filter((m) => m.address_known !== false);
  const protos = [...new Set(known.map((m) => (m.protocol || "").toUpperCase()).filter(Boolean))].join(" / ");
  scanMetrics(0, modules.length, 0, protos || t("из шлюза"));
  $("#ovScanStat").textContent = modules.length
    ? `${t("CAN-B из шлюза: ")}${modules.length}; ${t("с CAN id: ")}${known.length}`
    : t("CAN-B конфигурация не вернула блоки");
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
function moduleHex(x) {
  return typeof x === "number" ? "0x" + x.toString(16).toUpperCase() : "—";
}
function moduleLabel(m) {
  const src = m.source === "gateway" ? ` · ${t("из шлюза")}` : "";
  return `${m.name || m.ecu || m.id}  ·  ${moduleHex(m.tx)}${src}`;
}
function setModuleDropdowns(modules) {
  ["#dtcModule", "#codeModule"].forEach((sel) => {
    const el = $(sel);
    el.innerHTML = `<option value="" disabled selected>${t("— выбери модуль —")}</option>`;
    modules.forEach((m) => {
      const o = document.createElement("option");
      o.value = m.id;
      o.textContent = moduleLabel(m);   // textContent — safe
      el.appendChild(o);
    });
  });
}
function renderModuleTable(modules) {
  const tb = $("#modTable tbody");
  tb.innerHTML = "";
  if (!modules.length) {
    tb.innerHTML = `<tr><td colspan="8" class="muted">${t("Нет модулей для этого шасси")}</td></tr>`;
    return;
  }
  modules.forEach((m) => {
    const tr = document.createElement("tr");
    const part = (m.part_numbers && m.part_numbers[0]) || "—";
    const baud = m.baudrate ? (m.baudrate / 1000).toFixed(m.baudrate % 1000 ? 1 : 0) + "k" : "—";
    const src = m.source === "gateway"
      ? ` <span class="muted" title="${t("из шлюза")}">G</span>`
      : m.id_source === "cbf"
        ? ` <span class="muted" title="${t("из Vediamo CBF")}">✓</span>`
        : ` <span class="muted" title="${t("стандартная адресация, требует проверки")}">?</span>`;
    const canAct = m.address_known !== false;
    const actions = canAct
      ? `<button class="linkbtn" data-act="id" data-id="${esc(m.id)}">${t("ID")}</button>
        <button class="linkbtn" data-act="dtc" data-id="${esc(m.id)}" data-name="${esc(m.name)}">${t("Ошибки")}</button>
        <button class="linkbtn" data-act="coding" data-id="${esc(m.id)}" data-name="${esc(m.name)}">${t("Код")}</button>`
      : `<span class="muted">${t("нет CAN id в CBF")}</span>`;
    tr.innerHTML = `<td>${esc(m.name || m.ecu || m.id)}</td><td><code>${esc(m.cbf || m.ecu || "")}</code></td>
      <td><code>${moduleHex(m.tx)}</code>${src}</td>
      <td><code>${moduleHex(m.rx)}</code></td>
      <td>${m.protocol ? `<span class="proto ${esc(m.protocol)}">${esc(m.protocol.toUpperCase())}</span>` : "—"}</td>
      <td class="muted">${baud}</td>
      <td class="muted">${esc(part)}</td>
      <td style="white-space:nowrap">${actions}</td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll("button[data-act]").forEach((b) =>
    (b.onclick = () => goModule(b.dataset.id, b.dataset.act, b.dataset.name)));
}

async function loadModules(chassis = "") {
  const tb = $("#modTable tbody");
  let modules = [];
  try {
    const r = await api("/api/modules" + (chassis ? "?chassis=" + chassis : ""));
    modules = r.modules || [];
  } catch (e) {
    tb.innerHTML = `<tr><td colspan="8" class="muted">${t("Бэкенд недоступен")} (${esc(e.message || e)})${t(". Запусти uvicorn backend.main:app")}</td></tr>`;
    return;
  }
  renderModuleTable(modules);
  loadCatalog($("#chassis").value);
  setModuleDropdowns(modules);
}
$("#chassis").onchange = (e) => { _gatewayModules = null; $("#gwInfo").innerHTML = ""; loadModules(e.target.value); };

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
      ? `<button class="linkbtn" data-dtc="${esc(e.ecu)}">DTC</button> <button class="linkbtn" data-id="${esc(e.ecu)}">${t("ID")}</button>`
      : `<span class="muted" title="${t("нет CAN id в CBF")}">—</span>`;
    tr.innerHTML = `<td><code>${esc(e.ecu)}</code></td><td>${esc((e.protocol || "").toUpperCase())}</td>
      <td><code>${hx(e.can_request)}</code></td><td><code>${hx(e.can_response)}</code></td>
      <td class="muted">${baud}</td><td>${esc((e.chassis || []).join(", "))}</td>
      <td class="muted">${esc((e.part_numbers && e.part_numbers[0]) || "—")}</td><td>${act}</td>`;
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
  if (r.error) { box.innerHTML = `<b>${t("Ошибка:")}</b> ${esc(r.error)}`; return; }
  box.innerHTML = "<b>" + esc(id) + "</b><br>" +
    Object.entries(r.info).map(([k, v]) => `${esc(k)}: <code>${esc(v ?? "—")}</code>`).join("<br>");
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
    note.innerHTML = `<span class="bad">⚠ ${t("Ошибка адаптера")}: ${esc(r.detail || "")}</span>`; return;
  }
  if (r.status === "no_response") {
    note.innerHTML = `<span class="bad">✗ ${t("Нет ответа от блока")}</span>`; return;
  }
  if (r.status === "present") {
    note.innerHTML = `<span style="color:var(--warn)">● ${t("Блок на связи, но не отдаёт ошибки")} (${esc(r.detail || "")})</span>`; return;
  }
  if (!r.dtcs || !r.dtcs.length) {
    note.innerHTML = `<span class="ok">✓ ${t("Блок ответил: ошибок нет")}${via}</span>`; return;
  }
  note.classList.add("hidden");
  r.dtcs.forEach((d) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><button class="linkbtn dtc-code" data-code="${esc(d.code)}"><code>${esc(d.code)}</code></button></td><td>${esc(d.status)}</td>
      <td>${esc(d.description || "")}</td><td><code>${esc(d.raw)}</code></td>`;
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
  const li = (arr) => (arr || []).map((x) => `<li>${esc(x)}</li>`).join("");
  const steps = (c.checks || []).map((s, i) =>
    `${i ? '<span class="arrow">→</span>' : ""}<span class="step">${i + 1}. ${esc(s)}</span>`).join("");
  const lk = c.linked || { measurement: [], service: [] };
  const grpChip = (g) => `<button class="chip linkbtn" data-grp="${esc(g.path)}">${esc(g.title)}</button>`;
  const imgs = (c.media || []).filter((m) => m.kind !== "doc");
  const docs = (c.media || []).filter((m) => m.kind === "doc");
  const schematics = imgs.filter((m) => m.kind === "schematic");
  const realMedia = imgs.filter((m) => m.kind !== "schematic");
  const mediaFigure = (m) =>
    `<figure class="diag-media"><figcaption>${esc(m.title)}</figcaption>` +
    `<button class="diag-media-open" type="button" data-full="${esc(m.src)}" data-title="${esc(m.title)}">` +
    `<img src="${esc(m.src)}" alt="${esc(m.title)}" loading="lazy"></button></figure>`;
  const schematicsHtml = schematics.length
    ? `<h3>${t("Схемы диагностики")}</h3><div class="diag-media-grid">${schematics.map(mediaFigure).join("")}</div>`
    : "";
  const docsHtml = docs.length
    ? `<div class="diag-docs">` +
      docs.map((d) => `<a class="chip" href="${esc(d.src)}" target="_blank" rel="noopener">${esc(d.title)}</a>`).join("") +
      `</div>`
    : "";
  const starfinderHtml = (realMedia.length || docs.length)
    ? `<h3>${t("Материалы StarFinder")}</h3>` +
      (docsHtml ? `<div class="dim">${t("Документы")}</div>${docsHtml}` : "") +
      (realMedia.length ? `<div class="dim">${t("Изображения")}</div><div class="diag-media-grid">${realMedia.map(mediaFigure).join("")}</div>` : "")
    : "";
  const comp = (c.component && c.component.name)
    ? `<div class="dim" style="margin-top:4px">${t("ЭБУ")}: <code>${esc(c.component.code)}</code> · ${esc(c.component.name)}</div>` : "";
  box.innerHTML =
    `<div class="card">` +
    `<div style="display:flex; justify-content:space-between; align-items:start; gap:12px">` +
    `<div><b style="font-size:15px"><code>${esc(c.code)}</code> — ${esc(c.description)}</b>` +
    `<div class="dim" style="margin-top:4px">${esc(L.area || "")}: ${esc(c.area || "")}</div>` + comp + `</div>` +
    `<button class="ghost" id="drillClose">${t("Закрыть")}</button></div>` +
    `<h3 style="margin-top:16px">${esc(L.causes || "")}</h3><ul style="margin:0; padding-left:20px">${li(c.causes)}</ul>` +
    `<h3>${esc(L.checks || "")}</h3><div class="flow">${steps}</div>` +
    ((lk.measurement && lk.measurement.length) ?
      `<h3>${t("Связанные группы измерений")}</h3><div class="chips">${lk.measurement.map(grpChip).join("")}</div>` : "") +
    ((lk.service && lk.service.length) ?
      `<h3>${t("Связанные процедуры")}</h3><div class="chips">${lk.service.map(grpChip).join("")}</div>` : "") +
    schematicsHtml +
    starfinderHtml +
    sfHint(c.starfinder) +
    `</div>`;
  $("#drillClose").onclick = () => (box.innerHTML = "");
  box.querySelectorAll("button[data-grp]").forEach((b) =>
    (b.onclick = () => openGroup(b.dataset.grp)));
  box.querySelectorAll(".diag-media-open").forEach((b) =>
    (b.onclick = () => openMediaLightbox(b.dataset.full, b.dataset.title)));
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
    if (msg.error) { toast(t("Live: ") + msg.error); return; }
    renderGauges(msg.frame);
  };
  ws.onerror = () => toast(t("Live-поток: ошибка соединения"));
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

function renderMeasureCoverage(cov) {
  const box = $("#measCoverage");
  if (!box) return;
  if (!cov || !cov.available) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  const rows = Number(cov.service_rows || 0);
  const matched = Number(cov.matched_rows || 0);
  const normalized = Number(cov.normalized_rows || 0);
  const outputRows = Number(cov.output_rows || 0);
  const rawTypeRows = Number(cov.raw_type_rows || 0);
  const unitRows = Number(cov.unit_rows || 0);
  const formulaRows = Number(cov.formula_rows || 0);
  const missingJobs = Number(cov.missing_jobs || 0);
  const pct = Number(cov.coverage_pct || 0);
  const state = rows ? (pct >= 95 ? "ok" : pct >= 60 ? "warn" : "bad") : "empty";
  const title = rows ? `${pct.toFixed(pct % 1 ? 1 : 0)}%` : "—";
  const norm = normalized ? ` · ${normalized} ${t("нормализовано")}` : "";
  const output = outputRows
    ? ` · ${t("выход")} ${outputRows}/${matched || rows} · ${t("тип")} ${rawTypeRows}` +
      ` · ${t("единицы")} ${unitRows} · ${t("формула")} ${formulaRows}`
    : "";
  const details = rows
    ? `${matched} / ${rows} ${t("строк с request")} · ${missingJobs} ${t("job без request")}${norm}${output}`
    : t("нет импортированных job для этого ЭБУ");
  box.className = `coverage ${state}`;
  box.innerHTML =
    `<div class="coverage-main"><span>${t("CBF coverage")}</span><b>${esc(title)}</b></div>` +
    `<div class="coverage-detail">${esc(details)}</div>`;
}

async function initMeas() {
  const r = await api("/api/measure/ecus");
  const sel = $("#measEcu");
  if (!r.available) { sel.innerHTML = `<option>${t("группы измерений недоступны")}</option>`; return; }
  sel.innerHTML = `<option value="">${t("— выбери ЭБУ —")}</option>` +
    r.ecus.map((e) => `<option>${esc(e)}</option>`).join("");
}
$("#measEcu") && ($("#measEcu").onchange = async () => {
  const ecu = $("#measEcu").value;
  const gsel = $("#measGroup");
  gsel.innerHTML = "";
  $("#svcDetails").innerHTML = "";
  renderMeasureCoverage(null);
  if (!ecu) return;
  const g = await api("/api/measure/groups?module=" + encodeURIComponent(ecu) + "&lang=" + (window.LANG || "ru"));
  renderMeasureCoverage(g.coverage);
  gsel.innerHTML = g.measurement.map((m) =>
    `<option value="${esc(m.path)}">${esc(m.title)} (${m.count})  ·  ${m.auto ? "CBF" : "." + esc(m.source || "vsg")}</option>`).join("")
    || `<option value="">${t("нет измерительных групп")}</option>`;
  // service procedures -> select
  $("#svcSelect").innerHTML = `<option value="">${t("— выбери процедуру —")} (${g.service.length})</option>` +
    g.service.map((s) => `<option value="${esc(s.path)}">${esc(s.title)} · ${s.steps} ${t("шаг.")}</option>`).join("");
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
  const li = (arr) => arr.map((s) => `<span class="chip">${esc(s.label || s.job)}</span>`).join("");
  const flow = routines.map((s, i) =>
    `${i ? '<span class="arrow">→</span>' : ""}<span class="step">${esc(s.label || s.job)}</span>`).join("");
  box.innerHTML =
    `<div class="card"><b>${esc(d.title || g.title)}</b>` +
    (d.what ? `<div class="muted" style="margin-top:6px"><b>${t("Что:")}</b> ${esc(d.what)}<br><b>${t("Когда:")}</b> ${esc(d.when)}<br><b>${t("Как:")}</b> ${esc(d.how)}</div>` : "") +
    (d.warn ? `<div class="warn" style="margin-top:10px">⚠ ${esc(d.warn)}</div>` : "") +
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
        esc(steps.map((s) => s.label || s.job).join(" · ")) + "</div>" : "";
    box.innerHTML = `<b>${esc(d.title)}</b><div class="muted" style="margin-top:6px">` +
      `<b>${t("Что:")}</b> ${esc(d.what)}<br><b>${t("Когда:")}</b> ${esc(d.when)}<br><b>${t("Как:")}</b> ${esc(d.how)}</div>` +
      (d.warn ? `<div class="warn" style="margin-top:10px">⚠ ${esc(d.warn)}</div>` : "") + stepList;
    box.classList.remove("hidden");
  } else {
    box.classList.add("hidden");
  }
  await refreshMeas(path);
  $("#measAuto").disabled = false;
}
$("#measLoad") && ($("#measLoad").onclick = () => openGroup($("#measGroup").value));
async function refreshMeas(path) {
  const r = await api("/api/measure/read?path=" + encodeURIComponent(path) +
    "&lang=" + (window.LANG || "ru"), undefined, true);
  const g = $("#gauges");
  const readNote = (p) => {
    if (!p.read_status || p.read_status === "simulated" || p.read_status === "hw_ok") return "";
    const sid = p.read_sid ? ` SID ${p.read_sid}` : "";
    if (p.read_status === "error") return `${t("ошибка чтения")}${sid}`;
    if (p.read_status === "na" || p.read_status === "missing_request")
      return `N/A${sid}`;
    return `${t("запрос заблокирован")}${sid}`;
  };
  // per-parameter request/response debug record for the tooltip
  window._dbgRead = (p) => [
    p.read_req ? `req ${p.read_req}` : "",
    p.read_resp ? `resp ${p.read_resp}` : "",
    (p.read_raw !== null && p.read_raw !== undefined) ? `raw ${p.read_raw}` : "",
    p.read_reason ? p.read_reason : "",
  ].filter(Boolean).join("\n");
  // Load-collective blocks (PRES_BLK*) are exposed as one DiagService per cell
  // (job `<prefix>_COL_<n>`). Stitch the cells of one block into a single strip
  // instead of scattering dozens of gauges across the dashboard.
  const COL = /^(.+)_COL_(\d+)$/;
  const blocks = {};
  r.values.forEach((p) => {
    const m = COL.exec(p.job);
    if (!m) { renderGauge(g, p, readNote); return; }
    const b = blocks[m[1]] || (blocks[m[1]] = { unit: p.unit || "", cells: [] });
    b.cells.push({ i: Number(m[2]), value: p.value, job: p.job, p });
  });
  Object.keys(blocks).forEach((key) => renderBlock(g, key, blocks[key]));
}

function renderGauge(g, p, readNote) {
  let el = document.getElementById("m_" + p.job);
  if (!el) {
    el = document.createElement("div");
    el.className = "gauge"; el.id = "m_" + p.job;
    el.innerHTML = `<div class="label"></div><div class="vrow"><span class="value"></span><span class="unit"></span></div><div class="sub muted"></div>`;
    g.appendChild(el);
  }
  el.querySelector(".label").textContent = p.label;
  el.querySelector(".value").textContent = p.value;
  el.querySelector(".unit").textContent = " " + (p.unit || "");
  // reference range (norm) for comparison — only for numeric params with a unit
  const ref = (p.unit && p.low != null && p.high != null && p.high !== p.low)
    ? `${t("норма")} ${p.low}–${p.high} ${p.unit}` : "";
  const status = readNote(p);
  el.querySelector(".sub").textContent = [ref, status].filter(Boolean).join(" · ");
  const dbg = window._dbgRead ? window._dbgRead(p) : "";
  el.title = p.job + (p.note ? "\n(" + p.note + ")" : "") + (dbg ? "\n" + dbg : "");
}

function renderBlock(g, key, b) {
  b.cells.sort((a, c) => a.i - c.i);
  let el = document.getElementById("blk_" + key);
  if (!el) {
    el = document.createElement("div");
    el.className = "block"; el.id = "blk_" + key;
    g.appendChild(el);
  }
  const title = key.replace(/^DT_(BLK3S|BLK)_/, "").replace(/_/g, " ");
  el.innerHTML =
    `<div class="blabel">${esc(title)} <span class="muted">${b.unit ? esc(b.unit) + " · " : ""}${b.cells.length}</span></div>` +
    `<div class="bstrip">` + b.cells.map((cl) => {
      const dbg = (window._dbgRead && cl.p) ? "\n" + window._dbgRead(cl.p) : "";
      return `<span class="bcell" title="COL ${cl.i} · ${esc(cl.job)}${esc(dbg)}">${esc(cl.value)}</span>`;
    }).join("") +
    `</div>`;
}
$("#measAuto").onclick = () => {
  if (measTimer) { clearInterval(measTimer); measTimer = null; $("#measAuto").textContent = t("▶ Авто"); return; }
  const path = $("#measGroup").value;
  if (!path) return;
  $("#measAuto").textContent = t("■ Стоп");
  measTimer = setInterval(() => refreshMeas(path), 500);
};

// ---- measurement dictionary ----
let dictState = { offset: 0, limit: 100, total: 0 };

function dictQuery(reset) {
  if (reset) dictState.offset = 0;
  const p = new URLSearchParams({
    lang: $("#dictLang").value || "ru",
    kind: $("#dictKind").value || "all",
    status: $("#dictStatus").value || "all",
    q: $("#dictSearch").value || "",
    limit: String(dictState.limit),
    offset: String(dictState.offset),
  });
  return p.toString();
}

function renderDictStats(stats) {
  const src = stats.source_count || 0;
  const done = stats.translated_count || 0;
  const miss = stats.missing_count || 0;
  const pct = src ? Math.round(done * 100 / src) : 0;
  const status = $("#dictStatus")?.value || "all";
  const dictMetric = (filterStatus, label, value, hint) =>
    `<button type="button" class="metric dict-filter ${status === filterStatus ? "active" : ""}" data-status="${filterStatus}">` +
    `<span class="m-lbl">${esc(label)}</span>` +
    `<span class="m-val">${value}</span>` +
    (hint ? `<span class="m-hint">${esc(hint)}</span>` : "") +
    `</button>`;
  $("#dictStats").innerHTML =
    dictMetric("translated", t("переведено"), `${done} <span>/ ${src}</span>`, t("показать готовые")) +
    dictMetric("missing", t("осталось"), miss, t("показать без перевода")) +
    dictMetric("all", t("покрытие"), `${pct}%`, t("показать все"));
  $("#dictStats").querySelectorAll(".dict-filter").forEach((btn) => {
    btn.onclick = () => {
      $("#dictStatus").value = btn.dataset.status || "all";
      loadDict(true);
    };
  });
}

function renderDictRows(rows) {
  const tb = $("#dictTable tbody");
  tb.innerHTML = "";
  $("#dictEmpty").classList.toggle("hidden", rows.length > 0);
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    tr.dataset.key = r.localization_key;
    tr.dataset.original = r.translation || "";
    const kind = r.kind === "group" ? t("Группа") : r.kind === "service" ? t("Параметр") : r.kind;
    tr.innerHTML =
      `<td><span class="chip">${esc(kind)}</span></td>` +
      `<td><div class="dict-source">${esc(r.source_text)}</div>` +
      `<code>${esc(r.localization_key)}</code>` +
      `<div class="dim">${esc(r.source_context || "")}</div></td>` +
      `<td><textarea class="dict-input" rows="2">${esc(r.translation || "")}</textarea>` +
      `<div class="dim dict-state"></div></td>` +
      `<td><div class="dict-actions">` +
      `<button class="ghost dict-save">${t("Сохранить")}</button>` +
      `<button class="ghost dict-clear">${t("Очистить")}</button>` +
      `</div></td>`;
    const input = tr.querySelector(".dict-input");
    const state = tr.querySelector(".dict-state");
    input.oninput = () => {
      const changed = input.value !== tr.dataset.original;
      tr.classList.toggle("dirty", changed);
      state.textContent = changed ? t("изменено") : "";
    };
    tr.querySelector(".dict-save").onclick = () => saveDictRow(tr);
    tr.querySelector(".dict-clear").onclick = () => {
      input.value = "";
      input.dispatchEvent(new Event("input"));
      saveDictRow(tr);
    };
    tb.appendChild(tr);
  });
}

async function loadDict(reset) {
  const langSel = $("#dictLang");
  if (langSel && !langSel.value) langSel.value = window.LANG || "ru";
  const r = await api("/api/measure/translations?" + dictQuery(reset));
  if (r.error) { toast(r.error); return; }
  dictState.total = r.total || 0;
  renderDictStats(r.stats || {});
  renderDictRows(r.rows || []);
  const from = dictState.total ? dictState.offset + 1 : 0;
  const to = Math.min(dictState.offset + dictState.limit, dictState.total);
  $("#dictPageInfo").textContent = `${from}–${to} ${t("из")} ${dictState.total}`;
  $("#dictPrev").disabled = dictState.offset <= 0;
  $("#dictNext").disabled = dictState.offset + dictState.limit >= dictState.total;
}

async function saveDictRow(tr) {
  const input = tr.querySelector(".dict-input");
  const state = tr.querySelector(".dict-state");
  state.textContent = t("сохранение…");
  const r = await api("/api/measure/translations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      localization_key: tr.dataset.key,
      lang: $("#dictLang").value || "ru",
      text: input.value,
    }),
  });
  if (r.error) {
    state.textContent = r.error;
    state.classList.add("bad");
    return;
  }
  tr.dataset.original = input.value.trim();
  tr.classList.remove("dirty");
  state.classList.remove("bad");
  state.textContent = t("сохранено");
  const stats = await api("/api/measure/translations/stats?lang=" + encodeURIComponent($("#dictLang").value || "ru"), undefined, true);
  if (!stats.error) renderDictStats(stats);
}

$("#dictRefresh") && ($("#dictRefresh").onclick = () => loadDict(true));
$("#dictPrev") && ($("#dictPrev").onclick = () => {
  dictState.offset = Math.max(0, dictState.offset - dictState.limit);
  loadDict(false);
});
$("#dictNext") && ($("#dictNext").onclick = () => {
  dictState.offset += dictState.limit;
  loadDict(false);
});
["#dictLang", "#dictKind", "#dictStatus"].forEach((sel) => {
  const el = $(sel);
  if (el) el.onchange = () => loadDict(true);
});
let _dictSearchTimer = null;
$("#dictSearch") && ($("#dictSearch").oninput = () => {
  clearTimeout(_dictSearchTimer);
  _dictSearchTimer = setTimeout(() => loadDict(true), 250);
});

// ---- local reference links ----
let refState = { offset: 0, limit: 60, total: 0, statsLoaded: false };

function refQuery(reset) {
  if (reset) refState.offset = 0;
  const p = new URLSearchParams({
    q: $("#refSearch").value || "",
    tag: $("#refTag").value || "",
    vehicle: $("#refVehicle").value || "",
    limit: String(refState.limit),
    offset: String(refState.offset),
  });
  return p.toString();
}

function fillRefFilters(stats, canStats) {
  const tagSel = $("#refTag");
  const vehSel = $("#refVehicle");
  const tagValue = tagSel.value;
  const vehValue = vehSel.value;
  const mergedTags = { ...(stats.tags || {}) };
  Object.entries(canStats?.tags || {}).forEach(([key, count]) => {
    mergedTags[key] = (mergedTags[key] || 0) + count;
  });
  const mergedVehicles = { ...(stats.vehicles || {}) };
  Object.entries(canStats?.vehicles || {}).forEach(([key, count]) => {
    mergedVehicles[key] = (mergedVehicles[key] || 0) + count;
  });
  const tags = Object.keys(mergedTags).sort();
  const vehicles = Object.keys(mergedVehicles).sort();
  tagSel.innerHTML = `<option value="">${t("Все теги")}</option>` +
    tags.map((tag) => `<option value="${esc(tag)}">${esc(tag)} (${mergedTags[tag]})</option>`).join("");
  vehSel.innerHTML = `<option value="">${t("Все кузова")}</option>` +
    vehicles.map((v) => `<option value="${esc(v)}">${esc(v)} (${mergedVehicles[v]})</option>`).join("");
  if ([...tagSel.options].some((o) => o.value === tagValue)) tagSel.value = tagValue;
  if ([...vehSel.options].some((o) => o.value === vehValue)) vehSel.value = vehValue;
}

function renderRefStats(stats) {
  const total = stats.total || 0;
  const net = (stats.tags || {})["mercedes-network"] || 0;
  const can = (stats.tags || {})["can"] || 0;
  const adapters = ((stats.tags || {})["j2534"] || 0) + ((stats.tags || {})["openport"] || 0);
  $("#refStats").innerHTML =
    `<div class="metric"><span class="m-lbl">${t("ссылок")}</span><span class="m-val">${total}</span></div>` +
    `<div class="metric"><span class="m-lbl">${t("Mercedes network")}</span><span class="m-val">${net}</span></div>` +
    `<div class="metric"><span class="m-lbl">${t("CAN")}</span><span class="m-val">${can}</span></div>` +
    `<div class="metric"><span class="m-lbl">${t("адаптеры")}</span><span class="m-val">${adapters}</span></div>`;
}

function renderRefRows(rows) {
  const grid = $("#refGrid");
  grid.innerHTML = "";
  $("#refEmpty").classList.toggle("hidden", rows.length > 0);
  rows.forEach((r) => {
    const card = document.createElement("article");
    card.className = "ref-card";
    const tags = (r.tags || []).map((tag) => `<span class="chip">${esc(tag)}</span>`).join("");
    const vehicles = (r.vehicle_hints || []).map((v) => `<span class="chip ref-vehicle">${esc(v)}</span>`).join("");
    const folders = (r.folders || []).join(" | ");
    card.innerHTML =
      `<div class="ref-title">${esc(r.title || r.url)}</div>` +
      `<div class="ref-domain">${esc(r.domain || "")}</div>` +
      `<div class="chips">${tags}${vehicles}</div>` +
      (folders ? `<div class="dim">${esc(folders)}</div>` : "") +
      `<div class="ref-actions"><a class="ghost ref-open" href="${esc(r.url)}" target="_blank" rel="noopener">${t("Открыть")}</a></div>`;
    grid.appendChild(card);
  });
}

function renderCanExampleStats(stats) {
  const total = stats.total || 0;
  const ids = Object.keys(stats.can_ids || {}).length;
  const vehicles = Object.keys(stats.vehicles || {}).length;
  $("#canExampleStats").innerHTML =
    `<div class="metric"><span class="m-lbl">${t("фактов")}</span><span class="m-val">${total}</span></div>` +
    `<div class="metric"><span class="m-lbl">${t("CAN ID")}</span><span class="m-val">${ids}</span></div>` +
    `<div class="metric"><span class="m-lbl">${t("кузовов")}</span><span class="m-val">${vehicles}</span></div>`;
}

function renderCanExamples(rows) {
  const grid = $("#canExampleGrid");
  grid.innerHTML = "";
  $("#canExampleEmpty").classList.toggle("hidden", rows.length > 0);
  rows.forEach((r) => {
    const card = document.createElement("article");
    card.className = "can-example-card";
    const tags = (r.tags || []).map((tag) => `<span class="chip">${esc(tag)}</span>`).join("");
    const speed = r.speed_kbit_s ? `${r.speed_kbit_s} kbit/s` : "—";
    const canId = r.can_id || "—";
    const data = r.data_hex ? `<code>${esc(r.data_hex)}</code>` : `<span class="muted">—</span>`;
    card.innerHTML =
      `<div class="can-example-head"><b>${esc(canId)}</b><span>${esc(r.body || r.vehicle || "")}</span></div>` +
      `<div class="can-example-meta">${esc(speed)} · DLC ${esc(r.dlc ?? "—")}</div>` +
      `<div class="can-example-route">${esc(r.source_node || "—")} → ${esc(r.target_node || "—")}</div>` +
      `<div class="can-example-data">${data}</div>` +
      `<div class="can-example-meaning">${esc(r.payload_meaning || "")}</div>` +
      (r.safety_note ? `<div class="warn can-example-safety">${esc(r.safety_note)}</div>` : "") +
      `<div class="chips">${tags}</div>` +
      `<div class="ref-actions"><a class="ghost ref-open" href="${esc(r.source_url)}" target="_blank" rel="noopener">${t("Источник")}</a></div>`;
    grid.appendChild(card);
  });
}

async function loadCanExamples() {
  const p = new URLSearchParams({
    q: $("#refSearch").value || "",
    tag: $("#refTag").value || "",
    vehicle: $("#refVehicle").value || "",
    limit: "100",
    offset: "0",
  });
  const r = await api("/api/can/examples?" + p.toString(), undefined, true);
  if (r.error) { toast(r.error); return; }
  renderCanExampleStats(r.stats || {});
  renderCanExamples(r.rows || []);
}

async function loadRefs(reset) {
  const r = await api("/api/references?" + refQuery(reset));
  if (r.error) { toast(r.error); return; }
  const canStats = await api("/api/can/examples/stats", undefined, true).catch(() => ({}));
  refState.total = r.total || 0;
  const stats = r.stats || {};
  fillRefFilters(stats, canStats || {});
  renderRefStats(stats);
  renderRefRows(r.rows || []);
  const from = refState.total ? refState.offset + 1 : 0;
  const to = Math.min(refState.offset + refState.limit, refState.total);
  $("#refPageInfo").textContent = `${from}–${to} ${t("из")} ${refState.total}`;
  $("#refPrev").disabled = refState.offset <= 0;
  $("#refNext").disabled = refState.offset + refState.limit >= refState.total;
  await loadCanExamples();
}

$("#refRefresh") && ($("#refRefresh").onclick = () => loadRefs(true));
$("#refPrev") && ($("#refPrev").onclick = () => {
  refState.offset = Math.max(0, refState.offset - refState.limit);
  loadRefs(false);
});
$("#refNext") && ($("#refNext").onclick = () => {
  refState.offset += refState.limit;
  loadRefs(false);
});
["#refTag", "#refVehicle"].forEach((sel) => {
  const el = $(sel);
  if (el) el.onchange = () => loadRefs(true);
});
let _refSearchTimer = null;
$("#refSearch") && ($("#refSearch").oninput = () => {
  clearTimeout(_refSearchTimer);
  _refSearchTimer = setTimeout(() => loadRefs(true), 250);
});

// ---- variant coding ----
let vcState = { coding: "", domain: "", dump: 0 };
$("#vcLoad").onclick = async () => {
  const mod = $("#codeModule").value;
  const r = await api("/api/coding/domains" + (mod ? "?module=" + mod : ""));
  const sel = $("#vcDomain");
  if (!r.available) { sel.innerHTML = `<option>${t("CBF недоступны (MACDIAG_CBF_DIR)")}</option>`; return; }
  sel.innerHTML = r.domains.map((d) => `<option value="${esc(d.domain)}" data-dump="${d.dump_size}" data-rlid="${esc(d.read_lid || "")}" data-wlid="${esc(d.write_lid || "")}" data-sec="${d.sec_level || 0}">${esc(d.domain)} (${d.fragment_count} ${t("парам.")}, ${d.dump_size}B, LID ${esc(d.read_lid || "?")})</option>`).join("");
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
        f.options.map((o) => `<option${o === f.current ? " selected" : ""}>${esc(o)}</option>`).join("") +
        `</select>`;
    } else {
      valCell = `<span class="muted">${esc(f.current ?? f.value ?? "—")}</span>`;
    }
    tr.innerHTML = `<td>${esc(f.name)}${f.approx ? ' <span class="muted" title="длина приблизительна">~</span>' : ""}</td>
      <td class="muted">${esc(f.byte_bit_pos)}+${esc(f.bit_length)}</td><td>${valCell}</td>`;
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
  renderMeasureCoverage(null);
  refreshStatus();
  loadModules($("#chassis").value);
  initMeas();
  loadOverview();
  if ($("#dict").classList.contains("active")) {
    $("#dictLang").value = window.LANG || "ru";
    loadDict(true);
  }
  if ($("#refs").classList.contains("active")) loadRefs(true);
};

// ---- debug traffic log ----
let _dbgOpen = false;
function dbgFmt(e) {
  const ts = new Date(e.ts * 1000).toLocaleTimeString();
  if (e.kind === "error") return `<span class="err">${ts}  ⚠ ${esc(e.fn)} status ${esc(e.status)} ${esc(e.msg || "")}</span>`;
  const proto = ((e.kind || "") + "   ").slice(0, 3).toUpperCase();
  let tail, cls;
  if (e.timeout) { tail = "… timeout"; cls = "to"; }
  else if (e.nrc) { tail = "✗ NRC " + esc(e.nrc); cls = "nrc"; }
  else { tail = "✓ " + esc(e.resp || ""); cls = "ok"; }
  const rx = e.rx ? " [" + esc(e.rx) + "]" : "";
  return `${ts}  ${proto}  ${esc(e.tx)} → ${esc(e.req)}${rx}  ${e.ms}ms  <span class="${cls}">${tail}</span>`;
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
