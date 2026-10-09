# Parsing spec: mapping `decoded_data` to the bin definitions

Step 2 of the pipeline. **Design only**: nothing here parses data into tables, cleans anything, or changes raw files. Step 3 implements the parser from this spec.

## 0. Conventions and how to reproduce

| Label | Meaning |
|---|---|
| **[verified]** | Checked against the data or files by a named script. |
| **[inferred]** | A reading that fits the evidence but is not stated in the brief or the bin JSONs. |
| **[inferred from key name]** | A meaning guessed from a key name only. Treat as unconfirmed. |
| unknown | Neither the brief nor the bin JSONs say. Not guessed. |

Meaning policy: a field's meaning is recorded only if the brief or a bin JSON states it. The brief names metric *categories* only (motor: speed, power, pressure, exhaust-temperature distributions, ambient temperature, ambient pressure, cumulative runtime; battery: cell voltages, SoC, SoH, charge and discharge behaviour and statistics, runtime, battery temperature, resistance estimates). It does not define individual keys. Bin JSONs define bin arrays only (name, unit, edges, size).

The EEPROM debug-log document is still missing (see `docs/assumptions_log.md`), so several field meanings below may change when it arrives.

Reproduce, from the repo root, in this order:

```bash
python src/profile.py
python src/inspect_decoded.py
python src/cumulative_check.py      # reports/profiling/cumulative_check.csv, cumulative_gaps.csv
python src/build_parsing_spec.py    # reports/profiling/spec_tables/*.md, parsing_spec_paths.csv, spec_checks.csv
```

The tables below are generated output (copied from `reports/profiling/spec_tables/`). The full path-level data for every group is in `reports/profiling/parsing_spec_paths.csv`. Percentages count **payload rows before any de-duplication**; the duplicate rule is a Step 4 decision.

## 1. Payload groups

Step 1 expected five groups. The data has **six payload layouts** (battery return/repair splits in three) and the Normal battery contains two disjoint populations.

| Group | Non-empty payload rows | Serials | hdr_timestamp range | Distinct JSON paths |
|---|---|---|---|---|
| motor_normal | 470 | 76 | 2025-07-11 to 2026-06-21 | 51 |
| motor_rr | 564 | 44 | 2025-07-29 to 2026-06-25 | 51 |
| battery_normal | 1250 | 28 | 2025-06-19 to 2055-09-07 | 174 |
| battery_rr_standard | 542 | 42 | 2025-07-14 to 2026-06-21 | 160 |
| battery_rr_labelled | 26 | 1 | 2025-05-28 to 2025-07-01 | 296 |
| battery_rr_flat | 13 | 2 | 2025-05-21 to 2025-05-28 | 271 |

Layout variants, with the product model of each serial taken from the sessions files:

| Group | Root-key signature | Cell-voltage array lengths | Payload rows | Serials | hdr_timestamp range | Models (from sessions) |
|---|---|---|---|---|---|---|
| battery_normal | root keys: bpa_SNO, eventLog, miscAndSibyl, usage | 4 | 1077 | 18 | 2025-06-19 to 2026-06-17 | SV50-AA, SV50-AC, SV50-AF, not in sessions |
| battery_normal | root keys: eventLog, header, miscAndSibyl, usage | 7 | 173 | 10 | 2025-09-03 to 2055-09-07 | SV53-AB, SV53-AC, SV53-AE, SV53-AF, not in sessions |
| battery_rr_standard | root keys: eventLog, header, miscAndSibyl, usage | 7 | 542 | 42 | 2025-07-14 to 2026-06-21 | SV53-AB, SV53-AC, SV53-AE, SV53-AF, not in sessions |
| battery_rr_labelled | root keys: eventLog, header, miscAndSibyl, usage | 7 | 26 | 1 | 2025-05-28 to 2025-07-01 | SV53-AE |
| battery_rr_flat | flat /SECTION/... keys | 7 | 13 | 2 | 2025-05-21 to 2025-05-28 | SV53-AA, SV53-AE |

Findings:

- **[verified]** Motor Normal and Motor RR have the same 51 JSON paths (plus the root), all present in 100% of payloads.
- **[verified]** Return/repair battery has three layouts: *standard* (numeric bin arrays; 542 rows), *labelled* (same top-level keys, but `usage` bins are dicts keyed by text labels; 26 rows, 1 serial) and *flat* (no `eventLog`; 13 rows, 2 serials; all values are strings). Step 1 reported only the flat layout. The two label-based layouts fall between 2025-05-21 and 2025-07-01, before any standard return/repair row (earliest 2025-07-14). Why the layout changed is unknown.
- **[verified]** The Normal battery has two populations with no serial in common: **4-cell packs** (root-level `bpa_SNO`, no `header`, extra keys `counter`, `checksum`, `current secondary`, `secReason`; 1,077 rows; 18 serials) and **7-cell packs** (`header` object; 173 rows; 10 serials). Serials with a known model are SV50-* for 4-cell and SV53-* for 7-cell. Return/repair batteries are all 7-cell/SV53. A like-for-like Normal vs return/repair battery comparison therefore needs the 7-cell/SV53 subset or a variant column.
- **[verified]** The battery and RR-motor files contain many re-uploads of the same device record: Normal battery has 1,250 payload rows but 551 distinct (serial, `hdr_timestamp`, payload) combinations; battery RR standard 542 → 410; motor RR 564 → 492 (`reports/profiling/cumulative_gaps.csv`).

## 2. Motor payload (Normal and Return/Repair)

Both cohorts share this structure. In the tables `N` = Normal (470 payloads), `RR` = Return/Repair (564 payloads).

### 2.1 Scalars and objects

| Path | % payloads (N / RR) | Type | JSON types | Meaning | Monotonic % serials (decreasing pairs/pairs) (N / RR) |
|---|---|---|---|---|---|
| `ddmUsage` | 100% / 100% | object | dict | container | n/a / n/a |
| `ddmUsage.ambTempMeas` | 100% / 100% | scalar | int | unknown | 87% (7/394) / 94.6% (2/448) |
| `ddmUsage.ambientPressure_Pa` | 100% / 100% | scalar | int | [inferred from key name] ambient pressure, Pa (brief lists 'ambient pressure'). Normal `ambient_pressure_kpa` = value/1000 (verified) | 1.9% (167/394) / 8.1% (211/448) |
| `ddmUsage.ambientTemperature_mC` | 100% / 100% | scalar | int | [inferred from key name] ambient temperature, milli-degC (brief lists 'ambient temperature'). Normal `ambient_temperature_C` = value/1000 (verified) | 1.9% (177/394) / 5.4% (212/448) |
| `ddmUsage.barometerDerCounter` | 100% / 100% | scalar | int | unknown | constant / constant |
| `ddmUsage.bmsAmbientTemperature_mC` | 100% / 100% | scalar | int | [inferred from key name] ambient temperature seen by the BMS, milli-degC | 1.9% (191/394) / 2.7% (219/448) |
| `ddmUsage.ddm692_BarometerTempBins` | 100% / 100% | object | dict | container | n/a / n/a |
| `ddmUsage.ddm692_BarometerTempBins.formatId` | 100% / 100% | scalar | int | [inferred from key name] format/version id of the record or table | constant / constant |
| `ddmUsage.ddm692_BarometerTempBins.tableSize` | 100% / 100% | scalar | int | [verified] equals the length of the sibling `bins` array in every row (see spec_checks.csv) | constant / constant |
| `ddmUsage.ddm692_ExhaustTempBins` | 100% / 100% | object | dict | container | n/a / n/a |
| `ddmUsage.ddm692_ExhaustTempBins.formatId` | 100% / 100% | scalar | int | [inferred from key name] format/version id of the record or table | constant / constant |
| `ddmUsage.ddm692_ExhaustTempBins.tableSize` | 100% / 100% | scalar | int | [verified] equals the length of the sibling `bins` array in every row (see spec_checks.csv) | constant / constant |
| `ddmUsage.ddm692_FisfTempBins` | 100% / 100% | object | dict | container | n/a / n/a |
| `ddmUsage.ddm692_FisfTempBins.formatId` | 100% / 100% | scalar | int | [inferred from key name] format/version id of the record or table | constant / constant |
| `ddmUsage.ddm692_FisfTempBins.tableSize` | 100% / 100% | scalar | int | [verified] equals the length of the sibling `bins` array in every row (see spec_checks.csv) | constant / constant |
| `ddmUsage.ddm692_NormSpeedBins` | 100% / 100% | object | dict | container | n/a / n/a |
| `ddmUsage.ddm692_NormSpeedBins.formatId` | 100% / 100% | scalar | int | [inferred from key name] format/version id of the record or table | constant / constant |
| `ddmUsage.ddm692_NormSpeedBins.tableSize` | 100% / 100% | scalar | int | [verified] equals the length of the sibling `bins` array in every row (see spec_checks.csv) | constant / constant |
| `ddmUsage.ddm692_PowerBins` | 100% / 100% | object | dict | container | n/a / n/a |
| `ddmUsage.ddm692_PowerBins.formatId` | 100% / 100% | scalar | int | [inferred from key name] format/version id of the record or table | constant / constant |
| `ddmUsage.ddm692_PowerBins.tableSize` | 100% / 100% | scalar | int | [verified] equals the length of the sibling `bins` array in every row (see spec_checks.csv) | constant / constant |
| `ddmUsage.ddm692_PressureBins` | 100% / 100% | object | dict | container | n/a / n/a |
| `ddmUsage.ddm692_PressureBins.formatId` | 100% / 100% | scalar | int | [inferred from key name] format/version id of the record or table | constant / constant |
| `ddmUsage.ddm692_PressureBins.tableSize` | 100% / 100% | scalar | int | [verified] equals the length of the sibling `bins` array in every row (see spec_checks.csv) | constant / constant |
| `ddmUsage.ddm692_SpeedBins` | 100% / 100% | object | dict | container | n/a / n/a |
| `ddmUsage.ddm692_SpeedBins.formatId` | 100% / 100% | scalar | int | [inferred from key name] format/version id of the record or table | constant / constant |
| `ddmUsage.ddm692_SpeedBins.tableSize` | 100% / 100% | scalar | int | [verified] equals the length of the sibling `bins` array in every row (see spec_checks.csv) | constant / constant |
| `ddmUsage.ddmOnButNotRunTime_s` | 100% / 100% | scalar | int | [inferred from key name] seconds powered on but not running | 100% (0/394) / 100% (0/448) |
| `ddmUsage.exhaustDerCounter` | 100% / 100% | scalar | int | unknown | constant / constant |
| `ddmUsage.filterStateChgCounter` | 100% / 100% | scalar | int | [inferred from key name] count of filter state changes | constant / constant |
| `ddmUsage.filterWashCounter` | 100% / 100% | scalar | int | [inferred from key name] count of filter washes (brief has fault type 13 'Filter Wash') | 100% (0/394) / 100% (0/448) |
| `ddmUsage.filterWashStatus` | 100% / 100% | scalar | int | [inferred from key name] filter-wash status; coding unknown | 50% (39/394) / 56.8% (39/448) |
| `ddmUsage.fwFilteredDeqv_mm` | 100% / 100% | scalar | int | unknown | 1.9% (211/394) / 10.8% (224/448) |
| `ddmUsage.fwPrevFilteredDeqv_mm` | 100% / 100% | scalar | int | unknown | 1.9% (211/394) / 10.8% (224/448) |
| `ddmUsage.motorThermalBemfDerCounter` | 100% / 100% | scalar | int | unknown | constant / constant |
| `ddmUsage.packVoltLow_mV` | 100% / 100% | scalar | int | [inferred from key name] low pack voltage, mV | constant / constant |
| `ddmUsage.powerReset` | 100% / 100% | scalar | int | unknown | 14.8% (82/394) / 18.9% (79/448) |
| `ddmUsage.ppcPeakPowerTimeReset_ms` | 100% / 100% | scalar | int | unknown | 46.3% (50/394) / 54.1% (40/448) |
| `ddmUsage.ppcPeakPowerTime_ms` | 100% / 100% | scalar | int | unknown | 90.7% (5/394) / 89.2% (7/448) |
| `header` | 100% / 100% | object | dict | container | n/a / n/a |
| `header.checksum` | 100% / 100% | scalar | int | [inferred from key name] record checksum (not a measurement) | 3.7% (189/394) / 8.1% (220/448) |
| `header.dataSize` | 100% / 100% | scalar | int | [inferred from key name] record size; unit unknown. Equals RR `log_size` (verified) | constant / constant |
| `header.formatId` | 100% / 100% | scalar | int | [inferred from key name] format/version id of the record or table | constant / constant |
| `header.writeCount` | 100% / 100% | scalar | int | [inferred from key name] write counter. Equals Normal `write_count` column (verified) | 100% (0/394) / 100% (0/448) |

### 2.2 Bin arrays

| Array path | % payloads (N / RR) | Definition | Match status | Length vs declared | Bin edges (as declared) | Declared unit (array) | All-zero rows (N / RR) | Monotonic % serials (N / RR) |
|---|---|---|---|---|---|---|---|---|
| `ddmUsage.ddm692_BarometerTempBins.bins` | 100% / 100% | `ddm692_BarTempBins` | [inferred] payload name `ddm692_BarometerTempBins` vs definition `ddm692_BarTempBins`, length matches | 10 vs 10 | speed [krpm]: 10, 20, 30, 40, 50, 60, 70, 80, 90 | second | 0% / 0% | 100% (0/394) / 100% (0/448) |
| `ddmUsage.ddm692_ExhaustTempBins.bins` | 100% / 100% | `ddm692_ExhaustTempBins` | [verified] exact name, length matches | 10 vs 10 | speed [celsius]: 10, 20, 30, 40, 50, 60, 70, 80, 90 | second | 0% / 0% | 100% (0/394) / 100% (0/448) |
| `ddmUsage.ddm692_FisfTempBins.bins` | 100% / 100% | `ddm692_FisfTempBins` | [verified] exact name, length matches | 10 vs 10 | speed [celsius]: 14, 28, 42, 56, 70, 84, 98, 112, 126 | second | 0% / 0% | 100% (0/394) / 100% (0/448) |
| `ddmUsage.ddm692_NormSpeedBins.bins` | 100% / 100% | `ddm692_NormSpeedBins` | [verified] exact name, length matches | 14 vs 14 | speed [krpm]: 109.9, 111.9, 113.9, 115.9, 117.9, 119.9, 121.9, 123.9, 125.9, 127.9, 129.9, 133, 150 | second | 100% / 100% | constant / constant |
| `ddmUsage.ddm692_PowerBins.bins` | 100% / 100% | `ddm692_PowerBins` | [verified] exact name, length matches | 14 vs 14 | speed [watts]: 50, 75, 100, 125, 150, 200, 300, 400, 500, 600, 700, 800, 900 | second | 0% / 0% | 100% (0/394) / 100% (0/448) |
| `ddmUsage.ddm692_PressureBins.bins` | 100% / 100% | `ddm692_PressBins` | [inferred] payload name `ddm692_PressureBins` vs definition `ddm692_PressBins`, length matches | 9 vs 9 | speed [kilo-pascal]: 70, 75, 80, 85, 90, 95, 100, 105 | second | 0% / 0% | 100% (0/394) / 100% (0/448) |
| `ddmUsage.ddm692_SpeedBins.bins` | 100% / 100% | `ddm692_SpeedBins` | [verified] exact name, length matches | 25 vs 25 | speed [krpm]: 45, 55, 65, 75, 85, 95, 105, 110, 115, 120, 122.5, 125, 127.5, 130, 132.5, 135, 137.5, 140, 142.5, 145, 147.5, 150, 155, 160 | second | 0% / 0% | 100% (0/394) / 100% (0/448) |

Notes:

- **[verified]** The seven arrays all sit at `ddmUsage.<name>.bins`, which is the location `DDM_Bins.json` gives (`jsonLoc` `ddmUsage` + `field` `bins`). `tableSize` equals the array length in every row of both cohorts.
- **[verified]** Edge counts are consistent with array length (n edges = length − 1) for all seven arrays. Declared unit of every `ddm692_*` array is `second`, i.e. time per bin.
- **[verified]** The Normal file's flattened columns are a subset of the payload: the 25 `speed_bin_*` columns equal `ddm692_SpeedBins`, the 14 `power_*` columns equal `ddm692_PowerBins`, and the 7 `exhaust_temperature_bin_*` columns equal the first 7 bins of `ddm692_ExhaustTempBins` (checked by `src/inspect_decoded.py` and `src/build_parsing_spec.py`). The edges in those column names match the declared edges (compared by reading the names; not automated).
- **[verified]** Exhaust bins 8–10 are zero in every row of both cohorts, so the 7-column Normal file loses nothing.
- **[verified]** `ddm692_NormSpeedBins` is all zero in every row of both cohorts: it carries no information in this data.
- **[verified]** Only `sum(PowerBins)` equals the Normal column `cumulative_usage_duration_seconds` (100% of rows); `sum(SpeedBins)` matches in 30.6%. The bin arrays therefore do **not** share one time base, so a "total time" must be defined per array.
- **[inferred]** `ddm692_PressureBins` ↔ `ddm692_PressBins` and `ddm692_BarometerTempBins` ↔ `ddm692_BarTempBins`. The payload names differ from the JSON names but lengths match (9, 10). Supporting evidence for the pressure alias is weak: the row's ambient pressure falls in a non-empty bin in 100% of rows but in the modal bin in only 72% (N) / 61% (RR). No comparable check exists for the barometer temperature.

Consistency checks (`reports/profiling/spec_checks.csv`):

| check | result | rows |
|---|---|---|
| Normal `cumulative_usage_duration_seconds` == sum(ddm692_PowerBins.bins) | 100.0% | 470 |
| Normal `cumulative_usage_duration_seconds` == sum(ddm692_SpeedBins.bins) | 30.6% | 470 |
| Normal `write_count` == header.writeCount | 100.0% | 470 |
| Normal `ambient_pressure_pa` == ddmUsage.ambientPressure_Pa | 100.0% | 470 |
| Normal `ambient_temperature_mC` == ddmUsage.ambientTemperature_mC | 100.0% | 470 |
| RR `log_size` == header.dataSize | 100.0% | 564 |
| Normal: ddm692_NormSpeedBins.bins all zero | 100.0% | 470 |
| Normal: ddm692_ExhaustTempBins bins 8-10 all zero | 100.0% | 470 |
| Normal: tableSize == len(bins) for every bin container | 100.0% | 470 |
| Normal: ambient kPa falls in a non-empty ddm692_PressureBins bin (supports inferred Pressure~Press alias; weak) | 100.0% | 470 |
| Normal: ambient kPa falls in the modal ddm692_PressureBins bin | 72.3% | 470 |
| RR: ddm692_NormSpeedBins.bins all zero | 100.0% | 564 |
| RR: ddm692_ExhaustTempBins bins 8-10 all zero | 100.0% | 564 |
| RR: tableSize == len(bins) for every bin container | 100.0% | 564 |
| RR: ambient kPa falls in a non-empty ddm692_PressureBins bin (supports inferred Pressure~Press alias; weak) | 100.0% | 564 |
| RR: ambient kPa falls in the modal ddm692_PressureBins bin | 60.5% | 564 |

## 3. Battery payload, standard layout (Normal and Return/Repair)

`N` = Normal battery (1,250 payloads: 4-cell 86%, 7-cell 14%), `RR` = Return/Repair standard layout (542 payloads, all 7-cell). A path present in 86% / 14% / 100% is a variant difference, not missing data. For the `Meaning` column, a key suggesting a brief category (e.g. `cellVolt` → "cell voltages") is still marked **[inferred from key name]**.

### 3.1 Scalars, objects and record lists

`eventLog.events` always holds 15 records and `eventLog.faults` 2 records (all 1,250 N and all RR payloads). Their fields are listed with `[]`. `cellVolt` has 4 or 7 values (4 for the 4-cell variant). `temp` is an integer in the 7-cell variant and a 3-value list in the 4-cell variant. State and reason fields are numeric codes with no documented coding.

| Path | % payloads (N / RR) | Type | JSON types | Meaning | Monotonic % serials (decreasing pairs/pairs) (N / RR) |
|---|---|---|---|---|---|
| `bpa_SNO` | 86% / - | scalar | str | [inferred from key name] pack serial number | n/a / - |
| `eventLog` | 100% / 100% | object | dict | container | n/a / n/a |
| `eventLog.checksum` | 86% / - | scalar | int | [inferred from key name] record checksum (not a measurement) | 0% (190/400) / - |
| `eventLog.counter` | 86% / - | scalar | int | [inferred from key name] record counter | 47.1% (25/400) / - |
| `eventLog.eventFaultIndex` | 100% / 100% | scalar | int | [inferred from key name] index into the fault ring | constant / constant |
| `eventLog.eventIndex` | 100% / 100% | scalar | int | [inferred from key name] index into the event ring | 0% (263/523) / 10.8% (171/368) |
| `eventLog.events` | 100% / 100% | record list | list | record list (event/fault snapshots) | n/a / n/a |
| `eventLog.events[]` | 100% / 100% | object | dict | container | n/a / n/a |
| `eventLog.events[].cellVolt` | 100% / 100% | numeric array (not a bin array) | list | [inferred from key name] cell voltages (brief lists 'cell voltages'); unit unknown | n/a / n/a |
| `eventLog.events[].chargeReason` | 100% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.events[].current pack` | 100% / 100% | scalar | int | [inferred from key name] pack current; unit unknown | n/a / n/a |
| `eventLog.events[].current secondary` | 86% / - | scalar | int | unknown | n/a / - |
| `eventLog.events[].dischgReason` | 100% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.events[].fuelGauge` | 100% / 100% | scalar | int | [inferred from key name] fuel gauge reading; unit unknown | n/a / n/a |
| `eventLog.events[].inputOutput` | 100% / 100% | scalar | int | unknown (bit field?, not documented) | n/a / n/a |
| `eventLog.events[].lockout` | 100% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.events[].packVolt` | 100% / 100% | scalar | int | [inferred from key name] pack voltage; unit unknown | n/a / n/a |
| `eventLog.events[].reason` | 100% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.events[].runTime` | 100% / 100% | scalar | int | [inferred from key name] runtime (brief lists 'runtime'); unit unknown | n/a / n/a |
| `eventLog.events[].secReason` | 86% / - | scalar | int | unknown | n/a / - |
| `eventLog.events[].state` | 100% / 100% | scalar | int | unknown (enumeration, coding not documented) | n/a / n/a |
| `eventLog.events[].stateOfCharge` | 100% / 100% | scalar | int | [inferred from key name] state of charge (brief lists SoC); scale unknown | n/a / n/a |
| `eventLog.events[].stateOfHealth` | 100% / 100% | scalar | int | [inferred from key name] state of health (brief lists SoH); scale unknown | n/a / n/a |
| `eventLog.events[].stateReason` | 14% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.events[].temp` | 100% / 100% | other (int or array) | int\|list | [inferred from key name] temperature (brief lists 'battery temperature'); unit unknown | n/a / n/a |
| `eventLog.events[].time` | 100% / 100% | scalar | int | unknown (time base and unit not stated) | n/a / n/a |
| `eventLog.faults` | 100% / 100% | record list | list | record list (event/fault snapshots) | n/a / n/a |
| `eventLog.faults[]` | 100% / 100% | object | dict | container | n/a / n/a |
| `eventLog.faults[].cellVolt` | 100% / 100% | numeric array (not a bin array) | list | [inferred from key name] cell voltages (brief lists 'cell voltages'); unit unknown | n/a / n/a |
| `eventLog.faults[].chargeReason` | 100% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.faults[].current pack` | 100% / 100% | scalar | int | [inferred from key name] pack current; unit unknown | n/a / n/a |
| `eventLog.faults[].current secondary` | 86% / - | scalar | int | unknown | n/a / - |
| `eventLog.faults[].dischgReason` | 100% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.faults[].fuelGauge` | 100% / 100% | scalar | int | [inferred from key name] fuel gauge reading; unit unknown | n/a / n/a |
| `eventLog.faults[].inputOutput` | 100% / 100% | scalar | int | unknown (bit field?, not documented) | n/a / n/a |
| `eventLog.faults[].lockout` | 100% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.faults[].packVolt` | 100% / 100% | scalar | int | [inferred from key name] pack voltage; unit unknown | n/a / n/a |
| `eventLog.faults[].reason` | 100% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.faults[].runTime` | 100% / 100% | scalar | int | [inferred from key name] runtime (brief lists 'runtime'); unit unknown | n/a / n/a |
| `eventLog.faults[].secReason` | 86% / - | scalar | int | unknown | n/a / - |
| `eventLog.faults[].state` | 100% / 100% | scalar | int | unknown (enumeration, coding not documented) | n/a / n/a |
| `eventLog.faults[].stateOfCharge` | 100% / 100% | scalar | int | [inferred from key name] state of charge (brief lists SoC); scale unknown | n/a / n/a |
| `eventLog.faults[].stateOfHealth` | 100% / 100% | scalar | int | [inferred from key name] state of health (brief lists SoH); scale unknown | n/a / n/a |
| `eventLog.faults[].stateReason` | 14% / 100% | scalar | int | unknown (code, not documented) | n/a / n/a |
| `eventLog.faults[].temp` | 100% / 100% | other (int or array) | int\|list | [inferred from key name] temperature (brief lists 'battery temperature'); unit unknown | n/a / n/a |
| `eventLog.faults[].time` | 100% / 100% | scalar | int | unknown (time base and unit not stated) | n/a / n/a |
| `header` | 14% / 100% | object | dict | container | n/a / n/a |
| `header.bpa_SNO` | 14% / 100% | scalar | str | [inferred from key name] pack serial number | n/a / n/a |
| `header.bpa_WIP` | 14% / 100% | scalar | str | [inferred from key name] pack work-in-progress id | n/a / n/a |
| `header.configID` | 14% / 100% | scalar | int | [inferred from key name] configuration id | constant / constant |
| `header.power_ups` | 14% / 100% | scalar | int | [inferred from key name] number of power-ups | 87.5% (1/123) / 100% (0/368) |
| `header.rated_power` | 14% / 100% | scalar | int | [inferred from key name] rated power; unit unknown | constant / constant |
| `header.serial_HW` | 14% / 100% | scalar | str | [inferred from key name] hardware serial | n/a / n/a |
| `header.ver_FW` | 14% / 100% | scalar | str | [inferred from key name] firmware version string | n/a / n/a |
| `header.ver_SW` | 14% / 100% | scalar | str | [inferred from key name] software version string | n/a / n/a |
| `header.ver_Sibyl` | 14% / 100% | scalar | str | [inferred from key name] algorithm version string | n/a / n/a |
| `miscAndSibyl` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.counter` | 86% / - | scalar | int | [inferred from key name] record counter | 47.1% (25/400) / - |
| `miscAndSibyl.miscLog` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.miscLog.chgErrors` | 14% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.miscLog.chgErrors.ChgErrPresent` | 14% / 100% | scalar | int | unknown (key name only) | constant / constant |
| `miscAndSibyl.miscLog.chgErrors.ChgOverCurrent` | 14% / 100% | scalar | int | unknown (key name only) | constant / constant |
| `miscAndSibyl.miscLog.chgErrors.CycleCharger` | 14% / 100% | scalar | int | unknown (key name only) | constant / constant |
| `miscAndSibyl.miscLog.devMode` | 86% / - | object | dict | container | n/a / - |
| `miscAndSibyl.miscLog.devMode.devModeUsed` | 86% / - | scalar | int | [inferred from key name] flag, dev mode used | constant / - |
| `miscAndSibyl.miscLog.flags` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.miscLog.flags.Behaviour_Flags` | 100% / 100% | scalar | int | [inferred from key name] flag | 96% (1/523) / 94.6% (2/368) |
| `miscAndSibyl.miscLog.flags.Debug_Config` | 100% / 100% | scalar | int | [inferred from key name] flag | constant / constant |
| `miscAndSibyl.miscLog.flags.Main_Body_Fault` | 100% / 100% | scalar | int | [inferred from key name] flag | constant / constant |
| `miscAndSibyl.miscLog.flags.Pack_Flat` | 100% / 100% | scalar | int | [inferred from key name] flag | 100% (0/523) / constant |
| `miscAndSibyl.miscLog.flags.Stats_Frozen` | 100% / 100% | scalar | int | [inferred from key name] flag | constant / 100% (0/368) |
| `miscAndSibyl.miscLog.resets` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.miscLog.resets.Brown_Out_12_Resets` | 100% / 100% | scalar | int | [inferred from key name] reset count | constant / constant |
| `miscAndSibyl.miscLog.resets.Brown_Out_33_Resets` | 100% / 100% | scalar | int | [inferred from key name] reset count | constant / constant |
| `miscAndSibyl.miscLog.resets.External_Resets` | 100% / 100% | scalar | int | [inferred from key name] reset count | 100% (0/523) / constant |
| `miscAndSibyl.miscLog.resets.Power_On_Resets` | 100% / 100% | scalar | int | [inferred from key name] reset count | 60% (26/523) / 100% (0/368) |
| `miscAndSibyl.miscLog.resets.RTC_Resets` | 100% / 100% | scalar | int | [inferred from key name] reset count | 96% (1/523) / 100% (0/368) |
| `miscAndSibyl.miscLog.resets.System_Resets` | 100% / 100% | scalar | int | [inferred from key name] reset count | constant / constant |
| `miscAndSibyl.miscLog.resets.Watchdog_Resets` | 100% / 100% | scalar | int | [inferred from key name] reset count | constant / constant |
| `miscAndSibyl.miscLog.runtimeStats` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.miscLog.runtimeStats.Max_Stack_Used` | 100% / 100% | scalar | int | [inferred from key name] maximum stack used | 0% (237/523) / 10.8% (158/368) |
| `miscAndSibyl.miscLog.runtimeStats.bgnd_task` | 100% / 100% | scalar | int | [inferred from key name] task runtime statistic | 40% (91/523) / constant |
| `miscAndSibyl.miscLog.runtimeStats.d_10ms_task` | 100% / 100% | scalar | int | [inferred from key name] task runtime statistic | 0% (253/523) / 16.2% (176/368) |
| `miscAndSibyl.miscLog.runtimeStats.d_1ms_task` | 100% / 100% | scalar | int | [inferred from key name] task runtime statistic | 0% (173/523) / 13.5% (117/368) |
| `miscAndSibyl.miscLog.shipState` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.miscLog.shipState.AuxPower` | 14% / 100% | scalar | int | unknown (key name only) | 87.5% (1/123) / 94.6% (2/368) |
| `miscAndSibyl.miscLog.shipState.ChargerPresent` | 100% / 100% | scalar | int | unknown (key name only) | 28% (37/523) / 37.8% (39/368) |
| `miscAndSibyl.miscLog.shipState.WakeReqEnabled` | 14% / 100% | scalar | int | unknown (key name only) | 87.5% (1/123) / 94.6% (2/368) |
| `miscAndSibyl.miscLog.temperature` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.miscLog.temperature.highest` | 100% / 100% | scalar | int | [inferred from key name] highest ambient temperature (flat layout labels it 'Highest Ambient Temperature') | 12% (142/523) / 8.1% (185/368) |
| `miscAndSibyl.miscLog.temperature.latest` | 100% / 100% | scalar | int | [inferred from key name] latest ambient temperature (flat layout labels it 'Latest Ambient Temperature') | 8% (149/523) / 10.8% (172/368) |
| `miscAndSibyl.miscLog.timers` | 14% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.miscLog.timers.DisableAuxOnFlat` | 14% / 100% | scalar | int | unknown (key name only) | constant / constant |
| `miscAndSibyl.miscLog.timers.RecAmbientTemp` | 14% / 100% | scalar | int | unknown (key name only) | 12.5% (63/123) / 8.1% (184/368) |
| `miscAndSibyl.sibylData` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.sibylData.dekfSocAlgo` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.sibylData.dekfSocAlgo.Dekf_parameter_Cmax` | 100% / 100% | scalar | float | [inferred from key name] state/parameter of an SoC estimation algorithm (name only); unit unknown | 0% (449/523) / 2.7% (342/368) |
| `miscAndSibyl.sibylData.dekfSocAlgo.Dekf_parameter_G` | 100% / 100% | scalar | float | [inferred from key name] state/parameter of an SoC estimation algorithm (name only); unit unknown | 0% (260/523) / 5.4% (218/368) |
| `miscAndSibyl.sibylData.dekfSocAlgo.Dekf_parameter_alpha1` | 100% / 100% | scalar | float | [inferred from key name] state/parameter of an SoC estimation algorithm (name only); unit unknown | 12% (167/523) / 29.7% (106/368) |
| `miscAndSibyl.sibylData.dekfSocAlgo.Dekf_parameter_alpha2` | 100% / 100% | scalar | float | [inferred from key name] state/parameter of an SoC estimation algorithm (name only); unit unknown | 8% (247/523) / 13.5% (156/368) |
| `miscAndSibyl.sibylData.dekfSocAlgo.Dekf_parameter_chgRs` | 100% / 100% | scalar | float | [inferred from key name] state/parameter of an SoC estimation algorithm (name only); unit unknown | 8% (240/523) / 8.1% (176/368) |
| `miscAndSibyl.sibylData.dekfSocAlgo.Dekf_parameter_disRs` | 100% / 100% | scalar | float | [inferred from key name] state/parameter of an SoC estimation algorithm (name only); unit unknown | 4% (253/523) / 13.5% (188/368) |
| `miscAndSibyl.sibylData.dekfSocAlgo.Dekf_state_SOC` | 100% / 100% | scalar | float | [inferred from key name] state/parameter of an SoC estimation algorithm (name only); unit unknown | 0% (276/523) / 10.8% (176/368) |
| `miscAndSibyl.sibylData.dekfSocAlgo.Dekf_state_Vf1` | 100% / 100% | scalar | float | [inferred from key name] state/parameter of an SoC estimation algorithm (name only); unit unknown | 4% (262/523) / 13.5% (192/368) |
| `miscAndSibyl.sibylData.dekfSocAlgo.Dekf_state_Vf2` | 100% / 100% | scalar | float | [inferred from key name] state/parameter of an SoC estimation algorithm (name only); unit unknown | 4% (273/523) / 10.8% (185/368) |
| `miscAndSibyl.sibylData.initialSoC` | 86% / - | scalar | int | [inferred from key name] initial SoC | 0% (189/400) / - |
| `miscAndSibyl.sibylData.maxCapacity` | 100% / 100% | scalar | int | [inferred from key name] maximum capacity; unit unknown | 0% (448/523) / 2.7% (346/368) |
| `miscAndSibyl.sibylData.runtimeAlgo` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.sibylData.runtimeAlgo.Avg_EOD_imbalance` | 100% / 100% | scalar | int | [inferred from key name] average end-of-discharge imbalance | 76% (16/523) / constant |
| `miscAndSibyl.sibylData.runtimeAlgo.Charge_flag` | 100% / 100% | scalar | int | [inferred from key name] flag | 76% (9/523) / 78.4% (10/368) |
| `miscAndSibyl.sibylData.runtimeAlgo.Discharge_flag` | 100% / 100% | scalar | int | [inferred from key name] flag | 76% (7/523) / 83.8% (6/368) |
| `miscAndSibyl.sibylData.runtimeAlgo.High_Power_Resistance` | 100% / 100% | scalar | int | [inferred from key name] resistance estimate (brief lists 'battery resistance estimates'); unit unknown | 96% (6/523) / 94.6% (2/368) |
| `miscAndSibyl.sibylData.runtimeAlgo.Initialized_flag` | 100% / 100% | scalar | int | [inferred from key name] flag | constant / constant |
| `miscAndSibyl.sibylData.runtimeAlgo.Low_Power_Resistance` | 100% / 100% | scalar | int | [inferred from key name] resistance estimate (brief lists 'battery resistance estimates'); unit unknown | 96% (1/523) / 91.9% (5/368) |
| `miscAndSibyl.sibylData.runtimeAlgo.Medium_Power_Resistance` | 100% / 100% | scalar | int | [inferred from key name] resistance estimate (brief lists 'battery resistance estimates'); unit unknown | 88% (4/523) / 75.7% (19/368) |
| `miscAndSibyl.sibylData.runtimeAlgo.Min_Power_Resistance` | 14% / 100% | scalar | int | [inferred from key name] resistance estimate (brief lists 'battery resistance estimates'); unit unknown | constant / constant |
| `miscAndSibyl.sibylData.runtimeAlgo.Peak_Power_Resistance` | 14% / 100% | scalar | int | [inferred from key name] resistance estimate (brief lists 'battery resistance estimates'); unit unknown | constant / constant |
| `miscAndSibyl.sibylData.sohData` | 100% / 100% | object | dict | container | n/a / n/a |
| `miscAndSibyl.sibylData.sohData.Delta_Energy` | 86% / - | scalar | int | unknown (key name only) | 0% (197/400) / - |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_Age_High` | 100% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | 100% (0/523) / 100% (0/368) |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_Age_Low` | 100% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | 64% (16/523) / 100% (0/368) |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_Age_Med` | 100% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | 68% (16/523) / 100% (0/368) |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_Age_Min` | 14% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | 100% (0/123) / 100% (0/368) |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_Age_Peak` | 14% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | constant / constant |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_High` | 100% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | 100% (0/523) / 97.3% (1/368) |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_Low` | 100% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | 44% (56/523) / 48.6% (68/368) |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_Med` | 100% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | 20% (122/523) / 51.4% (53/368) |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_Min` | 14% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | 100% (0/123) / 100% (0/368) |
| `miscAndSibyl.sibylData.sohData.SoH_Rs_Peak` | 14% / 100% | scalar | int | [inferred from key name] SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates) | constant / constant |
| `usage` | 100% / 100% | object | dict | container | n/a / n/a |
| `usage.chargeLog` | 100% / 100% | object | dict | container | n/a / n/a |
| `usage.chargeLog.chargeActiveTime` | 100% / 100% | scalar | int | [inferred from key name] time in active charge phase; unit unknown | 60% (21/523) / 100% (0/368) |
| `usage.chargeLog.chargeMaintainCount` | 100% / 100% | scalar | int | [inferred from key name] count of maintenance-phase charges | 56% (26/523) / 100% (0/368) |
| `usage.chargeLog.chargeStopEvents` | 100% / 100% | object | dict | container | n/a / n/a |
| `usage.chargeLog.chargeStopEvents.chargerRemoved` | 100% / 100% | scalar | int | [inferred from key name] count of charger removals | 64% (18/523) / 100% (0/368) |
| `usage.chargeLog.chargeStopEvents.chargingForLong` | 100% / 100% | scalar | int | [inferred from key name] count of charge stops, charging too long | constant / constant |
| `usage.chargeLog.chargeStopEvents.otherFault` | 100% / 100% | scalar | int | [inferred from key name] count of charge stops, other fault | 56% (26/523) / 100% (0/368) |
| `usage.chargeLog.chargeStopEvents.overCurrent` | 100% / 100% | scalar | int | [inferred from key name] count of charge stops, over current | constant / constant |
| `usage.chargeLog.chargeStopEvents.overTemp` | 100% / 100% | scalar | int | [inferred from key name] count of stops, over temperature | 100% (0/523) / constant |
| `usage.chargeLog.chargeStopEvents.underTemp` | 100% / 100% | scalar | int | [inferred from key name] count of charge stops, under temperature | 100% (0/523) / 100% (0/368) |
| `usage.chargeLog.chargerInsertions` | 100% / 100% | object | dict | container | n/a / n/a |
| `usage.chargeLog.chargerInsertions.allTime` | 100% / 100% | scalar | int | [inferred from key name] all-time count | 56% (26/523) / 100% (0/368) |
| `usage.chargeLog.chargerInsertions.whenFrozen` | 100% / 100% | scalar | int | [inferred from key name] count when stats were frozen | 56% (26/523) / 100% (0/368) |
| `usage.chargeLog.everFullyCharged` | 100% / 100% | scalar | int | [inferred from key name] flag, ever fully charged | 96% (1/523) / 100% (0/368) |
| `usage.chargeLog.imbalanceAtEnd` | 100% / 100% | object | dict | container | n/a / n/a |
| `usage.chargeLog.imbalanceAtEnd.Initial` | 100% / 100% | scalar | int | [inferred from key name] initial value of imbalance at end of charge | 96% (1/523) / 100% (0/368) |
| `usage.chargeLog.imbalanceAtEnd.Latest` | 100% / 100% | scalar | int | [inferred from key name] latest value of imbalance at end of charge | 4% (171/523) / 13.5% (174/368) |
| `usage.checksum` | 86% / - | scalar | int | [inferred from key name] record checksum (not a measurement) | 0% (361/400) / - |
| `usage.counter` | 86% / - | scalar | int | [inferred from key name] record counter | 47.1% (25/400) / - |
| `usage.dischargeLog` | 100% / 100% | object | dict | container | n/a / n/a |
| `usage.dischargeLog.dischargeInhibitEvents` | 100% / 100% | object | dict | container | n/a / n/a |
| `usage.dischargeLog.dischargeInhibitEvents.other` | 100% / 100% | scalar | int | [inferred from key name] count of start inhibits, other reason | 56% (24/523) / 100% (0/368) |
| `usage.dischargeLog.dischargeInhibitEvents.packFlat` | 100% / 100% | scalar | int | [inferred from key name] count of start inhibits, pack flat | 100% (0/523) / 100% (0/368) |
| `usage.dischargeLog.dischargeSecsSinceLastCharge` | 100% / 100% | scalar | int | [inferred from key name] seconds of discharge since last charge | 40% (56/523) / 32.4% (67/368) |
| `usage.dischargeLog.dischargeStopEvents` | 100% / 100% | object | dict | container | n/a / n/a |
| `usage.dischargeLog.dischargeStopEvents.lowVolt` | 100% / 100% | scalar | int | [inferred from key name] count of discharge stops, low voltage | 92% (2/523) / 100% (0/368) |
| `usage.dischargeLog.dischargeStopEvents.noLoad` | 100% / 100% | scalar | int | [inferred from key name] count of discharge stops, no load | 96% (1/523) / 100% (0/368) |
| `usage.dischargeLog.dischargeStopEvents.overTemp` | 100% / 100% | scalar | int | [inferred from key name] count of stops, over temperature | 100% (0/523) / constant |
| `usage.dischargeLog.oneSecDischarge` | 100% / 100% | scalar | int | [inferred from key name] count of one-second discharges | 80% (7/523) / 100% (0/368) |
| `usage.dischargeLog.sigDischarges` | 100% / 100% | object | dict | container | n/a / n/a |
| `usage.dischargeLog.sigDischarges.allTime` | 100% / 100% | scalar | int | [inferred from key name] all-time count | 56% (22/523) / 100% (0/368) |
| `usage.dischargeLog.sigDischarges.whenFrozen` | 100% / 100% | scalar | int | [inferred from key name] count when stats were frozen | 56% (22/523) / 100% (0/368) |

### 3.2 Bin arrays

| Array path | % payloads (N / RR) | Definition | Match status | Length vs declared | Bin edges (as declared) | Declared unit (array) | All-zero rows (N / RR) | Monotonic % serials (N / RR) |
|---|---|---|---|---|---|---|---|---|
| `usage.chargeLog.chargeAmbientTempCustomerBins` | 100% / 100% | `chargeAmbientTempCustomerBins` | [verified] exact name, length matches | 6 vs 6 | ambient temp [celsius]: 15, 20, 25, 30, 40 | count | 6% / 6% | 56% (27/523) / 100% (0/368) |
| `usage.chargeLog.chargeAmbientTempPreCustomerBins` | 100% / 100% | `chargeAmbientTempPreCustomerBins` | [verified] exact name, length matches | 6 vs 6 | ambient temp [celsius]: 20, 25, 30, 40, 50 | count | 0% / 0% | 92% (2/523) / 100% (0/368) |
| `usage.chargeLog.chargeBandBins` | 100% / 100% | `chargeBandBins` | [verified] exact name, length matches | 9 vs 9 (sizes [3, 3]) | voltage [volt]: 3.3, 4.15; temperature [celsius]: 15, 45 | second | 3% / 0% | 56% (26/523) / 100% (0/368) |
| `usage.chargeLog.chargeDurationBins` | 100% / 100% | `chargeDurationBins` | [verified] exact name, length matches | 16 vs 16 | duration [minute]: 5, 10, 15, 30, 45, 60, 75, 90, 105, 120, 150, 180, 210, 240, 270 | count | 6% / 6% | 60% (21/523) / 100% (0/368) |
| `usage.chargeLog.chargeMaintainTempBins` | 100% / 100% | `chargeMaintainTempBins` | [verified] exact name, length matches | 6 vs 6 | charge maintain temp [celsius]: 20, 25, 30, 35, 40 | second | 6% / 6% | 56% (26/523) / 100% (0/368) |
| `usage.chargeLog.minCellVoltAtChargeStartBins` | 100% / 100% | `minCellVoltAtChargeStartBins` | [verified] exact name, length matches | 16 vs 16 | min cell voltage [volt]: 2.6, 2.7, 2.8, 2.9, 3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0 | count | 3% / 0% | 56% (26/523) / 100% (0/368) |
| `usage.dischargeLog.dischargeBandBins` | 100% / 100% | `dischargeBandBins` | [verified] exact name, length matches | 9 vs 9 (sizes [3, 3]) | voltage [volt]: 3.3, 4.0; temperature [celsius]: 15, 45 | second | 0% / 0% | 56% (22/523) / 100% (0/368) |
| `usage.dischargeLog.dischargeBtwChargesBins` | 100% / 100% | `dischargeBtwChargesBins` | [verified] exact name, length matches | 15 vs 15 | off time [minute]: 1, 2, 4, 6, 8, 10, 15, 20, 25, 30, 35, 40, 50, 60 | count | 3% / 0% | 56% (22/523) / 100% (0/368) |
| `usage.dischargeLog.dischargeDurationBins` | 100% / 100% | `dischargeDurationBins` | [verified] exact name, length matches | 23 vs 23 | duration [second]: 5, 10, 15, 20, 25, 30, 45, 60, 75, 90, 105, 120, 180, 240, 300, 360, 600, 900, 1200, 1800, 2400, 3000 | second | 0% / 0% | 56% (22/523) / 100% (0/368) |
| `usage.dischargeLog.dischargeOffTimeBins` | 100% / 100% | `dischargeOffTimeBins` | [verified] exact name, length matches | 6 vs 6 | off time [second]: 5, 20, 60, 300, 1800 | count | 0% / 0% | 56% (22/523) / 100% (0/368) |
| `usage.dischargeLog.dischargeStartTempBins` | 100% / 100% | `dischargeStartTempBins` | [verified] exact name, length matches | 10 vs 10 | start temperature [celsius]: 5, 10, 15, 20, 25, 30, 35, 45, 60 | count | 0% / 0% | 56% (22/523) / 100% (0/368) |
| `usage.dischargeLog.powerBins` | 100% / 100% | `powerBins` | [verified] exact name, length matches | 3 vs 3 | power [watt]: 95, 250 | second | 0% / 0% | 56% (22/523) / 100% (0/368) |

Notes:

- **[verified]** All 12 arrays match `BMS_Bins.json` by exact name, location (`usage.dischargeLog` / `usage.chargeLog`) and length, in both cohorts.
- **[verified]** Edge counts equal length − 1 for every array.
- **[inferred]** Two-dimensional arrays (`dischargeBandBins`, `chargeBandBins`, 3×3 = 9 values) are flattened to 9 values and the JSON does not say in which order. The label-based layouts list voltage first and temperature second (3.3 V bands vary slowest), consistent with row-major order over [voltage, temperature]; this is unconfirmed.
- Units: the bin JSON declares the edge unit (e.g. watt, celsius, minute) and an array-level unit (`second` or `count`). `count` is used for several arrays that hold time-like bins (e.g. `dischargeOffTimeBins`); what each cell counts is not stated beyond that.

## 4. Battery payload, label-based layouts (return/repair only)

These two layouts carry the same information as the standard layout, but bins are identified by text labels instead of position. They are small (26 and 13 rows; 3 serials in total) and are **not** recommended for Step 3 (see section 8).

### 4.1 Labelled layout (26 payloads, 1 serial)

Same top-level keys as standard (`header`, `eventLog`, `usage`, `miscAndSibyl`). Each `usage` section is a dict of label → count. The table compares the number of labels with the declared cells of the matching definition (matched by section name, **[inferred]**).

| Section | % labelled payloads | Labels | Candidate definition (inferred by section name) | Labels vs declared cells | First labels |
|---|---|---|---|---|---|
| `usage.chargeLog.chargeAmbientTemperatureForCustomers` | 100% | 6 | `chargeAmbientTempCustomerBins` | 6 vs 6 | c_lt_15C; c_15_20C; c_20_25C |
| `usage.chargeLog.chargeAmbientTemperatureForPreCustomers` | 100% | 6 | `chargeAmbientTempPreCustomerBins` | 6 vs 6 | c_lt_20C; c_20_25C; c_25_30C |
| `usage.chargeLog.chargeDurationBins` | 100% | 17 | `chargeDurationBins` | 17 vs 16  **MISMATCH** | c_0m; c_0_5m; c_5_10m |
| `usage.chargeLog.chargeOperatingBands` | 100% | 9 | `chargeBandBins` | 9 vs 9 | cV_<3.3V_lt_15C; cV_lt_3.3V_15_45C; cV_lt_3.3V_gt_45C |
| `usage.chargeLog.chargeTimeWhileInDifferentPhases` | 100% | 7 | `chargeMaintainTempBins` | 6 vs 6 | maint_lt_20C; maint_20_25C; maint_25_30C |
| `usage.chargeLog.chargerInsertions` | 100% | 2 | - | - | All_time; When_frozen |
| `usage.chargeLog.imbalanceAtEnd` | 100% | 2 | - | - | Initial; Latest |
| `usage.chargeLog.lowestCellVoltageAtStart` | 100% | 16 | `minCellVoltAtChargeStartBins` | 16 vs 16 | c_le_2.6V; c_le_2.7V; c_le_2.8V |
| `usage.chargeLog.otherChargeStatistics` | 100% | 6 | - | - | Charge_stop_due_to_over_temperature; Charge_stop_due_to_under_temperature; Charge_stop_due_to_fault |
| `usage.dischargeLog.durationBetweenChargesBins` | 100% | 15 | `dischargeBtwChargesBins` | 15 vs 15 | d_lt_1m; d_1_2m; d_2_4m |
| `usage.dischargeLog.durationBins` | 100% | 24 | `dischargeDurationBins` | 24 vs 23  **MISMATCH** | d_lt_1s; d_1_5s; d_5_10s |
| `usage.dischargeLog.offTimeBins` | 100% | 6 | `dischargeOffTimeBins` | 6 vs 6 | d_lt_5s; d_5_20s; d_20_60s |
| `usage.dischargeLog.operatingBands` | 100% | 9 | `dischargeBandBins` | 9 vs 9 | cellV_lt_3v3_lt_15C; cellV_lt_3v3_15C_45C; cellV_lt_3v3_gt_45C |
| `usage.dischargeLog.otherEvents` | 100% | 6 | - | - | Discharge_stop_due_to_no_load_detected; Discharge_stop_due_to_over_temperature; Discharge_stop_due_to_low_voltage |
| `usage.dischargeLog.powerBins` | 100% | 3 | `powerBins` | 3 vs 3 | Low_power; Mid_power; High_power |
| `usage.dischargeLog.sigDischarges` | 100% | 2 | - | - | allTime; whenFrozen |
| `usage.dischargeLog.startTempBins` | 100% | 10 | `dischargeStartTempBins` | 10 vs 10 | d_0_5C; d_5_10C; d_10_15C |

### 4.2 Flat layout (13 payloads, 2 serials)

All 748 keys are slash paths, such as `/USAGE_LOG/Discharge/Discharge power bins/Low power`, with string values. Event keys repeat per event (`event0`..`event14`, `fault0`..`fault1`) and per cell (`cell0`..`cell6`), collapsed to `eventN`/`faultN`/`cellN` below. Individual keys are in `reports/profiling/parsing_spec_paths.csv` and `parsing_spec_flat_sections.csv`.

| Section (collapsed: eventN/faultN/cellN) | Keys | % flat payloads | Value types | Candidate definition (inferred by section title) | Labels vs declared cells | First labels |
|---|---|---|---|---|---|---|
| `/HEADER` | 10 | 100% | str | - | - | /HEADER/BPA; /HEADER/CONFIGID; /HEADER/HARDWARE_SERIAL |
| `/EVENT_LOGS/eventN/data` | 8 | 100% | str | - | - | /EVENT_LOGS/eventN/data/chargeReason; /EVENT_LOGS/eventN/data/dischgReason; /EVENT_LOGS/eventN/data/lockout |
| `/EVENT_LOGS/eventN/data/inputs` | 7 | 100% | str | - | - | /EVENT_LOGS/eventN/data/inputs/charger; /EVENT_LOGS/eventN/data/inputs/chgFet; /EVENT_LOGS/eventN/data/inputs/extTrig |
| `/EVENT_LOGS/eventN/volt` | 2 | 100% | str | - | - | /EVENT_LOGS/eventN/volt/cellN; /EVENT_LOGS/eventN/volt/pack |
| `/EVENT_LOGS/eventN/current` | 2 | 100% | str | - | - | /EVENT_LOGS/eventN/current/pack_current; /EVENT_LOGS/eventN/current/padding |
| `/EVENT_LOGS/eventN` | 2 | 100% | str | - | - | /EVENT_LOGS/eventN/padding; /EVENT_LOGS/eventN/temperature |
| `/EVENT_LOGS/eventN/capacity` | 4 | 100% | str | - | - | /EVENT_LOGS/eventN/capacity/fuelGauge; /EVENT_LOGS/eventN/capacity/runtime; /EVENT_LOGS/eventN/capacity/soc |
| `/EVENT_LOGS/faultN/data` | 8 | 100% | str | - | - | /EVENT_LOGS/faultN/data/chargeReason; /EVENT_LOGS/faultN/data/dischgReason; /EVENT_LOGS/faultN/data/lockout |
| `/EVENT_LOGS/faultN/data/inputs` | 7 | 100% | str | - | - | /EVENT_LOGS/faultN/data/inputs/charger; /EVENT_LOGS/faultN/data/inputs/chgFet; /EVENT_LOGS/faultN/data/inputs/extTrig |
| `/EVENT_LOGS/faultN/volt` | 2 | 100% | str | - | - | /EVENT_LOGS/faultN/volt/cellN; /EVENT_LOGS/faultN/volt/pack |
| `/EVENT_LOGS/faultN/current` | 2 | 100% | str | - | - | /EVENT_LOGS/faultN/current/pack_current; /EVENT_LOGS/faultN/current/padding |
| `/EVENT_LOGS/faultN` | 2 | 100% | str | - | - | /EVENT_LOGS/faultN/padding; /EVENT_LOGS/faultN/temperature |
| `/EVENT_LOGS/faultN/capacity` | 4 | 100% | str | - | - | /EVENT_LOGS/faultN/capacity/fuelGauge; /EVENT_LOGS/faultN/capacity/runtime; /EVENT_LOGS/faultN/capacity/soc |
| `/EVENT_LOGS` | 2 | 100% | str | - | - | /EVENT_LOGS/eventIndex; /EVENT_LOGS/faultIndex |
| `/USAGE_LOG/Discharge/Significant discharges` | 2 | 100% | str | - | - | All time; When frozen |
| `/USAGE_LOG/Discharge/Discharge power bins` | 3 | 100% | str | `powerBins` | 3 vs 3 | Low power; Mid power; High power |
| `/USAGE_LOG/Discharge/Discharge operating bands` | 9 | 100% | str | `dischargeBandBins` | 9 vs 9 | cell voltage <3.3V, Temp <15 degC; cell voltage <3.3V, Temp 15-45 degC; cell voltage <3.3V, Temp >45 degC |
| `/USAGE_LOG/Discharge/Discharge duration bins` | 24 | 100% | str | `dischargeDurationBins` | 24 vs 23  **MISMATCH** | <1 second; 1-5 seconds; 5-10 seconds |
| `/USAGE_LOG/Discharge/Discharge start temperature bins` | 10 | 100% | str | `dischargeStartTempBins` | 10 vs 10 | 0-5 degC; 5-10 degC; 10-15 degC |
| `/USAGE_LOG/Discharge/Discharge off time bins` | 6 | 100% | str | `dischargeOffTimeBins` | 6 vs 6 | <5 secs; 5-20 secs; 20-60 secs |
| `/USAGE_LOG/Discharge/Discharge duration between charges bins` | 15 | 100% | str | `dischargeBtwChargesBins` | 15 vs 15 | <1 minute; 1-2 minutes; 2-4 minutes |
| `/USAGE_LOG/Discharge/Other events` | 6 | 100% | str | - | - | Discharge stop due to no load detected; Discharge stop due to over temperature; Discharge stop due to low voltage |
| `/USAGE_LOG/Charge/Charger insertions` | 2 | 100% | str | - | - | All time; When frozen |
| `/USAGE_LOG/Charge/Imbalance at end of charge` | 2 | 100% | str | - | - | Initial; Latest |
| `/USAGE_LOG/Charge/Charge time while in different phases (in seconds)` | 7 | 100% | str | `chargeMaintainTempBins` | 6 vs 6 | Maintenance phase, Temp <20 degC; Maintenance phase, Temp 20 - 25 degC; Maintenance phase, Temp 25 - 30 degC |
| `/USAGE_LOG/Charge/Charge operating bands (total time in seconds)` | 9 | 100% | str | `chargeBandBins` | 9 vs 9 | cell voltage <3.3V, Temp <15 degC; cell voltage <3.3V, Temp 15-45 degC; cell voltage <3.3V, Temp >45 degC |
| `/USAGE_LOG/Charge/Charge duration bins` | 17 | 100% | str | `chargeDurationBins` | 17 vs 16  **MISMATCH** | 0 mins; 0-5 mins; 5-10 mins |
| `/USAGE_LOG/Charge/Charge ambient temperature for pre-customers` | 6 | 100% | str | `chargeAmbientTempPreCustomerBins` | 6 vs 6 | <20 degC; 20-25 degC; 25-30 degC |
| `/USAGE_LOG/Charge/Charge ambient temperature for customers` | 6 | 100% | str | `chargeAmbientTempCustomerBins` | 6 vs 6 | <15 degC; 15-20 degC; 20-25 degC |
| `/USAGE_LOG/Charge/Other statistics` | 6 | 100% | str | - | - | Charge stop due to over temperature; Charge stop due to under temperature; Charge stop due to fault |
| `/USAGE_LOG/Charge/Lowest cell voltage at start of charge` | 18 | 100% | str | `minCellVoltAtChargeStartBins` | 16 vs 16 | <=2.6V; <=2.7V; <=2.8V |
| `/USAGE_LOG/Misc/Misc Flags` | 5 | 100% | str | - | - | Pack Flat; Stats Frozen; Main Body Fault |
| `/USAGE_LOG/Misc/Temperature` | 3 | 100% | str | - | - | Latest Ambient Temperature; Highest Ambient Temperature; padding1 |
| `/USAGE_LOG/Misc/Runtime` | 3 | 100% | str | - | - | 1ms Runtime; 10ms Runtime; Background Runtime |
| `/USAGE_LOG/Misc/Stack` | 1 | 100% | str | - | - | Max Stack Used |
| `/USAGE_LOG/Misc/Resets` | 10 | 100% | str | - | - | padding1; Brown Out 12 Resets; Brown Out 33 Resets |
| `/USAGE_LOG/Misc/State` | 9 | 100% | str | - | - | Auxiliary Power; Charger Present; DIPC Wake Alert Request Enable |
| `/USAGE_LOG/Capacity/Capacity` | 30 | 100% | str | - | - | Avg EOD imbalance; Min Power Resistance; Low Power Resistance |

Findings for both label-based layouts:

- **[verified]** In both, `Discharge duration bins` has 24 labels against 23 declared cells and `Charge duration bins` has 17 against 16. In each, the label list has two bins below the first JSON edge (`<1 s`, `1-5 s` against JSON `<5`; `0 mins`, `0-5 mins` against JSON `<5`). All other bin sections match the declared cell count.
- **[verified]** `Lowest cell voltage at start of charge` has 16 bin labels, `<=2.6V` to `<=4.1V`, against 16 declared cells, but the JSON's top edge is 4.0 V. The last label (`<=4.1V`) does not correspond to a JSON edge. Meaning of the difference is unknown.
- These layouts give text labels for the same quantities as the standard layout (for example `Significant discharges` ↔ `sigDischarges`), but the correspondence is by name only (**[inferred from key name]**). The flat layout also gives text for event codes (for example `state_phase` = `Ship`, `reason` = `Timeout`), which could name the numeric codes of the standard layout, but the records cannot be paired to confirm it.

## 5. Cumulative-counter check (read-only)

The brief says motor and battery counters are cumulative lifetime values captured weekly. `src/cumulative_check.py` tests this. For each numeric scalar and each numeric bin array, observations are ordered per serial by `hdr_timestamp` and consecutive values are compared. "Monotonic" means non-decreasing across all consecutive pairs of a serial; a serial needs ≥ 2 observations. Details of the method:

- Rows with the same serial, `hdr_timestamp` and identical payload text are counted once. This is **only for ordering**; it is not the Step 4 duplicate rule. No tied `hdr_timestamp` with different payloads exists in any group.
- For bin arrays, "monotonic" means every cell is non-decreasing. `cumulative_check.csv` also reports a looser test on the array total.
- Event-record lists (`eventLog.events[]`, `eventLog.faults[]`) are snapshots and are excluded. The 26 labelled and 13 flat payloads are excluded as too small to judge.
- A second ordering by `server_timestamp` is included to separate device-clock ordering effects from other causes.
- Nothing in the data is modified.

Summary by group:

| Group | Numeric paths checked | Constant in all rows | Non-constant, 100% serials monotonic | Non-constant, <100% monotonic | Bin arrays: median % serials monotonic |
|---|---|---|---|---|---|
| motor_normal | 42 | 22 | 9 | 11 | 100% |
| motor_rr | 42 | 22 | 9 | 11 | 100% |
| battery_normal | 102 | 22 | 10 | 70 | 56% |
| battery_rr_standard | 94 | 26 | 37 | 31 | 100% |
| battery_normal_4cell | 86 | 16 | 8 | 62 | 41.2% |
| battery_normal_7cell | 94 | 28 | 10 | 56 | 87.5% |

Selected fields (% of serials monotonic; in brackets: consecutive pairs that decrease / all consecutive pairs):

| Path | motor_normal | motor_rr | battery_normal_4cell | battery_normal_7cell | battery_rr_standard |
|---|---|---|---|---|---|
| `header.writeCount` | 100% (0/394) | 100% (0/448) | - | - | - |
| `ddmUsage.ddm692_SpeedBins.bins` | 100% (0/394) | 100% (0/448) | - | - | - |
| `ddmUsage.ddm692_PowerBins.bins` | 100% (0/394) | 100% (0/448) | - | - | - |
| `ddmUsage.ddm692_ExhaustTempBins.bins` | 100% (0/394) | 100% (0/448) | - | - | - |
| `ddmUsage.ddmOnButNotRunTime_s` | 100% (0/394) | 100% (0/448) | - | - | - |
| `ddmUsage.filterWashCounter` | 100% (0/394) | 100% (0/448) | - | - | - |
| `usage.dischargeLog.sigDischarges.allTime` | - | - | 41.2% (21/400) | 87.5% (1/123) | 100% (0/368) |
| `usage.chargeLog.chargerInsertions.allTime` | - | - | 41.2% (25/400) | 87.5% (1/123) | 100% (0/368) |
| `usage.dischargeLog.powerBins` | - | - | 41.2% (21/400) | 87.5% (1/123) | 100% (0/368) |
| `usage.dischargeLog.dischargeDurationBins` | - | - | 41.2% (21/400) | 87.5% (1/123) | 100% (0/368) |
| `usage.chargeLog.chargeDurationBins` | - | - | 47.1% (20/400) | 87.5% (1/123) | 100% (0/368) |
| `header.power_ups` | - | - | - | 87.5% (1/123) | 100% (0/368) |

Spacing of observations per serial:

| group | payload_rows | rows_after_identical_payload_dedup | serials | serials_ge2_obs | median_obs_per_serial | gap_days_p10 | gap_days_median | gap_days_p90 | pct_gaps_6_to_8_days |
|---|---|---|---|---|---|---|---|---|---|
| motor_normal | 470 | 470 | 76 | 54 | 6.0 | 7.57 | 21.97 | 63.86 | 15.2 |
| motor_rr | 564 | 492 | 44 | 37 | 8.0 | 7.01 | 7.51 | 9.87 | 70.1 |
| battery_normal | 1250 | 551 | 28 | 25 | 21.5 | 6.91 | 7.02 | 11.41 | 75.1 |
| battery_rr_standard | 542 | 410 | 42 | 37 | 6.5 | 7.06 | 7.89 | 15.77 | 53.5 |
| battery_normal_4cell | 1077 | 418 | 18 | 17 | 24.5 | 6.25 | 7.01 | 7.43 | 82.8 |
| battery_normal_7cell | 173 | 133 | 10 | 8 | 11.5 | 7.03 | 7.96 | 18.81 | 50.4 |

What this shows:

- **[verified] Motor bin arrays behave as cumulative counters.** `ddm692_SpeedBins`, `PowerBins`, `ExhaustTempBins`, `PressureBins`, `BarometerTempBins`, `FisfTempBins`, `header.writeCount`, `ddmOnButNotRunTime_s` and `filterWashCounter` are non-decreasing for 100% of serials in both cohorts, with zero decreases. Ordering by `server_timestamp` instead introduces decreases (89–94% monotonic), so `hdr_timestamp` is the right order for motor.
- **[verified] Battery return/repair standard behaves the same** (100% monotonic by `hdr_timestamp`; 0 decreases in 368 pairs).
- **[verified] Battery Normal does not, mainly the 4-cell variant.** Usage arrays and `sigDischarges`/`chargerInsertions` counters are monotonic for only 41–47% of 4-cell serials (about 20–25 decreasing pairs in 400) against 87.5% for 7-cell serials (1 decrease in 123). Some 4-cell decreases are large (for example a bin total falling 97,831 → 48,039), which is **consistent with** a counter reset or a rolling window, but the cause is not established. Some decreases are ordering effects: two records hours apart appear in the wrong order by device clock, and for the Normal battery as a whole, ordering by `server_timestamp` instead of `hdr_timestamp` raises the share of monotonic serials (for example `sigDischarges.allTime`) from 56% to 72%.
- **[verified] Many scalars are not counters**: `ambientPressure_Pa`, `ambientTemperature_mC`, `bmsAmbientTemperature_mC`, `fwFilteredDeqv_mm`, `header.checksum`, `ppcPeakPowerTimeReset_ms`, `powerReset`, the battery `Dekf_*`, `SoH_Rs_*`, `runtimeStats`, `eventLog.eventIndex` and similar are mostly non-monotonic, and 16–28 fields per group are constant in every row. Delta logic should apply only to the counter set chosen in section 7.
- **[verified] Observation spacing is not uniformly weekly.** Motor RR, battery Normal and battery RR have median gaps of 7.0–7.9 days, but with a long tail (RR battery p90 = 15.8 days; 7-cell Normal p90 = 18.8 days). **Motor Normal has a median gap of 22 days and p90 of 64 days; only 15% of its gaps are 6–8 days.** Per-period deltas are therefore not per-week deltas and need the elapsed days alongside them.
- **[verified]** `hdr_timestamp` is unreliable in places: the 7-cell Normal battery contains values up to 2055-09-07.

Implications for Step 5 delta logic (design notes, not decisions):

1. De-duplicate re-uploads before differencing (Step 4), or deltas will be zero-length intervals.
2. Order by `hdr_timestamp`; for each serial and counter compute delta = current − previous and elapsed days = difference in `hdr_timestamp`.
3. A negative delta cannot be a negative amount of usage. The rule for negatives (treat as reset and keep the current value as the delta, or drop the interval, or set missing) must be chosen and logged; the cause of decreases is currently unknown.
4. The first observation of a serial has no delta; the delta from install to first observation is unknown.
5. Report the share of intervals that are negative per group so the choice is visible.

## 6. Bin definitions: metadata errors and unused definitions

All 31 definitions (19 motor, 12 battery). "Used by payloads" is by name; "via inferred alias" refers to the inferred names in section 2.

| Definition | File | Declared size | Declared unit | Used by payloads | Metadata issues |
|---|---|---|---|---|---|
| `powerOnModeBins` | DDM_Bins.json | [3] | count | NO | - |
| `longestOperatingDurationBins` | DDM_Bins.json | [3, 3] | second | NO | - |
| `ddm683_UsageDurationBins` | DDM_Bins.json | [3, 3, 6] | count | NO | size 6 but 5 enum labels |
| `ddm683_UsageBins` | DDM_Bins.json | [3, 3] | second | NO | - |
| `ddm683_pwrOnFwiCountBins` | DDM_Bins.json | [2, 3] | count | NO | - |
| `ddm683_usageFwiStateBins` | DDM_Bins.json | [2, 3] | second | NO | - |
| `ddm683_SpeedBins` | DDM_Bins.json | [24] | count | NO | - |
| `ddm683_AmbPressBins` | DDM_Bins.json | [7] | count | NO | size 7 but 7 edges (+1 = 8) |
| `ddm683_AmbTempBins` | DDM_Bins.json | [7] | count | NO | - |
| `ddm683_ExhaustTempBins` | DDM_Bins.json | [7] | count | NO | - |
| `ddm683_normDPressOnFwiOffBins` | DDM_Bins.json | [25] | count | NO | - |
| `ddm692_SpeedBins` | DDM_Bins.json | [25] | second | yes, exact | - |
| `ddm692_PressBins` | DDM_Bins.json | [9] | second | yes, via inferred alias `ddm692_PressureBins` | dimension named 'speed' but unit is kilo-pascal |
| `ddm692_BarTempBins` | DDM_Bins.json | [10] | second | yes, via inferred alias `ddm692_BarometerTempBins` | temperature array with unit krpm (likely copy error; correct unit not stated) |
| `ddm692_FisfTempBins` | DDM_Bins.json | [10] | second | yes, exact | dimension named 'speed' but unit is celsius |
| `ddm692_PowerBins` | DDM_Bins.json | [14] | second | yes, exact | dimension named 'speed' but unit is watts |
| `ddm692_NormSpeedBins` | DDM_Bins.json | [14] | second | yes, exact | - |
| `ddm692_ExhaustTempBins` | DDM_Bins.json | [10] | second | yes, exact | dimension named 'speed' but unit is celsius |
| `ddm590_SpeedBins` | DDM_Bins.json | [24] | second | NO | - |
| `powerBins` | BMS_Bins.json | [3] | second | yes, exact | - |
| `dischargeBandBins` | BMS_Bins.json | [3, 3] | second | yes, exact | - |
| `dischargeDurationBins` | BMS_Bins.json | [23] | second | yes, exact | - |
| `dischargeStartTempBins` | BMS_Bins.json | [10] | count | yes, exact | - |
| `dischargeOffTimeBins` | BMS_Bins.json | [6] | count | yes, exact | - |
| `dischargeBtwChargesBins` | BMS_Bins.json | [15] | count | yes, exact | bin dimension named 'off time' although the array is 'between charges' |
| `chargeMaintainTempBins` | BMS_Bins.json | [6] | second | yes, exact | - |
| `chargeBandBins` | BMS_Bins.json | [3, 3] | second | yes, exact | - |
| `chargeDurationBins` | BMS_Bins.json | [16] | count | yes, exact | - |
| `chargeAmbientTempPreCustomerBins` | BMS_Bins.json | [6] | count | yes, exact | - |
| `chargeAmbientTempCustomerBins` | BMS_Bins.json | [6] | count | yes, exact | - |
| `minCellVoltAtChargeStartBins` | BMS_Bins.json | [16] | count | yes, exact | - |

Additional points:

- **[verified]** `ddm683_*` and `ddm590_SpeedBins` definitions, `powerOnModeBins` and `longestOperatingDurationBins` have no matching key in any payload. Only the `ddm692_*` format is present.
- **[verified]** New in this step: `ddm683_AmbPressBins` declares size 7 but has 7 edges, where 6 edges would give 7 bins (it is unused in the data, so no effect now).
- **[verified]** In both label-based layouts the duration bins have one more low bin than the JSON (section 4).
- **[inferred]** `ddm692_BarTempBins` unit `krpm` is probably a copy error (it is a temperature array). The correct unit is not stated, so it is treated as unknown rather than °C.
- Several `ddm692_*` dimensions are named "speed" although their units are kPa, °C or W. The unit, not the name, is used.

## 7. Recommended fields to parse in Step 3 (recommendations)

These are recommendations for your decision, not decisions. "Risk" is the exposure if the meaning is only inferred. All parsed fields go through one mapping module so a changed meaning (for example when the EEPROM document arrives) is fixed in one place.

| # | Insight area | Fields | Why | Risk if meaning is only inferred |
|---|---|---|---|---|
| R1 | Usage (motor) | `ddm692_SpeedBins`, `ddm692_PowerBins` (25 and 14 cells, as per-bin cumulative seconds) | Brief lists speed and power distributions; names, edges, length and unit are verified against `DDM_Bins.json`; both are clean counters | Low. Edges are corroborated by the Normal column names; time base differs between arrays (section 2) |
| R2 | Usage (motor) | `sum(PowerBins)` as total cumulative runtime | Reproduces Normal `cumulative_usage_duration_seconds` exactly (100% of rows) and gives RR the same measure; the brief lists "cumulative runtime" | Low-medium. The runtime meaning comes from the Normal column name, not the brief; confirm it with the EEPROM document if it arrives |
| R3 | Product performance (motor) | `ddm692_ExhaustTempBins` (bins 1–7; 8–10 are zero), `ddm692_FisfTempBins` | Brief lists exhaust temperature; exhaust is verified; FISF temperature is declared in `DDM_Bins.json` in celsius | Exhaust low. `Fisf` is an undefined abbreviation; use only as a distribution, not a named sensor |
| R4 | Product performance (motor) | `ambientTemperature_mC`, `ambientPressure_Pa`, `ddm692_PressureBins` | Brief lists ambient temperature and pressure. Ambient values equal the Normal `ambient_*` columns | Ambient scalars low (units confirmed by Normal column names). `PressureBins` medium: it relies on the inferred alias with weak supporting evidence; label it as such or leave it out |
| R5 | Faults / product performance (motor) | `filterWashCounter`, `ddmOnButNotRunTime_s` | Clean counters; filter wash relates to brief fault type 13 | Medium. Both meanings come from key names. Do not link `filterWashCounter` to fault type 13 events as causation |
| R6 | Battery | The 12 bin arrays of the standard layout | Brief lists charge and discharge behaviour; names, locations, lengths and edges verified against `BMS_Bins.json` | Low for definitions. Normal arrays are not clean counters (section 5); 2-D flattening order is inferred |
| R7 | Battery | `sigDischarges.allTime`, `chargerInsertions.allTime`, `dischargeStopEvents.*`, `dischargeInhibitEvents.*`, `chargeStopEvents.*`, `header.power_ups` | Brief lists charge and discharge statistics | Medium. Names only; meaning of "when frozen" and of the counters' reset behaviour unknown |
| R8 | Battery | From the 15 event snapshots: `stateOfCharge`, `stateOfHealth`, `temp`, `packVolt`, `cellVolt` (min/max/spread) | Brief lists SoC, SoH, temperature and cell voltages | **High.** Meaning is from key names; units and scales are unknown (for example `stateOfHealth` 9999 or 10000, `temp` 2434). Parse as raw values only; do not convert units until documented |
| R9 | Battery | `*_Power_Resistance`, `SoH_Rs_*` | Brief lists resistance estimates | High. Names only; units unknown. Low priority |
| R10 | All | Payload metadata: `payload_layout`, battery variant (4-cell/7-cell), cell count, `hdr_timestamp`, `server_timestamp` | Needed to compare like with like and to order observations | Low |

Not recommended for Step 3:

- `ddm692_NormSpeedBins` (always zero), `ddm692_BarometerTempBins` (inferred alias, no check possible), `tableSize`/`formatId`/`checksum`/`padding*`/`counter` fields, event code fields (`state`, `reason`, `lockout`, `inputOutput`: undocumented), `Dekf_*` and other algorithm state, `runtimeStats`, and the `ppc*`, `fw*`, `*DerCounter`, `powerReset` fields (undefined).
- The labelled and flat battery layouts (39 rows, 3 serials). Their value is small, they need a separate label parser and they carry an extra low bin. Keep them in the DQ report as an unparsed layout.

Suggested table shapes (recommendation): one row per payload with scalars (serial, `hdr_timestamp`, layout, variant, chosen scalars), and bins in long format (serial, `hdr_timestamp`, array, bin index, lower edge, upper edge, value) so edges live in the mapping module, not in column names.

## 8. Open questions

1. **Label-based battery layouts:** park them as an unparsed layout (recommended) or parse them? (39 rows, 3 serials.)
2. **Normal battery populations:** for battery comparisons, restrict to 7-cell/SV53 so Normal and Return/Repair are comparable, or keep both with a variant column? (The 4-cell/SV50 data is 86% of Normal battery rows and shows many counter decreases.)
3. **Counter decreases:** the cause is unknown (reset, rolling window, device-clock ordering, or a different record). Should negatives be treated as a reset (use the current value as the delta), dropped, or set missing? The EEPROM document may settle this.
4. **Pressure and barometer-temperature aliases:** accept `ddm692_PressureBins` ↔ `PressBins` as a labelled inference (weak evidence), or leave those two arrays out of the analysis?
5. **Motor Normal sampling:** its median gap between observations is 22 days (p90 64 days), unlike the other groups (about 7–8 days). Is that expected (different collection cadence), or is the file incomplete? It affects how deltas are normalised per week.
6. **Runtime:** may `sum(PowerBins)` be used as the cumulative runtime for both cohorts, given it reproduces the Normal column exactly?
7. **Units and scales for the battery event snapshots** (`stateOfCharge`, `stateOfHealth`, `temp`, `packVolt`, `cellVolt`, `runTime`) are not stated anywhere I have. Do you have a source, or should they stay raw until the EEPROM document arrives?
8. **`BarTempBins` unit (krpm):** keep the declared unit and flag it, or treat the unit as unknown? (Proposed: unknown.)
9. **Future `hdr_timestamp` (up to 2055):** the rule (exclude, null, or fall back to `server_timestamp`) belongs in Step 4. Do you agree?

## 9. Decisions (answers to section 8)

Recorded 2026-10-09 and logged in `docs/assumptions_log.md`. Numbering follows section 8.

1. **Labelled and flat battery layouts:** left unparsed (39 rows, 3 serials). Positional mapping is not safe and the volume is small.
2. **Battery cohort comparison:** Normal vs Return/Repair uses the 7-cell / SV53 subset only; a pack-type (variant) column is kept so the 4-cell / SV50 population stays available for non-cohort analysis. Size of the Normal subset after removing re-uploads: 133 records, 10 serials (8 serials with at least 2 records); Return/Repair: 410 records, 42 serials.
3. **Counter decreases:** not treated as resets and rows are not dropped. The delta for that interval is set to missing, a flag column marks it, and the count goes in the DQ summary. Re-uploads do not explain the decreases in Normal 4-cell (monotonic share is 41.2% with and without removing them).
4. **Pressure / barometer-temperature aliases:** both arrays left out; ambient pressure comes from the scalar `ambientPressure_Pa`.
5. **Normal motor cadence (22-day median):** cause unknown, kept as a Limitation and as a question for the data owner. Step 5 expresses deltas per day elapsed between observations.
6. **Runtime:** `sum(ddm692_PowerBins)` for both cohorts. **[verified]** for Normal; **[assumed]** for Return/Repair.
7. **Battery snapshot units:** kept raw, units "unknown", until the EEPROM document arrives. Battery health analysis prefers `battery_health` from Clean Sessions.
8. **`BarTempBins` unit:** unknown; the array is not parsed.
9. **Future `hdr_timestamp`:** the row is kept, `server_timestamp` is the fallback event time, and a flag column marks the fallback (count in the DQ summary). `server_timestamp` is upload time, so ordering for these rows is approximate.

Gate: the Step 3 parse list in section 7 is accepted, with the exclusions above (no aliases, no labelled or flat layouts, battery snapshot values raw). Effect on section 7: R4 keeps only the ambient scalars (`ddm692_PressureBins` is removed); R8 stays raw-only; R10 keeps the battery variant column.
