# Worklog

Chronological activity log. Entry format: `### <Day DD Mon, HH:MM>` then **Did / Why / Found / Next**. Append only.

### Fri 09 Oct, 22:30
- **Did**
  - Step 0: checked the file inventory (4 + 4 CSVs, 2 bin JSONs, brief PDF, all present), created `.venv` (Python 3.8.1), installed pandas / duckdb / jupyter / matplotlib, wrote `requirements.txt`, `.gitignore`, empty folders, `README.md` stub.
  - Step 1: wrote `src/profile.py` (per-file summary and per-column detail CSVs) and `src/inspect_decoded.py` (structure of `decoded_data`, comparison with the bin JSONs). Outputs are in `reports/profiling/`.
  - Cross-checked a few observations ad hoc (serial coverage, fault type/value combinations, motor flattened columns vs payload). These checks were run as one-off commands and are not yet in a script. They need to be moved into the DQ module before any number is quoted in the report.
- **Why**: establish what the data actually contains before designing the DQ checks and the model.
- **Found**
  - Row counts match the file metadata for all 8 files.
  - Duplicates are heavy. Exact duplicate rows: faults 5,813 normal / 17,432 return-repair (51% / 87%); battery 680 / 5,347. Key-level duplicates exceed exact duplicates in every domain except motor-normal.
  - Battery: most rows have no payload (`decoded_data`, `log_type`, `log_id` all null): 1,516 / 2,766 normal, 32,033 / 32,614 return-repair (5 serials). The "32.6k vs 2.7k" imbalance is mostly empty rows. Payload rows are 1,250 vs 581.
  - Return-repair battery has 13 payloads in a different, flat key format (`/HEADER/...`) with no `eventLog` or `usage`.
  - `decoded_data` is valid JSON in every non-null row (0 parse failures). Motor Normal and return-repair payloads share the same 52 JSON paths. Normal's flattened bin columns equal the payload bins.
  - Normal and return-repair cohorts share zero serials in any domain.
  - Fault codes present: 11 (1 row), 12, 13. Type 7 is absent. Fault value 0 and fault 12/value 3 are absent.
  - Battery `hdr_timestamp` has values up to 2055-09-07 (24 normal rows after 2026-07-01).
- **Next** (Step 2, not started): DQ checks as reusable functions (`check, table, rows_affected, pct, action_taken`). Decide how to handle the duplicate groups and the empty-payload battery rows. Confirm the open questions with the user first.

### Fri 09 Oct, 23:00
- **Did**: wrote `src/dup_diagnostics.py`. After dropping exact duplicates, it lists which columns differ inside each key-level duplicate group. It also lists battery rows with no payload by serial, and runs a `fault_status` ordering check.
- **Why**: choose duplicate rules from evidence rather than collapsing blindly. Decisions from the user: drop exact dups; pick the key-dup rule after checking the differing columns; report empty battery rows but exclude them from analysis tables; keep Python 3.8 and note it in the README; keep `fault_status` unknown unless the data settles it.
- **Found**
  - Battery (payload rows) and RR motor: groups differ only in `server_timestamp` (58 + 35 battery, 28 RR motor), so these are re-uploads of identical payloads.
  - Clean sessions: groups differ almost only in `log3_time_sync_old/new` (Normal 1,734 of 1,737, RR 161 of 164). Exceptions: Normal 2 groups differ in battery fields; RR 2 groups differ in `clean_duration`, and 1 RR group in `running_firmware_version` only.
  - Faults: under the original key, groups differ in `hex_error_code`, `product_alarm_source` and `fault_status`, so these are distinct alarm records and not duplicates. With those 3 columns added to the key, the remaining groups differ only in `date` and/or `log2_time_sync_*` (Normal 363 groups, RR 18).
  - Empty battery rows: Normal 9 serials / 1,516 rows (all 9 also have payload rows); RR 5 serials / 32,033 rows (two serials hold 21,316 and 10,711; 3 of 5 also have payload rows).
  - `fault_status`: within machine + fault_type, the first event by `fault_timestamp` is 1 in 130 of 182 series (Normal) and 28 of 41 (RR). 0→1 and 1→0 transitions are about equally frequent, and 1→1 is common, so the data does not behave like clean Raised/Cleared pairs. Weak, small-sample, inference only.
- **Next**: Step 2 (DQ functions plus cleaning that applies the rules in the assumptions log). Not started.

### Fri 09 Oct, 23:15
- **Did**
  - Housekeeping: removed the two mentions of the project instructions file from `docs/assumptions_log.md` (README and `src/` had none); recorded the user's answers to the Step 1 questions in the assumptions log.
  - Step 2 (design only): `docs/parsing_spec.md`, built from three read-only scripts plus a loader: `src/payload_io.py` (loader), `src/cumulative_check.py`, `src/build_parsing_spec.py`; outputs in `reports/profiling/` (`cumulative_check.csv`, `cumulative_gaps.csv`, `parsing_spec_paths.csv`, `spec_checks.csv`, `spec_tables/`).
  - Ad-hoc Step 1 checks that are not yet in a script and are **to be moved into `src/dq.py` in Step 4**: cross-table serial coverage and cohort serial overlap; fault_type / fault_value combination counts; Normal motor flattened columns vs payload bins (partly covered by `build_parsing_spec.py` now); clean-session sentinel and range counts (65535 dust, 255 charge, `charge_end` > `charge_start`, `clean_duration` = 0, `log3_time_sync_old` = 0); `session_id` sharing across serials.
- **Why**: decide how to parse `decoded_data` before writing a parser, and test the brief's "cumulative weekly counters" statement on the data.
- **Found**
  - Six battery layouts/populations (not two): the return/repair "standard" group hides 26 label-keyed payloads; Normal splits into 4-cell (SV50 models) and 7-cell (SV53) populations with no shared serials.
  - All 12 battery bin arrays and 5 of 7 motor bin arrays match their definitions by exact name, location and length; the other 2 motor arrays match only by an inferred alias.
  - Motor bin arrays are 100% monotonic per serial; Normal battery is not (4-cell: 41–47% of serials), cause unknown.
  - Motor Normal has a 22-day median gap between observations (others about 7–8 days).
  - `cumulative_usage_duration_seconds` (Normal motor) is the sum of `ddm692_PowerBins`.
  - Re-uploads are heavy: Normal battery 1,250 payload rows = 551 distinct.
- **Next**: wait for answers to the open questions in `docs/parsing_spec.md` section 8. Step 3 (parser) is not started.

### Fri 09 Oct, 23:32
- **Did**: recorded the user's nine decisions on the Step 2 open questions in `docs/assumptions_log.md` and in a new section 9 of `docs/parsing_spec.md`. Added `dedup_effect()` to `src/cumulative_check.py` (output `reports/profiling/cumulative_dedup_effect.csv`) and ran an ad-hoc size check of the Normal 7-cell battery subset.
- **Why**: close the Step 2 questions and test two assumptions behind the decisions (comparable subset size; whether re-uploads explain counter decreases).
- **Found**
  - Comparable Normal battery subset (7-cell / SV53, with payload, de-duplicated): 133 records, 10 serials (8 with at least 2 records; 2 serials not in sessions, SV53 assumed). Return/Repair standard: 410 records, 42 serials. Thin for a cohort contrast.
  - Normal 4-cell counter decreases are unaffected by removing re-uploads (median monotonic share 41.2% in all variants; 5,092 decreasing pairs in all variants).
  - Normal 7-cell: one record has a 2055 `hdr_timestamp`.
- **Next**: Step 3 (parser) once the user opens it. The size check in the Found list is ad hoc and not yet in a script; move it into the DQ module in Step 4 with the other ad-hoc checks.

### Sun 11 Oct, 17:00
- **Did**
  - Part A: logged that the EEPROM document will not arrive (supersedes the earlier Data gap row; "Additional data needed" list added at the end of `docs/assumptions_log.md`). Wrote `src/link_checks.py` (read-only) → `reports/profiling/link_checks.csv` and logged the three results. Recorded the Step 4 duplicate-handling decision (classify and flag, never merge differing content; fault rates computed both ways).
  - Step 3: wrote `src/field_meanings.py` (single home for meanings, units, bin edges and column names, edges read from the bin JSONs), `src/payload_parsers.py` (one motor parser for both cohorts, battery parser) and `src/build_clean.py` (lossless build to `data/clean/*.parquet`, `parse_summary.csv`, `machine_lookup_checks.csv`, `clean_column_dictionary.csv`). Added `src/check_band_order.py` for the 2-D battery bin order. README run steps and raw-data placement note updated.
- **Why**: turn the Step 2 parsing spec into tables that Step 4 (de-duplication flags, DQ) can use, without cleaning anything yet.
- **Found**
  - Link checks: (a) 2,310 of 33,001 serial + `session_id` groups have more than one `date` (867 also differ in content, 244 ignoring nulls): holds. (b) **Contradicted:** median `date` - `fault_timestamp` lag is 2.5 h (Normal 7.2, RR 0.8), not about 155 h. (c) motor and battery `session_id` pairs are found in clean sessions in 3.2% and 3.5% of cases: holds.
  - All 1,034 motor payloads parse. Reconciliation on 470 Normal rows × 52 columns: 0 mismatches; `runtime_s` equals `cumulative_usage_duration_seconds` everywhere.
  - Battery: 1,792 parsed (1,250 Normal, 542 RR), 39 unparsed layout, 33,549 empty, 0 errors; counts equal the spec. 2-D bins are flat lists of 9, voltage slowest ([inferred], two supports).
  - Motor `model` is `683` / `692B` in 52 RR rows (3 serials). 24 Normal battery rows (2 serials) have a future `hdr_timestamp` and use the `server_timestamp` fallback (cut-off 2026-06-28 13:44:05).
  - Two bugs were caught by the built-in checks during the build (booleans are lower case in the raw text; array path duplicated the array name) and fixed before the final run.
- **Next**: answer the open questions (which snapshot record represents a battery payload; whether to keep Parquet for Tableau). Then Step 4: duplicate classification and flags, DQ checks, outlier and invalid-value flags. Not started.

### Sun 11 Oct, 17:05
- **Did**: recorded the user's answers on the open questions. Added `motor_model_raw` to `data/clean/motor.parquet` (replaces `model`; the machine lookup now takes model from sessions and faults only). Added a third counting rule to the fault lag check in `src/link_checks.py` and re-ran it and `src/build_clean.py` (row counts and motor reconciliation unchanged).
- **Why**: avoid presenting one typical lag when it depends on how duplicates are counted; stop motor variant codes from creating false multi-model machines.
- **Found**: fault lag median is 2.5 h on raw rows, 31.9 / 13.1 h (Normal / RR) with exact duplicates removed, and 167.6 / 96.2 h with one row per fault event; p90 reaches 2,086 h. `date` >= `fault_timestamp` in all but 13 rows. Multi-model serials: 0 in both cohorts.
- **Next**: Step 4 (duplicate classification and flags, DQ checks). Not started.

### Sun 11 Oct, 17:30
- **Did**
  - Step 4: wrote `src/dq.py` (reusable check functions; one code path for both cohorts) and ran it. Outputs: flagged tables `data/clean/dq/{clean_sessions,faults,motor,battery}.parquet`, `machine_dq.parquet`, `reports/dq/dq_summary.csv` plus detail CSVs (`missingness`, `value_ranges`, `outlier_thresholds`, `counter_decreases*`, `coverage`, `fault_type_counts`, `fault_rate_sensitivity`, `motor_variant_structure`).
  - Added `FAULT_TYPES` (brief meanings only) to `src/field_meanings.py`; moved the Step 1 serial-coverage and fault type/value counts into `dq.py`. README run steps updated. Recorded the decisions, limitations and numbers in `docs/assumptions_log.md`.
- **Why**: classify duplicates, flag invalid values and outliers, and define the analysis rows before deltas and the model (Steps 5-6).
- **Found**
  - Analysis rows: sessions 30,832 Normal / 4,641 RR; faults 3,674 / 861 (primary) and 4,159 / 1,172 (status rule); motor 470 / 488; battery 551 / 407. Sessions and faults match the sanity expectations; RR battery is 407 against about 411 (hash-only grouping merges 3 more than the Step 2 grouping; 1 unexplained).
  - Largest data issues: 94.8% of battery rows are empty payloads; 78% of fault rows are exact copies; 24.7% of session rows are fan-out/copies; dust 65535 in 9% (Normal) / 26% (RR) of analysis sessions; no temperature flag true in 47% of Normal sessions; `log3_time_sync_old` = 0 in 58% of Normal sessions.
  - Counter decreases: none in motor; 27 pairs in Normal battery (26 in the 4-cell pack), none in RR; re-upload removal does not change them.
  - Median faults per 100 sessions per machine differs by rule (Normal 6.5 vs 10.7; RR 9.7 vs 15.5).
  - Only 6 Normal machines are in all four tables (33 RR).
  - The 683 / 692B motor rows have the same payload structure as the others.
- **Next**: review the Step 4 decisions and open questions, then Step 5 (deltas, `dim_machine`, star schema) when opened.

### Sun 11 Oct, 17:50
- **Did**: recorded the user's answers on the Step 4 open questions (zero-duration handling kept; hash-only re-upload grouping kept with rationale). Added `battery_temp_state` to the DQ sessions table and summary (`src/dq.py`), re-ran `dq.py`. Logged the temperature-comparability and cohort-recording limitations.
- **Why**: stop the temperature flags and other differently-recorded fields from being used in cohort contrasts by mistake.
- **Found**: analysis-row counts unchanged. `not_reported` is 14,494 Normal (47.0%) and 150 RR (3.2%); no true conflicts.
- **Next**: Step 5 when opened.

### Sun 11 Oct, 18:00
- **Did**: renamed `flag_temp_conflict` to `flag_temp_not_reported` in `src/dq.py` (it marks rows with no temperature flag true; same rows as `battery_temp_state = not_reported`) and updated the summary wording; re-ran `dq.py`. Earlier log rows that say `flag_temp_conflict` refer to this flag under its old name.

### Sun 11 Oct, 18:15
- **Did**
  - Step 5: wrote `src/model.py` and ran it. Outputs in `data/model/` (Parquet and CSV): `dim_machine`, `dim_date`, `fact_session`, `fact_fault`, `fact_motor_period`, `fact_battery_period`, `machine_summary`. Validation and counts in `reports/model/` (`model_checks.csv`, `table_row_counts.csv`, `period_summary.csv`).
  - Wrote `docs/erd.md` (Mermaid ERD and grain of each table) and `docs/productionization.md` (bronze/silver/gold flowchart and notes). Updated README run steps and repo structure. Logged the Step 5 decisions and limitations in `docs/assumptions_log.md`.
- **Why**: turn the flagged analysis rows into a star schema with per-period deltas, the Tableau source and a per-machine summary, before EDA (Steps 6-7).
- **Found**
  - Rows: sessions 30,832 Normal / 4,641 RR; faults 3,674 / 861; motor periods 394 / 444; battery periods 523 / 365; 232 machines.
  - 53 checks pass, 0 fail. Invalid periods: 27 (all Normal battery, `counter_decrease`); motor 0.
  - Fault-to-session link: 99.36% (4,506 of 4,535).
  - Blanking fault metrics for machines absent from the faults table changes the Step 4 medians (Normal 6.53 to 10.64, RR 9.69 to 14.95, primary rule). This is logged as an open question.
- **Next**: review the Step 5 open questions, then Step 6 (EDA shortlist) when opened. No cohort interpretation was done in this step.

### Sun 11 Oct, 18:30
- **Did**: applied the answers to the Step 5 open questions in `src/model.py`: fault rates in `machine_summary` are zero-filled for machines with >= 10 sessions and no fault rows [assumed]; added sensitivity columns `faults_per_100_fault_machines_only_primary` / `_status_rule`. Re-ran `model.py`; updated `docs/erd.md`.
- **Why**: absence from the fault event log is treated as no faults (user decision); the blanked version stays visible as a sensitivity check.
- **Found**: 53 checks pass, 0 fail. Medians per cohort (primary / status rule): Normal zero-filled 6.53 / 10.67 (158 machines), fault-table machines only 10.64 / 14.47 (137); Return/Repair zero-filled 9.69 / 15.50 (36), fault-table machines only 14.95 / 18.09 (32). Zero-filled values equal Step 4, so the earlier contradiction is gone.
- **Next**: Step 6 when opened.

### Sun 11 Oct, 18:12
- **Did**
  - Step 6: wrote `src/eda_helpers.py` and `notebooks/01_eda_shortlist.ipynb` (executed end to end, outputs saved). Outputs: `reports/eda/shortlist.md` and six figures in `reports/figures/eda/`. Read only `data/model/`; no pipeline or earlier output changed.
  - Compared Normal and Return/Repair on six candidates (fault rate, fault mix, motor load, usage intensity, battery, end-of-record fault change) using machine-level medians, bootstrap intervals (2,000 resamples, seed fixed) and the robustness checks: SV53 only, outliers removed, alternative rule.
  - Logged the method decision and the limitations found in `docs/assumptions_log.md`.
- **Why**: shortlist 3-4 candidate insights for Step 7; all results exploratory.
- **Found**
  - Model mix matters: faults per 100 sessions per machine, Normal SV50 16.8, Normal SV53 1.1, RR 9.7. All-machine RR - Normal gap is +3.2 (interval spans 0); SV53-only it is +8.6 (interval 2.9 to 18.9).
  - Fault mix: only airway blockage "inlet blocked and in error" (12/2) shows an RR excess in every check; 12/1 and 13/1 flip sign under SV53-only.
  - Motor runtime per day is about 2x higher for RR (2.4 vs 4.9 min/day; model-matched; interval excludes 0). Motor 300-400 W share and battery health show no difference. Battery used per session SV53-only: 5 vs 10, coarse and interval touches 0.
  - End-of-record: Normal machines also show a higher fault rate in their last 28 days, so the rise is not RR-specific; the RR - Normal difference in change is not distinguishable from zero.
- **Next**: user decides which 3-4 candidates to take forward, then Step 7.

### Sun 11 Oct, 18:21
- **Did**
  - Step 6b: added section 6b to `notebooks/01_eda_shortlist.ipynb` (re-executed end to end) and a 6b section plus updated recommendation in `reports/eda/shortlist.md`. Extended `src/eda_helpers.py` (group argument for comparisons, `three_stats`, `with_direction`). Same method: machine-level medians, bootstrap intervals, n per group.
  - Checks: fault rates with and without Filter Wash (13/1, labelled as a maintenance alert, our grouping); SV50 vs SV53 within Normal by type/value; airway blockage Normal vs RR (all models, SV53 only); ROW-PROD and SV53-AB restrictions; motor runtime per day over common calendar months; airway blockage per motor runtime hour. 12/1 and 13/1 share results marked checked, not robust.
  - Logged the decisions and numbers in `docs/assumptions_log.md`.
- **Why**: apply the review decisions and test the final candidates against model mix, region, sub-model, calendar-period and exposure differences.
- **Found**
  - Airway blockage pooled rate per 100 sessions: Normal 4.2 vs RR 13.1 (all models); SV53 only 2.8 vs 13.1; ROW-PROD only 2.4 vs 13.1; direction holds in all variants (SV53-AB only intervals are wide for type 12).
  - SV50 vs SV53 within Normal: total 16.5 vs 4.3; Filter Wash is 81% of the gap; excluding it the gap is -2.3 (interval spans 0).
  - Motor runtime per day: RR about 2x Normal; holds for ROW-PROD only and over common months; SV53-AB only has the same direction with an interval spanning 0.
  - Per runtime hour (SV53, 45 vs 30 machines): 0.32 vs 1.73 type 12 faults.
- **Next**: user decides which candidates go into Step 7.

### Sun 11 Oct, 18:25
- **Did**: recorded the Step 6 gate decision (three final insights; C3, C5a, C5b, C6 and the 12/1 and 13/1 share results dropped or caveat-only) and the method rule (pooled fault rates with machine-resampled bootstrap intervals; machine-level medians for continuous measures). Added a "Final selection" section to `reports/eda/shortlist.md` (generated by the notebook, which was re-executed) and logged both as Decisions in `docs/assumptions_log.md`.
- **Why**: fix the scope for Step 7 before charts and the report are built.
- **Found**: no new analysis; numbers in the final section are the 6b results.
- **Next**: Step 7 (figures, including fault rate with and without 13/1).

### Sun 11 Oct, 22:12
- **Did**
  - Step 7: added `src/insights.py` (all computation and the four final charts) and `notebooks/02_insights.ipynb` (calls it, shows tables and charts, executed end to end). Wrote `reports/insights/key_numbers.csv` (152 rows), `reports/insights/step6_consistency.csv`, `reports/insights/insight_cards.md` and four charts (PNG 200 dpi and SVG) in `reports/figures/final/`.
  - Read only `data/model/`, plus the generated Step 3/4 reports for the DQ headline numbers (cross-checked against the model). No pipeline or earlier output changed.
- **Why**: finalise the three insights chosen at the Step 6 gate with the pooled-rate method and consistent charts for the slides.
- **Found**
  - All 61 numbers repeated from Step 6/6b match when recomputed; no difference.
  - Insight 1: Normal SV50 16.5 vs SV53 4.3 faults per 100 sessions; Filter Wash 81% of the gap; excluding it the gap is -2.3 (interval -5.3 to 0.7).
  - Insight 2 (SV53): type 12 per 100 sessions RR 13.1 vs Normal 2.8 (about 5x); 12/2 alone 6.5 vs 1.1; per runtime hour 1.73 vs 0.32.
  - Insight 3: motor minutes per day RR 4.87 vs Normal 2.38 (about 2x).
  - Under SV53-only, RR is also higher for Filter Wash (+4.1, interval 0.2 to 9.7), so the insight 1 claim is about model mix in total counts, not that Filter Wash is unrelated to cohort.
- **Next**: review the cards and charts; then the dashboard and slides (not started).

### Sun 11 Oct, 22:20
- **Did**
  - Step 7 review changes: `key_numbers.csv` now has `n_denominator` and `denominator_unit` (clean sessions, motor runtime hours or raw rows) beside the numerator in `n_events_or_sessions`; DQ rows name their source report in `script_or_cell`. Chart 02 now marks and states the like-for-like comparison (Return/Repair SV53 vs Normal SV53, difference 14.4 [2.4, 34.4], not vs Normal SV50). Insight 3 card caveats now state the window difference (median 91 vs 240 valid days) and the SV53-AB result (2.50 [-0.45, 5.38], interval spans 0). Re-ran `src/insights.py` and the notebook.
- **Why**: make each rate self-explanatory and stop the model-mix comparison being misread.
- **Found**: Step 6/6b consistency check still passes (61 checked, 0 differ). No numbers changed.
- **Next**: review, then dashboard and slides (not started).
