# Reference data

Small, committed datasets the pipeline needs. **Every file states its source and retrieval date** in the table below. Nothing personal; nothing large.

| File | What | Source | Retrieved |
| --- | --- | --- | --- |
| `cells-ottawa.csv` (TODO) | Cell sites near Carleton: lat, lon, height, carrier, band | ISED Spectrum Management System / OpenCelliD | TBD |
| `navaids.csv` (TODO) | VOR/DME near YOW: ident, freq, lat, lon, magnetic variation | Canada Flight Supplement / NAV CANADA | TBD |
| `broadcast.csv` (TODO) | FM/TV transmitters (mostly Camp Fortune) | ISED broadcasting database | TBD |
| `chu.csv` (TODO) | CHU transmitter site and frequencies | NRC | TBD |
| `tle-*.txt` (TODO) | Orbital elements snapshot for the simulated LEO layer | CelesTrak | TBD |

Until these exist, scenarios use **synthetic** emitter geometry, labelled as such in their YAML.
