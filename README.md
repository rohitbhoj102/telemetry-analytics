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

Data model (Step 5), after `dq.py`:

```bash
python src/model.py   # data/model/*.parquet and *.csv, reports/model/model_checks.csv, table_row_counts.csv, period_summary.csv
```

`model.py` reads only analysis rows from `data/clean/dq/` and writes a star schema: `dim_machine`, `dim_date`, `fact_session`, `fact_fault`, `fact_motor_period`, `fact_battery_period` and `machine_summary`. Motor and battery facts are one row per interval between consecutive snapshots (with `days_elapsed`), and a counter decrease makes that period's deltas missing (`delta_valid = False`) rather than being treated as a reset. The CSV files are the Tableau source. The run exits non-zero, and writes no tables, if any validation check fails. Grain, keys and rules are in `docs/erd.md`; the production sketch is in `docs/productionization.md`.

EDA shortlist (Step 6), after `model.py`, from the repo root with the virtual environment active:

```bash
cd notebooks && jupyter nbconvert --to notebook --execute --inplace 01_eda_shortlist.ipynb
```

The notebook reads only `data/model/` (helpers in `src/eda_helpers.py`), keeps its outputs in the notebook, and writes `reports/eda/shortlist.md` and the figures in `reports/figures/eda/`. Run it from the `notebooks/` folder (it imports `../src`).

Final insights (Step 7), after `model.py`, from the repo root with the virtual environment active:

```bash
python src/insights.py   # reports/insights/key_numbers.csv, step6_consistency.csv, reports/figures/final/*.png and *.svg
cd notebooks && jupyter nbconvert --to notebook --execute --inplace 02_insights.ipynb
```

`src/insights.py` holds all Step 7 computation (pooled fault rates with machine-resampled bootstrap intervals; machine-level medians for continuous measures) and the four final charts. It reads `data/model/`; the DQ headline numbers come from the generated reports in `reports/profiling/` and `reports/dq/` and are cross-checked against the model. `reports/insights/key_numbers.csv` has one row per number used downstream, `step6_consistency.csv` compares the numbers repeated from Step 6/6b, and `reports/insights/insight_cards.md` has the write-up of each insight with its caveats. `02_insights.ipynb` calls the module and shows the tables and charts.

Tableau export (Step 8 prep), after `insights.py`:

```bash
python src/tableau_export.py   # data/model/tableau/tableau_machines.csv, tableau_insight_rates.csv, tableau_dq_volume.csv
```

`src/tableau_export.py` writes three flat CSVs with plain labels: one row per machine (232), the bar segments of the two fault charts (10), and raw vs analysis row counts per table and cohort (16). Rates and row counts are read from `reports/insights/key_numbers.csv` and re-computed from `data/model/`; the script stops with an assertion error if they differ, if the components of a bar do not add to its total, or if the 6-character `machine_id` is not unique.

TODO: remaining pipeline steps (Tableau workbook).

## Repo structure
```
normal_machines/, return_repair_machines/, reference_files/   raw inputs (read-only, git-ignored)
src/            profiling, parsing, build_clean.py, dq.py, model.py, eda_helpers.py (Step 6 helpers), insights.py (Step 7 numbers and charts), tableau_export.py (Step 8 Tableau CSVs), field_meanings.py (field meanings in one place)
data/clean/     parsed tables (Step 3); data/clean/dq/ flagged tables with is_analysis_row (Step 4)
data/model/     star schema, Parquet + CSV (Step 5); data/model/tableau/ flat Tableau CSVs (Step 8 prep)
reports/        profiling/, dq/, model/ (generated checks and summaries); eda/ (shortlist.md, Step 6); insights/ (key_numbers.csv, insight_cards.md, Step 7); figures/eda/ (Step 6 charts) and figures/final/ (Step 7 charts, PNG and SVG)
docs/           assumptions_log.md, worklog.md, parsing_spec.md, erd.md, productionization.md
notebooks/      EDA and presentation notebooks (01_eda_shortlist.ipynb, Step 6; 02_insights.ipynb, Step 7)
```
