"""One clean chart per final insight (I1 to I4) in reports/figures/final_v2/ (PNG + SVG).

Every printed number is read from the `f_` rows of reports/insights/key_numbers.csv and checked
against the file (insights.Printed logic, adapted because the file now holds rows from several scripts).
Run after src/insights_final.py (src/run_all.py does this). Python 3.8 compatible.
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import charts2 as c2  # noqa: E402
import insights as ins  # noqa: E402

ROOT = ins.ROOT
KEY = ROOT / "reports" / "insights" / "key_numbers.csv"
FIG_DIR = ROOT / "reports" / "figures" / "final_v2"
BASE, ACCENT, DARK, BLUE, ORANGE, INK, GREY = c2.BASE, c2.ACCENT, c2.DARK, c2.BLUE, c2.ORANGE, c2.INK, c2.GREY
GROUPS = [("normal_SV50", "Normal SV50", DARK), ("normal_SV53", "Normal SV53", BLUE), ("return_repair_SV53", "Return/Repair SV53", ORANGE)]
EXTRA_STATIC = {"2025", "2026", "45", "60", "7", "1", "24", "30", "100", "10", "3"}


class FinalPrinted(ins.Printed):
    """Printed numbers must equal the f_ rows of key_numbers.csv; the file is the single source (no recomputation)."""

    def __init__(self, path):
        ins.Printed.__init__(self, path)
        self.STATIC = set(ins.Printed.STATIC) | EXTRA_STATIC

    def verify(self, fig, name, R=None):
        fresh = pd.read_csv(self.path).set_index("id")
        fresh_raw = pd.read_csv(self.path, dtype=str).set_index("id")
        bad = []
        for id_, field, nd, comma, s in self.log:
            exp = ins.about(float(fresh.loc[id_, field])) if nd == -1 else ins._fmt_csv(fresh_raw.loc[id_, field], nd, comma)
            if exp != s:
                bad.append((id_, field, s, exp))
        assert not bad, "%s: printed number differs from key_numbers.csv: %s" % (name, bad)
        texts = [t.get_text() for t in fig.texts]
        for ax in fig.axes:
            texts += [t.get_text() for t in ax.texts] + [ax.get_title(), ax.get_xlabel(), ax.get_ylabel()]
            texts += [t.get_text() for t in ax.get_xticklabels() if not re.fullmatch(r"[-−]?[\d.,]+", t.get_text())]
            leg = ax.get_legend()
            if leg:
                texts += [t.get_text() for t in leg.get_texts()]
        stray = []
        for tx in texts:
            for pat in self.STRIP:
                tx = re.sub(pat, " ", tx)
            for tok in re.findall(self.TOKEN, tx):
                if tok not in self.reg and tok not in self.STATIC:
                    stray.append(tok)
        assert not stray, "%s: numbers printed on the chart that are not from key_numbers.csv: %s" % (name, sorted(set(stray)))
        return len(self.log)


def _dot(ax, P, y, id_, color, nd=1, label_suffix="", hollow=False, dx=0.0):
    v, lo, hi = P.k.loc[id_, ["value", "interval_low", "interval_high"]]
    ax.hlines(y, lo, hi, color=color, lw=2)
    ax.plot(v, y, "o", color="white" if hollow else color, ms=10, mec=color, mew=2)
    return v, lo, hi


def chart_i1(P):
    plt = ins._setup()
    from matplotlib.patches import Patch
    fig = ins._frame(plt, "A Filter Wash alert goes with airway blockages: in the same session, and in the days after",
                     "Left: share of sessions with an airway blockage, with and without a Filter Wash alert in the same session (machine-level risk ratio, all groups: %sx [%s to %s], %s machines). "
                     "Right: blockage rate in the 7 days after an alert compared with other times on the same machine" % (
                         P.num("f_i1_samesession_rr_all", nd=1), P.num("f_i1_samesession_rr_all", "interval_low", 1), P.num("f_i1_samesession_rr_all", "interval_high", 1), P.count("f_i1_samesession_rr_all")),
                     "Source: fact_session, fact_fault (faults linked to sessions on serial + session_id with matching server dates); analysis rows. Right panel: 7-day window after a Filter Wash alert, compared within each machine and "
                     "calendar month; 'starting 1 hour later' removes the alert's own session. 95% intervals from resampling machines (2,000). Order is not cause. Return/Repair is a selected population.")
    ax1 = fig.add_axes([0.07, 0.27, 0.40, 0.38])
    items = []
    for i, (g, lab, col) in enumerate(GROUPS):
        items += [(i - 0.2, "f_i1_p12_given_nowash_" + g, BASE), (i + 0.2, "f_i1_p12_given_wash_" + g, ACCENT)]
    c2._bars(ax1, P, items, nd=1)
    ax1.set_ylim(0, 58)
    ax1.set_xticks(range(3)); ax1.set_xticklabels(["Normal\nSV50", "Normal\nSV53", "Return/Repair\nSV53"], fontsize=13)
    c2._clean(ax1, "Sessions with an airway blockage (%)")
    ax1.legend(handles=[Patch(color=BASE, label="No Filter Wash alert in the session"), Patch(color=ACCENT, label="Filter Wash alert in the session")], frameon=False, loc="upper left", fontsize=12)
    ax2 = fig.add_axes([0.62, 0.27, 0.34, 0.38])
    fig.text(0.62, 0.69, "filled = 7 days from the alert; hollow = starting 1 hour later", fontsize=12, color=GREY)
    for i, (g, lab, col) in enumerate(GROUPS):
        y = 2 - i
        v, lo, hi = _dot(ax2, P, y + 0.12, "f_i1_lead_adjratio_sessionspan_7d_" + g, col)
        ax2.text(hi + 0.15, y + 0.12, "%s (%s machines)" % (P.num("f_i1_lead_adjratio_sessionspan_7d_" + g, nd=1), P.count("f_i1_lead_adjratio_sessionspan_7d_" + g)), va="center", fontsize=12, color=INK)
        v, lo, hi = _dot(ax2, P, y - 0.18, "f_i1_lead_adjratio_sessionspan_lag1h_7d_" + g, col, hollow=True)
        ax2.text(hi + 0.15, y - 0.18, P.num("f_i1_lead_adjratio_sessionspan_lag1h_7d_" + g, nd=1), va="center", fontsize=12, color=GREY)
    ax2.axvline(1, color=GREY, lw=1, ls="--")
    ax2.set_yticks([2, 1, 0]); ax2.set_yticklabels(["Normal SV50", "Normal SV53", "Return/Repair\nSV53"], fontsize=13)
    ax2.set_xlim(0, 10); ax2.tick_params(axis="y", length=0)
    ax2.set_xlabel("Times the usual blockage rate\n(dashed line = no difference)", color=GREY, fontsize=12)
    P.verify(fig, "f_i1")
    return ins._save(fig, "i1_filter_wash_alert_and_airway_blockage", FIG_DIR)


def chart_i2(P):
    plt = ins._setup()
    fig = ins._frame(plt, "SV50 is missing fields, and the heat it does report is concentrated: no temperature flag in three of four sessions, no dust at all",
                     "Battery packs with any discharge time above 45 C: %s of %s SV50 machines vs %s of %s SV53 machines. One SV50 machine holds %s%% of SV50 hot time; without it SV50 is still about %sx SV53 (interval %s to %s)" % (
                         P.count("f_i2_any_hot_machines_normal_SV50", "n_events_or_sessions"), P.count("f_i2_any_hot_machines_normal_SV50"), P.count("f_i2_any_hot_machines_sv53_all", "n_events_or_sessions"),
                         P.count("f_i2_any_hot_machines_sv53_all"), P.num("f_i2_top1_share_sv50", nd=0), P.num("f_i2_ratio_hot_sv50_drop_top_vs_sv53", nd=0),
                         P.num("f_i2_ratio_hot_sv50_drop_top_vs_sv53", "interval_low", 1), P.num("f_i2_ratio_hot_sv50_drop_top_vs_sv53", "interval_high", 0)),
                     "Source: fact_session (analysis sessions); fact_battery_period (BMS discharge band bins, unit second, temperature edges 15 and 45 C per BMS_Bins.json), valid periods; SV50 = %s battery machines, SV53 = %s. "
                     "'No flag' = hot, cold and ok are all false (meaning not stated). Data-quality and exposure result only; no cause is claimed. 95%% intervals from resampling machines." % (
                         P.count("f_i2_battery_machines_SV50"), P.count("f_i2_battery_machines_SV53")))
    ax1 = fig.add_axes([0.07, 0.2, 0.25, 0.45])
    c2._bars(ax1, P, [(0, "f_i2_notrep_pct_normal_SV50", DARK), (1, "f_i2_notrep_pct_normal_SV53", BLUE), (2, "f_i2_notrep_pct_return_repair_SV53", ORANGE)], nd=0, width=0.6, ymax=100)
    ax1.set_xticks(range(3)); ax1.set_xticklabels(["Normal\nSV50", "Normal\nSV53", "Return/\nRepair SV53"], fontsize=12)
    c2._clean(ax1, "Sessions with no temperature flag (%)")
    ax2 = fig.add_axes([0.40, 0.2, 0.22, 0.45])
    c2._bars(ax2, P, [(0, "f_i2_dust_available_pct_SV50", DARK), (1, "f_i2_dust_available_pct_SV53", BLUE)], nd=0, width=0.6, ymax=100)
    ax2.set_xticks(range(2)); ax2.set_xticklabels(["SV50", "SV53"], fontsize=13)
    c2._clean(ax2, "Sessions with a dust reading (%)")
    ax3 = fig.add_axes([0.72, 0.2, 0.26, 0.45])
    c2._bars(ax3, P, [(0, "f_i2_dis_hot_pct_normal_SV50", DARK), (1, "f_i2_dis_hot_pct_sv50_drop_top", DARK), (2, "f_i2_dis_hot_pct_sv53_all", BLUE)], nd=2, width=0.6)
    ax3.set_xticks(range(3)); ax3.set_xticklabels(["SV50", "SV50 without\ntop machine", "SV53"], fontsize=12)
    c2._clean(ax3, "Battery discharge time above 45 C (%)")
    P.verify(fig, "f_i2")
    return ins._save(fig, "i2_sv50_missing_fields_and_battery_heat", FIG_DIR)


def chart_i3(P):
    plt = ins._setup()
    rows = [("Normal SV53-AB", "f_i3_rate12_normal_SV53_AB", BLUE), ("Normal SV53-AC", "f_i3_rate12_normal_SV53_AC", BLUE), ("Normal SV53-AE", "f_i3_rate12_normal_SV53_AE", BLUE),
            ("Normal SV53-AF", "f_i3_rate12_normal_SV53_AF", BLUE), ("Return/Repair SV53-AB", "f_i3_rate12_return_repair_SV53_AB", ORANGE), ("Return/Repair SV53-AF", "f_i3_rate12_return_repair_SV53_AF", ORANGE)]
    fig = ins._frame(plt, "Airway blockage concentrates in sub-model SV53-AB, and part of the Return/Repair gap is sub-model mix",
                     "Left: airway blockages per 100 clean sessions by SV53 sub-model. Right: Return/Repair divided by Normal blockage rate, as recorded and after weighting both to the same sub-model mix. "
                     "SV53-AB is %s%% of Normal and %s%% of Return/Repair machines" % (P.num("f_i3_ab_share_normal", nd=0), P.num("f_i3_ab_share_return_repair", nd=0)),
                     "Source: machine_summary, rate-eligible machines (>= 10 sessions); sub-models with fewer than 3 machines not shown. Re-weighting: direct standardisation of AB, AC, AE and AF to the Normal share of sessions. "
                     "Sub-model codes have no stated meaning. Exploratory; intervals are wide and overlap. 95% intervals from resampling machines.")
    ax = fig.add_axes([0.20, 0.2, 0.38, 0.45])
    for i, (lab, id_, col) in enumerate(rows):
        y = len(rows) - 1 - i
        v, lo, hi = _dot(ax, P, y, id_, col)
        ax.text(hi + 0.8, y, "%s (%s machines)" % (P.num(id_, nd=1), P.count(id_)), va="center", fontsize=12, color=INK)
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows][::-1], fontsize=12)
    ax.set_xlim(0, 75); ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Airway blockages per 100 clean sessions", color=GREY)
    ax2 = fig.add_axes([0.76, 0.2, 0.21, 0.45])
    for y, (lab, id_, col) in enumerate([("Re-weighted to the\nsame sub-model mix", "f_i3_std_ratio", ACCENT), ("As recorded\n(no re-weighting)", "f_i3_crude_ratio", BASE)]):
        v, lo, hi = _dot(ax2, P, y, id_, col)
        ax2.text(min(hi, 15) + 0.4, y + 0.22, "%s [%s to %s]" % (P.num(id_, nd=1), P.num(id_, "interval_low", 1), P.num(id_, "interval_high", 1)), va="center", ha="right" if hi > 12 else "left", fontsize=12, color=INK)
    ax2.axvline(1, color=GREY, lw=1, ls="--")
    ax2.set_yticks([0, 1]); ax2.set_yticklabels(["Re-weighted to the\nsame sub-model mix", "As recorded\n(no re-weighting)"], fontsize=12)
    ax2.set_ylim(-0.6, 1.6); ax2.set_xlim(0, 16); ax2.tick_params(axis="y", length=0)
    ax2.set_xlabel("Return/Repair rate divided by\nNormal rate (times)", color=GREY, fontsize=12)
    P.verify(fig, "f_i3")
    return ins._save(fig, "i3_sub_model_and_return_repair_gap", FIG_DIR)


def chart_i4(P):
    plt = ins._setup()
    fig = ins._frame(plt, "On SV50 a blockage almost always shows a 'motor still running' warning first; on SV53 it mostly does not",
                     "Normal machines only, so the two models are compared on the same cohort. %s%% (SV50) and %s%% (SV53) of warnings become an error, a difference the intervals cannot separate; the gap from warning to error is a few seconds (fault timestamps resolve to about "
                     "10 ms, smallest gap %s s)" % (P.num("f_i4_esc_share_normal_SV50", nd=0), P.num("f_i4_esc_share_normal_SV53", nd=0), P.num("f_i4_ts_min_positive_gap_s", nd=3)),
                     "Source: fact_session, fact_fault; session = serial + session_id with matching server dates; order from fault_timestamp (device time, inferred). Warning = fault 12/1 (inlet blocked, motor still running); error = 12/2. "
                     "Sessions, not events. 95% intervals from resampling machines. SV53 groups are small. No claim about cause.")
    cols = [DARK, BLUE]
    ax1 = fig.add_axes([0.07, 0.2, 0.25, 0.45])
    c2._bars(ax1, P, [(0, "f_i4_esc_share_normal_SV50", cols[0]), (1, "f_i4_esc_share_normal_SV53", cols[1])], nd=0, width=0.6, ymax=100)
    ax1.set_xticks(range(2)); ax1.set_xticklabels(["SV50", "SV53"], fontsize=13)
    c2._clean(ax1, "Warning sessions that reach an error (%)")
    ax2 = fig.add_axes([0.40, 0.2, 0.25, 0.45])
    c2._bars(ax2, P, [(0, "f_i4_prior121_share_normal_SV50", cols[0]), (1, "f_i4_prior121_share_normal_SV53", cols[1])], nd=0, width=0.6, ymax=100)
    ax2.set_xticks(range(2)); ax2.set_xticklabels(["SV50", "SV53"], fontsize=13)
    c2._clean(ax2, "Error sessions with an earlier warning (%)")
    ax3 = fig.add_axes([0.74, 0.2, 0.23, 0.45])
    for y, (g, col) in enumerate([("f_i4_gap_median_s_normal_SV50", cols[0]), ("f_i4_gap_median_s_normal_SV53", cols[1])]):
        v, lo, hi = _dot(ax3, P, 1 - y, g, col)
        ax3.text(hi + 0.5, 1 - y, "%s s (%s machines)" % (P.num(g, nd=1), P.count(g)), va="center", fontsize=12, color=INK)
    ax3.set_yticks([1, 0]); ax3.set_yticklabels(["SV50", "SV53"], fontsize=13)
    ax3.set_ylim(-0.6, 1.6); ax3.set_xlim(0, 24); ax3.tick_params(axis="y", length=0)
    ax3.set_xlabel("Median seconds from warning to error", color=GREY, fontsize=12)
    P.verify(fig, "f_i4")
    return ins._save(fig, "i4_blockage_warning_to_error_by_model", FIG_DIR)


def main():
    P = FinalPrinted(KEY)
    out = {}
    for name, fn in (("i1", chart_i1), ("i2", chart_i2), ("i3", chart_i3), ("i4", chart_i4)):
        P.log, P.reg = [], set()
        out[name] = fn(P)
        print(name, [str(p.relative_to(ROOT)) for p in out[name]], "numbers checked:", len(P.log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
