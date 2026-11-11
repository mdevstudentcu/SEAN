# Spoof decision from the GPS sky (#206, ADR-0041)

`python analysis/spoof_sky.py --session data/sessions/20261111-0151-static-fullsuite2 --runs 1` at ac478bb. Almanac `tle-gps-20261111.txt`. Skyview stale after 15 s.

A second real session, recorded after the thresholds were set from the first (an independent check of the real-sky side). Real-session sections only: the script's sim section at `--runs 1` is left out; the sim at 20 seeds is in `summary.md`.

## Real session `20261111-0151-static-fullsuite2` (receiver position withheld for privacy)

120 skyviews over 595 s (one every 5 s: the GPS HAT's satellite list).

**As recorded (real sky):**

- GPS PRNs judged per skyview: min 9.00, median 11.00, max 13.00; other PRNs (GLONASS, SBAS) not judged: 6 to 10
- Received PRNs predicted below -5 deg: 0 in 120 skyviews
- C/N0 spread (dB): min 10.21, median 12.15, max 14.09
- Correlation of C/N0 with predicted elevation: min 0.88, median 0.92, max 0.94
- Power pattern judged flat: 0 of 120 judged skyviews
- Levels: not_spoofed 120
- False alarms (suspect or spoofed onsets): 0; spoofed onsets: 0

**Fake sky injected (software) from 300 s to the end:**

| Fake sky | Before: alarms | After: first suspect | After: first spoofed | Faked skyviews flagged (suspect or spoofed) |
| --- | --- | --- | --- | --- |
| PRNs below the horizon | 0 | 0.0 s | 5.0 s | 60 of 60 |
| every satellite at one power | 0 | 0.0 s | never | 60 of 60 |
| both | 0 | 0.0 s | 5.0 s | 60 of 60 |

**Full chain** (the session's GNSS fixes and barometer replayed through `ekf-guard`; the decision at each estimate reads the skyviews and the estimate's flags, as the panel does):

- Clean: 6002 estimates, 0 flagged `gnss_jump_latched`; levels unknown 9, not_spoofed 5993; false alarms (onsets) 0, spoofed onsets 0
- 300 m east jump plus every satellite at 45 dB-Hz from 300 s: alarms before 0; first suspect 0.0 s, first spoofed 5.0 s; cues at the end: power_flat (held), jump_latched

