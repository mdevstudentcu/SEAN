"""Scripted flight patterns over MAVLink (ADR-0012, level 1).

Safety model:
- Real drone: the PILOT arms, takes off and switches to GUIDED. This script only sends
  position targets while the mode is GUIDED, and exits the moment the pilot switches away.
  It never arms or takes off a real vehicle.
- SITL (--sitl): the script arms and takes off itself.

Usage:
    python flight/missions/fly.py square --side 3 --alt 1.5                 # real, via Pi router
    python flight/missions/fly.py square --sitl --conn udpin:0.0.0.0:14550  # SITL
"""

from __future__ import annotations

import argparse
import math
import sys
import time

from pymavlink import mavutil

POS_ONLY = 0b0000_1111_1111_1000  # use x, y, z; ignore velocity, accel, yaw


def mode(master) -> str:
    hb = master.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
    return mavutil.mode_string_v10(hb) if hb else "UNKNOWN"


def goto(master, n: float, e: float, alt: float, tol: float, timeout: float, sitl: bool) -> bool:
    """Fly to a local NED target; return False if the pilot left GUIDED (stop immediately)."""
    t_end = time.time() + timeout
    while time.time() < t_end:
        if not sitl and mode(master) != "GUIDED":
            return False
        master.mav.set_position_target_local_ned_send(
            0, master.target_system, master.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED, POS_ONLY,
            n, e, -alt, 0, 0, 0, 0, 0, 0, 0, 0,
        )  # fmt: skip
        pos = master.recv_match(type="LOCAL_POSITION_NED", blocking=True, timeout=1)
        if pos and math.dist((pos.x, pos.y, -pos.z), (n, e, alt)) < tol:
            return True
    return True  # timed out on this leg: move on rather than hover forever


def pattern(name: str, side: float) -> list[tuple[float, float]]:
    h = side / 2
    if name == "square":
        return [(h, -h), (h, h), (-h, h), (-h, -h), (h, -h)]
    if name == "line":
        return [(h, 0), (-h, 0), (h, 0)]
    raise SystemExit(f"unknown pattern {name!r}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("pattern", choices=["square", "line"])
    p.add_argument("--side", type=float, default=3.0, help="m (indoor default)")
    p.add_argument("--alt", type=float, default=1.5, help="m above home")
    p.add_argument("--laps", type=int, default=2)
    p.add_argument("--conn", default="udpin:0.0.0.0:14550")
    p.add_argument(
        "--sitl", action="store_true", help="arm and take off automatically (SITL only)"
    )
    a = p.parse_args()

    master = mavutil.mavlink_connection(a.conn)
    master.wait_heartbeat(timeout=10)
    print(f"connected: system {master.target_system}, mode {mode(master)}")

    if a.sitl:
        master.set_mode("GUIDED")
        master.arducopter_arm()
        master.motors_armed_wait()
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, a.alt,
        )  # fmt: skip
        time.sleep(8)
    elif mode(master) != "GUIDED":
        sys.exit("pilot: arm, take off, then switch to GUIDED; re-run this script")

    for lap in range(a.laps):
        for n, e in pattern(a.pattern, a.side):
            if not goto(master, n, e, a.alt, tol=0.3, timeout=20, sitl=a.sitl):
                sys.exit("pilot took over (mode left GUIDED): stopping")
        print(f"lap {lap + 1}/{a.laps} done")

    if a.sitl:
        master.set_mode("LAND")
    print("pattern complete" + ("" if a.sitl else ": pilot, take over and land"))


if __name__ == "__main__":
    main()
