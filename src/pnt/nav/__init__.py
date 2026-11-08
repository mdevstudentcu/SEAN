"""See AGENTS.md for what lives in pnt.nav.

`ESTIMATORS` is the registry behind `pnt ... --estimator NAME`. An estimator is a function that
takes time-ordered Measurements and yields Estimates (see `baseline.run`).
"""

from pnt.nav import baseline

ESTIMATORS = {"baseline": baseline.run}
