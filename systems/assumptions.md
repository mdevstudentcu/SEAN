# Assumptions

| ID | Assumption | Why it matters | Status |
| --- | --- | --- | --- |
| ASM-01 | GPS is available and trusted at start-up, long enough to initialise and calibrate. | Calibration of signal sources before an outage (candidate idea B) | TBC |
| ASM-02 | Transmitter locations come from public databases (ISED, Canada Flight Supplement; OpenCelliD only as a clustering hint, ADR-0023) with position error ≤ `TBD` m. | Ranging accuracy is bounded by emitter-position error | TBC |
| ASM-03 | GPS jamming and spoofing are only simulated in software; nothing is transmitted. | REQ-07, safety | Baselined |
| ASM-04 | Payload clocks are disciplined to GPS PPS to within 1 µs (`TBC`) while GPS is available. Measured 2026-11-11 on the payload Pi 4B with the Adafruit GPS HAT and its external active antenna, static, outdoors (#17): chrony selected PPS (`#*`), offset −35 ns ± 364 ns, PPS standard deviation 769 ns over 80 s, RMS offset 957 ns, residual frequency −0.024 ppm, skew 0.046 ppm; `ppstest /dev/pps0` asserted once a second, each edge within 1.0 µs of the whole second. NMEA alone is 385 ms late and only locks PPS to the right second (`noselect`). One night session, so `TBC` for heat, flight and the Pi Zero 2 W hub. | All sensor logs share one timebase (ADR-0008) | Measured once (#17) |
| ASM-05 | Navigation is primarily horizontal; altitude comes from the barometer. | Small drone flights below `TBD` m | TBC |
| ASM-06 | Live flights are indoors (netted area) or the payload is carried by hand or vehicle outdoors. | Carleton is likely inside YOW controlled airspace | TBC |
| ASM-07 | Most Ottawa–Gatineau FM/TV transmitters share one site (Camp Fortune), so broadcast ranging gives poor geometry. | Cell towers carry the positioning; broadcast is a fallback | TBC |
