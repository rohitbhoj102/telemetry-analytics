"""Step 6 helpers: machine-level cohort comparison, bootstrap intervals, robustness table, charts.

Used by notebooks/01_eda_shortlist.ipynb. Reads only data/model/. Python 3.8 compatible.
Unit of analysis is the machine; every comparison is Return/Repair (RR) minus Normal.
All results are exploratory (many comparisons, no multiplicity correction).
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "data" / "model"
FIG_DIR = ROOT / "reports" / "figures" / "eda"

NORMAL, RR = "normal", "return_repair"
COLORS = {NORMAL: "#2F6DB5", RR: "#D9822B"}      # fixed in every chart
LABELS = {NORMAL: "Normal", RR: "Return/Repair"}
N_BOOT = 2000
SEED = 20261011
MIN_SESSIONS = 10        # rate_eligible rule from Step 5 (analysis sessions per machine)


def load_model():
    """Return dict of model tables read from the CSV exports in data/model/."""
    t = {}
    t["summary"] = pd.read_csv(MODEL_DIR / "machine_summary.csv",
                               parse_dates=["first_session_ts", "last_session_ts"])
    t["dim"] = pd.read_csv(MODEL_DIR / "dim_machine.csv")
    t["session"] = pd.read_csv(MODEL_DIR / "fact_session.csv", parse_dates=["date_server"])
    t["fault"] = pd.read_csv(MODEL_DIR / "fact_fault.csv", parse_dates=["fault_timestamp"])
    t["motor"] = pd.read_csv(MODEL_DIR / "fact_motor_period.csv",
                             parse_dates=["period_start_ts", "period_end_ts"])
    t["battery"] = pd.read_csv(MODEL_DIR / "fact_battery_period.csv",
                               usecols=["period_key", "anonymized_serial", "cohort", "delta_valid"])
    return t


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------
def _boot_stat(values, stat, rng, n_boot):
    idx = rng.randint(0, len(values), size=(n_boot, len(values)))
    return stat(values[idx], axis=1)


def compare(df, col, stat="median", n_boot=N_BOOT, seed=SEED, group="cohort", a_val=NORMAL, b_val=RR):
    """RR vs Normal on machine-level column `col` (NaN rows dropped).

    stat: 'median' or 'mean' (mean of a 0/1 column = share of machines).
    By default group A = Normal and group B = RR (output keys "normal" and "rr"); other groups
    can be compared with group / a_val / b_val, and the keys then mean group A and group B.
    Interval: percentile bootstrap (machines resampled within cohort) of RR minus Normal.
    """
    fn = np.median if stat == "median" else np.mean
    a = df.loc[df[group] == a_val, col].dropna().values.astype(float)
    b = df.loc[df[group] == b_val, col].dropna().values.astype(float)
    out = {"n_normal": len(a), "n_rr": len(b)}
    if len(a) == 0 or len(b) == 0:
        out.update(normal=np.nan, rr=np.nan, diff=np.nan, ratio=np.nan, ci_lo=np.nan, ci_hi=np.nan)
        return out
    rng = np.random.RandomState(seed)
    da = _boot_stat(a, fn, rng, n_boot)
    db = _boot_stat(b, fn, rng, n_boot)
    d = db - da
    out["normal"], out["rr"] = float(fn(a)), float(fn(b))
    out["diff"] = out["rr"] - out["normal"]
    out["ratio"] = out["rr"] / out["normal"] if out["normal"] != 0 else np.nan
    out["ci_lo"], out["ci_hi"] = (float(x) for x in np.percentile(d, [2.5, 97.5]))
    return out


def direction_holds(main_diff, other_diff):
    """'yes' / 'no' / 'n/a' (a zero or missing difference has no direction)."""
    if any(pd.isna(x) for x in (main_diff, other_diff)) or main_diff == 0 or other_diff == 0:
        return "n/a"
    return "yes" if np.sign(main_diff) == np.sign(other_diff) else "no"


def robustness(df, col, variants, stat="median", main_label="all eligible machines"):
    """Main comparison plus variants. `variants` = {label: (filtered_df, col_or_None)}.

    Returns a table with n, medians (or shares), difference, ratio, interval and 'direction holds'.
    """
    rows = []
    main = compare(df, col, stat)
    rows.append(dict(variant=main_label, **main, direction_holds="(reference)"))
    for label, (d, c) in variants.items():
        r = compare(d, c or col, stat)
        rows.append(dict(variant=label, **r, direction_holds=direction_holds(main["diff"], r["diff"])))
    return pd.DataFrame(rows)[["variant", "n_normal", "n_rr", "normal", "rr", "diff", "ratio",
                               "ci_lo", "ci_hi", "direction_holds"]]


def compare_pooled(df, num_col, den_col, n_boot=N_BOOT, seed=SEED, scale=100.0,
                   group="cohort", a_val=NORMAL, b_val=RR):
    """Pooled rate (sum num / sum den x scale; default per 100) per group; bootstrap of B minus A."""
    parts = {}
    for c, gv in ((NORMAL, a_val), (RR, b_val)):
        parts[c] = df.loc[df[group] == gv, [num_col, den_col]].dropna().values.astype(float)
    out = {"n_normal": len(parts[NORMAL]), "n_rr": len(parts[RR])}
    rng = np.random.RandomState(seed)
    boots = {}
    for c in (NORMAL, RR):
        d = parts[c]
        idx = rng.randint(0, len(d), size=(n_boot, len(d)))
        boots[c] = scale * d[:, 0][idx].sum(axis=1) / d[:, 1][idx].sum(axis=1)
    out["normal"] = scale * parts[NORMAL][:, 0].sum() / parts[NORMAL][:, 1].sum()
    out["rr"] = scale * parts[RR][:, 0].sum() / parts[RR][:, 1].sum()
    out["diff"] = out["rr"] - out["normal"]
    out["ratio"] = out["rr"] / out["normal"] if out["normal"] else np.nan
    out["ci_lo"], out["ci_hi"] = (float(x) for x in np.percentile(boots[RR] - boots[NORMAL], [2.5, 97.5]))
    return out


def one_sample_ci(values, stat=np.median, n_boot=N_BOOT, seed=SEED):
    """Bootstrap 95% interval of the median (default) of one machine-level sample."""
    v = np.asarray(pd.Series(values).dropna(), dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.RandomState(seed)
    b = _boot_stat(v, stat, rng, n_boot)
    return float(stat(v)), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def md_table(df, nd=2):
    """Plain markdown table (no tabulate dependency)."""
    def f(x):
        if isinstance(x, (float, np.floating)):
            return "" if pd.isna(x) else ("%.*f" % (nd, x))
        return str(x)
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(f(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def three_stats(df, num_col, den_col, rate_col, scale=100.0, **grp):
    """Median per machine, pooled rate and share of machines with >= 1, for one count column."""
    rows = [dict(measure="median per machine", **compare(df, rate_col, "median", **grp)),
            dict(measure="pooled rate", **compare_pooled(df, num_col, den_col, scale=scale, **grp))]
    tmp = df.assign(_any=(df[num_col] > 0).astype(float))
    rows.append(dict(measure="share of machines with >=1", **compare(tmp, "_any", "mean", **grp)))
    return rows


def with_direction(tab, ref_variant, by="measure"):
    """Add direction_holds per measure: sign of diff vs the diff of the row with variant == ref_variant."""
    tab = tab.copy()
    out = []
    for _, r in tab.iterrows():
        ref = tab[(tab[by] == r[by]) & (tab.variant == ref_variant)]["diff"].iloc[0]
        out.append("(reference)" if r.variant == ref_variant else direction_holds(ref, r["diff"]))
    tab["direction_holds"] = out
    return tab


def sv53(df):
    """Machines whose model starts with SV53 (model known only from sessions and faults)."""
    return df[df.model.fillna("").str.startswith("SV53")]


# ---------------------------------------------------------------------------
# Charts (matplotlib; one fixed colour per cohort)
# ---------------------------------------------------------------------------
def style():
    import matplotlib.pyplot as plt
    plt.rcParams.update({"axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": 0.25, "font.size": 10,
                         "figure.dpi": 110})


def _legend(ax, ns, loc="best"):
    from matplotlib.patches import Patch
    handles = [Patch(color=COLORS[c], label="%s (n=%d machines)" % (LABELS[c], ns[c]))
               for c in (NORMAL, RR)]
    ax.legend(handles=handles, loc=loc, frameon=False)


def strip_compare(ax, df, col, ylabel, title, log=False, nonneg=True):
    """Jittered machine points per cohort, median line, bootstrap-free (interval is in the table)."""
    rng = np.random.RandomState(1)
    ns = {}
    for i, c in enumerate((NORMAL, RR)):
        v = df.loc[df.cohort == c, col].dropna().values.astype(float)
        ns[c] = len(v)
        if len(v) == 0:
            continue
        ax.scatter(i + rng.uniform(-0.18, 0.18, len(v)), v, s=14, alpha=0.55, color=COLORS[c],
                   linewidths=0)
        ax.hlines(np.median(v), i - 0.3, i + 0.3, color="black", lw=2)
        ax.annotate("median %.3g" % np.median(v), (i + 0.32, np.median(v)), va="center", fontsize=9)
    ax.set_xticks([0, 1])
    ax.set_xticklabels([LABELS[NORMAL], LABELS[RR]])
    ax.set_xlim(-0.6, 1.9)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10, loc="left")
    if log:
        ax.set_yscale("symlog", linthresh=1)
        if nonneg:
            ax.set_ylim(bottom=0)
    _legend(ax, ns)
    return ns


def save(fig, name):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / name
    fig.savefig(str(path), bbox_inches="tight")
    return path


def fmt_table(t, nd=2):
    return t.round(nd)
