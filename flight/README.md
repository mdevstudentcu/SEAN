# Flight

ArduPilot does the flying; we configure it and script it (ADR-0012).

| Folder | |
| --- | --- |
| `params/` | Versioned ArduPilot parameter files: `base.param` (frame, motors, failsafes, geofence), `indoor-flow.param` (MTF-01 optical flow + rangefinder, no GPS), `sitl.param`. Export from Mission Planner/QGC after each tuning session and commit |
| `missions/fly.py` | Scripted patterns over MAVLink. The pilot arms, takes off and selects GUIDED; the script stops the moment the mode changes. Only `--sitl` arms by itself |
| `sitl/` | ArduPilot software-in-the-loop: test scripts, generate realistic trajectories, and try "our nav in the loop" (level 2) with no crash risk |

Pre-flight (indoor): netted area · prop guards · RC kill switch tested · geofence on · battery failsafe → LAND · payload secured · `VIBE` checked after first hover.
