"""Band power from an `rtl_power` sweep, for the RF survey (#20): which signals are on air here.

Power only: no signal is demodulated, so nothing meant for someone else is decoded (ADR-0011).

`rtl_power` writes CSV rows `date, time, Hz low, Hz high, Hz step, samples, dB, dB, ...`, one
row per tuner hop per sweep. Bin i of a row is taken at `Hz low + i * step`; whether that is the
bin's edge or centre does not matter for bands MHz wide. Its dB values are relative to the
dongle's full scale, not dBm, so only differences within one sweep set mean anything.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Bands we look for (MHz, downlink or broadcast side), up to the R820T's 1766 MHz.
# Sources: 3GPP TS 36.101 table 5.5-1 (LTE bands); ICAO Annex 10 (VOR, DME, 1090 ES);
# GPS ICD IS-GPS-200 (L1); GLONASS ICD (L1 FDMA); Iridium (L band). ISED's Canadian
# allocations are TBC per band.
BANDS: dict[str, tuple[float, float]] = {
    "FM broadcast": (88.0, 108.0),
    "VOR/ILS localizer": (108.0, 118.0),
    "LTE B71 (600)": (617.0, 652.0),
    "LTE B12/17 (700 A-C)": (729.0, 746.0),
    "LTE B13 (700 C)": (746.0, 756.0),
    "LTE B14 (700 D)": (758.0, 768.0),
    "LTE B5 (850)": (869.0, 894.0),
    "DME/TACAN": (962.0, 1213.0),
    "ADS-B 1090ES": (1089.0, 1091.0),
    "GPS L1": (1574.4, 1576.4),
    "GLONASS L1": (1598.0, 1606.0),
    "Iridium": (1616.0, 1626.5),
}
OCCUPIED_DB = 6.0  # TBC: a bin this far above the sweep's noise floor counts as occupied


@dataclass
class Sweep:
    """Median power per frequency bin over every pass of the sweep."""

    freq_hz: np.ndarray  # bin centres, ascending
    power_db: np.ndarray  # median over passes, dB relative to full scale
    passes: int  # how many full passes the median is over (fewest rows any bin had)

    @property
    def floor_db(self) -> float:
        """Noise floor: the median bin. Most of 24-1766 MHz is quiet for a dongle."""
        return float(np.nanmedian(self.power_db))


def read_rtl_power(paths) -> Sweep:
    """Merge one or more rtl_power CSV files into one sweep (median per bin)."""
    bins: dict[int, list[float]] = {}
    for path in [paths] if isinstance(paths, (str, Path)) else paths:
        with open(path, newline="") as f:
            for row in csv.reader(f):
                if len(row) < 7:
                    continue
                lo, step = float(row[2]), float(row[4])
                for i, v in enumerate(row[6:]):
                    v = v.strip()
                    if not v or v.lower() in ("nan", "-nan", "inf", "-inf"):
                        continue
                    centre = int(round(lo + i * step))
                    bins.setdefault(centre, []).append(float(v))
    if not bins:
        raise ValueError(f"{paths}: no rtl_power rows")
    freqs = np.array(sorted(bins))
    power = np.array([np.median(bins[f]) for f in freqs])
    return Sweep(freqs.astype(float), power, min(len(v) for v in bins.values()))


@dataclass
class BandPower:
    name: str
    lo_mhz: float
    hi_mhz: float
    bins: int  # bins of the sweep inside the band (0: the sweep did not cover it)
    median_above_floor_db: float | None
    peak_above_floor_db: float | None
    occupied_frac: float | None  # bins >= OCCUPIED_DB above the floor


def band_power(sweep: Sweep, bands: dict[str, tuple[float, float]] = BANDS) -> list[BandPower]:
    floor = sweep.floor_db
    out = []
    for name, (lo, hi) in bands.items():
        sel = (sweep.freq_hz >= lo * 1e6) & (sweep.freq_hz <= hi * 1e6)
        p = sweep.power_db[sel] - floor
        if not sel.any():
            out.append(BandPower(name, lo, hi, 0, None, None, None))
            continue
        out.append(
            BandPower(
                name,
                lo,
                hi,
                int(sel.sum()),
                float(np.median(p)),
                float(p.max()),
                float(np.mean(p >= OCCUPIED_DB)),
            )
        )
    return out
