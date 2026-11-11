// PNT navigation panel (#25, #90). No libraries: canvas drawing only, so the page runs offline.
"use strict";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const C = {
  ink: css("--ink"), ink2: css("--ink-2"), muted: css("--muted"), grid: css("--grid"),
  axis: css("--axis"), surface: css("--surface"), est: css("--est"), pred: css("--pred"),
  err: css("--err"), truth: css("--truth"), good: css("--good"), warning: css("--warning"),
  critical: css("--critical"),
};
const STATUS_COLOR = { nominal: C.good, degraded: C.warning, unsafe: C.critical };
// Confidence of the position (health.confidence, #207): the track and the current position
const CONF_COLOR = { green: C.good, amber: C.warning, red: C.critical };
const CONF_WORD = { green: "confident", amber: "near the limit", red: "do not trust" };
const K95 = 2.4477; // 95 % radius of a 2-D Gaussian, in sigmas
const $ = (id) => document.getElementById(id);

const S = {
  info: null, emitters: new Map(), hist: [], frame: null, heard: new Set(),
  view: "follow", manual: null, done: false, failed: false,
};
// history point: [t, e, n, truth_e, truth_n, hpl, tpl_s, status, err_h, clock_err_s, confidence]
const P = { t: 0, e: 1, n: 2, te: 3, tn: 4, hpl: 5, tpl: 6, st: 7, err: 8, cerr: 9, conf: 10 };

// ---- formatting --------------------------------------------------------------------------
const fm = (v, d = 1) => (v == null ? "—" : `${v.toFixed(d)} m`);
const fns = (s) => (s == null ? "—" : s < 1e-6 ? `${(s * 1e9).toFixed(0)} ns` : `${(s * 1e6).toFixed(2)} µs`);
function ftta(s) {
  if (s === undefined) return "—";
  if (s === null) return "none within 10 min on the last 10 s trend";
  if (s <= 0) return "NOW: over the limit";
  if (s < 120) return `${s.toFixed(0)} s on the last 10 s trend`;
  return `${(s / 60).toFixed(1)} min on the last 10 s trend`;
}
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

// ---- canvas helpers ----------------------------------------------------------------------
function fit(canvas) {
  const r = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const w = Math.max(1, Math.round(r.width * dpr)), h = Math.max(1, Math.round(r.height * dpr));
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return [ctx, r.width, r.height];
}
function niceStep(span, target) {
  const raw = span / Math.max(1, target);
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  for (const m of [1, 2, 5, 10]) if (m * p >= raw) return m * p;
  return 10 * p;
}
const fmtDist = (m) => (m >= 1000 ? `${(m / 1000).toFixed(m % 1000 ? 1 : 0)} km` : `${m.toFixed(0)} m`);

// ---- map ---------------------------------------------------------------------------------
const map = $("map");
function mapView(w, h) {
  if (S.view === "manual" && S.manual) return S.manual;
  const f = S.frame;
  if (S.view === "follow" && f) {
    const half = Math.min(20000, Math.max(120, 2.5 * (f.hpl_m || 0), 3 * (f.err_h_m || 0)));
    return { cx: f.pos[0], cn: f.pos[1], scale: Math.min(w, h) / (2 * half) };
  }
  let xs = [], ys = [];
  for (const em of S.emitters.values()) { xs.push(em.e); ys.push(em.n); }
  for (const p of S.hist) { xs.push(p[P.e]); ys.push(p[P.n]); }
  const ref = S.info && S.info.reference_enu;
  if (ref) { xs.push(ref[0]); ys.push(ref[1]); }
  if (!xs.length) return { cx: 0, cn: 0, scale: 1 };
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const span = Math.max(x1 - x0, y1 - y0, 200) * 1.15;
  return { cx: (x0 + x1) / 2, cn: (y0 + y1) / 2, scale: Math.min(w, h) / span };
}
function drawMap() {
  const [ctx, w, h] = fit(map);
  const v = mapView(w, h);
  S.lastView = v;
  const X = (e) => w / 2 + (e - v.cx) * v.scale;
  const Y = (n) => h / 2 - (n - v.cn) * v.scale;
  ctx.fillStyle = C.surface; ctx.fillRect(0, 0, w, h);

  // grid
  const step = niceStep(w / v.scale, 6);
  ctx.strokeStyle = C.grid; ctx.lineWidth = 1; ctx.fillStyle = C.muted; ctx.font = "11px system-ui";
  const e0 = Math.ceil((v.cx - w / 2 / v.scale) / step) * step;
  for (let e = e0; X(e) < w; e += step) {
    ctx.beginPath(); ctx.moveTo(X(e), 0); ctx.lineTo(X(e), h); ctx.stroke();
  }
  const n0 = Math.ceil((v.cn - h / 2 / v.scale) / step) * step;
  for (let n = n0; Y(n) > 0; n += step) {
    ctx.beginPath(); ctx.moveTo(0, Y(n)); ctx.lineTo(w, Y(n)); ctx.stroke();
  }
  // origin cross
  ctx.strokeStyle = C.axis; ctx.lineWidth = 1.5;
  ctx.beginPath(); ctx.moveTo(X(0) - 8, Y(0)); ctx.lineTo(X(0) + 8, Y(0));
  ctx.moveTo(X(0), Y(0) - 8); ctx.lineTo(X(0), Y(0) + 8); ctx.stroke();

  // towers
  for (const em of S.emitters.values()) {
    const x = X(em.e), y = Y(em.n), on = S.heard.has(em.id);
    ctx.fillStyle = on ? C.ink2 : C.axis;
    ctx.strokeStyle = C.surface; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(x, y - 8); ctx.lineTo(x + 7, y + 5); ctx.lineTo(x - 7, y + 5); ctx.closePath();
    ctx.stroke(); ctx.fill();
    ctx.fillStyle = on ? C.ink2 : C.muted;
    ctx.fillText(em.id.replace(/^[^:]+:/, ""), x + 9, y + 4);
  }
  // reference station
  const ref = S.info && S.info.reference_enu;
  if (ref) {
    ctx.fillStyle = C.warning; ctx.fillRect(X(ref[0]) - 5, Y(ref[1]) - 5, 10, 10);
    ctx.fillStyle = C.ink2; ctx.fillText("reference", X(ref[0]) + 8, Y(ref[1]) + 4);
  }
  // tracks
  const track = (ie, in_, color, dash) => {
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.setLineDash(dash); ctx.beginPath();
    let pen = false;
    for (const p of S.hist) {
      if (p[ie] == null) { pen = false; continue; }
      const x = X(p[ie]), y = Y(p[in_]);
      if (pen) ctx.lineTo(x, y); else { ctx.moveTo(x, y); pen = true; }
    }
    ctx.stroke(); ctx.setLineDash([]);
  };
  track(P.te, P.tn, C.truth, [6, 5]);
  // estimate: each segment in the confidence of the epoch it ends at, one path per colour run
  ctx.lineWidth = 3; ctx.lineCap = "round";
  let prev = null, run = null;
  for (const p of S.hist) {
    const col = CONF_COLOR[p[P.conf]] || C.est;
    if (prev && col !== run) { ctx.stroke(); run = null; }
    if (!run) {
      const from = prev || p;
      ctx.strokeStyle = run = col; ctx.beginPath(); ctx.moveTo(X(from[P.e]), Y(from[P.n]));
    }
    ctx.lineTo(X(p[P.e]), Y(p[P.n]));
    prev = p;
  }
  if (run) ctx.stroke();
  ctx.lineCap = "butt";

  const f = S.frame;
  if (f) {
    const x = X(f.pos[0]), y = Y(f.pos[1]);
    const col = STATUS_COLOR[f.status] || C.ink2;
    if (f.hpl_m != null) {
      ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.setLineDash([7, 6]);
      ctx.beginPath(); ctx.arc(x, y, f.hpl_m * v.scale, 0, 2 * Math.PI); ctx.stroke(); ctx.setLineDash([]);
    }
    const [a, b, c] = f.cov;
    const m = (a + c) / 2, d = Math.sqrt(((a - c) / 2) ** 2 + b * b);
    const s1 = Math.sqrt(Math.max(m + d, 0)), s2 = Math.sqrt(Math.max(m - d, 0));
    const th = 0.5 * Math.atan2(2 * b, a - c); // from east, counter-clockwise
    ctx.fillStyle = "rgba(57,135,229,0.18)"; ctx.strokeStyle = C.est; ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.ellipse(x, y, Math.max(K95 * s1 * v.scale, 1), Math.max(K95 * s2 * v.scale, 1), -th, 0, 2 * Math.PI);
    ctx.fill(); ctx.stroke();
    if (f.truth) {
      ctx.strokeStyle = C.truth; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(X(f.truth[0]), Y(f.truth[1]), 5, 0, 2 * Math.PI); ctx.stroke();
    }
    ctx.fillStyle = CONF_COLOR[f.confidence] || C.est; ctx.strokeStyle = C.surface; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, 7, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    ctx.fillStyle = C.ink2; ctx.font = "12px system-ui";
    const word = CONF_WORD[f.confidence] || "";
    if (f.hpl_m != null) {
      ctx.fillText(`HPL ${f.hpl_m.toFixed(1)} m · ${word}`, x + f.hpl_m * v.scale * 0.72 + 4, y - f.hpl_m * v.scale * 0.72 - 4);
    } else if (word) ctx.fillText(`no HPL · ${word}`, x + 10, y - 10);
  }
  // scale bar + north
  const bar = niceStep(w / v.scale, 5);
  ctx.fillStyle = C.surface; ctx.fillRect(10, h - 38, bar * v.scale + 12, 30);
  ctx.strokeStyle = C.ink2; ctx.fillStyle = C.ink2; ctx.lineWidth = 2; ctx.font = "11px system-ui";
  ctx.beginPath(); ctx.moveTo(16, h - 18); ctx.lineTo(16 + bar * v.scale, h - 18); ctx.stroke();
  ctx.fillText(fmtDist(bar), 16, h - 24);
  ctx.beginPath(); ctx.moveTo(w - 22, 34); ctx.lineTo(w - 22, 14); ctx.lineTo(w - 27, 22); ctx.moveTo(w - 22, 14); ctx.lineTo(w - 17, 22); ctx.stroke();
  ctx.fillText("N", w - 26, 48);
  ctx.fillStyle = C.muted;
  ctx.fillText(`grid ${fmtDist(step)}`, w - 70, h - 12);
}
function setView(view) {
  S.view = view;
  $("view-follow").classList.toggle("on", view === "follow");
  $("view-area").classList.toggle("on", view === "area");
  redraw();
}
$("view-follow").onclick = () => setView("follow");
$("view-area").onclick = () => setView("area");
map.addEventListener("wheel", (ev) => {
  ev.preventDefault();
  const v = { ...(S.lastView || { cx: 0, cn: 0, scale: 1 }) };
  v.scale *= Math.exp(-ev.deltaY * 0.0015);
  S.manual = v; setView("manual");
}, { passive: false });
let drag = null;
map.addEventListener("pointerdown", (ev) => { drag = { x: ev.clientX, y: ev.clientY, v: { ...(S.lastView || { cx: 0, cn: 0, scale: 1 }) } }; });
window.addEventListener("pointerup", () => { drag = null; });
window.addEventListener("pointermove", (ev) => {
  if (!drag) return;
  const v = drag.v;
  S.manual = { cx: v.cx - (ev.clientX - drag.x) / v.scale, cn: v.cn + (ev.clientY - drag.y) / v.scale, scale: v.scale };
  setView("manual");
});

// ---- charts ------------------------------------------------------------------------------
const hover = { "chart-hpl": null, "chart-tpl": null };
function logTicks(lo, hi) {
  const out = [];
  for (let p = Math.floor(Math.log10(lo)); p <= Math.ceil(Math.log10(hi)); p++)
    for (const m of [1, 2, 5]) { const v = m * 10 ** p; if (v >= lo && v <= hi) out.push(v); }
  return out;
}
// series: [{x: [...], y: [...], color, dash}], refline: {y, label}
function drawChart(canvas, { series, limit, unit, scale = 1, shade = [], tmax, emptyText = "No data yet" }) {
  const [ctx, w, h] = fit(canvas);
  ctx.fillStyle = C.surface; ctx.fillRect(0, 0, w, h);
  const L = 54, R = 10, T = 8, B = 22;
  let lo = Infinity, hi = -Infinity;
  for (const s of series) for (const v of s.y) if (v != null && v > 0) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  const empty = !isFinite(lo);
  if (empty) { lo = limit / 10; hi = limit * 2; }
  lo = Math.max(Math.min(lo * 0.8, limit / 2), limit / 1e4); hi = Math.max(hi * 1.25, limit * 1.6);
  const x1 = Math.max(tmax || 0, 10);
  const X = (t) => L + (t / x1) * (w - L - R);
  const Y = (v) => T + (1 - (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (h - T - B);
  ctx.fillStyle = "rgba(208,59,59,0.12)";
  for (const [a, b] of shade) ctx.fillRect(X(a), T, Math.max(1, X(b) - X(a)), h - T - B);
  ctx.font = "11px system-ui"; ctx.lineWidth = 1;
  for (const v of logTicks(lo, hi)) {
    ctx.strokeStyle = C.grid; ctx.beginPath(); ctx.moveTo(L, Y(v)); ctx.lineTo(w - R, Y(v)); ctx.stroke();
    ctx.fillStyle = C.muted; ctx.textAlign = "right"; ctx.fillText(`${+(v * scale).toPrecision(3)}${unit}`, L - 6, Y(v) + 4);
  }
  const ts = niceStep(x1, 6);
  ctx.textAlign = "center";
  for (let t = 0; t <= x1 + 1e-9; t += ts) { ctx.fillStyle = C.muted; ctx.fillText(`${t.toFixed(0)} s`, X(t), h - 6); }
  ctx.textAlign = "left";
  ctx.strokeStyle = C.axis; ctx.beginPath(); ctx.moveTo(L, h - B); ctx.lineTo(w - R, h - B); ctx.stroke();
  // alert limit
  ctx.strokeStyle = C.critical; ctx.lineWidth = 2; ctx.setLineDash([6, 5]);
  ctx.beginPath(); ctx.moveTo(L, Y(limit)); ctx.lineTo(w - R, Y(limit)); ctx.stroke(); ctx.setLineDash([]);
  const alText = `alert limit ${+(limit * scale).toPrecision(3)}${unit}`;
  ctx.textAlign = "right"; ctx.fillStyle = C.surface;
  ctx.fillRect(w - R - ctx.measureText(alText).width - 8, Y(limit) - 17, ctx.measureText(alText).width + 6, 14);
  ctx.fillStyle = C.ink2; ctx.fillText(alText, w - R - 5, Y(limit) - 6); ctx.textAlign = "left";
  for (const s of series) {
    ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.setLineDash(s.dash || []); ctx.beginPath();
    let pen = false;
    for (let i = 0; i < s.x.length; i++) {
      const v = s.y[i];
      if (v == null || v <= 0) { pen = false; continue; }
      const px = X(s.x[i]), py = Y(Math.min(Math.max(v, lo), hi));
      if (pen) ctx.lineTo(px, py); else { ctx.moveTo(px, py); pen = true; }
    }
    ctx.stroke(); ctx.setLineDash([]);
  }
  if (empty) {
    ctx.fillStyle = C.muted; ctx.font = "13px system-ui"; ctx.textAlign = "center";
    ctx.fillText(emptyText, (L + w - R) / 2, (T + h - B) / 2 + 20);
    ctx.textAlign = "left";
  }
  // hover crosshair + values
  const hx = hover[canvas.id];
  if (hx != null && hx >= L && hx <= w - R) {
    const t = ((hx - L) / (w - L - R)) * x1;
    ctx.strokeStyle = C.muted; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(hx, T); ctx.lineTo(hx, h - B); ctx.stroke();
    const lines = [`t = ${t.toFixed(1)} s`];
    for (const s of series) {
      const i = nearest(s.x, t);
      if (i >= 0 && Math.abs(s.x[i] - t) < x1 / 50 && s.y[i] != null) lines.push(`${s.name}: ${+(s.y[i] * scale).toPrecision(3)}${unit}`);
    }
    const bw = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 14, bh = lines.length * 15 + 8;
    const bx = hx + bw + 12 > w ? hx - bw - 8 : hx + 8;
    ctx.fillStyle = "rgba(13,13,13,0.92)"; ctx.strokeStyle = C.axis;
    ctx.fillRect(bx, T + 4, bw, bh); ctx.strokeRect(bx, T + 4, bw, bh);
    ctx.fillStyle = C.ink; lines.forEach((l, k) => ctx.fillText(l, bx + 7, T + 19 + k * 15));
  }
}
function nearest(xs, t) {
  let lo = 0, hi = xs.length - 1;
  if (hi < 0) return -1;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (xs[mid] < t) lo = mid + 1; else hi = mid; }
  return lo > 0 && Math.abs(xs[lo - 1] - t) < Math.abs(xs[lo] - t) ? lo - 1 : lo;
}
for (const id of Object.keys(hover)) {
  const c = $(id);
  c.addEventListener("mousemove", (ev) => { hover[id] = ev.clientX - c.getBoundingClientRect().left; redraw(); });
  c.addEventListener("mouseleave", () => { hover[id] = null; redraw(); });
}
function drawCharts() {
  if (!S.info) return;
  const t = S.hist.map((p) => p[P.t]);
  const pre = S.info.preflight;
  const tmax = Math.max(t.length ? t[t.length - 1] : 0, pre ? pre.t_s[pre.t_s.length - 1] : 0);
  const hs = [];
  if (pre) hs.push({ name: "predicted", x: pre.t_s, y: pre.hpl_m, color: C.pred, dash: [6, 4] });
  if (S.info.has_truth) hs.push({ name: "error", x: t, y: S.hist.map((p) => p[P.err]), color: C.err });
  hs.push({ name: "HPL", x: t, y: S.hist.map((p) => p[P.hpl]), color: C.est });
  drawChart($("chart-hpl"), { series: hs, limit: S.info.alert_limit_m, unit: " m", shade: pre ? pre.unavailable : [], tmax });
  const ts = [];
  if (S.info.has_truth) ts.push({ name: "clock error", x: t, y: S.hist.map((p) => p[P.cerr]), color: C.err });
  ts.push({ name: "time PL", x: t, y: S.hist.map((p) => p[P.tpl]), color: C.est });
  drawChart($("chart-tpl"), { series: ts, limit: S.info.time_alert_limit_s, unit: " ns", scale: 1e9, tmax,
    emptyText: S.hist.length ? "Clock not estimated: no time source in this run, or the estimator has no clock" : "No data yet" });
}

// ---- side panel --------------------------------------------------------------------------
function chips(obj, low) {
  const keys = Object.keys(obj || {});
  if (!keys.length) return '<span class="muted">none</span>';
  return keys.map((k) => `<span class="chip${low ? " low" : ""}">${esc(k)} ${obj[k].toFixed(2)}</span>`).join("");
}
function alertsHtml(alerts, settled) {
  if (!alerts.length) {
    return settled ? '<li class="muted">No alerts.</li>'
      : '<li class="muted">Start-up: alerts latch once the filter first reports nominal (or after 30 s).</li>';
  }
  return alerts.map((a) => {
    const state = a.active ? (a.acked ? "active, acknowledged" : "active") : `cleared at T+${a.last_s.toFixed(1)} s`;
    const times = a.count > 1 ? ` (${a.count} times; first T+${a.since_s.toFixed(1)} s)` : "";
    const btn = a.acked ? "" : `<button data-id="${a.id}">Ack</button>`;
    return `<li class="${a.severity}${a.active ? "" : " cleared"}"><div class="txt"><span class="sev">${a.severity}</span>${esc(a.text)}<span class="when">since T+${a.onset_s.toFixed(1)} s${times} · ${state}</span></div>${btn}</li>`;
  }).join("");
}
// Rebuilt only when what it shows has changed: a button replaced between press and release, as a
// rebuild on every frame would do, never gets its click.
let shownAlerts = null;
function renderAlerts(alerts, settled = true) {
  const html = alertsHtml(alerts, settled);
  if (html === shownAlerts) return;
  shownAlerts = html;
  const ul = $("alerts");
  ul.innerHTML = html;
  ul.querySelectorAll("button").forEach((b) => (b.onclick = () => ack({ id: +b.dataset.id })));
}
function ack(body) {
  // The reply carries the alerts too: the stream is closed once a replay has finished
  fetch("/api/ack", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
    .then((r) => r.json()).then((d) => renderAlerts(d.alerts));
}
$("ack-all").onclick = () => ack({});

// ---- spoof decision (ADR-0041) -----------------------------------------------------------
const SPOOF_WORD = { unknown: "UNKNOWN", not_spoofed: "NOT SPOOFED", suspect: "SUSPECT", spoofed: "SPOOFED" };
const CUE_WORDS = {
  sky_below_horizon: "a satellite is received that is below the horizon here",
  power_flat: "every satellite arrives at the same power, unrelated to elevation",
  jump_latched: "GPS position jumped (jump guard)",
  towers_refute: "the towers contradict the GPS position",
};
function spoofWhy(sp) {
  const cues = sp.cues.map((c) => {
    const held = c.endsWith(" (held)");
    const k = held ? c.slice(0, -7) : c;
    return `${CUE_WORDS[k] || k}${held ? " (held)" : ""}`;
  });
  const parts = [cues.length ? `Cue: ${cues.join("; ")}.` : "No cue."];
  const s = sp.sky;
  if (s) {
    const pw = s.spread_db == null ? "" : `, C/N0 spread ${s.spread_db.toFixed(1)} dB, correlation with elevation ${s.corr.toFixed(2)}`;
    parts.push(`${s.n_judged} GPS satellites judged, ${s.n_below} below the horizon${pw}.`);
  }
  parts.push(...sp.notes.map((n) => `${n[0].toUpperCase()}${n.slice(1)}.`));
  parts.push(`Score ${sp.score.toFixed(2)}.`);
  return parts.join(" ");
}

function renderSpoof(sp) {
  if (!sp) return;
  $("spoof").className = `card spoof ${sp.level}`;
  $("spoof-word").textContent = SPOOF_WORD[sp.level] || sp.level;
  $("spoof-why").textContent = spoofWhy(sp);
}

function renderSide() {
  const f = S.frame;
  if (!f) return;
  const h = f.health;
  $("clock").textContent = `T+${f.t_s.toFixed(1)} s`;
  const st = $("status");
  st.className = `card status ${f.status}`;
  $("status-word").textContent = f.status.toUpperCase();
  $("headline").textContent = h.headline;
  $("rnp").textContent = fm(h.rnp_m, 0);
  $("anp").textContent = fm(h.anp95_m);
  $("hpl").textContent = fm(f.hpl_m);
  const frac = (v, lim) => Math.min(100, (100 * v) / (1.5 * lim));
  const bar = $("hpl-bar");
  bar.style.width = `${f.hpl_m == null ? 0 : frac(f.hpl_m, h.rnp_m)}%`;
  bar.style.background = f.hpl_m > h.rnp_m ? C.critical : f.hpl_m > 0.8 * h.rnp_m ? C.warning : C.good;
  $("tta-h").textContent = ftta(h.tta_hpl_s);
  $("err-row").style.display = S.info && S.info.has_truth ? "" : "none";
  // a replay's /truth need not be a simulation's (#264: a real session's withheld GPS fixes)
  const truthOf = S.info && S.info.kind === "sim" ? "sim truth" : "the session's truth";
  $("err").textContent = f.err_h_m == null ? "—" : `${f.err_h_m.toFixed(1)} m (${truthOf})`;
  $("clk").textContent = fns(f.clock_sigma_s);
  $("tpl").textContent = fns(h.tpl_s);
  $("tal").textContent = fns(h.time_alert_limit_s);
  const tb = $("tpl-bar");
  tb.style.width = `${h.tpl_s == null ? 0 : frac(h.tpl_s, h.time_alert_limit_s)}%`;
  tb.style.background = h.tpl_s > h.time_alert_limit_s ? C.critical : C.good;
  $("tta-t").textContent = h.tpl_s == null ? "clock not estimated" : ftta(h.tta_tpl_s);
  $("causes").innerHTML = h.causes.length
    ? h.causes.map((c) => `<li class="${c.severity}"><span class="sev">${c.severity}</span>${esc(c.text)}</li>`).join("")
    : '<li class="muted">Nothing flagged.</li>';
  renderAlerts(h.alerts, h.settled);
  renderSpoof(f.spoof);
  $("trusted").innerHTML = chips(h.trusted, false);
  $("lowtrust").innerHTML = chips(h.low_trust, true);
  const towers = [...S.emitters.keys()];
  $("heard").textContent = towers.length ? `${towers.filter((e) => S.heard.has(e)).length} of ${towers.length}` : "—";
}

// ---- stream ------------------------------------------------------------------------------
let pending = false;
function redraw() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => { pending = false; drawMap(); drawCharts(); });
}
function point(f) {
  const tr = f.truth || [null, null];
  const cerr = f.truth_clock_s != null && f.clock_sigma_s != null ? Math.abs(f.clock_bias_s - f.truth_clock_s) : null;
  return [f.t_s, f.pos[0], f.pos[1], tr[0], tr[1], f.hpl_m, f.health.tpl_s, f.status, f.err_h_m, cerr, f.confidence];
}
function addEmitters(list) { for (const em of list) S.emitters.set(em.id, em); }

const es = new EventSource("/api/stream");
const conn = $("conn");
es.addEventListener("info", (ev) => {
  const i = (S.info = JSON.parse(ev.data));
  $("kind").textContent = i.kind.toUpperCase();
  $("name").textContent = i.name;
  $("estimator").textContent = `estimator ${i.estimator}`;
  $("banner").textContent = i.banner || "";
  $("banner").hidden = !i.banner;
  $("speed").textContent = i.kind === "live" ? "" : i.speed == null ? "as fast as possible" : `×${i.speed}`;
  $("lg-truth").style.display = i.has_truth ? "" : "none";
  $("lg-err").style.display = i.has_truth ? "" : "none";
  $("lg-terr").style.display = i.has_truth ? "" : "none";
  $("lg-ref").style.display = i.reference_enu ? "" : "none";
  $("lg-pred").style.display = i.preflight ? "" : "none";
  const al = i.alert_limit_m, amb = i.confidence_amber_m;
  $("lg-conf-green").textContent = `HPL < ${amb.toFixed(0)} m`;
  $("lg-conf-amber").textContent = `${amb.toFixed(0)} to ${al.toFixed(0)} m`;
  $("lg-conf-red").textContent = `≥ ${al.toFixed(0)} m, no HPL, or spoof / integrity alarm`;
  const notes = [...(i.notes || [])];
  if (i.preflight && i.preflight.dropped_faults.length)
    notes.push(`Pre-flight prediction leaves out unplanned faults: ${i.preflight.dropped_faults.join(", ")}`);
  notes.push("Alert limits are TBC placeholders (REQ-01/02/03). ANP: 95 % radius from the estimate's covariance.");
  $("notes").textContent = notes.join("  ·  ");
  S.emitters.clear(); S.hist = []; S.frame = null; S.done = false; S.failed = false;
  conn.className = "dot live";
});
es.addEventListener("emitters", (ev) => addEmitters(JSON.parse(ev.data)));
es.addEventListener("history", (ev) => { S.hist = JSON.parse(ev.data); redraw(); });
es.addEventListener("frame", (ev) => {
  const f = JSON.parse(ev.data);
  addEmitters(f.new_emitters);
  if (!S.hist.length || S.hist[S.hist.length - 1][P.t] < f.t_s) S.hist.push(point(f));
  S.frame = f; S.heard = new Set(f.heard);
  if (!S.failed) conn.className = "dot live";
  renderSide(); redraw();
});
es.addEventListener("alerts", (ev) => renderAlerts(JSON.parse(ev.data)));
es.addEventListener("end", () => {
  S.done = true; conn.className = "dot done"; conn.title = "finished";
  es.close(); // nothing more will come; otherwise the browser would reconnect and replay the history
  $("speed").textContent += "  finished";
});
// The numbers have stopped: leave no green NOMINAL on screen. The next `info` and `frame` restore it.
function feedLost(message) {
  conn.className = "dot err";
  $("status").className = "card status lost";
  $("status-word").textContent = "NO DATA";
  $("headline").textContent = message;
}
es.addEventListener("error", (ev) => {
  if (ev.data) { S.failed = true; feedLost(`Feed error: ${JSON.parse(ev.data).message}. The values on this page are stale.`); }
  else if (!S.done && !S.failed) feedLost("Connection to the server lost: the values on this page are stale. Retrying.");
  else if (!S.done) conn.className = "dot err";
});
// Live only: the estimator runs on what arrives, so a stopped stream stops the frames and would
// leave the last NOMINAL on screen. The server says how long it has been quiet (its own clock, so
// a page opened late sees the age too); the next frame restores the panel. TBC: 3 s, three missed
// readings of a 1 Hz tower.
const STALE_S = 3;
es.addEventListener("quiet", (ev) => {
  const q = JSON.parse(ev.data).s;
  if (!S.info || S.info.kind !== "live" || S.done || S.failed || q == null || q <= STALE_S) return;
  feedLost(`No estimate for ${q.toFixed(0)} s: the payload's stream has stopped. The values on this page are stale.`);
});
window.addEventListener("resize", redraw);
