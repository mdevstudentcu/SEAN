# ICD-session: recorded session layout

- **Status:** Baselined 2026-11-08 (ADR-0007); `reference` block added 2026-11-09 (ADR-0020); SDR sidecar keys, `platform: static`, the Wi-Fi salt event and derived sessions added 2026-11-09 (#19, #23)

A session is one folder in `data/sessions/` (never committed):

```
data/sessions/20261110-1430-handheld-carleton/
├── meta.yaml          # who, where, platform, hardware, origin, notes
├── session.mcap       # all records (topics below), JSON encoding
├── sdr_a.cu8          # raw IQ, 8-bit unsigned interleaved (optional)
├── sdr_a.json         # sidecar: sample rate, centre freq, t_ns of sample 0, gain, buffer stamps (below)
├── sdr_b.cu8 / .json  # same for SDR B; band hops listed with their t_ns
└── camera.mp4         # optional, with camera.json (t_ns of first frame)
```

## Topics in `session.mcap`

| Topic | Record |
| --- | --- |
| `/meas/<source>` | `Measurement` (one topic per source, shared by both receivers; each record's `receiver` field says which made it, ICD-measurement) |
| `/nav/<estimator>` | `Estimate` (e.g. `/nav/baseline`) |
| `/truth` | `Truth` |
| `/mavlink/fc` | Flight-controller MAVLink, decoded to JSON |
| `/events` | Markers: free text (e.g. "GPS hidden from filter") plus fields, e.g. the `wifi salt` event with its `salt_id` |

## `meta.yaml`

```yaml
name: 20261110-1430-handheld-carleton
platform: handheld        # drone | handheld | vehicle | static | sim  (static: day-1 tests, the reference station)
origin_llh: [45.3876, -75.6960, 70.0]   # session ENU origin
simulated: false
scenario: null            # scenario file for sim sessions
seed: null                # sim random seed, so the run can be regenerated (REQ-10)
commit: <git sha>
hardware: [pi3bplus, pi-zero-2w, airnav-flightstick, nesdr-smart-v5, adafruit-gps-hat, mpu6050, bmp280, pi-camera]
reference: null           # or the reference station, when the session has `reference` records:
#   position_llh: [<lat>, <lon>, <h>]  # its antenna: WGS84 deg, deg, m
#   surveyed: true        # true: averaged GPS fix (ADR-0020); false: set by a sim scenario
#   sigma_m: TBD          # 1-sigma of position_llh, metres; TBD while unsurveyed; absent: unknown
notes: ""
```

`reference` is `null` when the session holds only payload records. A session with `reference` records must give its `position_llh`. `sigma_m` is a number of metres (≥ 0) or `TBD`; when it is absent the accuracy is unknown and a consumer must not assume one. `pnt.io.session` rejects any other `reference` key or value on write and on read.

## SDR sidecar (`sdr_<x>.json`)

One JSON object beside each `.cu8` (8-bit unsigned interleaved I/Q, as `rtl_sdr` writes it). The recorder (`pnt.payload.sdr`) writes it, and the LTE front end (`pnt.frontends.lte.capture`) reads it. Readers ignore keys they don't know.

| Key | Type | Required | Meaning |
| --- | --- | --- | --- |
| `sample_rate_hz` | number | yes | Nominal sample rate |
| `center_freq_hz` | number | yes, unless `hops` gives it from sample 0 | Tuned centre frequency |
| `t_ns` | int | yes | GPS ns of sample 0 on the payload's PPS-disciplined clock (chrony + PPS, ASM-04). The capture is **not** started on a PPS edge: `t_ns` is the recorder's estimate from the buffer stamps, and its bias (the minimum USB and pipe latency) is `TBD` |
| `gain_db` | number or null | no | Manual gain; null under automatic gain |
| `dongle` | string | no | Which receiver clock this is, e.g. `sdr_a` (default: the file stem) |
| `earfcn` | int | no | Overrides the EARFCN computed from the frequency |
| `hops` | list of `{sample_index` or `t_ns, center_freq_hz}` | no | Band hops; empty when there is one carrier |
| `gaps` | list of `[sample_index, n]` | no | Drops known exactly: `n` samples lost before `sample_index`. `rtl_sdr` never reports drops, so the recorder leaves this empty |
| `buffers` | list of `[sample_index, host_t_ns]` | no | Each USB buffer's first sample index and its host GPS-ns time (arrival minus the buffer's duration). Readers size drops from these |

The recorder also writes these, which are for people and the day-1 report, not for readers: `gain_mode`, `gaps_suspected` (drops it estimates from the stamps' latency floor), `rate_ppm_vs_host`, `t_ns_method`, `buffers_stamp`, `samples`, `device`, `command`, `stderr` and `ppm_correction`.

## Wi-Fi BSSID salt

BSSIDs are hashed at capture with a salt made fresh for each session (ADR-0011). The salt is never written anywhere. The session names it only by `salt_id` (8 hex characters of SHA-256 of a label plus the salt) in its `wifi salt` event on `/events`.

## Derived sessions

A tool that derives records from a session's raw files (e.g. `pnt frontend lte`) writes a **new** session folder (default `<session>-lte`) and never rewrites the original, so every derived number traces to an unchanged recording plus a commit (REQ-10). It may copy the original's records into the new folder, so that one `pnt replay` sees everything.
