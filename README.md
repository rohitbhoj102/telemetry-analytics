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
- Raw inputs are company-provided, read-only and **not committed** (git-ignored). Place them at the repo root before running anything: `normal_machines/` (4 CSVs), `return_repair_machines/` (4 CSVs), `reference_files/` (`DDM_Bins.json`, `BMS_Bins.json`) and the assignment brief `take_home_assignment_details.pdf`.
- Generated outputs in `data/clean/` and `data/model/` are git-ignored; rebuild them with the run steps below.
- Parquet files are written and read with DuckDB (no pyarrow needed). To inspect one: `python -c "import duckdb; print(duckdb.sql(\"SELECT * FROM 'data/clean/motor.parquet' LIMIT 5\").df())"`.

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

Payload parsing spec (Step 2, read-only), in this order:

```bash
python src/cumulative_check.py     # cumulative_check.csv, cumulative_gaps.csv
python src/build_parsing_spec.py   # parsing_spec_paths.csv, spec_checks.csv, spec_tables/*.md (used in docs/parsing_spec.md)
```

Link checks and parse/harmonise (Step 3), from the repo root:

```bash
python src/link_checks.py        # reports/profiling/link_checks.csv (read-only cross-table checks)
python src/check_band_order.py   # reports/profiling/band_order_check.csv (evidence for the 2-D battery bin order)
python src/build_clean.py        # data/clean/*.parquet, parse_summary.csv, machine_lookup_checks.csv, clean_column_dictionary.csv
```

`build_clean.py` is lossless (one output row per raw row, `source_file` + `source_row` for traceability), does not de-duplicate or correct values, and exits non-zero if a row count or the motor reconciliation (parsed values vs the Normal flattened columns) fails. Field meanings, units and bin-to-column mappings live in `src/field_meanings.py`; `payload_parsers.py` holds the motor and battery parsers.

Data quality (Step 4), after `build_clean.py`:

```bash
python src/dq.py   # data/clean/dq/*.parquet (flagged tables + machine_dq), reports/dq/dq_summary.csv and detail CSVs
```

`dq.py` never changes the Step 3 outputs. Each table in `data/clean/dq/` has every original column, `dup_class` / `dup_keep` and other `flag_*` columns, cleaned analysis columns (`*_clean`) and `is_analysis_row`; later steps use only rows with `is_analysis_row = True` (faults also have `is_analysis_row_status_rule` for the sensitivity count). Raw values are never overwritten and no row is deleted. The run exits non-zero if an original column's row or non-null count changes. `reports/dq/dq_summary.csv` has one row per check and cohort (`check, table, cohort, rows_affected, pct, action_taken`); the basis of each count is in the check name.

TODO: remaining pipeline steps (deltas, model, analysis, dashboard).

## Repo structure
TODO
