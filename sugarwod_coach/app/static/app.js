"use strict";

const $ = (sel) => document.querySelector(sel);
const state = { unit: "kg", lifts: [], analysis: null, chart: null, balanceChart: null };

const nf1 = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("de-DE", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const w = (v) => (v == null ? "–" : `${nf1.format(v)} ${state.unit}`);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const dateDe = (iso) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("de-DE") : "–");
const pct = (v) => (v == null ? "–" : `${v > 0 ? "+" : ""}${nf1.format(v)} %`);
const trendCls = (t) => ({ steigend: "up", fallend: "down", stagnierend: "flat" }[t] || "muted");

async function api(path, opts) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.fehler || `Fehler ${r.status}`);
  return data;
}

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ------------------------------------------------------------ Tabs
function showTab(name) {
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === name));
  try { localStorage.setItem("swc-tab", name); } catch (e) { /* egal */ }
  if (name === "verlauf") loadHistory();
}
document.querySelectorAll("nav button").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
document.querySelectorAll("[data-goto]").forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); showTab(a.dataset.goto); }));

// ------------------------------------------------------------ Laden
async function loadAll() {
  const [status, analysis, recent] = await Promise.all([api("api/status"), api("api/analysis"), api("api/workouts?limit=10")]);
  state.unit = status.unit;
  state.analysis = analysis;
  state.lifts = analysis.lifts;
  $("#empty").classList.toggle("hidden", status.workouts > 0);
  renderStatus(status);
  renderOverview(analysis, recent, status);
  renderAnalysis(analysis);
  fillLiftSelects();
}

function renderStatus(s) {
  const formulas = { epley: "Epley", brzycki: "Brzycki", mittel: "Mittelwert Epley/Brzycki" };
  $("#settings").innerHTML = `
    <dt>Einträge</dt><dd>${s.workouts} (${dateDe(s.first)} – ${dateDe(s.last)})</dd>
    <dt>Einheit Export</dt><dd>${esc(s.export_unit)}</dd>
    <dt>Anzeige</dt><dd>${esc(s.unit)}</dd>
    <dt>1RM-Formel</dt><dd>${formulas[s.formula] || esc(s.formula)}</dd>
    <dt>Rundung</dt><dd>${nf1.format(s.plate_increment)} ${esc(s.unit)}</dd>
    <dt>Körpergewicht</dt><dd>${s.body_weight_kg ? nf1.format(s.body_weight_kg) + " kg" : "nicht gesetzt"}</dd>
    <dt>HA-Sensoren</dt><dd>${s.ha_available ? esc(s.sensor_lifts.join(", ")) : "nur im Add-on verfügbar"}</dd>`;
  $("#watch-info").textContent = s.watch_folder
    ? `Alternativ: CSV in den Ordner ${s.watch_folder} legen (z. B. per Samba unter „share“). Er wird jede Minute geprüft.`
    : "";
  $("#imports").innerHTML = s.imports.length
    ? `<tr><th>Datei</th><th>Zeitpunkt</th><th class="num">Zeilen</th><th class="num">neu</th></tr>` +
      s.imports.map((i) => `<tr><td>${esc(i.filename)}</td><td>${new Date(i.at).toLocaleString("de-DE")}</td><td class="num">${i.rows}</td><td class="num">${i.new_rows}</td></tr>`).join("")
    : `<tr><td class="muted">Noch nichts importiert.</td></tr>`;
}

function renderOverview(a, recent, status) {
  const main = status.sensor_lifts.map((n) => a.lifts.find((l) => l.lift === n)).filter(Boolean).slice(0, 4);
  const days30 = new Set(recent.filter((r) => (Date.now() - new Date(r.date)) / 864e5 <= 30).map((r) => r.date)).size;
  $("#stats").innerHTML = [
    ...main.map((l) => `<div class="stat"><div class="l">${esc(l.lift)} 1RM</div><div class="v">${w(l.current_kg)}</div><div class="l ${trendCls(l.trend)}">${esc(l.trend)}</div></div>`),
    `<div class="stat"><div class="l">Letztes Training</div><div class="v">${dateDe(status.last)}</div><div class="l">${status.workouts} Einträge gesamt</div></div>`,
  ].join("");
  $("#recs-short").innerHTML = recList(a.recommendations.slice(0, 4));
  $("#recent").innerHTML = recent.length
    ? recent.map((r) => `<tr><td>${dateDe(r.date)}</td><td>${esc(r.title)}${r.pr ? ' <span class="badge">PR</span>' : ""}</td><td class="num">${esc(r.best_display)}</td></tr>`).join("")
    : `<tr><td class="muted">–</td></tr>`;
  $("#lift-table").innerHTML = `<tr><th>Übung</th><th>Kategorie</th><th class="num">1RM (geschätzt)</th><th class="num">Bestwert</th><th>Trend</th><th>zuletzt</th></tr>` +
    a.lifts.map((l) => `<tr class="${l.current_is_stale ? "stale" : ""}">
      <td><a href="#" data-lift="${esc(l.lift)}">${esc(l.lift)}</a></td><td>${esc(l.category)}</td>
      <td class="num">${w(l.current_kg)}</td><td class="num">${w(l.all_time_kg)}</td>
      <td class="${trendCls(l.trend)}">${esc(l.trend)} ${l.trend_pct != null ? "(" + pct(l.trend_pct) + ")" : ""}</td>
      <td>${dateDe(l.last_date)}</td></tr>`).join("");
  document.querySelectorAll("[data-lift]").forEach((el) => el.addEventListener("click", (e) => {
    e.preventDefault(); $("#h-lift").value = el.dataset.lift; showTab("verlauf");
  }));
}

function recList(recs) {
  if (!recs.length) return `<li class="muted">Keine Auffälligkeiten – weiter so.</li>`;
  return recs.map((r) => `<li><span class="art">${esc(r.art)}</span><b>${esc(r.titel)}</b>${esc(r.text)}</li>`).join("");
}

function fillLiftSelects() {
  for (const sel of [$("#s-lift"), $("#h-lift")]) {
    const prev = sel.value;
    sel.innerHTML = state.lifts.map((l) => `<option>${esc(l.lift)}</option>`).join("");
    if (prev && state.lifts.some((l) => l.lift === prev)) sel.value = prev;
  }
}

// ------------------------------------------------------------ Analyse
function renderAnalysis(a) {
  $("#recs").innerHTML = recList(a.recommendations);
  $("#strengths").innerHTML = a.strengths.length ? a.strengths.map((s) => `<li>${esc(s)}</li>`).join("") : `<li class="muted">Noch zu wenig Daten.</li>`;

  $("#ratios").innerHTML = a.ratios.length ? a.ratios.map((r) => {
    const min = Math.min(r.low * 0.75, r.ratio * 0.95), max = Math.max(r.high * 1.2, r.ratio * 1.05);
    const pos = (v) => ((v - min) / (max - min)) * 100;
    const label = { ok: "im Zielbereich", niedrig: "unter Richtwert", hoch: "über Richtwert" }[r.status];
    return `<div class="ratio"><div class="head"><b>${esc(r.name)}</b>
      <span>${nf2.format(r.ratio)} <span class="muted">· Ziel ${nf2.format(r.low)}–${nf2.format(r.high)} · ${label}</span></span></div>
      <div class="bar"><div class="band" style="left:${pos(r.low)}%;width:${pos(r.high) - pos(r.low)}%"></div>
      <div class="dot ${r.status}" style="left:${pos(r.ratio)}%"></div></div>
      ${r.hint ? `<div class="small">${esc(r.hint)}</div>` : ""}</div>`;
  }).join("") : `<p class="muted">Für Verhältnisse brauchst du Daten zu mindestens zwei zusammengehörigen Übungen (z. B. Front und Back Squat).</p>`;

  $("#relative-card").classList.toggle("hidden", !a.relative.length);
  $("#relative").innerHTML = `<table class="list"><tr><th>Übung</th><th class="num">× Körpergewicht</th><th class="num">Richtwert</th><th class="num">erreicht</th></tr>` +
    a.relative.map((r) => `<tr><td>${esc(r.lift)}</td><td class="num">${nf2.format(r.relative)}</td><td class="num">${nf2.format(r.standard)}</td><td class="num">${nf1.format(r.pct_of_standard)} %</td></tr>`).join("") +
    `</table><p class="muted small">Richtwerte entsprechen einem soliden Fortgeschrittenen-Niveau und dienen nur zur Orientierung.</p>`;

  $("#trends").innerHTML = `<tr><th>Übung</th><th>Trend</th><th class="num">Änderung</th><th class="num">Einheiten</th><th>zuletzt</th></tr>` +
    a.lifts.map((l) => `<tr><td>${esc(l.lift)}</td><td class="${trendCls(l.trend)}">${esc(l.trend)}</td><td class="num">${pct(l.trend_pct)}</td><td class="num">${l.sessions}</td><td>${dateDe(l.last_date)}${l.days_since > 120 ? ' <span class="badge">lange her</span>' : ""}</td></tr>`).join("");

  $("#benchmarks").innerHTML = a.benchmarks.length
    ? `<tr><th>Workout</th><th class="num">Anzahl</th><th>erstes Mal</th><th>zuletzt</th><th>Bestwert</th><th class="num">Entwicklung</th></tr>` +
      a.benchmarks.map((b) => `<tr><td>${esc(b.title)}${b.benchmark ? ' <span class="badge">Benchmark</span>' : ""}<div class="muted small">${esc(b.categories.replaceAll(",", ", "))}</div></td>
        <td class="num">${b.count}</td><td>${esc(b.first)}<div class="muted small">${dateDe(b.first_date)}</div></td>
        <td>${esc(b.last)}<div class="muted small">${dateDe(b.last_date)}</div></td><td>${esc(b.best)}</td>
        <td class="num ${b.change_pct > 0 ? "up" : b.change_pct < 0 ? "down" : ""}">${pct(b.change_pct)}</td></tr>`).join("")
    : `<tr><td class="muted">Noch keine Workouts, die mehrfach absolviert wurden.</td></tr>`;

  const bal = a.balance;
  if (state.balanceChart) state.balanceChart.destroy();
  state.balanceChart = new Chart($("#balance-chart"), {
    type: "bar",
    data: { labels: bal.map((b) => b.category), datasets: [{ data: bal.map((b) => b.count_90d), backgroundColor: css("--accent"), borderRadius: 4 }] },
    options: {
      indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false },
        tooltip: { callbacks: { label: (c) => `${c.raw} Einheiten · zuletzt ${dateDe(bal[c.dataIndex].last_date)}` } } },
      scales: { x: { ticks: { color: css("--muted"), precision: 0 }, grid: { color: css("--border") } }, y: { ticks: { color: css("--text") }, grid: { display: false } } },
    },
  });
}

// ------------------------------------------------------------ Verlauf
async function loadHistory() {
  const lift = $("#h-lift").value;
  if (!lift) return;
  const h = await api("api/history?lift=" + encodeURIComponent(lift));
  const s = h.summary;
  $("#h-stats").innerHTML = s ? `
    <div class="stat"><div class="l">1RM aktuell (geschätzt)</div><div class="v">${w(s.current_kg)}</div></div>
    <div class="stat"><div class="l">Bestwert</div><div class="v">${w(s.all_time_kg)}</div></div>
    <div class="stat"><div class="l">Trend 90 Tage</div><div class="v ${trendCls(s.trend)}">${pct(s.trend_pct)}</div><div class="l">${esc(s.trend)}</div></div>
    <div class="stat"><div class="l">Einheiten</div><div class="v">${s.sessions}</div><div class="l">zuletzt ${dateDe(s.last_date)}</div></div>` : "";
  const pts = h.points;
  const accent = css("--accent"), good = css("--good"), muted = css("--muted"), border = css("--border");
  if (state.chart) state.chart.destroy();
  state.chart = new Chart($("#h-chart"), {
    data: {
      datasets: [
        { type: "line", label: "Geschätztes 1RM", data: pts.map((p) => ({ x: p.date, y: p.e1rm_kg })), borderColor: accent, backgroundColor: accent,
          tension: 0.25, borderWidth: 2,
          pointRadius: pts.map((p) => (p.pr_e1rm ? 7 : 2)), pointStyle: pts.map((p) => (p.pr_e1rm ? "star" : "circle")),
          pointBorderColor: pts.map((p) => (p.pr_e1rm ? good : accent)), pointBorderWidth: pts.map((p) => (p.pr_e1rm ? 2 : 1)) },
        { type: "scatter", label: "Schwerster Satz", data: pts.map((p) => ({ x: p.date, y: p.top_kg })), backgroundColor: muted, pointRadius: 3 },
      ],
    },
    options: {
      maintainAspectRatio: false, interaction: { mode: "nearest", intersect: false },
      scales: {
        x: { type: "time", time: { unit: "month", tooltipFormat: "dd.MM.yyyy", displayFormats: { month: "MM/yy" } }, ticks: { color: muted }, grid: { color: border } },
        y: { title: { display: true, text: state.unit, color: muted }, ticks: { color: muted }, grid: { color: border } },
      },
      plugins: {
        legend: { labels: { color: css("--text") } },
        tooltip: { callbacks: {
          label: (c) => {
            const p = pts[c.dataIndex];
            return c.datasetIndex === 0
              ? `1RM ≈ ${w(p.e1rm_kg)} (aus ${p.e1rm_set}${p.assumed ? ", Wdh. angenommen" : ""})${p.pr_e1rm ? " ★ PR" : ""}`
              : `Schwerster Satz: ${w(p.top_kg)} × ${p.top_reps}`;
          },
          // Chart.js zeichnet Tooltips als Text auf das Canvas – kein HTML, also nicht escapen.
          afterBody: (items) => pts[items[0].dataIndex].title,
        } },
      },
    },
  });
  $("#h-table").innerHTML = `<tr><th>Datum</th><th>Workout</th><th class="num">schwerster Satz</th><th class="num">1RM geschätzt</th><th></th></tr>` +
    pts.slice().reverse().map((p) => `<tr><td>${dateDe(p.date)}</td><td>${esc(p.title)}</td><td class="num">${w(p.top_kg)} × ${p.top_reps}</td>
      <td class="num">${w(p.e1rm_kg)}</td><td>${p.pr_e1rm ? '<span class="badge">★ PR</span>' : ""}</td></tr>`).join("");
}
$("#h-lift").addEventListener("change", loadHistory);

// ------------------------------------------------------------ Vorschlag
const modeSel = $("#s-mode");
function syncMode() {
  $("#s-pct-wrap").classList.toggle("hidden", modeSel.value !== "prozent");
  $("#s-int-wrap").classList.toggle("hidden", modeSel.value !== "kraft");
}
modeSel.addEventListener("change", syncMode);
syncMode();

$("#suggest-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target));
  const box = $("#suggest-result");
  try {
    const r = await api("api/suggest", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(r.fehler);
    const scheme = `${body.sets} × ${body.reps}`;
    box.innerHTML = `
      <h2>${esc(r.lift)} · ${esc(scheme)}</h2>
      <div class="muted">Empfohlenes Arbeitsgewicht</div>
      <div class="big">${w(r.weight_kg)}</div>
      ${r.low_kg != null ? `<div class="range">Spanne ${w(r.low_kg)} – ${w(r.high_kg)}</div>` : ""}
      <div class="muted small">${nf1.format(r.percent_of_1rm)} % vom geschätzten 1RM (${w(r.one_rm_kg)})</div>
      <h3>So wurde gerechnet</h3>
      <ul class="plain small">${r.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>
      <h3>Prozenttabelle</h3>
      <div class="pct-grid">${r.table.map((t) => `<div><span>${t.pct} %</span>${nf1.format(t.kg)}</div>`).join("")}</div>
      <p class="muted small">Vorschläge sind Schätzungen. Tagesform, Technik und Coach-Vorgaben gehen vor.</p>`;
  } catch (err) {
    box.innerHTML = `<p class="err-msg">${esc(err.message)}</p>`;
  }
});

// ------------------------------------------------------------ Import & Einstellungen
$("#import-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#import-msg");
  msg.className = ""; msg.textContent = "Importiere …";
  try {
    const r = await api("api/import", { method: "POST", body: new FormData(e.target) });
    msg.className = "ok-msg";
    msg.textContent = r.ergebnisse.map((x) => `${x.datei}: ${x.neu} neue Einträge, ${x.doppelt} schon vorhanden${x.uebersprungen ? `, ${x.uebersprungen} ohne gültiges Datum` : ""}.`).join(" ");
    e.target.reset();
    await loadAll();
  } catch (err) {
    msg.className = "err-msg"; msg.textContent = err.message;
  }
});

$("#push-sensors").addEventListener("click", async () => {
  const r = await api("api/sensors", { method: "POST" });
  $("#settings-msg").textContent = r.hinweis || `${r.gesendet} Sensoren an Home Assistant gesendet.`;
});

$("#wipe").addEventListener("click", async () => {
  if (!confirm("Wirklich alle importierten Daten löschen? Du kannst die CSV danach neu importieren.")) return;
  await api("api/data", { method: "DELETE" });
  $("#settings-msg").textContent = "Alle Daten gelöscht.";
  await loadAll();
});

// ------------------------------------------------------------ Start
(async () => {
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  await loadAll();
  let tab = "uebersicht";
  try { tab = localStorage.getItem("swc-tab") || tab; } catch (e) { /* egal */ }
  showTab(document.getElementById(tab) ? tab : "uebersicht");
})();
