# Assumptions

| ID | Assumption | Why it matters | Status |
| --- | --- | --- | --- |
| ASM-01 | GPS is available and trusted at start-up, long enough to initialise and calibrate. | Calibration of signal sources before an outage (candidate idea B) | TBC |
| ASM-02 | Transmitter locations come from public databases (ISED, Canada Flight Supplement; OpenCelliD only as a clustering hint, ADR-0023) with position error ≤ `TBD` m. | Ranging accuracy is bounded by emitter-position error | TBC |
| ASM-03 | GPS jamming and spoofing are only simulated in software; nothing is transmitted. | REQ-07, safety | Baselined |
| ASM-04 | Payload clocks are disciplined to GPS PPS to within `TBD` µs while GPS is available. | All sensor logs share one timebase (ADR-0008) | TBC |
| ASM-05 | Navigation is primarily horizontal; altitude comes from the barometer. | Small drone flights below `TBD` m | TBC |
| ASM-06 | Live flights are indoors (netted area) or the payload is carried by hand or vehicle outdoors. | Carleton is likely inside YOW controlled airspace | TBC |
| ASM-07 | Most Ottawa–Gatineau FM/TV transmitters share one site (Camp Fortune), so broadcast ranging gives poor geometry. | Cell towers carry the positioning; broadcast is a fallback | TBC |
