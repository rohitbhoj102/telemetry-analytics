"""Step 5: star-schema data model (gold layer) built from the flagged DQ tables.

Run from the repo root, after src/build_clean.py and src/dq.py:  python src/model.py

Input  (read-only): data/clean/dq/{clean_sessions,faults,motor,battery,machine_dq}.parquet
                    Only rows with is_analysis_row = True are used (faults: the primary rule; the status rule
                    is used only for n_status_rows and the status-rule fault rates).
Output (generated): data/model/<table>.parquet and <table>.csv (the CSV files are the Tableau source)
                    reports/model/model_checks.csv, table_row_counts.csv, period_summary.csv

Tables and grain (also in docs/erd.md):
  dim_machine          one machine (anonymized_serial); all 232 serials in machine_dq, incl. machines with no analysis row
  dim_date             one calendar day, from the earliest to the latest fact date
  fact_session         one analysis session (serial + session_id + date_server; duplicates already resolved in Step 4)
  fact_fault           one fault occurrence under the primary rule (serial + session_id + fault_type + fault_value + fault_timestamp)
  fact_motor_period    one interval between two consecutive analysis motor snapshots of a machine (ordered by event_ts)
  fact_battery_period  one interval between two consecutive analysis battery snapshots of a machine (ordered by event_ts)
  machine_summary      one machine; per-machine metrics, each with its sample size

Delta rules: the first snapshot of a machine has no period. A decrease in any cumulative counter between the two
snapshots sets every delta of that period to missing, delta_valid = False and invalid_reason = 'counter_decrease'.
A decrease is never treated as a reset and the row is never dropped. Periods are per interval, not per week, because
snapshot spacing is uneven; days_elapsed is the gap between the two event_ts values.

Dates: faults use fault_timestamp; sessions use date_server (server-side, approximate); motor and battery use
event_ts (hdr_timestamp, or server_timestamp when the device time is in the future; see ts_fallback_flag).

One code path for both cohorts; cohort is a column. Python 3.8 compatible. Field meanings come from field_meanings.py;
anything not stated in the brief or bin JSONs is "unknown". The script exits non-zero if any validation check fails.
"""
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dq  # noqa: E402  (counter_columns, MIN_SESSIONS)
import field_meanings as fm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DQ_DIR = ROOT / "data" / "clean" / "dq"
MODEL_DIR = ROOT / "data" / "model"
REPORT_DIR = ROOT / "reports" / "model"
DQ_REPORT_DIR = ROOT / "reports" / "dq"
MIN_SESSIONS = dq.MIN_SESSIONS  # per-session rates are blank below this many analysis sessions (Step 4 rule)
COHORTS = ("normal", "return_repair")
LINK_METHOD = "serial+session_id, nearest date_server to fault_timestamp [approximate: date_server is server-side time]"

DELTA_ARRAYS_MOTOR = ("ddm692_SpeedBins", "ddm692_PowerBins", "ddm692_ExhaustTempBins")  # fisf bins are not output


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def read(con, name):
    return con.execute("SELECT * FROM read_parquet('%s/%s.parquet')" % (DQ_DIR, name)).df()


def date_key(ts):
    """YYYYMMDD integer from a timestamp series; <NA> where the timestamp is missing."""
    ts = pd.to_datetime(ts)
    k = ts.dt.year * 10000 + ts.dt.month * 100 + ts.dt.day
    return k.astype("Int64")


def to_int(s):
    return pd.Series(s).round().astype("Int64")


def motor_delta_columns():
    return [r["column"] for r in fm.motor_bin_columns() if r["array"] in DELTA_ARRAYS_MOTOR]


def battery_delta_columns():
    return [r["column"] for r in fm.battery_bin_columns()]


def fault_meaning(fault_type, fault_value):
    """Meaning from the brief only (fm.FAULT_TYPES); anything else is reported as unknown."""
    t = fm.FAULT_TYPES.get(int(fault_type))
    if t is None:
        return "unknown (fault_type not in brief)"
    v = t[1].get(int(fault_value))
    if t[1] and v is None:
        return "%s: fault_value not in the brief's list" % t[0]
    return "%s: %s" % (t[0], v if v is not None else "N/A (stall detected)")


# ---------------------------------------------------------------------------
# facts
# ---------------------------------------------------------------------------
def build_fact_session(s):
    d = s[s["is_analysis_row"]].copy()
    d = d.sort_values(["cohort", "anonymized_serial", "date_server", "session_id", "source_row"]).reset_index(drop=True)
    out = pd.DataFrame({
        "session_key": np.arange(1, len(d) + 1),
        "anonymized_serial": d["anonymized_serial"],
        "cohort": d["cohort"],
        "date_key": date_key(d["date_server"]),
        "date_server": d["date_server"],
        "session_id": d["session_id"],
        "clean_duration_clean": d["clean_duration_clean"],
        "battery_charge_start_clean": d["battery_charge_start_clean"],
        "battery_charge_end_clean": d["battery_charge_end_clean"],
    })
    # battery_used = start - end; missing if either is missing or the charge rose (flag_charge_gain)
    ok = d["battery_charge_start_clean"].notna() & d["battery_charge_end_clean"].notna() & ~d["flag_charge_gain"]
    out["battery_used"] = (d["battery_charge_start_clean"] - d["battery_charge_end_clean"]).where(ok)
    out["battery_health_clean"] = d["battery_health_clean"]
    for c in dq.DUST:
        out[c + "_clean"] = d[c + "_clean"]
    out["battery_temp_state"] = d["battery_temp_state"]
    for f in ("flag_duration_outlier", "flag_duration_nonpositive", "flag_dust_sentinel", "flag_charge_out_of_range",
              "flag_health_out_of_range", "flag_charge_gain", "flag_key_conflict", "flag_temp_not_reported",
              "flag_epoch_zero_sync"):
        out[f] = d[f].astype(bool)
    out["dup_class"] = d["dup_class"]
    out["source_file"] = d["source_file"]
    out["source_row"] = d["source_row"]
    for c in ("clean_duration_clean", "battery_charge_start_clean", "battery_charge_end_clean", "battery_used",
              "battery_health_clean") + tuple(c + "_clean" for c in dq.DUST):
        out[c] = to_int(out[c])
    out["session_id"] = to_int(out["session_id"])
    return out, d


def build_fact_fault(f, fact_session):
    prim = f[f["is_analysis_row"]].copy()
    occ = dq.FAULT_OCC
    status_n = (f[f["is_analysis_row_status_rule"]].groupby(occ).size().rename("n_status_rows").reset_index())
    prim = prim.merge(status_n, on=occ, how="left")
    prim = prim.sort_values(["cohort", "anonymized_serial", "fault_timestamp", "fault_type", "fault_value", "session_id",
                             "source_row"]).reset_index(drop=True)
    prim["fault_key"] = np.arange(1, len(prim) + 1)

    # optional link to a session: same serial + session_id, nearest date_server (approximate); blank if no match
    cand = prim[["fault_key", "anonymized_serial", "session_id", "fault_timestamp"]].merge(
        fact_session[["session_key", "anonymized_serial", "session_id", "date_server"]],
        on=["anonymized_serial", "session_id"], how="inner")
    cand["gap"] = (cand["date_server"] - cand["fault_timestamp"]).abs()
    cand = cand.sort_values(["fault_key", "gap", "session_key"]).drop_duplicates("fault_key")
    prim = prim.merge(cand[["fault_key", "session_key", "gap"]], on="fault_key", how="left")

    out = pd.DataFrame({
        "fault_key": prim["fault_key"],
        "anonymized_serial": prim["anonymized_serial"],
        "cohort": prim["cohort"],
        "date_key": date_key(prim["fault_timestamp"]),
        "fault_timestamp": prim["fault_timestamp"],
        "session_id": to_int(prim["session_id"]),
        "fault_type": to_int(prim["fault_type"]),
        "fault_value": to_int(prim["fault_value"]),
        "fault_meaning": [fault_meaning(t, v) for t, v in zip(prim["fault_type"], prim["fault_value"])],
        "n_status_rows": to_int(prim["n_status_rows"]),
        "session_key": prim["session_key"].astype("Int64"),
        "link_method": np.where(prim["session_key"].notna(), LINK_METHOD, "no session with the same serial + session_id"),
        "link_gap_hours": (prim["gap"].dt.total_seconds() / 3600.0).round(2),
        "flag_occ_multi_status": prim["flag_occ_multi_status"].astype(bool),
        "flag_epoch_zero_sync": prim["flag_epoch_zero_sync"].astype(bool),
        "source_file": prim["source_file"],
        "source_row": prim["source_row"],
    })
    return out


def build_periods(df, delta_cols, detect_cols):
    """One row per interval between consecutive analysis snapshots of a machine. See the module docstring."""
    d = df[df["is_analysis_row"]].sort_values(["anonymized_serial", "event_ts", "source_row"]).reset_index(drop=True)
    g = d.groupby("anonymized_serial", sort=False)
    has_prev = g.cumcount() > 0
    det = d[detect_cols].astype(float)
    det_diff = det.groupby(d["anonymized_serial"], sort=False).diff()
    n_dec = (det_diff < 0).sum(axis=1)
    delta = d[delta_cols].astype(float).groupby(d["anonymized_serial"], sort=False).diff()
    valid = n_dec == 0
    delta = delta.where(valid, np.nan)

    start_ts = g["event_ts"].shift(1)
    out = pd.DataFrame({
        "anonymized_serial": d["anonymized_serial"],
        "cohort": d["cohort"],
        "period_start_ts": start_ts,
        "period_end_ts": d["event_ts"],
        "date_key": date_key(d["event_ts"]),
        "days_elapsed": ((d["event_ts"] - start_ts).dt.total_seconds() / 86400.0).round(6),
        "ts_fallback_any": d["ts_fallback_flag"].astype(bool) | g["ts_fallback_flag"].shift(1).fillna(False).astype(bool),
    })
    if "pack_type" in d.columns:
        out["pack_type"] = d["pack_type"]
    out["delta_valid"] = valid
    out["invalid_reason"] = np.where(valid, None, "counter_decrease")
    out["n_decreasing_fields"] = n_dec.astype(int)
    out["source_file"] = d["source_file"]
    out["start_source_row"] = g["source_row"].shift(1)
    out["end_source_row"] = d["source_row"]
    for c in delta_cols:
        out["delta_" + c] = to_int(delta[c])
    out = out[has_prev].reset_index(drop=True)
    out["start_source_row"] = to_int(out["start_source_row"])
    out["end_source_row"] = to_int(out["end_source_row"])
    out.insert(0, "period_key", np.arange(1, len(out) + 1))
    return out, d


def build_fact_motor_period(m):
    cols = motor_delta_columns()
    out, snaps = build_periods(m, ["runtime_s"] + cols, dq.counter_columns("motor"))
    ok = out["delta_valid"] & (out["days_elapsed"] > 0)
    out.insert(out.columns.get_loc("delta_runtime_s") + 1, "runtime_s_per_day",
               (out["delta_runtime_s"].astype(float) / out["days_elapsed"]).where(ok).round(3))
    return out, snaps


def build_fact_battery_period(b):
    return build_periods(b, battery_delta_columns(), dq.counter_columns("battery"))


# ---------------------------------------------------------------------------
# dimensions
# ---------------------------------------------------------------------------
def single_value(frames_cols, label):
    """serial -> the one non-null value over several (frame, column) sources; null if none or more than one."""
    parts = [f[["anonymized_serial", c]].rename(columns={c: label}).dropna() for f, c in frames_cols]
    allv = pd.concat(parts, ignore_index=True).drop_duplicates()
    n = allv.groupby("anonymized_serial")[label].nunique()
    one = allv[allv["anonymized_serial"].isin(n[n == 1].index)].set_index("anonymized_serial")[label]
    return one, int((n > 1).sum())


def build_dim_machine(md, s, f, m, b):
    sa, fa, ma, ba = (x[x["is_analysis_row"]] for x in (s, f, m, b))
    model, n_multi_model = single_value([(sa, "model"), (fa, "model")], "model")
    region, n_multi_region = single_value([(sa, "region"), (fa, "region"), (ma, "region")], "region")
    country, n_multi_country = single_value([(ma, "country")], "country")
    pack, n_multi_pack = single_value([(ba, "pack_type")], "pack_type")
    d = md[["anonymized_serial", "cohort"]].copy()
    for ser in (model, region, country, pack):
        d = d.merge(ser.reset_index(), on="anonymized_serial", how="left")
    for t, col in (("clean_sessions", "session"), ("faults", "fault"), ("motor", "motor"), ("battery", "battery")):
        d["has_%s_rows" % col] = md["in_%s" % t].values
        d["has_%s_analysis_rows" % col] = md["in_%s_analysis" % t].values
    d["has_any_analysis_row"] = d[["has_session_analysis_rows", "has_fault_analysis_rows", "has_motor_analysis_rows",
                                   "has_battery_analysis_rows"]].any(axis=1)
    d["has_all_four_tables"] = d[["has_session_analysis_rows", "has_fault_analysis_rows", "has_motor_analysis_rows",
                                  "has_battery_analysis_rows"]].all(axis=1)
    for c in ("eligible_rate_machine", "flag_outlier_sessions_per_week", "flag_outlier_faults_per_100"):
        d[c] = md[c].values
    d = d.sort_values("anonymized_serial").reset_index(drop=True)
    return d, {"model": n_multi_model, "region": n_multi_region, "country": n_multi_country, "pack_type": n_multi_pack}


def build_dim_date(*keys):
    ks = pd.concat([pd.Series(k).dropna().astype(int) for k in keys])
    lo = pd.to_datetime(str(ks.min()), format="%Y%m%d")
    hi = pd.to_datetime(str(ks.max()), format="%Y%m%d")
    days = pd.date_range(lo, hi, freq="D")
    iso = days.isocalendar()
    return pd.DataFrame({
        "date_key": (days.year * 10000 + days.month * 100 + days.day).astype(int),
        "date": [x.date() for x in days],
        "year": days.year,
        "iso_year": iso["year"].astype(int).values,
        "iso_week": iso["week"].astype(int).values,
        "week_start": [(x - pd.Timedelta(days=x.weekday())).date() for x in days],
        "month": days.strftime("%Y-%m"),
        "month_start": [x.replace(day=1).date() for x in days],
    })


# ---------------------------------------------------------------------------
# machine summary
# ---------------------------------------------------------------------------
def combo_names(fault_type, fault_value):
    return "t%d_v%d" % (fault_type, fault_value)


def build_machine_summary(dim, md, fs, ff, f_status, fmot, msnap, fbat, bsnap):
    ms = dim[["anonymized_serial", "cohort", "model", "region", "country", "pack_type"]].copy()
    ix = ms.set_index("anonymized_serial")
    mdi = md.set_index("anonymized_serial")

    # sessions: n, span, rate per week, medians (each with its sample size)
    g = fs.groupby("anonymized_serial")
    ix["n_sessions"] = g.size()
    ix["first_session_ts"] = g["date_server"].min()
    ix["last_session_ts"] = g["date_server"].max()
    ix["observation_span_days"] = ((ix["last_session_ts"] - ix["first_session_ts"]).dt.total_seconds() / 86400.0).round(2)
    ix["sessions_per_week"] = mdi["sessions_per_week"].round(4)  # Step 4 definition: sessions / max(span in weeks, 1)
    ix["n_sessions"] = ix["n_sessions"].fillna(0).astype(int)
    ix["rate_eligible"] = ix["n_sessions"] >= MIN_SESSIONS
    ix["n_duration_valid"] = fs["clean_duration_clean"].notna().groupby(fs["anonymized_serial"]).sum()
    ix["median_clean_duration"] = fs.groupby("anonymized_serial")["clean_duration_clean"].apply(lambda x: x.astype(float).median())
    ix["n_battery_used_valid"] = fs["battery_used"].notna().groupby(fs["anonymized_serial"]).sum()
    ix["median_battery_used"] = fs.groupby("anonymized_serial")["battery_used"].apply(lambda x: x.astype(float).median())
    for c in ("n_duration_valid", "n_battery_used_valid"):
        ix[c] = ix[c].fillna(0).astype(int)
    ix.loc[ix["n_duration_valid"] == 0, "median_clean_duration"] = np.nan
    ix.loc[ix["n_battery_used_valid"] == 0, "median_battery_used"] = np.nan

    # faults: absence from the faults table is treated as no faults [assumed] (project decision), so a machine with
    # >= MIN_SESSIONS analysis sessions and no fault rows gets rate 0. The blanked version is kept as a sensitivity column.
    in_faults = mdi["in_faults"].reindex(ix.index)
    ok = ix["rate_eligible"]
    ix["in_faults_table"] = in_faults
    known = in_faults | (ix["n_sessions"] > 0)  # counts stay blank only with neither a fault row nor a session
    sess = ix["n_sessions"].replace(0, np.nan)
    prim_n = ff.groupby("anonymized_serial").size().reindex(ix.index).fillna(0)
    stat_n = f_status.groupby("anonymized_serial").size().reindex(ix.index).fillna(0)
    ix["n_faults_primary"] = prim_n.where(known).astype("Int64")
    ix["n_faults_status_rule"] = stat_n.where(known).astype("Int64")
    for rule, n in (("primary", prim_n), ("status_rule", stat_n)):
        rate = 100.0 * n / sess
        ix["faults_per_100_sessions_" + rule] = rate.where(ok).round(4)
        ix["faults_per_100_fault_machines_only_" + rule] = rate.where(ok & in_faults).round(4)  # sensitivity: blank if never in faults table
    combos = sorted(set(zip(ff["fault_type"].astype(int), ff["fault_value"].astype(int))) |
                    set(zip(f_status["fault_type"].astype(int), f_status["fault_value"].astype(int))))
    for t, v in combos:
        nm = combo_names(t, v)
        for rule, src in (("primary", ff), ("status_rule", f_status)):
            sel = src[(src["fault_type"] == t) & (src["fault_value"] == v)]
            n = sel.groupby("anonymized_serial").size().reindex(ix.index).fillna(0)
            ix["n_faults_%s_%s" % (nm, rule)] = n.where(known).astype("Int64")
            ix["faults_per_100_sessions_%s_%s" % (nm, rule)] = (100.0 * n / sess).where(ok).round(4)

    # motor: runtime per day over valid periods; shares from the latest analysis snapshot
    ix["n_motor_snapshots"] = msnap.groupby("anonymized_serial").size().reindex(ix.index).fillna(0).astype(int)
    vp = fmot[fmot["delta_valid"] & (fmot["days_elapsed"] > 0)]
    ix["n_motor_periods_total"] = fmot.groupby("anonymized_serial").size().reindex(ix.index).fillna(0).astype(int)
    ix["n_motor_periods_valid"] = vp.groupby("anonymized_serial").size().reindex(ix.index).fillna(0).astype(int)
    ix["motor_valid_days"] = vp.groupby("anonymized_serial")["days_elapsed"].sum().reindex(ix.index).round(3)
    rt = vp.groupby("anonymized_serial")["delta_runtime_s"].apply(lambda x: x.astype(float).sum()).reindex(ix.index)
    ix["motor_valid_runtime_s"] = rt
    ix["motor_runtime_s_per_day"] = (rt / ix["motor_valid_days"].replace(0, np.nan)).round(3)
    ix.loc[ix["n_motor_periods_valid"] == 0, ["motor_valid_days", "motor_valid_runtime_s", "motor_runtime_s_per_day"]] = np.nan

    latest = msnap.sort_values(["anonymized_serial", "event_ts", "source_row"]).groupby("anonymized_serial").tail(1).set_index("anonymized_serial")
    power_cols = [r["column"] for r in fm.motor_bin_columns() if r["array"] == fm.MOTOR_RUNTIME_ARRAY]
    ix["motor_latest_snapshot_ts"] = latest["event_ts"].reindex(ix.index)
    ix["motor_latest_runtime_s"] = latest["runtime_s"].reindex(ix.index).astype(float)
    den = ix["motor_latest_runtime_s"].where(ix["motor_latest_runtime_s"] > 0)
    for c in power_cols:
        ix["share_runtime_" + c.replace("_seconds", "")] = (latest[c].reindex(ix.index).astype(float) / den).round(6)
    ix["share_runtime_300_400w_lifetime"] = ix["share_runtime_power_300_400"]
    d300 = vp.groupby("anonymized_serial")["delta_power_300_400_seconds"].apply(lambda x: x.astype(float).sum()).reindex(ix.index)
    ix["share_runtime_300_400w_valid_periods"] = (d300 / rt.where(rt > 0)).round(6)

    # battery: sample sizes only (no battery insight selected yet)
    ix["n_battery_snapshots"] = bsnap.groupby("anonymized_serial").size().reindex(ix.index).fillna(0).astype(int)
    ix["n_battery_periods_total"] = fbat.groupby("anonymized_serial").size().reindex(ix.index).fillna(0).astype(int)
    ix["n_battery_periods_valid"] = fbat[fbat["delta_valid"]].groupby("anonymized_serial").size().reindex(ix.index).fillna(0).astype(int)

    # presence and outlier flags
    for c in ("has_session_rows", "has_session_analysis_rows", "has_fault_rows", "has_fault_analysis_rows", "has_motor_rows",
              "has_motor_analysis_rows", "has_battery_rows", "has_battery_analysis_rows", "has_all_four_tables",
              "flag_outlier_sessions_per_week", "flag_outlier_faults_per_100"):
        ix[c] = dim.set_index("anonymized_serial")[c]
    return ix.reset_index(), combos


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
class Checks(object):
    def __init__(self):
        self.rows = []

    def add(self, check, table, expected, actual, passed=None, cohort="all", note=""):
        if passed is None:
            passed = bool(expected == actual)
        self.rows.append({"check": check, "table": table, "cohort": cohort, "expected": expected, "actual": actual,
                          "status": "info" if passed == "info" else ("pass" if passed else "FAIL"), "note": note})

    def frame(self):
        return pd.DataFrame(self.rows, columns=["check", "table", "cohort", "expected", "actual", "status", "note"])


def sum_check(periods, snaps, cols, label, ck):
    """For machines with no invalid period: sum of deltas == last - first snapshot value (columns without nulls)."""
    bad_machines = set(periods.loc[~periods["delta_valid"], "anonymized_serial"])
    n_checked = n_failed = 0
    snaps = snaps.sort_values(["anonymized_serial", "event_ts", "source_row"])
    first = snaps.groupby("anonymized_serial").head(1).set_index("anonymized_serial")
    last = snaps.groupby("anonymized_serial").tail(1).set_index("anonymized_serial")
    nulls = snaps.groupby("anonymized_serial")[cols].apply(lambda x: x.isna().any())
    ok_ser = [x for x in periods["anonymized_serial"].unique() if x not in bad_machines]
    for c in cols:
        dc = "delta_" + c
        sums = periods[periods["anonymized_serial"].isin(ok_ser)].groupby("anonymized_serial")[dc].apply(lambda x: x.astype(float).sum())
        for ser in ok_ser:
            if nulls.loc[ser, c]:
                continue
            n_checked += 1
            if abs(sums.loc[ser] - (float(last.loc[ser, c]) - float(first.loc[ser, c]))) > 0.5:
                n_failed += 1
    ck.add("sum of deltas = last - first snapshot, machines with no invalid period, %s" % label, label.split(" ")[0], 0, n_failed,
           note="%d machine-column pairs checked over %d machines" % (n_checked, len(ok_ser)))


def run_checks(inp, fact, dim, dimdate, summ, md, combos):
    ck = Checks()
    s, f, m, b = inp["s"], inp["f"], inp["m"], inp["b"]
    fs, ff, fmot, fbat = fact["fact_session"], fact["fact_fault"], fact["fact_motor_period"], fact["fact_battery_period"]
    for c in COHORTS:
        ck.add("fact_session rows = analysis sessions", "fact_session", int((s["is_analysis_row"] & (s["cohort"] == c)).sum()),
               int((fs["cohort"] == c).sum()), cohort=c)
        ck.add("fact_fault rows = primary-rule analysis faults", "fact_fault", int((f["is_analysis_row"] & (f["cohort"] == c)).sum()),
               int((ff["cohort"] == c).sum()), cohort=c)
        for name, df, fact_t in (("motor", m, fmot), ("battery", b, fbat)):
            a = df[df["is_analysis_row"] & (df["cohort"] == c)]
            ck.add("fact_%s_period rows = snapshots minus one per machine" % name, "fact_%s_period" % name,
                   int(len(a) - a["anonymized_serial"].nunique()), int((fact_t["cohort"] == c).sum()), cohort=c)
    # keys
    ck.add("session_key unique", "fact_session", len(fs), int(fs["session_key"].nunique()))
    ck.add("fault_key unique", "fact_fault", len(ff), int(ff["fault_key"].nunique()))
    dm = set(dim["anonymized_serial"])
    dkeys = set(dimdate["date_key"])
    ck.add("dim_machine serials unique", "dim_machine", len(dim), len(dm))
    ck.add("dim_machine serials = machine_dq serials", "dim_machine", len(md), len(dm))
    for name, t in (("fact_session", fs), ("fact_fault", ff), ("fact_motor_period", fmot), ("fact_battery_period", fbat)):
        ck.add("every serial exists in dim_machine", name, 0, int((~t["anonymized_serial"].isin(dm)).sum()))
        ck.add("every date_key exists in dim_date (and is not null)", name, 0, int((~t["date_key"].isin(dkeys)).sum()))
        coh = t[["anonymized_serial", "cohort"]].merge(dim[["anonymized_serial", "cohort"]], on="anonymized_serial", suffixes=("", "_dim"))
        ck.add("cohort equals dim_machine cohort", name, 0, int((coh["cohort"] != coh["cohort_dim"]).sum()))
    ck.add("every non-null fault session_key exists in fact_session", "fact_fault", 0,
           int((~ff["session_key"].dropna().isin(set(fs["session_key"]))).sum()))
    lk = ff.dropna(subset=["session_key"]).merge(fs[["session_key", "anonymized_serial", "session_id"]], on="session_key", suffixes=("", "_s"))
    ck.add("linked session has the same serial and session_id", "fact_fault", 0,
           int(((lk["anonymized_serial"] != lk["anonymized_serial_s"]) | (lk["session_id"] != lk["session_id_s"])).sum()))
    ck.add("every fault has n_status_rows >= 1", "fact_fault", 0, int((ff["n_status_rows"].isna() | (ff["n_status_rows"] < 1)).sum()))
    ck.add("dim_date continuous (rows = days between first and last date)", "dim_date",
           int((pd.to_datetime(dimdate["date"].iloc[-1]) - pd.to_datetime(dimdate["date"].iloc[0])).days + 1), len(dimdate))
    # delta rules
    for name, t in (("fact_motor_period", fmot), ("fact_battery_period", fbat)):
        dc = [c for c in t.columns if c.startswith("delta_") and c != "delta_valid"]
        neg = int(((t.loc[t["delta_valid"], dc].astype(float)) < 0).sum().sum())
        ck.add("no negative delta where delta_valid = True", name, 0, neg)
        inv = t[~t["delta_valid"]]
        ck.add("invalid periods have all deltas missing and a reason", name, 0,
               int(inv[dc].notna().sum().sum() + inv["invalid_reason"].isna().sum()))
        ck.add("days_elapsed >= 0 and not null", name, 0, int((t["days_elapsed"].isna() | (t["days_elapsed"] < 0)).sum()))
    sum_check(fmot, inp["msnap"], ["runtime_s"] + motor_delta_columns(), "motor periods (runtime_s + all delta columns)", ck)
    sum_check(fbat, inp["bsnap"], battery_delta_columns(), "battery periods (all bin columns)", ck)
    # agreement with the Step 4 counter-decrease counts (reports/dq/counter_decreases.csv)
    cd = pd.read_csv(DQ_REPORT_DIR / "counter_decreases.csv")
    cd = cd[(cd["stage"] == "after_reupload_removal") & (cd["pack_type"] == "all")]
    for name, t in (("motor", fmot), ("battery", fbat)):
        for c in COHORTS:
            exp = cd[(cd["table"] == name) & (cd["cohort"] == c)]
            e_pairs = int(exp["pairs"].sum()) if len(exp) else 0
            e_dec = int(exp["pairs_with_decrease"].sum()) if len(exp) else 0
            x = t[t["cohort"] == c]
            ck.add("periods = Step 4 pairs (reports/dq/counter_decreases.csv)", "fact_%s_period" % name, e_pairs, len(x), cohort=c)
            ck.add("invalid periods = Step 4 pairs with a counter decrease", "fact_%s_period" % name, e_dec, int((~x["delta_valid"]).sum()), cohort=c)
    # machine summary
    ck.add("machine_summary rows = dim_machine rows", "machine_summary", len(dim), len(summ))
    ck.add("machine_summary n_sessions = machine_dq n_analysis_sessions", "machine_summary", 0,
           int((summ.set_index("anonymized_serial")["n_sessions"] != md.set_index("anonymized_serial")["n_analysis_sessions"].reindex(summ["anonymized_serial"]).values).sum()))
    share_cols = [c for c in summ.columns if c.startswith("share_runtime_power_")]
    tot = summ[share_cols].sum(axis=1, min_count=len(share_cols))
    have = tot.notna()
    ck.add("power-band shares sum to 1 (machines with a share)", "machine_summary", 0, int((abs(tot[have] - 1) > 1e-3).sum()),
           note="%d machines checked" % int(have.sum()))
    ck.add("battery_used = start - end in 0..100 and not negative", "fact_session", 0,
           int((fs["battery_used"].dropna().astype(float) < 0).sum() + (fs["battery_used"].dropna().astype(float) > 100).sum()))
    ck.add("battery_used equals Step 4 battery_drain_clean", "fact_session", 0,
           int((fs.set_index("session_key")["battery_used"].astype("float").fillna(-1).values !=
                inp["sessions_sorted"]["battery_drain_clean"].astype("float").fillna(-1).values).sum()))
    # information rows
    n_link = int(ff["session_key"].notna().sum())
    for c in COHORTS + ("all",):
        x = ff if c == "all" else ff[ff["cohort"] == c]
        n = int(x["session_key"].notna().sum())
        ck.add("fault-to-session link rate", "fact_fault", "info", "%d of %d (%.2f%%)" % (n, len(x), 100.0 * n / max(len(x), 1)),
               passed="info", cohort=c, note="method: " + LINK_METHOD)
    return ck


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def write(con, df, name):
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    con.register("_t", df)
    for ext, opts in (("parquet", "FORMAT PARQUET"), ("csv", "FORMAT CSV, HEADER")):
        con.execute("COPY _t TO '%s/%s.%s' (%s)" % (MODEL_DIR, name, ext, opts))
    con.unregister("_t")


def main():
    con = duckdb.connect()
    s, f, m, b, md = (read(con, n) for n in ("clean_sessions", "faults", "motor", "battery", "machine_dq"))

    fact_session, sessions_sorted = build_fact_session(s)
    fact_fault = build_fact_fault(f, fact_session)
    fact_motor, msnap = build_fact_motor_period(m)
    fact_battery, bsnap = build_fact_battery_period(b)
    dim, n_multi = build_dim_machine(md, s, f, m, b)
    dimdate = build_dim_date(fact_session["date_key"], fact_fault["date_key"], fact_motor["date_key"], fact_battery["date_key"])
    ff_status = f[f["is_analysis_row_status_rule"]]
    summ, combos = build_machine_summary(dim, md, fact_session, fact_fault, ff_status, fact_motor, msnap, fact_battery, bsnap)

    fact = {"fact_session": fact_session, "fact_fault": fact_fault, "fact_motor_period": fact_motor,
            "fact_battery_period": fact_battery}
    inp = {"s": s, "f": f, "m": m, "b": b, "msnap": msnap, "bsnap": bsnap, "sessions_sorted": sessions_sorted}
    ck = run_checks(inp, fact, dim, dimdate, summ, md, combos)
    for k, v in n_multi.items():
        ck.add("dim_machine: serials with more than one %s value (set to null)" % k, "dim_machine", 0, v)

    tables = [("dim_machine", dim), ("dim_date", dimdate)] + list(fact.items()) + [("machine_summary", summ)]
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    checks = ck.frame()
    checks.to_csv(REPORT_DIR / "model_checks.csv", index=False)

    counts = []
    for name, t in tables:
        if "cohort" in t.columns:
            for c in COHORTS:
                counts.append({"table": name, "cohort": c, "rows": int((t["cohort"] == c).sum())})
        counts.append({"table": name, "cohort": "all", "rows": len(t)})
    pd.DataFrame(counts).to_csv(REPORT_DIR / "table_row_counts.csv", index=False)

    per = []
    for name, t in (("fact_motor_period", fact_motor), ("fact_battery_period", fact_battery)):
        for c in COHORTS:
            x = t[t["cohort"] == c]
            per.append({"table": name, "cohort": c, "periods": len(x), "valid": int(x["delta_valid"].sum()),
                        "invalid_counter_decrease": int((x["invalid_reason"] == "counter_decrease").sum()),
                        "zero_days_elapsed": int((x["days_elapsed"] == 0).sum()), "ts_fallback_any": int(x["ts_fallback_any"].sum()),
                        "machines": int(x["anonymized_serial"].nunique()),
                        "median_days_elapsed": float(x["days_elapsed"].median()) if len(x) else np.nan})
    pd.DataFrame(per).to_csv(REPORT_DIR / "period_summary.csv", index=False)

    failed = checks[checks["status"] == "FAIL"]
    if len(failed):
        pd.set_option("display.width", 250, "display.max_colwidth", 90)
        print(failed.to_string())
        raise SystemExit("model validation failed: %d check(s); no model tables were written" % len(failed))
    for name, t in tables:
        write(con, t, name)
    print("model checks: %d pass, %d info, 0 fail -> %s" % ((checks["status"] == "pass").sum(), (checks["status"] == "info").sum(),
                                                            REPORT_DIR / "model_checks.csv"))
    print(pd.DataFrame(counts).pivot(index="table", columns="cohort", values="rows").to_string())


if __name__ == "__main__":
    main()
