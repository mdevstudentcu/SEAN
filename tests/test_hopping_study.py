"""The accuracy budget's hop sets (#173): registry rules only, no run."""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "analysis"))

import accuracy_budget as budget  # noqa: E402


def test_hop_sets_are_unflagged_carriers_in_scan_list_order():
    with open(ROOT / "data" / "reference" / "lte-scan-list-ottawa.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    unflagged = list(dict.fromkeys(int(r["earfcn"]) for r in rows if not r["flags"]))
    flagged = {int(r["earfcn"]) for r in rows if r["flags"]} - set(unflagged)
    assert budget.hop_set() == unflagged
    for cfg in budget.configs():
        hop = cfg.get("earfcn", [])
        assert not set(hop) & flagged
        assert hop == sorted(hop, key=unflagged.index)


def test_distinct_enb_sets_drop_only_a_carrier_whose_enbs_an_earlier_one_has():
    distinct = budget.distinct_enb_sets(budget.hop_set())
    assert distinct[0] == 2460 and 5085 not in distinct  # 5085's eNBs are 5035's
    assert set(budget.hop_set()) - set(distinct) == {5255, 5085, 68661, 68761}
