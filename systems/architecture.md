# D1: Architecture

- **Status:** Draft, 2026-11-09 (#28). The humans own the final D1 and the deck; this is the technical draft they build from.
- **Audience:** engineers who build navigation products (mentor Q7, [`mentor-qa.md`](mentor-qa.md)). This file points to the source of each statement instead of restating it.
- **State described:** `origin/main` at `3759d95` plus this branch. Work in flight on other branches is named as such.

## What it is

A receive-only payload records signals of opportunity (LTE towers first), the GPS fix and PPS, an IMU and a barometer. A ground laptop fuses them into position and time, each with a protection level, and treats every source, GPS and the towers alike, as something that can fail ([ADR-0021](adr/0021-what-we-build-and-pitch.md)).

The integrity idea in one line: **learn the towers while GPS is trusted, then use them to keep position and time, catch GPS lying, and catch them lying.** Calibrated, grouped tower clocks are what make a tower testable at all (Jia, Khalife & Kassas 2023, in [`research.md`](research.md)).

## Key requirements by use case

| Use case | Requirements that drive the design | Proposed targets (`TBC`, [`plan.md`](plan.md)) |
| --- | --- | --- |
| [UC-01](use-cases.md) drone on an urban corridor | REQ-01 continuity, REQ-02 HPL, REQ-04 spoof detection, REQ-05 live display | T1, T4, T5 |
| [UC-02](use-cases.md) crewed approach into YOW | REQ-01, REQ-02 (alert limit for RNP 0.3), REQ-04 | T2, T4, T5 |
| [UC-03](use-cases.md) timing user | REQ-03 time holdover with an honest bound, REQ-04 time-spoof detection | T3, T4 |
| All | REQ-06 SoOP primary, REQ-07 receive-only, REQ-08 privacy, REQ-09 platform-agnostic payload, REQ-10 reproducible | — |

Requirements and their verification methods: [`requirements.md`](requirements.md), [`verification.md`](verification.md). The ranked attacks per use case: [`threat-model.md`](threat-model.md).

## Data flow

```mermaid
flowchart LR
  subgraph PAY["Payload: Pi 4B, receive-only (ADR-0001, ADR-0018)"]
    SDR["2 x RTL-SDR<br/>LTE PSS/SSS IQ"]
    GPS["GPS HAT<br/>NMEA + PPS"]
    SENS["MPU6050 IMU<br/>BMP280 baro"]
    REC["Recorder<br/>raw IQ + MCAP session"]
    SDR --> REC
    GPS --> REC
    SENS --> REC
  end
  subgraph BASE["Ground reference station: Pi 3B+ (ADR-0020)"]
    BSDR["RTL-SDR, same towers<br/>surveyed position, PPS"]
  end
  subgraph GND["Ground laptop (ADR-0002)"]
    SRC["Source: sim | replay | live<br/>(ADR-0004)"]
    FE["Front ends<br/>IQ to Measurement"]
    NAV["Estimator<br/>EKF, tower clocks"]
    INT["Integrity<br/>spoof detector, MHSS, base check"]
    OUT["Estimate<br/>position, time, HPL, TPL, flags"]
    DASH["Operator panel<br/>(ADR-0010)"]
    SRC --> FE --> NAV --> INT --> OUT --> DASH
  end
  REC -- "Wi-Fi: ZeroMQ, CurveZMQ (ADR-0009, ADR-0026)" --> SRC
  REC -- "session folder (ICD-session)" --> SRC
  BSDR -- "Ethernet, authenticated (ADR-0026)" --> SRC
  SIM["Simulator<br/>scenarios + attack library"] --> SRC
```

- **Record raw on board, process on the ground** ([ADR-0002](adr/0002-record-raw-process-ground.md)). The payload decodes nothing beyond what it must; the laptop runs front ends, estimation and integrity, live or from logs.
- **One record type.** Every observable is a `Measurement` ([ICD-measurement](icd/measurement.md), [ADR-0006](adr/0006-measurement-record.md)); its `receiver` field separates payload from base. Time is int64 GPS nanoseconds, positions ENU metres about the session origin ([ADR-0008](adr/0008-time-and-frames.md)).
- **Three interchangeable sources** ([ADR-0004](adr/0004-three-sources.md)): `sim`, `replay` and `live` yield the same stream, so every result on simulated data runs unchanged on a recording.
- **Sessions** are a folder with `session.mcap` and raw IQ sidecars ([ICD-session](icd/session.md), [ADR-0007](adr/0007-logs-mcap.md)).
- **Tower identity** comes from the ISED registry, an EARFCN/PCI scan and a mapper, and every association is a hypothesis with a fault prior ([ADR-0023](adr/0023-tower-identity.md)).

## Estimator

Code: [`src/pnt/nav/`](../src/pnt/nav/). The registry is `pnt.nav.ESTIMATORS`.

| Estimator | What it is | Role |
| --- | --- | --- |
| `baseline` | Deliberately simple reference filter | Control for every comparison |
| `ekf` | Position, velocity, receiver clock (offset, drift), and one block per tower clock | The main filter. Tower clocks are `independent` by default, or `calibrated` ([ADR-0022](adr/0022-tower-clock-model.md)): offset and drift per site under a shared builder term, learned only while GNSS is trusted and checked by independent evidence, and rolled back when GNSS is flagged |
| `ekf-base` | `ekf` differenced against the ground reference station | Tower clocks cancel in the difference ([ADR-0020](adr/0020-ground-reference-station.md)); falls back to `ekf` when the base is lost or excluded |
| `ekf-mhss` | `ekf` with a solution-separation monitor | HPL and exclusion from the fault hypotheses below (#82) |

In flight on other branches: IMU propagation (stage 2, #12) and further calibrated-clock work. The barometer carries the vertical (ASM-05).

## Integrity layer

Code: [`src/pnt/integrity/`](../src/pnt/integrity/) and the checks inside [`ekf.py`](../src/pnt/nav/ekf.py). Design: [`verification.md`](verification.md) (*Integrity monitor: solution separation*).

**GNSS-dependency tags** ([ADR-0024](adr/0024-gnss-dependency-tags.md), `integrity/dependency.py`). Every source is independent (barometer, IMU, VOR), GNSS-timed (LTE towers: geometry survives a GNSS fault, time does not) or GNSS-derived (ADS-B, our own GPS). Only independent evidence can confirm GNSS; tower time can refute it but never confirm it.

**Fault hypotheses**, grouped by what fails together, not by single measurement:

| Hypothesis | Covers | Monitored by |
| --- | --- | --- |
| Tower site | One site's clock jump, a wrong or moved registry entry, a rogue cell on a real PCI | MHSS site subset; base tower-clock monitor (`tower_fault`) |
| Network builder | One builder's timing source in holdover or captured: every site of that builder moves together | MHSS builder subset (from `tower_groups`) |
| Source layer | A whole sensor type (LTE, barometer) wrong | MHSS layer subset |
| GNSS common mode | GNSS plus every GNSS-derived or unclassified source | MHSS GNSS-free subset; spoof detector; time gate |
| Reference station | Base moved, base clock step, base link lost or forged | Base check in `ekf-base` (`base_excluded`); as an MHSS hypothesis, #107 |
| Hostile emitter | A located jammer used as a beacon | Its own hypothesis behind a promotion gate, sim only ([ADR-0025](adr/0025-hostile-emitter-beacon.md), #93) |

**Detectors and outputs:**
- **Spoof detector** (#83, #102): calibrated towers that disagree with the GNSS-steered position refute GNSS (`spoof_suspected`, `gnss_excluded`) and roll the tower clocks back.
- **Time gate:** GNSS time tested against our clock model (`time_spoof_suspected`).
- **Solution separation** (#82, #108): Brenner-style bank of EKF copies; HPL from the multiple-hypothesis bound of Blanch et al.; exclusion when the subset without the faulty group can serve alone.
- **Protection levels:** HPL and VPL from MHSS, or from the covariance in plain `ekf`; a time protection level (`integrity/protection.py`, our definition, no standard exists).
- **Report card:** time-to-alert, hazardous epochs and a resilience level mapped onto the DHS levels (`pnt.metrics`), per scenario, regenerated by `just results`.

**Where it stops.** Two faults in different groups at once are not covered. A wide-area time spoof that also captures the towers' timing is invisible to the towers by design. MHSS is only valid with honest subset covariances, which the `realistic` environment does not yet give (stated in [`verification.md`](verification.md)). The full gap list is in [`threat-model.md`](threat-model.md).

## Simulation and evidence

- **Attack library:** [`src/pnt/sim/attacks.py`](../src/pnt/sim/attacks.py) and [`scenarios/`](../src/pnt/sim/scenarios/): 74 scenarios, from base cases to the `easy`, `realistic`, `realistic-with-base` and `worst` environments crossed with the attack menu in `sets/_attacks.yaml`. Classified by `integrity/taxonomy.py` (TEXBAT-style).
- **Calibration to reality** ([ADR-0015](adr/0015-sim-calibrated-to-reality.md)): every model's status is in the *Sim validity* table of [`verification.md`](verification.md). Today every model is `placeholder`.
- **Results:** `just results` (report card), `just figures` (error after GPS loss, Stanford plot, ablation, timing holdover), `pnt plot` per session. Every figure names its scenario or session and commit (REQ-10).

## What is real and what is simulated

| Part | Today | Evidence it rests on |
| --- | --- | --- |
| Estimators, integrity, scoring, sim, plots | Code on `main`, tested | Simulation only |
| LTE front end (PSS/SSS tracking on RTL-SDR) | **Not built** (`src/pnt/frontends/` is empty; #21, #23) | — |
| Payload recorder and streamer on the Pi 4B | **Not built** (`src/pnt/payload/` is empty; #17, #19). Live source is a stub | — |
| Operator panel | **Not built** (#25, #90) | — |
| Ground reference station | Simulated; hardware on the BOM, assembly is #84 | Simulated |
| Real sessions | **None recorded yet** | — |
| Tower positions | Real (ISED registry, `data/reference/cells-ottawa.csv`) | Registry, two years old |
| Tower noise, clocks, multipath, dropouts | Literature or `TBC` | `placeholder` in *Sim validity* |
| LEO (Iridium) | Simulated from real orbits ([ADR-0013](adr/0013-no-iridium-hardware.md)), confirmed acceptable by the mentors | Sim |
| Jamming and spoofing | Software injection only ([ADR-0001](adr/0001-receive-only-payload.md), ASM-03) | Sim; injection into real sessions once they exist |

## Safety, security and regulation

- **Receive-only** payload and base; no transmit path in hardware or code (REQ-07, ADR-0001). Jamming and spoofing exist only in software.
- **Privacy:** only broadcast sync and system information is decoded; Wi-Fi BSSIDs are hashed at capture (REQ-08, [ADR-0011](adr/0011-privacy-at-capture.md)).
- **Ground links** are authenticated (MAVLink 2 signing, CurveZMQ) so forged records are dropped, not fused ([ADR-0026](adr/0026-ground-link-security.md), #89).
- **Flight:** indoor or handheld only near YOW, RC kill switch always fitted ([ADR-0012](adr/0012-flight-control-levels.md), ASM-06).
- Full list: [`safety.md`](safety.md).
