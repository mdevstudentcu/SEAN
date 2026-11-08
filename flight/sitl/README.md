# ArduPilot SITL

Install once (Ubuntu): follow ArduPilot's "Setting up the Build Environment (Linux)" guide, then `./waf configure --board sitl && ./waf copter` and put `Tools/autotest` on your PATH.

```bash
just sitl                                   # starts Copter SITL at Carleton
just mission square                         # in another terminal (add --sitl via fly.py args)
python flight/missions/fly.py square --sitl
```

Uses: test `fly.py`; generate realistic trajectories and IMU data for `pnt.sim` (planned); feed our estimate back into ArduPilot (`GPS_INPUT` or external-nav) to show "flying on our navigation" with zero crash risk (level 2).
