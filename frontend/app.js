const $ = (s) => document.querySelector(s);
const api = (p, opt) => fetch(p, opt).then((r) => r.json());

// ---- tabs ----
document.querySelectorAll(".tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    $("#" + b.dataset.tab).classList.add("active");
  };
});

// ---- connection ----
async function refreshStatus() {
  const s = await api("/api/status");
  $("#mode").textContent = s.mode;
  $("#dot").className = "dot " + (s.connected ? "on" : "off");
  $("#connText").textContent = s.connected ? "подключено" : "не подключено";
  $("#connBtn").textContent = s.connected ? "Отключить" : "Подключить";
  $("#connBtn").dataset.connected = s.connected;
}
$("#connBtn").onclick = async () => {
  const connected = $("#connBtn").dataset.connected === "true";
  await api(connected ? "/api/disconnect" : "/api/connect", { method: "POST" });
  refreshStatus();
};

// ---- modules dropdowns ----
async function loadModules(chassis = "") {
  const { modules } = await api("/api/modules" + (chassis ? "?chassis=" + chassis : ""));
  // table
  const tb = $("#modTable tbody");
  tb.innerHTML = "";
  modules.forEach((m) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${m.name}</td><td><code>0x${m.tx.toString(16).toUpperCase()}</code></td>
      <td><code>0x${m.rx.toString(16).toUpperCase()}</code></td><td>${m.protocol.toUpperCase()}</td>
      <td><button class="linkbtn" data-id="${m.id}">Идентифицировать</button></td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll("button").forEach((b) => (b.onclick = () => identify(b.dataset.id)));
  // dropdowns
  ["#dtcModule", "#codeModule"].forEach((sel) => {
    const el = $(sel);
    el.innerHTML = '<option value="">Двигатель / OBD (0x7E0)</option>';
    modules.forEach((m) => {
      const o = document.createElement("option");
      o.value = m.id; o.textContent = m.name;
      el.appendChild(o);
    });
  });
}
$("#chassis").onchange = (e) => loadModules(e.target.value);

async function identify(id) {
  const r = await api("/api/identify?module=" + encodeURIComponent(id));
  const box = $("#modInfo");
  box.classList.remove("hidden");
  if (r.error) { box.innerHTML = `<b>Ошибка:</b> ${r.error}`; return; }
  box.innerHTML = "<b>" + id + "</b><br>" +
    Object.entries(r.info).map(([k, v]) => `${k}: <code>${v ?? "—"}</code>`).join("<br>");
}

// ---- DTC ----
$("#dtcRead").onclick = async () => {
  const mod = $("#dtcModule").value;
  const r = await api("/api/dtc" + (mod ? "?module=" + mod : ""));
  const tb = $("#dtcTable tbody");
  tb.innerHTML = "";
  if (r.error) { alert("Ошибка: " + r.error); return; }
  $("#dtcEmpty").classList.toggle("hidden", r.dtcs.length > 0);
  r.dtcs.forEach((d) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><code>${d.code}</code></td><td>${d.status}</td>
      <td>${d.description || ""}</td><td><code>${d.raw}</code></td>`;
    tb.appendChild(tr);
  });
};
$("#dtcClear").onclick = async () => {
  if (!confirm("Сбросить коды ошибок в выбранном модуле?")) return;
  const mod = $("#dtcModule").value;
  const r = await api("/api/dtc/clear" + (mod ? "?module=" + mod : ""), { method: "POST" });
  alert(r.error ? "Ошибка: " + r.error : "Ошибки сброшены");
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
  const g = $("#gauges");
  frame.forEach((p) => {
    let el = document.getElementById("g" + p.pid);
    if (!el) {
      el = document.createElement("div");
      el.className = "gauge"; el.id = "g" + p.pid;
      el.innerHTML = `<div class="label"></div><div><span class="value"></span><span class="unit"></span></div>`;
      g.appendChild(el);
    }
    el.querySelector(".label").textContent = p.label;
    el.querySelector(".value").textContent = p.value;
    el.querySelector(".unit").textContent = p.unit;
  });
}

// ---- coding ----
$("#codeRead").onclick = async () => {
  const mod = $("#codeModule").value;
  const did = parseInt($("#codeDid").value, 16);
  // reuse identify-style read via dedicated endpoint not present; use generic /api/identify is fixed set,
  // so read through a quick fetch to coding/read is not implemented server-side; show hint.
  $("#codeOut").textContent = "Чтение произвольного DID: используйте вкладку «Модули» → Идентифицировать для VIN/SW. " +
    "Для записи укажите DID и значение ниже.";
};
$("#codeWrite").onclick = async () => {
  if (!confirm("Записать значение в ЭБУ? Это может изменить поведение модуля.")) return;
  const r = await api("/api/coding/write", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      module: $("#codeModule").value || null,
      did: parseInt($("#codeDid").value, 16),
      value_hex: $("#codeVal").value.replace(/\s/g, ""),
    }),
  });
  $("#codeOut").textContent = r.ok ? "OK: значение записано." : "Ошибка: " + (r.error || "unknown");
};

// ---- init ----
refreshStatus();
loadModules();
setInterval(refreshStatus, 5000);
