# Risks

Ranked by likelihood × impact. Each has a mitigation and, where useful, an early spike to retire it.

| ID | Risk | L | I | Mitigation / spike |
| --- | --- | --- | --- | --- |
| RSK-01 | Drone parts (flight controller, RC, batteries) arrive late or the drone can't fly by Wednesday | H | M | Payload is platform-agnostic (REQ-09): collect handheld/vehicle data; SITL for flight demos |
| RSK-02 | LTE pseudoranges from an 8-bit RTL-SDR are too noisy to be useful | M | H | Spike Monday: RF survey + one-hour LTE timing test. Fallback: cell-ID/RSSI, sim with honest error models |
| RSK-03 | Estimator diverges or tuning eats the schedule | M | H | Baseline filter first (`nav/baseline.py`), NEES/NIS consistency tests in CI |
| RSK-04 | Live demo fails on the day (Wi-Fi, hardware, crash) | M | H | Demo runs from replay by default; live is a bonus. Same pipeline (ADR-0004) |
| RSK-05 | PPS timestamping on the Pi or the Pi Zero 2 W hub is worse than assumed | M | M | Measure PPS jitter on day 1; chrony statistics in every session |
| RSK-06 | USB 3 / ESC noise degrades GPS and SDR reception | M | M | SDRs on USB 2 ports, ferrites, antenna masts; compare noise floor props on/off |
| RSK-07 | Scope creep from choosing too many signal sources or ideas | H | M | Core shortlist only (LTE, Wi-Fi, ADS-B, + VOR/CHU quick wins); ADR for each addition |
| RSK-08 | Accidental emission or a legal issue (ISED, Radiocommunication Act s.9) | L | H | Receive-only hardware and code (REQ-07), `safety.md`, decode only broadcast fields |
| RSK-09 | Outdoor flying near YOW without authorization | L | H | Fly indoors; outdoor data handheld/vehicle only (ASM-06) |
