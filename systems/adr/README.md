# Architecture decision records

One file per decision, from [`0000-template.md`](0000-template.md). Never edit an accepted decision: supersede it.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-receive-only-payload.md) | The payload is receive-only | Accepted |
| [0002](0002-record-raw-process-ground.md) | Record raw on board, process on the ground | Accepted |
| [0003](0003-one-python-project.md) | One Python project managed with uv | Accepted |
| [0004](0004-three-sources.md) | Sim, replay and live are interchangeable sources | Accepted |
| [0005](0005-wire-protocol-mavlink.md) | ESP32↔Pi wire protocol is a custom MAVLink dialect | Accepted |
| [0006](0006-measurement-record.md) | One pipeline record: Measurement | Accepted |
| [0007](0007-logs-mcap.md) | Logs are MCAP, raw IQ sits beside them | Accepted |
| [0008](0008-time-and-frames.md) | Time is GPS nanoseconds; positions are ENU metres | Accepted |
| [0009](0009-live-transport-zeromq.md) | Live transport is ZeroMQ PUB/SUB | Accepted |
| [0010](0010-dashboard.md) | Operator dashboard is FastAPI plus one static page | Accepted |
| [0011](0011-privacy-at-capture.md) | Privacy is enforced at capture | Accepted |
| [0012](0012-flight-control-levels.md) | RC stays the safety layer; scripted flights first | Accepted |
| [0013](0013-no-iridium-hardware.md) | LEO (Iridium) is simulated, not received | Accepted |
| [0014](0014-provided-gps-and-sensors.md) | Use the Honeywell-provided GPS HAT, IMU and barometer | Accepted |
| [0015](0015-sim-calibrated-to-reality.md) | The simulation is calibrated against real measurements | Accepted |
| [0017](0017-quality-standard.md) | Work is ready when evidence matches the claim | Proposed |
