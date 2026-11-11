# Architecture decision records

One file per decision, from [`0000-template.md`](0000-template.md). Never edit an accepted decision: supersede it.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-receive-only-payload.md) | The payload is receive-only | Accepted |
| [0002](0002-record-raw-process-ground.md) | Record raw on board, process on the ground | Accepted |
| [0003](0003-one-python-project.md) | One Python project managed with uv | Accepted |
| [0004](0004-three-sources.md) | Sim, replay and live are interchangeable sources | Accepted |
| [0005](0005-wire-protocol-mavlink.md) | ESP32↔Pi wire protocol is a custom MAVLink dialect | Superseded by 0018 |
| [0006](0006-measurement-record.md) | One pipeline record: Measurement | Accepted |
| [0007](0007-logs-mcap.md) | Logs are MCAP, raw IQ sits beside them | Accepted |
| [0008](0008-time-and-frames.md) | Time is GPS nanoseconds; positions are ENU metres | Accepted |
| [0009](0009-live-transport-zeromq.md) | Live transport is ZeroMQ PUB/SUB | Accepted |
| [0010](0010-dashboard.md) | Operator dashboard is FastAPI plus one static page | Superseded by 0027 |
| [0011](0011-privacy-at-capture.md) | Privacy is enforced at capture | Accepted |
| [0012](0012-flight-control-levels.md) | RC stays the safety layer; scripted flights first | Superseded by 0028 |
| [0013](0013-no-iridium-hardware.md) | LEO (Iridium) is simulated, not received | Accepted |
| [0014](0014-provided-gps-and-sensors.md) | Use the Honeywell-provided GPS HAT, IMU and barometer | Accepted |
| [0015](0015-sim-calibrated-to-reality.md) | The simulation is calibrated against real measurements | Accepted |
| [0016](0016-sionna-campus-trial.md) | Ray-traced campus blockage is an optional, unvalidated model input | Proposed |
| [0017](0017-quality-standard.md) | Work is ready when evidence matches the claim | Proposed |
| [0018](0018-payload-boards.md) | The payload is a Pi 4B recorder; a Pi Zero 2 W hub only if day-1 tests need it | Proposed |
| [0019](0019-no-chu.md) | Drop CHU broadcast time | Proposed |
| [0020](0020-ground-reference-station.md) | A ground reference station measures tower clocks for differential LTE | Proposed |
| [0021](0021-what-we-build-and-pitch.md) | We pitch integrity-first navigation that treats signals of opportunity as things that can fail | Accepted |
| [0022](0022-tower-clock-model.md) | Tower clock model: site and network-builder grouping, learned while GPS is trusted | Proposed |
| [0023](0023-tower-identity.md) | Tower identity: ISED registry, PCI scan and mapper | Proposed |
| [0024](0024-gnss-dependency-tags.md) | Every source carries a GNSS-dependency tag | Proposed |
| [0025](0025-hostile-emitter-beacon.md) | A located jammer may be a low-trust beacon, in sim only | Proposed |
| [0026](0026-ground-link-security.md) | Ground links are signed and authenticated; logs are hash-chained | Accepted (CurveZMQ); MAVLink signing `TBC`; hash chain after judging |
| [0027](0027-dashboard-sse-canvas.md) | The dashboard streams over Server-Sent Events and draws on canvas | Accepted |
| [0028](0028-fly-inav.md) | The drone flies INAV on the BLITZ ATF435, pilot-flown with an RC kill switch | Accepted |
| [0029](0029-tethered-hover-wifi-control.md) | Tethered indoor hover may be flown from a gamepad through an ESP32 Wi-Fi bridge | Accepted |
| [0030](0030-challenge-benchmark-set.md) | A challenge benchmark set: one leg per use case, on records shaped like real ones | Proposed |
| [0031](0031-gnss-jam-indicator.md) | The GNSS jam indicator is the C/N0 drop of the strongest satellites | Proposed |
| [0032](0032-residual-map.md) | Learn a per-place residual map of each tower while GPS is trusted | Accepted, opt-in only |
| [0033](0033-adsb-raises-gnss-prior.md) | ADS-B interference evidence raises the GNSS fault prior | Proposed |
| [0034](0034-targets-after-mentor-answers.md) | Targets after the mentors' answers: our stricter T1, their figure as the fallback | T1 Accepted; T3–T5 Proposed |
| [0036](0036-lte-measured-error-model.md) | The LTE error model is split into white and correlated parts, sized from real captures | Proposed |
| [0037](0037-tower-spoof-monitor.md) | A tower displacement monitor checks the GNSS position against the towers, opt-in | Proposed |
| [0038](0038-refuse-detected-gnss-jump.md) | Refuse a detected GNSS position jump until the jump is undone (opt-in: `*-guard` estimators) | Proposed |
| [0040](0040-lte-carrier-hopping.md) | LTE carrier hopping with one dongle is a modelled option and a study leg, not part of the benchmark | Proposed |
| [0042](0042-record-iq-to-usb-drive.md) | Record the radios' IQ to a USB drive, not the SD card | Proposed |
| [0043](0043-calibrated-from-measured-values.md) | A calibrated EKF sized from measured values, not from the sim it is scored on (opt-in: `ekf-calibrated-measured`) | Proposed |
| [0044](0044-told-sigma-for-radio-records.md) | Tell radio LTE records ADR-0036's measured sigma, opt-in, beside learned noise (opt-in: `*-measured-sigma` estimators) | Proposed |
