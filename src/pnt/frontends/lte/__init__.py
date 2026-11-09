"""LTE front end (#21, #23): RTL-SDR IQ capture -> `lte` pseudorange and doppler Measurements.

Clean-room PSS/SSS cell search and time-of-arrival tracker, written from 3GPP TS 36.211. It
decodes only the broadcast synchronisation signals (ADR-0011) and never transmits (ADR-0001).

- `capture`: `.cu8` + `.json` sidecar reader, EARFCN conversion
- `signals`: PSS, SSS and frame timing from the standard
- `tracker`: search, PCI detection and the 5 ms tracking loop
- `frontend`: `process_file` / `process_capture` -> Measurements
- `synth`: synthetic baseband for tests and analysis
"""

from pnt.frontends.lte.capture import earfcn, open_capture
from pnt.frontends.lte.frontend import Result, process_capture, process_file
from pnt.frontends.lte.tracker import Config

__all__ = ["Config", "Result", "earfcn", "open_capture", "process_capture", "process_file"]
