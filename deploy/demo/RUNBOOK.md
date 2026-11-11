# Demo runbook: the 5-minute judging demo

Written for a presenter who did not build this. The live part is about 90 s on the operator panel (four short simulations, one after the other), then 15 s of real towers on the terminal. Everything runs on the laptop alone, from committed scenarios at seed 0: no Pi, no network, no recorded file to lose. The same seed gives the same screen on every run, so the numbers below are what you will see.

Commands are in `deploy/demo/demo.sh`; `just demo <segment>` runs the same script.

**Say "simulated" out loud.** Every panel segment is a simulation with placeholder error models (`systems/verification.md`, *Sim validity*). The **SIM** chip, scenario, seed and estimator are on the panel's top bar.

## What the demo claims, and nothing more

- The panel tells the operator, within seconds, when the position can no longer be trusted, and shows it as a colour: green NOMINAL, amber DEGRADED, red UNSAFE.
- A 300 m GPS location jump is caught at the first jumped fix (this run: T+150.0, the jump's start).
- **Without the jump guard** (`ekf`) the filter takes the fake GPS back 27 s later and shows green while 300 m wrong. **With the jump guard** (`ekf-guard`, opt-in on `main`, ADR-0038 *Proposed*) the fake GPS stays refused, the panel stays red with a growing bound, and real GPS is taken back as soon as the spoofer stops.
- **In a simulation study** (one radio hopping 13 LTE carriers, ADR-0040, and LTE range noise learned by the filter, ADR-0039; neither is on the payload) the towers hold the position to tens of metres where today's setup is hundreds of metres off, at the same moment of the same outage. The panel still says UNSAFE there, because the bound is over the 50 m alert limit.
- The towers on the map are the real registered Rogers sites around Carleton, and we track real LTE cells from a real capture (`demo.sh real`).

**What it does not claim:** that we meet the position target without GPS (we don't: the error is hundreds of metres after a minute without GPS, below); that the guard is our default (it is opt-in: ADR-0038 keeps it off until the manoeuvre follow-up is done); that one seed is a statistic. 50-seed figures are under *Numbers you may quote*, with their source.

## Pre-flight

**The day before**

- [ ] Laptop on the commit to be shown, clean tree: `git status` empty, `git describe --always --dirty` noted.
- [ ] `deploy/demo/demo.sh check` prints `pre-flight passed` (it also checks that `ekf-guard` exists).
- [ ] Rehearse once end to end with a stopwatch (*Timing* below).

**T−30 min (at the venue)**

- [ ] Power connected; sleep and screen saver off; notifications off (Focus mode).
- [ ] Close other heavy jobs (Monte Carlo, IDEs): the panel needs one free core.
- [ ] Projector at 1920×1080, browser full screen (Ctrl-Cmd-F), zoom 100 %. The two charts and the Sources card need it: in a 1451×722 window they are below the fold.
- [ ] Keep the terminal off the projector during the panel segments. With a browser connected, each segment switch prints `ERROR: Cancel 1 running task(s), timeout graceful shutdown exceeded` there. It is harmless (the server closing the open stream).
- [ ] `deploy/demo/demo.sh check` → `pre-flight passed`. This also warms the Python caches.
- [ ] Warm-up: `deploy/demo/demo.sh outage`, wait for the panel, Ctrl-C.
- [ ] Open `analysis/pr-evidence/elshoubky-docs-28-demo-guard/` in Finder, ready for *If everything fails*.

**T−2 min**

- [ ] Terminal open in the repo, font large, `deploy/demo/demo.sh stage` typed but not run.
- [ ] Browser on a blank tab (the script opens the panel itself).

## Commands

| Segment | Command | What it runs |
| --- | --- | --- |
| Pre-flight | `deploy/demo/demo.sh check` | Python and panel imports, `lsof`, port 8050 free, the five scenarios load and their estimators exist, the two real sessions are there (`realcut`'s only matters for that segment) |
| **Stage sequence** | `deploy/demo/demo.sh stage` | GPS lost → towers study → jump without guard → jump with guard, on port 8050; **Enter** moves on, the page reconnects by itself, the last Enter stops |
| GPS lost | `deploy/demo/demo.sh outage` | `challenge-drone-outage`, seed 0, `ekf`, ×5 |
| Towers study | `deploy/demo/demo.sh towers` | GPS lost (as `outage`); Enter; then `challenge-drone-hop-outage`, seed 0, `ekf-learned-noise`, ×5, with the *simulation study* line on the panel |
| Location jump | `deploy/demo/demo.sh jump` | `challenge-drone-spoof-jump`, seed 0, `ekf`, ×10; Enter; then `challenge-drone-gps-return`, seed 0, `ekf-guard`, ×10 |
| Jump with guard only | `deploy/demo/demo.sh guard` | the second half of `jump` alone |
| Time spoof (Q&A only) | `deploy/demo/demo.sh time` | `challenge-timing-time-spoof`, seed 0, `ekf`, ×10 |
| Real towers | `deploy/demo/demo.sh real` | the cells heard in session `20261110-1623-static-out-e5060-lte`, each with the registered site it is consistent with |
| Real GPS cut (optional) | `deploy/demo/demo.sh realcut` | session `20261111-0845-live-laptop-gps`, GPS removed from 35 s, `ekf`, ×3, origin hidden; after `stage`, not in it (*Real GPS cut* below) |
| Live (bonus) | `deploy/demo/demo.sh live --connect payload=tcp://<pi>:5556 --origin <lat,lon,h>` | `pnt live --dash --estimator ekf` (*Live segment* below) |

Without the repo's `.venv`, set `PNT_PY=/path/to/python`. Real sessions live outside git: `PNT_SESSIONS=/path/to/data/sessions` if they are not in this checkout. `PNT_DEMO_OPEN=0` stops the script opening the browser.

Ctrl-C stops any segment and frees the port. Each switch may print `ERROR: Cancel 1 running task(s), timeout graceful shutdown exceeded`: that is the server closing the open stream, not a fault.

**Why the time spoof is not in the stage sequence:** the mentor asked us to focus on location before timing, and four location segments fill the 90 s. Run `demo.sh time` only if a judge asks about timing (*Time spoof* below).

## The stage sequence, second by second

**Wall** is seconds after pressing Enter on `deploy/demo/demo.sh stage`, from the timed runs below (±3 s). **T+** is the panel's own clock, top right: move on by watching T+, not a stopwatch. All values: simulation, seed 0, commit `9aed72b`.

Segment 1b was added after the Wall columns of segments 2 and 3 were measured: in today's sequence each of their Wall times is about 22 s later (the jump now starts at wall 46 s, not 24 s) (*Timing* below). T+ values are unchanged.

Where to look: the big coloured word top right (NOMINAL / DEGRADED / UNSAFE); **HPL** under it (our bound on the error) and **Error against truth** (the real error, known only because this is a simulation); the **HPL chart** bottom left (blue: HPL, green: true error, red dashed: the 50 m alert limit); **What is wrong now** and **Alerts** on the right.

### 1. GPS lost (wall 0–24 s): `challenge-drone-outage`, seed 0, `ekf`, ×5

| Wall | Panel | Say |
| --- | --- | --- |
| 0–4 s | Browser opens, panel connects. **SIM**, `challenge-drone-outage (seed 0)`, `estimator ekf` | "A simulated drone flying a loop over Carleton. The triangles are the real Rogers tower sites from the government registry." |
| 4–15 s (T+0–60) | Green **NOMINAL**, HPL about 7 m against the 50 m alert limit | "Green means: trust this position. HPL is our bound on the error, here 7 metres." |
| 15 s (T+61.8) | Amber **DEGRADED**: *GPS not in use* | "GPS is gone." |
| 16 s (T+64.8) | Red **UNSAFE**, alert latched *since T+64.8 s*; the dashed HPL circle grows on the map | "Within five seconds of the loss the panel turns red: do not navigate on this position. The alert stays on the list until someone acknowledges it." |
| 16–24 s (T+65–105) | HPL chart: blue above green. About T+100: HPL 865 m, error 335 m | "Honest number: 40 seconds without GPS we are over 300 metres off. What matters is that the bound, the blue line, stays above the real error on this run." |

**Press Enter when T+ passes 105.**

### 1b. Towers holding, a simulation study (wall 23–46 s): `challenge-drone-hop-outage`, seed 0, `ekf-learned-noise`, ×5

The same GPS loss as segment 1, on a setup the payload does not have: one radio hopping 13 LTE carriers (ADR-0040, a study leg) and LTE range noise the filter learns from the towers' own readings (ADR-0039, opt-in, PR #156 not merged). A line under the top bar says so for the whole segment: *Simulation study: 13 LTE carriers hopped, learned tower range noise (opt-in). Our payload cannot hop yet: it listens to one carrier.* (`--banner`). This segment has no pre-flight prediction line (`--no-preflight`: predicting it for 13 carriers adds about 4 s to the switch), so its HPL chart's time axis runs only to now.

NO DATA for 2–7 s; talk over the gap: "Same flight, same GPS loss. This one is a simulation study, and the line at the top says so: one radio hopping across thirteen LTE carriers instead of listening to one, and a filter that learns how far off each tower's readings are. Our payload cannot hop yet."

| Wall | Panel | Say |
| --- | --- | --- |
| 25–37 s (T+0–60) | Green **NOMINAL**, HPL about 7 m; the study line under the top bar; Sources: `lte` under *In use* | (Finish the gap line over the clean part.) |
| 37 s (T+61.8) | Amber **DEGRADED**: *GPS not in use* | "GPS is gone, as before." |
| 38 s (T+65.0) | Red **UNSAFE**, alert latched *since T+65.0 s* | — |
| 38–46 s (T+65–105) | Red **UNSAFE** throughout. *Error against truth* moves between 10 and 58 m (T+70: 28.5 m, T+90: 42.4 m, T+104.7: 39.2 m, T+105.3: 17.9 m); HPL 75–160 m (T+104.7: 140.3 m, T+105.3: 108.7 m); `lte 1.00` under *In use*; the HPL chart's green line stays under the blue | "Now the towers carry us. At this moment in the last run we were nearly 400 metres off; here, tens of metres. It is still red, and rightly: our bound is over 100 metres, above the 50-metre alert limit, so the panel still says do not navigate on this. Much better, not yet good enough." |

**Press Enter when T+ passes 105.**

On this run the HPL is above the true error at every epoch from T+60 to T+120. Over the first 45 s without GPS the error stays under 60 m, against 380–390 m at the same T+ in segment 1 (HPL about 980 m there). The map's Follow view is zoomed to the drone here, so no tower triangles are in it; *Area* shows them.

#### The towers segment if short of time

Skip it (press Enter as soon as it loads) and say only: "In a simulation study, with thirteen carriers and learned tower noise, which our payload cannot do yet, the position held to tens of metres instead of hundreds. Still flagged unsafe."

#### If a judge asks about the towers

- *Is this what the payload does?* No. The recorder listens to one carrier (EARFCN 2460) and cannot hop yet (ADR-0040); learned noise is opt-in and not merged (ADR-0039, PR #156). No hopped capture exists, and the learned-noise settings were tuned on simulated seeds.
- *How good is it over many runs?* "Across 50 simulated runs, at every second of the first five minutes without GPS, 95 % of the runs were within 132 metres. With today's setup that figure is 12.5 kilometres, and 2.9 kilometres with no towers at all. Neither our 25-metre nor the 50-metre fallback target is met." That is a 95th percentile across runs at each second (*Numbers you may quote*); never say "95 % of flights stay within 132 m".
- *Why is today's setup worse than no towers?* One carrier, and a front end that reports a 2 m range noise where the simulated truth is about 50 m: the filter believes bad ranges (#147). Learned noise is the fix for that; hopping adds towers.
- *Is seed 0 picked to look good?* No: every segment uses seed 0. Where Enter is pressed (45 s after the loss) seed 0 is mid-pack among 50 runs: rank 23 of 50 for the study (39.7 m, median 44.7 m), 24 of 50 for today's setup (381 m, median 385 m). Left running, it turns unflattering for the study: at 300 s after the loss it is the worst of the 50 (117 m, median 50 m). Seed 4 is typical for the study at 60, 120 and 300 s.

#### If the towers segment fails

`check` FAILs on `challenge-drone-hop-outage` or `ekf-learned-noise`, or the panel does not load: press Enter for the jump and say the *short of time* line above. Afterwards show `towers-3-same-time.png` next to `outage-late.png` from `analysis/pr-evidence/elshoubky-feat-266-towers-demo/`.

### 2. Location jump, without the guard (wall 24–48 s): `challenge-drone-spoof-jump`, seed 0, `ekf`, ×10

The page shows **NO DATA** for 3–6 s, then reconnects by itself; the top bar now says `challenge-drone-spoof-jump (seed 0) · estimator ekf`. Talk over the gap: "Now a spoofer: someone transmits fake GPS that puts us 300 metres east."

| Wall | Panel | Say |
| --- | --- | --- |
| 29–44 s (T+0–150) | Green **NOMINAL**, HPL about 7 m | "Same flight, GPS healthy." |
| 44 s (T+150.0) | Amber **DEGRADED**, *GPS rejected* latched *since T+150.0 s* | "The jump is caught at the very first fake fix: GPS rejected." |
| 45 s (T+154.8) | Red **UNSAFE**. HPL 415 m, error 97 m at T+174.6 | "Red: without GPS the bound opens up, as before." |
| 47 s (T+176.8) | **Green NOMINAL again**, HPL 7 m, *Error against truth* 300 m. The three alerts stay listed, *cleared … unacknowledged* | "But watch. Half a minute later this plain filter lets the fake GPS back in and follows it: green, a 7-metre bound, 300 metres wrong. That is the failure the jump guard fixes." |

**Press Enter when T+ passes 188.**

### 3. Location jump, with the guard (wall 48–76 s): `challenge-drone-gps-return`, seed 0, `ekf-guard`, ×10

NO DATA for 3–6 s again; the top bar now says `challenge-drone-gps-return (seed 0) · estimator ekf-guard`. **Point at `ekf-guard` on the top bar.** Talk over the gap: "Same flight, same attack, now with our jump guard. This time the spoofer stops at T+200."

| Wall | Panel | Say |
| --- | --- | --- |
| 53–68 s (T+0–150) | Green **NOMINAL**, HPL about 7 m | (Keep talking over the clean part; it is the same as before.) |
| 68 s (T+150.0) | Amber **DEGRADED**, *GPS rejected* | "Caught at the first fake fix, as before." |
| 69–73 s (T+154.8–199.9) | Red **UNSAFE** throughout. T+180.0: HPL 549 m, error 133 m. T+193.9: HPL 948 m, error 255 m | "This time the fake GPS stays out. We are flying on the barometer and our last known speed and heading, so the error grows, but the bound grows faster and the panel stays red. Nobody is told a wrong position is safe." |
| 73 s (T+200.0) | **Green NOMINAL**: real GPS back, HPL 13.5 m then 6.9 m, error 1.7 m, then between 0.1 and 3.6 m to T+220 (median 1.5 m). The three alerts stay listed, *cleared at T+199.9 s* | "The spoofer stops, real GPS comes straight back, and we are green and within a few metres again." |

On this run the HPL is above the true error at every epoch from T+10 to T+212 (and in segment 1 to T+105); in segment 2 it is below it from T+176.8, which is the failure shown.

**Press Enter when T+ passes 212** (stops the demo). A single amber *GPS rejected* may flash at T+218.4 for 0.2 s if you wait: one honest fix rejected by the normal gate, on both estimators; ignore it.

#### The jump segment in 25 seconds (if short of time)

Segment 2: "A spoofer moves GPS 300 metres. Caught at the first fake fix: red. But half a minute later the plain filter takes the fake GPS back: green, and 300 metres wrong." Segment 3: "Same attack with our jump guard: it stays red until the spoofer stops, then real GPS comes straight back. All simulated."

#### If a judge asks about the jump

- *How big a jump?* This one is 300 m; ADR-0038 tests 20 m to 500 km (below). The target is 20 m or more, flagged within 2 s in at least 95 % of runs (ADR-0034; the 20 m is `TBC`). In the sim a 20 m jump on the UC-01 route was detected in 20 of 20 runs with the guard (`ekf` 19 of 20), and a 25 m jump on the challenge legs was missed on 1 of 50 seeds (seed 17). A jump too small to latch is followed as before (ADR-0038 *Consequences*).
- *Why is the guard not on by default?* It can keep honest GPS out after a hard manoeuvre when GPS is the only position source (ADR-0038: 5 of 46 manoeuvre cases at 1 Hz GPS). Making it the default waits on that follow-up.
- *Why does the error grow to 255 m with the guard?* With GPS refused, the challenge leg has little else: the filter rejects nearly every tower reading (one seed: 5,374 of 5,383 before the spoof, #180; Sources shows `lte` under *Not in use*; #147). The guard trades accuracy for honesty: wrong but flagged red, instead of wrong and green.
- *Can you tell it is a spoof and not just bad GPS?* The panel says GPS *disagrees with the rest of the solution*. Telling a spoof from a fault by signal power or satellite geometry, as the mentor suggested, is not in this demo.

### Timing

| Part | Seconds |
| --- | --- |
| Pre-flight `check` | 0.7 |
| Stage sequence (Enter at T+105, T+105, T+188, T+212) | **90.5** and **90.4** |
| of which the towers study (Enter to Enter) | 22.8 and 22.7 |
| Stage sequence before the towers study (Enter at T+105, T+188, T+212) | 72.9 and 75.9 |
| Real towers | 0.4 to print, ~15 to talk |
| Real GPS cut (optional, Ctrl-C at T+115) | about 41 (first frame 2.3–3.5 s after Enter) |

Measured twice back to back on 2026-11-11 at `ec5da67`, a local commit never pushed, so not reproducible from the repository (the same change before its rebase onto `main` `8892fca`, now `9aed72b`; after the rebase only `demo.sh check`, `demo.sh real` and the two jump segments' outcomes were re-checked, not the timings), clean tree, macOS, this laptop, each run a fresh `demo.sh stage` (Python caches warm, not a rebooted laptop), load average 7.8 from two other jobs. Enter was pressed by a script reading the panel clock, not by hand, and no browser was open: a browser reconnects 0–3 s after each switch, which delays what is visible but not the sequence. The segment switch took 3.1–5.3 s. Event times on the panel clock agreed exactly between runs. A just-booted laptop's first Python start is slower (`TBD`, not measured): hence the warm-up. Re-time the stage sequence at the commit that will be shown (`TBD`).

With the towers study: measured twice back to back on 2026-11-11 at commit `66b4bd8`, clean tree, the same way (script on the panel clock, no browser), load average 2.4 and 1.4. Event times on the panel clock agreed exactly between runs, and with two earlier runs of the same code at load 5–7.6 (stage 96.8 and 94.2 s, towers study 25.0 and 23.8 s). The switch into the towers study took 1.7–1.8 s; with a headless Chrome on the page, the study was on screen 4.2 s after Enter (screenshot run). An earlier screenshot run at load average about 7 took 7.3 s.

## Numbers you may quote

Only these, with their source. Never present the seed-0 run above as a statistic.

| Claim | Number | Source |
| --- | --- | --- |
| A held 300 m jump on the drone leg is detected | 50 of 50 seeds | `analysis/results/jump-refusal/summary.md` (sim, seeds 0–49, commit `df46bce`) |
| Runs with hazardous epochs (error over 50 m while HPL under it), held 300 m jump, drone leg | `ekf` 49/50 seeds, mean 5,244 epochs per run; with the guard 3/50 seeds, mean 3 per run | same; ADR-0038 *Options* |
| Jump ended (at 300 s in the study, not 200 s as on stage): real GPS taken back | `ekf` 48/50 seeds, median 18.8 s after the end; with the guard 50/50, median 0.1 s | same, *Jump ended at 300 s* |
| Jump sizes 20 m to 500 km on the UC-01 route (realistic set, not the challenge leg): detected 1.1 s after the jump in every run but one 20 m jump; runs with hazardous epochs at 300 m | `ekf` 19/20, `ekf-guard` 0/20 | ADR-0038 *Consequences* (sim, seeds 0–19, `analysis/guard_jump_sizes.py` at `5a7a1c9`) |
| Drone leg, GPS lost: the 95th percentile of error across 50 runs at each second, worst second of the first 300 s | no LTE 2,909 m; today's setup (`ekf`, 1 carrier) 12,507 m; study (`ekf-learned-noise`, 13 hopped carriers) 132 m. The 25 m / 300 s and 50 m / 120 s targets are not met | `analysis/results/stacked-fixes/summary.md`, draft PR #247 (sim, seeds 0–49, branch `elshoubky/feat/218-stacked-fixes` at `31aaca1`). Hopping is a study leg (ADR-0040), learned noise opt-in (ADR-0039) |
| Cost of the guard: median error on the drone leg after refusing | 115 m at +30 s, 1.2 km at +120 s, flagged unsafe | ADR-0038 *Consequences* |

`ekf` on `challenge-drone-outage` over 50 seeds has hazardous epochs on some seeds (#170): do not say the panel never tells less than the truth.

## Time spoof (Q&A only): `deploy/demo/demo.sh time`

`challenge-timing-time-spoof`, seed 0, `ekf`, ×10: a static timing receiver whose GPS time drifts at 50 ns/s from T+150. About 15 s after start (T+151.2) the panel goes amber, *GPS time spoofing suspected*, latched. Say: "1.2 seconds after onset on this run, GPS time disagrees with our clock model, so we stop using it." At T+230.4 the *time PL over limit* alarm latches. Over 50 seeds the median detection is 3.3 s, worst 4.1 s (#170 at `e7bd988`). Screenshots: `elshoubky-docs-28-demo-rehearsal/time-*.png` (commit `8cea8cf`, before today's wording fix).

## Real towers (≈ 15 s): `deploy/demo/demo.sh real`

```
session 20261110-1623-static-out-e5060-lte (commit 4c8b0ab, real capture, 3 cells over 59 s)
registry match around Carleton (the session has no origin; Ottawa capture)

cell            records  per s  SNR dB  sigma m  registry
lte:5060:204        600   10.1    -1.0      4.3  not matched (unknown)
lte:5060:4          595   10.0    -3.2      5.4  eNB 102790, Vidéotron, <site>
lte:5060:492        594   10.0    -6.3      9.0  eNB 102790, Vidéotron, <site>
```

Say: "This is real: a 60-second capture with a low-cost RTL-SDR radio dongle. Three cells tracked ten times a second, two consistent with one registered tower site." Say "consistent with", never "identified": the match is made around Carleton, not around the receiver. The terminal prints the site name where `<site>` is shown here (left out of this file: with the cells heard it hints at where the capture was made).

**What the real segment can show today (2026-11-11):** this table, and optionally the real GPS cut below (#264). `demo.sh real` runs at `9aed72b` (checked after the rebase).

## Real GPS cut (optional, ≈ 40 s, after the stage sequence): `deploy/demo/demo.sh realcut`

Not part of `stage`. Run it after the stage sequence's last Enter (the port is free again): `deploy/demo/demo.sh realcut`, then **Ctrl-C at about T+115**. It replays the real session `20261111-0845-live-laptop-gps` (a laptop with the GPS HAT, barometer and IMU, standing still for 600 s; **no LTE, no towers**) on the panel, with every GPS fix from 35 s after the first record removed in software (the `outage` fault of `pnt replay --inject`, written by `analysis/real_gps_cut.py --dash-out` into a temporary folder that is deleted when the segment stops). Estimator `ekf` (with #241's fix), ×3. The panel runs with `--hide-origin`: no origin, no towers, only metres about the session's first fix (the session origin is that fix, 0.2 m away).

Say: "This one is a real receiver, not a simulation: a laptop GPS standing still for ten minutes. We remove GPS in software at T+35, and the panel turns red on its own within three seconds. No towers in this recording, so after the cut the filter has only the barometer and its last speed."

When the bound reaches kilometres, add: "The bound is honest but far too wide: the real error stays within a couple of metres because the receiver never moved, and the filter does not know that." Do not say the position stays within 2 m without GPS: a stationary receiver says nothing about a moving one.

**Wall** is seconds after pressing Enter on `deploy/demo/demo.sh realcut` (±1 s); **T+** is the panel clock. Measured as for the stage sequence (a script reading the panel stream, no browser, Ctrl-C at T+157): four runs on 2026-11-11, two at the uncommitted change and two at commit `a3190ce`, clean tree, macOS, this laptop, load average 3–7. Every panel-clock time and value below was the same in all four; first frame 2.3–3.5 s after Enter (slower under load).

| Wall | T+ | Panel | Say |
| --- | --- | --- | --- |
| 0–4 s | 0–2 | Script writes the cut copy (about 2 s), browser opens. **REPLAY** chip, `20261111-0845-live-laptop-gps-gps-cut-35s · estimator ekf`, ×3. One start-up alarm is already listed, *Protection level over the alert limit, since T+1.6 · cleared at T+1.9*: the filter's first second, ignore it | "Real recording, replayed three times faster." |
| 3–15 s | 2–34 | Green **NOMINAL**, HPL 20–24 m; *In use* `baro`, `gnss` | "GPS in use, green, bound about 20 metres." |
| 14–16 s | 36.1 | Amber **DEGRADED**, *GPS not in use* latched *since T+36.0*; `gnss` moves to *Not in use* | "GPS is gone." |
| 15–16 s | 37.6 | Red **UNSAFE**, HPL 52.9 m; the start-up alarm comes back *since T+37.4 (2 times)* | "Three seconds later it says: do not navigate on this position." |
| 16–42 s | 40–115 | Red throughout; the HPL circle and the blue line grow: T+64.6 HPL 598 m, error 1.3 m; T+94.6 HPL 1,558 m, error 2.1 m; T+115.2 HPL 2,375 m, error 1.3 m | The two sentences above about the bound. |

*Error against truth* on this segment is the distance to the **GPS fixes we withheld** (the panel says *the session's truth*), which scatter by 0.8 m RMS, 2.5 m at most, on their own. The stage cut is at 35 s so the cut lands 14 s in; it also keeps the pre-cut part free of the 1 s amber at T+49 (*GPS height rejected*: the BMP180 barometer drifts with temperature, and #241 keeps GPS's horizontal while its height is set aside).

**Fallback if it fails** (session missing: the script prints `realcut: session … missing` and exits non-zero, nothing else is affected; or the page never connects): show `realcut-2-cut.png` and `realcut-4-bound.png` from `analysis/pr-evidence/elshoubky-feat-264-real-cut-demo/` and say: "On a real ten-minute GPS recording, removing GPS turns the panel red within three seconds, and the bound stays far above the real error. This laptop is missing that recording, so here are the screenshots."

**The real numbers behind it** (`ekf`, cut at 35 s, error against each withheld fix, horizontal, metres relative to that fix; the fix nearest each instant, which is 0.46 s earlier: the fixes fall at x.54 s. The four instants are `analysis/real_gps_cut.py <session> --cuts 35 --estimators ekf --variants none --out <dir>`, which since #264's fix scores the nearest withheld fix within 0.5 s; re-run with that fix and the same values as before it. The whole-coast row is beyond the script's 300 s horizon: its `load`, `cut_gnss` and `score_cut(..., horizon_s=600)` over `nav.estimate("ekf", ...)`, not a committed command):

| After the cut | Error | HPL |
| --- | --- | --- |
| +30 s | 1.3 m | 579 m |
| +60 s | 2.1 m | 1,533 m |
| +120 s | 2.1 m | 4,189 m |
| +300 s | 7.4 m | 16,217 m |
| whole coast (565 s, 565 fixes) | max 13.6 m (at +561.5 s) | above the error at every fix; smallest ratio 216 |

Holding the last fix before the cut does as well or better on this stationary receiver (0.6, 0.6 and 1.2 m at +30/+60/+120 s; at most 2.8 m). With GPS left in (no cut), its horizontal is never refused on this session (0 of 6,002 epochs, with #241; without it #241 reports 273 of 601 s refused), while its height is set aside on 2,602 epochs (about T+49–50 and from T+201 on). The status turns unsafe because HPL passes the 50 m alert limit 3 s after the cut, not because the filter sees that it is wrong. `ekf` does not use the IMU (`ekf-imu` does); *In use* shows `baro` only after the cut.

## Fallbacks

| Failure | Sign | Do |
| --- | --- | --- |
| Port 8050 in use | `port 8050 is in use` | `lsof -iTCP:8050`, stop it; or `PNT_DEMO_PORT=8051 deploy/demo/demo.sh stage` |
| Page stuck on NO DATA after a switch | No reconnect after 10 s | Cmd-R. The segment keeps running; the page gets its history |
| A segment ended before Enter | Clock shows `finished` | Cmd-R does not restart it: press Enter for the next one |
| Enter pressed too early in segment 2 | Segment 3 already loading before green-and-wrong showed | Carry on; say the line over segment 3's gap and show `jump-3-followed.png` afterwards |
| Browser did not open | Nothing after 5 s | Open `http://127.0.0.1:8050` by hand |
| `ekf-guard` missing or `check` fails | `FAIL` lines | *If everything fails* below |
| Towers study fails (`check` FAIL on `challenge-drone-hop-outage` / `ekf-learned-noise`, or no panel) | — | *If the towers segment fails* (segment 1b) |
| Venue Wi-Fi down | — | Nothing needed: the demo uses no network |
| Laptop dies | — | Same screenshots from a teammate's laptop or the PR page |
| Questions about real position | — | One real session has a GPS fix and is shown only as metres about its first fix (*Real GPS cut*); never show its coordinates |
| `realcut` prints `session … missing` | Exits non-zero, nothing started | Say the fallback sentence under *Real GPS cut* and show its screenshots |

## If everything fails: 60 seconds on screenshots

Open `analysis/pr-evidence/elshoubky-docs-28-demo-guard/` in Preview (select all, Space, full screen) and step through. Say "these are screenshots of the simulation you would have seen live".

| Seconds | File | Say |
| --- | --- | --- |
| 0–8 | `outage-1-clean.png` | "A simulated drone over Carleton, real tower sites. Green: trust it, bound 7 metres." |
| 8–16 | `outage-2-lost.png` | "GPS lost: within five seconds, red. Don't navigate on this." |
| 16–24 | `outage-3-bound.png` | "40 seconds without GPS: 335 m off, bound 865 m. Honest about it." |
| 24–32 | `jump-1-flagged.png` | "A spoofer jumps GPS 300 metres: caught at the first fake fix." |
| 32–40 | `jump-3-followed.png` | "Without our guard, half a minute later the filter follows the fake: green and 300 metres wrong." |
| 40–50 | `guard-2-before-end.png` | "With the guard, the fake stays out: red, bound 948 m, so nobody trusts the 255 m error." |
| 50–60 | `guard-3-readmitted.png` | "The spoofer stops, real GPS is back, green, within a few metres." |

## Live segment (bonus): what it can show

Unchanged since 2026-11-10 except where noted. The 2026-11-10 run (`20261110-1759-live-laptop`) streamed 28 min over the authenticated link with 0 estimates: no GPS fix and no LTE records in the stream. Since then the HAT has an external active antenna and a PPS-locked fix (first full-suite session `20261111-0040-static-fullsuite`, on the Pi), so live can give estimates. Not yet run through `pnt live` on the panel.

- **The payload streams records, not IQ.** LTE runs afterwards on the laptop (`pnt frontend lte`) from a finished capture, so live shows no towers.
- **Origin and first fix.** Give `--origin lat,lon,h` (`demo.sh live` passes extra arguments through). `ekf` gives no estimate until the first GPS fix, so the panel shows NO DATA until then.
- **With a fix,** the panel shows a LIVE position with its HPL, the time PL and the sources in use. Pulling or shielding the GPS antenna has **not been rehearsed**: do not do it on stage unless it has been. A stream that stops turns the panel to NO DATA after 3 s (not seen live).
- **Risk:** judging is likely indoors, where the HAT may get no fix. Show live only if `pnt live` already shows estimates before going on stage; keys and network per `deploy/pi/RUNBOOK.md` (laptop hotspot, never venue Wi-Fi).

## Evidence

Headless Google Chrome at 1920×1080, panel served by `deploy/demo/demo.sh jump` and `deploy/demo/demo.sh outage` at commit `9aed72b`, clean tree. All **simulation**, seed 0. T+ and values as on screen. Files in `analysis/pr-evidence/elshoubky-docs-28-demo-guard/`.

| File | Scenario | Estimator | Panel time | Shows |
| --- | --- | --- | --- | --- |
| `outage-1-clean.png` | `challenge-drone-outage` | `ekf` | T+51.7 | NOMINAL, HPL 7.4 m, error 1.0 m; `lte` under *Not in use* |
| `outage-2-lost.png` | `challenge-drone-outage` | `ekf` | T+67.6 | UNSAFE latched T+64.8, HPL 87.4 m, error 19.0 m; *GPS not in use* |
| `outage-3-bound.png` | `challenge-drone-outage` | `ekf` | T+101.2 | UNSAFE, HPL 864.7 m above the 335.1 m error |
| `jump-1-flagged.png` | `challenge-drone-spoof-jump` | `ekf` | T+154.3 | DEGRADED, *GPS rejected* latched T+150.0, HPL 45.4 m |
| `jump-2-unsafe.png` | `challenge-drone-spoof-jump` | `ekf` | T+174.6 | UNSAFE, HPL 415.1 m above the 97.3 m error |
| `jump-3-followed.png` | `challenge-drone-spoof-jump` | `ekf` | T+189.6 | NOMINAL, HPL 6.9 m, error 300.4 m: the output follows the jump; alerts cleared at T+176.7, still listed |
| `guard-1-refused.png` | `challenge-drone-gps-return` | `ekf-guard` | T+180.0 | UNSAFE, HPL 549.2 m, error 133.0 m; GPS refused |
| `guard-2-before-end.png` | `challenge-drone-gps-return` | `ekf-guard` | T+193.9 | UNSAFE, HPL 947.6 m above the 254.6 m error, just before the spoofer stops at T+200 |
| `guard-3-readmitted.png` | `challenge-drone-gps-return` | `ekf-guard` | T+210.0 | NOMINAL, HPL 6.9 m, error 0.8 m: real GPS back; alerts cleared at T+199.9, still listed |

The 2026-11-10 screenshots in `analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/` (commit `8cea8cf`) still show the time spoof and the real-session panel (`real-dash-today.png`: NO DATA, no origin in a real session). Their wording predates the fix in `ade3bbc` (*GPS lost … towers*, *Low trust*).

Real GPS cut (#264): headless Google Chrome at 1920×1080, panel served by `deploy/demo/demo.sh realcut` (the same code as `a3190ce`, before it was committed). **Real session**, GPS removed in software at 35 s, `ekf`, origin hidden. Files in `analysis/pr-evidence/elshoubky-feat-264-real-cut-demo/`; each was checked by eye for coordinates, a map or a tower: none (only the ENU grid, the session name and relative metres).

| File | Panel time | Shows |
| --- | --- | --- |
| `realcut-1-before.png` | T+30.4 | NOMINAL, HPL 22.6 m, error 0.0 m; `baro` and `gnss` in use; the start-up alarm listed, cleared at T+1.9 |
| `realcut-2-cut.png` | T+36.8 | DEGRADED, *GPS not in use* since T+36.0, HPL 44.0 m, error 0.2 m; `gnss` not in use |
| `realcut-3-unsafe.png` | T+40.6 | UNSAFE since T+37.4, HPL 91.4 m, error 0.2 m |
| `realcut-4-bound.png` | T+100.6 | UNSAFE, HPL 1,784 m above the 2.3 m error against the withheld fixes |

Towers study (#266): headless Google Chrome at 1920×1080, panel served by `deploy/demo/demo.sh towers` at commit `66b4bd8`, clean tree. **Simulation**, seed 0. Files in `analysis/pr-evidence/elshoubky-feat-266-towers-demo/`.

| File | Scenario | Estimator | Panel time | Shows |
| --- | --- | --- | --- | --- |
| `outage-late.png` | `challenge-drone-outage` | `ekf` | T+105.3 | Today's setup: UNSAFE, HPL 991.5 m, error 385.6 m; `lte` under *Not in use* |
| `towers-1-banner.png` | `challenge-drone-hop-outage` | `ekf-learned-noise` | T+30.6 | The study line under the top bar; NOMINAL, HPL 6.9 m, error 0.8 m; `lte` in use |
| `towers-2-holding.png` | `challenge-drone-hop-outage` | `ekf-learned-noise` | T+80.6 | UNSAFE, HPL 74.6 m above the 38.6 m error; `lte` in use |
| `towers-3-same-time.png` | `challenge-drone-hop-outage` | `ekf-learned-noise` | T+105.3 | Same T+ as `outage-late.png`: UNSAFE, HPL 108.7 m above the 17.9 m error; `lte` in use |
