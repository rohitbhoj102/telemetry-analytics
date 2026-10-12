# Dashboard data: final insights

Source of the dashboard: `dashboard/data/insights_dashboard.csv` (committed; a byte-identical copy is written to `data/model/tableau/`), written by `src/make_dashboard_data.py`
(also run by `python src/run_all.py`). The other Tableau CSVs in `data/model/tableau/` are generated and git-ignored.
Every value, interval and machine count is copied from the `f_` rows of `reports/insights/key_numbers.csv` by id;
nothing is recomputed. The script re-reads the CSV and prints a pass/fail table against `key_numbers.csv`
(string equality, i.e. full stored precision); it exits with an error if any value differs or an id is missing.

## Layout (one dashboard section per insight, in deck order)
| Order | Insight | Title | Charts |
|---|---|---|---|
| 1 | I1 | Blockages cluster around filter reminders | `same_clean` (2 bars), `lead_7d` (3 bars), `headline` (1) |
| 2 | I4 | The SV53 rarely warns before a blockage error | `warned_first` (2 bars), `headline` (1) |
| 3 | I3 | Returned SV53s log 3–5x more blockages, led by SV53-AB | `submodel` (4 bars), `ratio` (2 bars) |
| 4 | I2 | The SV50 sends no battery temperature in most cleans | `no_temp` (3 bars), `hot_batteries` (2 points) |

## What each chart shows
| Chart | Insight | What it shows |
|---|---|---|
| `same_clean` | 1 | Share of cleans with an airway blockage with a Filter Wash reminder vs without (11.8% vs 0.9%) |
| `lead_7d` | 1 | Blockage episode rate in the 7 days after a reminder vs other times, by group (Normal SV50, Normal SV53, Return/Repair SV53) |
| `headline` (I1) | 1 | Same-session risk ratio, reminder vs none, same machine (6.0x) |
| `warned_first` | 2 | Share of blockage-error sessions preceded by a warning, SV50 vs SV53 (92% vs 27%) |
| `headline` (I4) | 2 | Difference between the two shares, percentage points (65.2 pp) |
| `submodel` | 3 | Blockages per 100 cleans by SV53 sub-model, Normal machines (SV53-AB highest) |
| `ratio` | 3 | Returned vs Normal blockage-rate ratio, as recorded (4.7x) and with the same sub-model mix (3.1x) |
| `no_temp` | 4 | Share of cleans with no battery temperature flag (SV50 74%, SV53 3%) |
| `hot_batteries` | 4 | Machines with discharge above 45 C: 9 of 15 SV50, 5 of 42 SV53 (low confidence) |

The data quality screenshot (`dashboard/screenshots/02_dq_explorer.png`) is not built from this CSV: it shows raw vs usable rows per table and cohort (`dq_` rows of `key_numbers.csv`) and a machine-level scatter from `tableau_machines.csv`.

## Columns
| Column | Meaning |
|---|---|
| `deck_order` | 1–4, the order of the insight in the deck |
| `insight_id` | Insight id used in the analysis (I1, I4, I3, I2) |
| `insight_title` | Section title |
| `chart` | Chart within the insight (see layout) |
| `bar_label` | Text for the bar / point |
| `bar_order` | Position within the chart |
| `value` | Point estimate, as stored in `key_numbers.csv` |
| `low`, `high` | Interval bounds, as stored; blank where none is stored (e.g. the machine counts in `hot_batteries`) |
| `unit` | `pct` (percent; the I4 headline is percentage points), `per100` (type-12 faults per 100 clean sessions), `ratio`, `count` |
| `n_machines` | Machines behind the value (for I3 sub-model bars, from the matching `f_i3_machines_` row) |
| `role` | `focus` (highlighted), `baseline` (comparison), `gap` (the gap being shown) |
| `label_text` | The printed label, formatted from the stored value and interval (e.g. `11.8% [8.7–15.4]`) |
| `source_id` | `key_numbers.csv` id the row was copied from |

`value` for the two `hot_batteries` rows is the percentage of machines; the label shows the counts ("9 of 15", "5 of 42").
Roles `focus` / `baseline` were assigned for highlighting only and carry no statistical meaning.

## Caveats
- Intervals are 95% machine bootstraps (machines are resampled, not sessions), except where `key_numbers.csv` states otherwise for a specific row. Counts of 15 and 42 machines have no interval.
- `hot_batteries` is low confidence: one SV50 machine holds 85% of SV50 hot discharge time, and few machines contribute battery data. It is shown as a baseline-style point for that reason.
- Return/Repair machines are a selected population (selection bias), and several groups are small. Associations are not causal: for example, a blockage that follows a filter reminder does not show that the reminder or the filter caused it.
- Fault ordering in I1 and I4 uses `fault_timestamp` (device time), which is inferred, not documented.
- I3 "As recorded" and "Same sub-model mix" overlap; the intervals are wide, so "3–5x" is a range, not a precise figure.
- Excluded on purpose: copy-group sizes (100/636), geography figures and `filter_wash_counter`.
