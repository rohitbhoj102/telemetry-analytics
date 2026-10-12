"""Dashboard data: one long-format CSV for the four final insights, built only from f_ rows of key_numbers.csv.

Writes data/model/tableau/insights_dashboard.csv (next to the other Tableau CSVs) and a copy at
dashboard/data/insights_dashboard.csv (small, derived from key_numbers.csv only, so it can be committed). No statistic is recomputed:
value, low, high and n_machines are copied from key_numbers.csv by id; label_text is formatted from them.
Then re-reads both files and checks every copied value against key_numbers.csv at full stored precision.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
KEY = ROOT / "reports" / "insights" / "key_numbers.csv"
OUT = ROOT / "data" / "model" / "tableau" / "insights_dashboard.csv"
COPY = ROOT / "dashboard" / "data" / "insights_dashboard.csv"
COLS = ["deck_order", "insight_id", "insight_title", "chart", "bar_label", "bar_order", "value", "low", "high",
        "unit", "n_machines", "role", "label_text", "source_id"]

I1 = "Blockages cluster around filter reminders"
I4 = "The SV53 rarely warns before a blockage error"
I3 = "Returned SV53s log 3–5x more blockages, led by SV53-AB"
I2 = "The SV50 sends no battery temperature in most cleans"

# (deck_order, insight_id, title, chart, bar_label, source_id, unit, role, n_machines_source_id or None, label_override)
SPEC = [
    (1, "I1", I1, "same_clean", "Clean with reminder", "f_i1_p12_given_wash_all", "pct", "focus", None, None),
    (1, "I1", I1, "same_clean", "Clean without reminder", "f_i1_p12_given_nowash_all", "pct", "baseline", None, None),
    (1, "I1", I1, "lead_7d", "Normal SV50", "f_i1_lead_adjratio_sessionspan_7d_normal_SV50", "ratio", "focus", None, None),
    (1, "I1", I1, "lead_7d", "Normal SV53", "f_i1_lead_adjratio_sessionspan_7d_normal_SV53", "ratio", "focus", None, None),
    (1, "I1", I1, "lead_7d", "Return/Repair SV53", "f_i1_lead_adjratio_sessionspan_7d_return_repair_SV53", "ratio", "focus", None, None),
    (1, "I1", I1, "headline", "Same-session risk ratio", "f_i1_samesession_rr_all", "ratio", "focus", None, None),
    (2, "I4", I4, "warned_first", "SV50", "f_i4_prior121_share_normal_SV50", "pct", "baseline", None, None),
    (2, "I4", I4, "warned_first", "SV53", "f_i4_prior121_share_normal_SV53", "pct", "focus", None, None),
    (2, "I4", I4, "headline", "SV50 minus SV53 (pp)", "f_i4_prior121_diff_sv50_minus_sv53_normal", "pct", "focus", None, "pp"),
    (3, "I3", I3, "submodel", "SV53-AB", "f_i3_rate12_normal_SV53_AB", "per100", "focus", "f_i3_machines_normal_SV53_AB", None),
    (3, "I3", I3, "submodel", "SV53-AE", "f_i3_rate12_normal_SV53_AE", "per100", "baseline", "f_i3_machines_normal_SV53_AE", None),
    (3, "I3", I3, "submodel", "SV53-AF", "f_i3_rate12_normal_SV53_AF", "per100", "baseline", "f_i3_machines_normal_SV53_AF", None),
    (3, "I3", I3, "submodel", "SV53-AC", "f_i3_rate12_normal_SV53_AC", "per100", "baseline", "f_i3_machines_normal_SV53_AC", None),
    (3, "I3", I3, "ratio", "As recorded", "f_i3_crude_ratio", "ratio", "baseline", None, None),
    (3, "I3", I3, "ratio", "Same sub-model mix", "f_i3_std_ratio", "ratio", "focus", None, None),
    (4, "I2", I2, "no_temp", "Normal SV50", "f_i2_notrep_pct_normal_SV50", "pct", "gap", None, None),
    (4, "I2", I2, "no_temp", "Normal SV53", "f_i2_notrep_pct_normal_SV53", "pct", "baseline", None, None),
    (4, "I2", I2, "no_temp", "Return/Repair SV53", "f_i2_notrep_pct_return_repair_SV53", "pct", "baseline", None, None),
    (4, "I2", I2, "hot_batteries", "SV50", "f_i2_any_hot_machines_normal_SV50", "pct", "baseline", None, "of"),
    (4, "I2", I2, "hot_batteries", "SV53 (all)", "f_i2_any_hot_machines_sv53_all", "pct", "baseline", None, "of"),
]


def fmt(v, unit):
    return {"pct": "%.1f%%", "ratio": "%.1fx", "per100": "%.1f", "count": "%.0f"}[unit] % v


def label(row, unit, special):
    v, lo, hi = float(row["value"]), row["interval_low"], row["interval_high"]
    if special == "of":  # "9 of 15": machines with any hot discharge of machines with battery data (both from key_numbers)
        return "%d of %d" % (float(row["n_events_or_sessions"]), float(row["n_machines"]))
    if special == "pp":
        txt = "%.1f pp" % v
    else:
        txt = fmt(v, unit)
    if pd.notna(lo) and pd.notna(hi):
        lo, hi = float(lo), float(hi)
        n = lambda x: fmt(x, unit).rstrip("%x") if unit != "count" else fmt(x, unit)
        txt += " [%s–%s]" % (n(lo), n(hi))
    return txt


def build():
    k = pd.read_csv(KEY, dtype=str).set_index("id")  # text as stored: values are copied verbatim, never re-rounded
    need = [s[5] for s in SPEC] + [s[8] for s in SPEC if s[8]]
    missing = [i for i in need if i not in k.index]
    if missing:
        sys.exit("STOP: ids not in key_numbers.csv: %s" % missing)
    rows = []
    for (do, iid, title, chart, bl, sid, unit, role, nsid, special) in SPEC:
        r = k.loc[sid]
        n_src = k.loc[nsid] if nsid else r
        rows.append(dict(deck_order=do, insight_id=iid, insight_title=title, chart=chart, bar_label=bl, bar_order=0,
                         value=r["value"], low=r["interval_low"], high=r["interval_high"], unit=unit,
                         n_machines=n_src["n_machines"], role=role, label_text=label(r, unit, special), source_id=sid))
    df = pd.DataFrame(rows, columns=COLS)
    df["bar_order"] = df.groupby(["insight_id", "chart"]).cumcount() + 1
    return df, k


def check(k):
    out = pd.read_csv(OUT, dtype=str, keep_default_na=False, na_values=[""])
    ok_all = True
    print("%-62s %-8s %-6s %s" % ("source_id", "value", "low/hi", "n_machines"))
    for _, r in out.iterrows():
        s = k.loc[r["source_id"]]
        nsrc = s
        if r["source_id"].startswith("f_i3_rate12_"):
            nsrc = k.loc[r["source_id"].replace("rate12", "machines")]
        eq = lambda a, b: (pd.isna(a) and pd.isna(b)) or a == b  # string equality = full stored precision
        v = eq(r["value"], s["value"])
        b = eq(r["low"], s["interval_low"]) and eq(r["high"], s["interval_high"])
        n = eq(r["n_machines"], nsrc["n_machines"])
        ok_all &= v and b and n
        print("%-62s %-8s %-6s %s" % (r["source_id"], "PASS" if v else "FAIL", "PASS" if b else "FAIL", "PASS" if n else "FAIL"))
    print("ALL PASS" if ok_all else "CHECK FAILED")
    return ok_all


def main():
    df, k = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    COPY.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(COPY, index=False)
    print("wrote %s (%d rows)" % (OUT.relative_to(ROOT), len(df)))
    same = OUT.read_bytes() == COPY.read_bytes()
    print("copy at %s identical: %s" % (COPY.relative_to(ROOT), same))
    return 0 if check(k) and same else 1


if __name__ == "__main__":
    sys.exit(main())
