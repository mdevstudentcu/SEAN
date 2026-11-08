# Reference data

Small, committed datasets the pipeline needs. **Every file states its source and retrieval date** in the table below. Nothing personal; nothing large.

| File | What | Source | Retrieved |
| --- | --- | --- | --- |
| `cells-ottawa.csv` | Cell carriers within 10 km of Carleton that our radios can tune (600–1750 MHz): lat, lon, height, carrier, frequency, bandwidth, location, distance. Built by `analysis/extract_cells.py`. `height_m` is ground elevation plus antenna height as filed, but 1,328 of 1,971 rows (67 %) have no ground elevation and hold the antenna height alone; scenarios correct this with `tower_height_m` (below 80 m, TBC). The same site is sometimes filed twice a few metres apart; scenarios count it once. No PCI or EARFCN: the registry doesn't list them | [ISED Spectrum Licences Site Data](https://ised-isde.canada.ca/site/spectrum-management-system/en/download-sms-data), `Site_Data_Extract.zip` (file dated 2024-10-30) | 2026-11-08 |
| `sionna-campus-route.csv` | Ray-traced line of sight, excess delay and gain from six TELUS sites along the 150 m loop, every 5 s. Built by `analysis/sionna_campus.py`. Assumed heights and materials, no trees (ADR-0016) | Sionna RT 2.2.0 over [OpenStreetMap](https://www.openstreetmap.org/copyright) buildings (ODbL) | 2026-11-08 |
| `navaids.csv` (TODO) | VOR/DME near YOW: ident, freq, lat, lon, magnetic variation | Canada Flight Supplement / NAV CANADA | TBD |
| `broadcast.csv` (TODO) | FM/TV transmitters (mostly Camp Fortune) | ISED broadcasting database | TBD |
| `chu.csv` (TODO) | CHU transmitter site and frequencies | NRC | TBD |
| `tle-iridium-20261108.txt` | Orbital elements snapshot of Iridium NEXT, for the simulated LEO layer | [CelesTrak](https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle) (T.S. Kelso), from US Space Force 18 SDS data. Credit CelesTrak; usage terms `TBC` against celestrak.org | 2026-11-08 |

`cells-ottawa.csv` is an extract of *Spectrum Licences Site Data* by Innovation, Science and Economic Development Canada, reproduced for non-commercial use under the [Government of Canada terms](https://ised-isde.canada.ca/site/ised/en/terms-and-conditions). It is derived from the version at the source link above (filtered by distance and frequency, heights summed, distance computed); it is not an official version and is not endorsed by ISED. The SHA-256 of the source zip was not recorded: `TBD` on the next download. Commercial redistribution needs ISED's written permission.

Until these exist, scenarios use **synthetic** emitter geometry, labelled as such in their YAML.
