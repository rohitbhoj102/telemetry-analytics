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
