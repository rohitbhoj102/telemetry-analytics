"""Step 4: data-quality checks and flagged analysis tables.

Run from the repo root (after src/build_clean.py):  python src/dq.py

Input  (read-only): data/clean/{clean_sessions,faults,motor,battery}.parquet
Output (generated):
  data/clean/dq/{clean_sessions,faults,motor,battery}.parquet  every original column + flag columns
                                                              + *_clean analysis columns + is_analysis_row
  data/clean/dq/machine_dq.parquet                            machine-level rates and outlier flags
  reports/dq/dq_summary.csv        check, table, cohort, rows_affected, pct, action_taken
  reports/dq/*.csv                 detail tables (missingness, counter decreases, thresholds, ...)

Principles: flag, never delete; raw values are never overwritten (cleaned values go in new *_clean
columns); where a rule picks one row of a group the order is fixed: earliest server-side time, then
lowest source_row. One code path for both cohorts. Rules that depend on an unstated field meaning are
labelled [inferred] or [assumed] in `action_taken`.

Basis of each count is part of the check name: "[analysis rows]" or "[all rows]".
"""
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import field_meanings as fm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CLEAN = ROOT / "data" / "clean"
DQ_DIR = CLEAN / "dq"
REPORT_DIR = ROOT / "reports" / "dq"
SUMMARY_COLS = ["check", "table", "cohort", "rows_affected", "pct", "action_taken"]
COHORTS = ("normal", "return_repair")
IQR_K = 3.0
MIN_SESSIONS = 10  # machines with fewer analysis sessions are left out of per-machine rate statistics

SESSION_RAW = ["anonymized_serial", "date_server", "region", "session_id", "clean_duration", "battery_charge_start",
               "battery_charge_end", "battery_health", "battery_temperature_hot", "battery_temperature_cold",
               "battery_temperature_ok", "battery_soc_state", "model", "running_firmware_version",
               "ultra_fine_dust_particle_mass", "fine_dust_particle_mass", "coarse_dust_particle_mass",
               "large_dust_particle_mass", "log3_time_sync_old", "log3_time_sync_new"]
SESSION_KEY = ["cohort", "anonymized_serial", "session_id", "date_server"]
SESSION_MEASURED = [c for c in SESSION_RAW if c not in
                    ("anonymized_serial", "date_server", "session_id", "log3_time_sync_old", "log3_time_sync_new")]
DUST = ["ultra_fine_dust_particle_mass", "fine_dust_particle_mass", "coarse_dust_particle_mass",
        "large_dust_particle_mass"]
FAULT_RAW = ["anonymized_serial", "date_server", "region", "session_id", "fault_type", "fault_value",
             "fault_timestamp", "model", "product_alarm_source", "hex_error_code", "product_alarm_fault_severity",
             "fault_status", "log2_time_sync_old", "log2_time_sync_new"]
FAULT_OCC = ["cohort", "anonymized_serial", "session_id", "fault_type", "fault_value", "fault_timestamp"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _list(cols):
    return ", ".join(cols)


def summarise(check, table, df, mask, action, basis=None):
    """Summary rows (normal, return_repair, all) for `mask` among rows of `basis` (default: all rows of df)."""
    mask = pd.Series(mask, index=df.index).fillna(False).astype(bool)
    basis = pd.Series(True, index=df.index) if basis is None else pd.Series(basis, index=df.index).fillna(False).astype(bool)
    rows = []
    for c in COHORTS + ("all",):
        sel = basis if c == "all" else basis & (df["cohort"] == c)
        denom = int(sel.sum())
        n = int((sel & mask).sum())
        rows.append({"check": check, "table": table, "cohort": c, "rows_affected": n,
                     "pct": round(100.0 * n / denom, 2) if denom else np.nan, "action_taken": action})
    return pd.DataFrame(rows, columns=SUMMARY_COLS)


def info_rows(check, table, per_cohort, action, denominators=None):
    """Summary rows for a precomputed count per cohort ({cohort: n}); 'all' is the sum."""
    rows = []
    vals = dict(per_cohort)
    vals["all"] = sum(vals.get(c, 0) for c in COHORTS)
    dens = dict(denominators or {})
    if denominators is not None:
        dens["all"] = sum(dens.get(c, 0) for c in COHORTS)
    for c in COHORTS + ("all",):
        n = int(vals.get(c, 0))
        d = dens.get(c)
        rows.append({"check": check, "table": table, "cohort": c, "rows_affected": n,
                     "pct": round(100.0 * n / d, 2) if d else np.nan, "action_taken": action})
    return pd.DataFrame(rows, columns=SUMMARY_COLS)


def _read(con, table):
    return con.execute("SELECT * FROM %s" % table).df()


def _iqr_fences(values, k=IQR_K):
    v = pd.Series(values).dropna().astype(float)
    q1, q3 = v.quantile(0.25), v.quantile(0.75)
    iqr = q3 - q1
    return {"q1": q1, "q3": q3, "iqr": iqr, "lo": q1 - k * iqr, "hi": q3 + k * iqr, "n": int(len(v))}


# ---------------------------------------------------------------------------
# data window (server-side times of all tables, both cohorts)
# ---------------------------------------------------------------------------
def data_window(con):
    """[earliest, latest] of the server-side times over all four tables and both cohorts (all rows)."""
    q = """SELECT min(t), max(t) FROM (
             SELECT date_server t FROM read_parquet('%(c)s/clean_sessions.parquet')
             UNION ALL SELECT date_server FROM read_parquet('%(c)s/faults.parquet')
             UNION ALL SELECT server_timestamp FROM read_parquet('%(c)s/motor.parquet')
             UNION ALL SELECT server_timestamp FROM read_parquet('%(c)s/battery.parquet'))""" % {"c": CLEAN}
    lo, hi = con.execute(q).fetchone()
    return pd.Timestamp(lo), pd.Timestamp(hi)


# ---------------------------------------------------------------------------
# stage 1: build flagged tables in an in-memory DuckDB (SQL keeps original column types)
# ---------------------------------------------------------------------------
def build_sessions_stage_a(con, win):
    lo, hi = win
    key, meas, raw = _list(SESSION_KEY), _list(SESSION_MEASURED), _list(["cohort"] + SESSION_RAW)
    dust_clean = ",\n  ".join("CASE WHEN %s = 65535 THEN NULL ELSE %s END AS %s_clean" % (c, c, c) for c in DUST)
    dust_flag = " OR ".join("%s = 65535" % c for c in DUST)
    con.execute("""
    CREATE OR REPLACE TABLE sessions_a AS
    WITH x AS (
      SELECT *,
        count(*) OVER (PARTITION BY %(raw)s) AS _exact_n,
        count(*) OVER (PARTITION BY %(key)s) AS _key_n,
        count(*) OVER (PARTITION BY %(key)s, %(meas)s) AS _grp_n,
        row_number() OVER (PARTITION BY %(key)s, %(meas)s ORDER BY date_server, source_row) AS _grp_rn
      FROM read_parquet('%(c)s/clean_sessions.parquet')
    ), y AS (
      SELECT *,
        CASE WHEN _grp_n = 1 THEN 'distinct' WHEN _exact_n > 1 THEN 'exact_copy' ELSE 'join_fanout' END AS dup_class,
        _grp_rn = 1 AS dup_keep,
        _grp_n AS dup_group_size,
        _key_n > _grp_n AS flag_key_conflict,
        coalesce(%(dust_flag)s, false) AS flag_dust_sentinel,
        coalesce((battery_charge_start NOT BETWEEN 0 AND 100) OR (battery_charge_end NOT BETWEEN 0 AND 100), false) AS flag_charge_out_of_range,
        coalesce(battery_health NOT BETWEEN 0 AND 100, false) AS flag_health_out_of_range,
        coalesce(clean_duration <= 0, false) AS flag_duration_nonpositive,
        (coalesce(battery_temperature_hot::INT, 0) + coalesce(battery_temperature_cold::INT, 0)
          + coalesce(battery_temperature_ok::INT, 0)) AS temp_flags_true,
        (battery_temperature_hot IS NULL AND battery_temperature_cold IS NULL AND battery_temperature_ok IS NULL)
          AS flag_temp_all_null,
        coalesce(log3_time_sync_old = 0, false) OR coalesce(log3_time_sync_new = 0, false) AS flag_epoch_zero_sync,
        coalesce((log3_time_sync_old > 0 AND (log3_time_sync_old_ts < TIMESTAMP '%(lo)s' OR log3_time_sync_old_ts > TIMESTAMP '%(hi)s'))
          OR (log3_time_sync_new > 0 AND (log3_time_sync_new_ts < TIMESTAMP '%(lo)s' OR log3_time_sync_new_ts > TIMESTAMP '%(hi)s')), false)
          AS flag_timesync_outside_window,
        coalesce(date_server < TIMESTAMP '%(lo)s' OR date_server > TIMESTAMP '%(hi)s', false) AS flag_date_outside_window,
        %(dust_clean)s,
        CASE WHEN battery_charge_start BETWEEN 0 AND 100 THEN battery_charge_start END AS battery_charge_start_clean,
        CASE WHEN battery_charge_end BETWEEN 0 AND 100 THEN battery_charge_end END AS battery_charge_end_clean,
        CASE WHEN battery_health BETWEEN 0 AND 100 THEN battery_health END AS battery_health_clean,
        CASE WHEN clean_duration > 0 THEN clean_duration END AS clean_duration_clean
      FROM x
    )
    SELECT * EXCLUDE (_exact_n, _key_n, _grp_n, _grp_rn),
      temp_flags_true = 0 AS flag_temp_not_reported,
      CASE WHEN temp_flags_true >= 2 THEN 'conflict'
           WHEN temp_flags_true = 0 THEN 'not_reported'
           WHEN battery_temperature_hot THEN 'hot' WHEN battery_temperature_cold THEN 'cold' ELSE 'ok' END AS battery_temp_state,
      coalesce(battery_charge_end_clean > battery_charge_start_clean, false) AS flag_charge_gain,
      CASE WHEN battery_charge_start_clean IS NOT NULL AND battery_charge_end_clean IS NOT NULL
                AND battery_charge_end_clean <= battery_charge_start_clean
           THEN battery_charge_start_clean - battery_charge_end_clean END AS battery_drain_clean,
      dup_keep AS is_analysis_row
    FROM y
    """ % {"raw": raw, "key": key, "meas": meas, "dust_flag": dust_flag, "dust_clean": dust_clean,
           "c": CLEAN, "lo": lo, "hi": hi})


def build_sessions_final(con, fences):
    con.execute("""
    CREATE OR REPLACE TABLE sessions_dq AS
    SELECT *, coalesce(clean_duration_clean < %(lo)r OR clean_duration_clean > %(hi)r, false) AS flag_duration_outlier
    FROM sessions_a ORDER BY source_file, source_row
    """ % {"lo": float(fences["lo"]), "hi": float(fences["hi"])})


def build_faults(con, win):
    lo, hi = win
    raw, occ = _list(["cohort"] + FAULT_RAW), _list(FAULT_OCC)
    con.execute("""
    CREATE OR REPLACE TABLE faults_dq AS
    WITH x AS (
      SELECT *,
        count(*) OVER (PARTITION BY %(raw)s) AS _exact_n,
        count(*) OVER (PARTITION BY %(occ)s) AS _occ_n,
        row_number() OVER (PARTITION BY %(occ)s ORDER BY date_server, source_row) AS _occ_rn,
        count(*) OVER (PARTITION BY %(occ)s, fault_status) AS _occs_n,
        row_number() OVER (PARTITION BY %(occ)s, fault_status ORDER BY date_server, source_row) AS _occs_rn
      FROM read_parquet('%(c)s/faults.parquet')
    )
    SELECT * EXCLUDE (_exact_n, _occ_n, _occ_rn, _occs_n, _occs_rn),
      CASE WHEN _exact_n > 1 THEN 'exact_copy' WHEN _occs_n > 1 THEN 'reupload' ELSE 'distinct' END AS dup_class,
      (_occs_rn = 1 AND fault_timestamp IS NOT NULL) AS dup_keep,
      _occs_n AS dup_group_size,
      fault_timestamp IS NULL AS flag_null_fault_ts,
      _occ_n > _occs_n AS flag_occ_multi_status,
      (_occ_rn = 1 AND fault_timestamp IS NOT NULL) AS is_analysis_row,
      (_occs_rn = 1 AND fault_timestamp IS NOT NULL) AS is_analysis_row_status_rule,
      coalesce(date_server < fault_timestamp, false) AS flag_server_before_event,
      coalesce(log2_time_sync_old = 0, false) OR coalesce(log2_time_sync_new = 0, false) AS flag_epoch_zero_sync,
      coalesce(fault_timestamp < TIMESTAMP '%(lo)s' OR fault_timestamp > TIMESTAMP '%(hi)s', false) AS flag_fault_ts_outside_window,
      coalesce((log2_time_sync_old > 0 AND (log2_time_sync_old_ts < TIMESTAMP '%(lo)s' OR log2_time_sync_old_ts > TIMESTAMP '%(hi)s'))
        OR (log2_time_sync_new > 0 AND (log2_time_sync_new_ts < TIMESTAMP '%(lo)s' OR log2_time_sync_new_ts > TIMESTAMP '%(hi)s')), false)
        AS flag_timesync_outside_window
    FROM x ORDER BY source_file, source_row
    """ % {"raw": raw, "occ": occ, "c": CLEAN, "lo": lo, "hi": hi})


def _build_payload_table(con, name, win, parsed_only):
    lo, hi = win
    hashexpr = "CASE WHEN parse_status = 'parsed' THEN payload_hash END" if parsed_only else "payload_hash"
    con.execute("""
    CREATE OR REPLACE TABLE %(name)s_dq AS
    WITH x AS (
      SELECT *, %(h)s AS _h,
        count(*) OVER (PARTITION BY anonymized_serial, %(h)s) AS _n,
        row_number() OVER (PARTITION BY anonymized_serial, %(h)s ORDER BY server_timestamp, source_row) AS _rn,
        min(hdr_timestamp) OVER (PARTITION BY anonymized_serial, %(h)s) AS _hmin,
        max(hdr_timestamp) OVER (PARTITION BY anonymized_serial, %(h)s) AS _hmax
      FROM read_parquet('%(c)s/%(name)s.parquet')
    )
    SELECT * EXCLUDE (_h, _n, _rn, _hmin, _hmax),
      CASE WHEN _h IS NULL THEN 'n/a_not_parsed' WHEN _n > 1 THEN 'reupload' ELSE 'distinct' END AS dup_class,
      coalesce(_rn = 1, false) AS dup_keep,
      CASE WHEN _h IS NULL THEN NULL ELSE _n END AS dup_group_size,
      coalesce(_hmin <> _hmax, false) AS flag_reupload_hdr_differs,
      (parse_status = 'parsed' AND _rn = 1) AS is_analysis_row,
      coalesce(server_timestamp < hdr_timestamp, false) AS flag_server_before_hdr,
      coalesce(hdr_timestamp < TIMESTAMP '%(lo)s' OR hdr_timestamp > TIMESTAMP '%(hi)s', false) AS flag_hdr_outside_window
    FROM x ORDER BY source_file, source_row
    """ % {"name": name, "h": hashexpr, "c": CLEAN, "lo": lo, "hi": hi})


def build_motor(con, win):
    _build_payload_table(con, "motor", win, parsed_only=True)


def build_battery(con, win):
    _build_payload_table(con, "battery", win, parsed_only=True)


# ---------------------------------------------------------------------------
# A. duplicates / analysis rows
# ---------------------------------------------------------------------------
def check_duplicates_sessions(df):
    t, out = "clean_sessions", []
    for cls, act in (("exact_copy", "dup_keep=False for all but one (earliest date_server, then lowest source_row); not an analysis row"),
                     ("join_fanout", "same serial+session_id+date_server, differs only in log3_time_sync_*; one kept [assumed: join artefact]")):
        out.append(summarise("dup_class=%s, not kept [all rows]" % cls, t, df, (df["dup_class"] == cls) & ~df["dup_keep"], act))
    out.append(summarise("dup_class=exact_copy or join_fanout, any member of a group [all rows]", t, df,
                         df["dup_class"].isin(["exact_copy", "join_fanout"]), "informational: rows in a duplicate group incl. the kept one"))
    out.append(summarise("flag_key_conflict: same serial+session_id+date_server but different measured columns [all rows]", t, df,
                         df["flag_key_conflict"], "all rows kept (not merged); flag only"))
    out.append(summarise("is_analysis_row [all rows]", t, df, df["is_analysis_row"], "rows used from Step 5"))
    return pd.concat(out, ignore_index=True)


def check_duplicates_faults(df):
    t, out = "faults", []
    out.append(summarise("flag_null_fault_ts [all rows]", t, df, df["flag_null_fault_ts"],
                         "flagged and excluded from both analysis flags"))
    out.append(summarise("dup_class=exact_copy, not kept [all rows]", t, df, (df["dup_class"] == "exact_copy") & ~df["dup_keep"],
                         "identical in all raw columns; not kept"))
    out.append(summarise("dup_class=reupload, not kept [all rows]", t, df, (df["dup_class"] == "reupload") & ~df["dup_keep"],
                         "same occurrence key + fault_status, differs in other columns (e.g. date_server); earliest date_server kept [assumed: re-upload of one event]"))
    out.append(summarise("flag_occ_multi_status: occurrence key seen with more than one fault_status (incl. null) [all rows]", t, df,
                         df["flag_occ_multi_status"], "informational; meaning of fault_status unknown, so both counting rules are kept"))
    out.append(summarise("is_analysis_row (primary: one per serial+session_id+fault_type+fault_value+fault_timestamp) [all rows]", t, df,
                         df["is_analysis_row"], "primary fault count; does not depend on fault_status"))
    out.append(summarise("is_analysis_row_status_rule (primary key + fault_status) [all rows]", t, df,
                         df["is_analysis_row_status_rule"], "sensitivity count"))
    out.append(summarise("fault_status null [analysis rows]", t, df, df["fault_status"].isna(), "informational; null is its own level in the status rule",
                         basis=df["is_analysis_row_status_rule"]))
    return pd.concat(out, ignore_index=True)


def check_duplicates_payload(df, table):
    out = []
    parsed = df["parse_status"] == "parsed"
    out.append(summarise("dup_class=reupload, not kept (same serial+payload_hash) [parsed rows]", table, df,
                         (df["dup_class"] == "reupload") & ~df["dup_keep"],
                         "earliest server_timestamp kept, then lowest source_row; not an analysis row", basis=parsed))
    out.append(summarise("re-upload groups whose hdr_timestamp differs [parsed rows]", table, df, df["flag_reupload_hdr_differs"],
                         "informational: identical payload under different device timestamps; collapsed by payload_hash per project decision", basis=parsed))
    out.append(summarise("is_analysis_row [all rows]", table, df, df["is_analysis_row"], "parsed and first of its (serial, payload_hash) group"))
    if table == "battery":
        for status, act in (("empty_payload", "no decoded_data; not an analysis row"),
                            ("unparsed_layout", "labelled/flat layout left unparsed (project decision); not an analysis row")):
            sel = df["parse_status"] == status
            n_ser = df[sel].groupby("cohort")["anonymized_serial"].nunique().to_dict()
            for c in COHORTS:
                n_ser.setdefault(c, 0)
            r = summarise("parse_status=%s [all rows]" % status, table, df, sel,
                          act + "; serials: normal=%d, return_repair=%d" % (n_ser["normal"], n_ser["return_repair"]))
            out.append(r)
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------
# B. invalid values (clean_sessions)
# ---------------------------------------------------------------------------
def check_invalid_sessions(df):
    t, a = "clean_sessions", df["is_analysis_row"]
    out = []
    for c in DUST:
        out.append(summarise("%s = 65535 [analysis rows]" % c, t, df, df[c] == 65535,
                             "set to missing in %s_clean [inferred: sentinel for no reading]" % c, basis=a))
    out.append(summarise("flag_dust_sentinel (any dust column = 65535) [analysis rows]", t, df, df["flag_dust_sentinel"], "see per-column rows", basis=a))
    for c in ("battery_charge_start", "battery_charge_end", "battery_health"):
        out.append(summarise("%s outside 0-100 [analysis rows]" % c, t, df, (df[c] < 0) | (df[c] > 100),
                             "set to missing in %s_clean; row kept" % c, basis=a))
    out.append(summarise("flag_charge_gain: charge_end > charge_start (after range cleaning) [analysis rows]", t, df, df["flag_charge_gain"],
                         "values kept; battery_drain_clean left missing for these rows (drain metrics only)", basis=a))
    out.append(summarise("flag_temp_not_reported: none of hot/cold/ok true [analysis rows]", t, df, df["flag_temp_not_reported"],
                         "flag only; equals battery_temp_state = not_reported; 2-3 true would be 'conflict' (see state rows); all three null is reported separately", basis=a))
    for k in (2, 3):
        out.append(summarise("%d of the 3 temperature flags true (conflict) [analysis rows]" % k, t, df,
                             df["temp_flags_true"] == k, "breakdown", basis=a))
    for st in ("hot", "cold", "ok", "not_reported", "conflict"):
        out.append(summarise("battery_temp_state = %s [analysis rows]" % st, t, df, df["battery_temp_state"] == st,
                             "derived column; not_reported = no flag true (project decision); not comparable across cohorts", basis=a))
    out.append(summarise("flag_temp_all_null: all three temperature flags null [analysis rows]", t, df, df["flag_temp_all_null"],
                         "flag only", basis=a))
    out.append(summarise("clean_duration = 0 [analysis rows]", t, df, df["clean_duration"] == 0,
                         "flag_duration_nonpositive; set to missing in clean_duration_clean", basis=a))
    out.append(summarise("clean_duration < 0 [analysis rows]", t, df, df["clean_duration"] < 0,
                         "flag_duration_nonpositive; set to missing in clean_duration_clean", basis=a))
    return pd.concat(out, ignore_index=True)


def value_range_table(frames):
    """Min / max / count of zeros, negatives and common sentinels for every numeric column (analysis rows)."""
    rows = []
    for table, df in frames.items():
        d = df[df["is_analysis_row"]]
        num = [c for c in d.select_dtypes("number").columns if c not in ("source_row",)]
        for cohort in COHORTS:
            x = d[d["cohort"] == cohort]
            for c in num:
                v = x[c].dropna()
                rows.append({"table": table, "cohort": cohort, "column": c, "n_non_null": int(len(v)),
                             "min": v.min() if len(v) else np.nan, "max": v.max() if len(v) else np.nan,
                             "n_zero": int((v == 0).sum()), "n_negative": int((v < 0).sum()),
                             "n_eq_255": int((v == 255).sum()), "n_eq_65535": int((v == 65535).sum())})
    return pd.DataFrame(rows)


def check_other_ranges(frames):
    """Counts only; no new rule is invented. Negative values and 255 / 65535 in motor and battery numeric columns."""
    out = []
    for table in ("motor", "battery"):
        df = frames[table]
        a = df["is_analysis_row"]
        num = [c for c in df.select_dtypes("number").columns if c not in ("source_row", "session_id", "log_type", "log_id", "log_size")]
        d = df[num]
        neg = (d < 0).any(axis=1)
        out.append(summarise("rows with a negative value in any numeric column [analysis rows]", table, df, neg,
                             "no rule applied; counts only", basis=a))
        for v in (255, 65535):
            m = (d == v).any(axis=1)
            out.append(summarise("rows with a value equal to %d in any numeric column [analysis rows]" % v, table, df, m,
                                 "no rule applied; %d may be a real count or a saturation value (unknown); counts only" % v, basis=a))
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------
# C. timestamps
# ---------------------------------------------------------------------------
def check_timestamps(frames, win):
    lo, hi = win
    w = "window = [%s, %s] (min/max server-side time over all tables, both cohorts)" % (lo.strftime("%Y-%m-%d %H:%M:%S"), hi.strftime("%Y-%m-%d %H:%M:%S"))
    out = []
    s, f, m, b = frames["clean_sessions"], frames["faults"], frames["motor"], frames["battery"]
    for t, df in (("motor", m), ("battery", b)):
        a = df["is_analysis_row"]
        out.append(summarise("ts_fallback_flag (hdr_timestamp after cut-off, server_timestamp used) [analysis rows]", t, df, df["ts_fallback_flag"],
                             "event_ts falls back to server_timestamp (project decision); approximate", basis=a))
        out.append(summarise("hdr_timestamp outside data window [analysis rows]", t, df, df["flag_hdr_outside_window"], "flag only; " + w, basis=a))
        out.append(summarise("server_timestamp earlier than hdr_timestamp [analysis rows]", t, df, df["flag_server_before_hdr"],
                             "flag only; includes the future-dated hdr_timestamp rows", basis=a))
    a = s["is_analysis_row"]
    out.append(summarise("log3_time_sync_old = 0 [analysis rows]", "clean_sessions", s, s["log3_time_sync_old"] == 0,
                         "left as is; epoch zero [assumed: epoch seconds]; meaning unknown", basis=a))
    out.append(summarise("log3_time_sync_new = 0 [analysis rows]", "clean_sessions", s, s["log3_time_sync_new"] == 0, "left as is", basis=a))
    out.append(summarise("log3_time_sync_* non-zero but outside data window [analysis rows]", "clean_sessions", s, s["flag_timesync_outside_window"],
                         "flag only; " + w, basis=a))
    out.append(summarise("date_server outside data window [analysis rows]", "clean_sessions", s, s["flag_date_outside_window"], "flag only; " + w, basis=a))
    a = f["is_analysis_row"]
    out.append(summarise("fault_timestamp outside data window [analysis rows]", "faults", f, f["flag_fault_ts_outside_window"], "flag only; " + w, basis=a))
    out.append(summarise("log2_time_sync_old = 0 [analysis rows]", "faults", f, f["log2_time_sync_old"] == 0, "left as is", basis=a))
    out.append(summarise("log2_time_sync_new = 0 [analysis rows]", "faults", f, f["log2_time_sync_new"] == 0, "left as is", basis=a))
    out.append(summarise("log2_time_sync_* non-zero but outside data window [analysis rows]", "faults", f, f["flag_timesync_outside_window"],
                         "flag only; " + w, basis=a))
    out.append(summarise("date_server earlier than fault_timestamp [analysis rows]", "faults", f, f["flag_server_before_event"],
                         "flag only; [inferred] date_server is receipt time, so this would be unexpected", basis=a))
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------
# D. missing data (analysis rows only)
# ---------------------------------------------------------------------------
def missingness_table(frames):
    rows = []
    for table, df in frames.items():
        d = df[df["is_analysis_row"]]
        groups = [("all", d)]
        if table == "battery":
            groups += [(p, d[d["pack_type"] == p]) for p in sorted(d["pack_type"].dropna().unique())]
        for sub, x in groups:
            for cohort in COHORTS:
                y = x[x["cohort"] == cohort]
                n = len(y)
                for c in df.columns:
                    k = int(y[c].isna().sum())
                    rows.append({"table": table, "cohort": cohort, "subgroup": sub, "column": c, "n_rows": n,
                                 "null_n": k, "null_pct": round(100.0 * k / n, 2) if n else np.nan})
    return pd.DataFrame(rows)


def check_missing(frames, miss):
    out = []
    m = miss[miss["subgroup"] == "all"]
    for table in ("clean_sessions", "faults"):
        for col in frames[table].columns:
            sub = m[(m["table"] == table) & (m["column"] == col)]
            if sub["null_n"].sum() == 0:
                continue
            per = {r["cohort"]: int(r["null_n"]) for _, r in sub.iterrows()}
            den = {r["cohort"]: int(r["n_rows"]) for _, r in sub.iterrows()}
            out.append(info_rows("null: %s [analysis rows]" % col, table, per, "reported only; see missingness.csv", den))
    for table in ("motor", "battery"):
        base = m[(m["table"] == table)]
        per = {c: int((base[base["cohort"] == c]["null_n"] > 0).sum()) for c in COHORTS}
        den = {c: int((base["cohort"] == c).sum()) for c in COHORTS}
        out.append(info_rows("columns with at least one null (count of columns, not rows) [analysis rows]", table, per,
                             "reported only; rows_affected counts columns; many are structural (e.g. 4-cell battery lacks header fields), see missingness.csv with pack_type subgroup", den))
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------
# E. outliers (flag only; 3 x IQR; both cohorts together)
# ---------------------------------------------------------------------------
def check_outliers_rows(sessions, thresholds, sink=None):
    f = thresholds["clean_duration_clean"]
    a = sessions["is_analysis_row"]
    thr = pd.DataFrame([dict(metric="clean_duration_clean", level="row", **f)])
    if sink is not None:
        sink["outlier_thresholds_rows"] = thr
    act = "flag_duration_outlier only, no exclusion; fences Q1-3*IQR..Q3+3*IQR = %.1f..%.1f (Q1=%.1f, Q3=%.1f, n=%d, both cohorts together)" % (
        f["lo"], f["hi"], f["q1"], f["q3"], f["n"])
    return summarise("clean_duration_clean beyond 3xIQR [analysis rows]", "clean_sessions", sessions, sessions["flag_duration_outlier"], act, basis=a)


def build_machine_dq(frames):
    s, f = frames["clean_sessions"], frames["faults"]
    sa = s[s["is_analysis_row"]]
    g = sa.groupby("anonymized_serial")["date_server"].agg(["count", "min", "max"]).rename(
        columns={"count": "n_analysis_sessions", "min": "first_session", "max": "last_session"})
    g["span_days"] = (g["last_session"] - g["first_session"]).dt.total_seconds() / 86400.0
    g["sessions_per_week"] = g["n_analysis_sessions"] / np.maximum(g["span_days"] / 7.0, 1.0)  # [assumed] 1-week floor
    serials = set(s["anonymized_serial"]) | set(f["anonymized_serial"])
    cohort_of = {}
    for df in frames.values():
        for ser, c in df.groupby("anonymized_serial")["cohort"].first().items():
            cohort_of.setdefault(ser, c)
        serials |= set(df["anonymized_serial"])
    md = pd.DataFrame(index=sorted(serials))
    md.index.name = "anonymized_serial"
    md["cohort"] = [cohort_of[x] for x in md.index]
    md = md.join(g)
    md["n_analysis_sessions"] = md["n_analysis_sessions"].fillna(0).astype(int)
    md["n_faults_primary"] = f[f["is_analysis_row"]].groupby("anonymized_serial").size().reindex(md.index).fillna(0).astype(int)
    md["n_faults_status_rule"] = f[f["is_analysis_row_status_rule"]].groupby("anonymized_serial").size().reindex(md.index).fillna(0).astype(int)
    den = md["n_analysis_sessions"].replace(0, np.nan)
    md["faults_per_100_sessions_primary"] = 100.0 * md["n_faults_primary"] / den
    md["faults_per_100_sessions_status_rule"] = 100.0 * md["n_faults_status_rule"] / den
    md["eligible_rate_machine"] = md["n_analysis_sessions"] >= MIN_SESSIONS
    for name in ("clean_sessions", "faults", "motor", "battery"):
        df = frames[name]
        md["in_%s" % name] = md.index.isin(df["anonymized_serial"])
        md["in_%s_analysis" % name] = md.index.isin(df.loc[df["is_analysis_row"], "anonymized_serial"])
    return md.reset_index()


def add_machine_outlier_flags(md):
    """Fences from machines with >= MIN_SESSIONS analysis sessions, both cohorts together. Flag only."""
    el = md[md["eligible_rate_machine"]]
    fences = {"sessions_per_week": _iqr_fences(el["sessions_per_week"]),
              "faults_per_100_sessions_primary": _iqr_fences(el["faults_per_100_sessions_primary"])}
    md = md.copy()
    md["flag_outlier_sessions_per_week"] = md["eligible_rate_machine"] & (
        (md["sessions_per_week"] < fences["sessions_per_week"]["lo"]) | (md["sessions_per_week"] > fences["sessions_per_week"]["hi"]))
    fp = fences["faults_per_100_sessions_primary"]
    md["flag_outlier_faults_per_100"] = md["eligible_rate_machine"] & (
        (md["faults_per_100_sessions_primary"] < fp["lo"]) | (md["faults_per_100_sessions_primary"] > fp["hi"]))
    return md, fences


def check_outliers_machines(md, fences, sink=None):
    out = []
    thr = pd.DataFrame([dict(metric=k, level="machine (>=%d analysis sessions)" % MIN_SESSIONS, **v) for k, v in fences.items()])
    if sink is not None:
        sink["outlier_thresholds_machines"] = thr
    base = md["eligible_rate_machine"]
    for metric, flag in (("sessions_per_week", "flag_outlier_sessions_per_week"), ("faults_per_100_sessions_primary", "flag_outlier_faults_per_100")):
        f = fences[metric]
        act = "flag only (machine_dq); fences %.2f..%.2f (Q1=%.2f, Q3=%.2f, n=%d machines, both cohorts together); rows_affected counts machines" % (
            f["lo"], f["hi"], f["q1"], f["q3"], f["n"])
        out.append(summarise("%s beyond 3xIQR [machines with >=%d analysis sessions]" % (metric, MIN_SESSIONS), "machine_dq", md, md[flag], act, basis=base))
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------
# F. cumulative counters
# ---------------------------------------------------------------------------
def counter_columns(table):
    if table == "motor":
        cols = [r["column"] for r in fm.motor_bin_columns()]
        cols += ["write_count", "filter_wash_counter", "on_but_not_run_time_s", "runtime_s"]
    else:
        cols = [r["column"] for r in fm.battery_bin_columns()] + [r[0] for r in fm.BATTERY_COUNTERS]
    return cols


def _decrease_stats(d, cols, table):
    """d: rows of one stage. Returns (summary dict list, per-field list). Pairs = consecutive rows of a serial by event_ts, source_row."""
    d = d.sort_values(["anonymized_serial", "event_ts", "source_row"])
    cols = [c for c in cols if c in d.columns]
    vals = d[cols].astype(float)
    diffs = vals.groupby(d["anonymized_serial"]).diff()
    first = d.groupby("anonymized_serial").cumcount() == 0
    dec = diffs < 0
    any_dec = dec.any(axis=1) & ~first
    same_ts = (d["event_ts"] == d.groupby("anonymized_serial")["event_ts"].shift(1)) & ~first
    return d, dec, any_dec, same_ts, first


def counter_decrease_tables(frames):
    """Detail rows for F: stage in {before, after}; before = all parsed rows, after = analysis rows."""
    summ, fields = [], []
    for table in ("motor", "battery"):
        df = frames[table]
        parsed = df[df["parse_status"] == "parsed"]
        stages = (("before_reupload_removal", parsed), ("after_reupload_removal", parsed[parsed["is_analysis_row"]]))
        cols = counter_columns(table)
        for stage, d in stages:
            groups = [("all", d)]
            if table == "battery":
                groups += [(p, d[d["pack_type"] == p]) for p in sorted(d["pack_type"].dropna().unique())]
            for sub, x in groups:
                for cohort in COHORTS:
                    y = x[x["cohort"] == cohort]
                    if len(y) == 0:
                        continue
                    y, dec, any_dec, same_ts, first = _decrease_stats(y, cols, table)
                    n_pairs = int((~first).sum())
                    ser_dec = y.loc[any_dec, "anonymized_serial"].nunique()
                    summ.append({"table": table, "stage": stage, "pack_type": sub, "cohort": cohort,
                                 "rows": len(y), "serials": int(y["anonymized_serial"].nunique()),
                                 "pairs": n_pairs, "pairs_with_decrease": int(any_dec.sum()),
                                 "serials_with_decrease": int(ser_dec), "pairs_same_event_ts": int(same_ts.sum())})
                    for c in dec.columns:
                        fields.append({"table": table, "stage": stage, "pack_type": sub, "cohort": cohort, "field": c,
                                       "decreases": int(dec[c].sum())})
    return pd.DataFrame(summ), pd.DataFrame(fields)


def check_counter_decreases(frames, sink=None):
    summ, fields = counter_decrease_tables(frames)
    if sink is not None:
        sink["counter_decreases"] = summ
        sink["counter_decreases_by_field"] = fields
    out = []
    for table in ("motor", "battery"):
        for sub in (["all"] if table == "motor" else ["all", "4-cell", "7-cell"]):
            for stage in ("before_reupload_removal", "after_reupload_removal"):
                x = summ[(summ["table"] == table) & (summ["pack_type"] == sub) & (summ["stage"] == stage)]
                tag = "" if table == "motor" else " [%s]" % ("all packs" if sub == "all" else sub)
                per = {r["cohort"]: int(r["pairs_with_decrease"]) for _, r in x.iterrows()}
                den = {r["cohort"]: int(r["pairs"]) for _, r in x.iterrows()}
                out.append(info_rows("consecutive pairs with a counter decrease, %s%s [pairs]" % (stage, tag), table, per,
                                     "not fixed; Step 5 sets these deltas to missing; rows_affected counts pairs of consecutive observations", den))
                per = {r["cohort"]: int(r["serials_with_decrease"]) for _, r in x.iterrows()}
                den = {r["cohort"]: int(r["serials"]) for _, r in x.iterrows()}
                out.append(info_rows("serials with at least one counter decrease, %s%s [serials]" % (stage, tag), table, per,
                                     "rows_affected counts serials", den))
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------
# G. coverage and fault codes
# ---------------------------------------------------------------------------
def coverage_tables(frames):
    names = ["clean_sessions", "faults", "motor", "battery"]
    rows = []
    sets = {}
    for c in COHORTS:
        union = set()
        for n in names:
            df = frames[n]
            allset = set(df.loc[df["cohort"] == c, "anonymized_serial"])
            ana = set(df.loc[(df["cohort"] == c) & df["is_analysis_row"], "anonymized_serial"])
            sets[(c, n)] = (allset, ana)
            union |= allset
        sets[(c, "union")] = (union, union)
        for n in names:
            rows.append({"cohort": c, "metric": "machines in %s (any row)" % n, "machines": len(sets[(c, n)][0]), "of": len(union)})
            rows.append({"cohort": c, "metric": "machines in %s (analysis rows)" % n, "machines": len(sets[(c, n)][1]), "of": len(union)})
        rows.append({"cohort": c, "metric": "machines in all four tables (any row)", "machines": len(set.intersection(*[sets[(c, n)][0] for n in names])), "of": len(union)})
        rows.append({"cohort": c, "metric": "machines in all four tables (analysis rows)", "machines": len(set.intersection(*[sets[(c, n)][1] for n in names])), "of": len(union)})
    return pd.DataFrame(rows)


def check_coverage(frames, sink=None):
    cov = coverage_tables(frames)
    out = []
    for metric in cov["metric"].unique():
        x = cov[cov["metric"] == metric]
        per = {r["cohort"]: int(r["machines"]) for _, r in x.iterrows()}
        den = {r["cohort"]: int(r["of"]) for _, r in x.iterrows()}
        out.append(info_rows("coverage: %s [machines]" % metric, "all_tables", per, "reported only; rows_affected counts machines, pct = share of machines seen in any table", den))
    s, f = frames["clean_sessions"], frames["faults"]
    sess_keys = set(zip(s.loc[s["is_analysis_row"], "anonymized_serial"], s.loc[s["is_analysis_row"], "session_id"]))
    fa = f[f["is_analysis_row"]]
    match = pd.Series([k in sess_keys for k in zip(fa["anonymized_serial"], fa["session_id"])], index=fa.index)
    per = {c: int(match[fa["cohort"] == c].sum()) for c in COHORTS}
    den = {c: int((fa["cohort"] == c).sum()) for c in COHORTS}
    out.append(info_rows("fault occurrences (primary) matching a session on serial+session_id [occurrences]", "faults", per,
                         "reported only; rows_affected = matching occurrences", den))
    both = set(s.loc[s["cohort"] == "normal", "anonymized_serial"]) & set(s.loc[s["cohort"] == "return_repair", "anonymized_serial"])
    for n in ("faults", "motor", "battery"):
        both |= set(frames[n].loc[frames[n]["cohort"] == "normal", "anonymized_serial"]) & set(frames[n].loc[frames[n]["cohort"] == "return_repair", "anonymized_serial"])
    out.append(info_rows("serials present in both cohorts [serials]", "all_tables", {"normal": len(both), "return_repair": 0}, "expected 0; rows_affected counts serials"))
    if sink is not None:
        sink["coverage"] = cov
    return pd.concat(out, ignore_index=True)


def fault_code_table(faults):
    d = faults.copy()
    d["fault_status"] = d["fault_status"].astype("Int64")
    g = d.groupby(["cohort", "fault_type", "fault_value", "fault_status"], dropna=False).agg(
        rows_raw=("source_row", "size"),
        occurrences_primary=("is_analysis_row", "sum"),
        occurrences_status_rule=("is_analysis_row_status_rule", "sum")).reset_index()
    def meaning(r):
        t = fm.FAULT_TYPES.get(int(r["fault_type"]))
        if t is None:
            return "no stated meaning (fault_type not in brief)"
        v = t[1].get(int(r["fault_value"]))
        return "%s: %s" % (t[0], v if v is not None else "fault_value not in the brief's list")
    g["meaning_in_brief"] = g.apply(meaning, axis=1)
    return g


def check_fault_codes(faults, sink=None):
    tab = fault_code_table(faults)
    if sink is not None:
        sink["fault_type_counts"] = tab
    a = faults["is_analysis_row"]
    known = faults["fault_type"].isin(list(fm.FAULT_TYPES))
    def val_ok(r):
        t = fm.FAULT_TYPES.get(r["fault_type"])
        return t is not None and (not t[1] or r["fault_value"] in t[1])
    ok = faults.apply(val_ok, axis=1)
    out = [summarise("fault_type without a stated meaning [analysis rows]", "faults", faults, ~known, "reported as unknown, never guessed", basis=a),
           summarise("fault_value not in the brief's list for its fault_type [analysis rows]", "faults", faults, known & ~ok, "flag only", basis=a)]
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------
# H. motor variant rows
# ---------------------------------------------------------------------------
def _signature(obj, prefix=""):
    if isinstance(obj, dict):
        s = set()
        for k, v in obj.items():
            s |= _signature(v, prefix + "/" + str(k))
        return s
    if isinstance(obj, list):
        s = {prefix + "[%d]" % len(obj)}
        for v in obj:
            if isinstance(v, (dict, list)):
                s |= _signature(v, prefix + "[]")
        return s
    kind = "bool" if isinstance(obj, bool) else "num" if isinstance(obj, (int, float)) else "null" if obj is None else "str"
    return {prefix + ":" + kind}


def check_motor_variant(motor, sink=None):
    """Compare payload structure (key paths, array lengths, value kinds) of the 683 / 692B rows with the other
    Return/Repair rows. Reads the raw CSV (read-only); the Normal motor file has no decoded_data."""
    raw_path = ROOT / "return_repair_machines" / "Motor_Return:Repair Machines.csv"
    rr = motor[motor["cohort"] == "return_repair"].sort_values("source_row")
    raw = pd.read_csv(raw_path, usecols=["decoded_data"], low_memory=False)
    if len(raw) != len(rr) or (rr["source_row"].values != np.arange(len(rr))).any():
        raise RuntimeError("motor RR raw file and parquet rows do not line up")
    variant = rr["motor_model_raw"].isin(["683", "692B"]).values
    sigs = [frozenset(_signature(json.loads(x))) for x in raw["decoded_data"]]
    var_sigs = set(s for s, v in zip(sigs, variant) if v)
    oth_sigs = set(s for s, v in zip(sigs, variant) if not v)
    var_paths, oth_paths = set().union(*var_sigs), set().union(*oth_sigs)
    differs = [(v and s not in oth_sigs) for s, v in zip(sigs, variant)]
    detail = pd.DataFrame([
        {"item": "variant rows", "value": int(variant.sum())},
        {"item": "other RR rows", "value": int((~variant).sum())},
        {"item": "distinct structure signatures among variant rows", "value": len(var_sigs)},
        {"item": "distinct structure signatures among other rows", "value": len(oth_sigs)},
        {"item": "variant signatures also present among other rows", "value": len(var_sigs & oth_sigs)},
        {"item": "paths only in variant rows", "value": len(var_paths - oth_paths)},
        {"item": "paths only in other rows", "value": len(oth_paths - var_paths)},
        {"item": "variant rows with parse_status != parsed", "value": int((rr.loc[variant, "parse_status"] != "parsed").sum())},
        {"item": "variant rows by motor_model_raw", "value": json.dumps(rr.loc[variant, "motor_model_raw"].value_counts().to_dict())},
        {"item": "variant rows by serial", "value": rr.loc[variant, "anonymized_serial"].nunique()},
    ])
    if sink is not None:
        sink["motor_variant_structure"] = detail
    n_diff = int(sum(differs))
    act = ("key paths + array lengths + value kinds compared with the other RR rows: %d variant rows, %d with a structure not seen in other rows; "
           "paths only in variant: %d, only in other: %d. Report only; rows kept" % (int(variant.sum()), n_diff, len(var_paths - oth_paths), len(oth_paths - var_paths)))
    return info_rows("motor_model_raw 683/692B rows whose payload structure differs from other rows [RR rows]", "motor",
                     {"normal": 0, "return_repair": n_diff}, act, {"normal": 0, "return_repair": int(variant.sum())})


# ---------------------------------------------------------------------------
# I. fault count sensitivity
# ---------------------------------------------------------------------------
def fault_rate_sensitivity(md):
    el = md[md["eligible_rate_machine"]]
    rows = []
    for c in COHORTS + ("all",):
        x = el if c == "all" else el[el["cohort"] == c]
        rows.append({"cohort": c, "machines_with_ge_%d_sessions" % MIN_SESSIONS: len(x),
                     "median_faults_per_100_sessions_primary": x["faults_per_100_sessions_primary"].median(),
                     "median_faults_per_100_sessions_status_rule": x["faults_per_100_sessions_status_rule"].median(),
                     "total_faults_primary": int(x["n_faults_primary"].sum()),
                     "total_faults_status_rule": int(x["n_faults_status_rule"].sum())})
    return pd.DataFrame(rows)


def check_fault_sensitivity(md, sink=None):
    t = fault_rate_sensitivity(md)
    if sink is not None:
        sink["fault_rate_sensitivity"] = t
    per = {r["cohort"]: int(r.iloc[1]) for _, r in t.iterrows() if r["cohort"] in COHORTS}
    parts = ["%s: median primary=%.2f, status rule=%.2f" % (r["cohort"], r["median_faults_per_100_sessions_primary"],
                                                           r["median_faults_per_100_sessions_status_rule"]) for _, r in t.iterrows()]
    return info_rows("median faults per 100 sessions per machine, primary vs status rule [machines with >=%d analysis sessions]" % MIN_SESSIONS,
                     "machine_dq", per, "numbers only, no interpretation; rows_affected counts machines. " + "; ".join(parts))


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def _write(con, table, name):
    DQ_DIR.mkdir(parents=True, exist_ok=True)
    out = DQ_DIR / ("%s.parquet" % name)
    con.execute("COPY %s TO '%s' (FORMAT PARQUET)" % (table, out))


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    win = data_window(con)
    build_sessions_stage_a(con, win)
    sa = _read(con, "sessions_a")
    fences_dur = _iqr_fences(sa.loc[sa["is_analysis_row"], "clean_duration_clean"])
    build_sessions_final(con, fences_dur)
    build_faults(con, win)
    build_motor(con, win)
    build_battery(con, win)
    frames = {"clean_sessions": _read(con, "sessions_dq"), "faults": _read(con, "faults_dq"),
              "motor": _read(con, "motor_dq"), "battery": _read(con, "battery_dq")}

    for name, df in frames.items():
        nulls = [c for c in df.columns if (c.startswith("flag_") or c.startswith("is_analysis_row") or c == "dup_keep") and df[c].isna().any()]
        if nulls:
            raise SystemExit("flag columns with nulls in %s: %s" % (name, nulls))

    sink = {}
    md = build_machine_dq(frames)
    md, mfences = add_machine_outlier_flags(md)
    con.register("md_df", md)
    con.execute("CREATE OR REPLACE TABLE machine_dq AS SELECT * FROM md_df")

    s = frames["clean_sessions"]
    parts = [
        check_duplicates_sessions(s), check_duplicates_faults(frames["faults"]),
        check_duplicates_payload(frames["motor"], "motor"), check_duplicates_payload(frames["battery"], "battery"),
        check_invalid_sessions(s), check_other_ranges(frames), check_timestamps(frames, win),
    ]
    miss = missingness_table(frames)
    parts.append(check_missing(frames, miss))
    parts += [check_outliers_rows(s, {"clean_duration_clean": fences_dur}, sink), check_outliers_machines(md, mfences, sink),
              check_counter_decreases(frames, sink), check_coverage(frames, sink), check_fault_codes(frames["faults"], sink),
              check_motor_variant(frames["motor"], sink), check_fault_sensitivity(md, sink)]
    summary = pd.concat(parts, ignore_index=True)[SUMMARY_COLS]
    summary.to_csv(REPORT_DIR / "dq_summary.csv", index=False)
    miss.to_csv(REPORT_DIR / "missingness.csv", index=False)
    value_range_table(frames).to_csv(REPORT_DIR / "value_ranges.csv", index=False)
    thr = pd.concat([sink.pop("outlier_thresholds_rows"), sink.pop("outlier_thresholds_machines")], ignore_index=True)
    thr.to_csv(REPORT_DIR / "outlier_thresholds.csv", index=False)
    for k, v in sink.items():
        v.to_csv(REPORT_DIR / ("%s.csv" % k), index=False)

    for table, name in (("sessions_dq", "clean_sessions"), ("faults_dq", "faults"), ("motor_dq", "motor"), ("battery_dq", "battery"),
                        ("machine_dq", "machine_dq")):
        _write(con, table, name)

    # integrity: original columns preserved (row count and non-null counts equal the Step 3 outputs)
    for name in ("clean_sessions", "faults", "motor", "battery"):
        raw_cols = [r[0] for r in con.execute("DESCRIBE SELECT * FROM read_parquet('%s/%s.parquet')" % (CLEAN, name)).fetchall()]
        sel = ", ".join("count(%s) AS %s" % (c, c) for c in raw_cols)
        a = con.execute("SELECT count(*), %s FROM read_parquet('%s/%s.parquet')" % (sel, CLEAN, name)).fetchall()
        b = con.execute("SELECT count(*), %s FROM read_parquet('%s/%s.parquet')" % (sel, DQ_DIR, name)).fetchall()
        if a != b:
            raise SystemExit("integrity check failed for %s: original columns changed" % name)
    print("integrity: original columns preserved in all four tables")
    pd.set_option("display.width", 250, "display.max_colwidth", 70)
    print(frames["clean_sessions"].groupby("cohort")["is_analysis_row"].sum())
    print("wrote", REPORT_DIR / "dq_summary.csv", "(%d rows)" % len(summary))


if __name__ == "__main__":
    main()
