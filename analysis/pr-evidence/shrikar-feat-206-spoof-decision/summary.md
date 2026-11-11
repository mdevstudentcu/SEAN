# Spoof decision from the GPS sky (#206, ADR-0041)

`python analysis/spoof_sky.py --session data/sessions/20261111-0040-static-fullsuite --runs 20` at 6eb08a8. Almanac `tle-gps-20261111.txt`. Skyview stale after 15 s.

## Real session `20261111-0040-static-fullsuite` (receiver position withheld for privacy)

120 skyviews over 595 s (one every 5 s: the GPS HAT's satellite list).

**As recorded (real sky):**

- GPS PRNs judged per skyview: min 7.00, median 11.00, max 11.00; other PRNs (GLONASS, SBAS) not judged: 8 to 10
- Received PRNs predicted below -5 deg: 0 in 120 skyviews
- C/N0 spread (dB): min 7.56, median 10.48, max 13.26
- Correlation of C/N0 with predicted elevation: min 0.66, median 0.74, max 0.83
- Power pattern judged flat: 0 of 120 judged skyviews
- Levels: not_spoofed 120
- False alarms (suspect or spoofed onsets): 0; spoofed onsets: 0

**Fake sky injected (software) from 300 s to the end:**

| Fake sky | Before: alarms | After: first suspect | After: first spoofed | Faked skyviews flagged (suspect or spoofed) |
| --- | --- | --- | --- | --- |
| PRNs below the horizon | 0 | 5.0 s | 10.0 s | 59 of 59 |
| every satellite at one power | 0 | 5.0 s | never | 59 of 59 |
| both | 0 | 5.0 s | 10.0 s | 59 of 59 |

**Full chain** (the session's GNSS fixes and barometer replayed through `ekf-guard`; the decision at each estimate reads the skyviews and the estimate's flags, as the panel does):

- Clean: 6001 estimates, 0 flagged `gnss_jump_latched`; levels unknown 19, not_spoofed 5982; false alarms (onsets) 0, spoofed onsets 0
- 300 m east jump plus every satellite at 45 dB-Hz from 300 s: alarms before 0; first suspect 0.1 s, first spoofed 10.0 s; cues at the end: power_flat (held), jump_latched

## Sim `spoof-jump-sky` (seeds 0-19; sky model `measured` on the real session)

| Estimator | Clean (no faults): alarm onsets / spoofed onsets, all runs | Spoofed run before 150 s: alarm onsets | First suspect after the spoof (median, max) | First spoofed (median, max; runs reaching it) |
| --- | --- | --- | --- | --- |
| `ekf` | 0 / 0 | 0 | 0.0 s, 0.0 s (20/20 runs) | n/a (0/20 runs) |
| `ekf-guard` | 0 / 0 | 0 | 0.0 s, 0.0 s (20/20 runs) | 5.0 s, 5.0 s (20/20 runs) |
