"""Read-only link checks between tables (Step 3, part A).

Run from the repo root:  python src/link_checks.py
Output (generated): reports/profiling/link_checks.csv

Checks (all on raw rows, no de-duplication, both cohorts):
  a. session_id is not unique within a machine: serial+session_id groups with >1 distinct `date`,
     and how many of those also differ in clean_duration / battery_charge_start / battery_charge_end.
  b. Lag between faults.date and faults.fault_timestamp, in hours (median, p90).
  c. Share of serial+session_id pairs in motor and battery that also occur in clean sessions.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "profiling" / "link_checks.csv"
DIRS = {"normal": ROOT / "normal_machines", "return_repair": ROOT / "return_repair_machines"}
FILES = {
    "clean_sessions": "Clean Sessions_{}.csv",
    "faults": "Faults_{}.csv",
    "motor": "Motor_{}.csv",
    "battery": "Battery_{}.csv",
}
SUFFIX = {"normal": "Normal Machines", "return_repair": "Return:Repair Machines"}
DEDUP_KEY = ["anonymized_serial", "session_id", "fault_type", "fault_value", "fault_timestamp", "fault_status"]
CONTENT_COLS = ["clean_duration", "battery_charge_start", "battery_charge_end"]


def load(domain, cohort, usecols):
    path = DIRS[cohort] / FILES[domain].format(SUFFIX[cohort])
    df = pd.read_csv(path, low_memory=False, usecols=usecols)
    for c in df.columns:
        if c in ("date", "fault_timestamp"):
            df[c] = pd.to_datetime(df[c].str.replace(" UTC", "", regex=False))
    return df


def check_a(rows):
    for cohort in DIRS:
        df = load("clean_sessions", cohort, ["anonymized_serial", "session_id", "date"] + CONTENT_COLS)
        g = df.groupby(["anonymized_serial", "session_id"])
        multi_date = g["date"].nunique() > 1
        n_groups = len(multi_date)
        # distinct count with dropna=False so a value vs null counts as a difference
        differs = g[CONTENT_COLS].agg(lambda s: s.nunique(dropna=False)).gt(1).any(axis=1)
        # variant: nulls ignored, so only value-vs-value differences count
        differs_nn = g[CONTENT_COLS].nunique().gt(1).any(axis=1)
        rows.append((("a", cohort, "serial+session_id groups", n_groups)))
        rows.append((("a", cohort, "groups with >1 distinct date", int(multi_date.sum()))))
        rows.append((("a", cohort, "of those: also differ in clean_duration or battery_charge_start/end",
                      int((multi_date & differs).sum()))))
        rows.append((("a", cohort, "of those: differ in a non-null value of those columns (nulls ignored)",
                      int((multi_date & differs_nn).sum()))))
    # combined = sum, since cohorts share no serials (verified in Step 1)
    for item in ("serial+session_id groups", "groups with >1 distinct date",
                 "of those: also differ in clean_duration or battery_charge_start/end",
                 "of those: differ in a non-null value of those columns (nulls ignored)"):
        tot = sum(r[3] for r in rows if r[0] == "a" and r[2] == item)
        rows.append(("a", "all", item, tot))


def lag_hours(df):
    return (df["date"] - df["fault_timestamp"]).dt.total_seconds() / 3600.0


def check_b(rows):
    lags = []
    for cohort in DIRS:
        df = load("faults", cohort, None)
        h = lag_hours(df)
        lags.append(h)
        for rule, d in (("exact duplicates removed", df.drop_duplicates()),
                        ("one row per serial+session_id+fault_type+fault_value+fault_timestamp+fault_status "
                         "(earliest date kept)", df.sort_values("date").drop_duplicates(DEDUP_KEY))):
            hd = lag_hours(d)
            rows.append(("b", cohort, "rows, " + rule, int(len(d))))
            rows.append(("b", cohort, "median lag hours, " + rule, round(float(hd.median()), 1)))
            rows.append(("b", cohort, "p90 lag hours, " + rule, round(float(hd.quantile(0.9)), 1)))
        for name, s in ((cohort, h),):
            rows.append(("b", name, "rows with both timestamps", int(s.notna().sum())))
            rows.append(("b", name, "median lag hours (date - fault_timestamp)", round(float(s.median()), 1)))
            rows.append(("b", name, "p90 lag hours", round(float(s.quantile(0.9)), 1)))
            rows.append(("b", name, "rows with negative lag (date earlier than fault_timestamp)", int((s < 0).sum())))
    h = pd.concat(lags)  # "all" = raw rows of both cohorts
    rows.append(("b", "all", "rows with both timestamps", int(h.notna().sum())))
    rows.append(("b", "all", "median lag hours (date - fault_timestamp)", round(float(h.median()), 1)))
    rows.append(("b", "all", "p90 lag hours", round(float(h.quantile(0.9)), 1)))
    rows.append(("b", "all", "rows with negative lag (date earlier than fault_timestamp)", int((h < 0).sum())))


def check_c(rows):
    for cohort in DIRS:
        cs = load("clean_sessions", cohort, ["anonymized_serial", "session_id"])
        cs_pairs = set(zip(cs["anonymized_serial"], cs["session_id"]))
        for domain in ("motor", "battery"):
            df = load(domain, cohort, ["anonymized_serial", "session_id"]).drop_duplicates()
            pairs = set(zip(df["anonymized_serial"], df["session_id"]))
            hit = len(pairs & cs_pairs)
            rows.append(("c", f"{domain}/{cohort}", "distinct serial+session_id pairs", len(pairs)))
            rows.append(("c", f"{domain}/{cohort}", "pairs also in clean_sessions", hit))
            rows.append(("c", f"{domain}/{cohort}", "pct found in clean_sessions", round(100.0 * hit / len(pairs), 2)))
    for domain in ("motor", "battery"):
        tot = sum(r[3] for r in rows if r[0] == "c" and r[1].startswith(domain) and r[2] == "distinct serial+session_id pairs")
        hit = sum(r[3] for r in rows if r[0] == "c" and r[1].startswith(domain) and r[2] == "pairs also in clean_sessions")
        rows.append(("c", f"{domain}/all", "distinct serial+session_id pairs", tot))
        rows.append(("c", f"{domain}/all", "pairs also in clean_sessions", hit))
        rows.append(("c", f"{domain}/all", "pct found in clean_sessions", round(100.0 * hit / tot, 2)))


def main():
    rows = []
    check_a(rows)
    check_b(rows)
    check_c(rows)
    out = pd.DataFrame(rows, columns=["check", "scope", "metric", "value"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT, index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
