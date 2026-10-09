# Telemetry & Product Data Analytics Take-Home

## Overview
TODO

## Approach
TODO

## Assumptions
TODO (see `docs/assumptions_log.md`)

## Environment
- Python 3.8.1 (the only interpreter available on the development machine; a newer Python is fine if you have one, but `requirements.txt` was resolved on 3.8).
- **Note:** Python 3.8 is past end-of-life. It was kept deliberately for this take-home because upgrading would cost time for little benefit; nothing in the analysis depends on 3.8-specific behaviour.
- Packages: pandas, duckdb, jupyter, matplotlib. Exact versions (including transitive dependencies) are pinned in `requirements.txt`, taken from `pip freeze` of the working environment.
- Raw data is read-only and is committed to the repo; generated outputs in `data/clean/` and `data/model/` are git-ignored.

## How to run
Setup (from the repo root):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Profiling (Step 1), from the repo root:

```bash
python src/profile.py            # reports/profiling/profile_summary.csv, profile_columns.csv
python src/inspect_decoded.py    # reports/profiling/decoded_data_*.{csv,txt}
python src/dup_diagnostics.py    # dup_diff_columns.csv, battery_empty_payload.csv, fault_status_order.csv
```

TODO: remaining pipeline steps (clean, model, analysis, dashboard).

## Repo structure
TODO
