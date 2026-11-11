"""Fault taxonomy: what each injected attack is, for the report card (issue I6).

Each attack type in `pnt.sim.attacks` maps to one class, in the style of TEXBAT's scenario list
(Humphreys et al., "The Texas Spoofing Test Battery", ION GNSS 2012), which names attacks by what
they push (time or position) rather than by how they are generated. `affects` says which part of
the solution the attack corrupts, so the report card judges time only where it should.
`expect_alert` is False for checks where raising an alarm would itself be a false alarm.

The classes and TEXBAT analogues are our labels, not a standard's.
"""

from __future__ import annotations

from dataclasses import dataclass

POSITION, TIME = "position", "time"


@dataclass(frozen=True)
class FaultClass:
    cls: str
    affects: tuple[str, ...]
    texbat: str  # closest TEXBAT scenario type, or "none" if TEXBAT has no counterpart
    expect_alert: bool = True
    spatial: bool = False  # active by place, not by time: no onset time to measure from


TAXONOMY: dict[str, FaultClass] = {
    "outage": FaultClass("jamming / denial", (POSITION, TIME), "none (denial, not spoofing)"),
    "jamming_zone": FaultClass(
        "jamming / denial", (POSITION, TIME), "none (denial, not spoofing)", spatial=True
    ),
    "spoof_ramp": FaultClass("position spoof", (POSITION,), "position push (ds4, ds6)"),
    "spoof_jump": FaultClass("position spoof", (POSITION,), "none (crude takeover)"),
    # A spoofer at a fixed place (#91): a jump on entering its circle, like spoof_jump
    "spoof_zone": FaultClass("position spoof", (POSITION,), "none (crude takeover)", spatial=True),
    "time_spoof": FaultClass("time spoof", (TIME,), "time push (ds2, ds3, ds5)"),
    "meaconing": FaultClass("meaconing / replay", (POSITION, TIME), "none (record and replay)"),
    "gps_no_fix": FaultClass("receiver fault", (POSITION, TIME), "none"),
    "gps_low_sats": FaultClass("nuisance (false-alarm check)", (), "none", expect_alert=False),
    "baro_drift": FaultClass("sensor degradation", (POSITION,), "none"),
    "tower_clock_step": FaultClass("SoOP fault", (POSITION,), "none"),
    # The ground reference station's own faults (ADR-0020): every differenced reading inherits
    # them, so they corrupt position and the relative clock
    "reference_moved": FaultClass("reference station fault", (POSITION, TIME), "none"),
    "reference_clock_step": FaultClass("reference station fault", (POSITION, TIME), "none"),
    # TBC (owners confirm): like tower_clock_step, but it also corrupts time, since time held
    # through an outage rests on the towers
    "tower_holdover": FaultClass("SoOP fault", (POSITION, TIME), "none"),
    # TBC (owners confirm): like baro_drift
    "imu_degradation": FaultClass("sensor degradation", (POSITION,), "none"),
    # The hostile beacon's own faults (ADR-0025, #93). TBC (owners confirm): they corrupt
    # position only through a filter that uses the beacon, and its answer is to demote the beacon
    # or exclude its hypothesis, not to raise a GNSS alarm, so no alarm is expected
    "hostile_power": FaultClass("hostile emitter", (POSITION,), "none", expect_alert=False),
    "hostile_moves": FaultClass("hostile emitter", (POSITION,), "none", expect_alert=False),
    # TBC (owners confirm): the payload board's own capture effects (issue #53), not an attack. At
    # the sizes a working board shows, an alarm would be a false alarm, like gps_low_sats
    "capture_faults": FaultClass(
        "board capture (false-alarm check)", (), "none", expect_alert=False
    ),
}


def classify(fault: dict) -> FaultClass:
    """The class of one entry in a scenario's `faults:` list. An outage of a non-GNSS source
    (for example every LTE tower lost) is a SoOP fault, not GNSS jamming."""
    fc = TAXONOMY[fault["type"]]
    if fault["type"] == "outage" and fault.get("source", "gnss") != "gnss":
        return FaultClass("SoOP fault", (POSITION,), "none", fc.expect_alert)
    return fc


def markdown() -> str:
    """The taxonomy as a Markdown table, for the results block in systems/verification.md."""
    rows = [
        "| Attack (`type`) | Class | Corrupts | TEXBAT analogue | Alarm expected |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, fc in TAXONOMY.items():
        rows.append(
            f"| `{name}` | {fc.cls} | {', '.join(fc.affects) or 'nothing'} | {fc.texbat} "
            f"| {'yes' if fc.expect_alert else 'no'} |"
        )
    return "\n".join(rows)
