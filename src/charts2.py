"""Step 11 charts (second-round insights). Every printed number is read from
reports/insights/key_numbers_v2.csv through insights.Printed and re-checked against this run.

Run: python src/charts2.py   (recomputes src/insights2.py first, ~30 s). Python 3.8 compatible.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import insights as ins  # noqa: E402
import insights2 as i2  # noqa: E402

BASE, ACCENT = "#9AA0A6", "#C8553D"
BLUE, ORANGE, DARK = "#2F6DB5", "#D9822B", "#1B4478"
INK, GREY = ins.INK, ins.GREY
GROUP_IDS = [("normal_SV50", "Normal SV50"), ("normal_SV53", "Normal SV53"), ("return_repair_SV53", "Return/Repair SV53")]
EXTRA_STATIC = {"2025", "2026", "45", "60", "300", "600", "15", "24", "250", "5", "3", "61", "301", "65535", "-300", "-600"}


def _printed(path):
    P = ins.Printed(path)
    P.STATIC = set(P.STATIC) | EXTRA_STATIC
    return P


def _err(P, id_):
    r = P.k.loc[id_]
    return r["value"] - r["interval_low"], r["interval_high"] - r["value"]


def _bars(ax, P, items, nd=1, width=0.38, ymax=None, suffix="%"):
    """items: list of (x, id, color). Draws bar, 95% interval and the value label above the interval."""
    top = 0
    for x, id_, col in items:
        v = P.k.loc[id_, "value"]
        ax.bar(x, v, width, color=col, linewidth=0)
        if not np.isnan(P.k.loc[id_, "interval_low"]):
            lo, hi = _err(P, id_)
            ax.errorbar(x, v, yerr=[[lo], [hi]], color=INK, lw=1.2, capsize=3)
            top = max(top, P.k.loc[id_, "interval_high"])
            ytxt = P.k.loc[id_, "interval_high"]
        else:
            top = max(top, v)
            ytxt = v
        ax.text(x, ytxt, " " + P.num(id_, nd=nd) + suffix, ha="center", va="bottom", fontsize=12, color=INK)
    ax.set_ylim(0, (ymax or top) * 1.18)


def _clean(ax, ylabel):
    ax.set_ylabel(ylabel, color=GREY)
    ax.tick_params(axis="x", length=0)
    ax.spines["left"].set_color("#CCCCCC")
    ax.spines["bottom"].set_color("#CCCCCC")


def chart_wash(R, P):
    plt = ins._setup()
    from matplotlib.patches import Patch
    fig = ins._frame(plt, "On the same machine, a session with a Filter Wash alert is %s as likely to also record an airway blockage" % P.ratio("ic_mh_rr_all"),
                     "Share of sessions with an airway blockage (type 12), with and without a Filter Wash (13/1) alert in that session. All groups: risk ratio %sx [%s to %s], "
                     "comparing sessions within each machine (%s machines)" % (P.num("ic_mh_rr_all", nd=1), P.num("ic_mh_rr_all", "interval_low", 1), P.num("ic_mh_rr_all", "interval_high", 1), P.count("ic_mh_rr_all")),
                     "Source: fact_session, fact_fault; faults linked to sessions on serial + session_id with server dates within 24 h; analysis rows. 95% intervals from resampling machines (2,000). "
                     "Order inside the session is not cause. Return/Repair is a selected population.")
    ax = fig.add_axes([0.08, 0.2, 0.88, 0.5])
    items = []
    for i, (g, lab) in enumerate(GROUP_IDS):
        items += [(i - 0.2, "ic_p12_given_nowash_" + g, BASE), (i + 0.2, "ic_p12_given_wash_" + g, ACCENT)]
    _bars(ax, P, items)
    ax.set_xticks(range(3))
    ax.set_xticklabels([l for _, l in GROUP_IDS], fontsize=14)
    for i, (g, _) in enumerate(GROUP_IDS):
        ax.text(i, -0.14 * ax.get_ylim()[1], "within-machine risk ratio %sx" % P.num("ic_mh_rr_" + g, nd=1), ha="center", fontsize=12, color=GREY)
    _clean(ax, "Sessions with an airway blockage (%)")
    ax.legend(handles=[Patch(color=BASE, label="Session without Filter Wash alert"), Patch(color=ACCENT, label="Session with Filter Wash alert")], frameon=False, loc="upper left", fontsize=13)
    P.verify(fig, "v2_01_wash", R)
    return fig, ins._save(fig, "v2_01_wash_alert_and_airway_blockage", FIG_DIR)


def chart_escalation(R, P):
    plt = ins._setup()
    fig = ins._frame(plt, "Roughly half of 'inlet blocked, motor still running' sessions turn into an error, usually within seconds",
                     "Left: sessions with a 12/1 warning that also log 12/2 (in error). Right: sessions with a 12/2 error that logged a 12/1 first. Median gap from first 12/1 to first 12/2: "
                     "%s seconds; %s%% of cases within 60 seconds" % (P.num("ib_gap_median_s", nd=1), P.num("ib_gap_share_within_60s", nd=0)),
                     "Source: fact_session, fact_fault; session = serial + session_id; order from fault_timestamp (device time, inferred). Counts are sessions, not events. 95% intervals from resampling machines. "
                     "SV53 groups are small: read the intervals.")
    cols = [DARK, BLUE, ORANGE]
    ax1 = fig.add_axes([0.08, 0.2, 0.40, 0.5])
    _bars(ax1, P, [(i, "ib_121_to_122_" + g, cols[i]) for i, (g, _) in enumerate(GROUP_IDS)], nd=0, width=0.55, ymax=100)
    ax1.set_xticks(range(3)); ax1.set_xticklabels(["Normal\nSV50", "Normal\nSV53", "Return/Repair\nSV53"], fontsize=13)
    _clean(ax1, "% of 12/1 sessions that reach 12/2")
    ax1.set_title("Warning escalates to error", fontsize=14, loc="left", color=INK)
    ax2 = fig.add_axes([0.58, 0.2, 0.38, 0.5])
    _bars(ax2, P, [(i, "ib_122_after_121_" + g, cols[i]) for i, (g, _) in enumerate(GROUP_IDS)], nd=0, width=0.55, ymax=100)
    ax2.set_xticks(range(3)); ax2.set_xticklabels(["Normal\nSV50", "Normal\nSV53", "Return/Repair\nSV53"], fontsize=13)
    _clean(ax2, "% of 12/2 sessions with an earlier 12/1")
    ax2.set_title("Error preceded by a warning", fontsize=14, loc="left", color=INK)
    P.verify(fig, "v2_02_escalation", R)
    return fig, ins._save(fig, "v2_02_blockage_warning_to_error", FIG_DIR)


def chart_submodel(R, P):
    plt = ins._setup()
    rows = [("Normal SV50-AA", "ie_rate12_normal_SV50_AA", DARK), ("Normal SV50-AC", "ie_rate12_normal_SV50_AC", DARK), ("Normal SV50-AF", "ie_rate12_normal_SV50_AF", DARK),
            ("Normal SV53-AB", "ie_rate12_normal_SV53_AB", BLUE), ("Normal SV53-AC", "ie_rate12_normal_SV53_AC", BLUE), ("Normal SV53-AE", "ie_rate12_normal_SV53_AE", BLUE),
            ("Normal SV53-AF", "ie_rate12_normal_SV53_AF", BLUE), ("Return/Repair SV53-AB", "ie_rate12_return_repair_SV53_AB", ORANGE), ("Return/Repair SV53-AF", "ie_rate12_return_repair_SV53_AF", ORANGE)]
    fig = ins._frame(plt, "Airway blockage sits mostly in a few sub-models: Normal SV53-AB logs far more than the other Normal SV53 sub-models",
                     "Airway blockage (type 12) faults per 100 clean sessions, pooled, 95%% interval. Normal SV53-AB minus other Normal SV53: %s [%s to %s] per 100 sessions. "
                     "SV53-AB is %s%% of Normal and %s%% of Return/Repair rate-eligible SV53 machines" % (
                         P.num("ie_diff_sv53ab_n12", nd=1), P.num("ie_diff_sv53ab_n12", "interval_low", 1), P.num("ie_diff_sv53ab_n12", "interval_high", 1),
                         P.num("ie_ab_share_normal", nd=0), P.num("ie_ab_share_return_repair", nd=0)),
                     "Source: machine_summary, rate-eligible machines (>= 10 sessions); sub-models with fewer than 3 machines not shown. Sub-model codes (AA, AB...) have no stated meaning. "
                     "Exploratory: many cuts were made, intervals are wide. Return/Repair is a selected population.")
    ax = fig.add_axes([0.22, 0.22, 0.66, 0.48])
    for i, (lab, id_, col) in enumerate(rows):
        y = len(rows) - 1 - i
        v, lo, hi = P.k.loc[id_, ["value", "interval_low", "interval_high"]]
        ax.hlines(y, lo, hi, color=col, lw=2)
        ax.plot(v, y, "o", color=col, ms=9, mec="white", mew=1.5)
        ax.text(hi + 0.4, y, "%s (%s machines)" % (P.num(id_, nd=1), P.count(id_)), va="center", fontsize=12, color=INK)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows][::-1], fontsize=13)
    ax.set_xlim(0, 52)
    ax.set_xlabel("Airway blockage faults per 100 clean sessions", color=GREY)
    ax.tick_params(axis="y", length=0)
    ax.text(0.99, 0.60, "Same SV53 RR/Normal ratio: %s crude, %s after re-weighting\nto the Normal sub-model mix [%s to %s]" % (
        P.num("ie_crude_ratio", nd=1), P.num("ie_std_ratio", nd=1), P.num("ie_std_ratio", "interval_low", 1), P.num("ie_std_ratio", "interval_high", 1)),
        transform=ax.transAxes, ha="right", fontsize=12, color=GREY)
    P.verify(fig, "v2_03_submodel", R)
    return fig, ins._save(fig, "v2_03_submodel_airway_blockage", FIG_DIR)


def chart_battery(R, P):
    plt = ins._setup()
    fig = ins._frame(plt, "Battery temperature 'not OK' is mostly a missing reading; where heat does show, it is on SV50",
                     "Left: sessions with no temperature flag set. Middle: battery machines with any discharge time above 45 C. Right: share of discharge seconds above 45 C. "
                     "Only %s sessions are flagged HOT (all SV50, %s machines) and none COLD" % (P.count("if_hot_normal_SV50", "value"), P.count("if_hot_normal_SV50")),
                     "Source: fact_session (flags); fact_battery_period (BMS discharge band bins, unit second, edges 15 and 45 C per BMS_Bins.json), valid periods. SV50 = %s machines, SV53 = %s (%s Normal, %s Return/Repair). "
                     "One SV50 machine holds %s%% of SV50 hot seconds. 95%% intervals from resampling machines." % (P.count("if_pack_SV50_4_cell"), P.count("if_pack_SV53_7_cell"), P.count("if_any_hot_normal_SV53"), P.count("if_any_hot_return_repair_SV53"), P.num("if_top1_share_sv50", nd=0)))
    ax1 = fig.add_axes([0.07, 0.2, 0.25, 0.5])
    _bars(ax1, P, [(0, "if_notrep_normal_SV50", DARK), (1, "if_notrep_normal_SV53", BLUE), (2, "if_notrep_return_repair_SV53", ORANGE)], nd=0, width=0.6, ymax=100)
    ax1.set_xticks(range(3)); ax1.set_xticklabels(["Normal\nSV50", "Normal\nSV53", "RR\nSV53"], fontsize=13)
    _clean(ax1, "% of sessions, no flag set")
    ax2 = fig.add_axes([0.40, 0.2, 0.25, 0.5])
    _bars(ax2, P, [(0, "if_any_hot_normal_SV50", DARK), (1, "if_any_hot_sv53_all", BLUE)], nd=0, width=0.6, ymax=100)
    ax2.set_xticks(range(2)); ax2.set_xticklabels(["SV50", "SV53\n(Normal + RR)"], fontsize=13)
    _clean(ax2, "% of machines")
    ax3 = fig.add_axes([0.73, 0.2, 0.25, 0.5])
    _bars(ax3, P, [(0, "if_dis_hot_normal_SV50", DARK), (1, "if_dis_hot_sv50_drop_top", DARK), (2, "if_dis_hot_sv53_all", BLUE)], nd=2, width=0.6)
    ax3.set_xticks(range(3)); ax3.set_xticklabels(["SV50", "SV50 w/o\ntop machine", "SV53"], fontsize=12)
    _clean(ax3, "% of discharge seconds above 45 C")
    P.verify(fig, "v2_04_battery", R)
    return fig, ins._save(fig, "v2_04_battery_temperature", FIG_DIR)


def chart_trend(R, P):
    plt = ins._setup()
    fig = ins._frame(plt, "For the same machines, Filter Wash alerts and airway blockages became many times more frequent by mid 2026",
                     "Share of sessions with the fault, Oct-Dec 2025 vs Apr-Jun 2026, machines with at least 15 sessions in both windows (SV50 %s machines, SV53 %s). "
                     "SV50 Filter Wash: %s%% of machines rose" % (P.count("ig_early_wash_SV50"), P.count("ig_early_wash_SV53"), P.num("ig_rise_share_wash_SV50", nd=0)),
                     "Source: fact_session, fact_fault. Age of machine, season and software or logging changes cannot be separated in this data; first-seen month is not install date. "
                     "95% intervals from resampling machines.")
    ax1 = fig.add_axes([0.08, 0.2, 0.40, 0.5])
    _bars(ax1, P, [(0, "ig_early_wash_SV50", BASE), (0.45, "ig_late_wash_SV50", ACCENT), (1.5, "ig_early_wash_SV53", BASE), (1.95, "ig_late_wash_SV53", ACCENT)], width=0.4)
    ax1.set_xticks([0.225, 1.725]); ax1.set_xticklabels(["SV50", "SV53"], fontsize=14)
    _clean(ax1, "% of sessions")
    ax1.set_title("Filter Wash (13/1) alert", fontsize=14, loc="left", color=INK)
    ax2 = fig.add_axes([0.58, 0.2, 0.38, 0.5])
    _bars(ax2, P, [(0, "ig_early_block_SV50", BASE), (0.45, "ig_late_block_SV50", ACCENT), (1.5, "ig_early_block_SV53", BASE), (1.95, "ig_late_block_SV53", ACCENT)], width=0.4)
    ax2.set_xticks([0.225, 1.725]); ax2.set_xticklabels(["SV50", "SV53"], fontsize=14)
    _clean(ax2, "% of sessions")
    ax2.set_title("Airway blockage (type 12)", fontsize=14, loc="left", color=INK)
    from matplotlib.patches import Patch
    ax1.legend(handles=[Patch(color=BASE, label="Oct-Dec 2025"), Patch(color=ACCENT, label="Apr-Jun 2026")], frameon=False, loc="upper right", fontsize=13)
    P.verify(fig, "v2_05_trend", R)
    return fig, ins._save(fig, "v2_05_fault_rates_over_time", FIG_DIR)


def chart_duration_dust(R, P):
    plt = ins._setup()
    fig = ins._frame(plt, "Longer sessions carry more blockage risk, but dust mass does not flag a blockage",
                     "Left: sessions with an airway blockage by clean_duration band (unit not stated). Right: dust mass in blockage sessions vs other sessions of the same machine and similar length, "
                     "%% difference. Long vs short sessions on the same machine: risk ratio %s [%s to %s]" % (P.num("id_mh_rr_long_vs_short", nd=1), P.num("id_mh_rr_long_vs_short", "interval_low", 1), P.num("id_mh_rr_long_vs_short", "interval_high", 1)),
                     "Source: fact_session, fact_fault, SV53 only for dust (SV50 reports no dust values in any session). 65535 treated as no reading (inferred). Dust unit not stated. "
                     "Lower dust in blockage sessions is consistent with less air reaching the sensor, an interpretation we cannot test. 95% intervals from resampling machines.")
    ax1 = fig.add_axes([0.08, 0.2, 0.38, 0.5])
    bands = [("id_block_by_band_le60", "<=60"), ("id_block_by_band_61_300", "61-300"), ("id_block_by_band_301_600", "301-600"), ("id_block_by_band_gt600", ">600")]
    _bars(ax1, P, [(i, b[0], ACCENT if i >= 2 else BASE) for i, b in enumerate(bands)], width=0.6)
    ax1.set_xticks(range(4)); ax1.set_xticklabels([b[1] for b in bands], fontsize=13)
    ax1.set_xlabel("clean_duration band (raw value)", color=GREY)
    _clean(ax1, "Sessions with an airway blockage (%)")
    ax2 = fig.add_axes([0.62, 0.2, 0.34, 0.5])
    rows = [("Ultra-fine", "id_dust_effect_ultra_fine"), ("Fine", "id_dust_effect_fine"), ("Coarse", "id_dust_effect_coarse"), ("Large", "id_dust_effect_large")]
    for i, (lab, id_) in enumerate(rows):
        y = len(rows) - 1 - i
        v, lo, hi = P.k.loc[id_, ["value", "interval_low", "interval_high"]]
        col = ACCENT if hi < 0 else BASE
        ax2.hlines(y, lo, hi, color=col, lw=2)
        ax2.plot(v, y, "o", color=col, ms=9, mec="white", mew=1.5)
        ax2.text(hi + 3, y, P.num(id_, nd=0) + "%", va="center", fontsize=12, color=INK)
    ax2.axvline(0, color=GREY, lw=1)
    ax2.set_yticks(range(4)); ax2.set_yticklabels([r[0] for r in rows][::-1], fontsize=13)
    ax2.set_xlim(-80, 45)
    ax2.set_xlabel("Dust mass, blockage vs other sessions (%)", color=GREY)
    ax2.tick_params(axis="y", length=0)
    P.verify(fig, "v2_06_dust", R)
    return fig, ins._save(fig, "v2_06_duration_and_dust", FIG_DIR)


FIG_DIR = i2.FIG_DIR


def main():
    R = i2.compute()
    path = i2.write(R)
    P = _printed(path)
    out = {}
    for name, fn in (("wash", chart_wash), ("escalation", chart_escalation), ("submodel", chart_submodel), ("battery", chart_battery), ("trend", chart_trend), ("dust", chart_duration_dust)):
        out[name] = fn(R, P)
        print(name, [str(p.relative_to(i2.ROOT)) for p in out[name][1]])
    print("numbers read from key_numbers_v2.csv and checked: %d" % len(P.log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
