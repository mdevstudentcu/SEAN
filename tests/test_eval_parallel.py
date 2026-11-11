import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

import pnt
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


def test_eval_workers_run_one_blas_thread():
    """#255: `pnt eval` workers load numpy with one BLAS thread even when the caller's
    environment does not say so; the calling process keeps its own BLAS."""
    if not os.path.isdir("/proc/self/task"):
        pytest.skip("counts threads through /proc")
    script = (
        "import os\n"
        "import numpy as np\n"
        "from pnt.cli import _worker_pool\n"
        "if __name__ == '__main__':\n"
        "    a = np.ones((300, 300))\n"
        "    with _worker_pool(1) as pool:\n"
        "        pool.submit(np.dot, a, a).result()  # a product big enough to thread\n"
        "        print(len(pool.submit(os.listdir, '/proc/self/task').result()))\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.endswith("_NUM_THREADS")}
    env["PYTHONPATH"] = str(Path(pnt.__file__).parents[1])
    out = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "1"
