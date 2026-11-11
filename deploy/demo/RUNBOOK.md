# Demo runbook: the 5-minute judging demo

The live part of the pitch: 60–90 s on the operator panel, then 15 s of real towers on the terminal. It runs on the laptop alone, from committed scenarios at seed 0 (RSK-04, ADR-0004): no Pi, no network, no recorded file to lose. Commands are in `deploy/demo/demo.sh`; `just demo <segment>` calls the same script.

**What the demo claims, and nothing more:**

- The panel tells the operator, within seconds, when the position or the time can no longer be trusted. On this run (seed 0) the bound holds (protection level above the true error) through a GPS loss. Not on every run: over 50 seeds, `ekf` on `challenge-drone-outage` has hazardous epochs on 7 of 50 seeds (#170).
- A location jump is flagged and latched about a second after onset (1.1 s on 50 of 50 seeds, #180). A time spoof is flagged 1.2 s after onset on this run; over 50 seeds the median is 3.3 s and the worst 4.1 s (#170 at `e7bd988`).
- The towers on the map are the real registered sites around Carleton, and we track real cells from real captures. Each cell heard is *consistent with* a registered site: the match is made around Carleton, not around the receiver, so it is a hypothesis, not an identification.

**What it does not claim:** that we meet the position target without GPS (we don't: 321 m error 40 s into the outage below), or that a detected jump is refused (the demo runs plain `ekf`, whose output follows it; the opt-in `ekf-guard` that refuses it is not shown; see the jump segment).

Every number on screen is reproducible: scenario and seed on the panel's title bar, commit from `git describe`. All panel segments are **simulation** with placeholder error models (`systems/verification.md`, *Sim validity*); say "simulated" out loud.

## Pre-flight

**The day before**

- [ ] Laptop on the commit to be shown, clean tree: `git status` empty, `git describe --always --dirty` noted.
- [ ] `deploy/demo/demo.sh check` prints `pre-flight passed`.
- [ ] Rehearse once end to end, timed (below).

**T−30 min (at the venue)**

- [ ] Power connected; sleep and screen saver off; notifications off (Focus mode).
- [ ] Close other heavy jobs (Monte Carlo, IDEs): the panel needs one free core.
- [ ] Projector at 1920×1080 if possible. Browser full screen (Ctrl-Cmd-F), zoom 100 %.
- [ ] `deploy/demo/demo.sh check` → `pre-flight passed`. This also warms the Python caches.
- [ ] Warm-up: `deploy/demo/demo.sh outage`, wait for the panel, Ctrl-C.

**T−2 min**

- [ ] Terminal open in the repo, font large, `deploy/demo/demo.sh stage` typed but not run.
- [ ] Browser on a blank tab (the script opens the panel itself).

## Commands

| Segment | Command | What it runs |
| --- | --- | --- |
| Pre-flight | `deploy/demo/demo.sh check` | Python and panel imports, `lsof` present, port 8050 free, the three scenarios load, the real session is there |
| **Stage sequence** | `deploy/demo/demo.sh stage` | outage → jump → time on port 8050; Enter moves on, the page reconnects by itself |
| GPS lost | `deploy/demo/demo.sh outage` | `challenge-drone-outage`, seed 0, ekf, ×5 |
| Location jump | `deploy/demo/demo.sh jump` | `challenge-drone-spoof-jump`, seed 0, ekf, ×10 |
| Time spoof | `deploy/demo/demo.sh time` | `challenge-timing-time-spoof`, seed 0, ekf, ×10 |
| Real towers | `deploy/demo/demo.sh real` | the cells heard in session `20261110-1623-static-out-e5060-lte`, each with the ISED-registered site it is consistent with |
| Live (bonus) | `deploy/demo/demo.sh live --connect payload=tcp://<pi>:5556 --origin <lat,lon,h>` | `pnt live --dash --estimator ekf` (see *Live segment* below) |

Without the repo's `.venv`, set `PNT_PY=/path/to/python`. Real sessions live outside git: `PNT_SESSIONS=/path/to/data/sessions` if they are not in this checkout. `PNT_DEMO_OPEN=0` stops the script opening the browser.

Ctrl-C stops any segment and frees the port. Each switch prints `ERROR: Cancel 1 running task(s), timeout graceful shutdown exceeded` in the terminal: that is uvicorn closing the open stream, not a fault.

## The stage sequence, second by second

Times are wall seconds after pressing Enter on `deploy/demo/demo.sh stage`, as measured in the rehearsals below. **T+** is the panel's clock (top right). Move on by watching T+, not a stopwatch.

### 1. GPS lost (0–32 s): `challenge-drone-outage`, seed 0, ×5

| Wall | Panel | Say |
| --- | --- | --- |
| 0–4 s | Browser opens, panel connects. **SIM** chip, `challenge-drone-outage (seed 0)` | "A simulated drone circuit over Carleton. The towers are the real Rogers sites from the ISED registry." Click **Area** to show them, then **Follow**. |
| 4–15 s (T+0–60) | **NOMINAL**, HPL 6.9 m against the 50 m alert limit, time PL 29 ns | "GPS, barometer and towers. HPL is our bound on the error; the red dashed line is the alert limit." |
| 15.6 s (T+61.8) | **DEGRADED**, *GPS lost* caution | "GPS is gone." |
| 16.4 s (T+64.8) | **UNSAFE**, alert latched *since T+64.8 s*. HPL circle grows on the map | "Five seconds after the loss the panel says: do not navigate on this position. It stays latched until someone acknowledges it." |
| 16–24 s (T+65–100) | HPL chart: blue HPL above the green true error. T+100: HPL 829 m, error 321 m | "Honest number: 40 s without GPS we are 321 m off. The point is that on this run the bound stays above the error." If asked about other runs: over 50 seeds, 7 have hazardous epochs (#170); do not say the panel never tells you less than the truth. |
| 24–32 s (T+100–142) | Time PL rises; at T+138.9 the *time PL over limit* alarm latches. Clock error (green) still a few ns | "Time: the clock is still within ~20 ns of truth, but our bound is cautious and calls time unsafe after 79 s. We would rather warn early." |

Press Enter when T+ passes 142.

### 2. Location jump (32–56 s): `challenge-drone-spoof-jump`, seed 0, ×10

The panel shows **NO DATA** for 3–6 s while the next segment starts, then reconnects by itself (on T+20–25: the clean part is already drawn). Talk over the gap: "Now a spoofer: GPS jumps 300 m east."

| Wall | Panel | Say |
| --- | --- | --- |
| 38–51 s (T+25–150) | **NOMINAL**, HPL 6.9 m | "Same circuit, GPS healthy." |
| 51 s (T+150.0) | **DEGRADED**, *GPS rejected* latched *since T+150.0 s* | "The jump is caught at the first epoch: GPS rejected." |
| 51.5 s (T+154.8) | **UNSAFE**, HPL grows (399 m at T+174 against 93 m true error) | "Without GPS the bound opens up, as in the outage." |
| 54 s (T+176.7) | **NOMINAL** again, HPL 7 m, *error against truth* about 300 m; the three alerts stay listed, *cleared, unacknowledged* | **Say it plainly:** "Here is our open bug. After 27 s the filter lets the spoofed GPS back in and follows it: green, 7 m bound, 300 m wrong. The latched alerts are still on the panel, which is what an operator would see. The fix, refusing a flagged jump until GPS steps back, is in main as the opt-in `ekf-guard` (#191, ADR-0038, Proposed); this demo runs plain `ekf`." |

Press Enter when T+ passes ~190.

**Do not** swap in the plain `spoof-jump` scenario, where the output does not follow: it has six synthetic towers with 20 m noise, an easier world than the challenge leg. Showing it would be choosing the run that looks good.

**`ekf-guard` (#191, merged, opt-in):** `demo.sh` runs `ekf` only. Showing `ekf-guard` instead is the owners' call (ADR-0038 keeps the guard opt-in); not rehearsed. If chosen: `pnt sim challenge-drone-spoof-jump --seed 0 --estimator ekf-guard --dash --speed 10 --port 8050`, and look at T+177–190. Expected, not checked: no return to NOMINAL while the jump persists; GPS stays excluded and the status follows the HPL (UNSAFE, as in the outage). Then replace the last row's line with "caught at the first epoch and refused", retake `jump-3-followed.png`, and quote the paired numbers in `analysis/results/jump-refusal/summary.md` (seeds 0–49), not this one seed.

### 3. Time spoof (56–84 s): `challenge-timing-time-spoof`, seed 0, ×10

| Wall | Panel | Say |
| --- | --- | --- |
| 56–60 s | NO DATA for ~3 s, then **NOMINAL**: a static timing receiver | "A timing receiver, for a cell site or a substation. GPS time now drifts at 50 ns per second while positions look normal." |
| 74.5 s (T+151.2) | **DEGRADED**, *GPS time spoofing suspected* ALARM latched *since T+151.2 s* | "1.2 s after onset on this run: GPS time disagrees with our clock model, so we stop using it." |
| 75–82 s (T+152–230) | Timing chart: clock error (green) grows to 225 ns by T+220, time PL (blue) above it; *time PL over limit* at T+230.4 | "The clock still drifts with part of the attack, but the bound stays above the error and calls it unsafe at T+230." |

Press Enter to stop when T+ passes 232.

Over 50 seeds the jump is flagged in 1.1 s on 50 of 50 (#180's evidence on the challenge legs), and the time spoof in a median 3.3 s, worst 4.1 s (#170 at `e7bd988`, `ekf`, timing leg). On `challenge-drone-outage`, `ekf` has hazardous epochs on 7 of 50 seeds (#170). These were not re-run for this runbook: quote them with their source, and never present this one seed as a statistic.

### 4. Real towers (≈ 15 s): `deploy/demo/demo.sh real`

```
session 20261110-1623-static-out-e5060-lte (commit 4c8b0ab, real capture, 3 cells over 59 s)
cell            records  per s  SNR dB  sigma m  registry
lte:5060:204        600   10.1    -1.0      4.3  not matched (unknown)
lte:5060:4          595   10.0    -3.2      5.4  eNB 102790, Vidéotron, <site>
lte:5060:492        594   10.0    -6.3      9.0  eNB 102790, Vidéotron, <site>
```

Say: "This is a real 60 s capture with an RTL-SDR dongle (a NESDR SMArt v5): three cells tracked at 10 per second, two consistent with one registered site. No position yet: that capture had no GPS fix, so the filter never started." The match is made around Carleton, not the receiver (`cells.py --near`), so say "consistent with", never "identified". The terminal prints the registry site name where `<site>` is shown here (left out of this file: with the cells heard it hints at where the capture was made).

`analysis/lte_scan_table.py` (#192) gives the same comparison for many captures at once, from the `.cu8` files; `cells.py` reads one session's `/meas/lte` records, which `pnt frontend lte` has already written, so it prints in under a second on stage.

### Timing

| Part | Seconds |
| --- | --- |
| Pre-flight `check` | 0.9 |
| Stage sequence (Enter at +32, +24, +28 s) | 86.8 and 86.9 |
| Real towers | 0.3 to print, ~15 to talk |

Measured twice back to back on 2026-11-10 at commit `8cea8cf`, macOS 26.5.2, this laptop, Python caches warm, with two other Python jobs at 100 % CPU. Event times agreed within 0.5 s between runs. A just-booted laptop's first Python start is slower (`TBD`, not measured): hence the warm-up in the pre-flight.

## Fallbacks

| Failure | Sign | Do |
| --- | --- | --- |
| Port 8050 in use | `port 8050 is in use` | `lsof -iTCP:8050`, stop it; or `PNT_DEMO_PORT=8051 deploy/demo/demo.sh stage` |
| Page stuck on NO DATA after a switch | No reconnect after 10 s | Cmd-R. The segment keeps running; the page gets its history |
| A segment ended before Enter | Clock shows `finished` | Cmd-R does not restart it: Enter (stage) or rerun the segment command |
| Browser did not open | Nothing after 5 s | Open `http://127.0.0.1:8050` by hand |
| Python or panel broken | `check` fails | Show the evidence screenshots below (open the folder in Preview, full screen) and narrate the same lines |
| Venue Wi-Fi down | — | Nothing needed: the demo uses no network |
| Laptop dies | — | Same screenshots from a teammate's laptop or the PR page |
| Questions about real position | — | Real sessions have no GPS fix yet; say so (*Real sessions* below) |

## Real sessions on the panel: what is missing

`pnt dash data/sessions/20261110-1623-static-out-e5060-lte` today shows **NO DATA** with `Feed error: ValueError("real LTE records need the session's origin_llh")` (screenshot `real-dash-today.png`). Three things stand in the way, in order:

1. **No origin.** Every real LTE session has `origin_llh: null` (no GPS fix), and the registry lookup (`pnt.nav.cells.attach`) needs a point to match cells around.
2. **No estimate.** With an origin forced (Carleton), the `ekf` still gives 0 estimates on that session: it initialises from a first GNSS fix. The panel draws one frame per estimate, so it would still show nothing.
3. **No cell view.** The panel has no list of heard cells with rate and SNR; towers appear only on the map.

Smallest change that would show a real session's tracked cells: a listen-only feed in `pnt.dashboard.feed` for sessions with no GNSS records (or `--listen`), which runs no estimator and emits one frame per data second carrying the cells heard and their registered sites; `pnt dash --origin lat,lon,h` to place them (a public reference point, not the capture site); `app.js` drawing a frame with no position (it reads `f.pos` and `f.cov` unconditionally today) plus a small cells table. That touches `cli.py`, `feed.py`, `server.py` (`_point`), `app.js` and `index.html`, with tests: not small, so not done here. `deploy/demo/demo.sh real` shows the same information on the terminal today.

Done here: the panel now draws front-end-shaped and real LTE cells at their registered site (it noted emitters before the lookup, so the challenge legs showed no towers and "Towers heard: —").

## Live segment (bonus): what it can show

The 2026-11-10 run (`20261110-1759-live-laptop`) streamed 28 min over the authenticated link with 0 estimates: no GPS fix and no LTE records in the stream. Since then the HAT has its external active antenna and a PPS-locked fix (first full-suite session `20261111-0040-static-fullsuite`), so live can give estimates. Not yet run through `pnt live` on the panel.

- **The payload streams records, not IQ.** `pnt.payload.streamer` sends each `Measurement` the recorder writes plus a `meta` message once a second. The SDR's IQ goes only to `sdr_<x>.cu8` on the Pi's disk; the LTE front end runs afterwards on the laptop (`pnt frontend lte`), reading a finished capture.
- **Origin and first fix.** Without `--origin`, `pnt live` waits for the payload's session origin (its first 3D fix) for `--wait` 60 s, then exits with `no origin from the payload stream`. Give `--origin lat,lon,h` (`demo.sh live` passes extra arguments through). Even with an origin, `ekf` gives no estimate until the first GNSS fix arrives, so the panel shows NO DATA until then.
- **With a fix,** the panel shows a LIVE position with its HPL, the time PL and source trust. Pulling or shielding the GPS antenna has **not been rehearsed**: do not do it on stage unless it has been. In the sim proxy (GNSS + IMU only, `challenge-timing-outage`, seed 0) it gives *GPS lost* within 2 s and UNSAFE (HPL 52 m) 5 s after the loss; real timings `TBD`. A stream that stops turns the panel to NO DATA after 3 s (`STALE_S` in `app.js`; not seen live). No towers (no LTE in the stream), no truth.
- **Live LTE would need** either the front end running on the Pi over the growing capture (it memory-maps a finished file today; Pi 4B throughput `TBD`), or IQ streamed to the laptop (1.92 MS/s × 2 bytes = 3.84 MB/s, about 31 Mbit/s per dongle, over Wi-Fi and CurveZMQ; the record streamer drops messages by design, which would break tracking). Neither exists; in our estimate neither can be made demo-grade by Thursday.
- **Risk:** judging is likely indoors, where the HAT may get no fix at all. Treat live as a bonus shown only if `pnt live` already shows estimates before going on stage; keys and network per `deploy/pi/RUNBOOK.md` (laptop hotspot, never venue Wi-Fi).

## Evidence

Headless Google Chrome 157 at 1920×1080, panel served by `deploy/demo/demo.sh <segment>` at commit `8cea8cf`, clean tree. All simulation, estimator `ekf`, seed 0, except the last (replay of a real session). Files in `analysis/pr-evidence/elshoubky-docs-28-demo-rehearsal/`.

| File | Scenario / session | Panel time | Shows |
| --- | --- | --- | --- |
| `outage-1-clean.png` | `challenge-drone-outage` | T+51.6 | NOMINAL, HPL 6.9 m, 9 of 22 towers heard |
| `outage-2-lost.png` | `challenge-drone-outage` | T+66 | UNSAFE latched T+64.8, 5 s after the loss |
| `outage-3-time-pl-alert.png` | `challenge-drone-outage` | T+142.7 | HPL 2,386 m above the 896 m error; time PL alarm T+138.9; the real Rogers sites on the map |
| `jump-1-flagged.png` | `challenge-drone-spoof-jump` | T+152 | GPS rejected latched T+150.0 |
| `jump-2-hpl-grows.png` | `challenge-drone-spoof-jump` | T+173.9 | UNSAFE, HPL 399 m above the 93 m error |
| `jump-3-followed.png` | `challenge-drone-spoof-jump` | T+186.3 | NOMINAL, HPL 7.4 m, error 299.5 m: the output follows the jump (#184); alerts still listed |
| `time-1-flagged.png` | `challenge-timing-time-spoof` | T+153 | time spoof alarm latched T+151.2 |
| `time-2-time-pl-alert.png` | `challenge-timing-time-spoof` | T+233 | clock error below the time PL; time PL alarm T+230.4 |
| `real-dash-today.png` | `20261110-1623-static-out-e5060-lte` (real) | — | NO DATA: no origin in a real session |
