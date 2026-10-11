"""Step 3: parse and harmonise the raw CSVs into lossless Parquet tables in data/clean/.

Run from the repo root:  python src/build_clean.py

Outputs (generated, do not hand-edit):
    data/clean/clean_sessions.parquet, faults.parquet, motor.parquet, battery.parquet,
    data/clean/battery_event_snapshots.parquet, machine_lookup.parquet
    reports/profiling/parse_summary.csv, machine_lookup_checks.csv, clean_column_dictionary.csv

Principles: raw files are read-only; no row is dropped (every output row carries source_file and
source_row of exactly one raw row); values are not changed, cleaned, de-duplicated or deltaed
(that is Steps 4-5). The script exits non-zero if the motor reconciliation, or any row count, fails.
"""
import hashlib
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

import field_meanings as fm
import payload_parsers as pp

ROOT = Path(__file__).resolve().parent.parent
CLEAN_DIR = ROOT / "data" / "clean"
REPORT_DIR = ROOT / "reports" / "profiling"
COHORT_DIRS = {"normal": ROOT / "normal_machines", "return_repair": ROOT / "return_repair_machines"}
COHORT_SUFFIX = {"normal": "Normal Machines", "return_repair": "Return:Repair Machines"}
FILE_PREFIX = {"clean_sessions": "Clean Sessions", "faults": "Faults", "motor": "Motor", "battery": "Battery"}

# Expected payload counts from docs/parsing_spec.md (section 1 and the assumptions log).
SPEC_BATTERY_COUNTS = {
    "normal": {"parsed": 1250, "unparsed_layout": 0, "empty_payload": 1516},
    "return_repair": {"parsed": 542, "unparsed_layout": 39, "empty_payload": 32033},
}
SPEC_MOTOR_PARSED = {"normal": 470, "return_repair": 564}


# ---------------------------------------------------------------------------
# Reading and casting helpers
# ---------------------------------------------------------------------------


def read_raw(table):
    """Read both cohorts of a table as strings (empty field = null), add cohort/source columns."""
    frames = []
    for cohort, folder in COHORT_DIRS.items():
        fname = "%s_%s.csv" % (FILE_PREFIX[table], COHORT_SUFFIX[cohort])
        df = pd.read_csv(str(folder / fname), dtype=str, keep_default_na=False, na_values=[""])
        df.insert(0, "source_row", np.arange(len(df), dtype="int64"))  # 0-based position among data rows
        df.insert(0, "source_file", "%s/%s" % (folder.name, fname))
        df.insert(2, "cohort", cohort)
        frames.append(df)
    return pd.concat(frames, ignore_index=True, sort=False)


class Casts:
    """Casting with a count of values that became null because they did not parse."""

    def __init__(self):
        self.nulled = {}

    def _note(self, col, n):
        if n:
            self.nulled[col] = self.nulled.get(col, 0) + int(n)

    def ts(self, s, col):
        parsed = pd.to_datetime(s.str.replace(" UTC", "", regex=False), errors="coerce")
        self._note(col, (s.notna() & parsed.isna()).sum())
        return parsed  # tz-naive, value is UTC (the raw text ends in " UTC")

    def int(self, s, col):
        num = pd.to_numeric(s, errors="coerce")
        bad = (s.notna() & num.isna()) | (num.notna() & (num != num.round()))
        self._note(col, bad.sum())
        return num.where(~bad).astype("Int64")

    def bool(self, s, col):
        mapped = s.map({"true": True, "false": False})  # raw text is lower case
        self._note(col, (s.notna() & mapped.isna()).sum())
        return mapped.astype("boolean")

    def epoch_ts(self, int_series, col):
        """Epoch seconds -> timestamp. [assumed] unit is seconds."""
        return pd.to_datetime(int_series.astype("float64"), unit="s", errors="coerce")


def write_parquet(df, name):
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    path = CLEAN_DIR / ("%s.parquet" % name)
    con = duckdb.connect()
    con.register("t", df)
    con.execute("COPY t TO '%s' (FORMAT PARQUET)" % str(path))
    n = con.execute("SELECT count(*) FROM read_parquet('%s')" % str(path)).fetchone()[0]
    con.close()
    return n


def md5(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Clean sessions and faults
# ---------------------------------------------------------------------------

SESSION_SPEC = {
    "str": ["anonymized_serial", "region", "battery_soc_state", "model", "running_firmware_version"],
    "ts": ["date"],
    "int": ["session_id", "clean_duration", "battery_charge_start", "battery_charge_end", "battery_health",
            "ultra_fine_dust_particle_mass", "fine_dust_particle_mass", "coarse_dust_particle_mass",
            "large_dust_particle_mass", "log3_time_sync_old", "log3_time_sync_new"],
    "bool": ["battery_temperature_hot", "battery_temperature_cold", "battery_temperature_ok"],
    "epoch": ["log3_time_sync_old", "log3_time_sync_new"],
}
FAULT_SPEC = {
    "str": ["anonymized_serial", "region", "model", "product_alarm_source", "hex_error_code",
            "product_alarm_fault_severity"],
    "ts": ["date", "fault_timestamp"],
    "int": ["session_id", "fault_type", "fault_value", "fault_status", "log2_time_sync_old", "log2_time_sync_new"],
    "bool": [],
    "epoch": ["log2_time_sync_old", "log2_time_sync_new"],
}


def build_typed(table, spec, casts):
    """Union of both cohorts with types cast; one output row per raw row, values unchanged."""
    raw = read_raw(table)
    meta = ["source_file", "source_row", "cohort"]
    declared = set(spec["str"] + spec["ts"] + spec["int"] + spec["bool"])
    unexpected = [c for c in raw.columns if c not in declared and c not in meta]
    if unexpected:
        raise RuntimeError("%s: columns not covered by the cast spec: %s" % (table, unexpected))
    out = raw[meta].copy()
    renames = fm.RENAMED_COLUMNS[table]
    for col in [c for c in raw.columns if c not in meta]:
        name = renames.get(col, col)
        key = "%s.%s" % (table, col)
        if col in spec["str"]:
            out[name] = raw[col]
        elif col in spec["ts"]:
            out[name] = casts.ts(raw[col], key)
        elif col in spec["int"]:
            out[name] = casts.int(raw[col], key)
        else:
            out[name] = casts.bool(raw[col], key)
        if col in spec["epoch"]:
            out[name + "_ts"] = casts.epoch_ts(out[name], key + "_ts")
    # lossless check: the non-null count of every raw column is preserved
    lost = {}
    for col in [c for c in raw.columns if c not in meta]:
        a, b = int(raw[col].notna().sum()), int(out[renames.get(col, col)].notna().sum())
        if a != b:
            lost[col] = (a, b)
    return raw, out, lost


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

MOTOR_META = ["region", "country", "prefix", "session_id", "battery_version", "log_type", "log_id", "log_size"]
MOTOR_INT_META = ["session_id", "log_id", "log_size"]


def parsed_column_dtypes_motor():
    cols = {}
    for r in fm.motor_bin_columns():
        cols[r["column"]] = "Int64"
    for c in fm.MOTOR_SCALARS:
        cols[c[0]] = "Int64"
    cols["runtime_s"] = "Int64"
    cols["ambient_temperature_C"] = "float64"
    cols["ambient_pressure_kpa"] = "float64"
    cols["exhaust_bins_8_10_nonzero_flag"] = "boolean"
    return cols


def parsed_column_dtypes_battery():
    cols = {}
    for r in fm.battery_bin_columns():
        cols[r["column"]] = "Int64"
    for c in fm.BATTERY_COUNTERS:
        cols[c[0]] = "Int64"
    for c in fm.BATTERY_RESISTANCE:
        cols[c[0]] = "Int64"
    return cols


def parsed_frame(rows, dtypes, index):
    data = {}
    for col, dt in dtypes.items():
        vals = [r.get(col) for r in rows]
        data[col] = pd.array(vals, dtype=dt)
    return pd.DataFrame(data, index=index)


def add_event_ts(df, cutoff):
    """event_ts = hdr_timestamp, or server_timestamp when hdr is null or later than the cut-off."""
    hdr, srv = df["hdr_timestamp"], df["server_timestamp"]
    fb = hdr.isna() | (hdr > cutoff)
    df["event_ts"] = hdr.where(~fb, srv)
    df["ts_fallback_flag"] = fb
    return df


def common_payload_meta(raw, casts, table):
    out = raw[["source_file", "source_row", "cohort", "anonymized_serial"]].copy()
    out["server_timestamp"] = casts.ts(raw["server_timestamp"], table + ".server_timestamp")
    out["hdr_timestamp"] = casts.ts(raw["hdr_timestamp"], table + ".hdr_timestamp")
    return out


def build_motor(raw, casts, cutoff):
    rows, status, errors, hashes = [], [], [], []
    for s in raw["decoded_data"]:
        if pd.isna(s):
            rows.append({}); status.append("empty_payload"); errors.append(None); hashes.append(None)
            continue
        hashes.append(md5(s))
        try:
            rows.append(pp.parse_motor(json.loads(s)))
            status.append("parsed"); errors.append(None)
        except (ValueError, KeyError, TypeError, IndexError, AttributeError, pp.ParseError) as e:
            rows.append({}); status.append("error"); errors.append("%s: %s" % (type(e).__name__, e))
    out = common_payload_meta(raw, casts, "motor")
    out = add_event_ts(out, cutoff)
    out["motor_model_raw"] = raw["model"]  # raw value; may be a motor variant code, not a product model
    for c in MOTOR_META:
        if c not in raw:
            out[c] = None
        elif c in MOTOR_INT_META:
            out[c] = casts.int(raw[c], "motor." + c)
        else:
            out[c] = raw[c]
    out["payload_hash"] = hashes
    out["parse_status"] = status
    out["parse_error"] = errors
    parsed = parsed_frame(rows, parsed_column_dtypes_motor(), raw.index)
    return pd.concat([out, parsed], axis=1)


def reconcile_motor(raw, out):
    """Normal rows: parsed values must equal the flattened columns. Returns (n_rows, {column: mismatches})."""
    mask = (raw["cohort"] == "normal").values
    r, o = raw[mask], out[mask]
    cols = [c["column"] for c in fm.motor_bin_columns() if c["array"] != "ddm692_FisfTempBins"]
    cols += ["ambient_pressure_pa", "ambient_temperature_mC", "write_count", "ambient_temperature_C",
             "ambient_pressure_kpa"]
    pairs = [(c, c) for c in cols] + [("runtime_s", "cumulative_usage_duration_seconds")]
    mism = {}
    for parsed, flat in pairs:
        a = o[parsed].astype("float64").values
        b = pd.to_numeric(r[flat]).astype("float64").values
        mism[parsed] = int((~np.isclose(a, b, rtol=0, atol=1e-6)).sum())  # NaN on either side counts as a mismatch
    return int(mask.sum()), mism


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------


def build_battery(raw, casts, cutoff):
    rows, status, errors, hashes, layouts, packs, snaps, sig_mismatch = [], [], [], [], [], [], [], 0
    keyed = raw[["source_file", "source_row", "cohort", "anonymized_serial"]].to_dict("records")
    for k, s in zip(keyed, raw["decoded_data"]):
        if pd.isna(s):
            rows.append({}); status.append("empty_payload"); errors.append(None); hashes.append(None)
            layouts.append(None); packs.append(None)
            continue
        hashes.append(md5(s))
        try:
            payload = json.loads(s)
            layout = pp.detect_layout(payload)
            layouts.append(layout)
            packs.append(pp.pack_type_of(payload, layout))
            if layout != pp.LAYOUT_STANDARD:
                rows.append({}); status.append("unparsed_layout"); errors.append(None)
                continue
            row, snap = pp.parse_battery(payload)
            if row.pop("has_bpa_sno_root") != (packs[-1] == "4-cell"):
                sig_mismatch += 1
            rows.append(row); status.append("parsed"); errors.append(None)
            for r in snap:
                r.update(k)
                snaps.append(r)
        except (ValueError, KeyError, TypeError, IndexError, AttributeError, pp.ParseError) as e:
            if len(layouts) < len(hashes):
                layouts.append(None)
            if len(packs) < len(hashes):
                packs.append(None)
            rows.append({}); status.append("error"); errors.append("%s: %s" % (type(e).__name__, e))
    out = common_payload_meta(raw, casts, "battery")
    out = add_event_ts(out, cutoff)
    out["session_id"] = casts.int(raw["session_id"], "battery.session_id")
    out["log_type"] = raw["log_type"]
    out["log_id"] = casts.int(raw["log_id"], "battery.log_id")
    out["payload_layout"] = layouts
    out["pack_type"] = packs
    out["payload_hash"] = hashes
    out["parse_status"] = status
    out["parse_error"] = errors
    parsed = parsed_frame(rows, parsed_column_dtypes_battery(), raw.index)
    out = pd.concat([out, parsed], axis=1)

    snap_cols = (["source_file", "source_row", "cohort", "anonymized_serial", "record_kind", "record_index"]
                 + [c for c, _ in fm.SNAPSHOT_SCALARS]
                 + ["temp_n", "temp_1_raw", "temp_2_raw", "temp_3_raw", "n_cells", "cell_volt_min_raw",
                    "cell_volt_max_raw", "cell_volt_spread_raw"])
    sn = pd.DataFrame(snaps, columns=snap_cols)
    for c in snap_cols[6:]:
        sn[c] = sn[c].astype("Int64")
    sn["record_index"] = sn["record_index"].astype("Int64")
    sn["source_row"] = sn["source_row"].astype("int64")
    return out, sn, sig_mismatch


# ---------------------------------------------------------------------------
# Machine lookup
# ---------------------------------------------------------------------------


def _uniq(s):
    return sorted(set(s.dropna().astype(str)))


def build_machine_lookup(tables):
    sess, faults, motor, batt = tables["clean_sessions"], tables["faults"], tables["motor"], tables["battery"]
    long = pd.concat([
        sess[["anonymized_serial", "cohort", "model", "region"]].assign(table="clean_sessions"),
        faults[["anonymized_serial", "cohort", "model", "region"]].assign(table="faults"),
        motor[["anonymized_serial", "cohort", "region", "country"]].assign(table="motor"),
        batt[["anonymized_serial", "cohort", "pack_type"]].assign(table="battery"),
    ], ignore_index=True, sort=False)
    parsed_serials = set(batt.loc[batt["parse_status"] == "parsed", "anonymized_serial"])
    recs = []
    for serial, g in long.groupby("anonymized_serial"):
        rec = {"anonymized_serial": serial, "cohort": "|".join(_uniq(g["cohort"]))}
        for col, name in (("model", "models"), ("region", "regions"), ("country", "countries"),
                          ("pack_type", "pack_types")):
            u = _uniq(g[col]) if col in g else []
            single = name[:-1] if name != "countries" else "country"
            rec[single] = u[0] if len(u) == 1 else None
            rec["n_" + name] = len(u)
            rec[name + "_all"] = "|".join(u) if u else None
        present = set(g["table"])
        for t in ("clean_sessions", "faults", "motor", "battery"):
            rec["in_" + t] = t in present
        rec["battery_has_parsed_payload"] = serial in parsed_serials
        recs.append(rec)
    return pd.DataFrame(recs)


def lookup_checks(lk):
    rows = []

    def add(check, cohort, table, n, detail=""):
        rows.append({"check": check, "cohort": cohort, "table": table, "n_serials": n, "detail": detail})

    add("serials_in_more_than_one_cohort", "all", "all", int((lk["cohort"].str.contains(r"\|")).sum()))
    for cohort, g in lk.groupby("cohort"):
        add("serials_total", cohort, "all", len(g))
        for t in ("clean_sessions", "faults", "motor", "battery"):
            add("serials_in_table", cohort, t, int(g["in_" + t].sum()))
        for t in ("faults", "motor", "battery"):
            add("serials_in_table_not_in_clean_sessions", cohort, t, int((g["in_" + t] & ~g["in_clean_sessions"]).sum()))
            add("serials_in_clean_sessions_not_in_table", cohort, t, int((g["in_clean_sessions"] & ~g["in_" + t]).sum()))
        add("battery_serials_without_parsed_payload", cohort, "battery",
            int((g["in_battery"] & ~g["battery_has_parsed_payload"]).sum()))
        for n_col, label, all_col in (("n_models", "model", "models_all"), ("n_regions", "region", "regions_all"),
                                      ("n_countries", "country", "countries_all"),
                                      ("n_pack_types", "pack_type", "pack_types_all")):
            multi = g[g[n_col] > 1]
            detail = "; ".join("%s: %s" % (r.anonymized_serial[:10], r[all_col]) for _, r in multi.head(30).iterrows())
            add("serials_with_more_than_one_" + label, cohort, "all", len(multi), detail)
        pat = g[["in_clean_sessions", "in_faults", "in_motor", "in_battery"]].astype(int).astype(str).agg("".join, axis=1)
        for p, n in pat.value_counts().sort_index().items():
            add("presence_pattern_sessions_faults_motor_battery", cohort, "all", int(n), "pattern=%s" % p)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    casts = Casts()
    failures = []

    raw_sess, sess, lost_s = build_typed("clean_sessions", SESSION_SPEC, casts)
    raw_fault, faults, lost_f = build_typed("faults", FAULT_SPEC, casts)
    raw_motor, raw_batt = read_raw("motor"), read_raw("battery")

    # Event-time cut-off: the latest server_timestamp in the raw motor and battery files (both cohorts).
    srv = [pd.to_datetime(r["server_timestamp"].str.replace(" UTC", "", regex=False), errors="coerce")
           for r in (raw_motor, raw_batt)]
    cutoff = max(s.max() for s in srv)
    print("event_ts cut-off (latest raw server_timestamp, motor + battery): %s" % cutoff)

    motor = build_motor(raw_motor, casts, cutoff)
    battery, snaps, sig_mismatch = build_battery(raw_batt, casts, cutoff)
    n_recon, mism = reconcile_motor(raw_motor, motor)
    total_mism = sum(mism.values())

    tables = {"clean_sessions": sess, "faults": faults, "motor": motor, "battery": battery}
    raws = {"clean_sessions": raw_sess, "faults": raw_fault, "motor": raw_motor, "battery": raw_batt}
    rows_out = {t: write_parquet(df, t) for t, df in tables.items()}
    n_snap = write_parquet(snaps, "battery_event_snapshots")
    lookup = build_machine_lookup(tables)
    write_parquet(lookup, "machine_lookup")
    lookup_checks(lookup).to_csv(str(REPORT_DIR / "machine_lookup_checks.csv"), index=False)
    pd.DataFrame(fm.column_dictionary()).to_csv(str(REPORT_DIR / "clean_column_dictionary.csv"), index=False)

    # ---- parse_summary.csv ----
    summary = []
    lost_by_table = {"clean_sessions": lost_s, "faults": lost_f}
    for t, df in tables.items():
        raw = raws[t]
        for cohort in ("normal", "return_repair", "all"):
            m = (raw["cohort"] == cohort).values if cohort != "all" else np.ones(len(raw), bool)
            d = df[m]
            row = {"table": t, "cohort": cohort, "raw_rows_in": int(m.sum()), "rows_out": int(len(d)),
                   "rows_equal": int(m.sum()) == int(len(d))}
            if cohort == "all":
                row["rows_out"] = rows_out[t]  # read back from the Parquet file
                row["rows_equal"] = int(m.sum()) == rows_out[t]
            for st in ("parsed", "empty_payload", "unparsed_layout", "error"):
                row[st] = int((d["parse_status"] == st).sum()) if "parse_status" in d else None
            nulled = sum(v for k, v in casts.nulled.items() if k.startswith(t + "."))
            row["cast_nulls_introduced"] = nulled if cohort == "all" else None
            if t in lost_by_table:
                row["reconciliation"] = ("non-null count of every raw column preserved" if not lost_by_table[t]
                                         else "NON-NULL COUNTS CHANGED: %s" % lost_by_table[t])
            elif t == "motor":
                if cohort == "normal":
                    row["reconciliation"] = ("%d rows x %d columns compared with the flattened Normal columns; "
                                             "mismatches: %d" % (n_recon, len(mism), total_mism))
                elif cohort == "return_repair":
                    row["reconciliation"] = ("no flattened columns to compare; same parser as Normal. "
                                             "runtime_s = sum(PowerBins) is [assumed] to be the runtime")
                else:
                    row["reconciliation"] = "see cohort rows"
            else:
                if cohort in SPEC_BATTERY_COUNTS:
                    exp = SPEC_BATTERY_COUNTS[cohort]
                    got = {k: row[k] for k in exp}
                    row["reconciliation"] = ("counts equal docs/parsing_spec.md: %s" % ("yes" if got == exp
                                             else "NO (expected %s, got %s)" % (exp, got)))
                else:
                    row["reconciliation"] = "pack_type vs root-key signature mismatches: %d" % sig_mismatch
            summary.append(row)
    sm = pd.DataFrame(summary)
    notes = pd.DataFrame([
        {"table": "battery_event_snapshots", "cohort": "all", "raw_rows_in": None, "rows_out": n_snap,
         "reconciliation": "%d records = 17 per parsed battery payload (15 events + 2 faults): %s"
         % (n_snap, "yes" if n_snap == 17 * int((battery["parse_status"] == "parsed").sum()) else "NO")},
        {"table": "machine_lookup", "cohort": "all", "rows_out": len(lookup), "reconciliation": "one row per serial"},
    ])
    sm = pd.concat([sm, notes], ignore_index=True, sort=False)
    sm.to_csv(str(REPORT_DIR / "parse_summary.csv"), index=False)

    # ---- console report ----
    pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 80)
    print(sm.drop(columns=["reconciliation"]).to_string(index=False))
    print(sm[["table", "cohort", "reconciliation"]].to_string(index=False))
    print("cast nulls by column:", casts.nulled or "none")
    print("ts fallback rows: motor %d, battery %d" % (int(motor["ts_fallback_flag"].sum()),
                                                      int(battery["ts_fallback_flag"].sum())))
    print("battery errors:", battery.loc[battery["parse_status"] == "error", "parse_error"].value_counts().to_dict())
    print("motor errors:", motor.loc[motor["parse_status"] == "error", "parse_error"].value_counts().to_dict())

    # ---- fail loudly ----
    if total_mism:
        failures.append("motor reconciliation: %s" % {k: v for k, v in mism.items() if v})
    if not sm["rows_equal"].dropna().all():
        failures.append("row counts differ between raw and output")
    bad = sm[sm["reconciliation"].fillna("").str.contains("NO \\(expected|NON-NULL|: NO$")]
    if len(bad):
        failures.append("reconciliation failed: %s" % bad[["table", "cohort"]].values.tolist())
    if casts.nulled:
        failures.append("values nulled by casting: %s" % casts.nulled)
    if sig_mismatch:
        failures.append("pack_type disagrees with the root-key signature in %d rows" % sig_mismatch)
    if failures:
        print("\nFAILED:\n  " + "\n  ".join(failures), file=sys.stderr)
        sys.exit(1)
    print("\nOK: all row counts equal; motor reconciliation has 0 mismatches.")


if __name__ == "__main__":
    main()
