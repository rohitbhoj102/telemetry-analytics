"""Step 8 prep: three flat CSVs for Tableau, written to data/model/tableau/.

Reads data/model/ and reports/insights/key_numbers.csv. Every rate and DQ row count in the
insight and DQ files is taken from key_numbers.csv and then re-checked against data/model/;
the script exits non-zero (AssertionError) if anything differs.
"""
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "data" / "model"
OUT = MODEL / "tableau"
KEY = ROOT / "reports" / "insights" / "key_numbers.csv"

COHORT = {"normal": "Normal", "return_repair": "Return/Repair"}
TOL = 1e-3          # key_numbers.csv stores values to 6 significant figures


def fmt1(raw):
    """One decimal, rounding half up, from the text stored in key_numbers.csv."""
    return str(Decimal(str(raw).strip()).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def machines(ms):
    d = pd.DataFrame({
        "machine_id": ms.anonymized_serial.str[:6],
        "cohort": ms.cohort.map(COHORT),
        "model_family": ms.model.fillna("").str[:4].where(lambda s: s.isin(["SV50", "SV53"]), "Unknown"),
        "sub_model": ms.model.fillna("Unknown"),
        "region": ms.region.fillna("Unknown"),
        "rate_eligible": np.where(ms.n_sessions >= 10, "Yes", "No"),
        "n_sessions": ms.n_sessions,
        "sessions_per_week": ms.sessions_per_week,
        "faults_all": ms.n_faults_primary,
        "faults_filter_wash": ms.n_faults_t13_v1_primary,
        "faults_airway_running": ms.n_faults_t12_v1_primary,
        "faults_airway_error": ms.n_faults_t12_v2_primary,
        "motor_min_per_day": ms.motor_runtime_s_per_day / 60.0,
        "outlier_flag": np.where(ms.flag_outlier_sessions_per_week | ms.flag_outlier_faults_per_100, "Yes", "No"),
    })
    assert d.cohort.notna().all()
    assert d.machine_id.is_unique, "6-character machine_id is not unique"
    assert (d.rate_eligible == "Yes").sum() == ms.rate_eligible.sum()
    assert ((d.rate_eligible == "Yes") == ms.rate_eligible).all()
    return d


def rates(k, ms):
    kv = k.set_index("id")
    rows = []
    # chart, group, group_order, id stem, (component label, id prefix) pairs, total id
    specs = [
        ("Fault rate by model", "Normal SV50", 1, "normal_SV50", "i1_total_",
         [("Filter Wash (maintenance alert)", "i1_fw_"), ("Other faults", "i1_other_")]),
        ("Fault rate by model", "Normal SV53", 2, "normal_SV53", "i1_total_",
         [("Filter Wash (maintenance alert)", "i1_fw_"), ("Other faults", "i1_other_")]),
        ("Fault rate by model", "Return/Repair SV53", 3, "return_repair_SV53", "i1_total_",
         [("Filter Wash (maintenance alert)", "i1_fw_"), ("Other faults", "i1_other_")]),
        ("Airway blockage, SV53", "Normal SV53", 2, "normal", "i2_t12_main_",
         [("Blocked, still running (12/1)", "i2_t12_v1_main_"), ("Blocked, in error (12/2)", "i2_t12_v2_main_")]),
        ("Airway blockage, SV53", "Return/Repair SV53", 3, "return_repair", "i2_t12_main_",
         [("Blocked, still running (12/1)", "i2_t12_v1_main_"), ("Blocked, in error (12/2)", "i2_t12_v2_main_")]),
    ]
    for chart, group, order, stem, tot_prefix, comps in specs:
        t = kv.loc[tot_prefix + stem]
        n = int(t.n_machines)
        label = "%s (95%% interval %s to %s), %d machines" % (
            fmt1(t.value_raw), fmt1(t.interval_low_raw), fmt1(t.interval_high_raw), n)
        parts = 0.0
        for comp, prefix in comps:
            c = kv.loc[prefix + stem]
            assert int(c.n_machines) == n, (chart, group, comp)
            parts += c.value
            rows.append(dict(chart=chart, group=group, group_order=order, component=comp,
                             rate_per_100=c.value, total_rate=t.value, total_low=t.interval_low,
                             total_high=t.interval_high, n_machines=n, total_label=label))
        assert abs(parts - t.value) < TOL, ("components do not add to total", chart, group, parts, t.value)
    out = pd.DataFrame(rows)

    # independent recomputation from data/model: pooled events per 100 sessions, eligible machines
    elig = ms[ms.rate_eligible].copy()
    elig["grp"] = elig.cohort.map(COHORT) + " " + elig.model.fillna("").str[:4]
    elig["fw"] = elig.n_faults_t13_v1_primary
    elig["other"] = elig.n_faults_primary - elig.n_faults_t13_v1_primary
    elig["v1"] = elig.n_faults_t12_v1_primary
    elig["v2"] = elig.n_faults_t12_v2_primary
    pooled = elig.groupby("grp").agg(sessions=("n_sessions", "sum"), machines=("anonymized_serial", "size"),
                                     fw=("fw", "sum"), other=("other", "sum"), v1=("v1", "sum"), v2=("v2", "sum"))
    want = {"Filter Wash (maintenance alert)": "fw", "Other faults": "other",
            "Blocked, still running (12/1)": "v1", "Blocked, in error (12/2)": "v2"}
    for r in out.itertuples():
        p = pooled.loc[r.group]
        assert int(p.machines) == r.n_machines, ("machine count", r.chart, r.group, p.machines, r.n_machines)
        calc = 100.0 * p[want[r.component]] / p.sessions
        assert abs(calc - r.rate_per_100) < TOL, ("rate differs from data/model", r.chart, r.group, r.component, calc, r.rate_per_100)
    return out


def dq_volume(k, t):
    kv = k.set_index("id")
    names = {"clean_sessions": "Sessions", "faults": "Faults", "motor": "Motor", "battery": "Battery"}
    rows = []
    for tb, label in names.items():
        for c, clab in COHORT.items():
            for stage, order, pre in (("Raw rows", 1, "dq_raw_"), ("Analysis rows", 2, "dq_analysis_")):
                rows.append(dict(table=label, cohort=clab, stage=stage, stage_order=order,
                                 rows=int(kv.loc["%s%s_%s" % (pre, tb, c)].value)))
    out = pd.DataFrame(rows)
    # analysis rows must equal the rows in data/model
    ms = t["ms"]
    model_rows = {
        "Sessions": t["fact_session"].cohort.value_counts(),
        "Faults": t["fact_fault"].cohort.value_counts(),
        "Motor": ms.groupby("cohort").n_motor_snapshots.sum(),
        "Battery": ms.groupby("cohort").n_battery_snapshots.sum(),
    }
    for r in out[out.stage == "Analysis rows"].itertuples():
        key = {v: k_ for k_, v in COHORT.items()}[r.cohort]
        assert int(model_rows[r.table][key]) == r.rows, ("DQ analysis rows differ from data/model", r.table, r.cohort)
    return out


def main():
    k = pd.read_csv(KEY)
    raw = pd.read_csv(KEY, dtype=str)
    k["value_raw"], k["interval_low_raw"], k["interval_high_raw"] = raw.value, raw.interval_low, raw.interval_high
    t = {"ms": pd.read_csv(MODEL / "machine_summary.csv"),
         "fact_session": pd.read_csv(MODEL / "fact_session.csv", usecols=["cohort"]),
         "fact_fault": pd.read_csv(MODEL / "fact_fault.csv", usecols=["cohort"])}
    OUT.mkdir(parents=True, exist_ok=True)
    files = {"tableau_machines.csv": machines(t["ms"]),
             "tableau_insight_rates.csv": rates(k, t["ms"]),
             "tableau_dq_volume.csv": dq_volume(k, t)}
    for name, df in files.items():
        df.to_csv(OUT / name, index=False)
        print("%-28s %5d rows  %2d cols" % (name, len(df), df.shape[1]))


if __name__ == "__main__":
    main()
