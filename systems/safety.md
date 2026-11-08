# Safety, regulatory and responsible execution

Scored by the judges ("safety, RF, aviation, privacy, cybersecurity, and regulatory considerations"). Each item names the requirement or decision that enforces it.

## RF and spectrum

- **Receive-only payload** (REQ-07, ADR-0001). The only emitters on the vehicle are licence-exempt: the 2.4 GHz RC link, Wi-Fi to the ground laptop, and (if used) 915 MHz telemetry.
- **No jamming or spoofing, ever.** These are simulated in software (ASM-03). GNSS jammers are prohibited in Canada, and the organizers warned that anything drawing an ISED Spectrum Management call nearly rules a team out.
- No SDR with transmit capability is used (HackRF excluded for this reason).

## Legal: interception of radiocommunication

- Radiocommunication Act s.9(2) prohibits intercepting **and using** a radiocommunication without permission from its originator or intended recipient. We decode only signals intended for general reception: synchronization and reference signals, pilots, beacons, navaid signals, broadcasts, and ADS-B. **No user or communication content is decoded or stored** (REQ-08).
- This is our reading, not legal advice; confirmed with mentors: `TBD`.

## Privacy

- Wi-Fi BSSIDs are salted and hashed on the ESP32 before they leave it (ADR-0011). Client probe requests are never captured.
- ADS-B data is public broadcast; we store it but publish only aggregates.
- Camera footage stays local and is not published without review.

## Flight

- Independent RC link with a physical kill switch is always present; software never removes the pilot's ability to take over (ADR-0012).
- Flights indoors in a netted area, with prop guards, a speed limit, a geofence, and ArduPilot failsafes (RC loss / battery → land).
- Carleton appears to be inside YOW controlled airspace: no outdoor flights without the required Transport Canada certificate and NAV CANADA authorization (ASM-06).
- LiPo handling: charge in a LiPo bag, never unattended; damaged packs are retired.

## Cybersecurity and integrity of the navigation solution

- Spoofing is treated as an adversary, not noise: the estimator cross-checks GPS against independent sources (REQ-04).
- Sources that fail together with GPS (ADS-B content, GNSS-disciplined tower timing) are not counted as independent evidence.
- Live stream is on a local network only; no remote control path exists through the payload stream.
