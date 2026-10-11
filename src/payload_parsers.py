"""Parsers for the `decoded_data` JSON payloads of motor and battery rows (Step 3).

Pure functions: dict in, dict out. They never modify or drop anything; a payload that does not fit
raises ParseError (or KeyError / TypeError), and the caller records parse_status = 'error'.
All names, edges and units come from field_meanings.py.
"""
import re

import field_meanings as fm
from payload_io import battery_layout

LAYOUT_STANDARD, LAYOUT_LABELLED, LAYOUT_FLAT = "standard", "labelled", "flat"


class ParseError(Exception):
    pass


def _get(payload, path, default=None):
    cur = payload
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _int_array(payload, path, expected_len, label):
    arr = _get(payload, path)
    if not isinstance(arr, list):
        raise ParseError("%s: missing or not a list" % label)
    if len(arr) != expected_len:
        raise ParseError("%s: length %d, expected %d" % (label, len(arr), expected_len))
    if not all(_is_int(v) for v in arr):
        raise ParseError("%s: non-integer value" % label)
    return arr


# ---------------------------------------------------------------------------
# Motor (both cohorts, one parser)
# ---------------------------------------------------------------------------


def parse_motor(payload):
    out = {}
    for name, cols in fm.motor_bin_layout():
        bins = _int_array(payload, ("ddmUsage", name, "bins"), fm.expected_bin_length(name), name)
        for col, v in zip(cols, bins):
            out[col] = v
        if name == fm.MOTOR_EXHAUST_ARRAY:
            out["exhaust_bins_8_10_nonzero_flag"] = any(v != 0 for v in bins[len(cols):])
        if name == fm.MOTOR_RUNTIME_ARRAY:
            out["runtime_s"] = sum(bins)
    for col, path, _unit, _status, _note in fm.MOTOR_SCALARS:
        v = _get(payload, path)
        if not _is_int(v):
            raise ParseError("%s: missing or non-integer (%s)" % (col, ".".join(path)))
        out[col] = v
    out["ambient_temperature_C"] = out["ambient_temperature_mC"] / 1000.0
    out["ambient_pressure_kpa"] = out["ambient_pressure_pa"] / 1000.0
    return out


# ---------------------------------------------------------------------------
# Battery
# ---------------------------------------------------------------------------


def detect_layout(payload):
    """'standard' / 'labelled' / 'flat' (same rule as payload_io.battery_layout)."""
    return battery_layout(payload)


_FLAT_CELL = re.compile(r"^/EVENT_LOGS/event0/volt/cell\d+$")


def pack_type_of(payload, layout):
    """'4-cell' / '7-cell' from the number of cell voltages in the first event record, else None."""
    if layout == LAYOUT_FLAT:
        n = sum(1 for k in payload if _FLAT_CELL.match(k))
    else:
        events = _get(payload, ("eventLog", "events"))
        cells = events[0].get("cellVolt") if isinstance(events, list) and events and isinstance(events[0], dict) else None
        n = len(cells) if isinstance(cells, list) else 0
    if n == 0:
        return None
    return fm.PACK_TYPES.get(n, "%d-cell" % n)


def _snapshot(rec, kind, index):
    row = {"record_kind": kind, "record_index": index}
    for col, key in fm.SNAPSHOT_SCALARS:
        row[col] = rec.get(key)
    temp = rec.get("temp")
    temps = list(temp) if isinstance(temp, list) else ([temp] if temp is not None else [])
    row["temp_n"] = len(temps)
    for i in range(3):
        row["temp_%d_raw" % (i + 1)] = temps[i] if i < len(temps) else None
    cells = rec.get("cellVolt")
    cells = list(cells) if isinstance(cells, list) else []
    row["n_cells"] = len(cells)
    row["cell_volt_min_raw"] = min(cells) if cells else None
    row["cell_volt_max_raw"] = max(cells) if cells else None
    row["cell_volt_spread_raw"] = (max(cells) - min(cells)) if cells else None
    return row


def parse_battery(payload):
    """Parse a *standard-layout* battery payload. Returns (row dict, list of snapshot dicts)."""
    out = {}
    for name, path, cols in fm.battery_bin_layout():
        arr = _int_array(payload, path, fm.expected_bin_length(name), name)
        for col, v in zip(cols, arr):
            out[col] = v
    for col, path, _unit, _status in fm.BATTERY_COUNTERS:
        v = _get(payload, path)
        if v is not None and not _is_int(v):
            raise ParseError("%s: non-integer (%s)" % (col, ".".join(path)))
        out[col] = v  # optional keys (e.g. header.power_ups in the 4-cell variant) -> None
    for col, path in fm.BATTERY_RESISTANCE:
        v = _get(payload, path)
        out[col] = v if _is_int(v) else None
    snaps = []
    for kind in ("events", "faults"):
        recs = _get(payload, ("eventLog", kind))
        if not isinstance(recs, list):
            raise ParseError("eventLog.%s: missing or not a list" % kind)
        for i, rec in enumerate(recs):
            if not isinstance(rec, dict):
                raise ParseError("eventLog.%s[%d]: not an object" % (kind, i))
            snaps.append(_snapshot(rec, kind[:-1], i))  # 'event' / 'fault'
    out["has_bpa_sno_root"] = "bpa_SNO" in payload  # 4-cell signature, used only for a cross-check
    return out, snaps
