"""Tower identity (#87, ADR-0023): the committed scan list and cell-to-site table agree.

Counts are regression guards on the committed reference data, not targets. They back the
numbers in `systems/tower-identity.md`.
"""

import csv
import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

REF = Path(__file__).parents[1] / "data" / "reference"
_PATH = Path(__file__).parents[1] / "analysis" / "extract_lte_cells.py"
_SPEC = importlib.util.spec_from_file_location("extract_lte_cells", _PATH)
ex = importlib.util.module_from_spec(_SPEC)
sys.modules["extract_lte_cells"] = ex
_SPEC.loader.exec_module(ex)


def _rows(name):
    with open(REF / name, newline="") as f:
        return list(csv.reader(f))


def test_scan_list_is_generated_from_the_cell_table():
    header, *cells = _rows("lte-cells-ottawa.csv")
    assert header == ex.CELL_COLUMNS
    header, *committed = _rows("lte-scan-list-ottawa.csv")
    assert header == ex.SCAN_COLUMNS
    assert [[str(x) for x in r] for r in ex.scan_list(cells)] == committed


def test_sectors_group_by_enb_id_and_pci_div_3_never_matches_it():
    # ADR-0023 step 3 proposed grouping a site's sectors by PCI // 3. The 2026 extract gives the
    # eNB ID (ECI >> 8), and in Ottawa no eNB with several PCIs on one carrier keeps them in one
    # PCI // 3 group, so the lookup groups by eNB ID (pnt.nav.cells, ADR-0022).
    with open(REF / "lte-cells-ottawa.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    pcis = defaultdict(set)
    for r in rows:
        pcis[(r["earfcn"], r["enb_id"])].add(int(r["pci"]))
    several = [p for p in pcis.values() if len(p) > 1]
    assert len(pcis) == 1416 and len(several) == 1370
    assert sum(len({p // 3 for p in s}) == 1 for s in several) == 0
