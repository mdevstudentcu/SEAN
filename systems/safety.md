# Safety, regulatory and responsible execution

Scored by the judges ("safety, RF, aviation, privacy, cybersecurity, and regulatory considerations"). Each item names the requirement or decision that enforces it.

## RF and spectrum

- **Receive-only payload** (REQ-07, ADR-0001). The only emitters on the vehicle are licence-exempt: the 2.4 GHz RC link, Wi-Fi to the ground laptop, and (if used) 915 MHz telemetry. For tethered hover only, the ESP32 RC bridge's 2.4 GHz Wi-Fi access point is the control link instead of the RC link (ADR-0029). It is a control link, not a payload transmit path.
- **No jamming or spoofing, ever.** These are simulated in software (ASM-03). GNSS jammers are prohibited in Canada, and the organizers warned that anything drawing an ISED Spectrum Management call nearly rules a team out.
- No SDR with transmit capability is used (HackRF excluded for this reason).

## Legal: interception of radiocommunication

- Radiocommunication Act s.9(2) prohibits intercepting **and using** a radiocommunication without permission from its originator or intended recipient. We decode only signals intended for general reception: synchronization and reference signals, pilots, beacons, navaid signals, broadcasts, and ADS-B. **No user or communication content is decoded or stored** (REQ-08).
- This is our reading, not legal advice; confirmed with mentors: `TBD`.

## Privacy

- Wi-Fi BSSIDs are salted and hashed on the board that scans, before they leave it (ADR-0011, ADR-0018). Client probe requests are never captured.
- ADS-B data is public broadcast; we store it but publish only aggregates.
- Camera footage stays local and is not published without review.

## Flight

- Independent RC link with a physical kill switch is always present; software never removes the pilot's ability to take over (ADR-0028, which supersedes ADR-0012). Without it the drone doesn't fly, except that a tethered hover may use the ESP32 Wi-Fi control link instead, under ADR-0029:
  - Only on a floor-anchored tether of about 0.5 m, hovering at 0.3–0.5 m, with prop guards, padding and an XT60 loop plug as the kill on the ground.
  - Link silence → INAV failsafe LAND; the kill button disarms; boot is disarmed.
  - The props-off bench test in `firmware/esp32-rc-bridge/README.md` passes first.
  - Free flight still needs the RC link with a physical kill switch.
- Flights indoors in a netted area, with prop guards, a speed limit, INAV's failsafe (RC loss → land), and a geofence if the INAV version supports it (`TBC`).
- Carleton appears to be inside YOW controlled airspace: no outdoor flights without the required Transport Canada certificate and NAV CANADA authorization (ASM-06).
- LiPo handling: charge in a LiPo bag, never unattended; damaged packs are retired.

## Cybersecurity and integrity of the navigation solution

- Spoofing is treated as an adversary, not noise: the estimator cross-checks GPS against independent sources (REQ-04).
- Sources that fail together with GPS (ADS-B content, GNSS-disciplined tower timing) are not counted as independent evidence.
- Live stream is on a local network only; no remote control path exists through the payload stream.
