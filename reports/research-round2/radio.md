# Radio signals of opportunity: saturation pass (round 2)

Date 2026-11-11. Builds on `reports/sources-research-20261111.md` (sections 6 to 10, 16); repeats nothing from it
unless corrected or upgraded. Labels: [V] read today in the primary source (abstract or full text, stated), [S]
search snippet or secondary page, [M] memory, [C] own arithmetic. Flags: TX (vehicle transmits), NET (needs
network/operator cooperation or a data link), OPTICAL. No flag means passive and stand-alone.

## 1. Coverage

119 WebSearch calls (budget not exhausted; no budget error). Saturation rule: 8 consecutive searches with nothing new.

| # | Topic | Searches | Saturated? | New items | New in last 10 searches of topic | Blocked by |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Iridium burst Doppler | 21 | Near (last 3 gave only minor items) | 17 | 5 (vendor board numbers, HIT 13 m, sat clock ±10 µs, Delft thesis, outer-loop paper) | BYU/Humber 403; no UAV result exists |
| 2 | LEO Doppler and orbits | 14 | No | 18 | 6 (moving-platform table, clock-grade table, differential LEO 2026, SupGP, edge pilots) | Curtin 403; PDFs needed pdftotext |
| 3 | Cellular carrier phase, free-running clock | 10 | Near for "is there a result" (none exists); no for methods | 6 | 3 (RTL-SDR RTK, R820T drift, T-IV 2023) | IEEE 418 |
| 4 | Tower clocks | 10 | Near | 9 | 4 (Edwards jamming, operator statements, TDD rules, freq-offset survey absent) | Edwards PDF over size limit; Sensors (MDPI) 403 |
| 5 | 5G NR from drones | 7 | No | 7 | 7 | Polimi PDF needed pdftotext |
| 6 | AoA from small platforms | 8 | Near (results only patents now) | 8 | 4 | MDPI 403 (pdf mirror worked) |
| 7 | Error vs altitude | 5 | No, but the specific statistic does not seem to exist | 6 | 6 | — |
| 8 | Broadcast | 9 | Near | 9 | 5 | Humber 403 |
| 9 | Unconventional | 15 | Near for this pass (each sub-item 1 to 2 searches) | 16 | 6 | ICAO PDF 404 |
| 10 | Radio SLAM, tower maps | 6 | No | 6 | 6 | — |
| 11 | Datasets and licences | 5 | Near | 9 | 9 | OAKBAT licence page not found |
| 12 | Venue sweep | 9 | Near | 10 | 4 | ION programme pages not indexed |

Honest note: by the strict 8-in-a-row rule no topic is formally saturated. Topics 1, 3, 4, 6, 8, 11 and 12 were
returning repeats or patents by the end; 2, 5, 7 and 10 still produced new items on most searches. Context, not
search budget, was the limiting resource.

## 2. Findings per topic

### Topic 1. Iridium burst Doppler

**1.1 Snapshot differential Iridium Doppler with a Raspberry Pi rover (the closest thing to our hardware)**
- Desai (Skylo) & Cade (Stanford), "Experimental Demonstration of Snapshot Differential Positioning with LEO
  Satellites", arXiv 2603.15908, Mar 2026. https://arxiv.org/html/2603.15908v1 [V]
- Idea: a fixed base (USRP B200 + GPSDO) and a rover (MicroPhase ANTSDR E316 + Raspberry Pi, internal oscillator, no
  GPSDO) record Iridium in 5 s snapshots; base-minus-model Doppler residuals correct the rover, and a Doppler-curve fit
  solves position, a constant frequency offset and a linear frequency drift.
- Results [V]: rover alone about 500 m; differential under 265 m (about 47 % better). Three common satellites,
  10 km baseline, 55 min window. Doppler RMS against TLE model: base 5 to 7 Hz; rover raw 80 to 100 Hz; rover after
  correction 10 to 20 Hz. No IMU (listed as future work).
- Sim needs: rover Doppler noise 80 to 100 Hz RMS uncorrected with a free-running SDR crystal (this is the realistic
  number for our dongles, an order above the tone CRB); a frequency offset + linear drift state per snapshot; thermal
  drift of the crystal across start/stop snapshots named as the dominant error. Flags: NET only if the base is used.

**1.2 Iridium Doppler plus azimuth direction of arrival**
- Shahcheraghi, Nasihati Gourabi, Neinavaie, Kassas, "Joint Doppler and Azimuth DOA Tracking for Positioning with
  Iridium LEO Satellites", ION GNSS+ 2023 (OSU PDF). [V, abstract and intro]
- Ring-alert channel at 1626.2708 MHz, 41.667 kHz bandwidth. FFT acquisition, Kalman Doppler tracking, then
  Doppler-compensated MUSIC on an array.
- Results [V]: Doppler RMSE 8.1 Hz over 120 s; azimuth DOA RMSE 1.04° over 60 s; static receiver started 7 km off:
  656 m with Doppler only, 289.5 m with Doppler + azimuth.
- Sim needs: a tracked (not per-burst) Doppler noise of about 8 Hz (about 1.5 m/s at 1626 MHz [C]); azimuth to a
  satellite at about 1° from a small array. Cites Benzerrouk et al. 2019 (Iridium/INS aerial) and Farhangian 2021.

**1.3 Iridium/INS on aircraft (simulation and ground)**
- Benzerrouk, Nguyen, Xiaoxing, Amrhar, Nebylov, Landry, "Alternative PNT based on Iridium Next LEO Satellites
  Doppler/INS Integrated Navigation System", ICINS 2019, DOI 10.23919/ICINS.2019.8769440 [S]. Aircraft keywords,
  full text not read.
- Farhangian, Benzerrouk, Landry, "Opportunistic In-Flight INS Alignment Using LEO Satellites and a Rotatory IMU
  Platform", Aerospace 2021 [S]: ground test about 26 m. Farhangian & Landry, Proc. IMechE G 2022 [S]: tightly
  coupled Iridium/Orbcomm/Globalstar + INS on a ground vehicle, under 10 m.
- Still no flown Iridium-only result on a small drone. That gap stands.

**1.4 More static Iridium accuracies (all published orbits unless stated)**
| Result | Conditions | Source | Label |
| --- | --- | --- | --- |
| 140 m 3D cold start (130 m after Gauss-Newton refinement) | semidefinite relaxation, no initial position; code and datasets stated public | Song, Wen, Zhang, Xu, Yan, Li, Hsu (PolyU), arXiv 2509.17198, 2025 | [V abstract] |
| 24 m 2D / 41 m 3D | Iridium NEXT pseudorange + Doppler "time-frequency inversion", 40 km baseline (differential), TLE errors suppressed | Ying Xu et al. (AIR, CAS), Satellite Navigation 2025, DOI 10.1186/s43020-025-00163-y | [S] press release |
| 31.66 m 2D RMSE | 15 min static, six Iridium satellites | ICNS 2025 paper | [S] |
| 22.7 m | one Orbcomm + four Iridium NEXT, static (Kassas group, 2021) | upgrades the first report's 22.7 m snippet: context now known | [S] |
| about 50 m theoretical with two passes crossing at about 20°; complementary pairs within about 30 min | DDOP model validated on real Iridium | Liu, Fernández-Temprado, Reus-Bergas, Pan, Gao, Seco-Granados, López-Salcedo, arXiv 2607.10241, 2026 | [V abstract] |
| 46.7 % (TLE) and 65.7 % (broadcast orbit) improvement | Beihang Iridium SoOP method | shi.buaa.edu.cn | [S] |
| 7.13 m vs 41.29 m non-differential vs 87.74 m GNSS-aided IMU coasting | ground vehicle, 2 Orbcomm + 1 Iridium, differential, industrial IMU (Kassas group) | par.nsf.gov 10510325 | [S] |
The first report's "8.32 m with one Iridium satellite" was not found; the closest real number is the 7.13 m row,
which uses three satellites. Treat 8.32 m as unverified.

**1.5 Burst frequency estimation methods**
- Tone is 2.56 ms, so FFT resolution is 390 Hz; refinement needed [S, Remote Sensing 17(15):2565, 2025].
- Phase-time method (IEEE TAES 2022, DOI 10.1109/TAES.2022.3180702) [S]: time-domain Doppler, better than FFT.
- Implicit pilots (IEEE Comm. Letters 24, 2020) [S]: 58.41 % of ring-alert/paging frames contain usable implicit
  pilots; using them cuts Doppler error 70 %.
- Coarse FFT, then raise to the 4th power to strip QPSK, then MLE [S].
- Zanirato et al. CRB [S]: 10 to 100 Hz standard deviation for 40 to 60 dB-Hz with 1.33 ms windows.
- Sim value suggestion [C]: per-burst Doppler σ 10 to 30 Hz for good bursts with a refined estimator, 80 to 100 Hz
  for what a free-running SDR actually delivered in 1.1 (dominated by oscillator, not thermal noise).

**1.6 Iridium broadcast fields and timing**
- Ring alert carries satellite number, beam number and two alternating lat/lon/alt pairs; pairs with altitude above
  about 100 km are the satellite's own position [S, Iridium Toolkit wiki]. No accuracy for these positions found.
- L-band frame 90 ms; a time-transfer patent (US 8542147) describes 8.28 ms bursts and a frame count tied to a time
  message every 180 ms [S].
- Paid service timing: NIST/ION PTTI 2026 (Johnson & Novick) [V abstract]: 40-day comparison against UTC(NIST);
  receiver with a miniature atomic clock: max offset under 40 ns, MTIE under 80 ns; with ionospheric corrections MTIE
  about 60 ns; TDEV about 6 ns at 1 day; ADEV below 2e-14 at 5e5 s. Upgrades the first report's "205 to 300 ns"
  (that was the 2023 Auburn thesis, 110 ns deviation and under 205 ns mean error over 120 h [S]).
- Paid service position: EC JRC study (report released March 2023) [V, InsideGNSS]: 100 days static, 26.6 m
  horizontal 95 %, 16.8 m vertical 95 %, 100 % availability, indoor antenna worked; timing ADEV 2.28e-13 at 100 days.
  This upgrades "20 to 50 m (memory)". No airborne test of the paid service was found. NET (subscription).
- 2026 Jammertest: a vendor board (RockBLOCK APNT, built on the Iridium PNT ASIC) is said to have flagged GNSS
  spoofing in under 1 s while its Iridium position stayed stable [V, GPS World; vendor claim]. Board 59 × 36.5 ×
  7.7 mm, 10 g, receive-only, UART/SPI/I²C, 3.3 V [V]. Field median position 25 m at 69°N and 42 m at 19°N [S,
  platform not stated]. No independent result, no price. Iridium's own WSTS 2026 talk on static and "on the move"
  timing at Jammertest 2025 has no numbers in its abstract [V]. NET (subscription). This is the only receive-only,
  drone-sized, GNSS-independent position source on sale today; worth a sim model at 25 to 50 m, update rate TBD.
- Iridium satellite clocks are held within about 10 µs of UTC (patent US 7859455) [S]; 90 ms L-band frame usable for
  coarse timing [S].
- HIT self-differential Doppler (SDDP), Liu, Li, Zhang, Liu: real Iridium NEXT in three obstruction levels; joint
  pseudorange-Doppler "within 13 m" [S]. Beijing Inst. Tech. cites an earlier Iridium WLS result better than 70 m 3D
  [S]. UAB "outer-loop" LEO Doppler framework accounting for propagation time, Satellite Navigation 2026, DOI
  10.1186/s43020-026-00189-w [S].

**1.7 Iridium and spoofing**
- Oligeri, Sciancalepore, Di Pietro, "GNSS Spoofing Detection via Opportunistic IRIDIUM Signals", ACM WiSec 2020,
  arXiv 2006.10284 [V abstract]: single antenna, ring-alert content only (no physical layer), checks a GNSS track
  against the beams/satellites heard; 1000+ hours of ring alerts collected and published. Detection numbers not in the
  abstract. Directly relevant to the spoof-detection role: an RTL-SDR on Iridium is a GNSS-independent plausibility
  check. Our privacy rule (drop pages) still applies.
- Downlink spoofing of Iridium with low-cost SDRs: arXiv 2603.12062 (2026) [S]: all six attack types feasible; already
  in the first report. Transmitter fingerprinting of ring alerts as a defence: SpaceSec 2024, arXiv 2402.05042 [S].

### Topic 2. LEO Doppler and orbit error handling, 2023 to 2026

**2.1 Orbit sources (what a sim should assume)**
- SpaceX publishes Starlink operator ephemerides on Space-Track: Modified ITC format with position and velocity
  covariance, 72 h of prediction, updated three times a day [S, starlink.com/satellite-operators]. Space-Track needs
  an account and has its own user agreement (not read).
- CelesTrak SupGP builds element sets from operator data, listing Starlink, OneWeb, Kuiper, Iridium, Orbcomm and
  others as sources [V]; its own accuracy table shows about 10 times smaller errors than standard GP for GPS (0.87 km
  vs 7.54 km average) and GLONASS (0.20 vs 3.30 km) [V]. No published accuracy figure for Starlink SupGP was found.
  Sim implication: an "operator ephemeris" tier between TLE (km) and precise (m) is real and free.
- Epoch-time adjustment of SGP4 against SpaceX data significantly reduces open-loop error [S, par.nsf.gov 10652787].

**2.2 Double-difference Doppler with along-track correction (simulation)**
- Hasan, Han, Shin, Kabir, Islam, "A Double-Difference Doppler Shift-Based Positioning Framework with Ephemeris Error
  Correction of LEO Satellites" (3DPose), arXiv 2409.05026, 2024 [V]. Simulation only, 0.1 Hz Doppler noise
  (optimistic), injected orbit errors ±2 to 3 km along-track, 200 m radial, 2 to 3 m/s radial, 0.5 m/s along-track.
- 3D RMSE: short baseline (1 to 2.5 km) about 0.25 m vs 3.0 m for plain differential; 35 km baseline about 0.6 to
  0.8 m vs about 40 m. Double differencing alone barely helps; the along-track correction does the work.
- Caution: 0.1 Hz noise and no clock or atmosphere error; treat as an upper bound.

**2.3 Online tracking while GNSS is good (STAN)**
- Kassas group STAN: a tracking mode fuses GNSS + LEO to refine orbits while GNSS works, then navigates on LEO
  [S, InsideGNSS]. Khairallah & Kassas "Ephemeris closed-loop tracking": 879.3 m and 817.7 m orbit error reductions on
  two Orbcomm satellites [S].
- Orbcomm/INS on a UAV: 31.7 m to 8.9 m after 30 s of GNSS loss [S]; matches the first report's 8.8 m entry.

**2.4 Starlink signal: new 2026 result**
- Qin, Humphreys, Psiaki, Bowman, "Pilots and Other Predictable Elements of the Starlink Ku-Band Downlink",
  arXiv 2602.02627, Feb 2026 [V abstract and summary]. Two 8-subcarrier edge-pilot bands, identical across frames,
  beams, channels and satellites; most QPSK symbols follow a fixed template (only 40 distinct 60-bit codes in 530
  frames). Full-frame processing gains about 48.4 dB. With a 5 MHz narrowband receiver, one edge-pilot band moves the
  TOA threshold from 6.2 dB to -12 dB SNR. Authors argue a 6 cm, under 200 g feedhorn becomes usable, including side
  beams. Bounds only, no position result.
- Sim/hardware implication: a narrowband (about 5 MHz) Ku receiver on the edge pilots may be enough; that is within an
  Airspy/SDRplay bandwidth after an LNB, though the LNB's own oscillator must be locked or modelled.
- Timing: Qin & Humphreys arXiv 2501.05302 [S]: Ku frame timing variability "substantially higher than 1 ns";
  pseudorange PNT not currently possible. SpaceX's FCC reply (WT Docket 25-110) says metre-level needs differential
  corrections SpaceX does not provide [S, InsideGNSS, with a May 2026 correction notice].
- Starlink Doppler with a low-cost wide-beam LNB: 3.6 m 2D / 6.2 m 3D [S, Satellite Navigation 2025, Ying Xu et al.];
  conditions (static, duration, orbit source beyond "suppresses TLE errors") not read. Treat as static.

**2.5 NR-NTN and direct-to-cell**
- Bachl, Nabeel, Lei, "Opportunistic Positioning with LEO Satellites based on SSB from NR NTN", arXiv 2607.00967,
  Jul 2026 [V abstract]: simulation with the real Starlink constellation; SSB Doppler plus SSB-derived pseudoranges
  with integer ambiguity solved from geometry; mean error under 10 m; receiver clock bias and drift estimated.
- arXiv 2608.10270 (2026) [S]: CRB for SSB-based NTN positioning; without decoding PBCH the SSB gives only Doppler.
- Starlink direct-to-cell currently uses LTE on 1.9 GHz PCS-band-class spectrum; satellites pre-compensate Doppler
  per beam (up to 24 ppm cited) so a phone sees a stable carrier [S, blog]. If pre-compensated to beam centre, the
  residual Doppler at the user still varies with position within the beam; no positioning paper on D2C signals found.
- Amazon Kuiper/Leo: no public signal description or acquisition paper found; D2D filing at 2483.5 to 2500 MHz [S].

**2.6 Other constellations**
- OneWeb with reference network (Komodromos, Morgan, Clements, Qin, Morrison, Humphreys, IEEE/ION PLANS 2025) [V
  abstract]: newly found sync sequences, sub-metre positioning and timing in a field test; UE "could be consumer-grade
  hardware with an omnidirectional antenna and a lower-quality clock". NET.
- Globalstar: better than 300 m horizontal (IEEE 2023) and better than 100 m with two satellites (Chinese paper) [S].
- Orbcomm on RTL-SDR: a patent describes RTL-SDR + VHF dipole + SGP4 comparison, no final figure [S]. A 2025 URSI
  paper (UAB) describes an Orbcomm SDR receiver [S].
- NOAA APT / Meteor LRPT: no low-cost positioning result found; Kassas "blind Doppler tracking with NOAA" is the only
  one (first report).

**2.7 Moving-platform Starlink results, now with full conditions** — GPS World "Modern NorthStar" article by the
research group [V, secondary but author-written]:
| Platform | Hardware | Sats | Outage | Unaided | LEO, TLE as is | LEO, orbit corrected |
| --- | --- | --- | --- | --- | --- | --- |
| Car, I-79 Pittsburgh, Jun 2025 | 2 NI X410, LNBF, 2.5 MS/s, tactical IMU, OCXO | 11 | 90 s, 2.25 km | 258 m | 150 m | 8.41 m |
| DJI M600 UAV, Columbus, Aug 2025 | NI 2955 USRP, LNBF, tactical IMU, OCXO | 9 | 55 s, 370 m | 46.51 m | 17.82 m | 8.15 m |
| Balloon, 25 km altitude, NM, Jul 2024 | 2 B205-mini, no IMU, altimeter | 5 | 50 s analysed | 83.34 m | — | 12.28 m |
| Ship off Baffin Island (Canada), Aug 2024 | B205-mini + Raspberry Pi 4, no IMU | 12 | 20 min, 8.5 km | 846 m | — | 123 m |
- Doppler noise variances used: 0.05 to 6.75 (m/s)² at 1 Hz (so σ about 0.2 to 2.6 m/s). Orbit correction is
  "online equivalent timing error compensation": the along-track TLE error is treated as a per-satellite time offset
  and estimated from Doppler residuals [V]. This is cheap and fits our EKF: one extra state per satellite.
- The ship row is the only result found with a Raspberry Pi 4 in the loop, and without an IMU it stayed at 123 m.

**2.8 Receiver/emitter clock grade vs single-pass Doppler geolocation** — Murrian, Narula, Iannucci, Budzien,
O'Hanlon, Psiaki, Humphreys, "First results from three years of GNSS interference monitoring from LEO", arXiv
2009.04093 [V]. Monte Carlo, single LEO pass, frequency offset modelled as constant per capture, clock random walk
h-2: TCXO 3e-21 gives a 6,900 × 690 m error ellipse; low-quality OCXO 3e-23 gives 720 × 72 m; OCXO 3e-25 gives
67 × 7.4 m. The geometry is reversed (emitter clock), but the same arithmetic applies to a receiver clock in Doppler
positioning [C]. Implication: a free-running dongle TCXO makes single-pass LEO Doppler kilometre-class unless the
receiver frequency is tied to something stable (LTE carrier, GPSDO in holdover) or estimated jointly over several
satellites at once.
- Differential LEO with asynchronous satellite clocks, base tracks satellite clocks and sends corrections to an
  8-state rover EKF: Bader, Saleh, Wymeersch, Seco-Granados, Noureldin, arXiv 2606.21621, Jun 2026 [V abstract], real
  urban vehicle data + simulation; no numbers in abstract. NET.
- Allahvirdi-Zadeh, El-Mowafy, Wang, "Doppler Positioning Using Multi-Constellation LEO Satellite Broadband Signals
  as Signals of Opportunity", NAVIGATION 72(2), 2025 [S]: differential model reaches sub-metre kinematic positioning
  "even with a limited number of satellites"; data source (real or simulated) not confirmed.
- Low-SNR Starlink, 10 satellites, static, 21.2 m 2D from a 100 km initial error [S, Kassas group].
- Starlink frequency drift above 20 ppm attributed to software design (Qin/Humphreys timing preprint) [S].
- Orbcomm OG2: 12 of 18 operational per one directory, date unknown [S]. Fewer passes every year.

### Topic 3. Cellular carrier phase with free-running oscillators

- Still no published carrier-phase navigation result with a free-running, undisciplined receiver oscillator was found
  (10 searches). Every experiment found uses a GPSDO, rubidium or a GNSS-derived receiver clock:
  - UniBw Munich (Hameed, Arizabaleta-Diez, Philips-Blum, Pany), "LTE transmitter states estimation using a combined
    code and carrier phase observation model", IEEE/ION PLANS 2023 [V slides]: USRP 2974 on a DJI M600 and on a van;
    the receiver clock offset is taken from RTKLib GNSS SPP during mapping; states [pos, float ambiguity, clock bias,
    drift]; target an Amarisoft test eNB at 2.665 GHz.
  - Lapin et al. TVT 2024 (below): rubidium-referenced USRP N310.
  - Khalife & Kassas UAV carrier phase (TAES 2020) [S]: Monte Carlo study of how receiver oscillator quality affects
    results; flights 2.94 m and 5.99 m RMSE (earlier, non-differential); the sub-metre 2022 result is in the first
    report.
- Cycle slips:
  - Kassas patent US 2021/0373180 / ION GNSS+ 2019 [S]: slips detected by comparing carrier phase on the eNodeB's
    multiple antenna ports (CRS port 0 vs port 1). 63.06 cm RMSE in one experiment [S].
  - Lapin et al. [V]: a third-order PLL with 18 Hz bandwidth tracks through a simulated 16 ppb tower frequency jump
    without slipping; 14 Hz slips one or two cycles. DLL 0.5 Hz gives about 10 m code noise at 10 dB SNR.
- Feasibility hints for cheap hardware (GNSS, not cellular): O'Driscoll & Curran showed fixed-ambiguity RTK with an
  RTL-SDR and a low-cost L1 patch [S], so the dongle's phase noise does not by itself prevent carrier tracking.
  R820T-based dongles show random phase drift from chip heating; heat sinks helped when two dongles shared one
  oscillator [S, Osmocom list]. Two-dongle coherence about -40 dBc at 75 kHz offset in one hobby report [S].
- Differential cellular carrier phase with a base receiver and UAV rover (Khalife & Kassas, IEEE T-IV 2023): EKF then
  batch WNLS, sub-metre over 2.24 km [S]. Base and rover both GPS-disciplined in the published setups.
- Physics point [C]: in a single receiver, the receiver clock is common to every tower and cancels in between-tower
  differences, so a free-running receiver oscillator is survivable if all towers are tracked on one ADC clock. It does
  not cancel across several RTL-SDR dongles unless they share one reference (KrakenSDR-style). The real limit for a
  cheap crystal is phase tracking through its jitter and temperature ramps in a narrow PLL; no paper measured this.
- Sim needs: carrier phase σ a few mm to cm in LOS; cycle-slip process (rate rising with low SNR and with tower
  frequency jumps); receiver clock as a common random walk with TCXO-class Allan deviation (TBC, about 1e-9 at 1 s
  for a dongle TCXO [M]).

### Topic 4. Cell tower clocks

**4.1 Lapin, Seco-Granados, Samson, Garcia-Molina, "Base Station Clock Offset of Cellular Measurements and Its Impact
on Positioning", IEEE TVT 73(10), Oct 2024, DOI 10.1109/TVT.2024.3409088** [V full text]
- Two commercial LTE eNBs near ESA ESTEC tracked continuously for 11 days (CRS, 2 kHz output, USRP N310 on rubidium).
- Main finding: the tower clock offset is driven by regular oscillator frequency jumps, probably periodic steering to
  the reference. BS-1 jumped about every minute; one jump changed drift from about 0 to about -0.3 m/s (about 1 ppb
  [C]) and built up almost -20 m before the next jump. BS-2's jumps were gradual and unbounded. Over 11 days the
  carrier phase span was 31.22 m on BS-1 and over 23 km on BS-2.
- Code and carrier move coherently (code-minus-carrier stays bounded), so the tower clock looks the same on both.
- Allan deviation similar below 1 s; BS-1 worse between 1 and 500 s; BS-1 better beyond 500 s.
- Prediction: a linear clock model fitted 1 to 10 s before GNSS loss; coasting 50 s cut simulated 5G HPE from 7.2 m
  (P=1e-1) / 68.8 m (P=1e-5) uncorrected to 1.2 m / 16.4 m; 1 to 10 s coasting about 0.6 m / 6.5 m. Optimal fit
  window differs per tower (1 s vs 10 s).
- 3GPP limit cited: ±50 ppb over 1 ms for wide-area BS (±15 m/s worst drift).
- Sim needs (replaces pure random walk): per-tower clock = piecewise-linear drift with jumps; jump interval about
  60 s for some towers; drift after a jump up to about 1e-9 (0.3 m/s); some towers smooth. The first report's
  "step-like frequency corrections (snippet)" is now [V].

**4.2 Same operator vs different operators**
- Winter, Morrison, Sokolova (SINTEF), Sensors 24(1):213, 2024 [S, via Lapin's citation]: tower clock offsets differ
  a lot between three operators but are similar within one operator. Already in the first report as Trondheim; the
  "same operator shares a reference" point is now supported by a citing paper's summary [S], still not [V].

**4.3 5G commercial network ICCB** — Xu, Brambilla, Camajori Tedeschini, Nicoli, IEEE Access 14, May 2026, DOI
10.1109/ACCESS.2026.3694117, CC BY 4.0 [V]: six gNBs at 3.68 GHz (two co-located on one pylon); uncorrected TOA
fluctuations exceed ±200 ns; ICCB stable over a 10-minute window with per-PCI standard deviation 6.2 to 7.1 m for
the co-located good-signal pair, higher for others; smoothing window 30 s best; mean error 12.7 to 20.6 m, 90 %
under 40 m. Upgrades the first report's entry to [V] and adds the noise numbers.

**4.4 Sector-to-sector** — Khalife & Kassas, "Modeling and Analysis of Sector Clock Bias Mismatch for Navigation with
Cellular Signals" [V]: this is cellular CDMA (883.98 MHz), not LTE. The mismatch between two sectors of one BTS is a
random walk (AR(1) with α1 about -1) with zero-mean Laplace increments, sampled at 5 Hz, observed over 5-minute
spans; cause given as antenna phase-centre and RF chain delay differences. The paper says ignoring it costs tens of
metres and tens of ns. The 10.51 m figure is a UAV CDMA flight. The size of λ was in a figure, not extracted.
- Carrier-to-carrier at one site: a patent quotes UTRAN figures, ±65 ns for adjacent carriers in one Node B and
  ±325 to ±525 ns inter-band [S]. LTE TS 36.104 time-alignment error limits [M]: 65 ns between MIMO ports, 130 ns
  intra-band contiguous CA, 260 ns intra-band non-contiguous and inter-band CA. Sim value: per-carrier offset at one
  site, constant, uniform ±(65 to 260) ns, TBC.

**4.5 FDD vs TDD and holdover**
- FDD needs frequency only: ±50 ppb (wide area), ±100 ppb (local), ±250 ppb (home) [S, 3GPP via GPS.gov 2012 deck].
  TDD needs ±1.5 µs phase at the air interface (TS 38.104), 5 µs for cells over 3 km radius [S].
- So Canadian 5G n78 (TDD) cells are phase-locked to GNSS/PTP; LTE FDD cells may or may not be (vendor and feature
  dependent: eICIC/CoMP need phase). This matters for both the clock prior and the jamming model.
- Holdover oscillators [S, vendors]: TCXO about 450 µs/24 h, OCXO 1 to 25 µs/24 h, rubidium about 1 µs/24 h.
- Spoofing a grandmaster causes slow drift that thresholds miss; detection above 95 % for drift above 0.5 ns/s in a
  simulation [V abstract, arXiv 2607.11398, 2026].
- **Tower clocks under live GPS jamming: one measurement found.** Kassas, Khalife, Abdallah, Lee, "I Am Not Afraid of
  the GPS Jammer: Resilient Navigation via Signals of Opportunity in GPS-Denied Environments", IEEE AES Magazine,
  Jul 2022 (ION GNSS+ 2020 conference version) [S, snippets only; PDF over the fetch size limit]: DT NAVFEST at
  Edwards AFB, Sep 2019, J/S up to 90 dB; only two LTE eNodeBs heard; "the relative stability between the LTE SOPs
  is maintained for more than 95 min during GPS jamming." Two towers, one test, desert site; it supports holdover
  being benign over 1.5 h but says nothing about steps at jamming onset. Corrects the first report's "no field
  measurement was found".
- Operators' statements [S]: Telenor (Norway) says jamming and spoofing do not affect its mobile network; Traficom
  (Finland) says mobile systems are designed to withstand prolonged GNSS disruption without significant service
  impact. Service continuity is not timing continuity; no timing data published.
- GNSS timing receivers (not eNodeBs) shown to jump in time under replay/meaconing (UniBw Munich) [S]; LTE-TDD needs
  1.5 to 5 µs, 5G under 300 ns for some features [S].
- No Canadian rule found that mandates GNSS/PTP sync for n78; ISED can impose TDD synchronisation for cross-border
  interference at 3900 MHz [S]. Treat Canadian 5G TDD as GNSS-phase-locked (physics of TDD), LTE FDD as TBC.
- No measured survey of eNodeB frequency offsets across many sites found; requirement-level values only (±50 ppb air,
  16 ppb backhaul; small cells ±100 ppb, 33 ppb) [S, Calnex test plan].

### Topic 5. 5G NR from drones
- No commercial-network 5G flight result found beyond the Kassas-group private/commercial work in the first report.
  The "3.35 m on a drone" figure appears in an NTU thesis literature table as "PBCH DM-RS carrier-phase SDR, 3.35 m
  RMSE over 500 m" [S]; platform not confirmed.
- Ground vehicle, five commercial gNBs: 4.1 m RMSE over 773 m [S, InsideGNSS "Carpe Signum"]. UCI real 5G: 14.9 m
  RMSE [S]. On-demand 5G "ultimate reference signal" (IEEE SPL 2023): 10 dB C/N0 gain over SSB-only [S].
- SSB beams and angle: patents propose SSB index codebooks with angular info; no measured commercial SSB-AoD
  positioning found. Chalmers: single-BS mmWave positioning with a commercial BS and custom beam sweep (vehicle) [S].
  TU Dortmund: beam pointing as bearing for UAV/V2X at 28 GHz (VTC 2020) [S].
- Canada mmWave: no commercial mmWave yet; ISED auction of 26 and 38 GHz starts 19 Oct 2027 [S, ISED and press].
  So mmWave AoD is sim-only for Ottawa through at least 2028.
- Indoor private 5G TDOA: sub-metre 95 % in a hall (TU Dortmund, PerCom workshops 2026) [S]. NET (private network).
- U. Washington MSc thesis 2021 (Kuni) flight-tested RSSI-based cellular multilateration on a small UAS: not feasible
  for navigation, attributed to path-loss model error [S]. A useful negative result: RSSI ranging is not worth
  modelling as a primary source.

**5.x Closest analogue to our build: BYU MSc thesis** — Tyler Sweat, "GNSS-Denied Navigation Using LTE Signals of
Opportunity on Low-Cost, Low-SWaP Hardware", Brigham Young University, Apr 2025, ETD 10777 [V abstract]:
differential pseudorange between an LTE tower and a mobile receiver built on a low-cost, low-SWaP SDR, fused with
inertial data in an EKF; flight test 8.03 m RMSE, 14.6 m max. Full text (22.5 MB) returned 403; SDR model, clock and
reference-station setup not read. NET if the differential reference is a separate ground receiver with a link. This
is the best direct comparison for the team's LTE pseudorange result and is worth reading in full.

### Topic 6. Angle of arrival from small platforms
- Winter, Morrison, Hasler, Sokolova (SINTEF/NTNU), "Exploitation of 5G, LTE, and AIS Signals for Fallback UAV
  Navigation", Eng. Proc. 88:49, 2025 (ENC 2024), DOI 10.3390/engproc2025088049, CC BY [V full text]:
  - AoA system: KerberosSDR (4 coherent RTL-SDRs) + Raspberry Pi 4, about EUR 500, on AIS shore/ship transmitters
    that broadcast their own position (easy association). Simulated σAoA 3°.
  - Cellular system: one USRP B200 per tracked tower + x86 PC + possibly rubidium, about EUR 10,000.
  - Simulated INS aiding, RMS error (m): 1 beacon AoA 956 / range 440; 2 beacons 352 / 20; 3 beacons 392 / 15;
    6 beacons 56 / 11; 6 beacons without altimeter 1024 / 23. σrange 25 m, σvelocity 5 m/s used (deliberately
    pessimistic).
  - Trondheim tower clocks [V, restated]: two of three operators 1 to 5 m (3 to 16 ns) peak to peak over an hour
    including receiver clock; third operator stepped drift, piecewise constant, several hundred m per hour.
  - Says transmitter clock bias can be learned while GNSS is good, and receiver clock removed by using several
    uncorrelated towers, ideally from different operators. Notes Norway hid tower positions in 2022.
- Aalto: rotating directional antenna on a hovering drone, 6.02° AoA error, median under 45 m in a simulated LOS
  macro network (first report). A 2025 Aalto doctoral thesis extends it to 3D and hardware imperfections [S].
- Drone-tracking UCA (6 elements): 1.15° static, 1.86° dynamic average error [S, preprints.org 202503.0252] (ground
  array looking up, not on the drone).
- Massive-array vehicle SLAM with LTE multipath delays and AoA: under 6 m after 530 m vs 15 m dead reckoning [S,
  arXiv 2301.07560]. Large array, not drone-sized.
- Array calibration: aircraft with known ADS-B positions used as calibration sources for DF array phase bias
  (USNC-URSI 2024) [S]; self-calibrating SDR array with a reference transmitter (arXiv 2604.02498) [S, TX for calib].
- VOR with RTL-SDR: hobby decoders report about ±1° to ±3° [S]; no airborne small-drone test.
- Heading from AoA: patents only (two towers, array on vehicle); no measured heading accuracy found. Not saturated in
  the sense of results; saturated in the sense that searching keeps returning patents.
- KrakenSDR vendor note: below about 900 MHz cable lengths must match within 1 cm [S]. On a drone, airframe and
  rotor blockage are untested in public.
- Sim needs: bearing σ 1 to 3° plus per-installation bias up to 10° (first report), heavy-tailed multipath outliers,
  range-dependent position error (constant angle error grows with range).

### Topic 7. Pseudorange error vs altitude, air-to-ground cellular
- Still no altitude-binned ranging-error statistics found (5 searches).
- What exists:
  - LOS probability, 3GPP TR 36.777 [S, arXiv 1805.00826]: terrestrial model below 22.5 m (UMa/UMi) or 10 m (RMa);
    100 % LOS above 100 m (UMa) and 40 m (RMa); UMi has no upper threshold (antennas below rooftop).
  - Rician K-factor rises with height (3.565 GHz 5G campaign, IEEE Access 2024) [S]; LTE passive air-to-ground
    campaign with CRS-based CIRs, five vertical and five horizontal routes (Cai et al., TVT 2019) [S, no numbers in
    abstract].
  - Interference: median SINR at 40 m and 120 m about 11 dB below ground (rural 700 MHz simulation, arXiv 1707.07534)
    [S]; steepest degradation between 20 and 40 m (survey) [S]; flights at 330 m ASL gave 15 to 20 dB more signal and
    3 to 4 times more handovers due to many visible cells (arXiv 2605.27755, 2026) [V abstract].
  - Kassas group asserts UAVs "do not suffer severe multipath" [S] without altitude-binned data.
  - High-altitude aircraft (C-12, 5,000 to 15,000 ft AGL, 51 to 57 km trajectories): cellular-only RMSE 10.53, 4.96,
    15.44 m; 11 SOPs heard on one flight (six 3G, five LTE); EKF clock process noise used for a receiver TCXO
    Q = [[9.57e-5, 2.52e-8],[2.52e-8, 1.89e-6]] and tower OCXO Q = [[3.11e-7, 2.52e-11],[2.52e-11, 1.89e-9]] at a
    26.7 ms step (Kassas et al., IEEE ITS Mag. 15(4), 2023) [V].
- UAV cellular pseudorange error after removing the clock difference (Maaref & Kassas, "UAV Integrity Monitoring
  Measure Improvement using Terrestrial Signals of Opportunity", ION GNSS+ 2019) [V]: several hours of UAV flights;
  Gaussian fit σ 0.75 m open-sky/semi-urban (CDMA 1.23 MHz, 2 to 8 towers) and σ 1.23 m urban (LTE 10 MHz, 11 towers,
  739/1955/2125/2145 MHz). Altitude not binned. GPS+SOP RAIM cut UAV VPL 57.76 % (22.21 to 9.38 m) over 823 m urban.
  Caveat [C]: the clock-difference removal absorbs slowly varying biases, so these σ are noise, not total error.
- Operational 5G network synchronisation instabilities can produce ranging errors around ±60 m [S, 2024/2025 paper
  cited by search; not read].
- Sim needs (TBC): LOS probability per TR 36.777; at our 30 to 120 m, many more cells above detection threshold but
  lower SINR, so model PSS/SSS detection probability vs SINR and a per-cell NLOS bias that falls with height.

### Topic 8. Broadcast signals
- ATSC 3.0 BPS time transfer, NIST: Sherman & Howe, "Field test of ATSC 3.0/BPS precise time distribution", NAB BEIT
  2025 [V abstract]: KWGN Denver, receivers at two NIST sites up to 106 km away, 50 days, 30 km NLOS terrain-blocked
  path: peak-to-peak time deviation tens of ns, comparable to single-band GPS timing receivers.
- NAB claims about 15 to 20 ns in a 2025 demo (standard: under 100 ns) [S, vendor]; DOT gave NAB US$744k (Oct 2025)
  for a field trial with Dominion Energy [S]; positioning (multilateration) demo planned 2027 to 2029 [S].
- Canada: no ATSC 3.0 adoption decision found by CRTC/ISED in 2026 [S]; a Humber College (Toronto) BPS demo deck
  exists (403, unread). BPS is US-only for planning; Ottawa receives some US stations only at long range [M].
- ATSC 1.0: field sync PN511 every about 24 ms; transmitter clocks not GNSS-grade, so a monitor station measures
  offsets (Rosum) [S]. Pilot at 309.44 kHz above the lower band edge; some stations GPS-lock the pilot, tolerance
  ±3 Hz of an assigned offset in one engineer's account, and a station's GPS receiver was seen unlocked under
  interference [S]. 6 MHz bandwidth: needs at least about 6 MS/s, above an RTL-SDR [C].
- DVB-T 11 m RMS urban (EUSIPCO 2012) [S]; DVB-T/T2 SFN indoor inverse-radar under 50 m target (2024) [S]. Not used
  in Canada.
- DAB: TDOA with null symbol and phase reference symbol, double difference against a reference receiver (arXiv
  2605.26545, SIU 2026) [V abstract, no numbers]. DAB not used in Canada [M].
- HD Radio (IBOC): OFDM subcarriers 181.7 Hz apart; narrow bandwidth and long symbols; no positioning test found; one
  Ottawa station's HD feed reportedly discontinued [S].
- FM/AM: no new 2023 to 2026 result; 2008 DTIC study found weak FM autocorrelation peaks [S].
- Reference-station clock learning: Maul, Klob, Robert (TU Ilmenau), arXiv 2306.04586, 2023 [V abstract]: low-cost
  off-the-shelf front ends at separate sites synchronised from broadcast SoOs by cross-correlation: 200 ps and 6 mHz
  achieved in real measurements. This is the base-station side of what we would do with a ground laptop reference.
  NET (needs the link).

### Topic 9. Unconventional radio sources
- UAT (978 MHz) ground stations as APNT: Lo & Chen, NAVIGATION 68(2), 2021, DOI 10.1002/navi.424 [V]: flight range
  accuracy 20 to 30 m (2σ) excluding bias; horizontal mean 29 m, σ 22 m; stations only flagged within 500 ns of UTC.
  UAT is not used in Canada [M], so US-only.
- Mode N (DFS Germany): Mode S-like TDMA ranging on an unused DME channel, 4-station test range at Manching, first
  track 20 Sep 2023 [S]; modelled 13 m 1σ range accuracy [V, GPS World Nov 2021]. Needs new ground transmitters. Same
  article [V]: DME total 2σ 92 m (46 m one-way), 1090ES differential arrival time bias about 10 m, σ under 10 m.
- Passive DME by triggering replies to a non-existent aircraft: implies something interrogates; our payload cannot
  (TX). Listening to replies triggered by other aircraft remains research-only (first report).
- ADS-B in reverse: patent US 10244364 (small UAS locating itself from other aircraft's ADS-B TDOA) [S]; RSSI-only
  ADS-B self-localisation under 0.8 km in 2 min (URSI AT-RASC 2024) [V]. Failure mode for our use [C]: under regional
  GNSS jamming the other aircraft's broadcast positions degrade too, so ADS-B anchors are not independent of GNSS.
- AIS: R-Mode (ranging sequences inside AIS/VDES slots, needs modified shore stations) targets 10 to 100 m, coastal
  only [S]. Ottawa: not relevant except the river; St Lawrence shore stations far.
- Wi-Fi from the air: RFEye locates Wi-Fi emitters from a UAV at 1.03 m 2D median (outdoor) [S]; Android network
  location on a drone: about 32 to 38 m RMS suburban/urban, 1,637 m rural [S, Drones 6(2):35]. Hashing BSSIDs at
  capture (ADR-0011) still allows matching against a database only if the database is hashed the same way [C].
- LoRaWAN: gateways timestamp at about 1 ms unless GPS-PPS fitted; Class B beacons need 1 µs gateway timing;
  commodity TDOA sub-km [S]. Beacons are sparse (every 128 s). Low value.
- GEO / SBAS / Inmarsat: VIAVI SecureTime GEO sells GNSS-independent time over Inmarsat L-band, claims under 100 ns
  [S, vendor, NET subscription]. SBAS GEO ranging is part of GNSS time and sits in the jammed L1 band [C].
- Satellite TV GEO direction for heading: patents only, no measured accuracy.
- Weather/ATC radar scan timing: nothing published on self-location. Passive SSR (Litchford patents US 4115771,
  US 5198823; 2024 patent US 2024/0192356) uses the 1030 MHz interrogation timing and beam rotation to locate other
  aircraft [S]. Untested idea [C]: a receive-only payload hearing the main beam of a known SSR sweep at time t gets
  its azimuth from the radar if the rotation phase is learned while GNSS is good (like a VOR made from a radar).
  Sim-only; needs the radar's site and rotation period; airport SSRs rotate every few seconds.
- LDACS (L-band air-ground datalink) ranging: about 20 m σ or better in DLR flight trials (2012 to 2018), DME
  co-site interference noted; 5 to 6 stations meet RNP 0.3 around Frankfurt/Munich in models [S]. Not deployed;
  Europe-only. Passive radar self-localisation with broadcast illuminators: nothing found.
- VDL Mode 2: listed only as a multilateration signal; no positioning use.
- Xona Pulsar: 6 production satellites launched Oct 2026, initial service 2027, 258 planned; vendor specs 2 cm H /
  4 cm V (with corrections), timing under 10 ns; "Pulsar Verified" receiver programme since 9 Jul 2026 with Trimble and
  Septentrio; Furuno received live signals Jun 2026; ION ITM 2026 single-satellite test "metre-level" (arXiv
  2602.06376) [S]. NET (subscription expected).
- TrustPoint: C band, soft launch 2027; 40 satellites contracted to EnduroSat (Sep 2026); Calian (Canadian) C-band
  antenna tracked a live TrustPoint signal (Oct 2026); NovAtel receivers under a NAVAIR contract; no accuracy number
  published [S].
- Iridium PNT ASIC: see 1.6.

### Topic 10. Radio SLAM and mapper/navigator
- Kassas, Khairallah, Khalife, Lee, Jurado et al., "Aircraft Navigation in GNSS-Denied Environments via Radio SLAM
  With Terrestrial Signals of Opportunity", IEEE T-ITS 25(10), Oct 2024 [V abstract]: C-12 aircraft, industrial IMU +
  altimeter, tower clocks always unknown and estimated. 3D RMSE with towers all unknown vs all known: 43.27 vs 10.14 m
  (semi-urban, holding, about 5,600 ft); 89.82 vs 16.97 m (urban, 6 SOPs, 72.7 km); 36.42 vs 18.62 m (semi-urban
  descent, 18 SOPs, 111.9 km); 67.01 vs 25.65 m (rural grid, 32 SOPs, 78.4 km). Knowing tower positions halves to
  quarters the error; unknown positions still bounded over tens of km.
- UniBw Munich PLANS 2023 (topic 3): carrier-phase transmitter localisation using GNSS-derived receiver clock while
  mapping; float ambiguity state.
- Mapper/navigator: the sector-mismatch paper (4.4) and radio-SLAM motion planning (greedy, provable) [S].
- Tower maps: ISED Spectrum Management System site data (Site_Data_Extract.zip, monthly; ArcGIS mirror twice yearly,
  last CSV seen dated 29 Jan 2024) lists licensed site coordinates [S]. Accuracy not documented. Crowd maps:
  Mozilla's model locates coverage, not the mast; OpenCelliD sparse in places [S, anecdotal]. No measured accuracy
  study found.
- Tower localisation from user data [S]: Vienna 4G/5G drive-test dataset (arXiv 2603.02638, 2026) 38.55 m RMSE
  over validated LTE sites, sector azimuth errors about 28°; TU Wien crowdsourced timing advance on 4,946 LTE cells,
  about 100 m mean error, 5.8 % samples with negative multipath (bad data); 190 eNodeBs from drive tests under 100 m;
  patents quote about 300 m from drive tests. So a crowd-sourced tower map is a 40 to 100 m prior, and the radio-SLAM
  numbers above show what that costs.
- Mapper/navigator with carrier phase (Khalife & Kassas 2018 to 2022): mapper UAV + navigator UAV 63.06 cm;
  single UAV relying on tower clock stability 36.61 cm and 88.58 cm, sub-metre for over 5 min [S].
- Fingerprinting from the air: nothing measured at UAV altitude found (2 searches); RSSI multilateration on a UAS
  failed in a UW MSc flight test (topic 5).

### Topic 11. Public datasets (owner go-ahead needed before any download)
| Dataset | Content | Licence (read today?) |
| --- | --- | --- |
| FGI Jammer Test 2023 Repository, DOI 10.23729/fd-06d27736-45cb-3ca2-aff8-725d42c6caeb (Etsin/IDA) | LabSat 3 Wideband, 1575.42 MHz, 30.69 MS/s, 16-bit IQ, GPS L1 C/A + Galileo E1: high-power jamming 400 s; incoherent spoofing 896 s; coherent spoofing 1,174 s | CC BY 4.0 [V, research.fi record] |
| FGI OSNMA datasets (incl. Jammertest 2023 spoofing replays) | GNSS IQ | CC BY 4.0 [S] |
| FGI-SpoofRepo (Oct to Nov 2023 data, released 29 Feb 2024) | GNSS spoofing IQ | CC BY 4.0 [S] |
| Tuni2025 GPS / Galileo spoofing (Zenodo 15623460 etc.) | lab, USRP-2945R, 50 MS/s float32, about 30 GB per scenario, 1 to 4 spoofers | CC BY 4.0 [V] |
| Wang/Sankari/Lohan/Valkama GNSS RFF (Zenodo 13846381) | IQ with/without spoofing, only 1000-sample subsets public | CC BY 4.0 [S] |
| OAKBAT (ORNL DOIs 10.13139/ORNLNCCS/1668343, /1664429, /1665888; github.com/oakbat) | GPS L1 C/A, Galileo E1, pure tones | No licence stated; acknowledgement text requested [S] |
| PolyU Iridium Doppler (with arXiv 2509.17198) | 436 Doppler measurements, 8 satellites, about 35 s, static | Stated "publicly available"; licence not seen [S] |
| Oligeri et al. Iridium ring alerts (WiSec 2020) | 1000+ h of ring-alert messages | Released; licence not seen; contains pages, so privacy rules apply [S] |
| AERPAW LTE IQ from UAV (arXiv 2303.01635) | already in first report | CC BY 4.0 behind IEEE DataPort |
| DTU LTE drive test (IEEE DataPort 2249) | processed RSRP/SINR with lat/lon, no IQ | free IEEE login [S] |
- Still no public LEO IQ with ground truth, and no commercial-network cellular IQ from a moving platform with ground
  truth.

### Topic 12. Venue sweep
- ION GNSS+ 2025 programme not reachable through search; InsideGNSS summary only [S].
- NAVIGATION 2024 to 2025: Baron/Gurfil/Rotstein 71(2) (simulation, Doppler Jacobians) [V]; Allahvirdi-Zadeh et al.
  72(2) [S]; Kozhaya/Saroufim/Kassas "Unveiling Starlink for PNT" Mar 2025 (first report).
- IEEE/ION PLANS 2025: Komodromos et al. OneWeb [V]. PLANS 2023: UniBw LTE carrier phase [V].
- IEEE TVT 2024: Lapin et al. [V]. IEEE Access 2026: Xu et al. [V]. IEEE T-ITS 2024: radio SLAM aircraft [V].
- ION PTTI 2026: NIST Iridium timing [V].
- arXiv 2026 additions: 2602.02627 (Starlink pilots), 2603.15908 (Iridium snapshot), 2606.21621 (differential LEO),
  2607.00967 (NR-NTN SSB), 2607.10241 (Iridium pass pairs), 2607.11398 (TDD spoof detection), 2605.27755 (UAV
  cellular vs Starlink), 2605.26545 (DAB TDOA).
- Theses: BYU MSc 2025 (Sweat) [V abstract]; TU Delft MSc 2025 DopTrackBox (COTS Doppler tracking network) [S]; CTU
  MSc 2024 (Voska, Iridium/Orbcomm/Starlink SDR) [S, PDF fetch failed]; UW MSc 2021 (Kuni) [V abstract]; Aalto
  doctoral thesis 2025 (drone AoA) [S].

## 3. Corrections to the first-round report
| First report says | Correction | Evidence |
| --- | --- | --- |
| 16.3: "No field measurement [of tower holdover under jamming] was found, only patents" | One exists: two LTE eNodeBs kept relative clock stability for more than 95 min under GPS jamming (J/S up to 90 dB), Edwards AFB 2019 | [S] IEEE AES Mag. 2022 |
| 16.2: "Towers make step-like frequency corrections (snippet)" | Upgraded and quantified: jumps about every minute on one tower, up to about 1 ppb (0.3 m/s) drift change, about 20 m build-up between jumps; another tower smooth but unbounded (23 km over 11 days) | [V] Lapin et al. TVT 2024 |
| 6.3: Trondheim same-operator vs cross-operator figures | Confirmed in the authors' later paper: two operators 1 to 5 m (3 to 16 ns) p-p per hour incl. receiver clock; third operator stepped drift of several hundred m per hour | [V] Winter et al. Eng. Proc. 2025 |
| 6.1: Iridium paid service "timing under 205 to 300 ns (snippet)", "position 20 to 50 m (memory)" | Timing: under 40 ns max offset, MTIE under 80 ns (60 ns with iono corrections) over 40 days with a miniature atomic clock (NIST). Position: 26.6 m H / 16.8 m V at 95 %, 100 days static (EC JRC); vendor board median 25 to 42 m | [V] NIST PTTI 2026 abstract; [V] InsideGNSS on JRC; [S] vendor |
| 6.1: "With one Orbcomm satellite added: 22.7 m (snippet)" | Context: one Orbcomm + four Iridium NEXT, static, Kassas group 2021 | [S] |
| 16.2: "One Iridium satellite, a base station and an industrial IMU: 8.32 m" | Not found. Closest: 2 Orbcomm + 1 Iridium, differential, industrial IMU, ground vehicle, 7.13 m (vs 41.29 m non-differential) | [S] |
| 6.1 moving-platform table, drone row "via the market report" | Now with full conditions: DJI M600, NI 2955 USRP, OCXO, tactical IMU, 9 Starlink, 55 s/370 m outage: 46.51 / 17.82 / 8.15 m; plus a Raspberry Pi 4 ship test off Baffin Island at 123 m | [V] GPS World article by the group |
| 16.2: "5G: 3.35 m on a drone with four stations (snippet)" | Source appears to be a PBCH DM-RS carrier-phase SDR result over 500 m quoted in an NTU thesis table; platform unconfirmed. Keep as [S], do not cite as a drone result | [S] |
| 16.2 Polimi 5G entry | Now [V]: IEEE Access 14 (May 2026); ICCB std 6.2 to 7.1 m for co-located PCIs, ±200 ns raw TOA swings, 30 s smoothing | [V] |
| 6.3: "LTE code phase on a drone: 8.15 m (snippet)" | That number is the Kassas 3-eNodeB UAV result (σ 2.83 m). Separately, a 2025 BYU MSc on low-cost low-SWaP SDR got 8.03 m RMSE in flight with differential pseudoranges + IMU | [S]; [V abstract] |
| 6.4: "ATSC 3.0 BPS 100 ns timing claimed (snippet)" | NIST measured tens of ns peak to peak over 50 days on a 30 km NLOS path | [V abstract] |
| 6.2: "Iridium published orbits 100 m to several km" | Add: CelesTrak SupGP (operator data) lists Iridium, Starlink, OneWeb, Kuiper, Orbcomm as sources; about 10× better than GP for GPS/GLONASS. Starlink operator ephemerides with covariance on Space-Track, 72 h, 3× daily | [V], [S] |
| 16.3: bearing model "about 0.5° precision + up to 10° bias" | Unchanged; add SINTEF used 3° σ for a KerberosSDR on AIS and found it far worse than cellular ranging in simulation | [V] |
| 7.5: "Every device wide enough for a full 20 MHz LTE carrier can also transmit" | Unchanged. Note: SINTEF priced their cellular system at about EUR 10,000 (USRP per tower + rubidium) vs EUR 500 for KerberosSDR AoA | [V] |

## 4. Searches that found nothing
- An Iridium-only (or Iridium-led) position fix flown on a small drone; any airborne test of the Iridium paid service.
- A cellular carrier-phase navigation result with a free-running, undisciplined receiver oscillator.
- Altitude-binned cellular pseudorange error statistics at 30 to 150 m.
- Tower timing behaviour observed at Jammertest (any year), and operator timing logs under jamming.
- A measured survey of eNodeB frequency offsets across many sites; measured LTE carrier-to-carrier offsets at one site.
- Positioning with Starlink direct-to-cell (LTE) downlinks; Kuiper/Amazon Leo signal structure.
- Commercial-network SSB beam (AoD) positioning; any drone flight on commercial 5G SSB TOA.
- Heading from cellular AoA with a measured heading error; airborne FM bearing tests.
- HD Radio positioning; ATSC 3.0 in Canada; NOAA/Meteor positioning with an RTL-SDR.
- Weather or ATC radar scan timing used for self-location; VDL Mode 2 ranging; passive radar self-location.
- Measured accuracy of crowd-sourced tower maps vs surveyed masts (only timing-advance studies, 40 to 100 m).
- Public LEO IQ with ground truth; public commercial-network cellular IQ from a moving platform with ground truth.
- OAKBAT licence text.

## 5. Judgement per topic
1. **Iridium.** More searching would mostly re-find the same 2020 to 2026 static results. The open question (Iridium
   Doppler on a moving drone with a cheap oscillator) is unanswered because nobody has published it, not because the
   search missed it. The 2.8 clock-grade table says why: a free-running TCXO makes single-pass Doppler km-class. The
   next step is simulation and one ground capture, not more reading. The paid-service board (10 g, receive-only) is
   the one product worth tracking.
2. **LEO.** Not saturated: 2026 is producing a paper a month (pilots, NR-NTN SSB, differential under async clocks).
   Worth one more pass in a few months, especially for NR-NTN/D2C and Kuiper signal details. For the sim, the
   numbers are now sufficient: orbit error as a per-satellite along-track time offset, Doppler σ 0.2 to 2.6 m/s,
   clock grade per 2.8.
3. **Carrier phase, free-running clock.** The negative result is solid after 10 searches across two rounds: every
   published flight used a GPSDO/OCXO. More searching will not change that; only an experiment will. The supporting
   hints (RTL-SDR RTK on GNSS, receiver clock common to all towers) make it plausible but unproven.
4. **Tower clocks.** Near saturation. Lapin 2024 (frequency jumps) and the Edwards jamming observation are the two
   key new facts. A field survey of many towers' offsets does not appear to exist publicly. Further value would come
   from our own captures.
5. **5G from drones.** Not saturated, but the published base is thin: Canada has no mmWave until after Oct 2027, and
   commercial SSB results stay at 12 to 20 m mean with a reference receiver. More searching might find 1 or 2 UAV
   papers; it will not change the sim model much.
6. **AoA.** Near saturated; remaining hits are patents. Good enough to model.
7. **Error vs altitude.** The specific statistic seems not to exist publicly. The best proxies are TR 36.777 LOS, the
   UAV σ 0.75 to 1.23 m (noise only), and interference rising with height. Further searching has low expected value;
   the AERPAW dataset (first report) is the only way to measure it without our own flights.
8. **Broadcast.** Near saturated for Ottawa relevance: ATSC 1.0 is the only broadcast with ranging structure here and
   needs about 6 MS/s; BPS and DAB/DVB are not available in Canada.
9. **Unconventional.** Broad and shallow by design (1 to 2 searches per sub-source). Nothing found changes the
   ranking: Iridium paid service, ADS-B (but anchors fail under regional jamming), Xona/TrustPoint (2027, NET) are the
   only items with numbers. The SSR-sweep bearing idea is new and unpublished.
10. **Radio SLAM.** Not saturated but the key numbers are in: known towers 10 to 26 m vs unknown 36 to 90 m on an
    aircraft with an industrial IMU; crowd maps carry 40 to 100 m of tower error. More searching may add UAV-scale
    radio SLAM results.
11. **Datasets.** Near saturated. Jammertest 2023 (FGI, CC BY 4.0) and Tuni2025 (CC BY 4.0) are usable for spoof
    detection work with an owner go-ahead; OAKBAT licence unresolved. No LEO or cellular moving-platform IQ dataset.
12. **Venues.** Near saturated for what search engines index; ION conference programmes are poorly indexed, so a
    direct look at ION's proceedings table of contents (GNSS+ 2025, ITM/PLANS 2026) would be the efficient next step.
