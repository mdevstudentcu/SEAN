# Antenna build guide

- **Status:** Fallback only (2026-11-09). The antennas are bought ([`bom.md`](bom.md) section 3) because nobody is free to build them this week. Use this guide only if a bought antenna fails or misses delivery.
- **For:** whoever is in the EDC mechatronics workshop on Monday. Parts and sources are in [`bom.md`](bom.md).
- **Receive-only.** These antennas only feed our SDRs (ADR-0001, REQ-07). Nothing here is ever connected to a transmitter.

Three antennas, about 2 hours total for someone who has soldered before:

| # | Antenna | Signal | Polarization | Feeds | Goes on |
| --- | --- | --- | --- | --- | --- |
| A | Quarter-wave ground plane, 1090 MHz | ADS-B (aircraft) | Vertical | SDR A (FlightStick) | Payload: drone, handheld, vehicle |
| B | Quarter-wave ground plane, LTE band | Cell towers | Vertical | SDR B (NESDR) | Payload: drone, handheld, vehicle |
| C | Horizontal half-wave dipole, 114.6 MHz | YOW VOR | **Horizontal** | SDR B (NESDR), time-shared with LTE | Handheld and vehicle only (1.25 m wide: not on the drone) |

Build **A** first (it gets a quick on-air check from aircraft anywhere near YOW), then **C**, then **B** once the RF survey says which LTE band to cut it for.

## 1. Parts and tools

### Per antenna

| Part | A (ADS-B) | B (LTE) | C (VOR) |
| --- | --- | --- | --- |
| SMA male → SMA female bulkhead pigtail, RG316, 30 cm | 1 | 1 | 1 |
| Solid copper wire, 14 AWG (1.6 mm) | ~35 cm | ~55 cm | ~1.3 m |
| Solid copper wire, 20 AWG (0.8 mm), short stub | — | 1 × 10 mm | 1 × 10 mm |
| Single-sided copper-clad PCB, ~50 × 50 mm | 1 | 1 | 1 (smaller is fine) |
| PVC pipe (~20 mm) or a wood strip, ~1.4 m | — | — | 1 |
| Heat-shrink, cable ties, electrical tape | some | some | some |
| Clip-on ferrites (optional) | — | — | 2 |

Where to get 14 AWG solid copper: the bare ground wire inside household cable (NMD90 / "Romex") is exactly this. 1.5–2 mm brass rod also works and is stiffer.

### Tools

Soldering iron and solder, side cutters, wire strippers, metric ruler (calipers if available), drill with a 6.5 mm (or 1/4") bit, file or sandpaper, pliers, protractor (or eyeball 45°), multimeter.

### Know your connector

The bulkhead end of the pigtail is the antenna end:

```
   centre socket (hollow, ~0.9 mm)  ← the radiator / one dipole arm goes here
        │
  ┌─────┴─────┐
  │  threaded │  ← 1/4"-36 thread (6.35 mm), outer body = coax shield (ground)
  │   body    │
  ├───────────┤  ← nut
  │  flange   │
  └─────┬─────┘
        │ RG316 coax, 30 cm
        ▼
   SMA male  → screws onto the SDR, or onto the bundle's magnetic base (adds its 2 m RG58)
```

The centre socket takes a pin up to about 0.9 mm. **14 AWG (1.6 mm) does not fit.** Use a short 20 AWG (0.8 mm) stub as an adapter (section 2, step 3).

## 2. Common method: ground-plane antennas (A and B)

```
                 │  radiator (length R), vertical
                 │
                 │
     ────────────●────────────   ← PCB plate, copper side up, bulkhead through it
      ╲      ╱   ║   ╲      ╱
       ╲    ╱    ║    ╲    ╱       4 radials (length G each), 90° apart,
        ╲  ╱     ║     ╲  ╱        bent ~45° downward
                 ║
              coax down to SDR
```

Why the radials droop: flat radials give about 36 Ω; drooping them to about 45° brings the feed close to the SDR's 50 Ω.

### Steps

1. **Cut the wire.** Cut one radiator (length R) and four radials (length G each) from the 14 AWG, using the table for your antenna. Cut each piece **3 mm long**; you trim at the end.
2. **Prepare the plate.** Drill a 6.5 mm hole in the centre of the PCB. Push the bulkhead through from the copper side so the socket points up out of the copper side, and tighten the nut down onto the copper. Lightly sand the copper around the nut and **tack-solder the nut to the copper** at two points, so the plate is solidly grounded to the coax shield.
3. **Make the centre pin.** Push 5 mm of a 10 mm piece of 20 AWG into the centre socket and solder it (small iron tip, quick heat: the insulator inside the connector is PTFE and tolerates soldering heat, but don't cook it). For antenna A you can instead use 20 AWG for the whole radiator, which fits the socket directly.
4. **Attach the radiator.** Lap the bottom 5 mm of the 14 AWG radiator against the 20 AWG stub and solder them together. Slide heat-shrink over the joint. **Measure R from the top of the connector's white insulator to the radiator tip, including the joint.**
5. **Attach the radials.** Solder the four radials to the copper at 0°, 90°, 180° and 270° around the connector, starting about 3 mm from the nut. Measure G from the solder point to the tip.
6. **Bend.** Bend each radial down to about 45° below the plate. Keep the radiator straight and vertical.
7. **Trim.** Trim radiator and radials to the final lengths in the table. A receive antenna is forgiving: ±2% costs almost nothing.
8. **Check with the multimeter** (section 5) before connecting it to an SDR.

### Dimensions

Formulas (thin wire, the usual ground-plane rule): radiator R = 71,300 / f(MHz) mm, radials G = 75,000 / f(MHz) mm, with f the band centre.

| Antenna | Band (downlink) | Centre f | Radiator R | Radials G (×4) |
| --- | --- | --- | --- | --- |
| **A: ADS-B** | 1090 MHz | 1090 MHz | **65 mm** | **69 mm** |
| **B: LTE, 850 MHz** (band 5) | 869–894 MHz | 882 MHz | **81 mm** | **85 mm** |
| B: LTE, 700 MHz (bands 12/13/17) | 729–756 MHz | 742 MHz | 96 mm | 101 mm |
| B: LTE, 600 MHz (band 71) | 617–652 MHz | 635 MHz | 112 mm | 118 mm |

**Which B to build:** the RF survey (`CellSearch` over 617–894 MHz) decides. If you have to build before the survey, build the **850 MHz** version. `data/reference/cells-ottawa.csv` has more sites with an LTE-width 850 MHz carrier within 10 km of Carleton (200) than 700 MHz (171 on bands 12/17, 104 on band 13) or 600 MHz (147), and the Sionna campus trace (ADR-0016) is at 886 MHz. Sites counted once, positions rounded to 0.001°, carriers ≥ 1.4 MHz wide, from the ISED extract dated 2024-10-30. Expect it to be a few dB down at 700 MHz and more at 600 MHz.

## 3. VOR dipole (C)

```
   arm 1 (62 cm)                ●                arm 2 (62 cm)
  ════════════════════════════╗ ║ ╔════════════════════════════   ← horizontal, on a PVC/wood boom
                     centre ──┘ ║ └── shield (nut / PCB copper)
                       socket   ║   ~1 cm gap between arm ends
                                ║
                      coax drops straight down for ≥ 30 cm
                      (optional: 2 clip-on ferrites right below the feed)
```

The YOW VOR is **horizontally polarized**. A vertical whip loses a lot of signal; this dipole doesn't.

### Dimensions

Half-wave dipole total length = 142,600 / f(MHz) mm → at 114.6 MHz, **1,245 mm total, 622 mm per arm.** Measure each arm from the feed point (centre socket for arm 1, the solder point on the copper for arm 2) to the tip, including bends. The whole VOR band (108–118 MHz) is within this antenna's useful bandwidth.

### Steps

1. **Cut** two 14 AWG arms of 625 mm (3 mm long for trimming).
2. **Feed plate.** Mount the bulkhead through a small PCB square as in section 2, step 2 (nut tack-soldered to copper).
3. **Arm 1 (centre).** Solder a 20 AWG stub into the centre socket (section 2, step 3), lap-solder arm 1 to it, heat-shrink, then bend arm 1 **90° to horizontal**.
4. **Arm 2 (shield).** Solder arm 2 to the PCB copper right next to the nut, and bend it horizontal in the **opposite direction**, leaving a ~1 cm gap between the two arms at the centre.
5. **Mount.** Tie the feed plate to the middle of the PVC/wood boom and run the arms along it with cable ties or tape. **No metal boom**: it detunes the dipole.
6. **Coax.** Let the coax fall straight down from the centre for at least 30 cm before it turns, so it doesn't run parallel to an arm. Optional: two clip-on ferrites on the coax right under the feed (reduces pickup on the cable's outside).
7. **Trim** each arm to 622 mm.
8. **Multimeter check** (section 5).

### Pointing it

A dipole hears best **broadside** (side-on) and almost nothing off its ends.

- From Carleton, the YOW VOR (N45°26′30″ W75°53′49″) is **291° true, 16.8 km** (west-northwest).
- So run the **arms along 21° ↔ 201° true** (NNE–SSW), with the broad side facing WNW. On a magnetic compass that is roughly 33° ↔ 213° (Ottawa declination about 12° W, `TBC` for 2026).
- From somewhere else: compute the bearing to the VOR and put the arms at 90° to it.
- **For walking or driving sessions**, bend the arms into a horizontal **V** (90–120° between them). That fills in the end nulls at the cost of a little peak signal.
- Height: as high as practical, at least 1.5–2 m above ground, away from walls, cars and metal railings.

## 4. Placement rules (all antennas)

| Rule | Why |
| --- | --- |
| Outdoors beats a window; a window beats indoors | Low-E window coatings and building walls attenuate everything here |
| Keep ≥ 30 cm from the Pi, USB 3 ports and USB cables | They radiate noise right in these bands (RSK-06) |
| Keep the GPS antenna on its own mast, ≥ 30 cm from the SDR antennas | Same reason, and it keeps the GPS truth clean |
| A and B vertical; C horizontal | Match the transmitters' polarization |
| On the drone: antennas above the frame, clear of the props, away from carbon-fibre plates and the LiPo | Carbon fibre and batteries are conductive and detune or block the antenna |
| Use the 30 cm pigtail straight into the SDR when you can; add the bundle's 2 m RG58 base cable only when you need the reach | Every metre of thin coax costs signal (RG316 loses roughly 1 dB/m near 1 GHz, `TBC` from its datasheet) |

The FlightStick has its amplifier and 1090 MHz filter at the dongle, so a 2 m cable run to antenna A is fine.

## 5. Checks before connecting to an SDR

With the multimeter on continuity, probe the **SMA male** end of the pigtail:

| Test | Expected (A, B, C) | If not |
| --- | --- | --- |
| Centre pin ↔ outer shell | **Open** (no beep) | A short: solder bridge between the centre and the plate/nut. Fix before plugging in |
| Centre pin ↔ radiator tip (A, B) or arm 1 tip (C) | **Closed** | Cold joint at the stub or the lap joint |
| Outer shell ↔ a radial tip (A, B) or arm 2 tip (C) | **Closed** | Nut or radial not soldered to the copper |

Then measure the final lengths once more and write them down (section 7).

## 6. On-air tests (Monday, ~10 min per antenna)

Compare each DIY antenna against the bundle's stock antenna, **same spot, same cable, same fixed gain** (no AGC). Swap only the antenna. A few minutes per run is enough.

| Antenna | Tool | What to compare | Pass |
| --- | --- | --- | --- |
| A: ADS-B | readsb / dump1090 on SDR A | Messages per minute, number of aircraft, most distant aircraft | DIY ≥ stock on all three |
| B: LTE | `CellSearch` (LTE-Cell-Scanner) on SDR B over the band you built for | Number of cells detected, RX power per cell | DIY ≥ stock |
| C: VOR | SDR++ (or `rtl_power`) at 114.6 MHz | Carrier height above the noise floor (SNR, dB); the Morse ident **YOW** (`-.-- --- .--`) audible in AM | Clear carrier and audible ident |

Notes:

- **Gain:** start around 30–40 dB on the NESDR. The FlightStick already has an amplifier, so start lower.
- **FM overload check (VOR):** at 114.6 MHz, step the gain down by 10 dB. If the noise floor drops by more than about 10 dB, or spurious signals vanish, strong FM from Camp Fortune is overloading the dongle. Run at the lower gain and note it as a known limitation.
- **Software:** `rtl-sdr` comes from the Pi's apt repos (`deploy/pi/setup.sh`). readsb, LTE-Cell-Scanner and SDR++ are third-party downloads: per AGENTS.md they need a human owner's go-ahead before anyone installs them.
- **Record it:** these runs are part of the RF survey. Log them as sessions so the numbers feed the Sim validity table (ADR-0015, `systems/verification.md`).

## 7. Build record

Fill in after building; it's what lets someone else trust (and reproduce) the antenna behind a session.

| Antenna | Built by | Date | Radiator / arms (mm, measured) | Radials (mm) | Continuity OK | On-air result vs stock |
| --- | --- | --- | --- | --- | --- | --- |
| A: ADS-B 1090 | | | | | | |
| B: LTE ___ MHz | | | | | | |
| C: VOR 114.6 | | | | — | | |

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Nothing at all, any antenna | SDR not detected, or the kernel's DVB driver grabbed it | `rtl_test -t`; check the DVB driver is blacklisted (`deploy/pi/setup.sh`) |
| DIY worse than the stock whip | Short (failed the continuity test), cold joint, or wrong band | Redo section 5; re-measure lengths |
| ADS-B fine indoors only near the window | Building attenuation | Move outdoors or higher |
| VOR carrier weak | Dipole vertical, end-on to the VOR, or blocked by buildings | Rotate broadside (section 3), go higher, clear line of sight to the west-northwest |
| VOR noisy, spurs everywhere | FM overload | Lower the gain (section 6) |
| LTE: no cells found | Built for a band that isn't on the air here | Rebuild B for the band the survey found |
| Readings jump when someone touches the cable | Coax shield carrying signal (common-mode) | Add the clip-on ferrites near the feed |
