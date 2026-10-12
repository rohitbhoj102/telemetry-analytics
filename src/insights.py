"""Step 7: final insights. All numbers, key_numbers.csv and the final charts come from here.

Reads data/model/ for every analysis number. The DQ headline numbers (raw vs analysis rows, % exact
copies, % empty payloads) are not in the model tables, so they are read from the generated Step 3/4
reports (reports/profiling/parse_summary.csv, reports/dq/dq_summary.csv) and cross-checked against
data/model/. Python 3.8 compatible. Nothing here changes the pipeline or earlier outputs.

Method rules (project decisions):
- Fault rates are pooled (total faults / total sessions x 100); intervals are 95% percentile
  bootstraps resampling machines within each group (2,000 resamples, fixed seed).
- Continuous measures use machine-level medians with the same bootstrap.
- Machines are the unit. Same thresholds as Step 6 (rate-eligible = >= 10 analysis sessions).
- Return/Repair (RR) is a selected population; nothing here claims a cause.
- Filter Wash (13/1) as a "maintenance alert" is our analytical grouping, not the brief's.
"""
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eda_helpers as h  # noqa: E402

ROOT = h.ROOT
OUT_DIR = ROOT / "reports" / "insights"
FIG_DIR = ROOT / "reports" / "figures" / "final"
SLIDE_DIR = ROOT / "reports" / "figures" / "slide"      # slide-sized versions (Step 9), no titles
N_BOOT, SEED = h.N_BOOT, h.SEED
NORMAL, RR = h.NORMAL, h.RR
FW_LABEL = "Filter Wash 13/1 (maintenance alert; our grouping)"
KEY_COLS = ["id", "insight", "metric", "group", "value", "interval_low", "interval_high",
            "n_machines", "n_events_or_sessions", "n_denominator", "denominator_unit", "unit", "script_or_cell", "note"]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def pooled_ci(d, num_cols, den_col, scale=100.0, n_boot=N_BOOT, seed=SEED):
    """Pooled rate (sum num / sum den x scale) per count column with a 95% machine bootstrap.

    All count columns share the same resamples, so components and totals are consistent.
    Returns {col: (rate, lo, hi)} plus the machine count, summed counts and summed denominator.
    """
    d = d.dropna(subset=list(num_cols) + [den_col])
    x = d[list(num_cols)].values.astype(float)
    den = d[den_col].values.astype(float)
    idx = np.random.RandomState(seed).randint(0, len(d), size=(n_boot, len(d)))
    den_b = den[idx].sum(axis=1)
    out = {}
    for j, c in enumerate(num_cols):
        b = scale * x[:, j][idx].sum(axis=1) / den_b
        lo, hi = np.percentile(b, [2.5, 97.5])
        out[c] = (scale * x[:, j].sum() / den.sum(), float(lo), float(hi))
    meta = {"n_machines": len(d), "counts": dict(zip(num_cols, x.sum(axis=0))), "denominator": float(den.sum())}
    return out, meta


def median_ci(values, n_boot=N_BOOT, seed=SEED):
    """Median of a machine-level sample with a 95% bootstrap interval (median, lo, hi)."""
    return h.one_sample_ci(values, n_boot=n_boot, seed=seed)


def about(ratio):
    """Ratio rounded for text: 'about 5x'."""
    if pd.isna(ratio):
        return "n/a"
    return "about %dx" % int(round(ratio)) if ratio >= 1.5 else "about %.1fx" % ratio


class KeyNumbers(object):
    """Collects one row per number used downstream."""

    def __init__(self):
        self.rows = []

    def add(self, id_, insight, metric, group, value, lo=np.nan, hi=np.nan, n_machines=np.nan,
            n_events=np.nan, unit="", src="", note="", den=np.nan, den_unit=""):
        self.rows.append(dict(id=id_, insight=insight, metric=metric, group=group, value=value,
                              interval_low=lo, interval_high=hi, n_machines=n_machines,
                              n_events_or_sessions=n_events, n_denominator=den, denominator_unit=den_unit, unit=unit, script_or_cell=src, note=note))

    def frame(self):
        df = pd.DataFrame(self.rows)[KEY_COLS]
        assert df["id"].is_unique, "duplicate key_numbers ids: %s" % df.loc[df["id"].duplicated(), "id"].tolist()
        return df


# ---------------------------------------------------------------------------
# Data preparation (data/model only)
# ---------------------------------------------------------------------------
FAULT_COLS = {"t11_v2": "n_faults_t11_v2_primary", "t12_v1": "n_faults_t12_v1_primary",
              "t12_v2": "n_faults_t12_v2_primary", "t13_v1": "n_faults_t13_v1_primary"}


def prepare(t):
    ms, ff, motor = t["summary"], t["fault"], t["motor"]
    # the four fault type/value pairs in the model must be exactly the ones counted below
    pairs = set(map(tuple, ff[["fault_type", "fault_value"]].drop_duplicates().values.tolist()))
    assert pairs == {(11, 2), (12, 1), (12, 2), (13, 1)}, pairs
    elig = ms[ms.rate_eligible].copy()
    for k, c in FAULT_COLS.items():
        elig["n_" + k] = elig[c]
    elig["n_t12"] = elig.n_t12_v1 + elig.n_t12_v2
    elig["n_all"] = elig.n_t11_v2 + elig.n_t12 + elig.n_t13_v1
    elig["n_other"] = elig.n_all - elig.n_t13_v1
    assert (elig.n_all == elig.n_faults_primary).all()
    elig["family"] = elig.model.fillna("").str[:4]
    elig["grp"] = elig.cohort + "|" + elig.family

    c4c = ms[ms.motor_runtime_s_per_day.notna()].copy()
    c4c["motor_min_per_day"] = c4c.motor_runtime_s_per_day / 60.0
    assert len(h.sv53(c4c)) == len(c4c), "motor-runtime machines are not all SV53"

    mv = motor[motor.delta_valid & (motor.days_elapsed > 0)].copy()
    return dict(ms=ms, ff=ff, elig=elig, c4c=c4c, mv=mv)


def exposure_table(P):
    """SV53 machines in the faults table with a valid motor period; faults inside the motor window."""
    ms, ff, mv = P["ms"], P["ff"], P["mv"]
    win = mv.groupby("anonymized_serial").agg(ws=("period_start_ts", "min"), we=("period_end_ts", "max"),
                                              rt_s=("delta_runtime_s", "sum"))
    f12 = ff[ff.fault_type == 12][["anonymized_serial", "fault_timestamp", "fault_value"]].merge(
        win, left_on="anonymized_serial", right_index=True)
    f12 = f12[(f12.fault_timestamp >= f12.ws) & (f12.fault_timestamp <= f12.we)]
    n12 = f12.groupby("anonymized_serial").size().rename("n_t12_win")
    n1 = f12[f12.fault_value == 1].groupby("anonymized_serial").size().rename("n_t12_1_win")
    n2 = f12[f12.fault_value == 2].groupby("anonymized_serial").size().rename("n_t12_2_win")
    e = (ms[["anonymized_serial", "cohort", "model", "has_fault_analysis_rows"]]
         .join(win, on="anonymized_serial", how="inner").join(n12, on="anonymized_serial")
         .join(n1, on="anonymized_serial").join(n2, on="anonymized_serial"))
    cnt = ["n_t12_win", "n_t12_1_win", "n_t12_2_win"]
    e[cnt] = e[cnt].fillna(0)
    assert (e.n_t12_win == e.n_t12_1_win + e.n_t12_2_win).all()
    e["hours"] = e.rt_s / 3600.0
    e = h.sv53(e[e.has_fault_analysis_rows])
    return e[e.hours >= 1].copy()


def common_month_motor(mv, min_machines=10):
    """Per-machine motor min/day over the common calendar months (same logic as Step 6b-d)."""
    recs = []
    for _, r in mv.iterrows():
        cur = r.period_start_ts.normalize().replace(day=1)
        while cur < r.period_end_ts:
            nxt = cur + pd.offsets.MonthBegin(1)
            ov = (min(nxt, r.period_end_ts) - max(cur, r.period_start_ts)).total_seconds() / 86400.0
            if ov > 0:
                recs.append((r.anonymized_serial, r.cohort, cur.strftime("%Y-%m"), ov,
                             r.delta_runtime_s * ov / r.days_elapsed))
            cur = nxt
    lm = pd.DataFrame(recs, columns=["anonymized_serial", "cohort", "month", "days", "runtime_s"])
    mc = (lm.groupby(["month", "cohort"]).anonymized_serial.nunique().unstack(fill_value=0)
          .reindex(columns=[NORMAL, RR]).fillna(0).astype(int))
    common = list(mc.index[(mc[NORMAL] >= min_machines) & (mc[RR] >= min_machines)])
    assert common == list(pd.period_range(common[0], common[-1], freq="M").astype(str)), "months not contiguous"
    ws = pd.Timestamp(common[0] + "-01")
    we = pd.Timestamp(common[-1] + "-01") + pd.offsets.MonthBegin(1)
    w1 = mv[(mv.period_start_ts >= ws) & (mv.period_end_ts <= we)]
    g1 = w1.groupby(["anonymized_serial", "cohort"]).agg(rt=("delta_runtime_s", "sum"), dd=("days_elapsed", "sum")).reset_index()
    g1["motor_min_per_day"] = g1.rt / g1.dd / 60.0
    l2 = lm[lm.month.isin(common)]
    g2 = l2.groupby(["anonymized_serial", "cohort"]).agg(rt=("runtime_s", "sum"), dd=("days", "sum")).reset_index()
    g2["motor_min_per_day"] = g2.rt / g2.dd / 60.0
    return common, g1, g2


# ---------------------------------------------------------------------------
# Data-quality headline numbers
# ---------------------------------------------------------------------------
def dq_numbers(t):
    ps = pd.read_csv(ROOT / "reports" / "profiling" / "parse_summary.csv")
    dq = pd.read_csv(ROOT / "reports" / "dq" / "dq_summary.csv").drop_duplicates()
    tabs = ["clean_sessions", "faults", "motor", "battery"]
    rows = []
    for tb in tabs:
        for c in (NORMAL, RR):
            raw = int(ps[(ps.table == tb) & (ps.cohort == c)].raw_rows_in.iloc[0])
            sel = dq[(dq.table == tb) & (dq.cohort == c) & dq.check.str.startswith("is_analysis_row")
                     & ~dq.check.str.contains("status_rule")]
            assert len(sel) == 1, (tb, c, len(sel))
            rows.append(dict(table=tb, cohort=c, raw_rows=raw, analysis_rows=int(sel.rows_affected.iloc[0])))
    d = pd.DataFrame(rows)
    d["pct_kept"] = 100.0 * d.analysis_rows / d.raw_rows

    # cross-checks against data/model
    nrm = {(r.cohort): r.rows for r in pd.read_csv(ROOT / "reports" / "model" / "table_row_counts.csv").itertuples()
           if r.table == "fact_session"}
    for c in (NORMAL, RR):
        assert int(d[(d.table == "clean_sessions") & (d.cohort == c)].analysis_rows.iloc[0]) == len(t["session"][t["session"].cohort == c])
        assert int(d[(d.table == "faults") & (d.cohort == c)].analysis_rows.iloc[0]) == len(t["fault"][t["fault"].cohort == c])
        assert int(d[(d.table == "motor") & (d.cohort == c)].analysis_rows.iloc[0]) == int(t["summary"][t["summary"].cohort == c].n_motor_snapshots.sum())
        assert int(d[(d.table == "battery") & (d.cohort == c)].analysis_rows.iloc[0]) == int(t["summary"][t["summary"].cohort == c].n_battery_snapshots.sum())

    def one(check, tb, c):
        r = dq[(dq.check.str.startswith(check)) & (dq.table == tb) & (dq.cohort == c)]
        assert len(r) == 1, (check, tb, c)
        return int(r.rows_affected.iloc[0])

    extra = []
    for c in (NORMAL, RR, "all"):
        raw_f = int(d[(d.table == "faults")].raw_rows.sum()) if c == "all" else int(d[(d.table == "faults") & (d.cohort == c)].raw_rows.iloc[0])
        raw_b = int(d[(d.table == "battery")].raw_rows.sum()) if c == "all" else int(d[(d.table == "battery") & (d.cohort == c)].raw_rows.iloc[0])
        n_ex = one("dup_class=exact_copy, not kept", "faults", c)
        n_em = one("parse_status=empty_payload", "battery", c)
        extra.append(dict(cohort=c, exact_copy_rows=n_ex, fault_raw=raw_f, pct_exact_copy=100.0 * n_ex / raw_f,
                          empty_rows=n_em, battery_raw=raw_b, pct_empty=100.0 * n_em / raw_b))
    return d, pd.DataFrame(extra)


def recording_numbers():
    """Share of analysis sessions per cohort for three fields the cohorts record differently.

    Read from the flagged session table (data/clean/dq/clean_sessions.parquet, is_analysis_row only) and
    cross-checked against reports/dq/dq_summary.csv where that file has the same count.
    """
    import duckdb
    con = duckdb.connect()
    q = """SELECT cohort, count(*) AS base,
                  sum(CASE WHEN log3_time_sync_old = 0 THEN 1 ELSE 0 END) AS log3_zero,
                  sum(CASE WHEN flag_temp_not_reported THEN 1 ELSE 0 END) AS temp_not_reported,
                  sum(CASE WHEN flag_dust_sentinel THEN 1 ELSE 0 END) AS dust_sentinel
           FROM read_parquet('%s') WHERE is_analysis_row GROUP BY cohort""" % (ROOT / "data" / "clean" / "dq" / "clean_sessions.parquet")
    g = con.execute(q).df().set_index("cohort")
    dq = pd.read_csv(ROOT / "reports" / "dq" / "dq_summary.csv").drop_duplicates()

    def dq_count(prefix, c):
        r = dq[dq.check.str.startswith(prefix) & (dq.table == "clean_sessions") & (dq.cohort == c)]
        assert len(r) == 1, (prefix, c)
        return int(r.rows_affected.iloc[0])

    meta = [("log3_zero", "log3_time_sync_old", "log3_time_sync_old = 0, % of analysis sessions", None,
             "meaning of log3_time_sync_old is not stated; the value 0 is a recorded value, not a null"),
            ("temp_not_reported", "temp_not_reported", "battery temperature not reported (no hot/cold/ok flag true), % of analysis sessions",
             "flag_temp_not_reported", "equals battery_temp_state = not_reported"),
            ("dust_sentinel", "dust_sentinel", "any dust column = 65535, % of analysis sessions",
             "flag_dust_sentinel", "65535 treated as a no-reading sentinel [inferred]")]
    rows = []
    for col, field, label, dq_prefix, note in meta:
        for c in (NORMAL, RR):
            n, base = int(g.loc[c, col]), int(g.loc[c, "base"])
            if dq_prefix:
                assert dq_count(dq_prefix, c) == n, (col, c, dq_count(dq_prefix, c), n)
            rows.append(dict(field={"log3_zero": "log3_zero", "temp_not_reported": "temp_not_reported",
                                    "dust_sentinel": "dust_sentinel"}[col], cohort=c, label=label, n=n, base=base,
                             pct=100.0 * n / base, note=note))
    return pd.DataFrame(rows)


def leave_one_out(s53, col, n_boot=N_BOOT, seed=SEED):
    """Finding 2 leave-one-out: RR minus Normal pooled difference per 100 sessions, dropping each RR machine in turn.

    Returns the min and max difference, the worst case (bootstrap rerun, same method and seed as the main
    result), the RR rate and ratio in the worst case, and the share of RR faults from the top 1 and top 3 machines.
    """
    rr = s53[s53.cohort == RR]
    nm = s53[s53.cohort == NORMAL]
    rate_n = 100.0 * nm[col].sum() / nm.n_sessions.sum()
    diffs = []
    for ser in rr.anonymized_serial:
        d = rr[rr.anonymized_serial != ser]
        diffs.append((100.0 * d[col].sum() / d.n_sessions.sum() - rate_n, ser))
    diffs.sort()
    worst_ser = diffs[0][1]
    r = h.compare_pooled(s53[s53.anonymized_serial != worst_ser], col, "n_sessions", scale=100.0, group="cohort",
                         a_val=NORMAL, b_val=RR, n_boot=n_boot, seed=seed)
    top = rr[col].sort_values(ascending=False)
    return dict(min_diff=diffs[0][0], max_diff=diffs[-1][0], worst_serial=worst_ser, worst=r,
                worst_rr_rate=r["rr"], worst_ratio=r["ratio"], total=float(rr[col].sum()),
                top1=float(top.iloc[:1].sum()), top3=float(top.iloc[:3].sum()), n_rr=len(rr), n_normal=len(nm),
                n_dropped_same_sign=int(sum(1 for d, _ in diffs if d > 0)))


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------
def compute(t=None):
    t = t or h.load_model()
    P = prepare(t)
    elig, c4c, ms, dim = P["elig"], P["c4c"], P["ms"], t["dim"]
    K = KeyNumbers()
    R = {"P": P}
    SRC = "src/insights.py"

    # ---- DQ + counts --------------------------------------------------------
    dqt, dqx = dq_numbers(t)
    R["dq_table"], R["dq_extra"] = dqt, dqx
    for r in dqt.itertuples():
        K.add("dq_raw_%s_%s" % (r.table, r.cohort), "DQ", "raw rows", "%s / %s" % (r.table, h.LABELS[r.cohort]),
              r.raw_rows, unit="rows", src=SRC + ":dq_numbers | reports/profiling/parse_summary.csv", note="column raw_rows_in")
        K.add("dq_analysis_%s_%s" % (r.table, r.cohort), "DQ", "analysis rows", "%s / %s" % (r.table, h.LABELS[r.cohort]),
              r.analysis_rows, unit="rows", src=SRC + ":dq_numbers | reports/dq/dq_summary.csv",
              note="check is_analysis_row (faults: primary count); cross-checked with data/model")
        K.add("dq_pct_kept_%s_%s" % (r.table, r.cohort), "DQ", "analysis rows as % of raw rows",
              "%s / %s" % (r.table, h.LABELS[r.cohort]), r.pct_kept, unit="%", src=SRC + ":dq_numbers | reports/dq/dq_summary.csv, reports/profiling/parse_summary.csv",
              n_events=r.analysis_rows, den=r.raw_rows, den_unit="raw rows")
    for tb, g in dqt.groupby("table"):
        K.add("dq_raw_%s_all" % tb, "DQ", "raw rows", "%s / both cohorts" % tb, int(g.raw_rows.sum()), unit="rows", src=SRC + ":dq_numbers | reports/profiling/parse_summary.csv", note="sum of cohorts")
        K.add("dq_analysis_%s_all" % tb, "DQ", "analysis rows", "%s / both cohorts" % tb, int(g.analysis_rows.sum()), unit="rows", src=SRC + ":dq_numbers | reports/dq/dq_summary.csv", note="sum of cohorts")
        K.add("dq_pct_kept_%s_all" % tb, "DQ", "analysis rows as % of raw rows", "%s / both cohorts" % tb,
              100.0 * g.analysis_rows.sum() / g.raw_rows.sum(), unit="%",
              src=SRC + ":dq_numbers | reports/dq/dq_summary.csv, reports/profiling/parse_summary.csv",
              n_events=int(g.analysis_rows.sum()), den=int(g.raw_rows.sum()), den_unit="raw rows")
    for r in dqx.itertuples():
        lab = "all" if r.cohort == "all" else h.LABELS[r.cohort]
        K.add("dq_exact_copy_faults_" + r.cohort, "DQ", "faults: exact copies not kept, % of raw rows", lab,
              r.pct_exact_copy, unit="%", n_events=r.exact_copy_rows, den=r.fault_raw, den_unit="raw fault rows",
              src=SRC + ":dq_numbers | reports/dq/dq_summary.csv, reports/profiling/parse_summary.csv",
              note="%d of %d raw fault rows; identical in all 14 raw columns" % (r.exact_copy_rows, r.fault_raw))
        K.add("dq_empty_battery_" + r.cohort, "DQ", "battery: empty payloads, % of raw rows", lab,
              r.pct_empty, unit="%", n_events=r.empty_rows, den=r.battery_raw, den_unit="raw battery rows",
              src=SRC + ":dq_numbers | reports/dq/dq_summary.csv, reports/profiling/parse_summary.csv",
              note="%d of %d raw battery rows have no decoded_data" % (r.empty_rows, r.battery_raw))

    # ---- fields the cohorts record differently (share of analysis sessions) ----
    rec = recording_numbers()
    R["recording"] = rec
    for r in rec.itertuples():
        K.add("rec_%s_%s" % (r.field, r.cohort), "DQ", r.label, h.LABELS[r.cohort], r.pct, unit="%",
              n_events=r.n, den=r.base, den_unit="analysis sessions", src=SRC + ":recording_numbers | data/clean/dq/clean_sessions.parquet",
              note=r.note)

    def cnt(mask_df):
        return mask_df.groupby("cohort").anonymized_serial.nunique().reindex([NORMAL, RR]).fillna(0).astype(int)

    mach = {"machines_all": ("machines in dim_machine", cnt(dim)),
            "machines_rate_eligible": ("rate-eligible machines (>= 10 analysis sessions)", cnt(elig)),
            "machines_motor_runtime": ("machines with a valid motor runtime per day", cnt(c4c)),
            "machines_with_faults": ("machines with >= 1 fault occurrence (fact_fault)", cnt(t["fault"]))}
    for k, (m, s) in mach.items():
        for c in (NORMAL, RR):
            K.add("%s_%s" % (k, c), "counts", m, h.LABELS[c], int(s[c]), n_machines=int(s[c]), unit="machines", src=SRC + ":compute")
    gap = t["motor"].groupby("cohort").days_elapsed.median()
    for c in (NORMAL, RR):
        K.add("motor_gap_median_days_" + c, "counts", "median days between consecutive motor snapshots (fact_motor_period.days_elapsed)",
              h.LABELS[c], float(gap[c]), unit="days", src=SRC + ":compute",
              note="snapshot spacing is uneven, hence per-day rates; all motor periods in the model")
    fam_n = elig.groupby(["cohort", "family"]).size()
    for (c, fam), n in fam_n.items():
        K.add("machines_eligible_%s_%s" % (c, fam), "counts", "rate-eligible machines by model family",
              "%s %s" % (h.LABELS[c], fam), int(n), n_machines=int(n), unit="machines", src=SRC + ":compute")
    R["machine_counts"] = pd.DataFrame({v[0]: v[1] for v in mach.values()}).T.rename(columns=h.LABELS)

    # ---- Insight 1: model effect ---------------------------------------------
    groups1 = [("normal|SV50", "Normal SV50"), ("normal|SV53", "Normal SV53"), ("return_repair|SV53", "Return/Repair SV53")]
    comp = ["n_all", "n_t13_v1", "n_other"]
    rows1 = []
    for key, lab in groups1:
        d = elig[elig.grp == key]
        res, meta = pooled_ci(d, comp + ["n_t12_v1", "n_t12_v2", "n_t11_v2"], "n_sessions")
        slug = key.replace("|", "_")
        for col, name, idn in [("n_all", "all fault types", "total"), ("n_t13_v1", FW_LABEL, "fw"),
                               ("n_other", "all other faults (excl. 13/1)", "other"),
                               ("n_t12_v1", "12/1 inlet blocked, motor still running", "t12v1"),
                               ("n_t12_v2", "12/2 inlet blocked and in error", "t12v2"),
                               ("n_t11_v2", "11/2 Battery Temperature HOT", "t11v2")]:
            v, lo, hi = res[col]
            rows1.append(dict(group=lab, measure=name, rate=v, lo=lo, hi=hi, machines=meta["n_machines"],
                              faults=int(meta["counts"][col]), sessions=int(meta["denominator"])))
            K.add("i1_%s_%s" % (idn, slug), "Insight 1", "pooled faults per 100 sessions: " + name, lab, v, lo, hi,
                  meta["n_machines"], int(meta["counts"][col]), "per 100 sessions", SRC + ":compute (insight 1)",
                  "denominator %d clean sessions; rate-eligible machines" % meta["denominator"]
                  + ("; 13/1 grouping is ours, not the brief's" if idn in ("fw", "other") else ""),
                  den=meta["denominator"], den_unit="clean sessions")
    R["i1_rates"] = pd.DataFrame(rows1)

    def pdiff(d, num, a_val, b_val, scale=100.0, den="n_sessions", grp="grp"):
        r = h.compare_pooled(d, num, den, scale=scale, group=grp, a_val=a_val, b_val=b_val)
        return r

    diffs1 = []
    for cmp_id, (a, b, lab) in {"normal_sv53_minus_sv50": ("normal|SV50", "normal|SV53", "Normal: SV53 minus SV50"),
                                "rr_minus_normal_sv53": ("normal|SV53", "return_repair|SV53", "SV53: Return/Repair minus Normal")}.items():
        for col, name, idn in [("n_all", "all fault types", "total"), ("n_t13_v1", FW_LABEL, "fw"),
                               ("n_other", "all other faults (excl. 13/1)", "other")]:
            r = pdiff(elig, col, a, b)
            diffs1.append(dict(comparison=lab, measure=name, a=r["normal"], b=r["rr"], diff=r["diff"], ratio=r["ratio"],
                               lo=r["ci_lo"], hi=r["ci_hi"], n_a=r["n_normal"], n_b=r["n_rr"]))
            K.add("i1_diff_%s_%s" % (idn, cmp_id), "Insight 1", "difference in pooled faults per 100 sessions: " + name, lab,
                  r["diff"], r["ci_lo"], r["ci_hi"], r["n_normal"] + r["n_rr"], np.nan, "per 100 sessions",
                  SRC + ":compute (insight 1)", "n machines %d vs %d; ratio %.2f (%s)" % (r["n_normal"], r["n_rr"], r["ratio"], about(r["ratio"])))
    R["i1_diffs"] = pd.DataFrame(diffs1)
    g = R["i1_diffs"].set_index(["comparison", "measure"])
    gap_t = g.loc[("Normal: SV53 minus SV50", "all fault types"), "diff"]
    gap_f = g.loc[("Normal: SV53 minus SV50", FW_LABEL), "diff"]
    R["i1_fw_share"] = gap_f / gap_t
    K.add("i1_fw_share_of_gap", "Insight 1", "share of the Normal SV50-vs-SV53 gap in pooled rate that is Filter Wash 13/1",
          "Normal: SV53 minus SV50", 100.0 * R["i1_fw_share"], unit="%", src=SRC + ":compute (insight 1)",
          note="ratio of point differences (no interval); 13/1 grouping is ours")

    # ---- Insight 2: airway blockage, SV53 only -------------------------------
    s53 = h.sv53(elig)
    cols2 = ["n_t12", "n_t12_v1", "n_t12_v2"]
    names2 = {"n_t12": "type 12 airway blockage (values 1+2)", "n_t12_v1": "12/1 inlet blocked, motor still running",
              "n_t12_v2": "12/2 inlet blocked and in error"}
    rows2 = []
    subsets = [("SV53", s53), ("SV53, ROW-PROD only", s53[s53.region == "ROW-PROD"]),
               ("SV53-AB only", s53[s53.model == "SV53-AB"]),
               ("SV53-AB, ROW-PROD only", s53[(s53.model == "SV53-AB") & (s53.region == "ROW-PROD")])]
    tag = {"SV53": "main", "SV53, ROW-PROD only": "rowprod", "SV53-AB only": "ab", "SV53-AB, ROW-PROD only": "ab_rowprod"}
    for sname, sd in subsets:
        for c in (NORMAL, RR):
            d = sd[sd.cohort == c]
            res, meta = pooled_ci(d, cols2, "n_sessions")
            for col in cols2:
                v, lo, hi = res[col]
                rows2.append(dict(subset=sname, cohort=h.LABELS[c], measure=names2[col], col=col, rate=v, lo=lo, hi=hi,
                                  machines=meta["n_machines"], faults=int(meta["counts"][col]), sessions=int(meta["denominator"])))
                K.add("i2_%s_%s_%s" % (col[2:], tag[sname], c), "Insight 2", "pooled faults per 100 sessions: " + names2[col],
                      "%s / %s" % (h.LABELS[c], sname), v, lo, hi, meta["n_machines"], int(meta["counts"][col]),
                      "per 100 sessions", SRC + ":compute (insight 2)", "denominator %d clean sessions" % meta["denominator"],
                      den=meta["denominator"], den_unit="clean sessions")
        for col in ("n_t12", "n_t12_v2"):
            r = pdiff(sd, col, NORMAL, RR, grp="cohort")
            K.add("i2_diff_%s_%s" % (col[2:], tag[sname]), "Insight 2", "difference (RR minus Normal), pooled per 100 sessions: " + names2[col],
                  sname, r["diff"], r["ci_lo"], r["ci_hi"], r["n_normal"] + r["n_rr"], np.nan, "per 100 sessions",
                  SRC + ":compute (insight 2)", "n machines %d vs %d; ratio %.2f (%s)" % (r["n_normal"], r["n_rr"], r["ratio"], about(r["ratio"])))
            K.add("i2_ratio_%s_%s" % (col[2:], tag[sname]), "Insight 2", "ratio RR / Normal, pooled per 100 sessions: " + names2[col],
                  sname, r["ratio"], unit="ratio", src=SRC + ":compute (insight 2)", note="rounded in text: " + about(r["ratio"]))
    R["i2_rates"] = pd.DataFrame(rows2)

    # leave-one-out on the main Finding 2 sample (SV53): drop each RR machine in turn
    loo_rows = []
    for col, idn, nm_ in (("n_t12", "t12", names2["n_t12"]), ("n_t12_v2", "t12v2", names2["n_t12_v2"])):
        L = leave_one_out(s53, col)
        loo_rows.append(dict(measure=nm_, **{k: v for k, v in L.items() if k not in ("worst",)},
                             worst_lo=L["worst"]["ci_lo"], worst_hi=L["worst"]["ci_hi"], worst_diff=L["worst"]["diff"]))
        base = "SV53, RR machines dropped one at a time (%d fits)" % L["n_rr"]
        m = "RR minus Normal, pooled per 100 sessions: " + nm_
        K.add("i2_loo_%s_min_diff" % idn, "Insight 2", "leave-one-out minimum difference; " + m, base, L["min_diff"],
              n_machines=L["n_rr"] + L["n_normal"] - 1, unit="per 100 sessions", src=SRC + ":leave_one_out",
              note="all %d drops keep the same sign: %s; interval not recomputed for each drop" % (L["n_rr"], L["n_dropped_same_sign"] == L["n_rr"]))
        K.add("i2_loo_%s_max_diff" % idn, "Insight 2", "leave-one-out maximum difference; " + m, base, L["max_diff"],
              n_machines=L["n_rr"] + L["n_normal"] - 1, unit="per 100 sessions", src=SRC + ":leave_one_out")
        K.add("i2_loo_%s_worst" % idn, "Insight 2", "leave-one-out worst case (bootstrap rerun); " + m,
              "SV53, RR machine %s dropped" % L["worst_serial"][:6], L["worst"]["diff"], L["worst"]["ci_lo"], L["worst"]["ci_hi"],
              L["worst"]["n_normal"] + L["worst"]["n_rr"], unit="per 100 sessions", src=SRC + ":leave_one_out",
              note="n machines %d vs %d; ratio %.2f (%s); same method and seed as the main result" %
                   (L["worst"]["n_normal"], L["worst"]["n_rr"], L["worst"]["ratio"], about(L["worst"]["ratio"])))
        K.add("i2_loo_%s_worst_ratio" % idn, "Insight 2", "leave-one-out worst case: ratio RR / Normal; " + nm_,
              "SV53, RR machine %s dropped" % L["worst_serial"][:6], L["worst"]["ratio"], unit="ratio", src=SRC + ":leave_one_out",
              note="rounded in text: " + about(L["worst"]["ratio"]))
        K.add("i2_loo_%s_top1_share" % idn, "Insight 2", "share of RR faults from the single machine with most: " + nm_, "SV53 Return/Repair",
              100.0 * L["top1"] / L["total"], n_machines=1, n_events=L["top1"], den=L["total"], den_unit="RR faults (type/value as named)",
              unit="%", src=SRC + ":leave_one_out")
        K.add("i2_loo_%s_top3_share" % idn, "Insight 2", "share of RR faults from the 3 machines with most: " + nm_, "SV53 Return/Repair",
              100.0 * L["top3"] / L["total"], n_machines=3, n_events=L["top3"], den=L["total"], den_unit="RR faults (type/value as named)",
              unit="%", src=SRC + ":leave_one_out")
    R["i2_loo"] = pd.DataFrame(loo_rows)

    e = exposure_table(P)
    R["exposure"] = e
    cols_h = ["n_t12_win", "n_t12_1_win", "n_t12_2_win"]
    names_h = {"n_t12_win": names2["n_t12"], "n_t12_1_win": names2["n_t12_v1"], "n_t12_2_win": names2["n_t12_v2"]}
    rows2h = []
    for c in (NORMAL, RR):
        d = e[e.cohort == c]
        res, meta = pooled_ci(d, cols_h, "hours", scale=1.0)
        for col in cols_h:
            v, lo, hi = res[col]
            rows2h.append(dict(cohort=h.LABELS[c], measure=names_h[col], col=col, rate=v, lo=lo, hi=hi,
                               machines=meta["n_machines"], faults=int(meta["counts"][col]), hours=meta["denominator"]))
            K.add("i2h_%s_%s" % (col, c), "Insight 2", "pooled faults per motor runtime hour: " + names_h[col], h.LABELS[c],
                  v, lo, hi, meta["n_machines"], int(meta["counts"][col]), "per runtime hour", SRC + ":compute (insight 2, exposure)",
                  "runtime %.1f h; SV53 machines in the faults table with >= 1 h valid motor runtime; faults inside each machine's motor window" % meta["denominator"],
                  den=meta["denominator"], den_unit="motor runtime hours")
    for col, idn in (("n_t12_win", "t12"), ("n_t12_2_win", "t12v2")):
        r = h.compare_pooled(e, col, "hours", scale=1.0)
        K.add("i2h_diff_" + idn, "Insight 2", "difference (RR minus Normal), pooled per motor runtime hour: " + names_h[col], "SV53 exposure sample",
              r["diff"], r["ci_lo"], r["ci_hi"], r["n_normal"] + r["n_rr"], np.nan, "per runtime hour", SRC + ":compute (insight 2, exposure)",
              "n machines %d vs %d; ratio %.2f (%s)" % (r["n_normal"], r["n_rr"], r["ratio"], about(r["ratio"])))
        K.add("i2h_ratio_" + idn, "Insight 2", "ratio RR / Normal per motor runtime hour: " + names_h[col], "SV53 exposure sample",
              r["ratio"], unit="ratio", src=SRC + ":compute (insight 2, exposure)", note="rounded in text: " + about(r["ratio"]))
    R["i2_hour"] = pd.DataFrame(rows2h)
    R["i2_mix"] = pd.crosstab(s53.model, s53.cohort.map(h.LABELS)).assign(Total=lambda x: x.sum(axis=1))
    R["i2_region"] = pd.crosstab(s53.region.fillna("(not available)"), s53.cohort.map(h.LABELS))

    # ---- Insight 3: motor runtime per day --------------------------------------
    rows3 = []
    for c in (NORMAL, RR):
        v = c4c.loc[c4c.cohort == c, "motor_min_per_day"]
        m, lo, hi = median_ci(v)
        rows3.append(dict(cohort=h.LABELS[c], median=m, lo=lo, hi=hi, machines=len(v)))
        K.add("i3_median_main_" + c, "Insight 3", "median motor runtime, minutes per day (machine-level median)", h.LABELS[c],
              m, lo, hi, len(v), np.nan, "min/day", SRC + ":compute (insight 3)", "all motor-runtime machines are SV53")
        K.add("i3_valid_days_" + c, "Insight 3", "median observation window: valid motor days per machine", h.LABELS[c],
              float(c4c.loc[c4c.cohort == c, "motor_valid_days"].median()), n_machines=len(v), unit="days", src=SRC + ":compute (insight 3)",
              note="windows differ by cohort")
    R["i3_medians"] = pd.DataFrame(rows3)
    common, g1, g2 = common_month_motor(P["mv"])
    R["i3_common_months"] = common
    variants3 = [("main", "all valid periods", c4c), ("rowprod", "ROW-PROD only", c4c[c4c.region == "ROW-PROD"]),
                 ("ab", "SV53-AB only", c4c[c4c.model == "SV53-AB"]),
                 ("ab_rowprod", "SV53-AB, ROW-PROD only", c4c[(c4c.model == "SV53-AB") & (c4c.region == "ROW-PROD")]),
                 ("window", "whole periods inside common months %s to %s" % (common[0], common[-1]), g1),
                 ("prorated", "pro-rated to common months %s to %s" % (common[0], common[-1]), g2)]
    rows3d = []
    for tg, lab, d in variants3:
        r = h.compare(d, "motor_min_per_day")
        rows3d.append(dict(variant=lab, n_normal=r["n_normal"], n_rr=r["n_rr"], normal=r["normal"], rr=r["rr"], diff=r["diff"],
                           ratio=r["ratio"], ci_lo=r["ci_lo"], ci_hi=r["ci_hi"]))
        if tg != "main":
            for c, val in ((NORMAL, r["normal"]), (RR, r["rr"])):
                K.add("i3_median_%s_%s" % (tg, c), "Insight 3", "median motor runtime, minutes per day", "%s / %s" % (h.LABELS[c], lab),
                      val, n_machines=r["n_" + ("normal" if c == NORMAL else "rr")], unit="min/day", src=SRC + ":compute (insight 3)",
                      note="robustness variant; interval is on the difference")
        K.add("i3_diff_" + tg, "Insight 3", "difference (RR minus Normal) in median motor minutes per day", lab,
              r["diff"], r["ci_lo"], r["ci_hi"], r["n_normal"] + r["n_rr"], np.nan, "min/day", SRC + ":compute (insight 3)",
              "n machines %d vs %d; ratio %.2f (%s)" % (r["n_normal"], r["n_rr"], r["ratio"], about(r["ratio"])))
        K.add("i3_ratio_" + tg, "Insight 3", "ratio RR / Normal, median motor minutes per day", lab, r["ratio"], unit="ratio",
              src=SRC + ":compute (insight 3)", note="rounded in text: " + about(r["ratio"]))
    R["i3_variants"] = pd.DataFrame(rows3d)
    R["i3_data"] = c4c
    R["i3_mix"] = pd.crosstab(c4c.model, c4c.cohort.map(h.LABELS)).assign(Total=lambda x: x.sum(axis=1))

    R["key"] = K.frame()
    R["step6_check"] = check_against_step6(R["key"])
    return R


# ---------------------------------------------------------------------------
# Consistency with Step 6 / 6b (values as printed in reports/eda/shortlist.md)
# ---------------------------------------------------------------------------
# (key_numbers id, field, printed value, shortlist reference)
STEP6_EXPECTED = [
    ("i1_total_normal_SV50", "value", "16.535", "6b-a all fault types pooled, SV50"),
    ("i1_total_normal_SV53", "value", "4.286", "6b-a all fault types pooled, SV53"),
    ("i1_fw_normal_SV50", "value", "11.440", "6b-a 13/1 pooled, SV50"),
    ("i1_fw_normal_SV53", "value", "1.474", "6b-a 13/1 pooled, SV53"),
    ("i1_other_normal_SV50", "value", "5.095", "6b-a excluding 13/1 pooled, SV50"),
    ("i1_other_normal_SV53", "value", "2.812", "6b-a excluding 13/1 pooled, SV53"),
    ("i1_diff_total_normal_sv53_minus_sv50", "value", "-12.249", "6b-a all fault types pooled gap"),
    ("i1_diff_total_normal_sv53_minus_sv50", "interval_low", "-17.877", "6b-a all fault types pooled gap, lower"),
    ("i1_diff_total_normal_sv53_minus_sv50", "interval_high", "-7.258", "6b-a all fault types pooled gap, upper"),
    ("i1_diff_other_normal_sv53_minus_sv50", "value", "-2.283", "6b-a excluding 13/1 gap"),
    ("i1_diff_other_normal_sv53_minus_sv50", "interval_low", "-5.334", "6b-a excluding 13/1 gap, lower"),
    ("i1_diff_other_normal_sv53_minus_sv50", "interval_high", "0.714", "6b-a excluding 13/1 gap, upper"),
    ("i1_total_return_repair_SV53", "value", "18.678", "6b-0 all fault types pooled, RR SV53"),
    ("i1_other_return_repair_SV53", "value", "13.090", "6b-0 excluding 13/1 pooled, RR SV53"),
    ("i1_fw_return_repair_SV53", "value", "5.588", "6b-0 13/1 pooled, RR SV53"),
    ("i1_diff_fw_rr_minus_normal_sv53", "interval_low", "0.176", "6b-0 13/1 pooled, SV53 only, lower"),
    ("i1_diff_fw_rr_minus_normal_sv53", "interval_high", "9.744", "6b-0 13/1 pooled, SV53 only, upper"),
    ("i2_t12_main_normal", "value", "2.812", "6b-b type 12 pooled, SV53 Normal"),
    ("i2_t12_main_return_repair", "value", "13.090", "6b-b type 12 pooled, SV53 RR"),
    ("i2_diff_t12_main", "value", "10.278", "6b-b type 12 pooled diff, SV53"),
    ("i2_diff_t12_main", "interval_low", "1.658", "6b-b type 12 pooled diff, lower"),
    ("i2_diff_t12_main", "interval_high", "24.744", "6b-b type 12 pooled diff, upper"),
    ("i2_t12_v2_main_normal", "value", "1.106", "6b-b 12/2 pooled, SV53 Normal"),
    ("i2_t12_v2_main_return_repair", "value", "6.501", "6b-b 12/2 pooled, SV53 RR"),
    ("i2_diff_t12_v2_main", "interval_low", "1.484", "6b-b 12/2 pooled diff, lower"),
    ("i2_diff_t12_v2_main", "interval_high", "11.482", "6b-b 12/2 pooled diff, upper"),
    ("i2_t12_rowprod_normal", "value", "2.380", "6b-c type 12, ROW-PROD Normal"),
    ("i2_t12_rowprod_return_repair", "value", "13.073", "6b-c type 12, ROW-PROD RR"),
    ("i2_diff_t12_rowprod", "interval_low", "1.960", "6b-c type 12 diff, ROW-PROD, lower"),
    ("i2_diff_t12_rowprod", "interval_high", "24.450", "6b-c type 12 diff, ROW-PROD, upper"),
    ("i2_t12_ab_normal", "value", "8.159", "6b-c type 12, SV53-AB Normal"),
    ("i2_t12_ab_return_repair", "value", "17.038", "6b-c type 12, SV53-AB RR"),
    ("i2_diff_t12_ab", "interval_low", "-8.588", "6b-c type 12 diff, SV53-AB, lower"),
    ("i2_diff_t12_ab", "interval_high", "33.822", "6b-c type 12 diff, SV53-AB, upper"),
    ("i2_diff_t12_v2_ab", "interval_low", "0.217", "6b-c 12/2 diff, SV53-AB, lower"),
    ("i2_diff_t12_v2_ab", "interval_high", "15.643", "6b-c 12/2 diff, SV53-AB, upper"),
    ("i2h_n_t12_win_normal", "value", "0.321", "6b-e type 12 per runtime hour, Normal (main)"),
    ("i2h_n_t12_win_return_repair", "value", "1.732", "6b-e type 12 per runtime hour, RR (main)"),
    ("i2h_diff_t12", "interval_low", "0.173", "6b-e type 12 per runtime hour diff, lower"),
    ("i2h_diff_t12", "interval_high", "3.121", "6b-e type 12 per runtime hour diff, upper"),
    ("i2h_n_t12_2_win_normal", "value", "0.090", "6b-e 12/2 per runtime hour, Normal"),
    ("i2h_n_t12_2_win_return_repair", "value", "0.873", "6b-e 12/2 per runtime hour, RR"),
    ("i2h_diff_t12v2", "interval_low", "0.232", "6b-e 12/2 per runtime hour diff, lower"),
    ("i2h_diff_t12v2", "interval_high", "1.514", "6b-e 12/2 per runtime hour diff, upper"),
    ("i3_median_main_normal", "value", "2.384", "C4c motor min/day, Normal"),
    ("i3_median_main_return_repair", "value", "4.869", "C4c motor min/day, RR"),
    ("i3_diff_main", "value", "2.485", "C4c diff"),
    ("i3_diff_main", "interval_low", "0.430", "C4c diff, lower"),
    ("i3_diff_main", "interval_high", "3.979", "C4c diff, upper"),
    ("i3_diff_rowprod", "interval_low", "0.291", "6b-c C4c ROW-PROD diff, lower"),
    ("i3_diff_rowprod", "interval_high", "4.074", "6b-c C4c ROW-PROD diff, upper"),
    ("i3_diff_ab", "interval_low", "-0.447", "6b-c C4c SV53-AB diff, lower"),
    ("i3_diff_ab", "interval_high", "5.377", "6b-c C4c SV53-AB diff, upper"),
    ("i3_diff_window", "value", "2.279", "6b-d whole periods inside common window diff"),
    ("i3_diff_window", "interval_low", "0.488", "6b-d whole periods diff, lower"),
    ("i3_diff_window", "interval_high", "3.905", "6b-d whole periods diff, upper"),
    ("i3_diff_prorated", "value", "2.581", "6b-d pro-rated diff"),
    ("i3_diff_prorated", "interval_low", "0.544", "6b-d pro-rated diff, lower"),
    ("i3_diff_prorated", "interval_high", "3.957", "6b-d pro-rated diff, upper"),
    ("i3_valid_days_normal", "value", "240", "Final selection: valid motor days, median Normal (printed to 3 digits)"),
    ("i3_valid_days_return_repair", "value", "91", "Final selection: valid motor days, median RR (printed to 2 digits)"),
]


def check_against_step6(key):
    k = key.set_index("id")
    rows = []
    for id_, field, printed, ref in STEP6_EXPECTED:
        if id_ not in k.index:
            rows.append(dict(id=id_, field=field, step6_printed=printed, step7=np.nan, matches=False, reference=ref + " (id missing)"))
            continue
        val = float(k.loc[id_, field])
        dec = len(printed.split(".")[1]) if "." in printed else 0
        step7 = round(val, dec)
        ok = abs(step7 - float(printed)) < 10 ** (-dec) * 0.51 if dec else (abs(round(val, 0) - float(printed)) < 0.5)
        rows.append(dict(id=id_, field=field, step6_printed=printed, step7=val, matches=bool(ok), reference=ref))
    return pd.DataFrame(rows)


EXTRA_PREFIXES = ("n_", "f_")      # rows appended by src/insights3.py (n_) and src/insights_final.py (f_)


def write_key_numbers(R):
    """Write this script's rows, keeping any n_ / f_ rows already in the file (appended by later scripts) untouched."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "key_numbers.csv"
    kept = []
    if path.exists():
        kept = [l for l in path.read_text().splitlines(keepends=True)[1:] if l.startswith(EXTRA_PREFIXES)]
    R["key"].to_csv(path, index=False, float_format="%.6g")
    if kept:
        with open(str(path), "a") as f:
            f.writelines(kept)
    R["step6_check"].to_csv(OUT_DIR / "step6_consistency.csv", index=False, float_format="%.6g")
    return path


# ---------------------------------------------------------------------------
# Charts (16:9, 13.33 x 7.5 in, 200 dpi). Same two cohort colours as the EDA charts.
# ---------------------------------------------------------------------------
GREY, INK = "#5F6368", "#202124"
SV50_BLUE = "#1B4478"          # darker shade of the Normal blue for SV50 (shade, not a new hue)


def _setup():
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.size": 14, "axes.labelsize": 14, "xtick.labelsize": 14, "ytick.labelsize": 13,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False,
                         "figure.dpi": 100, "svg.fonttype": "path"})
    return plt


def _frame(plt, title, subtitle, source, rect=None):
    fig = plt.figure(figsize=(13.333, 7.5))
    tl = textwrap.wrap(title, 60, break_on_hyphens=False)
    sl = textwrap.wrap(subtitle, 108, break_on_hyphens=False)
    fig.text(0.04, 0.955, "\n".join(tl), fontsize=22, fontweight="bold", color=INK, va="top")
    ys = 0.955 - 0.052 * len(tl) - 0.008
    fig.text(0.04, ys, "\n".join(sl), fontsize=14, color=GREY, va="top")
    fig.text(0.04, 0.025, "\n".join(textwrap.wrap(source, 118)), fontsize=12, color=GREY, va="bottom")
    return fig


def _tint(color, amount=0.55):
    import matplotlib.colors as mc
    r = np.array(mc.to_rgb(color))
    return tuple(r + (1 - r) * amount)


def _save(fig, name, out_dir=None, dpi=200):
    out_dir = out_dir or FIG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for ext in ("png", "svg"):
        p = out_dir / ("%s.%s" % (name, ext))
        fig.savefig(str(p), dpi=dpi)
        out.append(p)
    return out


import re as _re
from decimal import Decimal, ROUND_HALF_UP


def _fmt_csv(raw, nd, comma=False):
    """Format a value as stored in key_numbers.csv (text), rounding half up, so 2.485 prints as 2.49."""
    q = Decimal(1).scaleb(-nd)
    d = Decimal(str(raw).strip()).quantize(q, rounding=ROUND_HALF_UP)
    return ("{:,.%df}" if comma else "{:.%df}") % nd and (("{:,.%df}" if comma else "{:.%df}") % nd).format(d)


class Printed(object):
    """Every number a chart prints comes through here, read from reports/insights/key_numbers.csv.

    `num` formats a value from the file and records it; `verify` re-reads the file, re-checks every
    recorded number and scans the text on the figure for any number that did not come through `num`.
    """
    STATIC = {"95", "2,000", "10", "100", "0", "1"}      # method text: 95% interval, 2,000 resamples, >= 10 sessions, per 100, "spans 0"
    STRIP = [r"SV\d+", r"\d+/\d+", r"type 12", r"ROW-PROD", r"\bSV53-AB\b"]
    TOKEN = r"-?\d+(?:,\d{3})*(?:\.\d+)?"

    def __init__(self, path):
        self.path = path
        self.k = pd.read_csv(path).set_index("id")
        self.raw = pd.read_csv(path, dtype=str).set_index("id")      # value text exactly as stored
        self.log = []
        self.reg = set()

    def num(self, id_, field="value", nd=1, comma=False):
        s = _fmt_csv(self.raw.loc[id_, field], nd, comma)
        self.log.append((id_, field, nd, comma, s))
        self.reg.add(s)
        return s

    def count(self, id_, field="n_machines"):
        return self.num(id_, field, 0, comma=True)

    def ratio(self, id_):
        """'about 5x' from a ratio row; registers the integer."""
        txt = about(float(self.k.loc[id_, "value"]))
        for t in _re.findall(self.TOKEN, txt):
            self.reg.add(t)
        self.log.append((id_, "value", -1, False, txt))
        return txt

    def verify(self, fig, name, R):
        fresh = pd.read_csv(self.path).set_index("id")
        fresh_raw = pd.read_csv(self.path, dtype=str).set_index("id")
        fresh = fresh[~fresh.index.str.startswith(EXTRA_PREFIXES)]            # rows owned by later scripts
        fresh_raw = fresh_raw[~fresh_raw.index.str.startswith(EXTRA_PREFIXES)]
        # the file on disk must equal this run's computed numbers
        calc = R["key"].set_index("id")
        assert set(calc.index) == set(fresh.index), "key_numbers.csv ids differ from this run"
        for col in ("value", "interval_low", "interval_high"):
            a, b = calc[col].astype(float), fresh[col].astype(float)
            ok = (a.isna() & b.isna()) | ((a - b).abs() <= 1e-5 * (1 + b.abs()))
            assert ok.all(), "key_numbers.csv is stale vs computed %s: %s" % (col, list(ok.index[~ok])[:5])
        bad = []
        for id_, field, nd, comma, s in self.log:
            exp = about(float(fresh.loc[id_, field])) if nd == -1 else _fmt_csv(fresh_raw.loc[id_, field], nd, comma)
            if exp != s:
                bad.append((id_, field, s, exp))
        assert not bad, "%s: printed number differs from key_numbers.csv: %s" % (name, bad)
        # scan figure text for numbers that were not registered
        texts = [t.get_text() for t in fig.texts]
        for ax in fig.axes:
            texts += [t.get_text() for t in ax.texts] + [ax.get_title(), ax.get_xlabel(), ax.get_ylabel()]
            texts += [t.get_text() for t in ax.get_xticklabels() if not _re.fullmatch(r"[-−]?[\d.,]+", t.get_text())]
            leg = ax.get_legend()
            if leg:
                texts += [t.get_text() for t in leg.get_texts()]
        for lg in fig.legends:
            texts += [t.get_text() for t in lg.get_texts()]
        stray = []
        for tx in texts:
            for pat in self.STRIP:
                tx = _re.sub(pat, " ", tx)
            for tok in _re.findall(self.TOKEN, tx):
                if tok not in self.reg and tok not in self.STATIC:
                    stray.append(tok)
        assert not stray, "%s: numbers printed on the chart that are not from key_numbers.csv: %s" % (name, sorted(set(stray)))
        return len(self.log)


def chart_dq(R, P):
    plt = _setup()
    pk = lambda t, c: P.num("dq_pct_kept_%s_%s" % (t, c), nd=0)
    fig = _frame(plt, "Only %s%% of raw fault rows and %s%% of raw battery rows remain as distinct records after cleaning" %
                 (P.num("dq_pct_kept_faults_all", nd=0), P.num("dq_pct_kept_battery_all", nd=0)),
                 "Raw rows vs analysis rows, by table and cohort (all four tables, both cohorts)",
                 "Source: parse_summary.csv (raw rows), dq_summary.csv (analysis rows, cross-checked with data/model); "
                 "faults use the primary count")
    titles = {"clean_sessions": "Clean sessions", "faults": "Faults", "motor": "Motor snapshots", "battery": "Battery snapshots"}
    gs = fig.add_gridspec(2, 2, left=0.13, right=0.97, top=0.70, bottom=0.10, hspace=0.75, wspace=0.42)
    for i, tb in enumerate(["clean_sessions", "faults", "motor", "battery"]):
        ax = fig.add_subplot(gs[i // 2, i % 2])
        ymax = max(float(P.k.loc["dq_raw_%s_%s" % (tb, c), "value"]) for c in (NORMAL, RR))
        for j, c in enumerate([NORMAL, RR]):
            y = 1 - j
            raw, ana = float(P.k.loc["dq_raw_%s_%s" % (tb, c), "value"]), float(P.k.loc["dq_analysis_%s_%s" % (tb, c), "value"])
            ax.barh(y + 0.2, raw, height=0.36, color=_tint(h.COLORS[c], 0.65), edgecolor=h.COLORS[c], linewidth=1)
            ax.barh(y - 0.2, ana, height=0.36, color=h.COLORS[c])
            ax.text(raw + ymax * 0.015, y + 0.2, "%s raw" % P.num("dq_raw_%s_%s" % (tb, c), nd=0, comma=True), va="center", fontsize=12, color=INK)
            ax.text(ana + ymax * 0.015, y - 0.2, "%s analysis (%s%%)" % (P.num("dq_analysis_%s_%s" % (tb, c), nd=0, comma=True), pk(tb, c)),
                    va="center", fontsize=12, color=INK, fontweight="bold")
        ax.set_yticks([1, 0])
        ax.set_yticklabels(["Normal", "Return/\nRepair"])
        ax.set_xlim(0, ymax * 1.75)
        ax.set_xticks([])
        ax.spines["bottom"].set_visible(False)
        ax.set_title(titles[tb], fontsize=14, loc="left", color=INK)
    P.verify(fig, "01_dq", R)
    return fig, _save(fig, "01_dq_raw_vs_analysis_rows")


def chart_insight1(R, P):
    plt = _setup()
    from matplotlib.patches import Patch
    order = [("Normal SV50", "normal_SV50", h.COLORS[NORMAL], SV50_BLUE), ("Normal SV53", "normal_SV53", h.COLORS[NORMAL], h.COLORS[NORMAL]),
             ("Return/Repair SV53", "return_repair_SV53", h.COLORS[RR], h.COLORS[RR])]
    n = {g: P.count("i1_total_" + s) for g, s, _, _ in order}
    fig = _frame(plt, "Filter Wash alerts make up %s%% of the SV50 vs SV53 fault-rate gap" % P.num("i1_fw_share_of_gap", nd=0),
                 "Pooled faults per 100 clean sessions with 95%% intervals (machines resampled); rate-eligible machines "
                 "(>= 10 sessions): %s Normal SV50, %s Normal SV53, %s Return/Repair SV53" % (n["Normal SV50"], n["Normal SV53"], n["Return/Repair SV53"]),
                 "Source: fact_session, fact_fault, analysis rows; pooled rate, 2,000 machine-bootstrap resamples. "
                 "Filter Wash 13/1 as a 'maintenance alert' is our grouping, not the brief's.")
    ax = fig.add_axes([0.08, 0.21, 0.58, 0.50])
    f = lambda i, fld="value": float(P.k.loc[i, fld])
    hi_max = max(f("i1_total_" + s, "interval_high") for _, s, _, _ in order)
    for i, (g, s, hue, shade) in enumerate(order):
        oth, fw = f("i1_other_" + s), f("i1_fw_" + s)
        tot, lo, hi = f("i1_total_" + s), f("i1_total_" + s, "interval_low"), f("i1_total_" + s, "interval_high")
        ax.bar(i, oth, width=0.6, color=shade)
        ax.bar(i, fw, bottom=oth, width=0.6, color=_tint(shade, 0.55), edgecolor=shade, hatch="//", linewidth=1)
        ax.errorbar(i, tot, yerr=[[tot - lo], [hi - tot]], color=INK, capsize=7, lw=2, zorder=5)
        ax.text(i, hi + 0.6, "%s\n[%s to %s]" % (P.num("i1_total_" + s), P.num("i1_total_" + s, "interval_low"), P.num("i1_total_" + s, "interval_high")),
                ha="center", va="bottom", fontsize=13, fontweight="bold", color=INK)
        xl = i - 0.17                                 # segment labels sit left of the centred error bar
        ax.text(xl, oth / 2.0, P.num("i1_other_" + s), ha="center", va="center", fontsize=13, color="white", fontweight="bold")
        if fw > 3:
            ax.text(xl, oth + fw / 2.0, P.num("i1_fw_" + s), ha="center", va="center", fontsize=13, color=INK, fontweight="bold")
        else:
            ax.text(xl, oth + fw + 0.4, P.num("i1_fw_" + s), ha="center", va="bottom", fontsize=13, color=INK)
    ax.set_xticks(range(3))
    ax.set_xticklabels(["%s\n(%s machines)" % (g, n[g]) for g, _, _, _ in order])
    ax.set_ylabel("Faults per 100 clean sessions")
    ax.set_ylim(0, hi_max * 1.25)
    ax.annotate("", xy=(2, ax.get_ylim()[1] * 0.97), xytext=(1, ax.get_ylim()[1] * 0.97), arrowprops=dict(arrowstyle="<->", color=INK, lw=1.8))
    ax.text(1.5, ax.get_ylim()[1] * 0.99, "like-for-like", ha="center", va="bottom", fontsize=13, fontweight="bold", color=INK)
    fig.legend(handles=[Patch(facecolor="#777777", label="All other faults (11/2, 12/1, 12/2)"),
                        Patch(facecolor="#CCCCCC", edgecolor="#777777", hatch="//", label="Filter Wash 13/1\n(maintenance alert; our grouping)")],
               loc="upper left", bbox_to_anchor=(0.69, 0.71), frameon=False, fontsize=12)
    d = "i1_diff_total_rr_minus_normal_sv53"
    fig.text(0.69, 0.45, "Like-for-like comparison:\nReturn/Repair SV53 vs Normal SV53\n(not vs Normal SV50).\nDifference %s [%s, %s]" %
             (P.num(d), P.num(d, "interval_low"), P.num(d, "interval_high")), fontsize=13, color=INK, va="top", fontweight="bold")
    P.verify(fig, "02_insight1", R)
    return fig, _save(fig, "02_insight1_model_effect_fault_rate")


def _grouped_panel(ax, P, ids, categories, ylabel, nd):
    """ids: {(cohort, category index): key id}. Bars, centred 95% interval and a value label per bar."""
    w = 0.36
    top = 0.0
    for j, c in enumerate((NORMAL, RR)):
        for i, _ in enumerate(categories):
            kid = ids[(c, i)]
            v, lo, hi = (float(P.k.loc[kid, fld]) for fld in ("value", "interval_low", "interval_high"))
            xp = i + (j - 0.5) * (w + 0.04)
            ax.bar(xp, v, width=w, color=h.COLORS[c])
            ax.errorbar(xp, v, yerr=[[v - lo], [hi - v]], color=INK, capsize=6, lw=1.8, zorder=5)
            ax.text(xp, hi + 0.02 * max(top, hi), P.num(kid, nd=nd), ha="center", va="bottom", fontsize=13, fontweight="bold", color=INK)
            top = max(top, hi)
    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories)
    ax.set_ylabel(ylabel)
    ax.set_ylim(0, top * 1.35)


def chart_insight2(R, P):
    plt = _setup()
    from matplotlib.patches import Patch
    nl, nr = P.count("i2_t12_main_normal"), P.count("i2_t12_main_return_repair")
    hl, hr = P.count("i2h_n_t12_win_normal"), P.count("i2h_n_t12_win_return_repair")
    fig = _frame(plt, "Among SV53 machines, Return/Repair log several times (%s) the airway-blockage rate of Normal" % P.ratio("i2_ratio_t12_main"),
                 "Airway blockage (type 12) per 100 clean sessions (left) and per motor runtime hour (right), pooled, with 95%% intervals. "
                 "Left: %s Normal, %s Return/Repair machines; right: %s and %s" % (nl, nr, hl, hr),
                 "Source: fact_session, fact_fault, fact_motor_period, analysis rows; SV53 only; pooled rate, 2,000 machine-bootstrap resamples. "
                 "Return/Repair is a selected population.")
    cats = ["12/2\ninlet blocked\nand in error", "All type 12\n(12/1 + 12/2)"]
    ax1 = fig.add_axes([0.08, 0.22, 0.42, 0.49])
    _grouped_panel(ax1, P, {(NORMAL, 0): "i2_t12_v2_main_normal", (RR, 0): "i2_t12_v2_main_return_repair",
                            (NORMAL, 1): "i2_t12_main_normal", (RR, 1): "i2_t12_main_return_repair"}, cats, "Faults per 100 clean sessions", 1)
    ax1.set_title("Per 100 sessions", fontsize=14, loc="left", color=INK)
    ax2 = fig.add_axes([0.60, 0.22, 0.37, 0.49])
    _grouped_panel(ax2, P, {(NORMAL, 0): "i2h_n_t12_2_win_normal", (RR, 0): "i2h_n_t12_2_win_return_repair",
                            (NORMAL, 1): "i2h_n_t12_win_normal", (RR, 1): "i2h_n_t12_win_return_repair"}, cats, "Faults per motor runtime hour", 2)
    ax2.set_title("Per hour of motor runtime", fontsize=14, loc="left", color=INK)
    ax1.legend(handles=[Patch(color=h.COLORS[NORMAL], label="Normal"), Patch(color=h.COLORS[RR], label="Return/Repair")],
               loc="upper left", frameon=False, fontsize=12)
    P.verify(fig, "03_insight2", R)
    return fig, _save(fig, "03_insight2_airway_blockage_sv53")


def chart_insight3(R, P):
    plt = _setup()
    d = R["i3_data"]
    nn, nr = P.count("i3_median_main_normal"), P.count("i3_median_main_return_repair")
    fig = _frame(plt, "Return/Repair machines run %s the motor minutes per day of Normal machines" % P.ratio("i3_ratio_main"),
                 "Motor runtime, minutes per day, one dot per machine; bar = median with 95%% interval. SV53 machines with a valid motor period: "
                 "%s Normal, %s Return/Repair" % (nn, nr),
                 "Source: fact_motor_period, analysis rows, valid periods; machine-level median, 2,000 machine-bootstrap resamples. "
                 "Observation windows differ (median valid days: %s Normal, %s Return/Repair)." %
                 (P.num("i3_valid_days_normal", nd=0), P.num("i3_valid_days_return_repair", nd=0)))
    ax = fig.add_axes([0.10, 0.20, 0.58, 0.52])
    rng = np.random.RandomState(1)
    for i, c in enumerate((NORMAL, RR)):
        v = d.loc[d.cohort == c, "motor_min_per_day"].values
        ax.scatter(i + rng.uniform(-0.22, 0.22, len(v)), v, s=46, color=h.COLORS[c], alpha=0.6, linewidths=0, zorder=2)
        kid = "i3_median_main_" + c
        m, lo, hi = (float(P.k.loc[kid, fld]) for fld in ("value", "interval_low", "interval_high"))
        ax.hlines(m, i - 0.34, i + 0.34, color=INK, lw=3, zorder=4)
        ax.errorbar(i + 0.42, m, yerr=[[m - lo], [hi - m]], color=INK, capsize=7, lw=2, zorder=4)
        ax.text(i + 0.50, m, "median %s\n[%s to %s]" % (P.num(kid, nd=2), P.num(kid, "interval_low", 2), P.num(kid, "interval_high", 2)),
                ha="left", va="center", fontsize=13, fontweight="bold", color=INK)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Normal\n(%s machines)" % nn, "Return/Repair\n(%s machines)" % nr])
    ax.set_xlim(-0.6, 2.1)
    ax.set_ylim(0, d.motor_min_per_day.max() * 1.05)
    ax.set_ylabel("Motor runtime (minutes per day)")
    dm = "i3_diff_main"
    fig.text(0.72, 0.70, "Return/Repair minus Normal:\n%s min/day\n[%s to %s]\nratio %s\n\nDirection also holds:\n"
             "ROW-PROD only, common calendar\nmonths (two versions), SV53-AB only\n(interval spans 0, %s vs %s)." %
             (P.num(dm, nd=2), P.num(dm, "interval_low", 2), P.num(dm, "interval_high", 2), P.ratio("i3_ratio_main"),
              P.count("i3_median_ab_normal"), P.count("i3_median_ab_return_repair")),
             fontsize=13, color=INK, va="top")
    P.verify(fig, "04_insight3", R)
    return fig, _save(fig, "04_insight3_motor_minutes_per_day")


# ---------------------------------------------------------------------------
# Slide-sized charts (Step 9): drawn at the physical size placed on the slide, no title or subtitle, labels >= 14 pt
# (the data-quality chart uses 12 pt). Every printed number is read from key_numbers.csv and checked like the others.
# ---------------------------------------------------------------------------
SLIDE_RC = {"font.size": 14, "axes.labelsize": 14, "xtick.labelsize": 14, "ytick.labelsize": 14,
            "axes.spines.top": False, "axes.spines.right": False, "axes.grid": False, "svg.fonttype": "path"}
SLIDE_SIZE = (3.0, 2.25)           # inches as placed on the slide (4:3)
DQ_SLIDE_SIZE = (5.9, 4.6)


def chart_slide_insight1(R, P):
    plt = _setup()
    order = [("Normal\nSV50", "normal_SV50", SV50_BLUE), ("Normal\nSV53", "normal_SV53", h.COLORS[NORMAL]),
             ("RR\nSV53", "return_repair_SV53", h.COLORS[RR])]
    f = lambda i, fld="value": float(P.k.loc[i, fld])
    with plt.rc_context(SLIDE_RC):
        fig = plt.figure(figsize=SLIDE_SIZE)
        ax = fig.add_axes([0.15, 0.25, 0.83, 0.72])
        hi_max = max(f("i1_total_" + s, "interval_high") for _, s, _ in order)
        for i, (lab, s, shade) in enumerate(order):
            oth, fw, tot = f("i1_other_" + s), f("i1_fw_" + s), f("i1_total_" + s)
            lo, hi = f("i1_total_" + s, "interval_low"), f("i1_total_" + s, "interval_high")
            ax.bar(i, oth, width=0.62, color=shade)
            ax.bar(i, fw, bottom=oth, width=0.62, color=_tint(shade, 0.55), edgecolor=shade, hatch="//", linewidth=1)
            ax.errorbar(i, tot, yerr=[[tot - lo], [hi - tot]], color=INK, capsize=5, lw=1.8, zorder=5)
            ax.text(i, hi + hi_max * 0.03, P.num("i1_total_" + s), ha="center", va="bottom", fontsize=14, fontweight="bold", color=INK)
        ax.set_xticks(range(3))
        ax.set_xticklabels([l for l, _, _ in order])
        ax.set_ylim(0, hi_max * 1.22)
        ax.set_yticks([0, 10, 20, 30])
        P.verify(fig, "slide_02_insight1", R)
        return fig, _save(fig, "slide_02_insight1_fault_rate", SLIDE_DIR, dpi=300)


def chart_slide_insight2(R, P):
    plt = _setup()
    from matplotlib.patches import Patch
    cats = ["12/2", "All\ntype 12"]
    with plt.rc_context(SLIDE_RC):
        fig = plt.figure(figsize=SLIDE_SIZE)
        ax = fig.add_axes([0.15, 0.25, 0.83, 0.72])
        ids = {(NORMAL, 0): "i2_t12_v2_main_normal", (RR, 0): "i2_t12_v2_main_return_repair",
               (NORMAL, 1): "i2_t12_main_normal", (RR, 1): "i2_t12_main_return_repair"}
        w, top = 0.36, 0.0
        for j, c in enumerate((NORMAL, RR)):
            for i in range(2):
                kid = ids[(c, i)]
                v, lo, hi = (float(P.k.loc[kid, fld]) for fld in ("value", "interval_low", "interval_high"))
                xp = i + (j - 0.5) * (w + 0.04)
                ax.bar(xp, v, width=w, color=h.COLORS[c])
                ax.errorbar(xp, v, yerr=[[v - lo], [hi - v]], color=INK, capsize=4, lw=1.6, zorder=5)
                ax.text(xp, hi + 0.5, P.num(kid), ha="center", va="bottom", fontsize=14, fontweight="bold", color=INK)
                top = max(top, hi)
        ax.set_xticks(range(2))
        ax.set_xticklabels(cats)
        ax.set_ylim(0, top * 1.3)
        ax.set_yticks([0, 10, 20])
        ax.legend(handles=[Patch(color=h.COLORS[NORMAL], label="Normal"), Patch(color=h.COLORS[RR], label="RR")],
                  loc="upper left", frameon=False, fontsize=14, handlelength=1.0, borderaxespad=0.0)
        P.verify(fig, "slide_03_insight2", R)
        return fig, _save(fig, "slide_03_insight2_airway_blockage", SLIDE_DIR, dpi=300)


def chart_slide_insight3(R, P):
    plt = _setup()
    d = R["i3_data"]
    with plt.rc_context(SLIDE_RC):
        fig = plt.figure(figsize=SLIDE_SIZE)
        ax = fig.add_axes([0.15, 0.25, 0.83, 0.72])
        rng = np.random.RandomState(1)
        for i, c in enumerate((NORMAL, RR)):
            v = d.loc[d.cohort == c, "motor_min_per_day"].values
            ax.scatter(i + rng.uniform(-0.2, 0.2, len(v)), v, s=22, color=h.COLORS[c], alpha=0.6, linewidths=0, zorder=2)
            kid = "i3_median_main_" + c
            m, lo, hi = (float(P.k.loc[kid, fld]) for fld in ("value", "interval_low", "interval_high"))
            ax.hlines(m, i - 0.32, i + 0.32, color=INK, lw=2.5, zorder=4)
            ax.errorbar(i + 0.4, m, yerr=[[m - lo], [hi - m]], color=INK, capsize=4, lw=1.6, zorder=4)
            ax.text(i + 0.47, m, P.num(kid, nd=2), ha="left", va="center", fontsize=14, fontweight="bold", color=INK)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Normal", "RR"])
        ax.set_xlim(-0.55, 2.1)
        ax.set_ylim(0, d.motor_min_per_day.max() * 1.05)
        ax.set_yticks([0, 5, 10, 15, 20])
        P.verify(fig, "slide_04_insight3", R)
        return fig, _save(fig, "slide_04_insight3_motor_minutes", SLIDE_DIR, dpi=300)


def chart_slide_dq(R, P):
    plt = _setup()
    titles = {"clean_sessions": "Clean sessions", "faults": "Faults", "motor": "Motor snapshots", "battery": "Battery snapshots"}
    rc = dict(SLIDE_RC, **{"font.size": 12, "xtick.labelsize": 12, "ytick.labelsize": 12})
    with plt.rc_context(rc):
        fig = plt.figure(figsize=DQ_SLIDE_SIZE)
        gs = fig.add_gridspec(4, 1, left=0.20, right=0.99, top=0.945, bottom=0.01, hspace=0.62)
        for i, tb in enumerate(["clean_sessions", "faults", "motor", "battery"]):
            ax = fig.add_subplot(gs[i])
            ymax = max(float(P.k.loc["dq_raw_%s_%s" % (tb, c), "value"]) for c in (NORMAL, RR))
            for j, c in enumerate([NORMAL, RR]):
                y = 1 - j
                raw, ana = float(P.k.loc["dq_raw_%s_%s" % (tb, c), "value"]), float(P.k.loc["dq_analysis_%s_%s" % (tb, c), "value"])
                ax.barh(y + 0.2, raw, height=0.36, color=_tint(h.COLORS[c], 0.65), edgecolor=h.COLORS[c], linewidth=1)
                ax.barh(y - 0.2, ana, height=0.36, color=h.COLORS[c])
                ax.text(raw + ymax * 0.015, y + 0.2, "%s raw" % P.num("dq_raw_%s_%s" % (tb, c), nd=0, comma=True), va="center", fontsize=12, color=INK)
                ax.text(ana + ymax * 0.015, y - 0.2, "%s analysis (%s%%)" % (P.num("dq_analysis_%s_%s" % (tb, c), nd=0, comma=True),
                        P.num("dq_pct_kept_%s_%s" % (tb, c), nd=0)), va="center", fontsize=12, color=INK, fontweight="bold")
            ax.set_yticks([1, 0])
            ax.set_yticklabels(["Normal", "RR"])
            ax.set_xlim(0, ymax * 1.85)
            ax.set_xticks([])
            ax.spines["bottom"].set_visible(False)
            ax.set_title(titles[tb], fontsize=12, loc="left", color=INK, pad=2)
        P.verify(fig, "slide_01_dq", R)
        return fig, _save(fig, "slide_01_dq_raw_vs_analysis_rows", SLIDE_DIR, dpi=300)


def make_charts(R):
    """Write key_numbers.csv, then build the four charts reading every printed number from that file.

    Fails (AssertionError) if a printed number differs from the file or if the file differs from this run.
    Returns {name: (figure, [paths])}.
    """
    path = write_key_numbers(R)
    P = Printed(path)
    out = {"dq": chart_dq(R, P), "insight1": chart_insight1(R, P), "insight2": chart_insight2(R, P), "insight3": chart_insight3(R, P),
           "slide_dq": chart_slide_dq(R, P), "slide_insight1": chart_slide_insight1(R, P),
           "slide_insight2": chart_slide_insight2(R, P), "slide_insight3": chart_slide_insight3(R, P)}
    R["n_printed_checked"] = len(P.log)
    return out


def main():
    R = compute()
    p = write_key_numbers(R)
    bad = R["step6_check"][~R["step6_check"].matches]
    print("wrote", p, "(%d rows)" % len(R["key"]))
    print("Step 6 consistency: %d checked, %d differ" % (len(R["step6_check"]), len(bad)))
    if len(bad):
        print(bad.to_string())
    charts = make_charts(R)
    print("chart numbers read from key_numbers.csv and checked: %d" % R["n_printed_checked"])
    for name, (fig, paths) in charts.items():
        print(name, [str(x.relative_to(ROOT)) for x in paths])
    return 0


if __name__ == "__main__":
    sys.exit(main())
