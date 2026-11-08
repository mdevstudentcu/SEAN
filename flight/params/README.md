# ArduPilot parameters

Commit parameter files exported from Mission Planner / QGroundControl. One file per configuration; describe changes in the commit message.

Must-haves for `base.param` (values TBD with the build team):
- `FRAME_CLASS=1` (quad), `FRAME_TYPE=1` (X), `MOT_PWM_TYPE` = DShot (BLHeli_S supports DShot600)
- RC failsafe `FS_THR_ENABLE` → LAND; battery failsafe `BATT_FS_LOW_ACT` → LAND
- Geofence `FENCE_ENABLE=1`, small radius/altitude for indoor flights
- Logging: `LOG_BITMASK` with IMU raw + optical flow for vibration checks

`indoor-flow.param`: `FLOW_TYPE` (MAVLink/MSP per MTF-01 setup), `RNGFND1_TYPE`, `EK3_SRC1_POSXY=0`, `EK3_SRC1_VELXY=5` (optical flow), `EK3_SRC1_POSZ=2` (rangefinder) — confirm against the ArduPilot optical-flow docs before flying.
