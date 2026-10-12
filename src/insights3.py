"""Step 12: candidate insight round (fixed list, in order, with the existing methods).

Appends new rows (ids prefixed `n_`) to reports/insights/key_numbers.csv at text level, so every
existing row stays byte-for-byte unchanged, and writes the detail tables:
  reports/insights/n_candidate_verdicts.csv      one row per candidate with verdict and rule
  reports/insights/n_window_sensitivity.csv      candidate 2, all window variants by group
  reports/insights/n_dust_within_machine.csv     candidate 3, per dust column and cohort
  reports/insights/n_motor_correlations.csv      candidate 4
  reports/insights/n_battery_temp_state_counts.csv  candidate 5, full breakdown
Run order: src/insights.py (rewrites key_numbers.csv without n_ rows), then this script.
Reads data/model/, data/clean/ and (candidate 4 only) the raw motor files, read-only.
Methods (project decisions): machine is the unit; pooled rates or within-machine comparisons;
95% percentile bootstrap, 2,000 machine resamples, fixed seed; Normal vs RR comparisons are SV53 only;
no causal claims. Python 3.8 compatible.
"""
import csv
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eda_helpers as h  # noqa: E402
import insights as ins  # noqa: E402
import insights2 as i2  # noqa: E402

ROOT = h.ROOT
OUT = ROOT / "reports" / "insights"
KEY = OUT / "key_numbers.csv"
N_BOOT, SEED = h.N_BOOT, h.SEED
SRC = "src/insights3.py"
GROUPS = i2.GROUPS
GLABEL, GKEY = i2.GLABEL, i2.GKEY
WINDOW_MAIN, WINDOW_ALT, LAG_H = 7, 30, 1.0       # days, days, hours (lagged-start variant)
DAY = np.timedelta64(1, "D")
MIN_IN_DAYS, MIN_OUT_DAYS = 1.0, 14.0     # minimum exposure inside / outside the windows for a machine to enter (rates on a few hours of exposure explode)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def boot_diff_share(a, b, num, den, scale=100.0):
    """Pooled share of a minus pooled share of b, with machine bootstrap of both groups."""
    ia, ib = i2.boot_idx(len(a), seed=SEED), i2.boot_idx(len(b), seed=SEED + 1)
    ra = scale * a[num].values[ia].sum(axis=1) / a[den].values[ia].sum(axis=1)
    rb = scale * b[num].values[ib].sum(axis=1) / b[den].values[ib].sum(axis=1)
    v = scale * a[num].sum() / a[den].sum() - scale * b[num].sum() / b[den].sum()
    lo, hi = np.percentile(ra - rb, [2.5, 97.5])
    return float(v), float(lo), float(hi)


def boot_stat(values, stat, n_boot=N_BOOT, seed=SEED):
    v = np.asarray(values, dtype=float)
    idx = np.random.RandomState(seed).randint(0, len(v), size=(n_boot, len(v)))
    b = stat(v[idx], axis=1)
    lo, hi = np.percentile(b, [2.5, 97.5])
    return float(stat(v)), float(lo), float(hi)


def spearman(x, y):
    return float(pd.Series(x).rank().corr(pd.Series(y).rank()))


def spearman_ci(x, y, n_boot=N_BOOT, seed=SEED):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    rng = np.random.RandomState(seed)
    out = []
    for _ in range(n_boot):
        i = rng.randint(0, len(x), len(x))
        r = spearman(x[i], y[i])
        if np.isfinite(r):
            out.append(r)
    lo, hi = np.percentile(out, [2.5, 97.5])
    return spearman(x, y), float(lo), float(hi)


def excludes_zero(lo, hi, null=0.0):
    return (lo > null) or (hi < null)


# ---------------------------------------------------------------------------
# candidate 0: facts
# ---------------------------------------------------------------------------
def cand0(T, K):
    dim = T["dim"]
    con = duckdb.connect()
    cl = i2.CLEAN
    fr = con.execute("SELECT cohort, fault_type, fault_value, count(*) raw_rows, sum(is_analysis_row::int) analysis_rows "
                     "FROM read_parquet('%s') GROUP BY ALL ORDER BY ALL" % (cl / "dq" / "faults.parquet")).df()
    raw_total = int(fr.raw_rows.sum())
    zero_rows = int(fr[fr.fault_value == 0].raw_rows.sum())
    nulls = con.execute("SELECT sum((fault_type IS NULL)::int), sum((fault_value IS NULL)::int) FROM read_parquet('%s')" % (cl / "dq" / "faults.parquet")).fetchone()
    K.add("n_f0_fault_rows_raw", "N0 facts", "raw fault rows (both cohorts)", "all", raw_total, n_events=raw_total, unit="rows", src=SRC + ":cand0")
    K.add("n_f0_value0_rows", "N0 facts", "raw fault rows with fault_value = 0 (12/0, 13/0, 11/0)", "all", zero_rows, n_events=zero_rows, den=raw_total, den_unit="raw fault rows", unit="rows", src=SRC + ":cand0",
          note="none exist: the faults table holds only non-zero events, so 'not blocked' / 'OK' is never recorded; absence is read as no fault [assumed]; null type/value rows: %d / %d" % (nulls[0], nulls[1]))
    for _, r in fr.iterrows():
        g = "%s_%d_%d" % (r.cohort, r.fault_type, r.fault_value)
        K.add("n_f0_raw_%s" % g, "N0 facts", "raw fault rows by type/value", "%s %d/%d" % (r.cohort, r.fault_type, r.fault_value), int(r.raw_rows), n_events=int(r.raw_rows), unit="rows", src=SRC + ":cand0")
        K.add("n_f0_analysis_%s" % g, "N0 facts", "analysis fault rows (occurrences) by type/value", "%s %d/%d" % (r.cohort, r.fault_type, r.fault_value), int(r.analysis_rows), n_events=int(r.analysis_rows), unit="occurrences",
              src=SRC + ":cand0", note="analysis row = distinct occurrence after exact-copy and re-upload removal (src/dq.py)")
    # model mix of all RR machines
    rr = dim[dim.cohort == "return_repair"]
    mixrr = rr.model.fillna("(no model)").value_counts().sort_index()
    for m, n in mixrr.items():
        K.add("n_f0_rr_mix_%s" % m.replace("-", "_").replace("(", "").replace(")", "").replace(" ", "_"), "N0 facts", "model mix of all Return/Repair machines", m, int(n), n_machines=int(n), unit="machines", src=SRC + ":cand0")
    K.add("n_f0_rr_machines", "N0 facts", "Return/Repair machines in dim_machine", "return_repair", len(rr), n_machines=len(rr), unit="machines", src=SRC + ":cand0")
    # motor machines: dim model, else SV53 label from the motor_model_raw, else the raw motor code
    allm = duckdb.connect().execute("SELECT cohort, anonymized_serial, motor_model_raw FROM read_parquet('%s')" % (cl / "motor.parquet")).df()
    ms = dim[dim.has_motor_rows.fillna(False).astype(bool)].copy()
    raw_codes = allm.groupby("anonymized_serial").motor_model_raw.agg(lambda s: ",".join(sorted(set(s.dropna()))))
    ms["motor_raw"] = ms.anonymized_serial.map(raw_codes)
    ms["mix_label"] = np.where(ms.model.notna() & (ms.model != ""), ms.model, "(no model; motor label " + ms.motor_raw.fillna("") + ")")
    for (c, lab), d in ms.groupby(["cohort", "mix_label"]):
        K.add("n_f0_motor_mix_%s_%s" % (c, lab.replace("-", "_").replace("(", "").replace(")", "").replace(" ", "_").replace(";", "").replace(",", "_")), "N0 facts",
              "model mix of machines with motor rows (dim_machine model; else motor label)", "%s %s" % (c, lab), len(d), n_machines=len(d), unit="machines", src=SRC + ":cand0")
    K.add("n_f0_motor_machines", "N0 facts", "machines with motor rows", "both cohorts", len(ms), n_machines=len(ms), unit="machines", src=SRC + ":cand0",
          note="motor_model_raw holds the motor generation code 683 for 3 RR machines and 692B for 1 on some rows, mixed with SV53 labels; 9 Normal machines have no model in sessions or faults but an SV53 sub-model label in the motor file")
    n_motor_other = int((ms.motor_raw.str.contains("683|692B", regex=True)).sum())
    K.add("n_f0_motor_code_machines", "N0 facts", "machines whose motor_model_raw includes a motor code (683 or 692B) on any row", "return_repair", n_motor_other, n_machines=n_motor_other, unit="machines", src=SRC + ":cand0")
    return fr, ms


# ---------------------------------------------------------------------------
# candidate 1: severity mix
# ---------------------------------------------------------------------------
def cand1(T, K):
    e = T["summ"][T["summ"].rate_eligible].copy()
    e["n12"] = e.n_faults_t12_v1_primary + e.n_faults_t12_v2_primary
    e["n122"] = e.n_faults_t12_v2_primary
    sets = {}
    for (c, fam) in GROUPS:
        d = e[(e.cohort == c) & (e.family == fam) & (e.n12 > 0)]
        sets[(c, fam)] = d
        i2.add_rate(K, "n_sev_share122_%s" % GKEY[(c, fam)], "N1 severity", "share of type-12 faults that are 12/2 (inlet blocked and in error), %", GLABEL[(c, fam)], d, "n122", "n12", "%",
                    den_unit="type-12 occurrences", note="pooled over rate-eligible machines with at least one type-12 occurrence; the rest are 12/1 (still running); 12/3 never occurs")
    out = {}
    for key, a, b, lab in (("rr_minus_normal_SV53", sets[("return_repair", "SV53")], sets[("normal", "SV53")], "RR SV53 minus Normal SV53"),
                           ("sv53_minus_sv50_normal", sets[("normal", "SV53")], sets[("normal", "SV50")], "Normal SV53 minus Normal SV50")):
        v, lo, hi = boot_diff_share(a, b, "n122", "n12")
        K.add("n_sev_diff_%s" % key, "N1 severity", "difference in the 12/2 share of type-12 faults, percentage points", lab, v, lo, hi, n_machines=len(a) + len(b),
              n_events=float(a.n122.sum() + b.n122.sum()), unit="percentage points", src=SRC + ":cand1")
        out[key] = (v, lo, hi)
    # sensitivity: machines with >= 5 type-12 occurrences (limits the weight of machines with one or two events)
    for (c, fam), d in sets.items():
        dd = d[d.n12 >= 5]
        if len(dd) >= 5:
            i2.add_rate(K, "n_sev_share122_min5_%s" % GKEY[(c, fam)], "N1 severity", "same share, machines with >= 5 type-12 occurrences, %", GLABEL[(c, fam)], dd, "n122", "n12", "%", den_unit="type-12 occurrences")
    return out


# ---------------------------------------------------------------------------
# candidate 2: filter reminder (13/1) then blockage (type 12), faults table only
# ---------------------------------------------------------------------------
def episodes(ts, gap=pd.Timedelta(hours=1)):
    """Start time of each episode: events of one kind closer than `gap` to the previous event are one episode."""
    ts = np.sort(np.asarray(ts, dtype="datetime64[ns]"))
    if len(ts) == 0:
        return ts
    keep = np.concatenate([[True], np.diff(ts) > np.timedelta64(int(gap.total_seconds()), "s")])
    return ts[keep]


def union_length_and_count(starts, ends, events, span_a, span_b):
    """Merged windows [start, end] clipped to the span: total days and number of events inside."""
    iv = sorted((max(s, span_a), min(e, span_b)) for s, e in zip(starts, ends) if min(e, span_b) > max(s, span_a))
    merged = []
    for s, e in iv:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    days = sum((e - s) / DAY for s, e in merged)
    n = 0
    if len(events):
        for s, e in merged:
            n += int(((events >= s) & (events <= e)).sum())
    return float(days), n, merged


def window_table(ff, summ, window_days, lag_h=0.0, span_source="faults", sess=None):
    """One row per machine (>= 1 filter-reminder 13/1, rate-eligible) with in-window and out-of-window type-12 episode rates."""
    elig = summ[summ.rate_eligible].set_index("anonymized_serial")
    rows, strata = [], []
    for ser, d in ff[ff.anonymized_serial.isin(elig.index)].groupby("anonymized_serial"):
        trig = episodes(d.loc[(d.fault_type == 13) & (d.fault_value == 1), "fault_timestamp"])
        if len(trig) == 0:
            continue
        blk = episodes(d.loc[d.fault_type == 12, "fault_timestamp"])
        if span_source == "faults":
            a, b = d.fault_timestamp.min().to_datetime64(), d.fault_timestamp.max().to_datetime64()
        else:
            ss = sess[sess.anonymized_serial == ser].date_server
            a, b = min(ss.min(), d.fault_timestamp.min()).to_datetime64(), max(ss.max(), d.fault_timestamp.max()).to_datetime64()
        blk_in_span = blk[(blk >= a) & (blk <= b)]
        starts = trig + np.timedelta64(int(lag_h * 3600), "s")
        ends = trig + np.timedelta64(int(lag_h * 3600), "s") + np.timedelta64(int(window_days * 86400), "s")
        in_days, in_n, merged = union_length_and_count(starts, ends, blk_in_span, a, b)
        total_days = float((b - a) / DAY)
        out_days, out_n = total_days - in_days, len(blk_in_span) - in_n
        if in_days < MIN_IN_DAYS or out_days < MIN_OUT_DAYS:
            continue
        edges = pd.date_range(pd.Timestamp(a).normalize().replace(day=1), pd.Timestamp(b) + pd.offsets.MonthBegin(1), freq="MS")
        for m0, m1 in zip(edges[:-1], edges[1:]):
            lo_, hi_ = max(m0.to_datetime64(), a), min(m1.to_datetime64(), b)
            if hi_ <= lo_:
                continue
            ov = sum(max(0.0, float((min(e, hi_) - max(s_, lo_)) / DAY)) for s_, e in merged)
            n_in = sum(int(((blk_in_span >= max(s_, lo_)) & (blk_in_span <= min(e, hi_))).sum()) for s_, e in merged if min(e, hi_) > max(s_, lo_))
            n_tot = int(((blk_in_span >= lo_) & (blk_in_span <= hi_)).sum())
            strata.append(dict(anonymized_serial=ser, in_n=n_in, in_days=ov, out_n=n_tot - n_in, out_days=float((hi_ - lo_) / DAY) - ov))
        rows.append(dict(anonymized_serial=ser, cohort=elig.loc[ser, "cohort"], family=elig.loc[ser, "family"], n_trig=len(trig), in_days=in_days, out_days=out_days, in_n=in_n, out_n=out_n,
                         in_rate=100.0 * in_n / in_days, out_rate=100.0 * out_n / out_days))
    t = pd.DataFrame(rows)
    t["d"] = t.in_rate - t.out_rate
    t.attrs["strata"] = pd.DataFrame(strata)
    return t


def mh_strata(st):
    """Rate ratio inside vs outside windows, Mantel-Haenszel over strata = machine x calendar month, bootstrap over machines."""
    st = st.copy()
    st["T"] = st.in_days + st.out_days
    st = st[st["T"] > 0]
    grp = {k: g[["in_n", "in_days", "out_n", "out_days", "T"]].values.astype(float) for k, g in st.groupby("anonymized_serial")}
    keys = list(grp)

    def mh(sel):
        v = np.vstack([grp[k] for k in sel])
        num = (v[:, 0] * v[:, 3] / v[:, 4]).sum()
        den = (v[:, 2] * v[:, 1] / v[:, 4]).sum()
        return num / den if den > 0 else np.nan
    r0 = mh(keys)
    rng = np.random.RandomState(SEED)
    b = np.array([mh([keys[i] for i in rng.randint(0, len(keys), len(keys))]) for _ in range(N_BOOT)])
    b = b[np.isfinite(b)]
    return float(r0), (float(np.percentile(b, 2.5)) if len(b) else np.nan), (float(np.percentile(b, 97.5)) if len(b) else np.nan)


def summarize_window(t):
    """Mean paired difference (per 100 days) with machine bootstrap, median, share of machines higher, pooled ratio with bootstrap."""
    m, lo, hi = boot_stat(t.d.values, lambda x, axis=None: np.mean(x, axis=axis))
    med = float(np.median(t.d))
    pos, neg = int((t.d > 0).sum()), int((t.d < 0).sum())
    # Mantel-Haenszel rate ratio, strata = machines (stable when exposure differs a lot between machines)
    ni, di, no, do = t.in_n.values.astype(float), t.in_days.values, t.out_n.values.astype(float), t.out_days.values
    T = di + do

    def mh(ix):
        den = (no[ix] * di[ix] / T[ix]).sum()
        return (ni[ix] * do[ix] / T[ix]).sum() / den if den > 0 else np.nan
    ratio = mh(np.arange(len(t)))
    idx = np.random.RandomState(SEED).randint(0, len(t), size=(N_BOOT, len(t)))
    rb = np.array([mh(i) for i in idx])
    rb = rb[np.isfinite(rb)]
    rlo, rhi = (np.percentile(rb, [2.5, 97.5]) if len(rb) else (np.nan, np.nan))
    st = t.attrs["strata"]
    st = st[st.anonymized_serial.isin(t.anonymized_serial)]
    adj, alo, ahi = mh_strata(st)
    return dict(n_machines=len(t), adj_ratio=adj, adj_lo=alo, adj_hi=ahi, mean_diff=m, lo=lo, hi=hi, median_diff=med, n_higher=pos, n_lower=neg, ratio=float(ratio), ratio_lo=float(rlo), ratio_hi=float(rhi),
                events_in=int(t.in_n.sum()), events_out=int(t.out_n.sum()), days_in=float(t.in_days.sum()), days_out=float(t.out_days.sum()))


def cand2(T, K):
    ff, summ, sess = T["ff"], T["summ"], T["sess"]
    variants = [("main_7d", WINDOW_MAIN, 0.0, "faults"), ("alt_30d", WINDOW_ALT, 0.0, "faults"), ("lag1h_7d", WINDOW_MAIN, LAG_H, "faults"), ("sessionspan_7d", WINDOW_MAIN, 0.0, "sessions"), ("sessionspan_30d", WINDOW_ALT, 0.0, "sessions"), ("sessionspan_lag1h_7d", WINDOW_MAIN, LAG_H, "sessions")]
    rows = []
    for vname, w, lag, span in variants:
        t = window_table(ff, summ, w, lag, span, sess)
        for (c, fam) in GROUPS:
            d = t[(t.cohort == c) & (t.family == fam)]
            if len(d) < 5:
                continue
            s = summarize_window(d)
            s.update(variant=vname, group=GLABEL[(c, fam)], key=GKEY[(c, fam)], window_days=w, lag_h=lag, span=span)
            rows.append(s)
            if True:
                K.add("n_win_%s_%s" % (vname, GKEY[(c, fam)]), "N2 reminder then blockage",
                      "within-machine difference in type-12 episodes per 100 days, in the %d days%s after a 13/1 minus outside those windows%s" % (w, " (starting 1 h later)" if lag else "", " [exposure span from sessions table]" if span == "sessions" else " [span = first to last fault]"),
                      GLABEL[(c, fam)], s["mean_diff"], s["lo"], s["hi"], n_machines=s["n_machines"], n_events=s["events_in"] + s["events_out"], unit="episodes per 100 days",
                      src=SRC + ":cand2", note="unit = type-12 episode (events less than 1 h apart merged); window and span from fault_timestamp (device time, inferred); machines with >= 1 13/1, >= 1 day inside and >= 14 days outside the windows; "
                      "%d machines higher, %d lower inside windows; Mantel-Haenszel rate ratio %.2f [%.2f to %.2f]; time-adjusted (strata machine x calendar month) %.2f [%.2f to %.2f]" % (s["n_higher"], s["n_lower"], s["ratio"], s["ratio_lo"], s["ratio_hi"], s["adj_ratio"], s["adj_lo"], s["adj_hi"]))
    res = pd.DataFrame(rows)
    res.to_csv(str(OUT / "n_window_sensitivity.csv"), index=False, float_format="%.6g")
    return res


# ---------------------------------------------------------------------------
# candidate 3: dust within machine
# ---------------------------------------------------------------------------
DUST = [("ultra_fine", "ultra_fine_dust_particle_mass_clean"), ("fine", "fine_dust_particle_mass_clean"), ("coarse", "coarse_dust_particle_mass_clean"), ("large", "large_dust_particle_mass_clean")]


def cand3(T, S, K):
    s53 = S[S.family == "SV53"].copy()
    rows = []
    for c in ("normal", "return_repair"):
        d = s53[s53.cohort == c]
        n_mach_block = d[d.f12 == 1].anonymized_serial.nunique()
        K.add("n_dust_block_machines_%s" % c, "N3 dust", "SV53 machines with at least one blockage session (linked)", c, n_mach_block, n_machines=n_mach_block, n_events=int((d.f12 == 1).sum()), unit="machines", src=SRC + ":cand3")
        for nm, col in DUST:
            v = d[d[col].notna()]
            has = v.groupby("anonymized_serial").f12.agg(["min", "max"])
            both = has[(has["min"] == 0) & (has["max"] == 1)].index
            med = v[v.anonymized_serial.isin(both)].groupby(["anonymized_serial", "f12"])[col].median().unstack()
            med = med.rename(columns={0: "nb", 1: "b"})
            use = med[med.nb > 0].copy()
            use["rel"] = (use.b - use.nb) / use.nb
            r = dict(cohort=c, dust=nm, machines_both=len(both), machines_usable=len(use), median_rel_diff=np.nan, lo=np.nan, hi=np.nan, share_higher=np.nan, n_blockage_sessions=int(v[v.f12 == 1].shape[0]))
            if len(use) >= 5:
                m, lo, hi = boot_stat(use.rel.values, lambda x, axis=None: np.median(x, axis=axis))
                r.update(median_rel_diff=m * 100, lo=lo * 100, hi=hi * 100, share_higher=float((use.rel > 0).mean() * 100), n_higher=int((use.rel > 0).sum()), n_lower=int((use.rel < 0).sum()))
                K.add("n_dust_rel_%s_%s" % (nm, c), "N3 dust", "median across machines of (median dust in blockage sessions minus median in other sessions) / median in other sessions, %",
                      "%s, %s dust" % (GLABEL[(c, "SV53")], nm.replace("_", "-")), m * 100, lo * 100, hi * 100, n_machines=len(use), n_events=r["n_blockage_sessions"], unit="% relative difference", src=SRC + ":cand3",
                      note="paired within machine; machines with both session kinds and a non-zero comparison median; dust unit not stated, 65535 treated as missing; cohorts not compared; %d of %d machines higher in blockage sessions" % (r["n_higher"], len(use)))
            rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(str(OUT / "n_dust_within_machine.csv"), index=False, float_format="%.6g")
    return res


# ---------------------------------------------------------------------------
# candidate 4: motor pressure / exhaust temperature vs blockage (SV53)
# ---------------------------------------------------------------------------
def read_raw_payload_bins(rows):
    """rows: DataFrame[source_file, source_row, anonymized_serial]. Returns pressure and exhaust bin arrays per row, read from the raw motor files."""
    csv.field_size_limit(10 ** 9)
    out = {}
    for sf, grp in rows.groupby("source_file"):
        want = dict(zip(grp.source_row, grp.index))
        with open(str(ROOT / sf), newline="") as f:
            rd = csv.DictReader(f)
            for i, r in enumerate(rd):
                if i in want:
                    u = json.loads(r["decoded_data"])["ddmUsage"]
                    out[want[i]] = (u["ddm692_PressureBins"]["bins"], u["ddm692_ExhaustTempBins"]["bins"])
    return out


def motor_shares(T):
    con = duckdb.connect()
    m = con.execute("SELECT source_file, source_row, cohort, anonymized_serial, event_ts FROM read_parquet('%s') WHERE is_analysis_row" % (i2.CLEAN / "dq" / "motor.parquet")).df()
    m = m.sort_values(["anonymized_serial", "event_ts", "source_row"]).groupby("anonymized_serial").tail(1).reset_index(drop=True)
    bins = read_raw_payload_bins(m[["source_file", "source_row"]])
    rows = []
    for i, r in m.iterrows():
        p, e = bins[i]
        p, e = np.array(p, dtype=float), np.array(e, dtype=float)
        rows.append(dict(anonymized_serial=r.anonymized_serial, press_ge100=p[7:].sum() / p.sum() if p.sum() > 0 else np.nan, press_ge95=p[6:].sum() / p.sum() if p.sum() > 0 else np.nan,
                         exh_ge50=e[5:].sum() / e.sum() if e.sum() > 0 else np.nan, exh_ge40=e[4:].sum() / e.sum() if e.sum() > 0 else np.nan, exh_bins8_10_nonzero=bool(e[7:].sum() > 0)))
    sh = pd.DataFrame(rows)
    e = T["summ"][T["summ"].rate_eligible & (T["summ"].family == "SV53")].copy()
    e["rate12"] = (e.n_faults_t12_v1_primary + e.n_faults_t12_v2_primary) * 100.0 / e.n_sessions
    return e[["anonymized_serial", "cohort", "rate12", "n_sessions"]].merge(sh, on="anonymized_serial", how="inner")


def cand4(T, K):
    d = motor_shares(T)
    assert not d.exh_bins8_10_nonzero.any(), "exhaust bins 8-10 are expected to be zero (docs/parsing_spec.md)"
    metrics = [("press_ge100", "runtime share in pressure array bins >= 100 kPa (top 2 of 9)"), ("press_ge95", "runtime share in pressure array bins >= 95 kPa (sensitivity)"),
               ("exh_ge50", "runtime share in exhaust-temperature bins >= 50 C (top bins present in both cohorts)"), ("exh_ge40", "runtime share in exhaust-temperature bins >= 40 C (sensitivity)")]
    meta = ("pressure array = payload ddm692_PressureBins, matched to DDM_Bins.json ddm692_PressBins by an inferred alias (dimension named 'speed' but unit kilo-pascal, edges 70-105); its time is concentrated near "
            "ambient pressure (docs/parsing_spec.md), so it may describe ambient pressure and not suction pressure [interpretation]; exhaust bins 8-10 are zero in both cohorts; shares from each machine's latest snapshot (lifetime counters)")
    rows = []
    for key, lab in metrics:
        for scope, sub in (("Normal SV53", d[d.cohort == "normal"]), ("RR SV53", d[d.cohort == "return_repair"]), ("SV53 both cohorts (not a comparison)", d)):
            s = sub.dropna(subset=[key, "rate12"])
            if len(s) < 8:
                continue
            r, lo, hi = spearman_ci(s[key].values, s.rate12.values)
            rows.append(dict(metric=key, scope=scope, n_machines=len(s), spearman=r, lo=lo, hi=hi))
            if scope != "SV53 both cohorts (not a comparison)":
                gid = "normal" if scope.startswith("Normal") else "return_repair"
                K.add("n_motor_rho_%s_%s" % (key, gid), "N4 motor", "Spearman correlation of machine type-12 rate per 100 sessions with " + lab, scope, r, lo, hi, n_machines=len(s), unit="Spearman rho", src=SRC + ":cand4", note=meta)
        a, b = d[d.cohort == "return_repair"][key].dropna().values, d[d.cohort == "normal"][key].dropna().values
        rng = np.random.RandomState(SEED)
        bs = [np.median(a[rng.randint(0, len(a), len(a))]) - np.median(b[rng.randint(0, len(b), len(b))]) for _ in range(N_BOOT)]
        lo, hi = np.percentile(bs, [2.5, 97.5])
        rows.append(dict(metric=key, scope="RR minus Normal, median share", n_machines=len(a) + len(b), spearman=float(np.median(a) - np.median(b)), lo=float(lo), hi=float(hi)))
        K.add("n_motor_share_diff_%s" % key, "N4 motor", "RR minus Normal, median machine " + lab, "SV53 RR minus Normal", float(np.median(a) - np.median(b)), float(lo), float(hi), n_machines=len(a) + len(b), unit="share (0-1)",
              src=SRC + ":cand4", note=meta + "; medians RR %.3f, Normal %.3f" % (np.median(a), np.median(b)))
    res = pd.DataFrame(rows)
    res.to_csv(str(OUT / "n_motor_correlations.csv"), index=False, float_format="%.6g")
    return res, d


# ---------------------------------------------------------------------------
# candidate 5: battery temperature state counts (data quality only)
# ---------------------------------------------------------------------------
def cand5(T, K):
    sess = T["sess"].copy()
    sess["family"] = sess.family.replace("", "unknown")
    st = sess.groupby(["cohort", "family", "model", "battery_temp_state"]).size().unstack(fill_value=0)
    for c in ("hot", "cold", "ok", "not_reported"):
        if c not in st.columns:
            st[c] = 0
    st = st[["hot", "cold", "ok", "not_reported"]]
    st["sessions"] = st.sum(axis=1)
    st["machines"] = sess.groupby(["cohort", "family", "model"]).anonymized_serial.nunique()
    st["not_reported_pct"] = st.not_reported / st.sessions * 100
    st.reset_index().to_csv(str(OUT / "n_battery_temp_state_counts.csv"), index=False, float_format="%.6g")
    fam = sess.groupby(["cohort", "family", "battery_temp_state"]).size().unstack(fill_value=0)
    for (c, f), r in fam.iterrows():
        tot = int(r.sum())
        for s in ("hot", "cold", "ok", "not_reported"):
            n = int(r.get(s, 0))
            K.add("n_bt_%s_%s_%s" % (s, c, f), "N5 battery temperature state", "sessions by battery_temp_state (hot / cold / ok / not_reported = no flag true)", "%s %s %s" % (c, f, s), n, n_events=n, den=tot, den_unit="analysis sessions",
                  unit="sessions", src=SRC + ":cand5", note="data quality only; the brief gives no meaning for the no-flag state")
    # not_reported % by sub-model (pooled, machine bootstrap)
    sess["nr"] = (sess.battery_temp_state == "not_reported").astype(int)
    for (c, m), d in sess[sess.family.isin(["SV50", "SV53"])].groupby(["cohort", "model"]):
        mt = d.groupby("anonymized_serial").agg(x=("nr", "sum"), n=("nr", "size")).reset_index()
        if len(mt) >= 2:
            i2.add_rate(K, "n_bt_nr_pct_%s_%s" % (c, m.replace("-", "_")), "N5 battery temperature state", "sessions with no temperature flag, % of sessions", "%s %s" % (c, m), mt, "x", "n", "%", den_unit="analysis sessions")
    # firmware: recorded in how many sessions, and not_reported share among them
    con = duckdb.connect()
    con.register("sessions_df", sess[["session_key", "source_file", "source_row", "cohort", "family", "nr"]])
    fw = con.execute("""SELECT s.cohort, s.family, count(*) n_sessions, sum((r.running_firmware_version IS NOT NULL)::int) n_with_firmware,
                               sum(CASE WHEN r.running_firmware_version IS NOT NULL THEN s.nr END) nr_with_firmware
                        FROM sessions_df s JOIN read_parquet('%s') r ON r.source_file = s.source_file AND r.source_row = s.source_row GROUP BY ALL ORDER BY ALL""" % (i2.CLEAN / "clean_sessions.parquet")).df()
    for _, r in fw.iterrows():
        K.add("n_bt_fw_recorded_%s_%s" % (r.cohort, r.family), "N5 battery temperature state", "analysis sessions with running_firmware_version recorded", "%s %s" % (r.cohort, r.family), float(r.n_with_firmware) / r.n_sessions * 100,
              n_events=int(r.n_with_firmware), den=int(r.n_sessions), den_unit="analysis sessions", unit="%", src=SRC + ":cand5",
              note="firmware is too sparse to explain the no-flag state; of sessions with firmware recorded, %s have no temperature flag" % (int(r.nr_with_firmware) if pd.notna(r.nr_with_firmware) else 0))
    # region within SV50 Normal (CN vs ROW) as a further non-cohort check
    sv = sess[(sess.family == "SV50")].merge(T["dim"][["anonymized_serial", "region"]], on="anonymized_serial", how="left")
    for reg, d in sv.groupby("region"):
        mt = d.groupby("anonymized_serial").agg(x=("nr", "sum"), n=("nr", "size")).reset_index()
        if len(mt) >= 5:
            i2.add_rate(K, "n_bt_nr_pct_SV50_%s" % str(reg).replace("-", "_"), "N5 battery temperature state", "SV50 sessions with no temperature flag, % of sessions by region", "SV50 %s" % reg, mt, "x", "n", "%", den_unit="analysis sessions")
    # cohort contrast inside SV53 and family contrast inside Normal
    mtn = lambda c, f: sess[(sess.cohort == c) & (sess.family == f)].groupby("anonymized_serial").agg(x=("nr", "sum"), n=("nr", "size")).reset_index()
    for key, a, b, lab in (("rr_minus_normal_SV53", mtn("return_repair", "SV53"), mtn("normal", "SV53"), "RR SV53 minus Normal SV53 (cohort)"),
                           ("sv50_minus_sv53_normal", mtn("normal", "SV50"), mtn("normal", "SV53"), "Normal SV50 minus Normal SV53 (model)")):
        v, lo, hi = boot_diff_share(a, b, "x", "n")
        K.add("n_bt_nr_diff_%s" % key, "N5 battery temperature state", "difference in the share of sessions with no temperature flag, percentage points", lab, v, lo, hi, n_machines=len(a) + len(b),
              n_events=float(a.x.sum() + b.x.sum()), unit="percentage points", src=SRC + ":cand5")
    return st, fw


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------
def verdict_rule(primary, others=()):
    """primary/others: (estimate, lo, hi). Strong: primary interval excludes 0 and every other variant keeps the sign
    with its interval also excluding 0. Moderate: primary excludes 0, or all variants keep the sign (some intervals touch 0).
    Not supported: otherwise."""
    est, lo, hi = primary
    if excludes_zero(lo, hi):
        if all((np.sign(o[0]) == np.sign(est)) and excludes_zero(o[1], o[2]) for o in others):
            return "Strong"
        return "Moderate"
    if others and all(np.sign(o[0]) == np.sign(est) for o in others) and np.sign(est) != 0:
        return "Moderate"
    return "Not supported"


def compute(T=None):
    T = T or i2.load()
    T["ff"] = i2.link_faults(T["sess"], T["ff"])
    S = i2.session_table(T["sess"], T["ff"])
    K = ins.KeyNumbers()
    fr, ms = cand0(T, K)
    c1 = cand1(T, K)
    c2 = cand2(T, K)
    c3 = cand3(T, S, K)
    c4, mshare = cand4(T, K)
    c5, fw = cand5(T, K)
    return dict(key=K.frame(), c1=c1, c2=c2, c3=c3, c4=c4, c5=c5, fw=fw, fr=fr, ms=ms)


def verdicts(R):
    rows = []
    kk = R["key"].set_index("id")

    def est(id_):
        r = kk.loc[id_]
        return (r.value, r.interval_low, r.interval_high)

    v = verdict_rule(est("n_sev_diff_rr_minus_normal_SV53"))
    rows.append(dict(candidate="1 severity mix: RR SV53 vs Normal SV53 share of 12/2", verdict=v, rule="difference interval excludes 0", detail="%.1f pp [%.1f to %.1f]" % est("n_sev_diff_rr_minus_normal_SV53")))
    v = verdict_rule(est("n_sev_diff_sv53_minus_sv50_normal"))
    rows.append(dict(candidate="1 severity mix: Normal SV53 vs Normal SV50 share of 12/2", verdict=v, rule="difference interval excludes 0", detail="%.1f pp [%.1f to %.1f]" % est("n_sev_diff_sv53_minus_sv50_normal")))
    w = R["c2"]
    for c, fam in GROUPS:
        g = GLABEL[(c, fam)]
        sub = w[w.group == g].set_index("variant")
        for tag, names, label in (("faults span (as specified)", ("main_7d", "alt_30d", "lag1h_7d"), "faults-only span"), ("sessions span (exposure only)", ("sessionspan_7d", "sessionspan_30d", "sessionspan_lag1h_7d"), "exposure from sessions table")):
            if names[0] not in sub.index:
                rows.append(dict(candidate="2 reminder then blockage, %s: %s" % (tag, g), verdict="Not supported", rule="too few qualifying machines", detail="n < 5"))
                continue
            prim = (sub.loc[names[0], "mean_diff"], sub.loc[names[0], "lo"], sub.loc[names[0], "hi"])
            others = [(sub.loc[x, "mean_diff"], sub.loc[x, "lo"], sub.loc[x, "hi"]) for x in names[1:] if x in sub.index]
            vd = verdict_rule(prim, others)
            adj_ok = (sub.loc[names[0], "adj_lo"] > 1) or (sub.loc[names[0], "adj_hi"] < 1)
            if vd == "Strong" and not adj_ok:
                vd = "Moderate"
            rows.append(dict(candidate="2 reminder then blockage, %s: %s" % (tag, g), verdict=vd,
                             rule="7-day interval excludes 0; Strong if the 30-day and 1-hour-lag variants also exclude 0 with the same sign AND the time-adjusted rate ratio (machine x month strata) excludes 1",
                             detail="; ".join("%s %.1f [%.1f to %.1f] (MH rate ratio %.1f)" % (x, sub.loc[x, "mean_diff"], sub.loc[x, "lo"], sub.loc[x, "hi"], sub.loc[x, "ratio"]) for x in names if x in sub.index)
                             + "; time-adjusted ratio (7-day) %.1f [%.1f to %.1f]" % (sub.loc[names[0], "adj_ratio"], sub.loc[names[0], "adj_lo"], sub.loc[names[0], "adj_hi"]) + "; n=%d machines in the 7-day variant" % sub.loc[names[0], "n_machines"]))
    d3 = R["c3"]
    for c in ("normal", "return_repair"):
        sub = d3[d3.cohort == c]
        okc = sub.dropna(subset=["lo"])
        verd = "Not supported"
        parts = []
        sig = [r for _, r in okc.iterrows() if excludes_zero(r.lo, r.hi)]
        if len(okc) == 0:
            parts.append("fewer than 5 qualifying machines for every dust column")
        else:
            verd = "Strong" if len(sig) == len(okc) and len(set(np.sign([r.median_rel_diff for r in sig]))) == 1 else ("Moderate" if sig else "Not supported")
            parts = ["%s %.0f%% [%.0f to %.0f] n=%d" % (r.dust, r.median_rel_diff, r.lo, r.hi, r.machines_usable) for _, r in okc.iterrows()]
        rows.append(dict(candidate="3 dust within machine: %s SV53" % c, verdict=verd, rule="Strong if all columns' intervals exclude 0 with one sign; Moderate if some do", detail="; ".join(parts)))
    c4 = R["c4"]
    for scope in ("Normal SV53", "RR SV53"):
        sub = c4[(c4.scope == scope)]
        parts, sig = [], []
        for _, r in sub.iterrows():
            parts.append("%s rho %.2f [%.2f to %.2f] n=%d" % (r.metric, r.spearman, r.lo, r.hi, r.n_machines))
            if excludes_zero(r.lo, r.hi):
                sig.append(r.metric)
        main_metrics = ["press_ge100", "exh_ge50"]
        main_sig = [m for m in main_metrics if m in sig]
        verd = "Strong" if len(main_sig) == 2 else ("Moderate" if main_sig else "Not supported")
        rows.append(dict(candidate="4 motor pressure / exhaust vs blockage: %s" % scope, verdict=verd, rule="Strong if both primary metrics' intervals exclude 0; Moderate if one does", detail="; ".join(parts)))
    sub = c4[c4.scope == "RR minus Normal, median share"]
    parts, sig = [], 0
    for _, r in sub.iterrows():
        parts.append("%s %.3f [%.3f to %.3f]" % (r.metric, r.spearman, r.lo, r.hi))
        if r.metric in ("press_ge100", "exh_ge50") and excludes_zero(r.lo, r.hi):
            sig += 1
    rows.append(dict(candidate="4 motor: RR vs Normal median share", verdict="Strong" if sig == 2 else ("Moderate" if sig == 1 else "Not supported"), rule="as above", detail="; ".join(parts)))
    d = kk.loc["n_bt_nr_diff_sv50_minus_sv53_normal"]
    c = kk.loc["n_bt_nr_diff_rr_minus_normal_SV53"]
    rows.append(dict(candidate="5 battery temperature 'not reported' is driven by model, not cohort", verdict="Strong" if excludes_zero(d.interval_low, d.interval_high) and abs(c.value) < abs(d.value) / 10 else "Moderate",
                     rule="model difference interval excludes 0 and the cohort difference (SV53) is under a tenth of it", detail="model (Normal SV50 minus SV53) %.1f pp [%.1f to %.1f]; cohort (RR minus Normal, SV53) %.1f pp [%.1f to %.1f]" % (
                         d.value, d.interval_low, d.interval_high, c.value, c.interval_low, c.interval_high)))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------
def append_to_key_numbers(df):
    """Drop earlier n_ rows, then append the new rows as text; every other line is left byte-for-byte unchanged."""
    lines = KEY.read_text().splitlines(keepends=True)
    head = lines[0]
    body = [l for l in lines[1:] if not l.startswith("n_")]
    before = "".join([head] + body)
    new = df[ins.KEY_COLS].to_csv(index=False, header=False, float_format="%.6g")
    KEY.write_text(before + new)
    return len(body), len(df)


def main():
    R = compute()
    V = verdicts(R)
    V.to_csv(str(OUT / "n_candidate_verdicts.csv"), index=False)
    n_old, n_new = append_to_key_numbers(R["key"])
    print("key_numbers.csv: %d existing rows unchanged, %d n_ rows appended" % (n_old, n_new))
    pd.set_option("display.width", 250, "display.max_colwidth", 160)
    print(V.to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
