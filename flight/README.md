# Flight

The real drone flies INAV on the iFlight BLITZ ATF435, pilot-flown with an RC kill switch (ADR-0028). The ArduPilot files below are for SITL only: they make trajectories for the sim and try "our nav in the loop" with no crash risk.

| Folder | |
| --- | --- |
| `params/` | Versioned ArduPilot parameter files: `base.param` (frame, motors, failsafes, geofence), `indoor-flow.param` (MTF-01 optical flow + rangefinder, no GPS), `sitl.param`. Export from Mission Planner/QGC after each tuning session and commit |
| `missions/fly.py` | Scripted patterns over MAVLink. The pilot arms, takes off and selects GUIDED; the script stops the moment the mode changes. Only `--sitl` arms by itself |
| `sitl/` | ArduPilot software-in-the-loop: test scripts, generate realistic trajectories, and try "our nav in the loop" (level 2) with no crash risk |

Pre-flight (indoor, INAV): netted area · prop guards · RC kill switch tested · INAV failsafe (RC loss → land) set and tested · geofence if the INAV version supports it (`TBC`) · optical-flow position hold checked in a low hover · payload secured · INAV MAVLink telemetry reaching the recorder (`/mavlink/fc`).
