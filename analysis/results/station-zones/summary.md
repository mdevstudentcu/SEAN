# Ground-station zones on measured noise sizes

Sim only. `realistic-with-base`, seeds 0–9, commit `cd4dba2f`. Regenerate: `python analysis/station_zones.py --runs 10`. Statistic: worst second of the 95th percentile across runs in 0–300 s after the fault (ADR-0034).


## Variant A: as committed: 50 m white, 50 m / 30 s multipath (placeholders)

| Filter | Worst second, long outage | Median after loss | Radius covers error, worst run | Unavailable | Dangerous epochs: outage / held jump |
| --- | --- | --- | --- | --- | --- |
| payload alone | 520 m | 96 m | 90.6 % | 82.1 % | 0 / 2,257 (3 runs) |
| + station | 316 m | 64 m | 100.0 % | 80.7 % | 0 / 12,142 (9 runs) |
| + station + jump guard | 316 m | 64 m | 100.0 % | 80.7 % | 0 / 0 (0 runs) |

## Variant B: white noise 10 m at 1 Hz (ADR-0036, measured bound); multipath as committed

| Filter | Worst second, long outage | Median after loss | Radius covers error, worst run | Unavailable | Dangerous epochs: outage / held jump |
| --- | --- | --- | --- | --- | --- |
| payload alone | 3,263 m | 171 m | 7.0 % | 81.9 % | 39 / 1,899 (7 runs) |
| + station | 982 m | 77 m | 51.1 % | 80.4 % | 0 / 1,355 (1 runs) |
| + station + jump guard | 982 m | 77 m | 51.1 % | 80.4 % | 0 / 0 (0 runs) |

## Variant C: B, plus multipath 10 m / 3 s (ADR-0036 at rest)

| Filter | Worst second, long outage | Median after loss | Radius covers error, worst run | Unavailable | Dangerous epochs: outage / held jump |
| --- | --- | --- | --- | --- | --- |
| payload alone | 359 m | 27 m | 67.2 % | 81.3 % | 0 / 86 (2 runs) |
| + station | 294 m | 35 m | 100.0 % | 80.4 % | 0 / 0 (0 runs) |
| + station + jump guard | 294 m | 35 m | 100.0 % | 80.4 % | 0 / 0 (0 runs) |
