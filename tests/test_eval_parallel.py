import math

from pnt.cli import _eval


def _same(a: dict, b: dict) -> bool:
    return a.keys() == b.keys() and all(
        (math.isnan(a[k]) and math.isnan(b[k]))
        if isinstance(a[k], float) and a[k] != a[k]
        else a[k] == b[k]
        for k in a
    )


def test_parallel_eval_matches_serial():
    serial = _eval("gps-outage", 2, "baseline", jobs=1)
    parallel = _eval("gps-outage", 2, "baseline", jobs=2)
    assert _same(serial, parallel)
