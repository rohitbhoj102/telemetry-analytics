"""Final consolidation: every number for the four final insights (I1 to I4) as `f_` rows in key_numbers.csv.

No new candidate analyses. This script (a) copies the numbers the deck needs from the round-2 and
candidate-round computations (src/insights2.py, src/insights3.py, recomputed in-process, not read
from their csv files) under stable `f_i1_*` ... `f_i4_*` ids, and (b) adds the verification numbers
asked for in the final round: I1 leave-one-out and robustness, join-rule comparison, I2 ratio with
interval, I3 crude ratio with interval and standardisation weights, I4 escalation by model.

Appends to reports/insights/key_numbers.csv at text level (every non-f_ line stays byte-for-byte
unchanged; earlier f_ rows are replaced) and writes reports/insights/f_*.csv detail tables.
Run order: src/run_all.py. Python 3.8 compatible.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eda_helpers as h  # noqa: E402
import insights as ins  # noqa: E402
import insights2 as i2  # noqa: E402
import insights3 as i3  # noqa: E402

ROOT = h.ROOT
OUT = ROOT / "reports" / "insights"
KEY = OUT / "key_numbers.csv"
N_BOOT, SEED = h.N_BOOT, h.SEED
SRC = "src/insights_final.py"
G3 = [("normal", "SV50"), ("normal", "SV53"), ("return_repair", "SV53")]
GL, GK = i2.GLABEL, i2.GKEY
VARIANTS = [("main_7d", i3.WINDOW_MAIN, 0.0, "faults"), ("alt_30d", i3.WINDOW_ALT, 0.0, "faults"), ("lag1h_7d", i3.WINDOW_MAIN, i3.LAG_H, "faults"),
            ("sessionspan_7d", i3.WINDOW_MAIN, 0.0, "sessions"), ("sessionspan_30d", i3.WINDOW_ALT, 0.0, "sessions"), ("sessionspan_lag1h_7d", i3.WINDOW_MAIN, i3.LAG_H, "sessions")]
PRIMARY_VARIANT = "sessionspan_7d"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def copy_row(K, new_id, old_id, insight, src, extra_note=""):
    r = src.loc[old_id]
    note = (r.note if isinstance(r.note, str) else "")
    note = (note + "; " if note else "") + "copied from %s" % old_id + (("; " + extra_note) if extra_note else "")
    K.add(new_id, insight, r.metric, r.group, r.value, r.interval_low, r.interval_high, n_machines=r.n_machines, n_events=r.n_events_or_sessions, unit=r.unit,
          src="%s (computed by %s)" % (SRC, r.script_or_cell), note=note, den=r.n_denominator, den_unit=r.denominator_unit)


def subset_machines(M, S, c, fam):
    ser = S[(S.cohort == c) & (S.family == fam)].anonymized_serial.unique()
    return M[M.anonymized_serial.isin(ser)]


def adj_point(st, drop=None):
    """Mantel-Haenszel rate ratio, strata = machine x calendar month (point estimate), optionally without one machine."""
    st = st if drop is None else st[st.anonymized_serial != drop]
    T = (st.in_days + st.out_days).values
    ok = T > 0
    num = (st.in_n.values * st.out_days.values / np.where(ok, T, 1))[ok].sum()
    den = (st.out_n.values * st.in_days.values / np.where(ok, T, 1))[ok].sum()
    return float(num / den) if den > 0 else np.nan


def boot_median(groups, stat=np.median, n_boot=N_BOOT, seed=SEED):
    """groups: dict machine -> array of values. Median of all values with a machine bootstrap."""
    keys = list(groups)
    allv = np.concatenate([groups[k] for k in keys])
    rng = np.random.RandomState(seed)
    b = []
    for _ in range(n_boot):
        pick = rng.randint(0, len(keys), len(keys))
        b.append(stat(np.concatenate([groups[keys[i]] for i in pick])))
    lo, hi = np.percentile(b, [2.5, 97.5])
    return float(stat(allv)), float(lo), float(hi)


def boot_diff_median(ga, gb, n_boot=N_BOOT, seed=SEED):
    ka, kb = list(ga), list(gb)
    rng = np.random.RandomState(seed)
    out = []
    for _ in range(n_boot):
        a = np.concatenate([ga[ka[i]] for i in rng.randint(0, len(ka), len(ka))])
        b = np.concatenate([gb[kb[i]] for i in rng.randint(0, len(kb), len(kb))])
        out.append(np.median(a) - np.median(b))
    lo, hi = np.percentile(out, [2.5, 97.5])
    va, vb = np.median(np.concatenate(list(ga.values()))), np.median(np.concatenate(list(gb.values())))
    return float(va - vb), float(lo), float(hi)


def touches(lo, hi, null):
    return (lo <= null) and (hi >= null)


# ---------------------------------------------------------------------------
# I1: Filter Wash reminders flag and precede blockages
# ---------------------------------------------------------------------------
def build_i1(K, src, T, S, M):
    ins_ = "I1"
    groups = ["normal_SV50", "normal_SV53", "return_repair_SV53", "all"]
    for g in groups:
        copy_row(K, "f_i1_p12_given_wash_" + g, "ic_p12_given_wash_" + g, ins_, src)
        copy_row(K, "f_i1_p12_given_nowash_" + g, "ic_p12_given_nowash_" + g, ins_, src)
        copy_row(K, "f_i1_samesession_rr_" + g, "ic_mh_rr_" + g, ins_, src, "same-session risk ratio, strata = machine")
        copy_row(K, "f_i1_samesession_rr_duration_" + g, "ic_mh_rr_duration_" + g, ins_, src)
    copy_row(K, "f_i1_wash_first_share", "ic_wash_first_share", ins_, src)
    # leave-one-machine-out minimum of the same-session ratio
    for (c, fam) in G3 + [("all", "all")]:
        if c == "all":
            d, lab, g = M, "All groups", "all"
        else:
            d, lab, g = subset_machines(M, S, c, fam), GL[(c, fam)], GK[(c, fam)]
        d = d.reset_index(drop=True)
        point = i2.mh_rr(d, "b_wash", "n_wash", "b_nowash", "n_nowash")
        loo = []
        for i in range(len(d)):
            dd = d.drop(index=i)
            loo.append(i2.mh_rr(dd, "b_wash", "n_wash", "b_nowash", "n_nowash"))
        K.add("f_i1_samesession_rr_loo_min_" + g, ins_, "same-session risk ratio, minimum over leaving out each machine in turn", lab, float(np.min(loo)), n_machines=len(d), unit="ratio", src=SRC + ":build_i1",
              note="point estimate %.2f; leave-one-machine-out range %.2f to %.2f" % (point, np.min(loo), np.max(loo)))
    # lead after a reminder: all window variants, both exposure definitions
    rows = []
    for vname, w, lag, span in VARIANTS:
        t = i3.window_table(T["ff"], T["summ"], w, lag, span, T["sess"])
        for (c, fam) in G3:
            d = t[(t.cohort == c) & (t.family == fam)]
            g = GK[(c, fam)]
            if len(d) < 5:
                rows.append(dict(variant=vname, group=GL[(c, fam)], n_machines=len(d), note="fewer than 5 qualifying machines"))
                continue
            s = i3.summarize_window(d)
            st = t.attrs["strata"]
            st = st[st.anonymized_serial.isin(d.anonymized_serial)]
            loo_adj = [adj_point(st, drop=m) for m in d.anonymized_serial]
            loo_diff = [d[d.anonymized_serial != m].d.mean() for m in d.anonymized_serial]
            s.update(variant=vname, group=GL[(c, fam)], span=span, window_days=w, lag_h=lag, loo_adj_min=float(np.nanmin(loo_adj)), loo_diff_min=float(np.min(loo_diff)))
            rows.append(s)
            flag_adj = "; adjusted-ratio interval touches or includes 1" if s["adj_lo"] <= 1 else ""
            flag_diff = "; paired-difference interval touches or includes 0" if s["lo"] <= 0 else ""
            common = "window %d days%s; exposure span from %s; machines with >= 1 13/1, >= %d day inside and >= %d days outside the windows; episodes = events < 1 h apart merged; time from fault_timestamp (device time, inferred)" % (
                w, " starting %g h after the alert" % lag if lag else "", "the sessions table (events from faults)" if span == "sessions" else "first to last fault", i3.MIN_IN_DAYS, i3.MIN_OUT_DAYS)
            K.add("f_i1_lead_adjratio_%s_%s" % (vname, g), ins_, "type-12 episode rate in the window after a 13/1 vs outside, ratio, Mantel-Haenszel with strata machine x calendar month", GL[(c, fam)],
                  s["adj_ratio"], s["adj_lo"], s["adj_hi"], n_machines=s["n_machines"], n_events=s["events_in"] + s["events_out"], unit="ratio", src=SRC + ":build_i1",
                  note=common + flag_adj + "; leave-one-machine-out minimum %.2f" % s["loo_adj_min"])
            K.add("f_i1_lead_adjratio_loo_min_%s_%s" % (vname, g), ins_, "time-adjusted lead ratio, minimum over leaving out each machine in turn", GL[(c, fam)], s["loo_adj_min"], n_machines=s["n_machines"], unit="ratio",
                  src=SRC + ":build_i1", note="point estimate with all machines %.2f; compare with the interval of f_i1_lead_adjratio_%s_%s" % (s["adj_ratio"], vname, g))
            K.add("f_i1_lead_mhratio_%s_%s" % (vname, g), ins_, "same ratio, strata = machine only (not adjusted for calendar time)", GL[(c, fam)], s["ratio"], s["ratio_lo"], s["ratio_hi"],
                  n_machines=s["n_machines"], n_events=s["events_in"] + s["events_out"], unit="ratio", src=SRC + ":build_i1", note=common)
            K.add("f_i1_lead_diff_%s_%s" % (vname, g), ins_, "within-machine difference in type-12 episodes per 100 days, inside the window after a 13/1 minus outside", GL[(c, fam)], s["mean_diff"], s["lo"], s["hi"],
                  n_machines=s["n_machines"], n_events=s["events_in"] + s["events_out"], unit="episodes per 100 days", src=SRC + ":build_i1",
                  note=common + flag_diff + "; %d machines higher, %d lower inside; leave-one-machine-out minimum %.2f" % (s["n_higher"], s["n_lower"], s["loo_diff_min"]))
    pd.DataFrame(rows).to_csv(str(OUT / "f_i1_robustness.csv"), index=False, float_format="%.6g")
    # machines with at least one 13/1 before exposure thresholds
    e = T["summ"][T["summ"].rate_eligible]
    for (c, fam) in G3:
        ser = e[(e.cohort == c) & (e.family == fam)].anonymized_serial
        n = T["ff"][T["ff"].anonymized_serial.isin(ser) & (T["ff"].fault_type == 13)].anonymized_serial.nunique()
        K.add("f_i1_machines_with_13_1_" + GK[(c, fam)], ins_, "rate-eligible machines with at least one 13/1 occurrence (before exposure thresholds)", GL[(c, fam)], n, n_machines=n, den=len(ser), den_unit="rate-eligible machines",
              unit="machines", src=SRC + ":build_i1")
    # parameters chosen during analysis (not pre-registered)
    for pid, val, unit, lab in (("window_main_days", i3.WINDOW_MAIN, "days", "main window after a 13/1"), ("window_alt_days", i3.WINDOW_ALT, "days", "sensitivity window"),
                                ("lag_hours", i3.LAG_H, "hours", "lagged-start sensitivity (removes same-session overlap)"), ("min_days_inside", i3.MIN_IN_DAYS, "days", "minimum exposure inside the windows"),
                                ("min_days_outside", i3.MIN_OUT_DAYS, "days", "minimum exposure outside the windows"), ("episode_gap_hours", 1, "hours", "events closer than this form one episode"),
                                ("link_window_hours", i2.LINK_WINDOW_H, "hours", "server-date tolerance for the fault-to-session link")):
        K.add("f_i1_param_" + pid, ins_, lab, "parameter", val, unit=unit, src=SRC + ":build_i1", note="chosen during analysis, not pre-registered; the minimum-exposure thresholds were added after a first run without them gave unstable rates")
    return rows


# ---------------------------------------------------------------------------
# I2: SV50 telemetry gaps and battery heat
# ---------------------------------------------------------------------------
def battery_machine_table(T):
    b = T["batt"][T["batt"].delta_valid.fillna(False).astype(bool)].copy()
    dall = [c for c in b.columns if c.startswith("delta_discharge_band_")]
    dh = [c for c in dall if c.endswith("gt_45C")]
    assert len(dall) == 9 and len(dh) == 3
    b["dis_hot"], b["dis_all"] = b[dh].sum(axis=1), b[dall].sum(axis=1)
    mb = b.groupby(["anonymized_serial", "cohort", "family"]).agg(dis_hot=("dis_hot", "sum"), dis_all=("dis_all", "sum")).reset_index()
    return mb[mb.family.isin(["SV50", "SV53"])]


def build_i2(K, src, T, S, ctx_dq):
    ins_ = "I2"
    for (c, fam) in G3:
        g = GK[(c, fam)]
        copy_row(K, "f_i2_notrep_pct_" + g, "if_notrep_" + g, ins_, src)
        for st in ("hot", "cold"):
            copy_row(K, "f_i2_%s_sessions_%s" % (st, g), "if_%s_%s" % (st, g), ins_, src)
        copy_row(K, "f_i2_dis_hot_pct_" + g, "if_dis_hot_" + g, ins_, src)
        copy_row(K, "f_i2_any_hot_machines_" + g, "if_any_hot_" + g, ins_, src)
    copy_row(K, "f_i2_notrep_diff_model", "n_bt_nr_diff_sv50_minus_sv53_normal", ins_, src)
    copy_row(K, "f_i2_notrep_diff_cohort_sv53", "n_bt_nr_diff_rr_minus_normal_SV53", ins_, src)
    for fam in ("SV50", "SV53"):
        copy_row(K, "f_i2_dust_available_pct_" + fam, "ctx_dust_available_" + fam, ins_, src)
    for nid, oid in (("f_i2_dis_hot_pct_sv53_all", "if_dis_hot_sv53_all"), ("f_i2_any_hot_machines_sv53_all", "if_any_hot_sv53_all"), ("f_i2_dis_hot_pct_sv50_drop_top", "if_dis_hot_sv50_drop_top"),
                     ("f_i2_top1_share_sv50", "if_top1_share_sv50"), ("f_i2_fisher_any_hot", "if_fisher_any_hot"), ("f_i2_pack_SV50_4_cell", "if_pack_SV50_4_cell"), ("f_i2_pack_SV53_7_cell", "if_pack_SV53_7_cell")):
        copy_row(K, nid, oid, ins_, src)
    for k in ctx_dq:
        copy_row(K, "f_i2_" + k, k, ins_, src)
    # ratio of hot discharge share: SV50 without its top machine vs SV53 (machine bootstrap)
    mb = battery_machine_table(T)
    s50, s53 = mb[mb.family == "SV50"], mb[mb.family == "SV53"]
    top = s50.sort_values("dis_hot").iloc[-1].anonymized_serial
    rest = s50[s50.anonymized_serial != top]
    ia, ib = i2.boot_idx(len(rest), seed=SEED), i2.boot_idx(len(s53), seed=SEED + 1)
    ra = rest.dis_hot.values[ia].sum(axis=1) / rest.dis_all.values[ia].sum(axis=1)
    rb = s53.dis_hot.values[ib].sum(axis=1) / s53.dis_all.values[ib].sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rat = ra / rb
    rat = rat[np.isfinite(rat)]
    v = (rest.dis_hot.sum() / rest.dis_all.sum()) / (s53.dis_hot.sum() / s53.dis_all.sum())
    K.add("f_i2_ratio_hot_sv50_drop_top_vs_sv53", ins_, "discharge time above 45 C: SV50 without its top machine divided by SV53, ratio", "SV50 (14 machines) / SV53 (42)", float(v), float(np.percentile(rat, 2.5)),
          float(np.percentile(rat, 97.5)), n_machines=len(rest) + len(s53), unit="ratio", src=SRC + ":build_i2", note="machine bootstrap of both groups; 45 C is a bin edge of BMS_Bins.json dischargeBandBins (temperature edges 15 and 45 celsius, unit second)")
    ratio_all = (s50.dis_hot.sum() / s50.dis_all.sum()) / (s53.dis_hot.sum() / s53.dis_all.sum())
    K.add("f_i2_ratio_hot_sv50_all_vs_sv53", ins_, "discharge time above 45 C: SV50 (all 15 machines) divided by SV53, ratio", "SV50 / SV53", float(ratio_all), n_machines=len(s50) + len(s53), unit="ratio", src=SRC + ":build_i2",
          note="point estimate only; one SV50 machine holds 85% of the SV50 hot seconds")
    # battery contribution counts and analysis-session check
    nb = T["batt"].groupby(["family", "anonymized_serial"]).delta_valid.apply(lambda s: bool(s.fillna(False).astype(bool).any())).reset_index()
    for fam in ("SV50", "SV53"):
        n = int(nb[(nb.family == fam) & nb.delta_valid].shape[0])
        K.add("f_i2_battery_machines_" + fam, ins_, "machines contributing at least one valid battery period", fam, n, n_machines=n, unit="machines", src=SRC + ":build_i2")
    K.add("f_i2_analysis_sessions_total", ins_, "analysis sessions used for the 'not reported' shares (fact_session rows)", "both cohorts", len(T["sess"]), n_events=len(T["sess"]), unit="sessions", src=SRC + ":build_i2",
          note="equals dq_analysis_clean_sessions_all (checked in this script)")
    return mb


# ---------------------------------------------------------------------------
# I3: sub-model concentration and the re-weighted RR vs Normal gap
# ---------------------------------------------------------------------------
def build_i3(K, src, T):
    ins_ = "I3"
    for oid in [i for i in src.index if i.startswith("ie_rate12_") and "_SV53_" in i]:
        copy_row(K, "f_i3_" + oid[3:], oid, ins_, src)
    for oid in [i for i in src.index if i.startswith("ie_rate12_normal_SV50_")]:
        copy_row(K, "f_i3_rate12_normal_SV50_" + oid[len("ie_rate12_normal_SV50_"):], oid, ins_, src)
    for nid, oid in (("f_i3_diff_sv53ab_vs_rest", "ie_diff_sv53ab_n12"), ("f_i3_permp_sv53ab_vs_rest", "ie_permp_sv53ab_n12"), ("f_i3_diff_sv50aa_vs_rest", "ie_diff_sv50aa_n12"),
                     ("f_i3_permp_sv50aa_vs_rest", "ie_permp_sv50aa_n12"), ("f_i3_ab_share_normal", "ie_ab_share_normal"), ("f_i3_ab_share_return_repair", "ie_ab_share_return_repair"),
                     ("f_i3_std_rate12_normal", "ie_std_rate12_normal"), ("f_i3_std_rate12_return_repair", "ie_std_rate12_return_repair"), ("f_i3_std_ratio", "ie_std_ratio"),
                     ("f_i3_ab_rr_minus_normal_all", "ie_ab_rr_minus_normal_all"), ("f_i3_ab_rr_minus_normal_drop_top", "ie_ab_rr_minus_normal_drop_top"),
                     ("f_i3_top1_share_normal", "ie_top1_share_normal"), ("f_i3_top1_share_return_repair", "ie_top1_share_return_repair")):
        copy_row(K, nid, oid, ins_, src)
    # crude ratio with an interval; must equal the first-round i2_ratio_t12_main
    e = T["summ"][T["summ"].rate_eligible & (T["summ"].family == "SV53")].copy()
    e["n12"] = e.n_faults_t12_v1_primary + e.n_faults_t12_v2_primary
    a, b = e[e.cohort == "return_repair"], e[e.cohort == "normal"]
    ia, ib = i2.boot_idx(len(a), seed=SEED), i2.boot_idx(len(b), seed=SEED + 1)
    ra = a.n12.values[ia].sum(axis=1) / a.n_sessions.values[ia].sum(axis=1)
    rb = b.n12.values[ib].sum(axis=1) / b.n_sessions.values[ib].sum(axis=1)
    rat = ra / rb
    v = (a.n12.sum() / a.n_sessions.sum()) / (b.n12.sum() / b.n_sessions.sum())
    K.add("f_i3_crude_ratio", ins_, "RR / Normal airway-blockage rate, all SV53 machines, no re-weighting (ratio)", "SV53", float(v), float(np.percentile(rat, 2.5)), float(np.percentile(rat, 97.5)),
          n_machines=len(a) + len(b), unit="ratio", src=SRC + ":build_i3", note="supersedes the first-round headline 'about 5x' (i2_ratio_t12_main); machine bootstrap of both cohorts")
    # standardisation weights (Normal sessions mix over AB, AC, AE, AF)
    s53 = e[e.cohort == "normal"]
    w = s53[s53.model.isin(["SV53-AB", "SV53-AC", "SV53-AE", "SV53-AF"])].groupby("model").n_sessions.sum()
    w = w / w.sum()
    for m_, x in w.items():
        K.add("f_i3_std_weight_" + m_.replace("-", "_"), ins_, "standardisation weight: share of Normal SV53 sessions (AB, AC, AE, AF) in this sub-model", m_, float(x * 100), unit="%", src=SRC + ":build_i3",
              note="direct standardisation: both cohorts' sub-model rates are weighted to the NORMAL sessions mix (not the RR mix); SV53-AA left out")
    # eligible machines per sub-model and cohort
    for (c, m_), d in e.groupby(["cohort", "model"]):
        K.add("f_i3_machines_%s_%s" % (c, m_.replace("-", "_")), ins_, "rate-eligible machines by cohort and sub-model", "%s %s" % (c, m_), len(d), n_machines=len(d), n_events=float(d.n12.sum()),
              den=float(d.n_sessions.sum()), den_unit="clean sessions", unit="machines", src=SRC + ":build_i3", note="n_events = type-12 occurrences")
    # the first-round value must agree
    old = pd.read_csv(KEY).set_index("id").loc["i2_ratio_t12_main", "value"]
    assert abs(old - v) < 1e-3 * max(1, abs(old)), (old, v)


# ---------------------------------------------------------------------------
# I4: escalation by model
# ---------------------------------------------------------------------------
def escalation_groups(S):
    """Primary: Normal SV50 vs Normal SV53 (same cohort, models only). Supplementary: SV53 both cohorts."""
    return [("normal", "SV50", "Normal SV50", "normal_SV50"), ("normal", "SV53", "Normal SV53", "normal_SV53"), (None, "SV53", "SV53 (Normal + Return/Repair)", "SV53_all")]


def gaps_by_machine(Sg):
    b = Sg[(Sg.f121 == 1) & (Sg.f122 == 1) & Sg.t121.notna() & Sg.t122.notna()].copy()
    b["gap"] = (b.t122 - b.t121).dt.total_seconds()
    pos = b[b.gap > 0]
    return {k: g.gap.values for k, g in pos.groupby("anonymized_serial")}, int((b.gap == 0).sum()), int((b.gap < 0).sum()), len(b)


def build_i4(K, T, S, M):
    ins_ = "I4"
    info = {}
    for (c, fam, lab, g) in escalation_groups(S):
        Sg = S[(S.family == fam) & ((S.cohort == c) if c else True)]
        d = M[M.anonymized_serial.isin(Sg.anonymized_serial.unique())]
        d1, d2 = d[d.s121 > 0], d[d.s122 > 0]
        i2.add_rate(K, "f_i4_esc_share_" + g, ins_, "of sessions with a 12/1 (inlet blocked, motor still running), % that also record 12/2 (in error)", lab, d1, "s121_any122", "s121", "%", den_unit="sessions with 12/1",
                    note="session = serial + session_id linked on matching server dates (<= 24 h); machine bootstrap")
        i2.add_rate(K, "f_i4_prior121_share_" + g, ins_, "of sessions with a 12/2 error, % whose first 12/1 came earlier in the same session", lab, d2, "s122_after121", "s122", "%", den_unit="sessions with 12/2",
                    note="order from fault_timestamp (device time, inferred); strictly earlier; ties and error-first count as not preceded")
        gm, n_ties, n_err_first, n_both = gaps_by_machine(Sg)
        allg = np.concatenate(list(gm.values()))
        med, lo, hi = boot_median(gm)
        K.add("f_i4_gap_median_s_" + g, ins_, "median seconds from the first 12/1 to the first 12/2 in a session (sessions where 12/1 came first)", lab, med, lo, hi, n_machines=len(gm), n_events=len(allg), unit="seconds",
              src=SRC + ":build_i4", note="machine bootstrap; fault_timestamp has millisecond-scale resolution (see f_i4_ts_*)")
        idx_within = {k: (v <= 60).astype(float) for k, v in gm.items()}
        sh, slo, shi = boot_median(idx_within, stat=np.mean)
        K.add("f_i4_gap_within60_" + g, ins_, "of those sessions, % where the 12/2 followed within 60 seconds", lab, sh * 100, slo * 100, shi * 100, n_machines=len(gm), n_events=int((allg <= 60).sum()), den=len(allg),
              den_unit="sessions with 12/1 then 12/2", unit="%", src=SRC + ":build_i4", note="machine bootstrap")
        K.add("f_i4_ties_%s" % g, ins_, "sessions with both 12/1 and 12/2 where the two timestamps are identical (no measurable order)", lab, n_ties, n_events=n_ties, den=n_both, den_unit="sessions with both", unit="sessions", src=SRC + ":build_i4")
        K.add("f_i4_errorfirst_%s" % g, ins_, "sessions with both 12/1 and 12/2 where 12/2 is timestamped first", lab, n_err_first, n_events=n_err_first, den=n_both, den_unit="sessions with both", unit="sessions", src=SRC + ":build_i4")
        info[g] = dict(d1=d1, d2=d2, gm=gm)
    # model differences, SV50 minus SV53, same cohort (Normal) and with SV53 pooled
    for tag, other in (("normal", "normal_SV53"), ("vs_sv53_all", "SV53_all")):
        a, b = info["normal_SV50"], info[other]
        lab = "Normal SV50 minus %s" % ("Normal SV53" if tag == "normal" else "SV53 (Normal + RR)")
        v, lo, hi = i3.boot_diff_share(a["d1"], b["d1"], "s121_any122", "s121")
        K.add("f_i4_esc_diff_sv50_minus_sv53_" + tag, ins_, "difference in the share of 12/1 sessions that escalate to 12/2, percentage points", lab, v, lo, hi, n_machines=len(a["d1"]) + len(b["d1"]),
              n_events=float(a["d1"].s121_any122.sum() + b["d1"].s121_any122.sum()), unit="percentage points", src=SRC + ":build_i4")
        v, lo, hi = i3.boot_diff_share(a["d2"], b["d2"], "s122_after121", "s122")
        K.add("f_i4_prior121_diff_sv50_minus_sv53_" + tag, ins_, "difference in the share of 12/2 sessions with an earlier 12/1, percentage points", lab, v, lo, hi, n_machines=len(a["d2"]) + len(b["d2"]),
              n_events=float(a["d2"].s122_after121.sum() + b["d2"].s122_after121.sum()), unit="percentage points", src=SRC + ":build_i4")
        v, lo, hi = boot_diff_median(a["gm"], b["gm"])
        K.add("f_i4_gap_diff_sv50_minus_sv53_" + tag, ins_, "difference in the median seconds from 12/1 to 12/2, SV50 minus SV53", lab, v, lo, hi, n_machines=len(a["gm"]) + len(b["gm"]), unit="seconds", src=SRC + ":build_i4")
    # timestamp resolution
    ff = T["ff"]
    us = ff.fault_timestamp.dt.microsecond
    whole = int((us == 0).sum())
    K.add("f_i4_ts_subsecond_share", ins_, "fault_timestamp values that are not whole seconds, %", "all fault occurrences", (1 - whole / float(len(ff))) * 100, n_events=len(ff) - whole, den=len(ff), den_unit="fault occurrences", unit="%", src=SRC + ":build_i4",
          note="raw format is a UTC timestamp with fractional seconds, e.g. 2025-12-16 18:01:17.950000")
    K.add("f_i4_ts_multiple_of_10ms_share", ins_, "fault_timestamp values that are multiples of 10 ms, %", "all fault occurrences", float((us % 10000 == 0).mean() * 100), n_events=int((us % 10000 == 0).sum()), den=len(ff),
          den_unit="fault occurrences", unit="%", src=SRC + ":build_i4")
    d = ff.sort_values(["anonymized_serial", "fault_timestamp"])
    dd = d.groupby("anonymized_serial").fault_timestamp.diff().dt.total_seconds()
    K.add("f_i4_ts_min_positive_gap_s", ins_, "smallest positive gap between two fault timestamps of one machine, seconds", "all fault occurrences", float(dd[dd > 0].min()), unit="seconds", src=SRC + ":build_i4")
    return info


# ---------------------------------------------------------------------------
# join rule: the one used, and the round-1 rule as a check
# ---------------------------------------------------------------------------
def pooled_value(d, num, den):
    return float(d[num].sum() * 100.0 / d[den].sum())


def join_metrics(S, M):
    out = {}
    for (c, fam) in G3:
        Sg = S[(S.cohort == c) & (S.family == fam)]
        d = M[M.anonymized_serial.isin(Sg.anonymized_serial.unique())]
        g = GK[(c, fam)]
        out["i1_samesession_rr_" + g] = i2.mh_rr(d, "b_wash", "n_wash", "b_nowash", "n_nowash")
        out["i1_p12_given_wash_" + g] = pooled_value(d, "b_wash", "n_wash")
        out["i1_p12_given_nowash_" + g] = pooled_value(d, "b_nowash", "n_nowash")
        out["i4_esc_share_" + g] = pooled_value(d[d.s121 > 0], "s121_any122", "s121")
        out["i4_prior121_share_" + g] = pooled_value(d[d.s122 > 0], "s122_after121", "s122")
    d = M
    out["i1_samesession_rr_all"] = i2.mh_rr(d, "b_wash", "n_wash", "b_nowash", "n_nowash")
    out["i4_esc_share_SV53_all"] = pooled_value(M[M.anonymized_serial.isin(S[S.family == "SV53"].anonymized_serial.unique()) & (M.s121 > 0)], "s121_any122", "s121")
    return out


def build_join(K, T, S, M):
    ins_ = "Method"
    ff = T["ff"]
    n_f = len(ff)
    K.add("f_join_rule_server_dates_rate", ins_, "faults linked to a session by the rule used for I1 and I4: serial + session_id with the fault and session server dates within 24 h", "all", ff.sess_key2.notna().mean() * 100,
          n_events=int(ff.sess_key2.notna().sum()), den=n_f, den_unit="fault occurrences", unit="%", src=SRC + ":build_join")
    K.add("f_join_rule_nearest_rate", ins_, "faults linked by the round-1 rule (fact_fault.session_key: serial + session_id, session server date nearest to fault_timestamp)", "all", ff.session_key.notna().mean() * 100,
          n_events=int(ff.session_key.notna().sum()), den=n_f, den_unit="fault occurrences", unit="%", src=SRC + ":build_join")
    both = ff[ff.sess_key2.notna() & ff.session_key.notna()]
    K.add("f_join_agree_pct", ins_, "of faults linked under both rules, % linked to the same session", "all", float((both.sess_key2 == both.session_key).mean() * 100), n_events=int((both.sess_key2 == both.session_key).sum()),
          den=len(both), den_unit="faults linked under both rules", unit="%", src=SRC + ":build_join")
    alt = ff.copy()
    alt["sess_key2"] = alt["session_key"]
    S_alt = i2.session_table(T["sess"], alt)
    M_alt = i2.machine_table(S_alt)
    main, other = join_metrics(S, M), join_metrics(S_alt, M_alt)
    rows = []
    for k in main:
        K.add("f_join_alt_" + k, ins_, "value of %s under the round-1 join rule (nearest session server date to fault_timestamp)" % k, "round-1 rule", other[k], unit="ratio" if "rr" in k else "%", src=SRC + ":build_join",
              note="rule used for I1 and I4 gives %.3f" % main[k])
        rows.append(dict(metric=k, server_date_rule=main[k], round1_rule=other[k], abs_diff=abs(main[k] - other[k]), rel_diff_pct=(other[k] / main[k] - 1) * 100 if main[k] else np.nan))
    pd.DataFrame(rows).to_csv(str(OUT / "f_join_rule_check.csv"), index=False, float_format="%.6g")
    return rows


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def compute():
    T = i2.load()
    R2 = i2.compute(T)
    S, M = R2["S"], R2["M"]
    R3 = i3.compute(i2.load())
    src = pd.concat([R2["key"], R3["key"]]).set_index("id")
    K = ins.KeyNumbers()
    build_i1(K, src, T, S, M)
    ctx_dq = ["ctx_machines_normal_SV50", "ctx_machines_return_repair_SV50", "ctx_machines_return_repair_SV53", "ctx_tables_SV50_motor", "ctx_tables_SV50_battery", "ctx_tables_SV50_sessions"]
    build_i2(K, src, T, S, ctx_dq)
    build_i3(K, src, T)
    build_i4(K, T, S, M)
    build_join(K, T, S, M)
    return K.frame(), dict(src=src)


def write(df):
    lines = KEY.read_text().splitlines(keepends=True)
    head, body = lines[0], [l for l in lines[1:] if not l.startswith("f_")]
    before = "".join([head] + body)
    KEY.write_text(before + df[ins.KEY_COLS].to_csv(index=False, header=False, float_format="%.6g"))
    return len(body), len(df)


def main():
    df, _ = compute()
    n_old, n_new = write(df)
    k = pd.read_csv(KEY).set_index("id")
    # consistency of copied rows with the first-round DQ numbers
    assert int(k.loc["f_i2_analysis_sessions_total", "value"]) == int(k.loc["dq_analysis_clean_sessions_all", "value"]), "analysis session count differs from the DQ number"
    print("key_numbers.csv: %d non-f_ rows unchanged, %d f_ rows written" % (n_old, n_new))
    return 0


if __name__ == "__main__":
    sys.exit(main())
