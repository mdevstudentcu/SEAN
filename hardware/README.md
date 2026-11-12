# Hardware

- **Bill of materials and sources:** [`bom.md`](bom.md); what is physically in hand is its *In hand* section. **Antennas are bought** (BOM section 3); the build guide [`antennas.md`](antennas.md) is a fallback.

- **Payload spec and rationale** (parts, why each, budgets, wiring diagram): the shared doc "PNT Payload — Hardware Spec & Rationale" (link in the team channel).
- CAD (STL/STEP/3MF) goes here via git LFS (`git lfs install` once): frame (ModuFrame-5 base, CC BY-SA, credited), payload box, antenna masts.
- Provided by Honeywell and used on the payload (ADR-0014): Adafruit Ultimate GPS HAT + active antenna, MPU6050 and BMP180 from the sensor kit (a BMP180, not a BMP280). Payload board: a Pi 4B with 4 GB (from 2026-11-10; Honeywell's 1 GB Pi 4B is the spare), with a Pi Zero 2 W hub only if day-1 tests need it (ADR-0018). Team-owned: Pi 3B+ (unused: the ground reference station stays in sim, ADR-0020, *Amendment 2026-11-10*), Pi camera. The LoRa HAT from Honeywell is in hand but not used (`bom.md`, *Not using*).
- Drone: 5" quad, Readytosky 2205 2700KV, iFlight BLITZ ATF435 stack (flight controller + E55S 55 A 4-in-1 ESC), MTF-01 optical flow. The ATF435 flies Betaflight 4.5.5, pilot-flown with a FlySky FS-i6 and its kill switch (ADR-0028, *Amendment 2026-11-11 (owners)*); the ArduPilot files in `flight/params/` are for SITL only.
