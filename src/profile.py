"""Step 1 profiling: one summary row per raw CSV plus one detail row per column.

Run from the repo root:  python src/profile.py
Outputs (generated, do not hand-edit):
    reports/profiling/profile_summary.csv
    reports/profiling/profile_columns.csv

Raw files are only read, never modified.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "reports" / "profiling"

COHORT_DIRS = {
    "normal": ROOT / "normal_machines",
    "return_repair": ROOT / "return_repair_machines",
}

# Filename prefix -> domain. Matching is case-insensitive on the filename start.
DOMAIN_PREFIXES = {
    "clean sessions": "clean_sessions",
    "faults": "faults",
    "motor": "motor",
    "battery": "battery",
}

# ASSUMPTION (logged in docs/assumptions_log.md): which columns identify a record.
# `primary` is the most plausible natural key; `loose` is a coarser key, shown so the
# reader can see how sensitive the duplicate count is to the key choice.
KEYS = {
    "clean_sessions": {
        "primary": ["anonymized_serial", "session_id", "date"],
        "loose": ["anonymized_serial", "session_id"],
    },
    "faults": {
        "primary": ["anonymized_serial", "session_id", "fault_type", "fault_timestamp"],
        "loose": ["anonymized_serial", "session_id", "fault_type"],
    },
    "motor": {
        "primary": ["anonymized_serial", "hdr_timestamp", "log_id"],
        "loose": ["anonymized_serial", "hdr_timestamp"],
    },
    "battery": {
        "primary": ["anonymized_serial", "hdr_timestamp", "log_id"],
        "loose": ["anonymized_serial", "hdr_timestamp"],
    },
}

# Text timestamps in the form "2025-10-18 14:10:45.140599 UTC".
TIMESTAMP_COLS = {"date", "server_timestamp", "hdr_timestamp", "fault_timestamp"}
# Integer epoch-second columns (ASSUMPTION: unit is seconds; checked via parse range).
EPOCH_COLS = {
    "log2_time_sync_old",
    "log2_time_sync_new",
    "log3_time_sync_old",
    "log3_time_sync_new",
}
MAX_LEVELS = 30
SKIP_LEVEL_COLS = {"decoded_data", "anonymized_serial"}


def find_files():
    """Glob the cohort folders; return list of (path, cohort, domain)."""
    found = []
    for cohort, folder in COHORT_DIRS.items():
        for path in sorted(folder.glob("*.csv")):
            name = path.name.lower()
            domain = next((d for p, d in DOMAIN_PREFIXES.items() if name.startswith(p)), None)
            if domain is None:
                raise ValueError(f"Cannot derive domain from filename: {path.name}")
            found.append((path, cohort, domain))
    return found


def parse_timestamps(series):
    """Parse 'YYYY-MM-DD HH:MM:SS.ffffff UTC' strings.

    Returns (parsed, n_failed). A failure is a non-null input that did not parse.
    Failures are counted, not silently dropped.
    """
    raw = series.dropna().astype(str)
    cleaned = raw.str.replace(r"\s*UTC$", "", regex=True)
    parsed = pd.to_datetime(cleaned, errors="coerce", format="mixed") if _has_mixed() else pd.to_datetime(cleaned, errors="coerce")
    return parsed, int(parsed.isna().sum())


def _has_mixed():
    # pandas >= 2.0 supports format="mixed"; older versions do not.
    major = int(pd.__version__.split(".")[0])
    return major >= 2


def parse_epoch(series):
    """Parse epoch-second values. Returns (parsed, n_failed)."""
    numeric = pd.to_numeric(series.dropna(), errors="coerce")
    n_failed = int(numeric.isna().sum())
    numeric = numeric.dropna()
    try:
        parsed = pd.to_datetime(numeric, unit="s", errors="coerce")
    except (OverflowError, ValueError):
        parsed = pd.Series(pd.NaT, index=numeric.index)
    n_failed += int(parsed.isna().sum())
    return parsed.dropna(), n_failed


def dup_stats(df, key):
    """Return (extra_rows, rows_involved) for duplicates on `key`.

    extra_rows: rows beyond the first occurrence. rows_involved: all rows in a dup group.
    """
    missing = [c for c in key if c not in df.columns]
    if missing:
        return None, None
    return int(df.duplicated(subset=key, keep="first").sum()), int(df.duplicated(subset=key, keep=False).sum())


def profile_file(path, cohort, domain):
    df = pd.read_csv(path, low_memory=False)
    n = len(df)
    summary = {
        "cohort": cohort,
        "domain": domain,
        "file": path.name,
        "rows": n,
        "cols": df.shape[1],
        "distinct_serials": int(df["anonymized_serial"].nunique()) if "anonymized_serial" in df else None,
        "null_serial_rows": int(df["anonymized_serial"].isna().sum()) if "anonymized_serial" in df else None,
        "exact_duplicate_rows": int(df.duplicated().sum()),
    }
    for label, key in KEYS[domain].items():
        extra, involved = dup_stats(df, key)
        summary[f"key_{label}"] = "+".join(key)
        summary[f"key_{label}_dup_extra_rows"] = extra
        summary[f"key_{label}_dup_rows_involved"] = involved

    detail = []
    date_ranges = []
    total_parse_failures = 0
    for col in df.columns:
        s = df[col]
        row = {
            "cohort": cohort,
            "domain": domain,
            "file": path.name,
            "column": col,
            "dtype_as_read": str(s.dtype),
            "non_null": int(s.notna().sum()),
            "nulls": int(s.isna().sum()),
            "null_pct": round(100 * s.isna().mean(), 2) if n else None,
            "distinct": int(s.nunique(dropna=True)),
        }

        if col in TIMESTAMP_COLS or col in EPOCH_COLS:
            parsed, failed = parse_timestamps(s) if col in TIMESTAMP_COLS else parse_epoch(s)
            row["ts_kind"] = "text_utc" if col in TIMESTAMP_COLS else "epoch_seconds"
            row["ts_min"] = str(parsed.min()) if len(parsed) else None
            row["ts_max"] = str(parsed.max()) if len(parsed) else None
            row["ts_parse_failures"] = failed
            total_parse_failures += failed
            if len(parsed):
                date_ranges.append(f"{col}: {parsed.min()} -> {parsed.max()}")

        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            row.update(
                num_min=s.min(),
                num_max=s.max(),
                num_mean=round(float(s.mean()), 4) if s.notna().any() else None,
                num_median=s.median(),
                num_negatives=int((s < 0).sum()),
            )

        if col not in SKIP_LEVEL_COLS and col not in TIMESTAMP_COLS and row["distinct"] <= MAX_LEVELS:
            counts = s.value_counts(dropna=False)
            row["levels"] = json.dumps({str(k): int(v) for k, v in counts.items()})
        detail.append(row)

    summary["date_ranges"] = " | ".join(date_ranges)
    summary["ts_parse_failures_total"] = total_parse_failures
    return summary, detail


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summaries, details = [], []
    for path, cohort, domain in find_files():
        print(f"profiling {cohort}/{path.name} ...")
        s, d = profile_file(path, cohort, domain)
        summaries.append(s)
        details.extend(d)
    pd.DataFrame(summaries).to_csv(OUT_DIR / "profile_summary.csv", index=False)
    pd.DataFrame(details).to_csv(OUT_DIR / "profile_columns.csv", index=False)
    print(f"wrote {len(summaries)} summary rows and {len(details)} column rows to {OUT_DIR}")


if __name__ == "__main__":
    main()
