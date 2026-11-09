"""See AGENTS.md for what lives in pnt.nav.

`ESTIMATORS` is the registry behind `pnt ... --estimator NAME`. An estimator is a function that
takes time-ordered Measurements and an optional `origin_llh` (the session origin, for emitters
given in lat/lon) and yields Estimates (see `baseline.run`).
"""

from functools import partial

from pnt.integrity.mhss import MHSS
from pnt.nav import baseline, ekf

# ekf-mhss: the same EKF, with solution-separation protection levels and exclusion (#82)
ESTIMATORS = {"baseline": baseline.run, "ekf": ekf.run, "ekf-mhss": partial(ekf.run, monitor=MHSS)}
