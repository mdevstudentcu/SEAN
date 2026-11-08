"""See AGENTS.md for what lives in pnt.nav.

`ESTIMATORS` is the registry behind `pnt ... --estimator NAME`. An estimator is a function that
takes time-ordered Measurements and an optional `origin_llh` (the session origin, for emitters
given in lat/lon) and yields Estimates (see `baseline.run`).
"""

from pnt.nav import baseline

ESTIMATORS = {"baseline": baseline.run}
