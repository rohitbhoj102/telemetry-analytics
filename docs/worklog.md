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
