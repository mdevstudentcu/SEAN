# Safety, regulatory and responsible execution

Scored by the judges ("safety, RF, aviation, privacy, cybersecurity, and regulatory considerations"). Each item names the requirement or decision that enforces it. The [hazard table](#hazard-analysis) comes first; the rules behind it follow.

## Hazard analysis

Draft, 2026-11-11 (#223). **Severity** is our assessment for this prototype (`TBC`), on an aviation-style scale: *catastrophic* could kill; *hazardous* could seriously injure someone or break radio law; *major* minor injury, damage, or a wrong result taken as true; *minor* lost time or data. No probabilities are given: we have no failure data. **State:** *built* (exists on `main`), *tested* (a test or result on `main` shows it; sim unless it says otherwise), *planned* (not on `main`), *open* (no mitigation).

| # | Hazard | Effect | Severity | Mitigation | State | Evidence on `main` |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | The payload transmits (REQ-07) | Interference; a spectrum legal issue (RSK-08) | Hazardous | Receivers only, no transmit-capable SDR; the LoRa HAT is not used; jamming and spoofing exist only in software. The licence-exempt control and Wi-Fi links stay | Tested (code scan of a fixed API list); hardware by inspection | ADR-0001; `tests/test_hard_rules.py::test_no_transmit_calls_req07`; `hardware/bom.md` *Not using* |
| H2 | Communication content decoded (LTE user channels, Mode S replies, datalink) (REQ-08, RSK-08) | Radiocommunication Act s.9(2) offence; privacy | Hazardous | Only sync, reference and broadcast fields; ADS-B decoder gets extended squitters only | Tested (scan + ADS-B test); mentor confirmation `TBD` | ADR-0011; `test_hard_rules.py::test_no_communication_content_decoders_req08`, `::test_adsb_decoder_never_sees_interrogation_replies_req08` |
| H3 | Payload mass or mounting overloads or comes off the drone (REQ-09) | Crash, prop strike | Major | Weigh it before mounting; tether on the frame, not the payload (`TBC`: not yet in ADR-0029 or the pre-flight checklist) | **Open**: weight and mounting `TBD`; checklist built | `hardware/bom.md` *Size, weight and power*; `firmware/esp32-rc-bridge/README.md` pre-flight checklist |
| H4 | Loss of control in free flight (RSK-09) | Drone leaves the net; injury | Hazardous | Free flight only with an RC link and physical kill switch; indoors, netted, prop guards; INAV RC-loss failsafe; our navigation never steers the drone | Planned: no RC link in hand, so no free flight; failsafe settings `TBC` | ADR-0028; `hardware/bom.md` *Open decisions* |
| H5 | Tethered hover: link stall, forged packet or unintended arm | Thrust inside the tether radius | Major | 0.5 m floor tether, prop guards, XT60 loop plug; HMAC, sequence, boot nonce; silence stops CRSF so INAV lands; boot disarmed; kill wins | Built; protocol tested on the host. Props-off bench run not recorded on `main`; INAV settings `TBC` | ADR-0029; `tests/test_rc_bridge_cpp.py::test_watchdog_replay_and_forgery`, `::test_kill_packet_from_python` |
| H6 | "Green and wrong": confident wrong position after a GNSS spoof (REQ-02, REQ-04) | Operator acts on a false position (hazardous in a product role, `TBC`) | Major | GNSS gate (default); the sky-map spoof decision on the panel by default, advisory: it changes no estimate (ADR-0041, Accepted); the tower spoof monitor (`ekf-spoof`, ADR-0037 Proposed), `ekf-mhss` and the jump guard (ADR-0038 Proposed), **all three opt-in**; a P12 tower map is built with the guard and withheld if flagged (ADR-0048, Accepted) | Tested in sim for the opt-in estimators. T4's jump target is Accepted (ADR-0034, *Amendment 2026-11-11*): detection is met by every estimator, exclusion and no hazardous epoch only by the opt-in `-guard` filters. **Open for the default `ekf`**: it follows a held 300 m jump once its covariance grows (ADR-0038). Slow drift (a 2 m/s ramp on four towers is not caught and is handed on in a P12 map, ADR-0048), jam-then-spoof: open | `tests/test_mhss.py::test_gnss_spoof_is_flagged_and_never_hazardously_misleading`; `tests/test_jump_guard.py::test_held_offset_is_refused_however_long_the_spoofer_waits`; `analysis/results/jump-refusal/summary.md`; `analysis/pr-evidence/shrikar-feat-206-spoof-decision/summary.md`; `analysis/results/p12-spoofed-map/summary.md`; `threat-model.md` *Gaps* |
| H7 | Protection level does not bound the error (REQ-02) | False confidence | Major | MHSS hypotheses (site, builder, GNSS); filter consistency checks; Stanford plots | Tested in sim only; fault priors `TBC`, error models `placeholder`. Towers-only `ekf-calibrated` has hazardous epochs (ADR-0038). Since ADR-0047, `ekf`'s worst-run T1 HPL bound on `realistic-long-outage` is 0.631 (`ekf-calibrated` 0.887). Real data: open | `tests/test_mhss.py::test_nominal_has_no_exclusion_and_bounds_the_error`; `tests/test_consistency.py::test_baseline_filter_is_consistent`; `verification.md` *Sim validity* |
| H8 | A simulated number taken as real (REQ-10) | Wrong claim to judges or users | Major | Panel shows SIM, REPLAY or LIVE; every result names its evidence kind and model status | Built. Open: a replayed *simulated* session shows REPLAY, not SIM | `src/pnt/dashboard/web/app.js` (`kind` chip), `src/pnt/dashboard/feed.py`; `quality.md` *Reporting numbers*; `roadmap.md` *What we will not claim* |
| H9 | Wi-Fi identifiers stored (REQ-08) | Devices traceable; s.9(2) | Major | Passive scan only; BSSIDs salted and hashed on the scanning board; SSIDs not stored; no probe requests | Tested (session audit over a fake `iw`) | ADR-0011; `src/pnt/payload/wifi.py`; `test_hard_rules.py::test_recorded_wifi_session_holds_no_bssid_or_ssid_req08` |
| H10 | Capture locations and raw data leak (GPS tracks, IQ, camera, the confidential deck) (REQ-08) | Where people were becomes public; confidential material published | Major | Sessions git-ignored; PR images carry no raw data or personal details; ADS-B published only as aggregates; camera reviewed before release; Remote ID not received | Tested for git. Publishing rules are procedure only. Sessions copied outside git, retention: open | `test_hard_rules.py::test_no_raw_session_data_tracked`, `::test_no_confidential_files_tracked`; `quality.md` *PR descriptions*; ADR-0024 |
| H11 | Forged records on the ground link (REQ-04) | Bypasses every radio check: green and wrong | Major | CurveZMQ, pinned Pi keys, laptop allow-list; plaintext needs `--insecure` | Tested (loopback). Open: a stolen key; MAVLink signing `TBC` | ADR-0026; `tests/test_link_security.py::test_an_impersonating_server_gets_nothing_into_the_laptop`, `::test_a_record_tampered_in_flight_is_never_accepted`, `::test_plaintext_needs_insecure` |
| H12 | Tampered session logs; leaked credentials (REQ-10) | Unprovable results; impersonation | Major | Secret keys mode 600 and git-ignored, never overwritten; firmware secrets git-ignored. Log hash chain designed | Credentials tested. **Logs open**: MCAP CRCs catch accidents only; hash chain after judging | `test_link_security.py::test_key_files_are_private_and_never_overwritten`; `.gitignore`; ADR-0026 |
| H13 | Time output overconfident after GNSS time is lost (REQ-03) | A timing user trusts a clock beyond its bound | Major | A tower error model with multipath and correlation in the default filter (#77, `roadmap.md`); `ekf-calibrated` already models it (0.0 time-misleading epochs per run on `realistic-long-outage`) | **Open, cost accepted** by the owners with ADR-0047 (2026-11-11): the default `ekf` has 22 to 316 time-misleading epochs per run on the realistic, worst and approach sets (sim, 50 seeds) | ADR-0047 *Consequences*; `analysis/pr-evidence/228/before-after.md`; `tests/test_ekf_rx_clock_modes.py` |

**Regulation, as it applies (our reading, not legal advice).** Three regimes touch this prototype: spectrum (ISED: the payload is receive-only and our only emitters are licence-exempt links, *RF and spectrum*); interception (Radiocommunication Act s.9(2): we decode only what is meant for everyone, *Legal*); and aviation (we fly only indoors in a netted area; outdoor flight near YOW needs the Transport Canada certificate and NAV CANADA authorization named in *Flight*, ASM-06). Privacy is handled by design at capture (*Privacy*). Mentor confirmation is `TBD`, and the product needs a legal opinion (`roadmap.md`, *Certify*).

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
- Live stream is on a local network only; no remote control path exists through the payload stream. It is authenticated and encrypted with CurveZMQ, and plaintext needs an explicit `--insecure` (ADR-0026, #89).
