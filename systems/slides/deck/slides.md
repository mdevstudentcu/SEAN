---
theme: default
title: A navigation layer that knows when it is wrong
info: Hack the Horizons 2026, Challenge 2 (resilient navigation in GPS-denied environments). Every number cites its source in systems/results.md.
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
  <div class="kicker">Hack the Horizons · Challenge 2 · resilient navigation</div>
  <h1 style="font-size: 3rem">A navigation layer that knows when it is wrong</h1>
  <p class="lede" style="margin-top: 1.2rem">A receive-only GPS trust monitor. It keeps position and time from the cell towers already in the air, and tells the operator, with a number, how far to trust them.</p>
  <p class="muted small" style="margin-top: 2.2rem">Shrikar Vempati · M. Elshoubky</p>
</div>

<!--
(0:00, 15 s) The real danger is not losing GPS. It is a display that says "trust me" when it should not. We built a navigation layer that knows when it is wrong, and says so with a number.
-->

---
class: topo-content
---

<div class="kicker">The problem</div>

# GPS fails quietly

<p class="lede">When GPS is jammed or spoofed, the aircraft keeps showing a confident position. The operator needs to know <strong>when not to trust it</strong>, and what is left.</p>

<div class="cols cols-3" style="margin-top: 1.6rem">
<div class="card">

### Users
- **Drone operators** flying beyond line of sight (UC-01)
- **Crewed aircraft** on approach (UC-02)
- **Timing users**, e.g. a satcom terminal disciplined to GPS (UC-03)

</div>
<div class="card">

### Constraints
- **Receive-only**: we never transmit or interfere
- **Signals already in the air**: LTE towers first, ADS-B and GPS health as checks
- **Low cost**: radios and antennas CAD 170

</div>
<div class="card">

### Success measures <span class="muted small">(ours, TBC)</span>
- ≤ 25 m for 300 s after GPS loss <span class="muted">(mentors: 50 m, 2 min)</span>
- The bound covers the true error
- A ≥ 20 m jump flagged within 2 s
- A 50 ns/s time drift within 60 s
- ≤ 1 false alarm per hour

</div>
</div>

<div class="foot">systems/requirements.md · use-cases.md · plan.md (targets T1–T5)</div>

<!--
(0:15, 30 s) Three users: drones beyond line of sight, crewed aircraft on approach, and anyone who takes time from GPS. Our constraints: receive-only, so no call from ISED; signals already in the air, cell towers first; and cheap radios. We set measurable targets: 25 metres for five minutes, a bound that covers the real error, a jump caught in two seconds, a time drift in a minute, under one false alarm an hour.
-->

---
class: topo-light
---

<div class="kicker">Architecture</div>

# One code path from simulation to live flight

<div class="arch" style="margin-top: 1.3rem">
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
<div class="arch-in">
  <div class="tagline"><span class="tag">Inputs</span> public tower registry (ISED) · simulation, replay and live share one interface</div>
</div>

<div class="cols cols-3 small" style="margin-top: 1.6rem">
<div><span class="tag">Decisions</span><br>57 recorded, each with its trade-off</div>
<div><span class="tag">Interfaces</span><br>one measurement record; GPS-nanosecond time everywhere</div>
<div><span class="tag">Sim to real</span><br>error models set from our own real captures</div>
</div>

<div class="foot">systems/architecture.md (D1) · systems/adr/ · systems/icd/</div>

<!--
(0:45, 25 s) The payload is a Raspberry Pi with a low-cost LTE radio, GPS with a timing pulse, an IMU and a barometer. It only listens. A laptop turns tower sync signals into ranges, fuses them in a filter that tracks every tower's clock and our own, and the integrity layer turns that into a bound and a colour. Simulation, recordings and live data go through the same code.
-->

---
class: topo-content
---

<div class="kicker">What is new</div>

# Every source can lie. The towers too.

<div class="cols cols-3" style="margin-top: 1.4rem">
<div class="card">

### Towers are checked, not trusted
A tower clock jump, a wrong registry entry or a fake tower is a fault the filter tests for, the same way it tests GPS.

</div>
<div class="card">

### Tower time comes from GPS
So towers may **contradict** GPS time, but never **confirm** it. A spoofer that moves GPS can move the towers' clocks with it.

</div>
<div class="card">

### The bound stays honest
The slow part of each tower's error is carried as its own filter state, so the confidence widens instead of shrinking when the towers drift.

</div>
</div>

<p class="muted" style="margin-top: 1.4rem">Prior work (the Kassas group) fuses cell towers for <strong>accuracy</strong>. We build the <strong>integrity</strong> on them: when to believe the answer.</p>

<div class="foot">ADR-0021 (pitch) · ADR-0046 (honest bound) · systems/research.md (novelty check)</div>

<!--
(1:10, 25 s) Others have used cell towers for accuracy. Our angle is integrity. Towers fail too: clock jumps, wrong registry entries, fake towers, and we test for them. Tower time comes from GPS, so it can contradict GPS time but never confirm it. And we keep the slow part of each tower's error as a state, so the bound grows when it should.
-->

---
class: topo-section
---

<div class="h-full flex flex-col justify-center" style="max-width: 40rem">
  <div class="kicker">Live demo · real-time monitoring · simulated flight, real tower sites</div>
  <h1 style="font-size: 2.6rem">Watch the confidence change</h1>
  <div class="flex flex-col gap-5" style="margin-top: 1.6rem">
    <div class="step"><div class="n">1</div><div><strong>GPS lost.</strong> <span class="muted">Red within three seconds: do not navigate on this.</span></div></div>
    <div class="step"><div class="n">2</div><div><strong>A 300 m spoofed jump, no guard.</strong> <span class="muted">Caught at the first fake fix, then the plain filter takes it back: green and wrong.</span></div></div>
    <div class="step"><div class="n">3</div><div><strong>The same attack, with our guard.</strong> <span class="muted">Stays red until the spoofer stops, then recovers to within metres.</span></div></div>
  </div>
</div>

<!--
(1:35, 80 s) SWITCH TO THE PANEL: deploy/demo/demo.sh stage. Enter at T+105 (skip the towers study if short of time), T+188, T+212.
1. "A simulated drone over Carleton, real tower sites. Green: trust it, bound 7 m. GPS is gone... within three seconds, red. Forty seconds later we are 300 m off, and the bound says so."
2. "A spoofer jumps GPS 300 m. Caught at the first fake fix. But watch: half a minute later the plain filter takes it back. Green, and 300 m wrong."
3. "Same attack with our jump guard. It stays red, the error grows but the bound grows faster. The spoofer stops, real GPS is back, green, within a few metres."
-->

---
class: topo-light
---

<div class="kicker">Results · 50 simulated runs per scenario unless marked real</div>

# The scoreboard, misses included

<table class="score" style="margin-top: 0.8rem">
<thead><tr><th>Target</th><th>Result</th><th>Kind</th><th></th></tr></thead>
<tbody>
<tr><td>Location jump ≥ 20 m flagged within 2 s</td><td class="r">1.1 s, 50 of 50 runs</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>No hazardous epoch from a held jump</td><td class="r">0 with the guard · 17,042 without</td><td class="muted">sim</td><td><span class="pill ok">Met, opt-in</span></td></tr>
<tr><td>Bound covers the error after GPS loss</td><td class="r">0 of 3,005 checks missed · default 34 %</td><td class="muted"><strong>real</strong></td><td><span class="pill ok">Met, opt-in</span></td></tr>
<tr><td>50 ns/s GPS time drift within 60 s</td><td class="r">3.3 s median, 50 of 50</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>≤ 1 false alarm per hour</td><td class="r">0 spoof alarms in 40 h of clean data</td><td class="muted">sim + real</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Time error ≤ 1.5 µs after 10 min</td><td class="r">0.44 µs mean · 1.55 µs worst seed</td><td class="muted">sim</td><td><span class="pill warn">49 of 50</span></td></tr>
<tr><td>Position ≤ 25 m for 300 s after GPS loss</td><td class="r">449 m best payload filter · 677 m default</td><td class="muted">sim</td><td><span class="pill bad">Not met</span></td></tr>
<tr><td>Slow 2 m/s GPS drag within 30 s</td><td class="r">0 of 50 today · 50 of 50 in a hopping study, 127 s</td><td class="muted">sim</td><td><span class="pill bad">Not met</span></td></tr>
</tbody>
</table>

<div class="foot">systems/results.md · analysis/results/headline (24aa5d1, seeds 0–49) · real: two static sessions, GPS cut in software</div>

<!--
(2:55, 30 s) Here is every target, including the misses. Detection works: jumps in 1.1 seconds, time drift in about 3, no false alarms in 40 hours of clean data. With the guard, a held jump never produces a hazardous epoch. On real recordings our bound never under-stated the error; the default did a third of the time. What does not work yet: accuracy without GPS, 449 metres against 25, and a slow drag that nothing catches in time.
-->

---
class: topo-content
---

<div class="kicker">Rigor · how the confidence number is computed</div>

# A bound you can act on, and why accuracy misses

<div class="cols cols-2" style="margin-top: 1rem; gap: 2.4rem">
<div>

### The protection level
$$\mathrm{HPL} = k_H\,\sigma_{\max},\qquad k_H=\sqrt{2\ln 10^{7}} = 5.68$$
<p class="muted small">σ<sub>max</sub>: the filter's largest horizontal standard deviation. A horizontal error is two-dimensional, so a 10<sup>−7</sup> per-epoch risk (TBC) needs 5.68, not the one-dimensional 5.33. We found and fixed that in our own code (ADR-0056). Time gets its own bound from the clock's σ.</p>

<h3 style="margin-top: 1.2rem">On real recordings, GPS cut in software</h3>
<div class="flex flex-col gap-2 small" style="margin-top: 0.5rem">
<div>Default filter: bound below the true error</div>
<div class="bar"><span style="width: 34%; background: var(--bad)"></span></div>
<div class="num">1,025 of 3,005 checks (34 %)</div>
<div style="margin-top: 0.4rem">Honest-bound filter</div>
<div class="bar"><span style="width: 0.6%; background: var(--ok)"></span></div>
<div class="num">0 of 3,005</div>
</div>

</div>
<div>

### The accuracy budget
<p class="small">Each error term is grown from the handover, when GPS is lost, and checked against the Monte Carlo:</p>
<ul class="small">
<li><strong>Clean route</strong>: range noise after the handover sets it (21 of 22 m) and the fallback is met</li>
<li><strong>Realistic route</strong>: multipath alone is 215 m at 2 min; four more terms each exceed 25 m</li>
</ul>
<h3 style="margin-top: 1rem">What our radio measured</h3>
<div class="flex gap-10" style="margin-top: 0.4rem">
<div><div class="bigstat">0.73<span style="font-size: 1.6rem"> m</span></div><div class="statlabel">jitter on the strongest cells</div></div>
<div><div class="bigstat">8<span style="font-size: 1.6rem"> m</span></div><div class="statlabel">slow error it does not report</div></div>
</div>
<p class="muted small" style="margin-top: 0.6rem">The slow error is why towers made position worse: the filter believed them. The fix is to model it, which is what the honest bound does.</p>

</div>
</div>

<div class="foot">systems/accuracy-budget.md · ADR-0056 · analysis/results/lte-measured-noise · results.md (a)</div>

<!--
(3:25, 30 s) How the number is computed: 5.68 times the filter's largest horizontal standard deviation, the two-dimensional factor for a one-in-ten-million risk. We caught our own one-dimensional factor and fixed it. On real recordings the default filter's bound was too small a third of the time; ours, never. The accuracy budget explains the miss: our radio is precise, 0.73 m, but carries a slow 8 m error it does not report, so the filter over-trusted the towers.
-->

---
class: topo-content
---

<div class="kicker">Safety, regulation, privacy, security</div>

# Safe and legal by design

<div class="cols cols-3" style="margin-top: 1.4rem">
<div class="card">

### Receive-only
No transmit path in hardware or code (REQ-07). Spoofing and jamming exist only as software fault injection. No ISED exposure.

</div>
<div class="card">

### Broadcast fields only
We decode sync signals and beacons meant for everyone, never content (Radiocommunication Act s.9(2)).

</div>
<div class="card">

### Privacy
Wi-Fi identifiers are hashed at capture. The panel can hide where a session was recorded.

</div>
<div class="card">

### Cyber
The payload-to-laptop link is authenticated and encrypted. Every source, GPS included, is a fault hypothesis.

</div>
<div class="card">

### Flight
Pilot-flown with an RC kill switch and failsafe, low and close over empty ground, a pre-flight checklist.

</div>
<div class="card">

### Aviation role
Advisory: it tells the operator, it does not steer. No certification claim; we found no standard for this kind of source yet.

</div>
</div>

<div class="foot">systems/safety.md · ADR-0001 · ADR-0011 · systems/roadmap.md (Certification)</div>

<!--
(3:55, 20 s) It never transmits, so there is no spectrum risk; attacks are injected in software. We decode only fields meant for everyone. Wi-Fi identifiers are hashed. The link is authenticated. And it is advisory: it warns, it does not steer, and we do not claim certification.
-->

---
class: topo-content
---

<div class="kicker">Roadmap · from hackathon to product (D3)</div>

# A GPS trust monitor that warns the autopilot

<div class="cols cols-3" style="margin-top: 1.2rem">
<div class="card">
<span class="tag">Now</span>

### Built this week
Detection and the bound on a ground laptop; a real payload; static real captures; 50-run Monte Carlo on every scenario.

</div>
<div class="card">
<span class="tag">Next</span>

### Earn the accuracy
Heading at GPS loss, a velocity source, LTE carrier phase, carrier hopping. Moving captures and a flight test.

</div>
<div class="card">
<span class="tag">Product</span>

### Earn the integrity case
Many hours of tower data for fault rates; an on-board receiver; the warning output to the autopilot; a LEO layer (Iridium PNT) as one more source.

</div>
</div>

<div class="cols cols-2 small" style="margin-top: 1.2rem">
<div><strong>First buyers (proposed):</strong> operators flying beyond line of sight, drone shows, defence trials. <strong>Gap:</strong> we found no spoof detector on sale that checks GPS against cell towers.</div>
<div><strong>Risks:</strong> towers over-trusted until the slow error is modelled everywhere; slow drag undetected; untested in flight. <strong>Cost today:</strong> radios and antennas CAD 170.</div>
</div>

<p style="margin-top: 1.4rem"><strong>Every number in this deck traces to a scenario or session and a commit in our repository.</strong></p>

<!--
(4:15, 40 s) The product is a receive-only trust monitor that warns the autopilot. Built now: detection and an honest bound. Next: accuracy, with heading, a velocity source and carrier phase, proven on moving captures and a flight. Then the integrity case: hours of tower data, an on-board receiver, the autopilot output, and LEO as one more source. Every number you saw traces to a commit in our repository. Thank you.
-->

---
layout: default
class: topo-section
---

<div class="h-full flex flex-col justify-center">
  <div class="kicker">Backup slides for questions</div>
  <h1 style="font-size: 2.6rem">Questions</h1>
  <p class="lede">The full evidence: systems/results.md · prepared answers: systems/judge-questions.md</p>
</div>

---
class: topo-light
---

<div class="kicker">Backup · spoof defence and the base station, 15 attacks × 50 runs (sim)</div>

# Which filter to trust

<table class="score" style="margin-top: 0.8rem">
<thead><tr><th>Filter</th><th>Error at worst second, 300 s after loss</th><th>Bound covers error, worst run</th><th>Hazardous epochs, held jump</th><th>Unavailable</th></tr></thead>
<tbody>
<tr><td><code>ekf</code> (default)</td><td class="r">677 m</td><td class="r">69.2 %</td><td class="r">17,042 (20 of 50 runs)</td><td class="r">14.9 %</td></tr>
<tr><td><code>ekf-guard</code></td><td class="r">677 m</td><td class="r">69.2 %</td><td class="r">0</td><td class="r">19.3 %</td></tr>
<tr><td><strong><code>ekf-honest-guard</code></strong></td><td class="r"><strong>449 m</strong></td><td class="r"><strong>100 %</strong></td><td class="r"><strong>0</strong></td><td class="r">19.1 %</td></tr>
<tr><td><code>ekf-base-imu</code> (sim-only base station)</td><td class="r">332 m</td><td class="r">100 %</td><td class="r">68,537 (49 of 50 runs)</td><td class="r">12.4 %</td></tr>
</tbody>
</table>

<p class="small muted" style="margin-top: 1rem">A base station helps through an outage and hurts under spoofing: it has no jump guard. Every filter detects 0 of 50 slow 2 m/s drags. Computed at the earlier 5.33 factor; at 5.68 each bound is 6.5 % wider.</p>

<div class="foot">analysis/results/headline/summary.md (24aa5d1, seeds 0–49)</div>

---
class: topo-light
---

<div class="kicker">Backup · real signals</div>

# What our radio saw on real towers

<div class="cols cols-2" style="margin-top: 1rem">
<div class="card">

### LTE range precision (15 static captures)
- White noise **0.73 m** at 13–16 dB SNR, **10.9 m** at −11 to −8 dB
- Slow, correlated error inside one track: **2.4 to 17 m, median 8.1 m**, not in the reported σ
- The radio's reported σ is 1.3 to 2.0 times the white part
- Sectors of one site drift together within 0.5 m/s: one clock per site

</div>
<div class="card">

### Real GPS cut, four static sessions
- With towers, position is hundreds of metres to kilometres worse than without: **no tower filter beats no towers yet**
- Honest bound: 0 of 3,005 checks under the error, but kilometres wide: honest, not yet usable
- A real 60 s capture: three cells tracked ten times a second, two consistent with one registered site

</div>
</div>

<div class="foot">analysis/results/lte-measured-noise (8892fca) · ADR-0036 · results.md (a)</div>

---
class: topo-light
---

<div class="kicker">Backup · timing (UC-03)</div>

# Time, with its own bound

<div class="cols cols-3" style="margin-top: 1.4rem">
<div class="card"><div class="bigstat">0.44<span style="font-size: 1.4rem"> µs</span></div><div class="statlabel">mean time error after 10 min without GPS (sim, 50 runs); worst seed 1.55 µs against 1.5</div></div>
<div class="card"><div class="bigstat">3.3<span style="font-size: 1.4rem"> s</span></div><div class="statlabel">median to flag a 50 ns/s GPS time drift, 50 of 50 runs (target 60 s)</div></div>
<div class="card"><div class="bigstat">99.5<span style="font-size: 1.4rem"> %</span></div><div class="statlabel">of epochs where the stated 1σ clock bound covers the time error (target 68 %)</div></div>
</div>

<p class="muted" style="margin-top: 1.2rem">The time protection level is 5.33 × the clock's σ. Real time-of-day discipline on the payload: the GPS timing pulse into chrony, 769 ns standard deviation over 80 s.</p>

<div class="foot">systems/results.md (b), #170 (seeds 0–49) · #216 (PPS)</div>
