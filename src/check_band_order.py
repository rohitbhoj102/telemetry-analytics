"""Evidence for the storage order of the 2-D battery bin arrays (read-only, Step 3).

Run from the repo root:  python src/check_band_order.py
Output (generated): reports/profiling/band_order_check.csv

dischargeBandBins / chargeBandBins are flat lists of 9 in the payload; BMS_Bins.json lists two
dimensions (voltage, temperature) but not the order. Two pieces of evidence:
  1. mean share of the array total per index across all standard-layout payloads;
  2. the label order in the label-keyed layouts (labelled layout, 9 labels per band section).
"""
from pathlib import Path

import numpy as np
import pandas as pd

import field_meanings as fm
from payload_io import load_groups

OUT = Path(__file__).resolve().parent.parent / "reports" / "profiling" / "band_order_check.csv"


def main():
    groups = load_groups()
    rows = []
    for name in ("battery_normal", "battery_rr_standard"):
        for array, path in (("dischargeBandBins", ("usage", "dischargeLog")), ("chargeBandBins", ("usage", "chargeLog"))):
            a = np.array([p[path[0]][path[1]][array] for p in groups[name].payload], dtype=float)
            share = (a / np.clip(a.sum(axis=1, keepdims=True), 1, None)).mean(axis=0)
            for i, s in enumerate(share):
                rows.append({"evidence": "mean share of array total", "group": name, "array": array,
                             "index": i, "value": round(float(s), 4)})
    lab = groups["battery_rr_labelled"].payload.iloc[0]
    for loc in ("dischargeLog", "chargeLog"):
        for key, v in lab["usage"][loc].items():
            if isinstance(v, dict) and len(v) == 9:
                for i, label in enumerate(v):
                    rows.append({"evidence": "label order in labelled layout", "group": "battery_rr_labelled",
                                 "array": key, "index": i, "value": label})
    out = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(str(OUT), index=False)
    print("Assumed order: %s" % fm.BAND_2D_ORDER)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
