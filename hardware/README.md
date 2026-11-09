# Hardware

- **Bill of materials and sources:** [`bom.md`](bom.md). **Antenna build guide:** [`antennas.md`](antennas.md).

- **Payload spec and rationale** (parts, why each, budgets, wiring diagram): the shared doc "PNT Payload — Hardware Spec & Rationale" (link in the team channel).
- CAD (STL/STEP/3MF) goes here via git LFS (`git lfs install` once): frame (ModuFrame-5 base, CC BY-SA, credited), payload box, antenna masts.
- Provided by Honeywell and used on the payload (ADR-0014): Adafruit Ultimate GPS HAT + active antenna, MPU6050 and BMP280 from the sensor kit, a spare Pi for the ground reference station. Payload boards: Pi 3B+ with a Pi Zero 2 W sensor hub (ADR-0018). Team-owned: Pi 4B (spare), Pi camera.
- Drone: 5" quad, Readytosky 2205 2700KV + 45 A BLHeli_S ESCs, ArduPilot, MTF-01 optical flow. Parameters in `flight/params/`.
