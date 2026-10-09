"""Duplicate diagnostics (read-only; no cleaning is applied here).

Run from the repo root:  python src/dup_diagnostics.py
Outputs in reports/profiling/:
    dup_diff_columns.csv        per file: duplicate groups (after exact-dup removal) by the set of columns that differ
    battery_empty_payload.csv   per cohort/serial: battery rows with no decoded_data
    fault_status_order.csv      fault_status ordering check (inference only)
"""
from collections import Counter
from pathlib import Path

import pandas as pd

from profile import COHORT_DIRS, KEYS, find_files

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "profiling"
FAULT_KEY_EXT = KEYS["faults"]["primary"] + ["product_alarm_source", "hex_error_code", "fault_status"]


def diff_columns(df, key):
    """Return Counter{tuple(differing columns): n_groups} for groups with >1 row on `key`."""
    d = df[df.duplicated(key, keep=False)]
    out = Counter()
    if d.empty:
        return out
    other = [c for c in df.columns if c not in key]
    for _, g in d.groupby(key, dropna=False, sort=False):
        out[tuple(c for c in other if g[c].nunique(dropna=False) > 1)] += 1
    return out


def main():
    rows, empty_rows = [], []
    for path, cohort, domain in find_files():
        df = pd.read_csv(path, low_memory=False)
        if domain == "battery":
            empty = df[df["decoded_data"].isna()]
            for ser, n in empty.groupby("anonymized_serial").size().items():
                empty_rows.append({"cohort": cohort, "serial": ser, "empty_payload_rows": int(n),
                                   "serial_has_payload_rows": bool(ser in set(df.loc[df.decoded_data.notna(), "anonymized_serial"]))})
            df = df[df["decoded_data"].notna()]  # empty rows are excluded from analysis tables
        before = len(df)
        df = df.drop_duplicates()  # exact duplicates dropped
        keys = [KEYS[domain]["primary"]]
        if domain == "faults":  # extended key: alarm columns treated as part of the event identity
            keys.append(FAULT_KEY_EXT)
        for key in keys:
            for cols, n in diff_columns(df, key).most_common():
                rows.append({"cohort": cohort, "domain": domain, "rows_after_exact_dedup": len(df),
                             "exact_dups_dropped": before - len(df), "key": "+".join(key),
                             "groups": n, "differing_columns": "|".join(cols)})
    pd.DataFrame(rows).to_csv(OUT / "dup_diff_columns.csv", index=False)
    pd.DataFrame(empty_rows).to_csv(OUT / "battery_empty_payload.csv", index=False)

    # fault_status: within a machine + fault_type, does the first status (by fault_timestamp) tend to be 1?
    fs = []
    for path, cohort, domain in find_files():
        if domain != "faults":
            continue
        f = pd.read_csv(path)
        f = f.dropna(subset=["fault_status", "fault_timestamp"]).drop_duplicates()
        f["ts"] = pd.to_datetime(f.fault_timestamp.str.replace(" UTC", ""))
        f = f.sort_values(["anonymized_serial", "fault_type", "ts"])
        g = f.groupby(["anonymized_serial", "fault_type"])
        first = g.fault_status.first().value_counts().to_dict()
        # transitions between consecutive events
        f["prev"] = g.fault_status.shift()
        trans = f.dropna(subset=["prev"]).groupby(["prev", "fault_status"]).size().to_dict()
        fs.append({"cohort": cohort, "rows_used": len(f), "first_status_counts": first,
                   "transitions_prev_to_next": {f"{int(a)}->{int(b)}": n for (a, b), n in trans.items()}})
    pd.DataFrame(fs).to_csv(OUT / "fault_status_order.csv", index=False)
    print("done")


if __name__ == "__main__":
    main()
