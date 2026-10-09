"""Step 2: read-only check of whether numeric payload fields behave like cumulative counters.

Run from the repo root:  python src/cumulative_check.py
Outputs (generated):
    reports/profiling/cumulative_check.csv   one row per (group, numeric path)
    reports/profiling/cumulative_gaps.csv    observation spacing per group
    reports/profiling/cumulative_dedup_effect.csv  monotonic share with vs without removing re-uploads

For every numeric scalar and every numeric bin array, observations are ordered per serial by
`hdr_timestamp` and consecutive values are compared. "Monotonic" means non-decreasing.
Nothing is written back to the data. De-duplication here is only for ordering: rows with the
same serial, `hdr_timestamp` AND identical payload text are counted once. The Step 4 duplicate
rule is not applied or pre-empted. Event-log records (`eventLog.events[]`, `eventLog.faults[]`)
are snapshots, not counters, and are excluded. The flat battery layout (13 rows, 2 serials,
string values) is excluded as too small to judge.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from payload_io import load_groups

OUT = Path(__file__).resolve().parent.parent / "reports" / "profiling"
GROUPS = ["motor_normal", "motor_rr", "battery_normal", "battery_rr_standard"]
MAX_EXAMPLES = 2


def flatten(node, path, out):
    """Collect numeric scalars (str path -> number) and numeric arrays (str path -> list)."""
    if isinstance(node, dict):
        for k, v in node.items():
            flatten(v, f"{path}.{k}" if path else k, out)
    elif isinstance(node, list):
        if node and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in node):
            out[path] = node
        # lists of dicts / mixed lists (event records) are skipped on purpose
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        out[path] = node


def check_group(name, df):
    df = df.sort_values(["anonymized_serial", "hdr_timestamp", "server_timestamp"])
    n_raw = len(df)
    df = df.drop_duplicates(["anonymized_serial", "hdr_timestamp", "raw"])
    ties = int(df.duplicated(["anonymized_serial", "hdr_timestamp"], keep=False).sum())
    df = df.assign(flat=df["payload"].map(lambda p: _flat(p)))
    paths = sorted({p for f in df["flat"] for p in f})
    rows = []
    gaps = []
    for ser, g in df.groupby("anonymized_serial"):
        d = g["hdr_timestamp"].diff().dropna().dt.total_seconds() / 86400
        gaps.extend(d[d > 0].tolist())
    # Primary ordering: hdr_timestamp (as asked). Secondary: server_timestamp, to separate
    # device-clock ordering artefacts from genuine decreases (resets or other causes).
    ordered = {o: {ser: g.sort_values([o, "hdr_timestamp"]) for ser, g in df.groupby("anonymized_serial")}
               for o in ("hdr_timestamp", "server_timestamp")}
    for path in paths:
        res = {}
        for order, per_ser in ordered.items():
            per_serial = {}
            for ser, g in per_ser.items():
                seq = [(t, f[path]) for t, f in zip(g[order], g["flat"]) if path in f]
                if seq:
                    per_serial[ser] = seq
            res[order] = _metrics(per_serial)
        m, m2 = res["hdr_timestamp"], res["server_timestamp"]
        rows.append({
            "group": name, "path": path, "kind": m["kind"],
            "serials_with_path": m["serials"], "serials_ge2_obs": m["n_ge2"], "consecutive_pairs": m["pairs"],
            "pct_serials_monotonic": m["pct_mono"], "pct_serials_monotonic_total": m["pct_mono_total"],
            "pairs_with_decrease": m["dec_any"], "pairs_total_decrease": m["dec_total"],
            "pct_pairs_unchanged": m["pct_unchanged"], "constant_everywhere": m["constant"],
            "pct_serials_monotonic_by_server_ts": m2["pct_mono"], "pairs_with_decrease_by_server_ts": m2["dec_any"],
            "decrease_examples": m["examples"],
        })
    g = pd.Series(gaps)
    obs = df.groupby("anonymized_serial").size()
    gap_row = {
        "group": name, "payload_rows": n_raw, "rows_after_identical_payload_dedup": len(df),
        "tied_hdr_timestamp_rows_with_different_payload": ties, "serials": df["anonymized_serial"].nunique(),
        "serials_ge2_obs": int((obs >= 2).sum()), "median_obs_per_serial": float(obs.median()),
        "gap_days_p10": round(g.quantile(.1), 2) if len(g) else None, "gap_days_median": round(g.median(), 2) if len(g) else None,
        "gap_days_p90": round(g.quantile(.9), 2) if len(g) else None,
        "pct_gaps_6_to_8_days": round(100 * g.between(6, 8).mean(), 1) if len(g) else None,
    }
    return rows, gap_row


def _metrics(per_serial):
    """Compare consecutive observations per serial. `per_serial`: {serial: [(time, value_or_list), ...]}."""
    is_array = any(isinstance(v[0][1], list) for v in per_serial.values())
    n_ge2 = mono_cells = mono_total = pairs = dec_any = dec_total = unchanged = 0
    examples, all_vals = [], set()
    for ser, seq in per_serial.items():
        if len({len(v) if isinstance(v, list) else 1 for _, v in seq}) > 1:  # array length changed: cannot compare
            continue
        mat = np.array([v if isinstance(v, list) else [v] for _, v in seq], dtype=float)
        all_vals.update(map(float, mat.ravel()[:50]))
        if len(seq) < 2:
            continue
        n_ge2 += 1
        diff = np.diff(mat, axis=0)
        tot = np.diff(mat.sum(axis=1))
        pairs += len(diff)
        any_dec = (diff < 0).any(axis=1)
        dec_any += int(any_dec.sum())
        dec_total += int((tot < 0).sum())
        unchanged += int((diff == 0).all(axis=1).sum())
        mono_cells += int(not any_dec.any())
        mono_total += int(not (tot < 0).any())
        for i in np.where(tot < 0 if is_array else any_dec)[0][:MAX_EXAMPLES]:
            if len(examples) < MAX_EXAMPLES:
                examples.append(f"{ser[:8]} {seq[i + 1][0]:%Y-%m-%d}: {mat[i].sum():g}->{mat[i + 1].sum():g}")
    pct = lambda x: round(100 * x / n_ge2, 1) if n_ge2 else None
    return {"kind": "array" if is_array else "scalar", "serials": len(per_serial), "n_ge2": n_ge2, "pairs": pairs,
            "pct_mono": pct(mono_cells), "pct_mono_total": pct(mono_total), "dec_any": dec_any, "dec_total": dec_total,
            "pct_unchanged": round(100 * unchanged / pairs, 1) if pairs else None,
            "constant": len(all_vals) == 1, "examples": " | ".join(examples)}


def _flat(payload):
    out = {}
    flatten(payload, "", out)
    return out


def dedup_effect(groups):
    """Does removing re-uploaded duplicate records change the monotonic share? (read-only)

    Compares, per group and for every numeric path, the share of monotonic serials with all rows kept
    versus with rows collapsed on (serial, hdr_timestamp, identical payload text). Also reports how many
    rows each variant uses and a stricter collapse on (serial, identical payload text) that keeps the earliest hdr_timestamp.
    """
    variants = {
        "all_rows": None,
        "dedup_serial_hdr_payload": ["anonymized_serial", "hdr_timestamp", "raw"],
        "dedup_serial_payload": ["anonymized_serial", "raw"],
    }
    rows = []
    for name in ("battery_normal_4cell", "battery_normal_7cell", "battery_rr_standard", "motor_normal", "motor_rr"):
        base = groups[name].sort_values(["anonymized_serial", "hdr_timestamp", "server_timestamp"])
        for vname, key in variants.items():
            df = base if key is None else base.drop_duplicates(key)
            df = df.assign(flat=df["payload"].map(_flat))
            paths = sorted({p for f in df["flat"] for p in f})
            res = []
            for path in paths:
                per_serial = {}
                for ser, g in df.groupby("anonymized_serial"):
                    seq = [(t, f[path]) for t, f in zip(g["hdr_timestamp"], g["flat"]) if path in f]
                    if seq:
                        per_serial[ser] = seq
                m = _metrics(per_serial)
                if not m["constant"] and m["pct_mono"] is not None:
                    res.append((m["pct_mono"], m["dec_any"], m["pairs"]))
            arr = pd.DataFrame(res, columns=["pct", "dec", "pairs"])
            rows.append({"group": name, "variant": vname, "rows_used": len(df), "serials": df["anonymized_serial"].nunique(),
                         "non_constant_paths": len(arr), "median_pct_serials_monotonic": arr.pct.median(),
                         "paths_100pct_monotonic": int((arr.pct == 100).sum()), "total_decreasing_pairs": int(arr.dec.sum()),
                         "total_pairs": int(arr.pairs.sum())})
    pd.DataFrame(rows).to_csv(OUT / "cumulative_dedup_effect.csv", index=False)


def main():
    groups = load_groups()
    # Normal battery has two disjoint payload variants (root `bpa_SNO` / 4 cells vs `header` / 7 cells); also check them separately.
    nb = groups["battery_normal"]
    has_header = nb["payload"].map(lambda p: "header" in p)
    groups["battery_normal_4cell"] = nb[~has_header]
    groups["battery_normal_7cell"] = nb[has_header]
    all_rows, gap_rows = [], []
    for name in GROUPS + ["battery_normal_4cell", "battery_normal_7cell"]:
        print("checking", name)
        r, g = check_group(name, groups[name])
        all_rows += r
        gap_rows.append(g)
    pd.DataFrame(all_rows).to_csv(OUT / "cumulative_check.csv", index=False)
    pd.DataFrame(gap_rows).to_csv(OUT / "cumulative_gaps.csv", index=False)
    dedup_effect(groups)
    print("done")


if __name__ == "__main__":
    main()
