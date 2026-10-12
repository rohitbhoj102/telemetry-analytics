"""Step 11: second round of insights (deeper cuts requested after the first review).

Writes reports/insights/key_numbers_v2.csv (same columns as key_numbers.csv) and, with --charts,
the v2 charts in reports/figures/v2/. Reads data/model/ plus the server date of each fault from
data/clean/dq/faults.parquet (needed to link faults to sessions, see link_faults). Python 3.8
compatible. Does not change key_numbers.csv, the first-round charts or any pipeline output.

Method rules (project decisions, same as src/insights.py):
- Machines are the unit of resampling. 95% percentile bootstrap, 2,000 resamples, fixed seed.
- Return/Repair (RR) is a selected population; nothing here claims a cause.
- Everything is exploratory: many cuts, no multiplicity correction. Permutation / exact p-values are
  given only as a rough guide and are labelled as such.
- Meanings used beyond the brief and bin JSONs are labelled [inferred] in the `note` column.
"""
import sys
from math import comb
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eda_helpers as h  # noqa: E402
import insights as ins  # noqa: E402

ROOT = h.ROOT
MODEL = ROOT / "data" / "model"
CLEAN = ROOT / "data" / "clean"
OUT_DIR = ROOT / "reports" / "insights"
FIG_DIR = ROOT / "reports" / "figures" / "v2"
N_BOOT, SEED = h.N_BOOT, h.SEED
NORMAL, RR = h.NORMAL, h.RR
SRC = "src/insights2.py"
LINK_WINDOW_H = 24          # a fault is linked to a session only if the two server dates are within 24 h
GROUPS = [("normal", "SV50"), ("normal", "SV53"), ("return_repair", "SV53")]
GLABEL = {("normal", "SV50"): "Normal SV50", ("normal", "SV53"): "Normal SV53", ("return_repair", "SV53"): "Return/Repair SV53"}
GKEY = {("normal", "SV50"): "normal_SV50", ("normal", "SV53"): "normal_SV53", ("return_repair", "SV53"): "return_repair_SV53"}


def gk(c, f):
    return GKEY[(c, f)]


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------
def load():
    con = duckdb.connect()

    def m(t):
        return "read_parquet('%s')" % (MODEL / (t + ".parquet"))

    dim = con.execute("SELECT * FROM %s" % m("dim_machine")).df()
    dim["family"] = dim.model.fillna("").str[:4]
    dim["sub"] = dim.model.fillna("").str[5:]
    summ = con.execute("SELECT * FROM %s" % m("machine_summary")).df()
    summ["family"] = summ.model.fillna("").str[:4]
    summ["sub"] = summ.model.fillna("").str[5:]
    sess = con.execute("SELECT * FROM %s" % m("fact_session")).df()
    sess = sess.merge(dim[["anonymized_serial", "model", "family", "sub"]], on="anonymized_serial", how="left")
    # fact_fault has one row per fault occurrence; the server date of that row is only in the clean DQ table
    ff = con.execute("""
        SELECT f.*, d.date_server AS fault_server_ts, d.product_alarm_source, d.product_alarm_fault_severity
        FROM %s f LEFT JOIN read_parquet('%s') d
          ON d.source_file = f.source_file AND d.source_row = f.source_row""" % (m("fact_fault"), CLEAN / "dq" / "faults.parquet")).df()
    assert ff.fault_server_ts.notna().all() and len(ff) == con.execute("SELECT count(*) FROM %s" % m("fact_fault")).fetchone()[0]
    ff = ff.merge(dim[["anonymized_serial", "model", "family", "sub"]], on="anonymized_serial", how="left")
    batt = con.execute("SELECT * FROM %s" % m("fact_battery_period")).df()
    batt = batt.merge(dim[["anonymized_serial", "model", "family", "sub", "region"]], on="anonymized_serial", how="left")
    return dict(dim=dim, summ=summ, sess=sess, ff=ff, batt=batt)


def link_faults(sess, ff):
    """Link each fault to a session on (serial, session_id) when the two server dates are within 24 h.

    Verified from the data (see key numbers link_*): the fault row and the session row of the same
    serial + session_id arrive together (server dates within 1 h for 99% of links), while
    fault_timestamp (device time) is hours to weeks earlier. This is a firmer link than the nearest-date
    rule in fact_fault.session_key, which compares fault_timestamp with the session server date.
    Returns the fault table with `sess_key2` (NaN = not linked).
    """
    s = sess[["session_key", "anonymized_serial", "session_id", "date_server"]].rename(columns={"date_server": "sess_server_ts"})
    c = ff[["fault_key", "anonymized_serial", "session_id", "fault_server_ts"]].merge(s, on=["anonymized_serial", "session_id"], how="left")
    c["gap_h"] = (c.fault_server_ts - c.sess_server_ts).abs().dt.total_seconds() / 3600.0
    c = c.sort_values(["fault_key", "gap_h"]).drop_duplicates("fault_key")
    c.loc[c.gap_h > LINK_WINDOW_H, "session_key"] = np.nan
    c.loc[c.gap_h > LINK_WINDOW_H, "gap_h"] = np.nan
    out = ff.merge(c[["fault_key", "session_key", "gap_h"]].rename(columns={"session_key": "sess_key2", "gap_h": "link_gap_server_h"}), on="fault_key", how="left")
    return out


def session_table(sess, ff2):
    """One row per analysis session with linked fault flags (airway blockage 12/1, 12/2, Filter Wash 13/1)."""
    lk = ff2[ff2.sess_key2.notna()].copy()
    lk["sess_key2"] = lk.sess_key2.astype(int)
    lk["is121"] = ((lk.fault_type == 12) & (lk.fault_value == 1))
    lk["is122"] = ((lk.fault_type == 12) & (lk.fault_value == 2))
    lk["is12"] = lk.fault_type == 12
    lk["is13"] = lk.fault_type == 13
    ts = lk.fault_timestamp
    agg = pd.DataFrame({
        "f121": lk.groupby("sess_key2").is121.any().astype(int),
        "f122": lk.groupby("sess_key2").is122.any().astype(int),
        "f13": lk.groupby("sess_key2").is13.any().astype(int),
        "t121": ts.where(lk.is121).groupby(lk.sess_key2).min(),
        "t122": ts.where(lk.is122).groupby(lk.sess_key2).min(),
        "t12": ts.where(lk.is12).groupby(lk.sess_key2).min(),
        "t13": ts.where(lk.is13).groupby(lk.sess_key2).min(),
    })
    s = sess.merge(agg, left_on="session_key", right_index=True, how="left")
    for c in ("f121", "f122", "f13"):
        s[c] = s[c].fillna(0).astype(int)
    s["f12"] = ((s.f121 + s.f122) > 0).astype(int)
    return s


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def boot_idx(n, n_boot=N_BOOT, seed=SEED):
    return np.random.RandomState(seed).randint(0, n, size=(n_boot, n))


def pooled_share(d, num, den, scale=100.0, seed=SEED):
    """Pooled share sum(num)/sum(den) x scale with a machine bootstrap. d has one row per machine."""
    d = d.dropna(subset=[num, den])
    d = d[d[den] > 0]
    x, y = d[num].values.astype(float), d[den].values.astype(float)
    idx = boot_idx(len(d), seed=seed)
    b = scale * x[idx].sum(axis=1) / y[idx].sum(axis=1)
    lo, hi = np.percentile(b, [2.5, 97.5])
    return scale * x.sum() / y.sum(), float(lo), float(hi), len(d), float(x.sum()), float(y.sum())


def mh_rr(d, a, n1, c, n0):
    """Mantel-Haenszel risk ratio across strata (rows of d): exposed = n1 with a events, unexposed = n0 with c events."""
    a, n1, c, n0 = (d[k].values.astype(float) for k in (a, n1, c, n0))
    N = n1 + n0
    ok = (N > 0) & (n1 > 0) & (n0 > 0)
    return float((a[ok] * n0[ok] / N[ok]).sum() / (c[ok] * n1[ok] / N[ok]).sum())


def mh_rr_boot(d, cols, n_boot=N_BOOT, seed=SEED):
    """MH risk ratio with strata = machines (one row per machine); interval from resampling machines."""
    a, n1, c, n0 = (d[k].values.astype(float) for k in cols)
    N = n1 + n0
    ok = (N > 0) & (n1 > 0) & (n0 > 0)
    a, n1, c, n0, N = a[ok], n1[ok], c[ok], n0[ok], N[ok]
    num, den = a * n0 / N, c * n1 / N
    idx = boot_idx(len(a), n_boot, seed)
    with np.errstate(divide="ignore", invalid="ignore"):
        b = num[idx].sum(axis=1) / den[idx].sum(axis=1)
    b = b[np.isfinite(b)]
    return float(num.sum() / den.sum()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5)), int(ok.sum())


def exact_binom_p(k, n, p=0.5):
    """Two-sided exact binomial test p (sum of outcomes no more likely than observed)."""
    pm = [comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    return float(sum(x for x in pm if x <= pm[k] * (1 + 1e-9)))


def fisher_two_sided(a, b, c, d):
    """Fisher exact test for [[a, b], [c, d]] (a,b = group 1 yes/no; c,d = group 2 yes/no)."""
    n1, n2, k = a + b, c + d, a + c
    tot = comb(n1 + n2, k)
    pm = {x: comb(n1, x) * comb(n2, k - x) / float(tot) for x in range(max(0, k - n2), min(n1, k) + 1)}
    return float(sum(p for p in pm.values() if p <= pm[a] * (1 + 1e-9)))


def perm_p(a, b, num, den, n_perm=20000, seed=SEED):
    """Permutation p for the difference in pooled rates between two machine groups (label shuffling)."""
    x = np.concatenate([a[num].values, b[num].values]).astype(float)
    y = np.concatenate([a[den].values, b[den].values]).astype(float)
    na = len(a)
    obs = x[:na].sum() / y[:na].sum() - x[na:].sum() / y[na:].sum()
    rng = np.random.RandomState(seed)
    cnt = 0
    for _ in range(n_perm):
        p = rng.permutation(len(x))
        d = x[p[:na]].sum() / y[p[:na]].sum() - x[p[na:]].sum() / y[p[na:]].sum()
        if abs(d) >= abs(obs) - 1e-12:
            cnt += 1
    return (cnt + 1.0) / (n_perm + 1.0)


def within_effect(d, y, xs, grp, n_boot=N_BOOT, seed=SEED):
    """Coefficient of xs[0] in y ~ xs with machine fixed effects (within transformation); cluster bootstrap CI."""
    ids = d[grp].values
    uniq = np.unique(ids)
    pos = {u: np.where(ids == u)[0] for u in uniq}
    X = d[xs].values.astype(float)
    Y = d[y].values.astype(float)
    Xc = {u: X[pos[u]] - X[pos[u]].mean(axis=0) for u in uniq}
    Yc = {u: Y[pos[u]] - Y[pos[u]].mean() for u in uniq}

    def fit(sel):
        xm = np.vstack([Xc[u] for u in sel])
        ym = np.concatenate([Yc[u] for u in sel])
        return np.linalg.lstsq(xm, ym, rcond=None)[0][0]

    b0 = fit(uniq)
    rng = np.random.RandomState(seed)
    bs = [fit(uniq[rng.randint(0, len(uniq), len(uniq))]) for _ in range(n_boot)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return float(b0), float(lo), float(hi), len(uniq)


# ---------------------------------------------------------------------------
# Computation: one function per insight, all adding rows to KeyNumbers
# ---------------------------------------------------------------------------
def add_rate(K, id_, insight, metric, group, d, num, den, unit, note="", den_unit="sessions", scale=100.0, seed=SEED):
    v, lo, hi, n, x, y = pooled_share(d, num, den, scale=scale, seed=seed)
    K.add(id_, insight, metric, group, v, lo, hi, n_machines=n, n_events=x, unit=unit, src=SRC, note=note, den=y, den_unit=den_unit)
    return v


def machine_table(S):
    """Per-machine session-level counts used by several insights."""
    S = S.copy()
    S["both"] = ((S.f12 == 1) & (S.f13 == 1)).astype(int)
    S["nowash"] = (S.f13 == 0).astype(int)
    S["b_wash"] = S.both
    S["b_nowash"] = ((S.f12 == 1) & (S.f13 == 0)).astype(int)
    S["s121_any122"] = ((S.f121 == 1) & (S.f122 == 1)).astype(int)
    S["s122_after121"] = ((S.f122 == 1) & (S.f121 == 1) & (S.t121 < S.t122)).astype(int)
    g = S.groupby("anonymized_serial")
    M = pd.DataFrame({
        "n_sess": g.size(), "s12": g.f12.sum(), "s121": g.f121.sum(), "s122": g.f122.sum(), "s13": g.f13.sum(),
        "n_wash": g.f13.sum(), "n_nowash": g.nowash.sum(), "b_wash": g.b_wash.sum(), "b_nowash": g.b_nowash.sum(),
        "s121_any122": g.s121_any122.sum(), "s122_after121": g.s122_after121.sum(),
    }).reset_index()
    return M


def compute_context(T, K):
    dim, sess, ff = T["dim"], T["sess"], T["ff"]
    ins_ = "Context"
    for c in ("normal", "return_repair"):
        for fam in ("SV50", "SV53"):
            n = int(((dim.cohort == c) & (dim.family == fam)).sum())
            K.add("ctx_machines_%s_%s" % (c, fam), ins_, "machines in dim_machine by cohort and model family", "%s %s" % (c, fam), n, n_machines=n, unit="machines", src=SRC + ":compute_context")
    n_unk = int((dim.family == "").sum())
    K.add("ctx_machines_unknown_model", ins_, "machines with no model in sessions or faults", "both cohorts", n_unk, n_machines=n_unk, unit="machines", src=SRC + ":compute_context")
    for fam in ("SV50", "SV53"):
        d = dim[dim.family == fam]
        for col, lab in (("has_session_rows", "sessions"), ("has_fault_rows", "faults"), ("has_motor_rows", "motor"), ("has_battery_rows", "battery")):
            n = int(d[col].fillna(False).astype(bool).sum())
            K.add("ctx_tables_%s_%s" % (fam, lab), ins_, "machines with raw rows in table: " + lab, fam, n, n_machines=n, unit="machines", src=SRC + ":compute_context")
    mo = dim[dim.has_motor_rows.fillna(False).astype(bool)]
    for c in ("normal", "return_repair"):
        n = int((mo.cohort == c).sum())
        K.add("ctx_motor_machines_%s" % c, ins_, "machines with motor rows", c, n, n_machines=n, unit="machines", src=SRC + ":compute_context")
    K.add("ctx_motor_machines_total", ins_, "machines with motor rows", "both cohorts", len(mo), n_machines=len(mo), unit="machines", src=SRC + ":compute_context")
    for fam in ("SV50", "SV53"):
        d = sess[sess.family == fam]
        v = d.ultra_fine_dust_particle_mass_clean.notna().mean() * 100
        K.add("ctx_dust_available_%s" % fam, ins_, "analysis sessions with an ultra-fine dust value (not null, not 65535)", fam, v,
              n_events=int(d.ultra_fine_dust_particle_mass_clean.notna().sum()), den=len(d), den_unit="analysis sessions", unit="%", src=SRC + ":compute_context",
              note="the 65535 sentinel is set to null in the clean table [inferred sentinel]")
    pairs = ff.groupby(["fault_type", "fault_value"]).size()
    K.add("ctx_fault_pairs_present", ins_, "distinct fault type/value pairs in fact_fault", "all", len(pairs), unit="pairs", src=SRC + ":compute_context",
          note="present: " + ", ".join("%d/%d" % k for k in pairs.index) + "; type 7 (Brush Bar Stall) and values 12/0, 12/3 never occur")


def compute_fault_anatomy(T, K):
    dim, summ, ff = T["dim"], T["summ"], T["ff"]
    ins_ = "I-A fault anatomy"
    e = summ[summ.rate_eligible]
    for (c, fam) in GROUPS:
        d = e[(e.cohort == c) & (e.family == fam)].copy()
        d["n12"] = d.n_faults_t12_v1_primary + d.n_faults_t12_v2_primary
        d["nall"] = d.n_faults_primary
        d["n121"] = d.n_faults_t12_v1_primary
        d["n13"] = d.n_faults_t13_v1_primary
        g = gk(c, fam)
        add_rate(K, "ia_share_wash_%s" % g, ins_, "Filter Wash 13/1 as % of fault occurrences", GLABEL[(c, fam)], d, "n13", "nall", "%", den_unit="fault occurrences",
                 note="pooled over rate-eligible machines; fault meanings from the brief (13 Filter Wash, value 1 needs cleaning)")
        add_rate(K, "ia_share_block_%s" % g, ins_, "Airway blockage (type 12) as % of fault occurrences", GLABEL[(c, fam)], d, "n12", "nall", "%", den_unit="fault occurrences")
        add_rate(K, "ia_share_running_%s" % g, ins_, "of airway-blockage occurrences, % that are 12/1 (inlet blocked, motor still running)", GLABEL[(c, fam)], d, "n121", "n12", "%",
                 den_unit="airway blockage occurrences", note="the remainder is 12/2 (inlet blocked and in error); 12/3 outlet blocked never occurs")
        ee = dim[(dim.cohort == c) & (dim.family == fam) & dim.has_fault_rows.fillna(False).astype(bool)]
        K.add("ia_machines_with_faults_%s" % g, ins_, "machines with at least one fault row", GLABEL[(c, fam)], len(ee), n_machines=len(ee), unit="machines", src=SRC + ":compute_fault_anatomy")
    f = ff[(ff.cohort == "normal") & (ff.family == "SV50")]
    tot = int((dim.cohort.eq("normal") & dim.family.eq("SV50")).sum())
    for key, mask, lab in (("wash", f.fault_type == 13, "Filter Wash 13/1"), ("run", (f.fault_type == 12) & (f.fault_value == 1), "12/1 inlet blocked, motor still running"),
                           ("err", (f.fault_type == 12) & (f.fault_value == 2), "12/2 inlet blocked and in error")):
        n = f[mask].anonymized_serial.nunique()
        K.add("ia_sv50_machines_%s" % key, ins_, "SV50 machines with at least one " + lab, "Normal SV50", n / float(tot) * 100, n_machines=n, den=tot, den_unit="SV50 machines",
              unit="% of SV50 machines", src=SRC + ":compute_fault_anatomy", n_events=int(mask.sum()))


def compute_escalation(S, M, K):
    """12/1 (motor still running) -> 12/2 (in error) inside one session."""
    ins_ = "I-B escalation"
    for (c, fam) in GROUPS + [("all", "all")]:
        if c == "all":
            d, lab, g = M, "All groups", "all"
        else:
            d = M[M.anonymized_serial.isin(S[(S.cohort == c) & (S.family == fam)].anonymized_serial)]
            lab, g = GLABEL[(c, fam)], gk(c, fam)
        add_rate(K, "ib_121_to_122_%s" % g, ins_, "of sessions with a 12/1 warning, % that also record 12/2 (in error)", lab, d, "s121_any122", "s121", "%", den_unit="sessions with 12/1",
                 note="linked on serial+session_id and server dates within 24 h; unit is the session, not the event (one session can repeat events)")
        add_rate(K, "ib_122_after_121_%s" % g, ins_, "of sessions with a 12/2 error, % whose first 12/1 came earlier in the same session", lab, d, "s122_after121", "s122", "%", den_unit="sessions with 12/2",
                 note="order from fault_timestamp (device time) [inferred]; 12/2 sessions with no 12/1 count in the denominator only")
    b = S[(S.f121 == 1) & (S.f122 == 1) & S.t121.notna() & S.t122.notna()]
    gap = (b.t122 - b.t121).dt.total_seconds()
    ok = gap > 0
    K.add("ib_gap_median_s", ins_, "median seconds from first 12/1 to first 12/2 (sessions where 12/1 came first)", "all groups", float(gap[ok].median()),
          float(gap[ok].quantile(0.25)), float(gap[ok].quantile(0.75)), n_machines=b[ok].anonymized_serial.nunique(), n_events=int(ok.sum()), unit="seconds", src=SRC + ":compute_escalation",
          note="interval shown is the interquartile range, not a bootstrap; fault_timestamp is device time [inferred]")
    K.add("ib_gap_share_within_60s", ins_, "of those, % where 12/2 followed within 60 seconds", "all groups", float((gap[ok] <= 60).mean() * 100), n_machines=b[ok].anonymized_serial.nunique(),
          n_events=int((gap[ok] <= 60).sum()), den=int(ok.sum()), den_unit="sessions with 12/1 then 12/2", unit="%", src=SRC + ":compute_escalation")


def compute_wash_link(S, M, K):
    """Sessions with a Filter Wash alert vs airway blockage."""
    ins_ = "I-C wash->blockage"
    for (c, fam) in GROUPS + [("all", "all")]:
        if c == "all":
            d, sub, lab, g = M, S, "All groups", "all"
        else:
            sub = S[(S.cohort == c) & (S.family == fam)]
            d = M[M.anonymized_serial.isin(sub.anonymized_serial)]
            lab, g = GLABEL[(c, fam)], gk(c, fam)
        add_rate(K, "ic_p12_given_wash_%s" % g, ins_, "sessions with an airway blockage, % of sessions that have a Filter Wash alert", lab, d, "b_wash", "n_wash", "%", den_unit="sessions with 13/1")
        add_rate(K, "ic_p12_given_nowash_%s" % g, ins_, "sessions with an airway blockage, % of sessions with no Filter Wash alert", lab, d, "b_nowash", "n_nowash", "%", den_unit="sessions without 13/1")
        v, lo, hi, n = mh_rr_boot(d, ["b_wash", "n_wash", "b_nowash", "n_nowash"])
        K.add("ic_mh_rr_%s" % g, ins_, "risk ratio of an airway-blockage session, Filter Wash session vs not (Mantel-Haenszel, strata = machine)", lab, v, lo, hi, n_machines=n,
              n_events=float(d.b_wash.sum() + d.b_nowash.sum()), unit="ratio", src=SRC + ":compute_wash_link",
              note="compares sessions of the same machine, so machine-level differences cannot drive it; interval from resampling machines")
        sb = sub[sub.clean_duration_clean.notna()].copy()
        sb["band"] = pd.cut(sb.clean_duration_clean, [-1, 60, 300, 1e12], labels=["<=60", "61-300", ">300"])
        rows = []
        for band, dd in sb.groupby("band"):
            rows.append(dict(a=int(((dd.f12 == 1) & (dd.f13 == 1)).sum()), n1=int((dd.f13 == 1).sum()), c=int(((dd.f12 == 1) & (dd.f13 == 0)).sum()), n0=int((dd.f13 == 0).sum())))
        bt = pd.DataFrame(rows)
        K.add("ic_mh_rr_duration_%s" % g, ins_, "same risk ratio, strata = clean_duration band (<=60, 61-300, >300; unit not stated)", lab, mh_rr(bt, "a", "n1", "c", "n0"),
              n_events=float(bt.a.sum() + bt.c.sum()), unit="ratio", src=SRC + ":compute_wash_link", note="sensitivity to session length; no interval (session-level strata)")
    b = S[(S.f12 == 1) & (S.f13 == 1) & S.t12.notna() & S.t13.notna()]
    first_wash = (b.t13 < b.t12)
    K.add("ic_wash_first_share", ins_, "of sessions with both, % where the first Filter Wash alert came before the first airway blockage", "all groups", float(first_wash.mean() * 100),
          n_machines=b.anonymized_serial.nunique(), n_events=int(first_wash.sum()), den=len(b), den_unit="sessions with both", unit="%", src=SRC + ":compute_wash_link",
          note="order from fault_timestamp (device time) [inferred]; ties count as not first. Order is not cause")


def compute_duration_dust(S, K):
    ins_ = "I-D duration and dust"
    sb = S[S.clean_duration_clean.notna() & (S.clean_duration_clean > 0)].copy()
    sb["band"] = pd.cut(sb.clean_duration_clean, [0, 60, 300, 600, 1e12], labels=["le60", "61_300", "301_600", "gt600"])
    for band, d in sb.groupby("band"):
        mt = d.groupby("anonymized_serial").agg(x=("f12", "sum"), n=("f12", "size")).reset_index()
        add_rate(K, "id_block_by_band_%s" % band, ins_, "sessions with an airway blockage, % of sessions in the clean_duration band", "band %s" % band, mt, "x", "n", "%", den_unit="sessions",
                 note="clean_duration unit is not stated in the brief; bands use the raw values")
    t = []
    for ser, d in sb.groupby("anonymized_serial"):
        lo, hi = d[d.clean_duration_clean <= 60], d[d.clean_duration_clean > 300]
        t.append(dict(a=hi.f12.sum(), n1=len(hi), c=lo.f12.sum(), n0=len(lo)))
    t = pd.DataFrame(t)
    v, lo_, hi_, n = mh_rr_boot(t, ["a", "n1", "c", "n0"])
    K.add("id_mh_rr_long_vs_short", ins_, "risk ratio of an airway-blockage session, clean_duration >300 vs <=60 (Mantel-Haenszel, strata = machine)", "all groups", v, lo_, hi_, n_machines=n,
          n_events=float(t.a.sum() + t.c.sum()), unit="ratio", src=SRC + ":compute_duration_dust", note="exposure effect: a longer session has more chance to hit a fault; not a defect finding on its own")
    cols = ["ultra_fine_dust_particle_mass_clean", "fine_dust_particle_mass_clean", "coarse_dust_particle_mass_clean", "large_dust_particle_mass_clean"]
    names = ["ultra_fine", "fine", "coarse", "large"]
    d0 = sb[(sb.family == "SV53") & ~sb.flag_dust_sentinel].copy()
    d0 = d0[(d0.f12 == 1) | ((d0.f12 == 0) & (d0.f13 == 0))]      # blockage sessions vs sessions with no linked fault at all
    d0["ld"] = np.log(d0.clean_duration_clean)
    for col, nm in zip(cols, names):
        d = d0[d0[col].notna()].copy()
        d["y"] = np.log1p(d[col])
        has = d.groupby("anonymized_serial").f12.agg(["min", "max"])
        keep = has[(has["min"] == 0) & (has["max"] == 1)].index
        d = d[d.anonymized_serial.isin(keep)]
        beta, lo, hi, nm_ = within_effect(d, "y", ["f12", "ld"], "anonymized_serial")
        K.add("id_dust_effect_%s" % nm, ins_, "%s dust mass in airway-blockage sessions vs other sessions of the same machine and same log(clean_duration), %% difference" % nm.replace("_", "-"),
              "SV53 (Normal + RR)", (np.exp(beta) - 1) * 100, (np.exp(lo) - 1) * 100, (np.exp(hi) - 1) * 100, n_machines=nm_, n_events=int(d.f12.sum()), den=len(d), den_unit="sessions with a valid dust value",
              unit="% difference (log1p scale, machine fixed effects)", src=SRC + ":within_effect",
              note="dust unit is not stated; 65535 sentinel excluded [inferred]; SV50 has no dust values; machines with both session kinds only; interval from resampling machines")


def _diff_boot(a, b, col, den="ns"):
    ia, ib = boot_idx(len(a), seed=SEED), boot_idx(len(b), seed=SEED + 1)
    ra = 100 * a[col].values[ia].sum(axis=1) / a[den].values[ia].sum(axis=1)
    rb = 100 * b[col].values[ib].sum(axis=1) / b[den].values[ib].sum(axis=1)
    return np.percentile(ra - rb, [2.5, 97.5])


def compute_submodel(T, K):
    summ = T["summ"]
    ins_ = "I-E sub-model"
    e = summ[summ.rate_eligible].copy()
    e["n12"] = e.n_faults_t12_v1_primary + e.n_faults_t12_v2_primary
    e["n13"] = e.n_faults_t13_v1_primary
    e["ns"] = e.n_sessions
    for (c, model), d in e.groupby(["cohort", "model"]):
        if len(d) < 2:
            continue
        g = "%s_%s" % (c, model.replace("-", "_"))
        add_rate(K, "ie_rate12_%s" % g, ins_, "airway blockage (type 12) faults per 100 clean sessions", "%s %s" % (c, model), d, "n12", "ns", "per 100 sessions", den_unit="clean sessions")
        add_rate(K, "ie_rate13_%s" % g, ins_, "Filter Wash 13/1 faults per 100 clean sessions", "%s %s" % (c, model), d, "n13", "ns", "per 100 sessions", den_unit="clean sessions")
    N = e[e.cohort == "normal"]
    tests = [("sv53ab", N[N.model == "SV53-AB"], N[(N.family == "SV53") & (N.model != "SV53-AB")], "Normal SV53-AB vs the other Normal SV53 sub-models"),
             ("sv50aa", N[N.model == "SV50-AA"], N[(N.family == "SV50") & (N.model != "SV50-AA")], "Normal SV50-AA vs the other Normal SV50 sub-models")]
    for key, a, b, lab in tests:
        for col, nm in (("n12", "airway blockage"), ("n13", "Filter Wash 13/1")):
            diff = a[col].sum() * 100.0 / a.ns.sum() - b[col].sum() * 100.0 / b.ns.sum()
            lo, hi = _diff_boot(a, b, col)
            K.add("ie_diff_%s_%s" % (key, col), ins_, "%s: difference in faults per 100 sessions" % nm, lab, diff, lo, hi, n_machines=len(a) + len(b),
                  n_events=float(a[col].sum() + b[col].sum()), unit="per 100 sessions", src=SRC + ":compute_submodel")
            K.add("ie_permp_%s_%s" % (key, col), ins_, "%s: permutation p-value for that difference (rough guide only, many cuts made)" % nm, lab, perm_p(a, b, col, "ns"), n_machines=len(a) + len(b),
                  unit="p-value", src=SRC + ":perm_p", note="20,000 label shuffles across machines")
    s53 = e[e.family == "SV53"]
    for c in ("normal", "return_repair"):
        d = s53[s53.cohort == c]
        n_ab = int((d.model == "SV53-AB").sum())
        K.add("ie_ab_share_%s" % c, ins_, "share of rate-eligible SV53 machines that are SV53-AB", c, n_ab / float(len(d)) * 100, n_machines=len(d), n_events=n_ab, den=len(d), den_unit="machines", unit="%", src=SRC + ":compute_submodel")
    subs = ["SV53-AB", "SV53-AC", "SV53-AE", "SV53-AF"]
    nm = s53[(s53.cohort == "normal") & s53.model.isin(subs)]
    rr = s53[(s53.cohort == "return_repair") & s53.model.isin(subs)]
    w = nm.groupby("model").ns.sum()
    w = w / w.sum()

    def std_rate(d, idx):
        r = 0.0
        for m_ in subs:
            dm = d[d.model == m_]
            ii = idx[m_]
            r += w[m_] * 100 * dm.n12.values[ii].sum() / dm.ns.values[ii].sum()
        return r

    rng = np.random.RandomState(SEED)
    res = {}
    for label, d in (("normal", nm), ("return_repair", rr)):
        base = dict((m_, np.arange(int((d.model == m_).sum()))) for m_ in subs)
        v0 = std_rate(d, base)
        bs = []
        for _ in range(N_BOOT):
            idx = dict((m_, rng.randint(0, len(base[m_]), len(base[m_]))) for m_ in subs)
            bs.append(std_rate(d, idx))
        bs = np.array(bs)
        res[label] = (v0, np.percentile(bs, [2.5, 97.5]), bs)
        K.add("ie_std_rate12_%s" % label, ins_, "airway blockage per 100 sessions, SV53 sub-models AB/AC/AE/AF re-weighted to the Normal sessions mix", label, v0, res[label][1][0], res[label][1][1],
              n_machines=len(d), n_events=float(d.n12.sum()), unit="per 100 sessions", src=SRC + ":compute_submodel",
              note="direct standardisation; weights = Normal share of sessions per sub-model; SV53-AA left out (no eligible RR machine)")
    ratio_b = res["return_repair"][2] / res["normal"][2]
    K.add("ie_std_ratio", ins_, "RR / Normal airway-blockage rate after re-weighting to the same sub-model mix", "SV53", res["return_repair"][0] / res["normal"][0],
          float(np.percentile(ratio_b, 2.5)), float(np.percentile(ratio_b, 97.5)), n_machines=len(nm) + len(rr), unit="ratio", src=SRC + ":compute_submodel")
    crude = dict((c, s53[s53.cohort == c].n12.sum() * 100.0 / s53[s53.cohort == c].ns.sum()) for c in ("normal", "return_repair"))
    K.add("ie_crude_ratio", ins_, "RR / Normal airway-blockage rate, all SV53 machines, no re-weighting", "SV53", crude["return_repair"] / crude["normal"], n_machines=len(s53), unit="ratio", src=SRC + ":compute_submodel",
          note="same quantity as first-round i2_ratio_t12_main")
    ab_rr = s53[(s53.model == "SV53-AB") & (s53.cohort == "return_repair")].sort_values("n12")
    ab_n = s53[(s53.model == "SV53-AB") & (s53.cohort == "normal")]
    for key, lab, a in (("all", "all", ab_rr), ("drop_top", "without the RR machine with most events", ab_rr.iloc[:-1])):
        diff = a.n12.sum() * 100.0 / a.ns.sum() - ab_n.n12.sum() * 100.0 / ab_n.ns.sum()
        lo, hi = _diff_boot(a, ab_n, "n12")
        K.add("ie_ab_rr_minus_normal_%s" % key, ins_, "SV53-AB airway blockage per 100 sessions, RR minus Normal (%s)" % lab, "SV53-AB", diff, lo, hi,
              n_machines=len(a) + len(ab_n), n_events=float(a.n12.sum() + ab_n.n12.sum()), unit="per 100 sessions", src=SRC + ":compute_submodel")
    for c in ("normal", "return_repair"):
        d = s53[s53.cohort == c]
        K.add("ie_top1_share_%s" % c, ins_, "share of SV53 airway-blockage events from the single machine with most events", c, d.n12.max() / float(d.n12.sum()) * 100,
              n_machines=len(d), n_events=float(d.n12.max()), den=float(d.n12.sum()), den_unit="airway blockage events", unit="%", src=SRC + ":compute_submodel")


def compute_battery(T, K):
    sess, batt = T["sess"], T["batt"]
    ins_ = "I-F battery temperature"
    for (c, fam) in GROUPS:
        d = sess[(sess.cohort == c) & (sess.family == fam)]
        mt = d.groupby("anonymized_serial").agg(x=("battery_temp_state", lambda s: int((s == "not_reported").sum())), n=("battery_temp_state", "size")).reset_index()
        add_rate(K, "if_notrep_%s" % gk(c, fam), ins_, "sessions where no battery-temperature flag (hot, cold, ok) is true, % of sessions", GLABEL[(c, fam)], mt, "x", "n", "%", den_unit="analysis sessions",
                 note="'not reported' is our label for all three flags false; the brief gives no meaning for that state")
        nh = int((d.battery_temp_state == "hot").sum())
        nc = int((d.battery_temp_state == "cold").sum())
        K.add("if_hot_%s" % gk(c, fam), ins_, "sessions flagged battery temperature HOT", GLABEL[(c, fam)], nh, n_machines=d[d.battery_temp_state == "hot"].anonymized_serial.nunique(), n_events=nh, den=len(d),
              den_unit="analysis sessions", unit="sessions", src=SRC + ":compute_battery")
        K.add("if_cold_%s" % gk(c, fam), ins_, "sessions flagged battery temperature COLD", GLABEL[(c, fam)], nc, n_events=nc, den=len(d), den_unit="analysis sessions", unit="sessions", src=SRC + ":compute_battery")
    sv = sess[sess.family == "SV50"].copy()
    sv["nr"] = (sv.battery_temp_state == "not_reported").astype(int)
    sv["band"] = pd.cut(sv.battery_charge_start_clean, [-1, 40, 80, 100], labels=["0_40", "41_80", "81_100"])
    for band, d in sv.groupby("band"):
        mt = d.groupby("anonymized_serial").agg(x=("nr", "sum"), n=("nr", "size")).reset_index()
        add_rate(K, "if_notrep_sv50_start_%s" % band, ins_, "SV50 sessions with no temperature flag, % of sessions by battery_charge_start band", "start charge %s" % band.replace("_", "-"), mt, "x", "n", "%",
                 den_unit="SV50 sessions", note="coverage is low in every band")
    b = batt[batt.delta_valid.fillna(False).astype(bool)].copy()
    dall = [c for c in b.columns if c.startswith("delta_discharge_band_")]
    dh = [c for c in dall if c.endswith("gt_45C")]
    call = [c for c in b.columns if c.startswith("delta_charge_band_")]
    ch = [c for c in call if c.endswith("gt_45C")]
    assert len(dh) == 3 and len(dall) == 9 and len(ch) == 3 and len(call) == 9, (dh, ch)
    b["dis_hot"], b["dis_all"] = b[dh].sum(axis=1), b[dall].sum(axis=1)
    b["chg_hot"], b["chg_all"] = b[ch].sum(axis=1), b[call].sum(axis=1)
    pcols = ["delta_discharge_power_lt_95_W", "delta_discharge_power_95_250_W", "delta_discharge_power_gt_250_W"]
    b["p_hi"], b["p_all"] = b["delta_discharge_power_gt_250_W"], b[pcols].sum(axis=1)
    mb = b.groupby(["anonymized_serial", "cohort", "family"]).agg(dis_hot=("dis_hot", "sum"), dis_all=("dis_all", "sum"), chg_hot=("chg_hot", "sum"), chg_all=("chg_all", "sum"),
                                                                 p_hi=("p_hi", "sum"), p_all=("p_all", "sum")).reset_index()
    mb = mb[mb.family.isin(["SV50", "SV53"])]
    for (c, fam) in GROUPS:
        d = mb[(mb.cohort == c) & (mb.family == fam)]
        g = gk(c, fam)
        add_rate(K, "if_dis_hot_%s" % g, ins_, "discharge time above 45 C, % of discharge seconds (voltage x temperature band bins)", GLABEL[(c, fam)], d, "dis_hot", "dis_all", "%", den_unit="discharge seconds",
                 note="BMS bin definition dischargeBandBins: unit second, temperature edges 15 and 45 celsius (stated); pooled over valid battery periods")
        add_rate(K, "if_chg_hot_%s" % g, ins_, "charge time above 45 C, % of charge seconds", GLABEL[(c, fam)], d, "chg_hot", "chg_all", "%", den_unit="charge seconds")
        any_hot = int((d.dis_hot > 0).sum())
        K.add("if_any_hot_%s" % g, ins_, "machines with any discharge time above 45 C, % of machines with a valid battery period", GLABEL[(c, fam)], any_hot / float(len(d)) * 100, n_machines=len(d), n_events=any_hot, den=len(d),
              den_unit="machines", unit="%", src=SRC + ":compute_battery")
    s50, s53_ = mb[mb.family == "SV50"], mb[mb.family == "SV53"]
    a, bb = int((s50.dis_hot > 0).sum()), int((s50.dis_hot == 0).sum())
    c_, d_ = int((s53_.dis_hot > 0).sum()), int((s53_.dis_hot == 0).sum())
    K.add("if_fisher_any_hot", ins_, "Fisher exact p: SV50 vs SV53 machines with any discharge time above 45 C (rough guide only)", "SV50 vs SV53 (both cohorts)", fisher_two_sided(a, bb, c_, d_),
          n_machines=len(s50) + len(s53_), unit="p-value", src=SRC + ":fisher_two_sided", note="SV50 %d of %d machines vs SV53 %d of %d" % (a, a + bb, c_, c_ + d_))
    K.add("if_any_hot_sv53_all", ins_, "SV53 machines (Normal + RR) with any discharge time above 45 C", "SV53", c_ / float(c_ + d_) * 100, n_machines=c_ + d_, n_events=c_, den=c_ + d_, den_unit="machines", unit="%", src=SRC + ":compute_battery")
    add_rate(K, "if_dis_hot_sv53_all", ins_, "discharge time above 45 C, % of discharge seconds", "SV53 (Normal + RR)", s53_, "dis_hot", "dis_all", "%", den_unit="discharge seconds")
    top = s50.sort_values("dis_hot").iloc[-1]
    rest = s50[s50.anonymized_serial != top.anonymized_serial]
    add_rate(K, "if_dis_hot_sv50_drop_top", ins_, "discharge time above 45 C, % of discharge seconds, without the SV50 machine with the most hot time", "SV50 without top machine", rest, "dis_hot", "dis_all", "%",
             den_unit="discharge seconds")
    K.add("if_top1_share_sv50", ins_, "share of SV50 hot discharge seconds held by the single machine with the most", "SV50", top.dis_hot / float(s50.dis_hot.sum()) * 100, n_machines=len(s50), n_events=float(top.dis_hot),
          den=float(s50.dis_hot.sum()), den_unit="hot discharge seconds", unit="%", src=SRC + ":compute_battery")
    pk = b.groupby(["family", "pack_type"]).anonymized_serial.nunique().reset_index()
    for _, r in pk[pk.family.isin(["SV50", "SV53"])].iterrows():
        K.add("if_pack_%s_%s" % (r.family, str(r.pack_type).replace("-", "_")), ins_, "machines with a valid battery period by pack type (from the battery payload)", "%s %s" % (r.family, r.pack_type),
              int(r.anonymized_serial), n_machines=int(r.anonymized_serial), unit="machines", src=SRC + ":compute_battery")
    for fam in ("SV50", "SV53"):
        d = mb[mb.family == fam]
        add_rate(K, "if_power_hi_%s" % fam, ins_, "discharge time above 250 W, % of discharge seconds", fam, d, "p_hi", "p_all", "%", den_unit="discharge seconds", note="powerBins edges 95 and 250 watt (stated)")


def compute_trend(S, K):
    ins_ = "I-G trend in use"
    s = S.copy()
    s["win"] = np.where(s.date_server < pd.Timestamp("2026-01-01"), "early", np.where(s.date_server >= pd.Timestamp("2026-04-01"), "late", "mid"))
    for fam in ("SV50", "SV53"):
        d = s[(s.family == fam) & (s.win != "mid")]
        pv = d.groupby(["anonymized_serial", "win"]).agg(n=("f12", "size"), b=("f12", "sum"), w=("f13", "sum")).unstack("win").dropna()
        pv = pv[(pv[("n", "early")] >= 15) & (pv[("n", "late")] >= 15)]
        for col, lab, key in (("w", "Filter Wash 13/1 alert", "wash"), ("b", "airway blockage", "block")):
            e_ = pv[(col, "early")] / pv[("n", "early")]
            l_ = pv[(col, "late")] / pv[("n", "late")]
            rise, fall = int((l_ > e_).sum()), int((l_ < e_).sum())
            te = pd.DataFrame({"x": pv[(col, "early")].values, "n": pv[("n", "early")].values})
            tl = pd.DataFrame({"x": pv[(col, "late")].values, "n": pv[("n", "late")].values})
            ve, vl = pooled_share(te, "x", "n"), pooled_share(tl, "x", "n")
            K.add("ig_early_%s_%s" % (key, fam), ins_, "%% of sessions with a %s, Oct-Dec 2025, machines observed in both windows" % lab, fam, ve[0], ve[1], ve[2], n_machines=len(pv),
                  n_events=float(te.x.sum()), den=float(te.n.sum()), den_unit="sessions", unit="%", src=SRC + ":compute_trend", note="windows by session server date; machines need >= 15 sessions in each window")
            K.add("ig_late_%s_%s" % (key, fam), ins_, "%% of sessions with a %s, Apr-Jun 2026, same machines" % lab, fam, vl[0], vl[1], vl[2], n_machines=len(pv),
                  n_events=float(tl.x.sum()), den=float(tl.n.sum()), den_unit="sessions", unit="%", src=SRC + ":compute_trend")
            K.add("ig_rise_share_%s_%s" % (key, fam), ins_, "machines whose %s rate is higher in Apr-Jun than in Oct-Dec, %% of machines with a change" % lab, fam, rise / float(max(rise + fall, 1)) * 100,
                  n_machines=len(pv), n_events=rise, den=rise + fall, den_unit="machines with a change", unit="%", src=SRC + ":compute_trend",
                  note=("exact sign-test p = %.4g (rough guide)" % exact_binom_p(rise, rise + fall)) if rise + fall else "")


def compute(T=None):
    T = T or load()
    T["ff"] = link_faults(T["sess"], T["ff"])
    ff2 = T["ff"]
    S = session_table(T["sess"], ff2)
    K = ins.KeyNumbers()
    n_f, n_l = len(ff2), int(ff2.sess_key2.notna().sum())
    K.add("link_faults_linked", "Method", "faults linked to a session on serial + session_id with server dates within 24 h", "all", n_l / float(n_f) * 100, n_events=n_l, den=n_f, den_unit="fault occurrences",
          unit="%", src=SRC + ":link_faults", note="fault server date is read from data/clean/dq/faults.parquet")
    lk = ff2[ff2.sess_key2.notna()]
    K.add("link_gap_within_1h", "Method", "of linked faults, % whose server date is within 1 hour of the session server date", "all", float((lk.link_gap_server_h <= 1).mean() * 100),
          n_events=int((lk.link_gap_server_h <= 1).sum()), den=len(lk), den_unit="linked faults", unit="%", src=SRC + ":link_faults")
    fts = lk.merge(T["sess"][["session_key", "date_server"]], left_on="sess_key2", right_on="session_key", how="inner", suffixes=("", "_s"))
    K.add("link_fault_ts_lag_median_h", "Method", "median hours from fault_timestamp (device time) to the server date of its session", "all",
          float(((fts.date_server - fts.fault_timestamp).dt.total_seconds() / 3600).median()), unit="hours", src=SRC + ":link_faults",
          note="why the nearest-date rule in fact_fault.session_key is only approximate")
    M = machine_table(S)
    compute_context(T, K)
    compute_fault_anatomy(T, K)
    compute_escalation(S, M, K)
    compute_wash_link(S, M, K)
    compute_duration_dust(S, K)
    compute_submodel(T, K)
    compute_battery(T, K)
    compute_trend(S, K)
    return dict(key=K.frame(), S=S, M=M, T=T)


def write(R):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / "key_numbers_v2.csv"
    R["key"].to_csv(str(p), index=False, float_format="%.6g")
    return p


def main():
    R = compute()
    p = write(R)
    print("wrote", p, "(%d rows)" % len(R["key"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
