"""Does the GNSS jump guard (ADR-0038) keep honest GNSS out after a hard manoeuvre?

GNSS-only, constant-velocity EKF: no towers, no IMU. Honest GNSS (sigma 2.5 m per axis, seed 0)
on a receiver that is still or straight-and-level, then at 20 s either accelerates hard for 4 s
or turns instantly. The gate rejects GNSS while the coast's predicted motion is wrong. Without
the guard the coast's covariance grows until GNSS passes the gate again. With it, a fix that
steps away from the GNSS stream's own track while also far from the filter latches, and only the
stream's steps adding back to zero release it. An honest manoeuvre that the stream's track does
not predict (a sharp turn or hard acceleration, worst at 1 Hz where the track is short) can latch
and is never undone, so GNSS stays out for the rest of the run. A GNSS-only coast after a hard
manoeuvre says nothing about a jump, so this is the case for latching only when an independent
coast exists (ADR-0038, follow-up).

"Recovered": GNSS position was used within 2 s of the last fix (80 s). Prints a Markdown table.

    PYTHONPATH=src python analysis/guard_manoeuvre.py
"""

from __future__ import annotations

import numpy as np

from pnt.core.measurement import Measurement
from pnt.integrity.jump_guard import JumpGuard
from pnt.nav import ekf
from pnt.sim.scenario import T0_NS

S = 1_000_000_000
SIGMA = 2.5  # m per axis, as the base scenarios
UNTIL_S = 80.0
START_S = 20.0  # the manoeuvre starts here


def gnss(pos, rate_hz: float, seed: int = 0) -> list[Measurement]:
    """Honest GNSS fixes of the truth `pos(t_s)` (ENU m) at `rate_hz` until `UNTIL_S`."""
    rng = np.random.default_rng(seed)
    out = []
    for k in range(int(UNTIL_S * rate_hz)):
        t = k / rate_hz
        out.append(
            Measurement(
                t_ns=T0_NS + int(t * S),
                source="gnss",
                kind="position_enu",
                value=tuple(np.asarray(pos(t), float) + rng.normal(0.0, SIGMA, 3)),
                sigma=(SIGMA,) * 3,
            )
        )
    return out


def accel(a: float, dur_s: float = 4.0):
    """Still, then `a` m/s^2 east for `dur_s` from `START_S`, then constant velocity."""

    def pos(t):
        tt = min(max(t - START_S, 0.0), dur_s)
        return (0.5 * a * tt**2 + a * dur_s * max(0.0, t - START_S - dur_s), 0.0, 0.0)

    return pos


def turn(v: float, deg: float):
    """East at `v` m/s, then an instant turn of `deg` degrees at `START_S`, same speed."""
    c, s = np.cos(np.radians(deg)), np.sin(np.radians(deg))

    def pos(t):
        if t < START_S:
            return (v * t, 0.0, 0.0)
        d = v * (t - START_S)
        return (v * START_S + c * d, s * d, 0.0)

    return pos


CASES = {
    **{
        f"accel {a} m/s^2 x 4 s, {r} Hz": (accel(a), r)
        for a in (3.0, 4.0, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5, 8.0, 8.5, 9.0)
        for r in (5, 1)
    },
    **{
        f"turn {d} deg at {v} m/s, {r} Hz": (turn(v, d), r)
        for v in (5, 10, 15, 20)
        for d in (45, 90, 180)
        for r in (5, 1)
    },
}


def outcome(name: str, guard: bool) -> tuple[bool, int]:
    """(recovered, number of latches set) for case `name`, with or without the jump guard."""
    pos, rate = CASES[name]
    meas = gnss(pos, rate)
    f = ekf.EKF(jump_guard=JumpGuard if guard else None)
    for m in meas:
        f.process(m)
    latches = len(f.jump.latches) if guard else 0
    return f.last_used.get("gnss", T0_NS) >= meas[-1].t_ns - 2 * S, latches


def main() -> None:
    print("| Case | Gate only: recovered | Guard: recovered | Latches set |")
    print("| --- | --- | --- | --- |")
    lost = 0
    for name in CASES:
        gate, _ = outcome(name, False)
        guard, n = outcome(name, True)
        lost += gate and not guard
        mark = " **(locked out)**" if gate and not guard else ""
        print(f"| {name} | {'yes' if gate else 'no'} | {'yes' if guard else 'no'}{mark} | {n} |")
    print(f"\nGuard keeps honest GNSS out where the gate alone recovers: {lost} of {len(CASES)}")


if __name__ == "__main__":
    main()
