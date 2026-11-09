# ESP32-S3 sensor hub

> **Superseded by ADR-0018:** the sensors are on the Pi 4B, with a Pi Zero 2 W hub only as a fallback. This firmware is not built for the payload; it stays until `just gen` and the CI firmware job stop using it (needs owner sign-off for `.github/`).

Reads the payload's IMU (MPU6050, I2C), barometer (BMP280, I2C), the GPS PPS edge (wired from the Pi's GPS HAT) and Wi-Fi (scans + FTM ranging), timestamps everything with the ESP32's microsecond timer, and sends it to the Pi as MAVLink messages defined in [`systems/icd/pnt.xml`](../../systems/icd/pnt.xml).

```bash
just gen        # after any change to pnt.xml: regenerates lib/pnt_mavlink (never edit it by hand)
just fw         # build
just fw-flash   # flash over USB
```

Needs [PlatformIO](https://platformio.org) (`pipx install platformio`). The chip must be an **S2, S3, C3 or C6** for Wi-Fi FTM.

Privacy (ADR-0011): BSSIDs are hashed on the hub with a per-session salt before they leave it. Client probe requests are never captured.
