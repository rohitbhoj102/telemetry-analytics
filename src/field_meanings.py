"""Single home for field meanings, units, bin mappings and output column names (Step 3).

Rules (project decisions):
- A meaning is recorded as "stated" only if the brief or a bin JSON states it.
- A meaning read from a key name is "inferred from key name". Anything else is "unknown".
- Bin edges and array units are read from reference_files/*.json, never retyped here.
- Battery snapshot values (SoC, SoH, temperature, voltage, runtime) are kept raw, unit "unknown".
"""
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF_DIR = ROOT / "reference_files"

STATED = "stated (brief or bin JSON)"
INFERRED_NAME = "inferred from key name"
INFERRED = "inferred"
UNKNOWN = "unknown"

# Edge-unit symbols used in battery column names.
UNIT_SYMBOL = {"second": "s", "minute": "min", "celsius": "C", "volt": "V", "watt": "W"}

# ---------------------------------------------------------------------------
# Renamed columns in the cleaned tables (original name -> clean name)
# ---------------------------------------------------------------------------
RENAMED_COLUMNS = {
    "clean_sessions": {"date": "date_server"},
    "faults": {"date": "date_server"},
}
DATE_SERVER_NOTE = (
    "`date` in the raw clean-sessions and faults files, kept unchanged and renamed date_server. "
    "[inferred] server receipt time: it is later than faults.fault_timestamp in all but 13 of 31,398 fault "
    "rows (src/link_checks.py); the brief does not define it."
)
# Time-sync columns: kept as the raw numbers; *_ts is the same number read as epoch seconds.
TIME_SYNC_NOTE = "[assumed] epoch seconds (values fall in 1970 / 2025-2026); meaning unknown (not in brief or bin JSONs)."

# ---------------------------------------------------------------------------
# Bin definitions
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def bin_defs():
    out = {}
    for fname in ("DDM_Bins.json", "BMS_Bins.json"):
        with open(str(REF_DIR / fname)) as f:
            for k, v in json.load(f).items():
                out[k] = dict(v, source_file=fname)
    return out


def _num(x, dec):
    return ("%g" % x).replace(".", dec)


def range_tokens(edges, dec="_", unit=""):
    """['lt_e0', 'e0_e1', ..., 'gt_ek'] for edges e0..ek (len(edges) + 1 tokens)."""
    toks = ["lt_%s%s" % (_num(edges[0], dec), unit)]
    for a, b in zip(edges[:-1], edges[1:]):
        toks.append("%s_%s%s" % (_num(a, dec), _num(b, dec), unit))
    toks.append("gt_%s%s" % (_num(edges[-1], dec), unit))
    return toks


def _bounds(edges):
    """(lo, hi) per bin; None at the open ends."""
    lows = [None] + list(edges)
    highs = list(edges) + [None]
    return list(zip(lows, highs))


# Motor: (definition name in DDM_Bins.json, column stem, number of bins kept).
# Column names follow the Normal motor flattened columns (decimal point -> "_", suffix "_seconds").
# Exhaust: bins 1-7 only (bins 8-10 are zero in every row of both cohorts; a flag column watches them).
# NOT parsed (project decisions): ddm692_NormSpeedBins (always zero), ddm692_PressureBins and
# ddm692_BarometerTempBins (alias evidence weak; ambient pressure comes from the scalar).
MOTOR_BIN_ARRAYS = (
    ("ddm692_SpeedBins", "speed_bin", None),
    ("ddm692_PowerBins", "power", None),
    ("ddm692_ExhaustTempBins", "exhaust_temperature_bin", 7),
    ("ddm692_FisfTempBins", "fisf_temperature_bin", None),
)
MOTOR_EXHAUST_ARRAY = "ddm692_ExhaustTempBins"
MOTOR_RUNTIME_ARRAY = "ddm692_PowerBins"

# Battery: (definition name in BMS_Bins.json, column stem).
BATTERY_BIN_ARRAYS = (
    ("powerBins", "discharge_power"),
    ("dischargeBandBins", "discharge_band"),
    ("dischargeDurationBins", "discharge_duration"),
    ("dischargeStartTempBins", "discharge_start_temp"),
    ("dischargeOffTimeBins", "discharge_off_time"),
    ("dischargeBtwChargesBins", "discharge_btw_charges"),
    ("chargeMaintainTempBins", "charge_maintain_temp"),
    ("chargeBandBins", "charge_band"),
    ("chargeDurationBins", "charge_duration"),
    ("chargeAmbientTempPreCustomerBins", "charge_ambient_temp_precustomer"),
    ("chargeAmbientTempCustomerBins", "charge_ambient_temp_customer"),
    ("minCellVoltAtChargeStartBins", "min_cell_volt_at_charge_start"),
)

# Storage order of the 2-D arrays (dischargeBandBins, chargeBandBins). Found from the data, see
# docs/parsing_spec.md section 3.2 and reports/profiling/parse_summary.csv notes:
# flat list of 9, row-major with dimension 0 (voltage) slowest and dimension 1 (temperature) fastest,
# i.e. index = 3 * voltage_band + temperature_band. [inferred]: the bin JSON does not state the order.
BAND_2D_ORDER = "row-major, voltage (dimension 0) slowest, temperature (dimension 1) fastest"


@lru_cache(maxsize=None)
def motor_bin_columns():
    """List of dicts, one per kept motor bin column."""
    rows = []
    for name, stem, keep in MOTOR_BIN_ARRAYS:
        d = bin_defs()[name]
        dim = d["bins"][0]
        toks = range_tokens(dim["partitions"], "_")
        assert len(toks) == d["sizes"][0], name
        bounds = _bounds(dim["partitions"])
        for i, tok in enumerate(toks[:keep]):
            rows.append({
                "table": "motor", "column": "%s_%s_seconds" % (stem, tok), "array": name,
                "json_path": "ddmUsage.%s.bins" % name, "index": i, "lo": bounds[i][0], "hi": bounds[i][1],
                "edge_unit": dim["unit"], "array_unit": d["unit"], "meaning_status": STATED,
                "note": "JSON names this bin dimension 'speed' but declares unit %s; the unit is used" % dim["unit"]
                if dim["unit"] != "krpm" else "",
            })
    return rows


@lru_cache(maxsize=None)
def battery_bin_columns():
    """List of dicts, one per battery bin column (flat order = payload order)."""
    rows = []
    for name, stem in BATTERY_BIN_ARRAYS:
        d = bin_defs()[name]
        path = "%s.%s" % (d["jsonLoc"], name)
        dims = d["bins"]
        if len(dims) == 1:
            dim = dims[0]
            sym = UNIT_SYMBOL[dim["unit"]]
            toks = range_tokens(dim["partitions"], "p")
            assert len(toks) == d["sizes"][0], name
            bounds = _bounds(dim["partitions"])
            for i, tok in enumerate(toks):
                rows.append({
                    "table": "battery", "column": "%s_%s_%s" % (stem, tok, sym), "array": name, "json_path": path,
                    "index": i, "lo": bounds[i][0], "hi": bounds[i][1], "edge_unit": dim["unit"],
                    "array_unit": d["unit"], "meaning_status": STATED, "note": ""})
        else:
            dv, dt = dims
            tv = range_tokens(dv["partitions"], "p", UNIT_SYMBOL[dv["unit"]])
            tt = range_tokens(dt["partitions"], "p", UNIT_SYMBOL[dt["unit"]])
            assert [len(tv), len(tt)] == d["sizes"], name
            bv, bt = _bounds(dv["partitions"]), _bounds(dt["partitions"])
            for iv, a in enumerate(tv):
                for it, b in enumerate(tt):
                    rows.append({
                        "table": "battery", "column": "%s_%s_%s" % (stem, a, b), "array": name, "json_path": path,
                        "index": len(tt) * iv + it,
                        "lo": "V:%s T:%s" % (bv[iv][0], bt[it][0]), "hi": "V:%s T:%s" % (bv[iv][1], bt[it][1]),
                        "edge_unit": "volt x celsius", "array_unit": d["unit"], "meaning_status": INFERRED,
                        "note": "2-D storage order is %s" % BAND_2D_ORDER})
    return rows


def battery_bin_layout():
    """[(array name, full json_path tuple incl. the array key, [column names in payload order])]."""
    out = {}
    for r in battery_bin_columns():
        out.setdefault(r["array"], []).append(r)
    layout = []
    for name, _stem in BATTERY_BIN_ARRAYS:
        rows = sorted(out[name], key=lambda r: r["index"])
        layout.append((name, tuple(rows[0]["json_path"].split(".")), [r["column"] for r in rows]))
    return layout


def motor_bin_layout():
    """[(array name, [column names in payload order])]."""
    out = {}
    for r in motor_bin_columns():
        out.setdefault(r["array"], []).append(r)
    return [(name, [r["column"] for r in sorted(out[name], key=lambda r: r["index"])])
            for name, _stem, _keep in MOTOR_BIN_ARRAYS]


def expected_bin_length(name):
    d = bin_defs()[name]
    n = 1
    for s in d["sizes"]:
        n *= s
    return n


# ---------------------------------------------------------------------------
# Motor scalars: clean name -> (json path, unit, meaning status, meaning)
# ---------------------------------------------------------------------------
MOTOR_SCALARS = (
    ("ambient_temperature_mC", ("ddmUsage", "ambientTemperature_mC"), "milli-degC", INFERRED_NAME,
     "ambient temperature (brief lists 'ambient temperature'); equals the Normal column of the same name"),
    ("ambient_pressure_pa", ("ddmUsage", "ambientPressure_Pa"), "Pa", INFERRED_NAME,
     "ambient pressure (brief lists 'ambient pressure'); equals the Normal column of the same name"),
    ("write_count", ("header", "writeCount"), "count", INFERRED_NAME,
     "write counter; equals the Normal column of the same name"),
    ("filter_wash_counter", ("ddmUsage", "filterWashCounter"), "count", INFERRED_NAME,
     "count of filter washes; do not link to fault type 13 as causation"),
    ("on_but_not_run_time_s", ("ddmUsage", "ddmOnButNotRunTime_s"), "s", INFERRED_NAME,
     "seconds powered on but not running"),
)
MOTOR_DERIVED = (
    ("runtime_s", "s", INFERRED, "sum(ddm692_PowerBins). [verified] equals Normal cumulative_usage_duration_seconds "
     "in all rows; [assumed] to be the cumulative runtime for Return/Repair (project decision)"),
    ("ambient_temperature_C", "degC", INFERRED, "ambient_temperature_mC / 1000 (verified against the Normal column)"),
    ("ambient_pressure_kpa", "kPa", INFERRED, "ambient_pressure_pa / 1000 (verified against the Normal column)"),
    ("exhaust_bins_8_10_nonzero_flag", "flag", "derived", "True if any of exhaust bins 8-10 (not output) is non-zero; "
     "False in every row of both cohorts in the current data"),
)

# ---------------------------------------------------------------------------
# Battery scalars (event counters) and raw algorithm values
# ---------------------------------------------------------------------------
BATTERY_COUNTERS = (
    ("sig_discharges_all_time", ("usage", "dischargeLog", "sigDischarges", "allTime"), "count", INFERRED_NAME),
    ("charger_insertions_all_time", ("usage", "chargeLog", "chargerInsertions", "allTime"), "count", INFERRED_NAME),
    ("discharge_stop_low_volt", ("usage", "dischargeLog", "dischargeStopEvents", "lowVolt"), "count", INFERRED_NAME),
    ("discharge_stop_no_load", ("usage", "dischargeLog", "dischargeStopEvents", "noLoad"), "count", INFERRED_NAME),
    ("discharge_stop_over_temp", ("usage", "dischargeLog", "dischargeStopEvents", "overTemp"), "count", INFERRED_NAME),
    ("discharge_inhibit_other", ("usage", "dischargeLog", "dischargeInhibitEvents", "other"), "count", INFERRED_NAME),
    ("discharge_inhibit_pack_flat", ("usage", "dischargeLog", "dischargeInhibitEvents", "packFlat"), "count", INFERRED_NAME),
    ("charge_stop_over_temp", ("usage", "chargeLog", "chargeStopEvents", "overTemp"), "count", INFERRED_NAME),
    ("charge_stop_under_temp", ("usage", "chargeLog", "chargeStopEvents", "underTemp"), "count", INFERRED_NAME),
    ("charge_stop_charging_for_long", ("usage", "chargeLog", "chargeStopEvents", "chargingForLong"), "count", INFERRED_NAME),
    ("charge_stop_over_current", ("usage", "chargeLog", "chargeStopEvents", "overCurrent"), "count", INFERRED_NAME),
    ("charge_stop_other_fault", ("usage", "chargeLog", "chargeStopEvents", "otherFault"), "count", INFERRED_NAME),
    ("charge_stop_charger_removed", ("usage", "chargeLog", "chargeStopEvents", "chargerRemoved"), "count", INFERRED_NAME),
    ("power_ups", ("header", "power_ups"), "count", INFERRED_NAME),  # absent in the 4-cell variant (no header)
)
# Raw algorithm values (parsing spec R9): names only, unit unknown. Optional keys give null.
BATTERY_RESISTANCE = (
    ("min_power_resistance_raw", ("miscAndSibyl", "sibylData", "runtimeAlgo", "Min_Power_Resistance")),
    ("low_power_resistance_raw", ("miscAndSibyl", "sibylData", "runtimeAlgo", "Low_Power_Resistance")),
    ("medium_power_resistance_raw", ("miscAndSibyl", "sibylData", "runtimeAlgo", "Medium_Power_Resistance")),
    ("high_power_resistance_raw", ("miscAndSibyl", "sibylData", "runtimeAlgo", "High_Power_Resistance")),
    ("peak_power_resistance_raw", ("miscAndSibyl", "sibylData", "runtimeAlgo", "Peak_Power_Resistance")),
    ("soh_rs_min_raw", ("miscAndSibyl", "sibylData", "sohData", "SoH_Rs_Min")),
    ("soh_rs_low_raw", ("miscAndSibyl", "sibylData", "sohData", "SoH_Rs_Low")),
    ("soh_rs_med_raw", ("miscAndSibyl", "sibylData", "sohData", "SoH_Rs_Med")),
    ("soh_rs_high_raw", ("miscAndSibyl", "sibylData", "sohData", "SoH_Rs_High")),
    ("soh_rs_peak_raw", ("miscAndSibyl", "sibylData", "sohData", "SoH_Rs_Peak")),
)
BATTERY_RESISTANCE_NOTE = ("[inferred from key name] resistance-related value (brief lists 'resistance estimates'); "
                           "unit unknown; kept raw")

# Event / fault snapshot records (eventLog.events: 15 records, eventLog.faults: 2 records).
# All raw values; unit and scale unknown. (clean name, key in the record)
SNAPSHOT_SCALARS = (
    ("time_raw", "time"),
    ("state_of_charge_raw", "stateOfCharge"),
    ("state_of_health_raw", "stateOfHealth"),
    ("pack_volt_raw", "packVolt"),
    ("run_time_raw", "runTime"),
)
SNAPSHOT_NOTES = {
    "time_raw": "unknown: time base and unit not stated",
    "state_of_charge_raw": "inferred from key name (brief lists SoC); scale unknown",
    "state_of_health_raw": "inferred from key name (brief lists SoH); scale unknown (e.g. 9999 / 10000 seen)",
    "pack_volt_raw": "inferred from key name; unit unknown",
    "run_time_raw": "inferred from key name (brief lists 'runtime'); unit unknown",
    "temp_1_raw": "inferred from key name (brief lists 'battery temperature'); unit unknown. 7-cell packs hold one "
                  "integer (stored in temp_1_raw); 4-cell packs hold three values",
    "cell_volt_min_raw": "inferred from key name (brief lists 'cell voltages'); unit unknown",
}

PACK_TYPES = {4: "4-cell", 7: "7-cell"}


def column_dictionary():
    """Rows describing every parsed (non-metadata) column, for reports/profiling/clean_column_dictionary.csv."""
    rows = []
    for r in motor_bin_columns() + battery_bin_columns():
        rows.append({"table": r["table"], "column": r["column"], "source": r["json_path"] + "[%d]" % r["index"],
                     "unit": r["edge_unit"] + " (edges); array unit: " + r["array_unit"],
                     "status": r["meaning_status"], "note": r["note"]})
    for col, path, unit, status, note in MOTOR_SCALARS:
        rows.append({"table": "motor", "column": col, "source": ".".join(path), "unit": unit, "status": status, "note": note})
    for col, unit, status, note in MOTOR_DERIVED:
        rows.append({"table": "motor", "column": col, "source": "derived", "unit": unit, "status": status, "note": note})
    for col, path, unit, status in BATTERY_COUNTERS:
        rows.append({"table": "battery", "column": col, "source": ".".join(path), "unit": unit, "status": status,
                     "note": "counter semantics (reset behaviour) unknown"})
    for col, path in BATTERY_RESISTANCE:
        rows.append({"table": "battery", "column": col, "source": ".".join(path), "unit": UNKNOWN,
                     "status": INFERRED_NAME, "note": BATTERY_RESISTANCE_NOTE})
    for col, key in SNAPSHOT_SCALARS:
        rows.append({"table": "battery_event_snapshots", "column": col, "source": "eventLog.events|faults[].%s" % key,
                     "unit": UNKNOWN, "status": INFERRED_NAME if col != "time_raw" else UNKNOWN, "note": SNAPSHOT_NOTES[col]})
    rows.append({"table": "battery_event_snapshots", "column": "temp_1_raw / temp_2_raw / temp_3_raw / temp_n",
                 "source": "eventLog.events|faults[].temp", "unit": UNKNOWN, "status": INFERRED_NAME,
                 "note": SNAPSHOT_NOTES["temp_1_raw"]})
    rows.append({"table": "battery_event_snapshots", "column": "cell_volt_min_raw / cell_volt_max_raw / cell_volt_spread_raw / n_cells",
                 "source": "eventLog.events|faults[].cellVolt", "unit": UNKNOWN, "status": INFERRED_NAME,
                 "note": SNAPSHOT_NOTES["cell_volt_min_raw"]})
    return rows


# ---------------------------------------------------------------------------
# Fault types stated in the brief (used by src/dq.py). Any type not listed here has NO stated meaning.
# fault_type -> (name, {fault_value: meaning}).  fault_status (0/1) is NOT defined anywhere: unknown.
# ---------------------------------------------------------------------------
FAULT_TYPES = {
    12: ("Airway Blockage", {0: "not blocked", 1: "inlet blocked, motor still running",
                             2: "inlet blocked and in error", 3: "outlet blocked and in error"}),
    7: ("Brush Bar Stall", {}),  # fault_value N/A (stall detected)
    11: ("Battery Temperature", {0: "OK", 1: "COLD", 2: "HOT"}),
    13: ("Filter Wash", {0: "OK", 1: "needs cleaning"}),
}
