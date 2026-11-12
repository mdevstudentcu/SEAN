---
theme: default
title: A navigation layer that knows when it is wrong
info: Hack the Horizons 2026, Challenge 2 (resilient navigation in GPS-denied environments). Every number cites its source; systems/results.md lists them all.
colorSchema: dark
aspectRatio: 16/9
canvasWidth: 1280
fonts:
  provider: none
  sans: Red Hat Text
  mono: Red Hat Mono
transition: fade
mdc: true
class: topo-cover
layout: default
---

<div class="h-full flex flex-col justify-center" style="max-width: 44rem">
  <div class="kicker">Hack the Horizons · Challenge 2 · resilient navigation in GPS-denied environments</div>
  <h1 style="font-size: 3rem">A navigation layer that knows when it is wrong</h1>
  <p class="lede" style="margin-top: 1.2rem">A receive-only GPS trust monitor. It keeps position and time from the cell towers already in the air, and tells the operator, with a number, how far to trust them.</p>
  <p class="muted small" style="margin-top: 2.2rem">Shrikar Vempati · M. Elshoubky</p>
</div>
<div style="position: absolute; right: 4.2rem; top: 50%; transform: translateY(-50%); width: 27rem">
  <Media file="drone-payload.jpg" label="The drone with the payload mounted" hint="Outdoors, three-quarter view, antennas visible. Landscape." ratio="4 / 3" />
</div>

<!--
(0:00, 10 s) The real danger is not losing GPS. It is a display that says "trust me" when it should not. We built a navigation layer that knows when it is wrong, and says so with a number.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Problem understanding & requirements</div>
<div class="kicker">The problem</div>

# GPS fails quietly

<p class="lede">Jammed or spoofed, the aircraft keeps showing a confident position. The operator needs to know <strong>when not to trust it</strong>, and what is left.</p>

<div class="cols cols-3" style="margin-top: 1.2rem">
<div class="card">

### Users
- **Drone operators** beyond line of sight
- **Crews** on approach to an airport
- **Timing users** that discipline a clock to GPS

</div>
<div class="card">

### Constraints
- **Receive-only**: never transmit or interfere
- **Signals already in the air**: cell towers first
- **Low cost**: radios and antennas CAD 170
- One week, two people

</div>
<div class="card">

### Assumptions we state
- GPS is good at start-up, long enough to learn the towers (ASM-01)
- Tower sites come from the public ISED registry (ASM-02)
- Attacks are software-injected only (ASM-03)
- Horizontal first; height from the barometer (ASM-05)

</div>
</div>

<div class="foot">systems/requirements.md · systems/assumptions.md · systems/use-cases.md</div>

<!--
(0:10, 20 s) Three users: drones beyond line of sight, crews on approach, and anyone who takes time from GPS. We only listen, we use signals already in the air, and it is cheap. And we state our assumptions: GPS is good at start-up, tower sites come from the public registry, attacks are injected in software.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Problem understanding · Documentation</div>
<div class="ask"><span>Mentor ask</span> requirements tied to the use cases (D1)</div>
<div class="kicker">Use case → requirement → measure</div>

# Every requirement traces to a use case

<table class="score" style="margin-top: 0.8rem">
<thead><tr><th>Use case</th><th>Requirement</th><th>Success measure (ours, TBC)</th></tr></thead>
<tbody>
<tr><td rowspan="2"><strong>UC-01</strong> drone on an urban corridor</td><td>REQ-01 keep position after GPS loss</td><td class="r">95 % ≤ 25 m for 300 s · mentors: 50 m for 2 min</td></tr>
<tr><td>REQ-02 a protection level on every estimate</td><td class="r">bound covers the error ≥ 99.9 % · alert limit 50 m</td></tr>
<tr><td><strong>UC-02</strong> crew on approach</td><td>REQ-01, REQ-02 at approach scale</td><td class="r">within RNP 0.3 (556 m) · alert limit 556 m</td></tr>
<tr><td><strong>UC-03</strong> timing user</td><td>REQ-03 keep time, with its uncertainty</td><td class="r">≤ 1.5 µs after 10 min · 1σ covers ≥ 68 %</td></tr>
<tr><td rowspan="4"><strong>All</strong></td><td>REQ-04 catch GPS that lies</td><td class="r">20 m jump in 2 s · 2 m/s drag in 30 s · 50 ns/s in 60 s · ≤ 1 false alarm/h</td></tr>
<tr><td>REQ-05 live operator display</td><td class="r">position, bound, time bound, per-source status, ≥ 1 Hz</td></tr>
<tr><td>REQ-06 communication signals carry the solution</td><td class="r">removing them hurts more than removing any other aid</td></tr>
<tr><td>REQ-07 receive-only</td><td class="r">no transmit path in hardware or code</td></tr>
</tbody>
</table>

<div class="foot">systems/requirements.md · systems/plan.md (targets T1–T5) · ADR-0034 (targets after the mentors' answers)</div>

<!--
(0:30, 15 s) Each use case maps to requirements with a number we can test against. These are our own targets, marked to be confirmed; where the mentors gave a figure, 50 metres for two minutes, we keep it as the fallback.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Technical approach · Prototype quality</div>
<div class="kicker">Architecture (D1)</div>

# One code path from simulation to live flight

<div class="arch" style="margin-top: 0.8rem">
  <div class="node payload">
    <div class="nt">Payload</div>
    <div class="ns">Raspberry Pi 4B · never transmits</div>
    <ul><li>LTE radio</li><li>GPS + timing pulse</li><li>IMU + barometer</li><li>ADS-B receiver</li></ul>
  </div>
  <div class="arrow"><span>authenticated link<br>or recording</span></div>
  <div class="node"><div class="nt">Front ends</div><div class="ns">cell sync timing → tower ranges</div></div>
  <div class="arrow"></div>
  <div class="node"><div class="nt">Fusion filter</div><div class="ns">position, velocity, every tower's clock, our own clock</div></div>
  <div class="arrow"></div>
  <div class="node"><div class="nt">Integrity</div><div class="ns">position bound · time bound · jump guard · sky check</div></div>
  <div class="arrow"></div>
  <div class="node panel"><div class="nt">Operator panel</div><div class="ns"><span class="ok">green</span> · <span class="warn">amber</span> · <span class="bad">red</span>, with the number</div></div>
</div>
<div class="arch-in"><span class="tag">Inputs</span> public tower registry (ISED) · simulation, replay and live share one interface</div>

<div class="cols" style="grid-template-columns: 1fr 1fr 1.15fr; margin-top: 0.9rem; gap: 1.2rem; align-items: start">
<Media file="payload.jpg" label="The payload, lid off" hint="Pi, LTE radio, GPS with its timing pulse, IMU, barometer, labelled if you can." ratio="16 / 9" />
<Media file="panel-live.jpg" label="The panel on the ground laptop" hint="A real session on screen, location hidden." ratio="16 / 9" />
<div class="flex flex-col gap-3 small">
<div><span class="tag">Built</span> real payload, real captures, live link, panel</div>
<div><span class="tag">Decisions</span> 57 recorded, each with its trade-off</div>
<div><span class="tag">Interfaces</span> one measurement record; GPS-nanosecond time</div>
</div>
</div>

<div class="foot">systems/architecture.md (D1) · systems/adr/ · systems/icd/ · hardware/bom.md</div>

<!--
(0:45, 20 s) The payload is a Raspberry Pi with a low-cost LTE radio, GPS with a timing pulse, an IMU and a barometer. It only listens. A laptop turns tower sync signals into ranges, fuses them in a filter that tracks every tower's clock and our own, and the integrity layer turns that into a bound and a colour. Simulation, recordings and live data run the same code.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Innovation & originality</div>
<div class="ask"><span>Challenge</span> communication signals first</div>
<div class="kicker">What is new</div>

# Every source can lie. The towers too.

<div class="cols cols-3" style="margin-top: 1.2rem">
<div class="card">

### Towers are checked, not trusted
A tower clock jump, a wrong registry entry or a fake tower is a fault the filter tests for, as it tests GPS.

</div>
<div class="card">

### Tower time comes from GPS
So towers may **contradict** GPS time, never **confirm** it. A spoofer that moves GPS can move the towers' clocks too.

</div>
<div class="card">

### The bound stays honest
The slow part of each tower's error is its own filter state, so the confidence widens when the towers drift instead of shrinking.

</div>
</div>

<div class="cols cols-2" style="margin-top: 1.2rem">
<div class="card"><h3>Prior work</h3><p class="small">The Kassas group fuses cell towers for <strong>accuracy</strong>, with per-tower clocks.</p></div>
<div class="card"><h3>Ours</h3><p class="small">We build the <strong>integrity</strong> on them: when to believe the answer, and a refusal when GPS lies.</p></div>
</div>

<div class="foot">ADR-0021 (pitch) · ADR-0046 (honest bound) · systems/research.md (novelty check, papers re-read 2026-11-09)</div>

<!--
(1:05, 20 s) Others use cell towers for accuracy. Our angle is integrity. Towers fail too, and we test for it. Tower time comes from GPS, so it can contradict GPS time but never confirm it. And we keep the slow part of each tower's error as a state, so the bound grows when it should.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Presentation & demonstration</div>
<div class="ask"><span>D2</span> real-time monitoring</div>
<div class="kicker">Live demo · simulated drone, real tower sites</div>

# Watch the confidence change

<div class="cols cols-3" style="margin-top: 1.1rem; gap: 1.2rem">
<figure class="shot">
  <Clip src="/proof/clips/outage-rail.mp4" poster="/proof/outage-3-rail.jpg" label="Panel after GPS loss: UNSAFE, bound 895 m, error 325 m inside it" />
  <figcaption><span class="n">1</span><span><strong>GPS lost.</strong> Red within 3 s. Forty seconds on: 325 m off, and the bound (895 m) says so.</span></figcaption>
</figure>
<figure class="shot">
  <Clip src="/proof/clips/jump-rail.mp4" poster="/proof/jump-3-rail.jpg" label="Spoofed jump without the guard: NOMINAL, bound 7 m, error 298 m outside it" />
  <figcaption><span class="n">2</span><span><strong>Spoofed 300 m, no guard.</strong> Caught at the first fake fix, then taken back: <span class="ok">green</span> and 298 m wrong.</span></figcaption>
</figure>
<figure class="shot">
  <Clip src="/proof/clips/guard-rail.mp4" poster="/proof/guard-1-rail.jpg" label="Same attack with the guard: UNSAFE, fake GPS refused, error inside the bound" />
  <figcaption><span class="n">3</span><span><strong>Same attack, guard on.</strong> Fake GPS refused, stays <span class="bad">red</span>; real GPS back within metres.</span></figcaption>
</figure>
</div>

<div class="foot">The panel's status rail, recorded live and looped (main de28b38) · deploy/demo/RUNBOOK.md</div>

<!--
(1:25, 50 s) LIVE: deploy/demo/demo.sh jump (about 50 s: jump without the guard, Enter at T+188, then with the guard, Enter at T+212). If short of time or anything fails, talk over these clips.
1. "GPS lost: within three seconds, red. Forty seconds on we are 325 m off, and the bound says so."
2. "A spoofer jumps GPS 300 m. Caught at the first fake fix. Half a minute later the plain filter takes it back: green, and 300 m wrong."
3. "Same attack with our jump guard: it stays red, the bound grows faster than the error, and when the spoofer stops, real GPS comes straight back."
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Technical approach & rigor</div>
<div class="ask"><span>Mentor ask</span> several ways to show confidence</div>
<div class="kicker">The real panel, 40 s after GPS loss</div>

# Ten readouts, one answer: do not navigate on this

<div class="cols" style="grid-template-columns: 1.55fr 1fr; gap: 1.4rem; margin-top: 0.7rem; align-items: start">
<div class="annot">
  <img src="/proof/panel-unsafe.jpg" alt="The operator panel 40 s after GPS loss, UNSAFE">
  <span class="pin" style="left: 96%; top: 8%">1</span>
  <span class="pin" style="left: 67.5%; top: 40%">2</span>
  <span class="pin" style="left: 95%; top: 33%">3</span>
  <span class="pin" style="left: 67.5%; top: 26%">4</span>
  <span class="pin" style="left: 67.5%; top: 30.5%">5</span>
  <span class="pin" style="left: 67.5%; top: 94%">6</span>
  <span class="pin" style="left: 52%; top: 93%">7</span>
  <span class="pin" style="left: 42%; top: 28%">8</span>
  <span class="pin" style="left: 22%; top: 79%">9</span>
  <span class="pin" style="left: 67.5%; top: 66%">10</span>
</div>
<ol class="legend">
<li><strong>State</strong> by colour and words: nominal, degraded, unsafe</li>
<li><strong>Protection level</strong> against the alert limit: 895 m, 17.9× the limit</li>
<li><strong>ANP against RNP</strong>: the 95 % radius, in a crew's terms</li>
<li><strong>GPS trust</strong>: trusted, checking, not trusted, no GPS</li>
<li><strong>Spoof check</strong> from sky, power and cues: unknown, suspect, spoofed</li>
<li><strong>Per-source trust</strong>: what is in use, with its weight</li>
<li><strong>Time bound</strong> and time left to its alert limit</li>
<li><strong>Map</strong>: the bound as a circle; the track coloured by confidence</li>
<li><strong>Bound over time</strong>, with the pre-flight prediction</li>
<li><strong>Alerts</strong> latched with the time they started, until acknowledged</li>
</ol>
</div>

<div class="foot">HPL = 5.68 × σ<sub>max</sub> (two-dimensional, 10⁻⁷ per epoch, TBC; ADR-0056) · time bound = 5.33 × σ<sub>clock</sub> · ADR-0027 (panel) · ADR-0041 (spoof check)</div>

<!--
(2:15, 20 s) The mentors asked us to consider several ways of showing confidence. The panel gives ten, and they agree: a state colour, the protection level against the limit, the aviation 95 % radius, a GPS trust word, a spoof check, per-source trust, a time bound, the map circle, the bound over time with its prediction, and latched alerts.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Testing, evidence & results</div>
<div class="kicker">Is the confidence true? Sim truth and real recordings</div>

# A bound that does not lie

<div class="cols" style="grid-template-columns: 0.9fr 1.25fr; margin-top: 0.8rem; gap: 2rem">
<div>

$$\mathrm{HPL} = k_H\,\sigma_{\max},\quad k_H=\sqrt{2\ln 10^{7}} = 5.68$$
<p class="muted small">A horizontal error is two-dimensional, so a 10<sup>−7</sup> risk per epoch (TBC) needs 5.68, not the one-dimensional 5.33. We caught that in our own code and fixed it (ADR-0056).</p>

<h3 style="margin-top: 1rem">Real recordings, GPS cut in software</h3>
<div class="flex flex-col gap-2 small" style="margin-top: 0.4rem">
<div>Default filter: bound below the true error</div>
<div class="bar"><span style="width: 34%; background: var(--bad)"></span></div>
<div class="num">1,025 of 3,005 checks (34 %)</div>
<div style="margin-top: 0.3rem">Honest-bound filter</div>
<div class="bar"><span style="width: 0.6%; background: var(--ok)"></span></div>
<div class="num">0 of 3,005</div>
</div>

</div>
<figure class="fig">
  <img src="/proof/honest-bound-top.png" alt="Error against protection level, before and after the fix: 41.6 % of epochs above the bound before, 0.4 % after">
  <figcaption>Simulated drone, GPS lost for 600 s, 200 runs. Every dot above the diagonal is a moment the error escaped the bound: 41.6 % before, 0.4 % after, 0 hazardous.</figcaption>
</figure>
</div>

<div class="foot">ADR-0046 · ADR-0056 · analysis/results/honest-bound (1385a48) · analysis/results/real-replay-256</div>

<!--
(2:35, 20 s) Is that number true? Every dot above the line is a moment the error escaped the bound. Before our fix: 42 percent. After: under half a percent, and none hazardous. On real recordings the default bound was too small a third of the time; ours, never.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Technical approach & rigor</div>
<div class="ask"><span>Mentor ask</span> explain the calculation · handover timing</div>
<div class="kicker">Accuracy budget against Monte Carlo</div>

# Why accuracy misses, and how long GPS must be good first

<div class="cols cols-2" style="margin-top: 0.7rem; gap: 1.4rem">
<figure class="fig">
  <img src="/proof/budget-vs-mc.png" alt="Accuracy budget against Monte Carlo on the clean and realistic routes">
  <figcaption><strong>Budget vs Monte Carlo.</strong> Each error term (tower clock, multipath, told tower position, our clock, noise) grown from the moment GPS is lost, summed, and checked against 20 runs. Clean route: inside the 50 m fallback. Realistic towers: hundreds of metres; multipath alone is 215 m at 2 min.</figcaption>
</figure>
<figure class="fig">
  <img src="/proof/handover-clean.png" alt="95 % error against how long GPS was good before loss">
  <figcaption><strong>Handover timing.</strong> 95 % error against how long GPS was good before loss. Clean route. The filter that learns tower clock drift (orange) needs ≥ 150 s of good GPS to stay under 50 m (read off its budget curve); the others (blue, green) do not depend on it. On realistic towers no wait is enough (systems/accuracy-budget.md).</figcaption>
</figure>
</div>

<div class="foot">systems/accuracy-budget.md · analysis/accuracy_budget.py (f3fc928 / f736bda, seeds 0–19) · ADR-0034</div>

<!--
(2:55, 20 s) The mentors asked for the calculation. Each error term is grown from the moment GPS is lost and checked against the Monte Carlo: a clean route stays inside the 50 m fallback; realistic towers do not, multipath alone is 215 m. And handover timing: the filter that learns tower drift needs at least two and a half minutes of good GPS first.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Testing, evidence & results</div>
<div class="ask"><span>Mentor ask</span> how the sim aligns to reality</div>
<div class="kicker">Simulation against reality</div>

# We measured the radio, and it changed the filter

<div class="cols" style="grid-template-columns: 1.05fr 1fr; gap: 1.4rem; margin-top: 0.7rem">
<div>
<table class="score">
<thead><tr><th>Model</th><th>Set from</th><th>Status</th></tr></thead>
<tbody>
<tr><td>IMU noise and bias drift</td><td class="small">overnight bench capture</td><td><span class="pill ok">measured</span></td></tr>
<tr><td>LTE range noise</td><td class="small">15 real captures: 0.73 m on strong cells</td><td><span class="pill ok">measured</span></td></tr>
<tr><td>LTE slow error</td><td class="small">2.4–17 m, median 8.1 m, never reported by the radio</td><td><span class="pill ok">measured</span></td></tr>
<tr><td>GPS fix and signal power</td><td class="small">static sessions with the GPS HAT</td><td><span class="pill warn">partly</span></td></tr>
<tr><td>Tower clocks, multipath, barometer</td><td class="small">literature</td><td><span class="pill bad">placeholder</span></td></tr>
<tr><td>Spoofing, jamming</td><td class="small">injected in software, also into real recordings</td><td><span class="pill bad">placeholder</span></td></tr>
</tbody>
</table>
<p class="small" style="margin-top: 0.7rem">Same comparison tool on both: the sim's LTE error was <strong>white, 49 m</strong>; the real one is <strong>smooth, 21 m</strong>. That mismatch is why the honest-bound filter carries the slow error as a state.</p>
</div>
<figure class="fig">
  <img src="/proof/white-vs-snr.png" alt="LTE range noise against SNR over 15 real captures">
  <figcaption>Real: range jitter against signal strength, 15 static captures. Our radio reports a σ 1.3–2× the true white noise, and nothing of the slow error.</figcaption>
</figure>
</div>

<div class="foot">systems/verification.md (Sim validity) · ADR-0015 · ADR-0036 · analysis/results/lte-measured-noise (8892fca) · #199 (pnt compare)</div>

<!--
(3:15, 15 s) How the simulation lines up with reality: the IMU and the LTE radio are measured, the rest is labelled placeholder. Measuring the radio showed the sim's error had the wrong shape, white where reality is slow, and that is what led to the honest bound.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Testing, evidence & results</div>
<div class="ask"><span>Challenge</span> position <em>and</em> timing</div>
<div class="kicker">UC-03 timing · sim, 50 runs</div>

# Time, with its own bound and its own spoof check

<div class="cols cols-3" style="margin-top: 0.6rem">
<div class="card"><div class="bigstat" style="font-size: 2.6rem">0.44<span style="font-size: 1.4rem"> µs</span></div><div class="statlabel">mean time error 10 min after GPS loss; 49 of 50 runs within 1.5 µs (worst 1.55)</div></div>
<div class="card"><div class="bigstat" style="font-size: 2.6rem">3.3<span style="font-size: 1.4rem"> s</span></div><div class="statlabel">median to flag GPS time drifting at 50 ns/s, 50 of 50 runs (target 60 s)</div></div>
<div class="card"><div class="bigstat" style="font-size: 2.6rem">99.5<span style="font-size: 1.4rem"> %</span></div><div class="statlabel">of epochs where the stated 1σ clock bound covers the time error (target ≥ 68 %)</div></div>
</div>

<div class="cols" style="grid-template-columns: 1.3fr 1fr; margin-top: 1rem; gap: 1.4rem">
<figure class="fig short"><img src="/proof/t3-timing.png" alt="Time error 10 minutes after GPS loss, one dot per run"><figcaption>Time error 10 min after GPS loss, one dot per run; dashed line the 1.5 µs target.</figcaption></figure>
<div class="small">
<p><strong>Real:</strong> the payload's clock follows the GPS timing pulse to 769 ns (standard deviation over 80 s).</p>
<p><strong>Design rule:</strong> towers take their time from GPS, so they may contradict GPS time, never confirm it.</p>
</div>
</div>

<div class="foot">systems/results.md (b) · #170 (seeds 0–49) · #216 (timing pulse) · ADR-0024</div>

<!--
(3:30, 15 s) Timing: after ten minutes without GPS the clock is off by under half a microsecond on average, a drifting GPS clock is flagged in about three seconds, and the stated clock bound holds 99.5 percent of the time.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Testing, evidence & results</div>
<div class="ask"><span>D2</span> quantitative results</div>
<div class="kicker">Every target · 50 sim runs each unless marked real</div>

# The scoreboard, misses included

<table class="score dense" style="margin-top: 0.6rem">
<thead><tr><th>Target</th><th>Result</th><th>Kind</th><th></th></tr></thead>
<tbody>
<tr><td>Location jump ≥ 20 m flagged within 2 s</td><td class="r">1.1 s, 50 of 50 runs</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>No hazardous moment from a held jump</td><td class="r">0 with the guard · 17,042 without</td><td class="muted">sim</td><td><span class="pill ok">Met, opt-in</span></td></tr>
<tr><td>Bound covers the error after GPS loss</td><td class="r">0 of 3,005 checks missed · default 34 %</td><td><strong>real</strong></td><td><span class="pill ok">Met, opt-in</span></td></tr>
<tr><td>GPS time drift 50 ns/s within 60 s</td><td class="r">3.3 s median, 50 of 50</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>≤ 1 false alarm per hour</td><td class="r">0.0 per hour on clean runs; 0 spoof alarms in 40 h</td><td class="muted">sim + real</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Cell towers carry the solution (REQ-06)</td><td class="r">without LTE +1,961 m · without barometer +78 m · without IMU +0 m</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Crews warned of interference on approach</td><td class="r">50 of 50 warned from other aircraft's ADS-B, 48–78 s early</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Time error ≤ 1.5 µs after 10 min</td><td class="r">0.44 µs mean · 1.55 µs worst run</td><td class="muted">sim</td><td><span class="pill warn">49 of 50</span></td></tr>
<tr><td>Approach position within 556 m (UC-02)</td><td class="r">approach towers are synthetic</td><td class="muted">sim</td><td><span class="pill warn">Not scored</span></td></tr>
<tr><td>Position ≤ 25 m for 300 s after GPS loss</td><td class="r">449 m best payload filter · 677 m default</td><td class="muted">sim</td><td><span class="pill bad">Not met</span></td></tr>
<tr><td>Slow 2 m/s GPS drag within 30 s</td><td class="r">0 of 50 today · 50 of 50 with carrier hopping, 127 s</td><td class="muted">sim</td><td><span class="pill bad">Not met</span></td></tr>
</tbody>
</table>

<div class="foot">systems/results.md · analysis/results/headline (24aa5d1) · analysis/results/final (d66c929, ablation) · real: two static sessions, GPS cut in software</div>

<!--
(3:45, 20 s) Every target, including the misses. Detection works, false alarms are zero, the towers carry the solution, and crews get a 48-second warning from other aircraft. Not yet: accuracy without GPS, 449 m against 25, and a slow drag nothing catches in time. The approach leg is not scored because its towers are synthetic.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Technical approach · trade-offs</div>
<div class="kicker">Choosing the filter · 15 attacks × 50 runs each, simulation</div>

# What each defence costs

<table class="score" style="margin-top: 0.7rem">
<thead><tr><th>Filter</th><th>Error at worst second, 300 s after loss</th><th>Bound covers error, worst run</th><th>Hazardous, held jump</th><th>Unavailable</th></tr></thead>
<tbody>
<tr><td><code>ekf</code> (default)</td><td class="r">677 m</td><td class="r">69.2 %</td><td class="r bad">17,042 (20 of 50 runs)</td><td class="r">14.9 %</td></tr>
<tr><td><code>ekf-guard</code></td><td class="r">677 m</td><td class="r">69.2 %</td><td class="r ok">0</td><td class="r">19.3 %</td></tr>
<tr><td><strong><code>ekf-honest-guard</code></strong> <span class="pill ok">our pick</span></td><td class="r"><strong>449 m</strong></td><td class="r ok"><strong>100 %</strong></td><td class="r ok"><strong>0</strong></td><td class="r">19.1 %</td></tr>
<tr><td><code>ekf-mhss</code> (solution separation)</td><td class="r">677 m</td><td class="r ok">100 %</td><td class="r ok">0</td><td class="r bad">100 %</td></tr>
<tr><td><code>ekf-base-imu</code> (ground base station, sim only)</td><td class="r">332 m</td><td class="r ok">100 %</td><td class="r bad">68,537 (49 of 50 runs)</td><td class="r">12.4 %</td></tr>
</tbody>
</table>

<div class="cols cols-3 small" style="margin-top: 1rem">
<div class="card"><strong>Safety costs availability.</strong> Refusing a jumped GPS turns 17,042 hazardous moments into unavailable ones: 14.9 → 19.1 %.</div>
<div class="card"><strong>Safe is not useful.</strong> Solution separation is never wrong because it never answers: 100 % unavailable.</div>
<div class="card"><strong>A base station helps outages, hurts spoofing.</strong> Without a guard it follows the jump in 49 of 50 runs.</div>
</div>

<div class="foot">analysis/results/headline/summary.md (24aa5d1, seeds 0–49) · ADR-0038 (jump guard) · ADR-0046 · ADR-0020 (base station)</div>

<!--
(4:05, 15 s) The choice we made, and what it costs. The honest filter with the guard is the only one that is both accurate-best and never hazardous on a jump; it pays with availability. Solution separation is safe because it never answers. A base station helps through an outage and makes spoofing worse.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Safety, regulatory compliance & responsible execution</div>
<div class="kicker">Safety, regulation, privacy, security</div>

# Safe and legal by design

<div class="cols cols-3" style="margin-top: 1.2rem">
<div class="card">

### RF and ISED
Receive-only: no transmit path in hardware or code (REQ-07). Spoofing and jamming exist only as software injection.

</div>
<div class="card">

### Broadcast fields only
We decode sync signals and beacons meant for everyone, never content (Radiocommunication Act s.9(2)).

</div>
<div class="card">

### Privacy
Wi-Fi identifiers are hashed at capture. The panel hides where a recording was made.

</div>
<div class="card">

### Cybersecurity
The payload-to-laptop link is authenticated and encrypted. Every source, GPS included, is a fault hypothesis.

</div>
<div class="card">

### Flight
Pilot-flown with an RC kill switch and failsafe, low and close over empty ground, checklist before every flight.

</div>
<div class="card">

### Aviation role
Advisory: it warns, it does not steer. No certification claim; we found no standard for this kind of source yet.

</div>
</div>

<div class="foot">systems/safety.md · systems/risks.md · ADR-0001 · ADR-0011 · ADR-0026 (authenticated links) · systems/roadmap.md (Certification)</div>

<!--
(4:20, 10 s) It never transmits, we decode only fields meant for everyone, identifiers are hashed, the link is authenticated, flights follow a checklist, and it is advisory with no certification claim.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Impact, feasibility & next steps</div>
<div class="ask"><span>D3</span> roadmap to a product · LEO layer</div>
<div class="kicker">Roadmap · from hackathon to product</div>

# A GPS trust monitor that warns the autopilot

<div class="cols cols-3" style="margin-top: 1rem">
<div class="card">
<span class="tag">Now</span>

### Built this week
Detection and an honest bound on a ground laptop; a real payload; real captures; 50-run Monte Carlo on every scenario.

</div>
<div class="card">
<span class="tag">Next</span>

### Earn the accuracy
Heading at GPS loss, a velocity source, LTE carrier phase, carrier hopping; moving captures and flight tests.

</div>
<div class="card">
<span class="tag">Product</span>

### Earn the integrity case
Hours of tower data for fault rates; an on-board receiver; the warning output to the autopilot; LEO (Iridium PNT) as one more source.

</div>
</div>

<div class="cols cols-3 small" style="margin-top: 1rem">
<div><strong>Value.</strong> No spoof detector we found on sale checks GPS against cell towers. First buyers (proposed): operators beyond line of sight, drone shows, defence trials.</div>
<div><strong>Feasibility.</strong> Radios and antennas cost CAD 170; the software runs on a laptop today.</div>
<div><strong>Risks.</strong> Towers over-trusted until the slow error is modelled everywhere; slow drag undetected; untested in flight.</div>
</div>

<div class="foot">systems/roadmap.md (D3) · ADR-0013 (LEO in the roadmap) · hardware/bom.md</div>

<!--
(4:30, 20 s) The product is a receive-only trust monitor that warns the autopilot. Built now: detection and an honest bound. Next: accuracy, with heading, velocity, carrier phase and flight tests. Then the integrity case and LEO as one more source. Radios cost 170 dollars; the risks are on the slide.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Documentation quality</div>
<div class="kicker">Documentation · traceable, reproducible, decisions recorded</div>

# Every number here traces to a commit

<div class="cols cols-2" style="margin-top: 1.2rem; max-width: 52rem; gap: 1.2rem">
<div class="card small">

### In the repository
- **D1** `systems/architecture.md` · **D3** `systems/roadmap.md`
- Requirements, assumptions, risks, safety, verification
- **57 decision records**, each with options and trade-offs
- Interfaces as contracts between the two of us

</div>
<div class="card small">

### Reproducible
- Each result names its scenario or real session, seeds and commit
- One command regenerates every table and figure
- **1,485 automated tests** run before every merge
- Raw recordings stay out of git; reference data cites its source

</div>
</div>

<p class="lede" style="margin-top: 1.6rem">Thank you. Questions?</p>

<div class="foot">systems/README.md · systems/results.md · systems/quality.md · AGENTS.md</div>

<!--
(4:50, 10 s) Everything you saw traces to a scenario, a session and a commit in our repository: 57 recorded decisions and 1,485 tests. Thank you.
-->

---
layout: default
class: topo-section
---

<div class="h-full flex flex-col justify-center">
  <div class="kicker">Backup slides for questions</div>
  <h1 style="font-size: 2.6rem">Backup</h1>
  <p class="lede">Full evidence: systems/results.md · prepared answers: systems/judge-questions.md</p>
</div>

---
class: topo-light
---

<div class="kicker">Backup · real GPS cut</div>

# On real towers, no tower filter beats no towers yet

<div class="cols" style="grid-template-columns: 1.4fr 1fr; margin-top: 0.8rem; gap: 1.6rem">
<figure class="fig">
  <img src="/proof/real-cut-0040.png" alt="Error after a software GPS cut on a real session, by filter">
  <figcaption>A real static session with GPS cut in software: with towers, every filter ends hundreds of metres to kilometres off; without towers (blue) it stays within metres while standing still.</figcaption>
</figure>
<div class="small">
<p><strong>Why:</strong> the radio's slow 8 m error is not in its reported σ, and the default filter believes it.</p>
<p><strong>What the honest filter buys:</strong> 0 of 3,005 checks under the error, but a bound kilometres wide. Honest, not yet usable.</p>
<p><strong>What closes it:</strong> moving captures, carrier phase, and hearing more towers (M1–M4 in the roadmap).</p>
</div>
</div>

<div class="foot">analysis/results/real-replay-256 · analysis/results/real-gps-cut-20261111 · results.md (a)</div>

---
class: topo-light
---

<div class="kicker">Backup · the hardware we built and flew</div>

# The real payload

<div class="cols" style="grid-template-columns: repeat(4, 1fr); margin-top: 1.2rem; gap: 1.1rem">
<Media file="payload-inside.jpg" label="Inside the payload" hint="The radios on USB 2, the GPS HAT, the IMU." ratio="3 / 4" />
<Media file="antenna.jpg" label="The LTE antenna as mounted" hint="Its ground plane mattered more than the antenna: 25 dB." ratio="3 / 4" />
<Media file="field-capture.jpg" label="A static capture outdoors" hint="Where the real LTE measurements came from." ratio="3 / 4" />
<Media file="flight.mp4" label="The payload flight" hint="A 10–20 s clip, muted; it loops." ratio="3 / 4" />
</div>

<div class="foot">hardware/bom.md · hardware/antennas.md · ADR-0057 (Bingfu antenna)</div>

---
class: topo-light
---

<div class="kicker">Backup · REQ-06 ablation · realistic-long-outage, 50 runs</div>

# The cell towers carry the solution

<div class="cols" style="grid-template-columns: 1.2fr 1fr; margin-top: 0.8rem; gap: 1.6rem">
<figure class="fig"><img src="/proof/ablation.png" alt="Ablation: error with each source removed"><figcaption>95 % error after GPS loss with each source removed, paired runs.</figcaption></figure>
<table class="score">
<thead><tr><th>Removed</th><th>Added error (m)</th></tr></thead>
<tbody>
<tr><td>LTE towers</td><td class="r">+1,960.7 ± 33.3</td></tr>
<tr><td>Barometer</td><td class="r">+77.7 ± 27.8</td></tr>
<tr><td>IMU</td><td class="r">+0.0</td></tr>
</tbody>
</table>
</div>

<div class="foot">analysis/results/final/summary.md (d66c929, seeds 0–49)</div>
