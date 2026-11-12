// PNT navigation panel (#25, #90). No libraries: canvas drawing only, so the page runs offline.
"use strict";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const C = {
  ink: css("--ink"), ink2: css("--ink-2"), muted: css("--muted"), grid: css("--grid"),
  axis: css("--axis"), surface: css("--surface"), est: css("--est"), pred: css("--pred"),
  err: css("--err"), truth: css("--truth"), good: css("--good"), warning: css("--warning"),
  critical: css("--critical"),
};
// "#rrggbb" with an opacity, for canvas fills
const alpha = (hex, a) => `rgba(${[1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).join(",")},${a})`;
// Canvas sizes follow the page's root font size (style.css scales it with the window): U = 1 at
// 1920x1080, so a number below is in pixels on the projector
let U = 1;
const measure = () => { U = parseFloat(getComputedStyle(document.documentElement).fontSize) / 16; };
measure();
const font = (px, weight = 400) => `${weight} ${px * U}px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`;
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
function ftta(s) {  // predicted time to an alert, on the last 10 s trend (health.time_to_limit_s)
  if (s === undefined) return "—";
  if (s === null) return "none in 10 min";
  if (s <= 0) return "NOW";
  return s < 120 ? `${s.toFixed(0)} s` : `${(s / 60).toFixed(1)} min`;
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
  ctx.strokeStyle = C.grid; ctx.lineWidth = 1; ctx.fillStyle = C.muted; ctx.font = font(13);
  const e0 = Math.ceil((v.cx - w / 2 / v.scale) / step) * step;
  for (let e = e0; X(e) < w; e += step) {
    ctx.beginPath(); ctx.moveTo(X(e), 0); ctx.lineTo(X(e), h); ctx.stroke();
  }
  const n0 = Math.ceil((v.cn - h / 2 / v.scale) / step) * step;
  for (let n = n0; Y(n) > 0; n += step) {
    ctx.beginPath(); ctx.moveTo(0, Y(n)); ctx.lineTo(w, Y(n)); ctx.stroke();
  }
  // origin cross
  ctx.strokeStyle = C.axis; ctx.lineWidth = 1.5 * U;
  ctx.beginPath(); ctx.moveTo(X(0) - 8 * U, Y(0)); ctx.lineTo(X(0) + 8 * U, Y(0));
  ctx.moveTo(X(0), Y(0) - 8 * U); ctx.lineTo(X(0), Y(0) + 8 * U); ctx.stroke();

  // towers
  for (const em of S.emitters.values()) {
    const x = X(em.e), y = Y(em.n), on = S.heard.has(em.id);
    ctx.fillStyle = on ? C.ink : C.axis;
    ctx.strokeStyle = C.surface; ctx.lineWidth = 2 * U;
    ctx.beginPath(); ctx.moveTo(x, y - 9 * U); ctx.lineTo(x + 8 * U, y + 6 * U); ctx.lineTo(x - 8 * U, y + 6 * U); ctx.closePath();
    ctx.stroke(); ctx.fill();
    ctx.fillStyle = on ? C.ink2 : C.axis;
    ctx.fillText(em.id.replace(/^[^:]+:/, ""), x + 11 * U, y + 5 * U);
  }
  // reference station
  const ref = S.info && S.info.reference_enu;
  if (ref) {
    ctx.fillStyle = C.warning; ctx.fillRect(X(ref[0]) - 5 * U, Y(ref[1]) - 5 * U, 10 * U, 10 * U);
    ctx.fillStyle = C.ink2; ctx.fillText("reference", X(ref[0]) + 9 * U, Y(ref[1]) + 5 * U);
  }
  // tracks
  const track = (ie, in_, color, dash) => {
    ctx.strokeStyle = color; ctx.lineWidth = 2 * U; ctx.setLineDash(dash.map((d) => d * U)); ctx.beginPath();
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
  ctx.lineWidth = 4 * U; ctx.lineCap = "round";
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
    // The HPL circle is the confidence display: a disc in the colour of the bound against the limit
    const col = CONF_COLOR[f.confidence] || C.ink2;
    if (f.hpl_m != null) {
      const r = f.hpl_m * v.scale;
      ctx.fillStyle = alpha(col, 0.1); ctx.strokeStyle = col; ctx.lineWidth = 2.5 * U; ctx.setLineDash([8 * U, 6 * U]);
      ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill(); ctx.stroke(); ctx.setLineDash([]);
    }
    const [a, b, c] = f.cov;
    const m = (a + c) / 2, d = Math.sqrt(((a - c) / 2) ** 2 + b * b);
    const s1 = Math.sqrt(Math.max(m + d, 0)), s2 = Math.sqrt(Math.max(m - d, 0));
    const th = 0.5 * Math.atan2(2 * b, a - c); // from east, counter-clockwise
    ctx.fillStyle = alpha(C.est, 0.16); ctx.strokeStyle = C.est; ctx.lineWidth = 2 * U;
    ctx.beginPath();
    ctx.ellipse(x, y, Math.max(K95 * s1 * v.scale, 1), Math.max(K95 * s2 * v.scale, 1), -th, 0, 2 * Math.PI);
    ctx.fill(); ctx.stroke();
    const boxed = (text, tx, ty, ink) => {  // a label on its own patch, so it reads over tracks
      const tw = ctx.measureText(text).width;
      ctx.fillStyle = alpha(C.surface, 0.85); ctx.fillRect(tx - 4 * U, ty - 14 * U, tw + 8 * U, 19 * U);
      ctx.fillStyle = ink; ctx.fillText(text, tx, ty);
    };
    ctx.font = font(15, 600);
    if (f.truth) {
      const tx = X(f.truth[0]), ty = Y(f.truth[1]);
      // Truth outside the bound (only a simulation knows): join the two and say how far
      if (f.err_h_m != null && f.hpl_m != null && f.err_h_m > f.hpl_m) {
        ctx.strokeStyle = C.critical; ctx.lineWidth = 2 * U; ctx.setLineDash([3 * U, 4 * U]);
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(tx, ty); ctx.stroke(); ctx.setLineDash([]);
        const text = `${f.err_h_m.toFixed(0)} m from truth`;
        boxed(text, (x + tx) / 2 - ctx.measureText(text).width / 2, (y + ty) / 2 + 26 * U, C.ink);
      }
      ctx.fillStyle = C.surface; ctx.strokeStyle = C.truth; ctx.lineWidth = 2.5 * U;
      ctx.beginPath(); ctx.arc(tx, ty, 6 * U, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    }
    ctx.fillStyle = col; ctx.strokeStyle = C.surface; ctx.lineWidth = 2.5 * U;
    ctx.beginPath(); ctx.arc(x, y, 8 * U, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    // The number is on the rail; here only the word, at the circle's edge while it is on screen
    const word = CONF_WORD[f.confidence] || "";
    const r = f.hpl_m == null ? 0 : Math.min(f.hpl_m * v.scale, 0.42 * Math.min(w, h));
    if (word) boxed(f.hpl_m == null ? `no HPL · ${word}` : word, x + r * 0.72 + 12 * U, y - r * 0.72 - 10 * U, C.ink);
  }
  // scale bar + north
  const bar = niceStep(w / v.scale, 5);
  ctx.font = font(13);
  ctx.fillStyle = alpha(C.surface, 0.85); ctx.fillRect(8 * U, h - 42 * U, bar * v.scale + 16 * U, 36 * U);
  ctx.strokeStyle = C.ink2; ctx.fillStyle = C.ink2; ctx.lineWidth = 2 * U;
  ctx.beginPath(); ctx.moveTo(16 * U, h - 20 * U); ctx.lineTo(16 * U, h - 14 * U); ctx.lineTo(16 * U + bar * v.scale, h - 14 * U); ctx.lineTo(16 * U + bar * v.scale, h - 20 * U); ctx.stroke();
  ctx.fillText(fmtDist(bar), 16 * U, h - 24 * U);
  const nx = w - 24 * U;
  ctx.beginPath(); ctx.moveTo(nx, 40 * U); ctx.lineTo(nx, 16 * U); ctx.lineTo(nx - 6 * U, 25 * U); ctx.moveTo(nx, 16 * U); ctx.lineTo(nx + 6 * U, 25 * U); ctx.stroke();
  ctx.textAlign = "center"; ctx.fillText("N", nx, 56 * U);
  ctx.textAlign = "right"; ctx.fillStyle = C.muted;
  ctx.fillText(`grid ${fmtDist(step)}`, w - 12 * U, h - 12 * U);
  ctx.textAlign = "left";
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
const sig = (v) => +v.toPrecision(3);
const fmtM = (v) => (v >= 1000 ? `${sig(v / 1000)} km` : `${sig(v)} m`);
const fmtT = (s) => (s >= 1e-6 ? `${sig(s * 1e6)} µs` : `${sig(s * 1e9)} ns`);
// series: [{name, x: [...], y: [...], color, dash, label}]; a series with `label` is named at its
// last point. Log axis: decades labelled, from a floor of limit / 500 (lower values draw on the
// floor). Time axis: from 0 to a little past now, so the plot is full and the prediction leads.
function drawChart(canvas, { series, limit, fmt, limitName, shade = [], tnow, tend, emptyText = "No data yet" }) {
  const [ctx, w, h] = fit(canvas);
  ctx.fillStyle = C.surface; ctx.fillRect(0, 0, w, h);
  const L = 64 * U, R = 14 * U, T = 8 * U, B = 26 * U;
  const lo = 10 ** Math.floor(Math.log10(limit / 500));
  let top = -Infinity;
  for (const s of series) for (let i = 0; i < s.y.length; i++) if (s.y[i] != null && s.y[i] > 0 && (tnow == null || s.x[i] <= tnow)) top = Math.max(top, s.y[i]);
  const empty = !isFinite(top);
  const hi = Math.max(empty ? 0 : top * 2, limit * 5);
  let x1 = tnow == null ? Math.max(tend || 0, 60) : Math.max(30, tnow * 1.22 + 4);
  const ts = niceStep(x1, 7);
  x1 = Math.ceil(x1 / ts - 1e-9) * ts;
  const X = (t) => L + (t / x1) * (w - L - R);
  const Y = (v) => T + (1 - (Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo))) * (h - T - B);
  // over the limit: a faint red field, so "above the dashed line" reads at a glance
  ctx.fillStyle = alpha(C.critical, 0.07); ctx.fillRect(L, T, w - L - R, Y(limit) - T);
  ctx.fillStyle = alpha(C.pred, 0.1);  // where the pre-flight prediction is over the limit
  for (const [a, b] of shade) if (a < x1) ctx.fillRect(X(a), T, Math.max(1, X(Math.min(b, x1)) - X(a)), h - T - B);
  ctx.font = font(13); ctx.lineWidth = 1;
  for (let p = Math.round(Math.log10(lo)); 10 ** p <= hi; p++) {
    const v = 10 ** p;
    ctx.strokeStyle = C.axis; ctx.beginPath(); ctx.moveTo(L, Y(v)); ctx.lineTo(w - R, Y(v)); ctx.stroke();
    ctx.fillStyle = C.ink2; ctx.textAlign = "right"; ctx.fillText(fmt(v), L - 8 * U, Y(v) + 4.5 * U);
    ctx.strokeStyle = C.grid;
    for (const m of [2, 5]) if (m * v < hi) { ctx.beginPath(); ctx.moveTo(L, Y(m * v)); ctx.lineTo(w - R, Y(m * v)); ctx.stroke(); }
  }
  ctx.textAlign = "center"; ctx.fillStyle = C.ink2;
  for (let t = 0; t <= x1 + 1e-9; t += ts) ctx.fillText(`${t.toFixed(0)} s`, Math.min(X(t), w - R - 12 * U), h - 7 * U);
  ctx.textAlign = "left";
  ctx.strokeStyle = C.axis; ctx.beginPath(); ctx.moveTo(L, h - B); ctx.lineTo(w - R, h - B); ctx.moveTo(L, T); ctx.lineTo(L, h - B); ctx.stroke();
  // alert limit
  ctx.strokeStyle = C.critical; ctx.lineWidth = 2 * U; ctx.setLineDash([7 * U, 5 * U]);
  ctx.beginPath(); ctx.moveTo(L, Y(limit)); ctx.lineTo(w - R, Y(limit)); ctx.stroke(); ctx.setLineDash([]);
  ctx.font = font(13, 600); ctx.fillStyle = C.ink;
  ctx.fillText(`${limitName} ${fmt(limit)}`, L + 8 * U, Y(limit) - 7 * U);
  ctx.save(); ctx.beginPath(); ctx.rect(L, T, w - L - R, h - T - B); ctx.clip();
  const ends = [];
  for (const s of series) {
    ctx.strokeStyle = s.color; ctx.lineWidth = (s.dash ? 2 : 2.5) * U; ctx.lineJoin = "round";
    ctx.setLineDash((s.dash || []).map((d) => d * U)); ctx.beginPath();
    let pen = false, last = null;
    for (let i = 0; i < s.x.length; i++) {
      const v = s.y[i];
      if (v == null || v <= 0) { pen = false; continue; }
      const px = X(s.x[i]), py = Y(Math.min(Math.max(v, lo), hi));
      if (pen) ctx.lineTo(px, py); else { ctx.moveTo(px, py); pen = true; }
      last = [px, py];
    }
    ctx.stroke(); ctx.setLineDash([]);
    if (s.label && last) ends.push({ x: last[0], y: last[1], ty: last[1], s });
  }
  // the lines the presenter talks about are named where they end; names kept a line apart
  ends.sort((a, b) => a.ty - b.ty);
  for (let i = 1; i < ends.length; i++) ends[i].ty = Math.max(ends[i].ty, ends[i - 1].ty + 17 * U);
  ctx.font = font(14, 700);
  for (const e of ends) {
    ctx.fillStyle = e.s.color; ctx.strokeStyle = C.surface; ctx.lineWidth = 2 * U;
    ctx.beginPath(); ctx.arc(e.x, e.y, 4.5 * U, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
    const ly = Math.min(Math.max(e.ty + 5 * U, T + 14 * U), h - B - 5 * U);
    const tw = ctx.measureText(e.s.label).width;
    const lx = Math.min(e.x + 9 * U, w - R - tw - 3 * U);  // kept inside the plot
    ctx.fillStyle = alpha(C.surface, 0.8); ctx.fillRect(lx - 2 * U, ly - 13 * U, tw + 5 * U, 17 * U);
    ctx.fillStyle = C.ink; ctx.fillText(e.s.label, lx, ly);
  }
  ctx.restore();
  if (empty) {
    ctx.fillStyle = C.muted; ctx.font = font(15); ctx.textAlign = "center";
    ctx.fillText(emptyText, (L + w - R) / 2, (Y(limit) + h - B) / 2 + 5 * U);
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
      if (i >= 0 && Math.abs(s.x[i] - t) < x1 / 50 && s.y[i] != null) lines.push(`${s.name}: ${fmt(s.y[i])}`);
    }
    ctx.font = font(13);
    const lh = 17 * U, bw = Math.max(...lines.map((l) => ctx.measureText(l).width)) + 16 * U, bh = lines.length * lh + 9 * U;
    const bx = hx + bw + 12 * U > w ? hx - bw - 8 * U : hx + 8 * U;
    ctx.fillStyle = alpha(css("--page"), 0.94); ctx.strokeStyle = C.axis;
    ctx.fillRect(bx, T + 4 * U, bw, bh); ctx.strokeRect(bx, T + 4 * U, bw, bh);
    ctx.fillStyle = C.ink; lines.forEach((l, k) => ctx.fillText(l, bx + 8 * U, T + 4 * U + (k + 1) * lh));
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
  const tnow = t.length ? t[t.length - 1] : null, tend = pre ? pre.t_s[pre.t_s.length - 1] : 0;
  const hs = [];
  if (pre) hs.push({ name: "predicted", x: pre.t_s, y: pre.hpl_m, color: C.pred, dash: [6, 4] });
  if (S.info.has_truth) hs.push({ name: "error", label: "error", x: t, y: S.hist.map((p) => p[P.err]), color: C.err });
  hs.push({ name: "HPL", label: "HPL", x: t, y: S.hist.map((p) => p[P.hpl]), color: C.est });
  drawChart($("chart-hpl"), { series: hs, limit: S.info.alert_limit_m, fmt: fmtM, limitName: "alert limit", shade: pre ? pre.unavailable : [], tnow, tend });
  const ts = [];
  if (S.info.has_truth) ts.push({ name: "clock error", label: "clock error", x: t, y: S.hist.map((p) => p[P.cerr]), color: C.err });
  ts.push({ name: "time PL", label: "time PL", x: t, y: S.hist.map((p) => p[P.tpl]), color: C.est });
  drawChart($("chart-tpl"), { series: ts, limit: S.info.time_alert_limit_s, fmt: fmtT, limitName: "time alert limit", tnow, tend,
    emptyText: S.hist.length ? "Clock not estimated: no time source in this run, or the estimator has no clock" : "No data yet" });
}

// ---- the rail ----------------------------------------------------------------------------
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
    const when = `since T+${a.onset_s.toFixed(1)} s${times} · ${state}`;
    const btn = a.acked ? "" : `<button data-id="${a.id}">Ack</button>`;
    return `<li class="${a.severity}${a.active ? "" : " cleared"}"><span class="sev">${a.severity}</span><span class="one" title="${esc(a.text)}">${esc(a.text)}</span><span class="when" title="${esc(when)}">${when}</span>${btn}</li>`;
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
  // with no sky data and no cue the level already says it all: keep that case to one line
  const parts = cues.length ? [`Cue: ${cues.join("; ")}.`] : sp.level === "unknown" ? [] : ["No cue."];
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
  $("spoof").className = `spoof ${sp.level}`;
  $("spoof-word").textContent = SPOOF_WORD[sp.level] || sp.level;
  $("spoof-why").textContent = spoofWhy(sp);
}

// ---- GPS trust (health.gps_trust) and the error bound -----------------------------------
const TRUST_WORD = { trusted: "TRUSTED", checking: "CHECKING", not_trusted: "NOT TRUSTED", absent: "NO GPS" };
const fdur = (s) => (s < 120 ? `${s.toFixed(0)} s` : `${(s / 60).toFixed(1)} min`);
const cap = (t) => t[0].toUpperCase() + t.slice(1);
function renderTrust(g) {
  if (!g) return;
  $("gps-trust").className = `trust ${g.level}`;
  $("trust-word").textContent = TRUST_WORD[g.level] || g.level;
  // One line beside the word: how long GPS has been unused (the reasons are then the sentences
  // under "What is wrong now"), or else the first reason
  $("trust-since").textContent = g.unused_s != null ? `GPS not used for ${fdur(g.unused_s)}` : g.reasons.length ? cap(g.reasons[0]) : "";
}
// The bound, the limit and (where truth is known) the true error on one scale: 0 to twice the limit
function renderBound(f, h) {
  const al = h.rnp_m, hpl = f.hpl_m, max = 2 * al;
  $("bound").className = `bound ${f.confidence}`;
  $("big-hpl").textContent = fm(hpl);
  $("big-al").textContent = fm(al, 0);
  $("anp").textContent = fm(h.anp95_m);
  // zones as the map colours them (health.confidence)
  const amb = S.info ? S.info.confidence_amber_m : 0.8 * al, pc = (v) => `${(100 * Math.min(v, max)) / max}%`;
  $("zg-green").style.width = `calc(${pc(amb)} - 2px)`; $("zg-amber").style.width = `calc(${pc(al - amb)} - 2px)`;
  $("zt-amber").style.left = pc(amb); $("zt-al").style.left = pc(al);
  $("zt-amber").textContent = fm(amb, 0);
  $("zt-al").textContent = `limit ${fm(al, 0)}`;
  $("zt-max").textContent = `${fm(max, 0)} and over`;
  // the zone the HPL is in is lit; the number takes the confidence colour, which an alarm also reddens
  $("zgauge").className = `zgauge ${hpl == null ? "" : hpl >= al ? "in-red" : hpl >= amb ? "in-amber" : "in-green"}`;
  $("big-mark").style.left = hpl == null ? "100%" : pc(hpl);
  $("big-mark").title = hpl != null && hpl > max ? "HPL: off this scale" : "HPL";
  const trend = ' <span class="muted">on the last 10 s trend</span>';
  let sub;
  if (hpl == null) sub = "No bound: do not trust the position";
  else if (hpl >= al) sub = `Over the alert limit: ${(hpl / al).toFixed(1)}× the limit`;
  else if (f.confidence === "red") sub = "Within the limit, but an alarm is raised: do not trust";
  else if (h.tta_hpl_s == null) sub = `Not heading for the alert limit${trend}`;
  else sub = `Reaches the alert limit in ${fdur(h.tta_hpl_s)}${trend}`;
  $("big-tta").innerHTML = sub;
  // Error against truth: shown wherever truth is known, and loud when it is outside the bound.
  // That is the one thing the estimator cannot see for itself (a spoof it has accepted).
  const truth = S.info && S.info.has_truth, err = f.err_h_m;
  $("err-row").style.display = truth ? "" : "none";
  // a replay's /truth need not be a simulation's (#264: a real session's withheld GPS fixes)
  const truthOf = S.info && S.info.kind === "sim" ? "sim truth" : "the session's truth";
  $("err").textContent = err == null ? "—" : `${err.toFixed(1)} m (${truthOf})`;
  $("err-mark").hidden = !truth || err == null;
  if (err != null) $("err-mark").style.left = pc(err);
  const breach = err != null && hpl != null && err > hpl;
  $("err-row").classList.toggle("breach", breach);
  $("err-check").textContent = err == null || hpl == null ? "" : breach ? "OUTSIDE THE BOUND" : "inside the bound";
}

function renderSide() {
  const f = S.frame;
  if (!f) return;
  const h = f.health;
  document.body.classList.remove("stale");
  $("clock").textContent = `T+${f.t_s.toFixed(1)} s`;
  $("status").className = `status ${f.status}`;
  $("status-word").textContent = f.status.toUpperCase();
  $("headline").textContent = h.headline;
  renderBound(f, h);
  $("clk").textContent = fns(f.clock_sigma_s);
  $("tpl").textContent = fns(h.tpl_s);
  $("tta-t").textContent = h.tpl_s == null ? "clock not estimated" : ftta(h.tta_tpl_s);
  $("tta-t").title = h.tpl_s == null ? "" : h.tta_tpl_s === 0 ? "over the time alert limit" : "on the last 10 s trend";
  $("causes").innerHTML = h.causes.length
    ? h.causes.map((c) => `<li class="${c.severity}"><span class="sev">${c.severity}</span>${esc(c.text)}</li>`).join("")
    : '<li class="muted">Nothing flagged.</li>';
  renderAlerts(h.alerts, h.settled);
  renderSpoof(f.spoof);
  renderTrust(f.gps_trust);
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
  $("kind").className = `chip kind ${i.kind}`;
  $("name").textContent = i.name;
  $("estimator").textContent = `estimator ${i.estimator}`;
  // Which filter is on screen: only the `-guard` estimators refuse a GPS jump (ADR-0038), so a
  // plain one that takes a spoofed GPS back is seen for what it is
  const guarded = /(^|-)guard$/.test(i.estimator);
  $("guard").textContent = `jump guard ${guarded ? "on" : "off"}`;
  $("guard").className = `tag${guarded ? " on" : ""}`;
  $("guard").title = guarded ? "This estimator refuses a GPS position that jumps (ADR-0038)" : "This estimator has no jump guard (ADR-0038): it can take a jumped GPS position back";
  $("guard").hidden = false;
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
  $("notes").title = notes.join("\n");
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
  document.body.classList.add("stale");
  $("status").className = "status lost";
  $("status-word").textContent = "NO DATA";
  $("headline").textContent = message;
  $("gps-trust").className = "trust";
  $("trust-word").textContent = "NO DATA";
  $("trust-since").textContent = "No estimate: the values on this page are stale.";
  $("bound").className = "bound";
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
window.addEventListener("resize", () => { measure(); redraw(); });
