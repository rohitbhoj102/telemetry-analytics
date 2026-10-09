"""Read-only helper: load motor/battery payload rows and assign each to a payload group.

Used by diagnostics only (Step 2). It does not clean, de-duplicate or modify anything.
Groups: motor_normal, motor_rr, battery_normal, battery_rr_standard, battery_rr_labelled, battery_rr_flat.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {
    "motor_normal": ROOT / "normal_machines" / "Motor_Normal Machines.csv",
    "motor_rr": ROOT / "return_repair_machines" / "Motor_Return:Repair Machines.csv",
    "battery_normal": ROOT / "normal_machines" / "Battery_Normal Machines.csv",
    "battery_rr": ROOT / "return_repair_machines" / "Battery_Return:Repair Machines.csv",
}


def battery_layout(payload):
    """Classify a battery payload.

    'flat': no `eventLog` key (keys like /HEADER/...).
    'labelled': `eventLog` present but `usage` bins are dicts keyed by text labels, not arrays.
    'standard': `eventLog` present and `usage` bins are numeric arrays.
    """
    if "eventLog" not in payload:
        return "flat"
    power = payload.get("usage", {}).get("dischargeLog", {}).get("powerBins")
    return "labelled" if isinstance(power, dict) else "standard"


def load_groups():
    """Return {group: DataFrame[anonymized_serial, server_timestamp, hdr_timestamp, payload]}.

    `hdr_timestamp` / `server_timestamp` are parsed to datetime (parse failures were 0 in profiling).
    Rows with a null `decoded_data` are not included (reported separately as a DQ finding).
    """
    groups = {}
    for name, path in SOURCES.items():
        df = pd.read_csv(path, low_memory=False, usecols=["anonymized_serial", "server_timestamp", "hdr_timestamp", "decoded_data"])
        df = df[df["decoded_data"].notna()].copy()
        for c in ("server_timestamp", "hdr_timestamp"):
            df[c] = pd.to_datetime(df[c].str.replace(" UTC", "", regex=False))
        df["raw"] = df["decoded_data"]
        df["payload"] = df["decoded_data"].map(json.loads)
        df = df.drop(columns="decoded_data")
        if name == "battery_rr":
            layout = df["payload"].map(battery_layout)
            groups["battery_rr_standard"] = df[layout == "standard"]
            groups["battery_rr_labelled"] = df[layout == "labelled"]
            groups["battery_rr_flat"] = df[layout == "flat"]
        else:
            groups[name] = df
    return groups
