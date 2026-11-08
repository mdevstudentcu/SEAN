# ICD-session: recorded session layout

- **Status:** Baselined 2026-11-08 (ADR-0007)

A session is one folder in `data/sessions/` (never committed):

```
data/sessions/20261110-1430-handheld-carleton/
├── meta.yaml          # who, where, platform, hardware, origin, salt id, notes
├── session.mcap       # all records (topics below), JSON encoding
├── sdr_a.cu8          # raw IQ, 8-bit unsigned interleaved (optional)
├── sdr_a.json         # centre freq, sample rate, gain, t_ns of first sample (PPS-aligned)
├── sdr_b.cu8 / .json  # same for SDR B; band hops listed with their t_ns
└── camera.mp4         # optional, with camera.json (t_ns of first frame)
```

## Topics in `session.mcap`

| Topic | Record |
| --- | --- |
| `/meas/<source>` | `Measurement` (one topic per source) |
| `/nav/<estimator>` | `Estimate` (e.g. `/nav/baseline`) |
| `/truth` | `Truth` |
| `/mavlink/fc` | Flight-controller MAVLink, decoded to JSON |
| `/events` | Free-text markers (e.g. "GPS hidden from filter") |

## `meta.yaml`

```yaml
name: 20261110-1430-handheld-carleton
platform: handheld        # drone | handheld | vehicle | sim
origin_llh: [45.3876, -75.6960, 70.0]   # session ENU origin
simulated: false
scenario: null            # scenario file for sim sessions
commit: <git sha>
hardware: [pi4b, esp32-s3, nesdr-smart-v5 x2, neo-6m, bmi160, bme280]
notes: ""
```
