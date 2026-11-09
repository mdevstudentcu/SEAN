# Hardware

- **Bill of materials and sources:** [`bom.md`](bom.md). **Antennas are bought** (BOM section 3); the build guide [`antennas.md`](antennas.md) is a fallback.

- **Payload spec and rationale** (parts, why each, budgets, wiring diagram): the shared doc "PNT Payload — Hardware Spec & Rationale" (link in the team channel).
- CAD (STL/STEP/3MF) goes here via git LFS (`git lfs install` once): frame (ModuFrame-5 base, CC BY-SA, credited), payload box, antenna masts.
- Provided by Honeywell and used on the payload (ADR-0014): Adafruit Ultimate GPS HAT + active antenna, MPU6050 and BMP280 from the sensor kit, a spare Pi for the ground reference station. Payload board: Pi 4B, with a Pi Zero 2 W hub only if day-1 tests need it (ADR-0018). Team-owned: Pi 3B+ (ground reference station, ADR-0020), Pi camera.
- Drone: 5" quad, Readytosky 2205 2700KV + 45 A BLHeli_S ESCs, ArduPilot, MTF-01 optical flow. Parameters in `flight/params/`.
