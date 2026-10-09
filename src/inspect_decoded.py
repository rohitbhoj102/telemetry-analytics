"""Step 1: inspect the structure of `decoded_data` (NOT a parser).

Run from the repo root:  python src/inspect_decoded.py
Outputs (generated):
    reports/profiling/decoded_data_paths.csv     one row per (file, JSON path)
    reports/profiling/decoded_data_examples.txt  truncated raw examples
    reports/profiling/decoded_data_vs_bins.csv   key/length comparison with the bin JSONs

No field meanings are assigned here. Bin-JSON comparison is by key name and array length only.
"""
import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "reports" / "profiling"
FILES = {
    ("normal", "motor"): ROOT / "normal_machines" / "Motor_Normal Machines.csv",
    ("return_repair", "motor"): ROOT / "return_repair_machines" / "Motor_Return:Repair Machines.csv",
    ("normal", "battery"): ROOT / "normal_machines" / "Battery_Normal Machines.csv",
    ("return_repair", "battery"): ROOT / "return_repair_machines" / "Battery_Return:Repair Machines.csv",
}
BIN_FILES = {
    "motor": ROOT / "reference_files" / "DDM_Bins.json",
    "battery": ROOT / "reference_files" / "BMS_Bins.json",
}
N_EXAMPLES = 3
EXAMPLE_CHARS = 1200


class PathStats:
    def __init__(self):
        self.n = 0
        self.types = set()
        self.list_lens = defaultdict(int)  # length -> count


def walk(node, path, stats):
    """Record type (and list length) for every JSON path. Lists of dicts are walked as `path[]`."""
    st = stats[path]
    st.n += 1
    st.types.add(type(node).__name__)
    if isinstance(node, dict):
        for k, v in node.items():
            walk(v, f"{path}.{k}" if path else k, stats)
    elif isinstance(node, list):
        st.list_lens[len(node)] += 1
        for item in node:
            if isinstance(item, (dict, list)):
                walk(item, f"{path}[]", stats)


def sizes_product(sizes):
    out = 1
    for s in sizes:
        out *= s
    return out


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path_rows, example_lines = [], []
    seen_paths = {}  # (cohort, domain) -> {path: PathStats}
    parse_report = []

    for (cohort, domain), csv_path in FILES.items():
        df = pd.read_csv(csv_path, usecols=["decoded_data"], low_memory=False)
        col = df["decoded_data"]
        n_null = int(col.isna().sum())
        stats = defaultdict(PathStats)
        n_ok = n_fail = 0
        for raw in col.dropna():
            try:
                walk(json.loads(raw), "", stats)
                n_ok += 1
            except (json.JSONDecodeError, TypeError):
                n_fail += 1
        parse_report.append((cohort, domain, len(df), n_null, n_ok, n_fail))
        seen_paths[(cohort, domain)] = stats
        for p, st in stats.items():
            path_rows.append({
                "cohort": cohort, "domain": domain, "path": p or "<root>",
                "n_records_with_path": st.n,
                "json_types": "|".join(sorted(st.types)),
                "list_lengths": json.dumps(dict(sorted(st.list_lens.items()))) if st.list_lens else "",
            })

        example_lines.append(f"===== {cohort} / {domain}  (rows={len(df)}, null={n_null}, json_ok={n_ok}, json_fail={n_fail})")
        for raw in col.dropna().head(N_EXAMPLES):
            txt = str(raw)
            example_lines.append(f"[len={len(txt)}] {txt[:EXAMPLE_CHARS]}{' ...[truncated]' if len(txt) > EXAMPLE_CHARS else ''}")
            example_lines.append("")

    pd.DataFrame(path_rows).to_csv(OUT_DIR / "decoded_data_paths.csv", index=False)
    (OUT_DIR / "decoded_data_examples.txt").write_text("\n".join(example_lines))

    # Compare payload keys / array lengths with the bin definitions.
    cmp_rows = []
    for domain, bin_path in BIN_FILES.items():
        bins = json.loads(bin_path.read_text())
        for cohort in ("normal", "return_repair"):
            stats = seen_paths[(cohort, domain)]
            # last path segment -> (full path, stats) for every list-of-scalars that looks like a bin array
            by_leaf = defaultdict(list)
            for p, st in stats.items():
                by_leaf[p.split(".")[-1]].append((p, st))
            for name, spec in bins.items():
                hits = by_leaf.get(name, [])
                declared_sizes = spec.get("sizes")
                declared_total = sizes_product(declared_sizes) if declared_sizes else None
                if not hits:
                    cmp_rows.append({"domain": domain, "cohort": cohort, "bin_definition": name,
                                     "declared_sizes": declared_sizes, "declared_cells": declared_total,
                                     "status": "no matching key in payload", "payload_path": "", "observed_array_lengths": ""})
                    continue
                for p, st in hits:
                    # bins live at <name>.bins in the payload where the key is a dict wrapper
                    child = stats.get(f"{p}.bins")
                    lens = dict(child.list_lens) if child else dict(st.list_lens)
                    obs = sorted(lens)
                    status = "key found; no array length to compare"
                    if obs:
                        status = "length matches declared cells" if obs == [declared_total] else "LENGTH MISMATCH"
                    cmp_rows.append({"domain": domain, "cohort": cohort, "bin_definition": name,
                                     "declared_sizes": declared_sizes, "declared_cells": declared_total,
                                     "status": status, "payload_path": p, "observed_array_lengths": json.dumps(lens)})
            # payload keys that look like bin containers but have no definition
            defined = set(bins)
            for p, st in stats.items():
                leaf = p.split(".")[-1]
                if p.endswith(".bins") or leaf in defined:
                    continue
                if f"{p}.bins" in stats and leaf not in defined:
                    cmp_rows.append({"domain": domain, "cohort": cohort, "bin_definition": "(none)",
                                     "declared_sizes": None, "declared_cells": None,
                                     "status": "payload bin container with NO definition in bin JSON",
                                     "payload_path": p, "observed_array_lengths": json.dumps(dict(stats[f"{p}.bins"].list_lens))})
    pd.DataFrame(cmp_rows).to_csv(OUT_DIR / "decoded_data_vs_bins.csv", index=False)

    print("cohort, domain, rows, null decoded_data, json ok, json fail")
    for r in parse_report:
        print(r)
    print(f"wrote outputs to {OUT_DIR}")


if __name__ == "__main__":
    main()
