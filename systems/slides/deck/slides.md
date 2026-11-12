---
theme: default
title: SEAN, a navigation layer that knows when it is wrong
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
  <div style="font-family: var(--display); font-size: 4.2rem; letter-spacing: 0.08em; line-height: 1; margin-top: 0.6rem">SEAN</div>
  <div class="small muted" style="font-family: var(--mono); margin-top: 0.5rem; letter-spacing: 0.06em">Signals-of-opportunity · Error-bounded · Assured Navigation</div>
  <h1 style="font-size: 2.2rem; margin-top: 1.4rem">A navigation layer that knows when it is wrong</h1>
  <p class="lede" style="margin-top: 1.2rem">A receive-only GPS trust monitor. It keeps position and time from the cell towers already in the air, and tells the operator, with a number, how far to trust them.</p>
  <p class="muted small" style="margin-top: 2.2rem">Team 12</p>
</div>
<div style="position: absolute; right: 4.2rem; top: 50%; transform: translateY(-50%); width: 27rem">
  <Media file="drone-payload.jpg" label="The drone with the payload mounted" hint="Outdoors, three-quarter view, antennas visible. Landscape." ratio="4 / 3" />
</div>

<!--
**0:00 → 0:20 · 20 s**

**Say:**

Hi, we're Team 12, and this is SEAN: the Signals-of-opportunity, Error-bounded, Assured Navigation module.

It does two jobs: keep a position from cell towers when GPS goes away, and catch any source that's lying to us, GPS or even the towers, with a number that says how far to trust it.

***

**Why this pitch (ADR-0021).** We weighed three:
- *Accuracy-first* (more signals, a better filter): a simple story, but it repeats published work (the Kassas group) and is weak on innovation.
- *Integrity-first* (**chosen**): learn the signals while GPS is trusted, then use them to keep position and time, to catch GPS lying, *and* to catch the towers lying. It covers all three use cases and speaks the integrity language a navigation company uses.
- *Hostile emitters or space* (jammer-as-beacon, Starlink): eye-catching, but simulation only, so the weakest evidence.

**Name:** S = signals of opportunity, E = error-bounded (the protection level), A = assured (the industry's word: assured PNT), N = navigation.
-->

---
class: topo-light
---

<div class="ask"><span>D1</span> requirements tied to the use cases</div>
<div class="kicker">The problem</div>

# GPS fails quietly

<p class="lede" style="max-width: 60ch">Jammed or spoofed, the aircraft keeps showing a confident position. The operator needs to know <strong>when not to trust it</strong>, and what is left.</p>

<div class="cols" style="grid-template-columns: 0.8fr 1.7fr; gap: 1.6rem; margin-top: 1.1rem; align-items: start">
<div class="flex flex-col gap-3">
<div class="card"><h3>Users</h3>Drones beyond line of sight · crews on approach · timing users</div>
<div class="card"><h3>Rules we set</h3>Listen only · cell towers first · CAD 170 of radios</div>
</div>
<table class="score big">
<thead><tr><th>User</th><th>Needs</th><th>Target</th></tr></thead>
<tbody>
<tr><td><strong>Drone</strong></td><td>keep position after GPS loss</td><td class="r">25 m for 5 min</td></tr>
<tr><td><strong>Drone, crew</strong></td><td>a trustworthy radius on every fix</td><td class="r">error inside 99.9 %</td></tr>
<tr><td><strong>Crew</strong></td><td>approach-grade position</td><td class="r">within 556 m (RNP 0.3)</td></tr>
<tr><td><strong>Timing</strong></td><td>keep time without GPS</td><td class="r">1.5 µs after 10 min</td></tr>
<tr><td><strong>All</strong></td><td>catch GPS that lies</td><td class="r">20 m jump in 2 s</td></tr>
</tbody>
</table>
</div>

<div class="foot">systems/requirements.md · systems/use-cases.md · systems/assumptions.md · ADR-0034 (targets after the mentors' answers)</div>

<!--
**0:20 → 0:45 · 25 s**

**Say:**

Jammed or spoofed GPS rarely goes blank. It keeps showing a confident position that's simply wrong.

That hurts drone operators beyond line of sight, crews on approach, and anyone who takes time from GPS. Our rules: only listen; use signals already in the air, cell towers first; and keep it cheap, 170 dollars of radios. Every use case maps to a requirement with a number.

**Point at:** the table, row by row with your hand.

**Scores:** Problem & requirements (1) · D1 requirements tied to use cases (mentor ask) · crewed *and* uncrewed, position *and* timing.

***

**How the mentors shaped the targets (mentor-qa.md, ADR-0034):**
- Accuracy: "≤ 50 m for ~2 min should be OK-ish… explain the calculations." We kept our stricter 25 m / 300 s and score both, and the per-term accuracy budget became a deliverable (slide 6).
- Integrity level: "part of the challenge… consider different methods for indicating confidence." So we set our own target and built ten readouts (slide 5).
- Timing: "handover timing matters." So the budget includes how long GPS must be good before loss (slide 6).
- Attacks: "begin with location jumps." So jumps came first (slide 4).

**Why each assumption:**
- *GPS good at start-up:* tower clocks are learned while GPS is trusted. Learning is gated (GPS trusted for 30 s, `TBC`) and rolled back if GPS turns out to have been lying (ADR-0022).
- *ISED registry:* our dongle decodes only the cell's physical ID, not its global ID (that needs the whole carrier), so we match the frequency and ID to one registered site or drop the cell (ADR-0023).
- *Attacks in software only:* we never transmit (ADR-0001). The mentors said transmitting is only OK in a trusted lab.

**If asked about the numbers:** the alert limits are our proposal (`TBC`), set from the mentors' guidance; the exposure time behind the 10⁻⁷ risk is the next thing to define.

**If asked:**
- *Why 25 m when the mentors said 50 m?* We set ours first and kept it; we score both.
- *What altitude?* Simulated flights at 40–45 m; our real captures are on the ground. How tower antenna downtilt affects reception at altitude is not measured.
-->

---
class: topo-light
---

<div class="ask"><span>Challenge</span> communication signals first</div>
<div class="kicker">Architecture (D1) and what is new</div>

# Every source can lie, the towers too

<div class="arch" style="margin-top: 0.7rem">
  <div class="node payload">
    <div class="nt">Payload</div>
    <div class="ns">Raspberry Pi 4B · never transmits</div>
    <ul><li>LTE radio</li><li>GPS + timing pulse</li><li>IMU + barometer</li><li>ADS-B receiver</li></ul>
  </div>
  <div class="arrow"><span>authenticated link<br>or recording</span></div>
  <div class="node"><div class="nt">Front ends</div><div class="ns">cell sync timing → tower ranges</div></div>
  <div class="arrow"></div>
  <div class="node"><div class="nt">Fusion filter</div><div class="ns">position, every tower's clock, our own clock</div></div>
  <div class="arrow"></div>
  <div class="node"><div class="nt">Integrity</div><div class="ns">position and time bounds · jump guard · sky check</div></div>
  <div class="arrow"></div>
  <div class="node panel"><div class="nt">Operator panel</div><div class="ns"><span class="ok">green</span> · <span class="warn">amber</span> · <span class="bad">red</span>, with the number</div></div>
</div>

<div class="cols" style="grid-template-columns: 1fr 1fr 1fr 0.95fr; margin-top: 1rem; gap: 1rem; align-items: stretch">
<div class="card small"><h3>Towers are checked</h3>A clock jump, a wrong registry entry or a fake tower is a fault the filter tests for, as it tests GPS.</div>
<div class="card small"><h3>Tower time is GPS time</h3>Towers may <strong>contradict</strong> GPS time, never <strong>confirm</strong> it.</div>
<div class="card small"><h3>The bound stays honest</h3>Each tower's slow error is its own state, so confidence widens when towers drift.</div>
<Media file="payload.jpg" label="The payload, lid off" hint="Pi, LTE radio, GPS, IMU, barometer." ratio="4 / 3" />
</div>

<p class="small muted" style="margin-top: 0.7rem">Prior work (the Kassas group) fuses cell towers for <strong>accuracy</strong>. We build the <strong>integrity</strong> on them. Simulation, recordings and live data run the same code.</p>

<div class="foot">systems/architecture.md (D1) · ADR-0021 · ADR-0024 · ADR-0046 · systems/research.md (novelty check)</div>

<!--
**0:45 → 1:10 · 25 s**

**Say:**

The payload is a Raspberry Pi with an LTE radio, GPS, an IMU and a barometer; it only listens. [point along the chain] The laptop turns tower signals into distances and outputs a position, a bound on how wrong it could be, and a colour.

The twist: nothing is trusted blindly, not even the towers. Their errors are tracked, and since they take their time from GPS, they can contradict GPS but never vouch for it.

**Scores:** Technical approach (2) · Innovation (3) · Prototype (4) · communication signals primary.

***

**Why cell towers carry it:**
- The challenge says communication signals of opportunity should be primary.
- They're everywhere, strong, at fixed registered sites, and their sync signals (PSS/SSS) are fully known and sit in the central 1.08 MHz, so a cheap RTL-SDR can range on them.
- Sync signals are hard to jam: in a cabled LTE testbed, denial took about 30 dB more power than for the reference signals (Rao 2017).
- The gap: we found no spoof detector on sale that checks GPS against cell towers.

**What else we looked at, and why it isn't primary:**
- **ADS-B:** it's someone else's GPS fix, so it fails with GPS (ADR-0024). Spoofed aircraft kept high-integrity flags in published data. We use it only as an early warning: it raises our GPS fault prior and never steers position (ADR-0033).
- **VOR:** the front end is built, but it got no lock on real captures. It's an independent source, so it stays on the list.
- **Wi-Fi:** short range; beacons can be cloned (hashing protects privacy, not integrity); ranging (FTM) would need us to transmit.
- **LEO, Iridium:** our radio can hear it. But published fixes from its open bursts are 100–200 m, standing still, over minutes, and the bursts are unauthenticated; the paid service already sells on a chip. So it's simulated (ADR-0013) and in the roadmap, which the mentors called "a good choice".
- **Starlink:** a dish transmits, so we can only listen; simulation only.
- **Broadcast time:** CHU stopped in June 2026; WWVB needs an LF receiver; FM RDS gives minute resolution (ADR-0019).
- **A jammer as a beacon:** simulation only, behind guardrails, never the sole aid (ADR-0025).

**Architecture choices:**
- *Record raw, process on the ground (ADR-0002); sim, replay and live are interchangeable (ADR-0004).* One code path, so a result in sim runs unchanged on a recording.
- *Pi 4B alone* over a Pi Zero hub or a Pico (ADR-0018): one board, one PPS-disciplined clock for every timestamp.
- *Radio IQ to a USB drive:* the SD card dropped 2.9 % of the IQ in 4 gaps per 10 min (ADR-0042).
- *Tower clocks per site, grouped by network builder* (TELUS builds for Bell and TELUS; Rogers; Vidéotron) (ADR-0022). Rejected: one independent clock per tower (no redundancy, no drift); one clock per builder (wrong for FDD, sites are only frequency-locked); base-station differencing (ADR-0020: built in sim only; helps outages, but follows a spoofer without a guard).
- *Three dependency classes, not two* (independent, GPS-timed, GPS-derived; ADR-0024): keeps tower geometry when GPS fails and drops only tower time.

**On novelty:** Jia, Khalife & Kassas (2023) already group tower clocks and run solution separation. What we found no one doing: tagging each source by its GPS dependence, and a GPS fault hypothesis that includes the towers' borrowed time. Say "we found none", never "first".

**If asked:**
- *What if the tower table is wrong?* An ambiguous row is dropped. In sim a fake tower on a real ID fooled one filter; solution separation flagged it.
- *Is the link secure?* CurveZMQ: authenticated and encrypted (ADR-0026).
-->

---
class: topo-light
---

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
**1:10 → 2:05 · 55 s · LIVE DEMO**

**Before the talk:** terminal open with the demo command typed; the panel in a browser tab beside the slides.

**Do:** run `deploy/demo/demo.sh jump` (about 55 s, two runs). It starts on the jump **without** the guard. Press **Enter when T+ passes 188** to switch to the guarded run (the panel shows NO DATA for 3–6 s; keep talking). Press **Enter when T+ passes 212** to stop. If anything fails, don't debug: say "here's the recording" and use the clips (script at the bottom).

**Say:**

Let me show you. This is our real operator panel, with a simulated drone flying past real tower sites. Right now GPS is healthy: green, with a 7-metre bound.

[T+150, amber] Now a spoofer pushes GPS 300 metres east. We catch the very first fake fix. [T+155, red] And it goes red.

[T+177, green again] But watch. Half a minute later this normal filter gives in and takes the fake GPS back. Green, a 7-metre bound, and 300 metres wrong. That's exactly the failure we're worried about.

[Enter at T+188; NO DATA for a few seconds] Same flight, same attack, now with our jump guard. [point at "ekf-guard" in the top bar]

[T+150] Caught at the first fake fix again. [T+155 to 200, red] This time the fake GPS stays out. We're flying on the barometer and dead reckoning, so the error grows, but the bound grows faster, and it stays red.

[T+200, green] The spoofer stops, real GPS comes straight back, and we're within a few metres. [Enter at T+212 to stop]

**If you're on the clips instead:** (1) "GPS lost: red in three seconds. Forty seconds on we're 325 metres off, and the bound, 895, says so." (2) "A spoofer jumps GPS 300 metres. Caught, but half a minute later the normal filter takes it back: green and 300 metres wrong." (3) "Same attack with our guard: it stays red, and real GPS comes straight back when the spoofer stops."

**Scores:** Presentation & demo (8) · D2 real-time monitoring · mentor ask: begin with location jumps.

***

**Why the plain filter gets fooled:** once it rejects GPS, its own uncertainty grows, so the same fake fix eventually passes its check. *A spoofer only has to wait.*

**Four ways to handle a detected jump (ADR-0038; sim, 50 runs per leg):**
- *Gate only* (before): hazardous on 49 of 50 runs, and on the spoofed position at +120 s.
- *Refuse until GPS steps back* (**chosen**): hazardous epochs on 3 of 50 runs; honest GPS back 0.1 s after the jump ends.
- *Refuse for the rest of the flight:* as safe, but honest GPS never returns.
- *Re-admit on a likelihood test against the filter's covariance:* the spoofer waits it out, hazardous on 46 of 50.

**What it costs:** while GPS is refused we dead-reckon: median error 1,263 m at +120 s after a refused jump, shown as unsafe. It's opt-in, not the default.

**Problems still open:**
- The guard never judges GPS *returning after an outage*, so jam-then-spoof meets only the normal check.
- After a long outage the normal check can reject honest GPS for good; one simulated run drifted to 54 km (#246).

**If asked:**
- *Is that real?* A simulated drone (seed 0) past real tower sites, through the same code that runs recordings and live data. Attacks are injected in software because we never transmit. The panel is the real operator panel.
- *Why not stop the spoof?* We flag, refuse and coast; the warning goes to the autopilot or pilot. Mitigation stays with them.
-->

---
class: topo-light
---

<div class="ask"><span>Use case</span> navigation continuity</div>
<div class="kicker">Cell-tower positioning after GPS loss · simulation, 50 runs</div>

# The towers do localize, once they're modelled honestly

<div class="cols" style="grid-template-columns: 1.55fr 1fr; gap: 1.2rem; margin-top: 0.3rem; align-items: start">
<figure class="fig" style="margin: 0">
  <img src="/proof/ladder.png" alt="Worst-second 95 % error after GPS loss for each fix, from 12,507 m down to 10 m">
  <figcaption>Each row adds one fix to the same flights. Worst second of the first 5 min, 95 % of runs.</figcaption>
</figure>
<div class="flex flex-col gap-2">
<figure class="fig" style="margin: 0">
  <img style="max-height: 12.5rem; object-fit: contain" src="/proof/towers-holding.png" alt="Panel 45 s after GPS loss in the towers study: 17.9 m error, LTE in use, HPL 108.7 m">
  <figcaption>The study on the real panel, 45 s after GPS loss: <strong>17.9 m off</strong>, towers in use, bound 109 m.</figcaption>
</figure>
<div class="card grounded">
<h3>Grounded in real measurements</h3>
<ul>
<li><strong>Real towers:</strong> every site from the ISED licence database, at its licensed location</li>
<li><strong>Our radio, measured:</strong> 0.73 m jitter and the hidden 8 m slow error, from 15 real captures</li>
<li><strong>Our sensors, measured:</strong> motion-sensor noise overnight; payload clock to 35 ns of GPS</li>
<li><strong>Same code on real data:</strong> faults injected into real recordings are caught (300 m jump in 0.6 s)</li>
</ul>
</div>
</div>
</div>

<div class="foot">PR #247 · PR #262 (seeds 0–49, ekf) · tower-count #208 (clean ranges, seeds 0–19) · towers demo #266 · lte-measured-noise · final ablation (d66c929)</div>

<!--
**2:05 → 2:40 · 35 s**

**Say:**

So can the towers actually navigate? Yes, once they're modelled honestly. [point down the bars] Believe the radio's own accuracy claim and you're 12 kilometres off. Learn each tower's real noise and hear more carriers, and the same flights hold to 132 metres, 105 on our measured noise. With clean ranges from all 17 nearby towers: 10 metres for the full five minutes.

[point at the panel] Here it is on our panel: 45 seconds without GPS, 18 metres off.

[point at the box] And this isn't a toy simulation: it flies over the real licensed towers, with our radio's noise, our motion sensor and our clock all measured on the payload. The same code runs on real recordings.

**Scores:** Technical approach (2) · Evidence (5) · Innovation (3) · use case: navigation continuity · communication signals primary.

***

**What each bar is (all sim, drone leg, worst second of 0–300 s after GPS loss, 95th percentile across 50 runs):**
- *No towers:* barometer and dead reckoning only, 2,909 m.
- *Believing the radio:* the front end tells the filter 2 m; the truth is tens. The filter rejects almost every reading, and each one it accepts is believed to 2 m and drags the position: 12,507 m, worse than no towers.
- *Learned noise* (ADR-0039): the filter learns each tower's real noise from its residuals, 2,474 m.
- *+ 13 carriers* (ADR-0040): one radio hops across 13 LTE frequencies and hears about 27 masts instead of 2. With learned noise: 132 m. Hopping alone, without learned noise, doesn't help (11,894 m).
- *Measured noise* (PR #262): the sim's LTE noise set from our real captures, 105 m.
- *Reflections at rest:* multipath as small as we measured standing still, 51 m. Just over the mentors' 50 m.
- *Clean ranges* (tower-count study, 20 runs): ideal ranges from all 17 sites within 3 km, with barometer and IMU, 10 m, inside 25 m for all 300 s. This shows the geometry is enough; the limit is range quality.

**If pressed, frame it like this:**
- These are simulated flights over the real towers; the hardware step is a front end that hears several carriers (the payload listens to one today). Learned noise is an option in the code, selected by name.
- On real static recordings, towers haven't beaten no towers yet → backup *real GPS cut*.
- The demo seed isn't cherry-picked: at 45 s it's mid-pack (rank 23 of 50: 39.7 m against a median of 44.7). Left running to 300 s, it's the worst of the 50 (117 m against a median of 50).

**What closes the gap:** hearing more towers (a hopping front end or a second radio), multipath measured in motion, then LTE carrier phase.

**If asked:**
- *Why does believing the radio make it worse than nothing?* Each accepted reading shrinks the filter's uncertainty while pulling the position away, so it stops listening to anything else.
- *Is 10 m realistic?* It's the ceiling with perfect ranges: it proves the geometry works, not that our radio delivers it today.
-->

---
class: topo-light
---

<div class="ask"><span>Mentor ask</span> several ways to show confidence</div>
<div class="kicker">The real panel, live as GPS is lost · 6× speed</div>

# Confidence shown ten ways, and it holds up

<div class="cols" style="grid-template-columns: 2.75fr 1fr; gap: 1.1rem; margin-top: 0.2rem; align-items: start">
<div class="annot">
  <Clip src="/proof/clips/outage-full.mp4" poster="/proof/panel-unsafe.jpg" label="The operator panel as GPS is lost: nominal, then UNSAFE with the bound growing" />
  <span class="pin" style="left: 96%; top: 8%">1</span>
  <span class="pin" style="left: 65.3%; top: 40%">2</span>
  <span class="pin" style="left: 100.6%; top: 36.6%">3</span>
  <span class="pin" style="left: 65.3%; top: 26%">4</span>
  <span class="pin" style="left: 65.3%; top: 30.5%">5</span>
  <span class="pin" style="left: 65.3%; top: 94%">6</span>
  <span class="pin" style="left: 66.6%; top: 83%">7</span>
  <span class="pin" style="left: 42%; top: 28%">8</span>
  <span class="pin" style="left: 22%; top: 79%">9</span>
  <span class="pin" style="left: 65.3%; top: 66%">10</span>
</div>
<div>
<ol class="legend tight">
<li><strong>State</strong> colour and words</li>
<li><strong>Protection level</strong> vs limit</li>
<li><strong>ANP vs RNP</strong>, a crew's terms</li>
<li><strong>GPS trust</strong> word</li>
<li><strong>Spoof check</strong>: sky, power, cues</li>
<li><strong>Per-source</strong> trust</li>
<li><strong>Time bound</strong>, time to alert</li>
<li><strong>Map</strong>: bound circle</li>
<li><strong>Bound over time</strong> + forecast</li>
<li><strong>Alerts</strong>, latched</li>
</ol>
<h3 style="margin-top: 0.8rem">Is it true?</h3>
<div class="proofstat"><div class="num"><span class="bad">41.6 %</span> → <span class="ok">0.4 %</span></div><div class="lbl">error above the bound · sim, 200 runs · 0 hazardous</div></div>
<div class="proofstat"><div class="num"><span class="bad">34 %</span> → <span class="ok">0</span></div><div class="lbl">bound below the error · <strong>real</strong>, 3,005 checks</div></div>
</div>
</div>

<div class="foot">HPL = 5.68 × σ<sub>max</sub> (two-dimensional, 10⁻⁷ per epoch, TBC; ADR-0056) · ADR-0046 · analysis/results/honest-bound · real-replay-256</div>

<!--
**2:40 → 3:05 · 25 s**

**Say:**

As the mentors asked, the panel shows confidence ten ways [sweep the pins], from a colour to a pilot's 95 % radius to latched alerts.

And it's true. [point at the numbers] In simulation the standard bound was wrong 40 % of the time; ours, under half a percent. On real recordings: a third of the time, against never.

**Point at:** pins 1, 2, 3 and 7 as you name them, the rest in one sweep; then the two red → green numbers.

**Scores:** Technical approach (2) · Evidence (5) · mentor ask: several ways to show confidence · numerical confidence for crewed and uncrewed.

***

**Why ten readouts, not one number:** the mentors said to "consider different methods". Each user reads it differently: a colour for a drone operator, ANP against RNP for a crew (UC-02), a time bound for timing users (UC-03).

**The spoof check (ADR-0041):** the sky map alone (a satellite received from below the horizon) is blind to a spoofer that fakes the right sky. Power pattern alone is soft, because an antenna indoors flattens it too. So we combine both, plus the filter's cues, into one *advisory* level. It changes no estimate: the mentors asked us to decide, and the jump guard already acts.

**Why the default bound lied:** the radio told the filter its ranges were good to **2 m**; in truth they're tens of metres, with a slow error on top. Almost every reading fails the check, and each one that passes is believed to 2 m, so it shrinks the uncertainty while pulling the position away.

**Three fixes we weighed (ADR-0046):**
- *A bigger factor after GPS loss:* one number, but it hides the model error and only fits what it was tuned on.
- *More process noise:* the wrong term; it inflates the bound everywhere.
- *The slow error as a filter state* (**chosen**, `ekf-honest`), on top of learning each radio's noise from its residuals (ADR-0039).

**Then a field A/B of 7 other settings on real and sim data (ADR-0052): none beat it** under a rule fixed in advance. For example, using LTE only when 3 cells are heard gave 4 m on the real session but 5,765 m in sim. Real and sim disagree, and only a moving capture settles it.

**Exact numbers:** 41.6 % → 0.4 % counts the whole run; counted from GPS loss it's **45.3 % → 0.45 %**, 200 runs, 0 hazardous. **The worst single run still escapes 18.5 %**, so per-run coverage is *not* met in sim. Every result was computed at the old factor, 5.33; at 5.68 each bound is 6.5 % wider, so coverage can only rise.

**What honesty costs:** after GPS loss the honest bound is under the 50 m limit only about 10 % of the time. It mostly says "don't navigate", which is right.

**If asked:**
- *How is the protection level calculated?* 5.68 × the largest horizontal standard deviation. Horizontal error is two-dimensional, so 10⁻⁷ per epoch needs √(2 ln 10⁷) = 5.68, not the 1-D 5.33. We caught that in our own code (ADR-0056). Call it "a bound under our model", not a certified protection level.
- *0 on real data, but how wide?* Wide, because the receiver heard one or two towers: the radius says exactly how little it knows, which is the point → backup *On real recordings, the bound stays honest*.
-->

---
class: topo-content
---

<div class="ask"><span>Mentor asks</span> call of 10 November</div>
<div class="kicker">What the Honeywell mentors asked for, and what we built</div>

# They asked. We built it, and measured it.

<div class="asks">
<div class="card"><div class="q">Start with location jumps, in the hundreds of metres</div><div class="a"><span class="num ok">1.1 s</span> to flag any jump from 20 m to 500 km; dangerous moments on a held 300 m jump <span class="num">5,244 → 3</span></div><div class="k">sim · 50 runs</div></div>
<div class="card"><div class="q">A satellite received that shouldn't be visible means spoofed</div><div class="a">Sky check built: <span class="num ok">59 of 59</span> faked reports flagged, <span class="num">0 of 120</span> genuine ones</div><div class="k"><strong>real</strong> recording, fake sky injected</div></div>
<div class="card"><div class="q">Tell spoofing from the signal power you have; detecting matters more than handling</div><div class="a">Flat-power cue in the same check; other aircraft's broadcasts warn <span class="num ok">48–78 s</span> early</div><div class="k">real + sim</div></div>
<div class="card"><div class="q">A heat map: green confident, red don't trust</div><div class="a">The track is coloured by confidence, beside <span class="num ok">ten</span> confidence readouts, live</div><div class="k">live panel</div></div>
<div class="card"><div class="q">Explain the calculation: the drifts, how you compensate, how long until</div><div class="a">Error budget term by term, matching the Monte Carlo; <span class="num ok">≥ 150 s</span> of good GPS needed first</div><div class="k">sim · 20 runs</div></div>
<div class="card"><div class="q">Assume the mission starts with GPS and loses it in one area</div><div class="a">Exactly our concept: learn the towers while GPS is good, then carry on and check GPS</div><div class="k">design</div></div>
<div class="card"><div class="q">A ground station is valid if you can communicate with it reliably</div><div class="a">Designed and simulated: worst moment <span class="num">677 → 332 m</span>, radius honest <span class="num ok">100 %</span></div><div class="k">sim · 50 runs</div></div>
<div class="card"><div class="q">Timing is second priority; focus on location</div><div class="a">Still delivered: <span class="num ok">0.44 µs</span> after 10 min; time drag caught in <span class="num">3.3 s</span></div><div class="k">sim · 50 runs</div></div>
</div>

<div class="foot">systems/mentor-qa.md · call of 2026-11-10 · systems/results.md · ADR-0034 · ADR-0038 · ADR-0041 · ADR-0020</div>

<!--
**3:05 → 3:30 · 25 s**

**Say:**

When we spoke to the Honeywell mentors, they told us what they care about, and we built each one. Start with location jumps in the hundreds of metres: caught in 1.1 seconds. Spot a satellite that shouldn't be visible: our sky check flagged every faked report on a real recording. Detecting matters more than handling: that's where we're strongest. A green-to-red heat map: it's on the panel. And they said the rationale matters as much as the result, so here's the calculation.

**Scores:** Problem understanding (1) · Evidence (5) · Answers (9) · every mentor ask in one place.

***

**Source:** the mentors' answers are in `systems/mentor-qa.md` and the call of 10 November. Paraphrase, don't quote word for word.

**If asked:**
- *How does the sky check work?* Published orbits tell us where each satellite should be; one received from below the horizon twice in a row is a hard cue; signal strengths that are suspiciously equal are a soft cue (§5.4 of D1).
- *Is 59 of 59 real?* A real 10-minute recording with a fake sky injected in software from 300 s; 120 genuine reports from real sessions, none flagged.
- *The ground station?* Backup *A ground station cancels tower clocks*.
-->

---
class: topo-light
---

<div class="ask"><span>Mentor ask</span> the calculation · handover · sim vs real</div>
<div class="kicker">Accuracy budget against Monte Carlo</div>

# The accuracy calculation, term by term

<p class="lede" style="max-width: 62ch">Five error terms, each grown from the moment GPS is lost and added up. The sum matches 20 simulated flights, so we know exactly which term to attack.</p>

<div class="cols cols-3 three" style="margin-top: 1.6rem; gap: 1.4rem">
<div class="card"><div class="bigstat">215 m</div><div class="statlabel">the biggest term: reflections, two minutes after GPS loss on realistic towers. Hearing more towers attacks it</div></div>
<div class="card"><div class="bigstat">150 s</div><div class="statlabel">of good GPS needed before the outage, to learn how each tower's clock drifts</div></div>
<div class="card"><div class="bigstat">0.73 m</div><div class="statlabel">real jitter of our radio, plus a hidden 8 m slow error we measured and now model</div></div>
</div>

<div class="foot">systems/accuracy-budget.md (seeds 0–19) · systems/verification.md (Sim validity) · ADR-0015 · ADR-0036 · lte-measured-noise (8892fca)</div>

<!--
**3:30 → 3:50 · 20 s**

**Say:**

The mentors asked for the maths: we built the error up term by term and it matches the Monte Carlo, with reflections the biggest piece. The filter needs two and a half minutes of good GPS to learn the towers first.

**Scores:** Technical approach & rigor (2) · Evidence (5) · mentor asks: explain the calculation, handover timing, how the sim aligns to reality.

***

**How we built the sim to be checked (ADR-0015):** we rejected pure simulation with literature values (judges couldn't tell if it transfers). Every model parameter is labelled *datasheet*, *literature* or *measured*, and the same comparison tool runs on sim and on real recordings.

**What the sim got wrong, found by measuring (ADR-0036):**
- The sim assumed 50 m of white noise per second. At rest the real white noise is **0.7 m on strong cells to 23 m on weak ones**, plus a slow error, median **8 m**, that the radio never reports.
- Real cells drop and reacquire often; the sim kept every track.
- The 8 m isn't the dongle or the tower clock: it stays in differences between two sectors of one site, where both cancel. That leaves multipath at a static antenna or our tracking loop; we haven't found which.

**What sets the accuracy today:** the radio reports only the fast part of its error, so the filter over-trusts towers. In sim that's worse than no towers. Learning each tower's noise on a study leg hopping 13 frequencies brings the worst second to 132 m. But the payload can't hop yet, so it's a study, not a result (ADR-0040).

**Other problems we hit:**
- *Heading at GPS loss:* a low-cost IMU can't hold position without a heading. We studied S-turns before the cut and a magnetometer, both opt-in in sim (ADR-0051).
- *The barometer:* our BMP180 drifted with temperature, −3 to +78 m on one real session, and made the filter refuse honest GPS for 262 of 601 s. Fix: when only the height fails, still use the horizontal fix (ADR-0045).

**If asked:**
- *Which terms?* Tower clock, multipath, error in the registered tower position, our clock, noise.
- *Why not a ground reference station?* Designed and simulated: it cancels tower clocks and takes the worst second to 332 m, but the parts weren't in hand → backup *A ground station*.
- *How do you close the gap?* In order: the honest filter on real data, heading at loss, a velocity source, LTE carrier phase. Each ends in a real measurement. No dates, and no promise of 25 m.
-->

---
class: topo-light
---

<div class="ask"><span>D2</span> quantitative results</div>
<div class="kicker">Headline targets · 50 simulated runs each unless marked real</div>

# The scoreboard

<table class="score big" style="margin-top: 0.8rem">
<thead><tr><th>Target</th><th>Result</th><th>Kind</th><th></th></tr></thead>
<tbody>
<tr><td>GPS jump flagged within 2 s</td><td class="r">1.1 s, 50 of 50 · 0 false alarms</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>No dangerous moment from a held jump</td><td class="r">0 with the guard · 17,042 without</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Radius always covers the error</td><td class="r">0 of 3,005 misses · standard filter 34 %</td><td><strong>real</strong></td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Cell towers carry the solution</td><td class="r">+1,961 m without them</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Time within 1.5 µs after 10 min</td><td class="r">0.44 µs · drift caught in 3.3 s</td><td class="muted">sim</td><td><span class="pill ok">49 of 50</span></td></tr>
<tr><td>Position within 25 m for 5 min</td><td class="r">10 m with clean tower signals</td><td class="muted">sim</td><td><span class="pill warn">Met, clean signals</span></td></tr>
</tbody>
</table>

<p class="small" style="margin-top: 0.8rem"><span class="tag">Trade-off</span> Our filter is never fooled by a jump and its radius always covers the error; the price is saying "don't trust me" a little more often. Full table: backup.</p>

<div class="foot">systems/results.md · analysis/results/headline (24aa5d1, seeds 0–49) · analysis/results/final (d66c929, ablation)</div>

<!--
**3:50 → 4:15 · 25 s**

**Say:**

The headline targets. Jumps caught in 1.1 seconds with zero false alarms, and with our guard zero dangerous moments. On real recordings our radius never understated the error. The towers carry the solution. Timing holds in 49 of 50 runs.

And with clean tower signals the filter holds 10 metres for the full five minutes, well inside the 25-metre target; the next step is hearing more towers. Every other target is in the backup.

**Point at:** down the green rows, then the amber one, and say what it needs: more towers heard.

**Scores:** Testing & results, limitations recognised (5) · D2 quantitative results · trade-offs (2).

***

**Read the rows carefully:**
- *Bound covers the error* is **real data** (0 of 3,005). In simulation it is 99.55 % over 200 flights with no dangerous moments; a few flights escape for part of the time, which is what more towers heard will close (slide 7).
- *Towers carry the solution* is **sim**. On real static sessions, towers made position *worse* than none so far (backup *real GPS cut*).
- *False alarms 0.0 / h* is the spoof alarms. The ADS-B crew warning had **1.94 false warnings per hour** in sim; a false warning costs a wider bound, not accuracy.
- *Timing:* our time bound is over-confident on the harder sets. The owners accepted that cost when they put our clock into the tower ranges (ADR-0047), and the fix is on the roadmap.

**Slow GPS drag, everything we tried (ADR-0037):**
- The filter's own gate: 0 of 50.
- Solution separation: 1 of 5 seeds, and 14 false alarms per hour.
- An IMU-only copy of the filter: no detection added.
- **Tower displacement monitor** (opt-in): 1 of 50 on the leg as flown (1–3 cells heard); 48 of 50 if every tower within 3 km is heard.
- With 13 carriers: 50 of 50, median 127 s, still over the 30 s target. The payload can't hop yet (ADR-0040).

**Wins to stress** (sim, → backup *In simulation, each defence pays*): any jump from 20 m to 500 km flagged in 1.1 s; the guard takes hazardous moments on a held jump from 5,244 to 3 per run, and a GPS replay's misleading moments from 1,995 to 0; every accuracy fix together takes the drone study leg from 12.5 km to 132 m.

**Why our pick:** the default follows a held jump (17,042 hazardous moments). The guard turns those into unavailable ones (14.9 → 19.1 %), and the honest bound adds coverage. → backup *What each defence costs*.

**The ground station** would be the best result for GPS loss (332 m, bound 100 %), but it follows a spoof without a guard and is sim only → backup *A ground station cancels tower clocks*.

**If asked:**
- *"Opt-in"?* Our pick is a filter you select by name; the default `ekf` stays as the reference until the owners switch it.
- *Why does the IMU add nothing?* Over a long outage a low-cost IMU without heading drifts too far to help.
-->

---
class: topo-content
---

<div class="ask"><span>D3</span> roadmap to a product · LEO layer</div>
<div class="kicker">Responsible by design, and what comes next</div>

# Safe by design, and the road to a product

<div class="cols" style="grid-template-columns: 1fr 1.3fr; gap: 1.6rem; margin-top: 1rem; align-items: start">
<div class="card">
<h3>Safe and legal</h3>
<ul class="roomy">
<li><strong>Never transmits:</strong> no spectrum risk</li>
<li><strong>Public signals only,</strong> never content</li>
<li><strong>Encrypted link;</strong> every source checked</li>
<li><strong>Advisory:</strong> it warns, it never steers</li>
</ul>
</div>
<div class="cols cols-3" style="gap: 0.9rem">
<div class="card"><span class="tag">Now</span><p>Detection and an honest radius, on real hardware</p></div>
<div class="card"><span class="tag">Next</span><p>Hear more towers; flight tests</p></div>
<div class="card"><span class="tag">Product</span><p>A box that warns the autopilot; LEO satellites as one more source</p></div>
</div>
</div>

<p class="lede" style="margin-top: 1.4rem; max-width: none">No spoof detector we found on sale checks GPS against cell towers. <strong>Every number here traces to a commit</strong>: 57 recorded decisions, 1,485 tests.</p>

<div class="foot">systems/safety.md · systems/roadmap.md (D3) · systems/results.md · ADR-0001 · ADR-0011 · ADR-0013 · ADR-0026</div>

<!--
**4:15 → 4:45 · 30 s**

**Say:**

It never transmits, so it can't interfere with anything. We decode only what's broadcast for everyone, the link is encrypted, and it advises; it never steers.

The product: a small receive-only box that warns the autopilot when GPS can't be trusted. Next: a better receiver to hear more towers, real flights, then low-orbit satellites. Every number here traces to a commit. Thank you, happy to take questions.

**Do:** stop on "thank you". Leave this slide up; press **O** to jump to a backup.

**Scores:** Safety & regulatory (6) · Impact & next steps (10) · Documentation (7) · D3 roadmap · mentor ask: LEO in the roadmap · spectrum interference: we never transmit.

***

**Safety choices:**
- *Receive-only (ADR-0001):* no transmit-capable radio on board (a HackRF was ruled out). Spoofing results come from software injection, which we say openly.
- *Flight:* ArduPilot was ruled out because it needed a new flight controller and rewiring days before judging (ADR-0028). The owners then chose Betaflight 4.5.5 on the flight controller we had (amendment, 2026-11-11). It's pilot-flown with a physical kill switch; RC loss disarms. A Wi-Fi gamepad bridge for tethered hover was built, then retired once we had a real RC transmitter (ADR-0029).
- *Privacy:* Wi-Fi identifiers hashed at capture; the panel hides where a recording was made.

**If asked about the path to market:**
- *Law:* we decode only signals meant for everyone, but we found no ruling on whether taking timing from them counts as "use" under s.9(2) of the Radiocommunication Act. We'd need a legal opinion before selling.
- *Patents:* the University of California holds LTE-navigation patents running to about 2038. We haven't assessed them; a freedom-to-operate check comes before any product.
- *Certification:* we found no standard for opportunistic navigation. RTCA SC-159 covers GNSS equipment. So it's advisory, with no certification claim.

**Roadmap logic (D3):** the order follows what limits us: honest filter on real data → heading at GPS loss → a velocity source → LTE carrier phase, each ending in a real measurement. Carrier phase reached under a metre on drones in the literature, but with a disciplined receiver clock we don't have, so we don't promise it. LEO comes after the towers work (ADR-0013).

**Competition, in our words:** we found no company selling cell-tower navigation for drones; the work is in universities. The nearest product is a 10 g receive-only Iridium board (a vendor figure). Don't compare with any Honeywell product.

**If asked:** *Who buys it?* Proposed: operators flying beyond line of sight, drone shows, defence trials. None has been approached yet.
-->

---
layout: default
class: topo-section
title: Backup
---

<div class="h-full flex flex-col justify-center">
  <div class="kicker">Backup slides for questions</div>
  <h1 style="font-size: 2.6rem">Backup</h1>
  <p class="lede">Full evidence: systems/results.md · prepared answers: systems/judge-questions.md</p>
</div>

<!--
**Backups for questions.** Press **O** for the overview and click a slide, or **G** and its number. Answer first, then show the slide.

**Rules for answers (systems/judge-questions.md has 24 prepared ones):**
- Never estimate a number on stage. "I don't have that number; it's in our results file."
- "We found none", never "nobody does this" or "first".
- "A bound under our model", never "certified".
- Say whether a number is sim or real. Accuracy and detection numbers are sim; the radio noise, the payload and the bound check on recordings are real.
- Never claim the payload hops carriers, or any real accuracy from towers.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Testing, evidence & results</div>
<div class="kicker">Backup · Every target, in full</div>

# Every target, and where it stands

<table class="score dense" style="margin-top: 0.5rem">
<thead><tr><th>Target</th><th>Result</th><th>Kind</th><th></th></tr></thead>
<tbody>
<tr><td>Location jump ≥ 20 m flagged within 2 s</td><td class="r">1.1 s, 50 of 50 runs</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>No hazardous moment from a held jump</td><td class="r">0 with the guard · 17,042 without</td><td class="muted">sim</td><td><span class="pill ok">Met, opt-in</span></td></tr>
<tr><td>Bound covers the error after GPS loss</td><td class="r">0 of 3,005 checks missed · default 34 %</td><td><strong>real</strong></td><td><span class="pill ok">Met, opt-in</span></td></tr>
<tr><td>GPS time drift 50 ns/s within 60 s</td><td class="r">3.3 s median, 50 of 50</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>≤ 1 false alarm per hour</td><td class="r">0.0 per hour; 0 spoof alarms in 40 h clean</td><td class="muted">sim + real</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Cell towers carry the solution</td><td class="r">without LTE +1,961 m · barometer +78 m · IMU +0 m</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Crews warned of interference on approach</td><td class="r">50 of 50, from other aircraft's ADS-B, 48–78 s early</td><td class="muted">sim</td><td><span class="pill ok">Met</span></td></tr>
<tr><td>Time ≤ 1.5 µs after 10 min without GPS</td><td class="r">0.44 µs mean · 1.55 µs worst run</td><td class="muted">sim</td><td><span class="pill ok">49 of 50</span></td></tr>
<tr><td>Approach position within 556 m</td><td class="r">crew warning verified 50 of 50 · position awaits real airport towers</td><td class="muted">sim</td><td><span class="pill warn">Next</span></td></tr>
<tr><td>Position ≤ 25 m for 300 s after GPS loss</td><td class="r">10 m with clean tower signals · 105 m with every fix</td><td class="muted">sim</td><td><span class="pill warn">Met with clean signals</span></td></tr>
<tr><td>Slow 2 m/s GPS drag within 30 s</td><td class="r">50 of 50 with carrier hopping, 127 s · not on one carrier</td><td class="muted">sim</td><td><span class="pill warn">Caught, slower</span></td></tr>
</tbody>
</table>


<div class="foot">systems/results.md · analysis/results/headline (24aa5d1, seeds 0–49) · analysis/results/final (d66c929, ablation)</div>

<!--
**Use when:** a judge wants every target, including the drag and approach rows.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Problem understanding · Documentation</div>
<div class="ask"><span>Mentor ask</span> requirements tied to the use cases (D1)</div>
<div class="kicker">Backup · Use case → requirement → measure</div>

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
**Use when:** "how do requirements tie to the use cases?" or "where's the D1 trace?"

**Say:** Each use case maps to numbered requirements, each with a success measure we test in the scoreboard. REQ-06, towers carry the solution, is tested by removing them. REQ-07, receive-only, is a design rule checked in hardware and code.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Technical approach & rigor</div>
<div class="ask"><span>Mentor ask</span> several ways to show confidence</div>
<div class="kicker">Backup · The real panel, 40 s after GPS loss</div>

# Ten readouts, one answer: do not navigate on this

<div class="cols" style="grid-template-columns: 2.3fr 1fr; gap: 1.2rem; margin-top: 0.2rem; align-items: start">
<div class="annot">
  <img src="/proof/panel-unsafe.jpg" alt="The operator panel 40 s after GPS loss, UNSAFE">
  <span class="pin" style="left: 96%; top: 8%">1</span>
  <span class="pin" style="left: 65.3%; top: 40%">2</span>
  <span class="pin" style="left: 100.6%; top: 36.6%">3</span>
  <span class="pin" style="left: 65.3%; top: 26%">4</span>
  <span class="pin" style="left: 65.3%; top: 30.5%">5</span>
  <span class="pin" style="left: 65.3%; top: 94%">6</span>
  <span class="pin" style="left: 66.6%; top: 83%">7</span>
  <span class="pin" style="left: 42%; top: 28%">8</span>
  <span class="pin" style="left: 22%; top: 79%">9</span>
  <span class="pin" style="left: 65.3%; top: 66%">10</span>
</div>
<ol class="legend tight">
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
**Use when:** "explain the readouts" or "how would a pilot use this?"

**Say:** Every readout answers one question: can I navigate on this? Here, 40 s after GPS loss, all ten say no: the bound is 895 m, about 18 times the 50 m limit. Readout 3 gives a crew the same thing in their terms, ANP against RNP. Alerts latch until acknowledged, so a short red isn't missed.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Testing, evidence & results</div>
<div class="kicker">Backup · Is the confidence true? Sim truth and real recordings</div>

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
**Use when:** "how is the protection level calculated?" or "how do you know it's honest?"

**Say:** HPL = k × the largest position standard deviation. Horizontal error is two-dimensional, so a 10⁻⁷ risk per epoch gives k = √(2 ln 10⁷) = 5.68. We had 5.33, the one-dimensional value, and fixed it ourselves (ADR-0056). Every dot above the diagonal is a moment the error escaped the bound: 41.6 % before, 0.4 % after, none hazardous. On real recordings with GPS cut: 34 % of checks under the error, against 0.

**Be ready for:** the 10⁻⁷ risk is our proposal (TBC), not a certified allocation.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Technical approach & rigor</div>
<div class="ask"><span>Mentor ask</span> explain the calculation · handover timing</div>
<div class="kicker">Backup · Accuracy budget against Monte Carlo</div>

# The accuracy calculation, and how long GPS must be good first

<div class="cols cols-2" style="margin-top: 0.7rem; gap: 1.4rem">
<figure class="fig">
  <img src="/proof/budget-vs-mc.png" alt="Accuracy budget against Monte Carlo on the clean and realistic routes">
  <figcaption><strong>Budget vs Monte Carlo.</strong> Each error term (tower clock, multipath, told tower position, our clock, noise) grown from the moment GPS is lost, summed, and checked against 20 runs. Clean route: inside the 50 m fallback. Realistic towers: hundreds of metres; multipath alone is 215 m at 2 min.</figcaption>
</figure>
<figure class="fig">
  <img src="/proof/handover-clean.png" alt="95 % error against how long GPS was good before loss">
  <figcaption><strong>Handover timing.</strong> 95 % error against how long GPS was good before loss. Clean route. The filter that learns tower clock drift (orange) needs ≥ 150 s of good GPS to stay under 50 m (read off its budget curve); the others (blue, green) do not depend on it. On realistic towers, hearing more towers matters more than a longer wait (systems/accuracy-budget.md).</figcaption>
</figure>
</div>

<div class="foot">systems/accuracy-budget.md · analysis/accuracy_budget.py (f3fc928 / f736bda, seeds 0–19) · ADR-0034</div>

<!--
**Use when:** "walk me through the accuracy calculation" or "how long does GPS need to be good first?"

**Say:** Left: each error term grown from the moment GPS is lost, summed, against 20 Monte Carlo runs. The budget predicts the simulation, so we know exactly which term to attack: on realistic towers, multipath alone is 215 m at two minutes. Right: the filter that learns tower clock drift needs at least 150 s of good GPS to stay under 50 m on the clean route; the other filters don't depend on it. On realistic towers, hearing more towers matters more than a longer wait.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Testing, evidence & results</div>
<div class="ask"><span>Mentor ask</span> how the sim aligns to reality</div>
<div class="kicker">Backup · Simulation against reality</div>

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
<tr><td>Tower clocks, multipath, barometer</td><td class="small">literature</td><td><span class="pill warn">literature</span></td></tr>
<tr><td>Spoofing, jamming</td><td class="small">injected in software, also into real recordings</td><td><span class="pill warn">injected</span></td></tr>
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
**Use when:** "how does the simulation line up with reality?"

**Say:** We set the models from measurements wherever we could: IMU from an overnight bench capture, LTE noise from 15 real captures. The table says honestly what's still a placeholder. The same comparison tool runs on sim and real: the sim's LTE error was white, 49 m; the real one is smooth, 21 m. The radio reports a σ 1.3–2× too big for the white noise and says nothing about the slow error, so the honest-bound filter carries that error as a state.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Testing, evidence & results</div>
<div class="ask"><span>Challenge</span> position <em>and</em> timing</div>
<div class="kicker">Backup · UC-03 timing · sim, 50 runs</div>

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
**Use when:** "what about timing?" (the challenge asks for position *and* timing)

**Say:** Ten minutes after GPS loss, the mean time error is 0.44 µs; 49 of 50 runs are within 1.5 µs and the worst is 1.55. A GPS time drift of 50 ns/s is flagged in 3.3 s median. The stated 1σ clock bound covers the error 99.5 % of the time. On real hardware, the payload's clock follows the GPS timing pulse to 769 ns. Towers take their time from GPS, so they can contradict GPS time but never confirm it.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Technical approach · trade-offs</div>
<div class="kicker">Backup · Choosing the filter · 15 attacks × 50 runs each, simulation</div>

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
**Use when:** "why that filter?" or "what are the trade-offs?"

**Say:** 15 attacks, 50 runs each. The default follows a held jump: 17,042 hazardous moments. The guard turns those into unavailable ones, 14.9 → 19.1 % of the time. Our pick adds the honest bound: best accuracy of the payload filters and a bound that always covers the error. Solution separation is never wrong because it never answers. A ground base station helps outages but follows the spoofer without a guard, and it's sim only.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Testing, evidence & results</div>
<div class="ask"><span>D2</span> quantitative results</div>
<div class="kicker">Backup · What the defences bought · simulation, 50 runs each unless marked</div>

# In simulation, each defence pays

<div class="cols cols-3 wins" style="margin-top: 0.6rem">
<div class="card"><div class="bigstat">1.1 s</div><div class="statlabel">to flag a GPS jump, every size from 20 m to 500 km</div></div>
<div class="card"><div class="bigstat"><span class="bad">5,244</span> → <span class="ok">3</span></div><div class="statlabel">hazardous moments per run on a held 300 m jump, with the guard</div></div>
<div class="card"><div class="bigstat"><span class="bad">1,995</span> → <span class="ok">0</span></div><div class="statlabel">misleading moments per run from replayed GPS (meaconing), with the guard</div></div>
<div class="card"><div class="bigstat"><span class="bad">45 %</span> → <span class="ok">0.45 %</span></div><div class="statlabel">error above the bound after GPS loss, honest filter, 200 runs, 0 hazardous</div></div>
<div class="card"><div class="bigstat"><span class="bad">12.5 km</span> → <span class="ok">132 m</span></div><div class="statlabel">drone study leg, every fix together (worst second, 0–300 s); 105 m on our measured radio noise</div></div>
<div class="card"><div class="bigstat">3.3 s</div><div class="statlabel">median to catch GPS time drifting 50 ns/s, 50 of 50; 0.44 µs after 10 min</div></div>
<div class="card"><div class="bigstat">48–78 s</div><div class="statlabel">warning to a crew from other aircraft's ADS-B, before reaching the interference, 50 of 50</div></div>
<div class="card"><div class="bigstat">59 / 59</div><div class="statlabel"><strong>real</strong> session, fake sky injected: every faked report flagged; 0 false in 120 real ones</div></div>
<div class="card"><div class="bigstat">0.0 / h</div><div class="statlabel">spoof false alarms on clean runs, every filter, every leg</div></div>
</div>

<p class="small muted" style="margin-top: 0.8rem">Simulated flights over the real Ottawa tower sites, with radio, motion-sensor and clock errors set from measurements on our own payload.</p>

<div class="foot">systems/results.md (b)–(d) · ADR-0038 · ADR-0039 · ADR-0041 · ADR-0046 · PR #247 · PR #262 · each number names its commit and seeds there</div>

<!--
**Use when:** "what did you achieve?", or when the misses come up.

**Say:**

And the defences pay off. [sweep left to right] Any GPS jump, from 20 metres to 500 kilometres, flagged in 1.1 seconds. Our guard cuts hazardous moments on a held jump from over 5,000 per run to 3, and a replayed-GPS attack to zero. Time drift caught in 3.3 seconds, crews warned up to 78 seconds early, and zero false alarms.

**Scores:** Testing & results (5) · D2 quantitative results · mentor ask: begin with location jumps.

***

**Be exact when pressed:**
- 132 m is a *study leg* hopping 13 carriers; the payload can't hop yet (ADR-0040). Without hopping, learned noise alone gives 2,474 m. On our measured radio noise the stack gives 105 m. Adding modelled track restarts: about 150 m.
- 45 % → 0.45 % is pooled over 200 runs; the worst single run still escapes 18.5 %.
- Learned noise on its own: median error 4,034 → 982 m and hazardous moments 320 → 0 (drone leg).
- Every number here is sim except the 59 / 59.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Technical approach · trade-offs</div>
<div class="ask"><span>D3</span> next layer</div>
<div class="kicker">Backup · Ground reference station · ADR-0020 · simulation only</div>

# A ground station cancels tower clocks, in simulation

<div class="cols" style="grid-template-columns: 1fr 1.1fr 1fr; gap: 1.1rem; margin-top: 0.7rem; align-items: stretch">
<div class="card small">
<h3>What it is</h3>
<p>A second receiver at a surveyed point hears the same towers. The laptop subtracts its readings from the payload's, so each tower's clock error cancels, as GBAS does for aircraft.</p>
<p>The station is its own fault hypothesis. It can't protect against a wide-area GPS time spoof, which pulls the station too.</p>
</div>
<div class="card small">
<h3>What it buys · long outage, 50 runs</h3>
<table class="score dense nw">
<thead><tr><th></th><th>default</th><th>+ station</th><th>+ IMU</th></tr></thead>
<tbody>
<tr><td>Error, worst second</td><td class="r">677 m</td><td class="r">500 m</td><td class="r ok">332 m</td></tr>
<tr><td>Bound covers error, worst run</td><td class="r">69 %</td><td class="r">93 %</td><td class="r ok">100 %</td></tr>
<tr><td>Time error, p95</td><td class="r">0.46 µs</td><td class="r">0.31 µs</td><td class="r ok">0.29 µs</td></tr>
</tbody>
</table>
<p style="margin-top: 0.5rem">Station faults during the outage (moved 50 m, 1 µs clock step, 60 s link loss): 0 hazardous.</p>
</div>
<div class="card small">
<h3>What it costs, and what's next</h3>
<p><span class="bad">Follows a held spoof jump in 49 of 50 runs</span> (68,537 hazardous moments against the default's 17,042): there is no guarded station filter yet.</p>
<p>Parts weren't in hand by the cut-off: our second radio is the ADS-B one, filtered to 1090 MHz, and the only GPS with a timing pulse is on the payload.</p>
</div>
</div>

<div class="foot">analysis/results/headline/summary.md (24aa5d1, seeds 0–49, realistic-with-base) · ADR-0020 (Amendment 2026-11-10) · ADR-0038</div>

<!--
**Use when:** "what about a ground station?", "differential?", "how would you fix the tower clocks?"

**Say:** We designed a ground reference station: a second receiver at a known point hearing the same towers. Subtract the two and the towers' clock errors cancel, the way GBAS works for aircraft. In simulation it's our best result for GPS loss: worst-second error 677 → 332 m with the IMU, and its bound covers the error 100 % of the time in the worst run. But it can't defend against spoofing yet: without a jump guard it follows a held jump in 49 of 50 runs. And we didn't build it: the parts weren't in hand by our cut-off.

**Why we chose this design over the alternatives (ADR-0020, ADR-0022):**
- *No station, learn tower clocks only:* no hardware, but the error grows with outage length and a lone tower clock can't be tested.
- *Station on hardware:* real evidence for the strongest part of the integrity story, $92.34 of parts, but set-up, a zero-baseline test and a new single point of failure. Planned, then deferred.
- *Station in sim only* (**where we are**): free, but no real evidence.

**Design details if pressed:**
- The base and payload share GPS time through their own PPS-disciplined clocks over a wired link: NTP gives only milliseconds, and 1 µs is 300 m.
- A zero-baseline test before each session: both side by side for 5–10 min to measure their receiver bias.
- The link to the laptop is authenticated; the station is a fault hypothesis of its own (a moved or spoofed base corrupts every correction).
- The sim assumes the link is always up with no latency; that's the mentors' condition ("if you can reliably communicate") taken as true, not shown.

**Next:** build it with a guard, and run the zero-baseline test. It's on the roadmap.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Safety, regulatory compliance & responsible execution</div>
<div class="kicker">Backup · Safety, regulation, privacy, security</div>

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
**Use when:** safety, regulation, privacy or cyber questions.

**Say:** Receive-only: there's no transmit path, and spoofing and jamming exist only as software injection, so we never touch the spectrum. We decode only fields meant for everyone, never content (Radiocommunication Act s.9(2)). Wi-Fi identifiers are hashed at capture. The link is authenticated and encrypted. Flights are pilot-flown with a kill switch and a checklist. It's advisory: it warns, it doesn't steer.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Impact, feasibility & next steps</div>
<div class="ask"><span>D3</span> roadmap to a product · LEO layer</div>
<div class="kicker">Backup · Roadmap · from hackathon to product</div>

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
<div><strong>Next to prove.</strong> The slow-error model on every tower, the drag check with more towers heard, and flight tests.</div>
</div>

<div class="foot">systems/roadmap.md (D3) · ADR-0013 (LEO in the roadmap) · hardware/bom.md</div>

<!--
**Use when:** "what's the product?", "is it feasible?" or "where does LEO fit?"

**Say:** Three steps. Now: detection and an honest bound, on real hardware. Next: earn the accuracy with heading, velocity, carrier phase and flight tests. Product: earn the integrity case with hours of tower data for fault rates, an on-board receiver and the warning to the autopilot, with LEO (Iridium PNT) as one more source. We found no spoof detector on sale that checks GPS against cell towers. The risks are on the slide; we name them.
-->

---
class: topo-content
---

<div class="rubric"><span>Rubric</span> Documentation quality</div>
<div class="kicker">Backup · Documentation · traceable, reproducible, decisions recorded</div>

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


<div class="foot">systems/README.md · systems/results.md · systems/quality.md · AGENTS.md</div>

<!--
**Use when:** "how would we reproduce this?" or documentation questions.

**Say:** D1 and D3 are in the repository with the requirements, risks, safety case and verification plan. 57 decision records, each with its options and trade-offs. Every result names its scenario or real session, its seeds and its commit, and one command regenerates every table and figure. 1,485 automated tests run before every merge.
-->

---
class: topo-light
---

<div class="rubric"><span>Rubric</span> Testing & evidence · limitations · next steps</div>
<div class="ask"><span>Mentor ask</span> how the sim aligns to reality</div>
<div class="kicker">Backup · Real captures · two 10-min static sessions outdoors, GPS as truth</div>

# In the field, the receiver is the bottleneck, not the method

<div class="cols" style="grid-template-columns: 0.9fr 1.25fr; gap: 1.4rem; margin-top: 0.5rem; align-items: start">
<div class="flex flex-col gap-3">
<div class="card" style="padding: 0.8rem 1rem"><div class="bigstat" style="font-size: 2.3rem">43 %</div><div class="statlabel">of the time our radio has <strong>one</strong> usable tower</div></div>
<div class="card" style="padding: 0.8rem 1rem"><div class="bigstat bad" style="font-size: 2.3rem">≤ 1.4 %</div><div class="statlabel">of the time it has <strong>two at once</strong>. A position fix needs <strong>three</strong>.</div></div>
<div class="card" style="padding: 0.8rem 1rem"><div class="bigstat ok" style="font-size: 2.3rem">0.73 m</div><div class="statlabel">range jitter when it does lock: the measurement itself is good</div></div>
</div>
<div>
<table class="score">
<thead><tr><th></th><th>Our payload today</th><th>What the method needs</th></tr></thead>
<tbody>
<tr><td>Radio</td><td>one 8-bit hobby SDR, $78 with antennas</td><td>a wider-band receiver, or several</td></tr>
<tr><td>LTE carriers heard</td><td class="bad">1</td><td class="ok">many: 13 in our study → 27 masts</td></tr>
<tr><td>Towers usable at once</td><td class="bad">1, rarely 2</td><td class="ok">3 or more</td></tr>
<tr><td>Weak cells</td><td>lose lock but keep reporting, km off</td><td>now distrusted in software</td></tr>
</tbody>
</table>
<div class="flex flex-col gap-2 small" style="margin-top: 0.9rem">
<div><span class="tag">Published</span> a research-grade receiver on a drone, 3 towers: <strong>8.15 m</strong> RMS (Shamaei, Khalife &amp; Kassas, 2018)</div>
<div><span class="tag">Our sim</span> clean ranges from 17 towers: <strong>10 m</strong> for the full 5 minutes</div>
</div>
</div>
</div>

<div class="foot">analysis/results/lte-gps-truth-20261111 (sessions 0151, 0040) · lte-measured-noise (8892fca) · ADR-0036 · ADR-0050 · systems/research.md §2 · hardware/bom.md</div>

<!--
**Use when:** a judge asks how it does on real data, or why the payload itself doesn't hit 25 m.

**Say:**

So why not on real data yet? The radio: one 8-bit hobby SDR on one LTE frequency. On our real captures it had one usable tower 43 % of the time, and two at once under 1.5 % of the time; a fix needs three. When it does lock, the range is good: under a metre of jitter.

A research-grade receiver on a drone has reached 8 metres with three towers. So our next step is hardware, not a new algorithm.

**Scores:** Testing & evidence, limitations recognised (5) · mentor ask: how the sim aligns to reality · Impact & next steps (10).

***

**Where the numbers come from (real, `lte-gps-truth-20261111`):**
- Session 0151: the best cell (PCI 92) is above the usable SNR (−8 dB, `TBC`) for 43.1 % of the capture, in runs up to 71 s; every other cell 0.6–6.6 %. Any two cells together: 0–1.4 % (81 epochs at most). Session 0040: best cell 18.9 %, pairs 0–1.5 %.
- Jitter: 0.73 m on strong cells (ADR-0036, 15 captures); 0.86 m on the best cell at 10 Hz in session 0151. On top of that sits a slow error, median 8 m, that the radio never reports.
- Weak cells (below −8 dB) lose lock but still report: errors spread 1.5–12.9 km while the records claim 21–31 m. ADR-0050 now gives each re-found track its own bias and tells the filter the measured noise.
- A 2-D fix with our clock unknown needs 3 towers at once.
- Published: Shamaei, Khalife & Kassas 2018 (IEEE TWC): a UAV receiver sampling one channel at 3 Msps, 8.15 m RMSE with three eNodeBs. Ours samples 1.92 Msps on a free-running dongle. Their hardware, not ours; say "published".

**If pressed, frame it like this:**
- "Bottleneck", not "only": reflections while moving are still unmeasured (our captures are static), and part of the early trouble was our own software believing the radio's 2 m claim. That's fixed (ADR-0050), and towers still don't beat no towers on real static data (364–595 m against about 1 m).
- The 10 m is the sim with ideal ranges: it shows the geometry is enough, not what our radio delivers today.

**If asked:**
- *Why not just buy a better radio?* We had a week and a CAD 170 budget for radios. The next steps are a second dongle or a hopping front end to hear more towers, then a GPS-disciplined clock for carrier phase.
- *How do you know the towers are the right ones?* Every heard cell matched one registered ISED site; that's consistent with the registry, not a confirmed identity.
-->

---
class: topo-light
---

<div class="kicker">Backup · real GPS cut</div>

# On real recordings, the bound stays honest

<div class="cols" style="grid-template-columns: 1.4fr 1fr; margin-top: 0.8rem; gap: 1.6rem">
<figure class="fig">
  <img src="/proof/real-cut-0040.png" alt="Error after a software GPS cut on a real session, by filter">
  <figcaption>A real static session with GPS cut in software, per filter. With one or two towers heard, the standard filters drift; the honest filter's radius covers its error throughout.</figcaption>
</figure>
<div class="small">
<p><strong>Why the default filter drifts:</strong> it believes the radio's own accuracy claim, which leaves out a slow 8 m error. Ours models that error.</p>
<p><strong>What the honest filter buys:</strong> 0 of 3,005 checks under the error. With one or two towers heard the radius is wide, exactly as it should be: it never claims more than it knows.</p>
<p><strong>Accuracy comes next:</strong> hear more towers at once, then moving captures and carrier phase (roadmap). In simulation, clean signals already give 10 m.</p>
</div>
</div>

<div class="foot">analysis/results/real-replay-256 · analysis/results/real-gps-cut-20261111 · results.md (a)</div>

<!--
**Use when:** "does it work on real data?"

**Say:** On real recordings, the part that matters most holds: our radius never understated the error, in 3,005 checks, where a standard filter did a third of the time. With our receiver hearing one or two towers, the radius is wide, as it should be. The standard filters drift because they believe the radio's own accuracy claim; ours models the slow 8 m error the radio hides. Accuracy comes with hearing more towers: in simulation, clean signals give 10 m.

**Numbers (two real static sessions, GPS cut in software, 300 s):** default filter 4,689 m and 857 m against 1.7 m and 6.9 m without LTE; `ekf-honest` 1,229 m and 492 m, with its bound above the error on all 3,005 checks (default: below it on 1,025). On two other real sessions, the default fed real records gave 11–22 km; telling it the measured noise and giving each new track its own bias brought that to 0.2–1.5 km (ADR-0050). Hearing more towers is the next step.
-->

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

<!--
**Use when:** "show us the hardware."

**Say:** Raspberry Pi 4B with the LTE and ADS-B radios on USB, a GPS HAT with the timing pulse, an IMU and a barometer. The antenna's ground plane mattered more than the antenna itself: 25 dB.

**Before the talk:** any slot still showing "Photo to add" → skip this slide.
-->

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

<!--
**Use when:** "do the cell towers actually matter?" (the challenge says communication signals should be primary)

**Say:** Paired runs, removing one source at a time. Without the LTE towers the error grows by nearly 2 km; without the barometer, by 78 m; without the IMU, nothing measurable. The communication signals carry the solution.
-->
