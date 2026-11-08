# ICD-measurement: pipeline records

- **Status:** Baselined 2026-11-08 (ADR-0006)
- **Owners:** front-ends/capture (SW 1) ↔ nav/integrity (SW 2). Changes need both.
- **Code:** `src/pnt/core/measurement.py` (this file wins if they disagree)

Three record types flow through the pipeline. All are msgspec structs, encoded as JSON in MCAP and msgpack on the live stream.

## Measurement: one observable from one source

| Field | Type | Meaning |
| --- | --- | --- |
| `t_ns` | int64 | GPS time of validity, nanoseconds since the GPS epoch (ADR-0008) |
| `source` | str | Which sensor or signal family produced it (registry below) |
| `kind` | str | What the value is (registry below) |
| `emitter` | str | Transmitter ID, or `""` for self-contained sensors. Cell: `lte:<earfcn>:<pci>`; aircraft: `adsb:<icao>`; VOR: `vor:<ident>`; Wi-Fi: `wifi:<hashed bssid>` |
| `value` | tuple[float] | The observable, in the units of its kind |
| `sigma` | tuple[float] | 1-σ uncertainty per element, same units; the front-end's own estimate |
| `meta` | dict | Optional extras: SNR, emitter position (`emitter_enu` or `emitter_llh`), raw-file offset, flags |

### `source` registry

`gnss`, `imu`, `baro`, `lte`, `nr`, `adsb`, `vor`, `wifi`, `ble`, `chu`, `fm`, `leo` (simulated), `cam`. Simulated data keeps the same names; the session metadata says it is simulated.

### `kind` registry

| kind | value | units |
| --- | --- | --- |
| `position_enu` | (e, n, u) | m |
| `velocity_enu` | (ve, vn, vu) | m/s |
| `accel_gyro` | (ax, ay, az, gx, gy, gz), body frame | m/s², rad/s |
| `altitude` | (h,) above session origin | m |
| `pseudorange` | (ρ,) range + unknown emitter/receiver clock terms | m |
| `range` | (r,) true range (e.g. Wi-Fi FTM) | m |
| `doppler` | (ρ̇,) range rate | m/s |
| `bearing` | (θ,) from the emitter to us, clockwise from true north (VOR radial) | rad |
| `rssi` | (p,) | dBm |
| `time` | (Δt,) offset of local clock from the source's time | s |
| `gnss_health` | (jam_indicator, n_sats, hdop) | — |
| `adsb_report` | (e, n, u, nacp, nic) of the aircraft | m, — |

New kinds are added here first, then in code.

## Estimate: the navigation output

| Field | Type | Meaning |
| --- | --- | --- |
| `t_ns` | int64 | GPS time |
| `pos_enu` | (3) | m |
| `vel_enu` | (3) | m/s |
| `pos_cov` | (9) row-major 3×3 | m² |
| `clock_bias_s`, `clock_sigma_s` | float, float \| null | Receiver clock offset from GPS time and its 1-σ (`null` = not estimated) |
| `hpl_m`, `vpl_m` | float \| null | Horizontal / vertical protection levels (`null` = not computed) |
| `status` | str | `nominal` \| `degraded` \| `unsafe` |
| `trust` | dict[str, float] | Per-source trust in [0, 1] |
| `flags` | list[str] | e.g. `gnss_excluded`, `spoof_suspected` |

## Truth (simulation and RTK sessions only)

`t_ns`, `pos_enu` (3), `vel_enu` (3), `clock_bias_s`.
