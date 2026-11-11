# gnss_health on 20261111-0040-static-fullsuite-gnss (#22, ADR-0031)

`python analysis/gnss_health_real.py` at `c1a76d3` on the `gnss_health` records that `pnt frontend gnss` derived from the session's gpsd SKY reports. Real session, GPS HAT (MediaTek, C/N0 from NMEA GSV), statistics only. Indicator parameters (ADR-0031, all `TBC`): open-sky reference 40 dB-Hz, loss level 25 dB-Hz, top 4 satellites.

120 records over 595.0 s; 0 without a fix (HDOP 99); indicator above 0 in 0.0 % of records.

| Quantity | min | p5 | median | p95 | max |
|---|---|---|---|---|---|
| Record spacing (s) | 4.86 | 4.90 | 5.00 | 5.10 | 5.12 |
| Jamming indicator | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| Mean C/N0 of top 4 (dB-Hz) | 43.8 | 43.8 | 44.2 | 44.8 | 45.0 |
| C/N0, every tracked satellite (dB-Hz) | 11.0 | 17.0 | 32.0 | 46.0 | 47.0 |
| Satellites used | 16 | 16 | 18 | 20 | 20 |
| Satellites tracked (C/N0 > 0) | 17 | 18 | 20 | 21 | 21 |
| Satellites seen | 21 | 21 | 22 | 22 | 22 |
| HDOP | 0.55 | 0.55 | 0.59 | 0.66 | 0.68 |
