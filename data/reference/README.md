# Reference data

Small, committed datasets the pipeline needs. **Every file states its source and retrieval date** in the table below. Nothing personal; nothing large.

| File | What | Source | Retrieved |
| --- | --- | --- | --- |
| `cells-ottawa.csv` | Cell carriers within 10 km of Carleton that our radios can tune (600–1750 MHz): lat, lon, height, carrier, frequency, bandwidth, location, distance. Built by `analysis/extract_cells.py`. `height_m` is ground elevation plus antenna height as filed, and ground elevation is sometimes missing. No PCI or EARFCN: the registry doesn't list them | [ISED Spectrum Licences Site Data](https://ised-isde.canada.ca/site/spectrum-management-system/en/download-sms-data), `Site_Data_Extract.zip` (file dated 2024-10-30) | 2026-11-08 |
| `navaids.csv` (TODO) | VOR/DME near YOW: ident, freq, lat, lon, magnetic variation | Canada Flight Supplement / NAV CANADA | TBD |
| `broadcast.csv` (TODO) | FM/TV transmitters (mostly Camp Fortune) | ISED broadcasting database | TBD |
| `chu.csv` (TODO) | CHU transmitter site and frequencies | NRC | TBD |
| `tle-iridium-20261108.txt` | Orbital elements snapshot of Iridium NEXT, for the simulated LEO layer | [CelesTrak](https://celestrak.org/NORAD/elements/gp.php?GROUP=iridium-NEXT&FORMAT=tle) | 2026-11-08 |

`cells-ottawa.csv` is an extract of *Spectrum Licences Site Data* by Innovation, Science and Economic Development Canada, reproduced for non-commercial use under the [Government of Canada terms](https://ised-isde.canada.ca/site/ised/en/terms-and-conditions). It is a copy of the version available at the source link above. Commercial redistribution needs ISED's written permission.

Until these exist, scenarios use **synthetic** emitter geometry, labelled as such in their YAML.
