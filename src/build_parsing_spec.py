"""Step 2: generate the tables used in docs/parsing_spec.md. Read-only; no parsing of data into tables.

Run from the repo root (after src/cumulative_check.py):  python src/build_parsing_spec.py
Outputs (generated):
    reports/profiling/parsing_spec_paths.csv        every path, every group
    reports/profiling/spec_tables/*.md              markdown tables pasted into docs/parsing_spec.md
    reports/profiling/spec_checks.csv               derived-relationship / consistency checks

Meaning policy: a meaning is written only if the brief or a bin JSON states it. A reading taken from a
key name is written as "[inferred from key name] ...". Everything else is "unknown".
"""
import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from payload_io import ROOT, load_groups

OUT = ROOT / "reports" / "profiling"
TBL = OUT / "spec_tables"
DEFS = {
    "motor": json.loads((ROOT / "reference_files" / "DDM_Bins.json").read_text()),
    "battery": json.loads((ROOT / "reference_files" / "BMS_Bins.json").read_text()),
}
DEF_FILE = {"motor": "DDM_Bins.json", "battery": "BMS_Bins.json"}
# [inferred] payload name -> definition name (no exact match exists)
ALIASES = {"ddm692_PressureBins": "ddm692_PressBins", "ddm692_BarometerTempBins": "ddm692_BarTempBins"}
FLAT_SECTION_TO_DEF = {  # [inferred] by section title; flat layout only
    "Discharge power bins": "powerBins",
    "Discharge operating bands": "dischargeBandBins",
    "Discharge duration bins": "dischargeDurationBins",
    "Discharge start temperature bins": "dischargeStartTempBins",
    "Discharge off time bins": "dischargeOffTimeBins",
    "Discharge duration between charges bins": "dischargeBtwChargesBins",
    "Charge time while in different phases (in seconds)": "chargeMaintainTempBins",
    "Charge operating bands (total time in seconds)": "chargeBandBins",
    "Charge duration bins": "chargeDurationBins",
    "Charge ambient temperature for pre-customers": "chargeAmbientTempPreCustomerBins",
    "Charge ambient temperature for customers": "chargeAmbientTempCustomerBins",
    "Lowest cell voltage at start of charge": "minCellVoltAtChargeStartBins",
}

# Meanings read from key names only. Keyed by the last path segment (after stripping [] and 'bins').
# Brief-stated categories: motor: speed/power/pressure/exhaust-temperature distributions, ambient
# temperature, ambient pressure, cumulative runtime. Battery: cell voltages, SoC, SoH, charge/discharge
# behaviour and statistics, runtime, battery temperature, resistance estimates.
N = "[inferred from key name] "
INFER = {
    # motor
    "checksum": N + "record checksum (not a measurement)",
    "dataSize": N + "record size; unit unknown. Equals RR `log_size` (verified)",
    "formatId": N + "format/version id of the record or table",
    "writeCount": N + "write counter. Equals Normal `write_count` column (verified)",
    "ambientTemperature_mC": N + "ambient temperature, milli-degC (brief lists 'ambient temperature'). Normal `ambient_temperature_C` = value/1000 (verified)",
    "ambientPressure_Pa": N + "ambient pressure, Pa (brief lists 'ambient pressure'). Normal `ambient_pressure_kpa` = value/1000 (verified)",
    "ddmOnButNotRunTime_s": N + "seconds powered on but not running",
    "filterStateChgCounter": N + "count of filter state changes",
    "filterWashCounter": N + "count of filter washes (brief has fault type 13 'Filter Wash')",
    "filterWashStatus": N + "filter-wash status; coding unknown",
    "bmsAmbientTemperature_mC": N + "ambient temperature seen by the BMS, milli-degC",
    "packVoltLow_mV": N + "low pack voltage, mV",
    "tableSize": "[verified] equals the length of the sibling `bins` array in every row (see spec_checks.csv)",
    # shared battery
    "ver_FW": N + "firmware version string", "ver_SW": N + "software version string", "ver_Sibyl": N + "algorithm version string",
    "configID": N + "configuration id", "serial_HW": N + "hardware serial", "power_ups": N + "number of power-ups",
    "rated_power": N + "rated power; unit unknown", "bpa_WIP": N + "pack work-in-progress id", "bpa_SNO": N + "pack serial number",
    "eventIndex": N + "index into the event ring", "eventFaultIndex": N + "index into the fault ring", "counter": N + "record counter",
    "cellVolt": N + "cell voltages (brief lists 'cell voltages'); unit unknown",
    "packVolt": N + "pack voltage; unit unknown", "current pack": N + "pack current; unit unknown",
    "temp": N + "temperature (brief lists 'battery temperature'); unit unknown",
    "stateOfCharge": N + "state of charge (brief lists SoC); scale unknown", "stateOfHealth": N + "state of health (brief lists SoH); scale unknown",
    "runTime": N + "runtime (brief lists 'runtime'); unit unknown", "fuelGauge": N + "fuel gauge reading; unit unknown",
    "time": "unknown (time base and unit not stated)",
    "state": "unknown (enumeration, coding not documented)", "reason": "unknown (code, not documented)",
    "dischgReason": "unknown (code, not documented)", "chargeReason": "unknown (code, not documented)",
    "lockout": "unknown (code, not documented)", "inputOutput": "unknown (bit field?, not documented)", "stateReason": "unknown (code, not documented)",
    "allTime": N + "all-time count", "whenFrozen": N + "count when stats were frozen",
    "oneSecDischarge": N + "count of one-second discharges",
    "noLoad": N + "count of discharge stops, no load", "overTemp": N + "count of stops, over temperature",
    "lowVolt": N + "count of discharge stops, low voltage", "packFlat": N + "count of start inhibits, pack flat",
    "other": N + "count of start inhibits, other reason", "dischargeSecsSinceLastCharge": N + "seconds of discharge since last charge",
    "underTemp": N + "count of charge stops, under temperature", "chargingForLong": N + "count of charge stops, charging too long",
    "overCurrent": N + "count of charge stops, over current", "otherFault": N + "count of charge stops, other fault",
    "chargerRemoved": N + "count of charger removals", "Initial": N + "initial value of imbalance at end of charge",
    "Latest": N + "latest value of imbalance at end of charge", "chargeActiveTime": N + "time in active charge phase; unit unknown",
    "chargeMaintainCount": N + "count of maintenance-phase charges", "everFullyCharged": N + "flag, ever fully charged",
    "latest": N + "latest ambient temperature (flat layout labels it 'Latest Ambient Temperature')",
    "highest": N + "highest ambient temperature (flat layout labels it 'Highest Ambient Temperature')",
    "Avg_EOD_imbalance": N + "average end-of-discharge imbalance", "maxCapacity": N + "maximum capacity; unit unknown",
    "initialSoC": N + "initial SoC", "Delta_Energy": "unknown (key name only)",
    "Charge_flag": N + "flag", "Discharge_flag": N + "flag", "Initialized_flag": N + "flag",
    "Max_Stack_Used": N + "maximum stack used", "devModeUsed": N + "flag, dev mode used",
}
RE_INFER = [
    (r"Resistance$", N + "resistance estimate (brief lists 'battery resistance estimates'); unit unknown"),
    (r"^SoH_Rs", N + "SoH-related resistance value; unit unknown (brief lists SoH and resistance estimates)"),
    (r"^Dekf_", N + "state/parameter of an SoC estimation algorithm (name only); unit unknown"),
    (r"_Resets$", N + "reset count"), (r"_task$", N + "task runtime statistic"),
    (r"^(Pack_Flat|Stats_Frozen|Main_Body_Fault|Debug_Config|Behaviour_Flags)$", N + "flag"),
    (r"^(ChgErrPresent|CycleCharger|ChgOverCurrent|AuxPower|ChargerPresent|WakeReqEnabled|DisableAuxOnFlat|RecAmbientTemp)$", "unknown (key name only)"),
    (r"^(Peak|Min|High)_Power_Resistance$", N + "resistance estimate (see above)"),
]


def meaning_for(path, group_kind):
    leaf = re.sub(r"\[\]", "", path.split(".")[-1])
    if leaf in INFER:
        return INFER[leaf]
    for rx, txt in RE_INFER:
        if re.search(rx, leaf):
            return txt
    return "unknown"


def collect(groups):
    """{group: {path: {'types', 'lens', 'present'}}} with `present` = number of payloads containing the path."""
    inv = {}
    for name, df in groups.items():
        acc = defaultdict(lambda: {"types": set(), "lens": set(), "present": 0})
        for payload in df["payload"]:
            seen = set()

            def walk(node, path):
                a = acc[path]
                a["types"].add(type(node).__name__)
                seen.add(path)
                if isinstance(node, dict):
                    for k, v in node.items():
                        walk(v, f"{path}.{k}" if path else k)
                elif isinstance(node, list):
                    a["lens"].add(len(node))
                    for it in node:
                        if isinstance(it, (dict, list)):
                            walk(it, f"{path}[]")

            walk(payload, "")
            for p in seen:
                acc[p]["present"] += 1
        inv[name] = dict(acc)
    return inv


def find_definition(domain, path):
    """Return (def_name, status, note) for a numeric-array path; def_name None if unmatched."""
    parts = path.split(".")
    leaf = parts[-1]
    container = parts[-2] if leaf == "bins" and len(parts) > 1 else leaf
    defs = DEFS[domain]
    if container in defs:
        d = defs[container]
        expect = d["jsonLoc"] + "." + container + (".bins" if d["field"] == "bins" else "")
        loc = "location matches jsonLoc" if path == expect else f"location differs from jsonLoc (expected {expect})"
        return container, "verified", loc
    if container in ALIASES and ALIASES[container] in defs:
        return ALIASES[container], "inferred", f"payload name `{container}` vs definition `{ALIASES[container]}`"
    return None, "unmatched", ""


def edges_text(d):
    parts = []
    for b in d["bins"]:
        parts.append(f"{b['name']} [{b['unit']}]: " + ", ".join(str(x) for x in b["partitions"]))
    return "; ".join(parts)


def declared_cells(d):
    out = 1
    for s in d["sizes"]:
        out *= s
    return out


def cum_text(cum, group, path):
    if (group, path) not in cum.index:
        return "n/a"
    r = cum.loc[(group, path)]
    if r["constant_everywhere"]:
        return "constant"
    if pd.isna(r["pct_serials_monotonic"]):
        return "<2 obs"
    return f"{r['pct_serials_monotonic']:g}% ({int(r['pairs_with_decrease'])}/{int(r['consecutive_pairs'])})"


def md_table(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in r) + " |")
    return "\n".join(lines) + "\n"


def pct(n, d):
    return f"{100 * n / d:.0f}%" if d else "-"


def classify(path, info, domain):
    """Return (class, def_name, status, note)."""
    types = info["types"]
    if types == {"dict"}:
        return "object", None, "", ""
    if "list" in types:
        if types == {"list"}:
            # numeric array? (record lists contain dicts and were walked as path[])
            return "array", None, "", ""
        return "other (int or array)", None, "", ""
    return "scalar", None, "", ""


def main():
    TBL.mkdir(parents=True, exist_ok=True)
    groups = load_groups()
    cum = pd.read_csv(OUT / "cumulative_check.csv").set_index(["group", "path"])
    inv = collect(groups)
    all_rows = []

    def numeric_array_paths(group):
        """Paths whose values are lists of numbers (not record lists, which have a `path[]` child)."""
        inv_g = inv[group]
        return {p for p, i in inv_g.items() if i["types"] == {"list"} and f"{p}[]" not in inv_g}

    for g, df in groups.items():
        if g in ("battery_rr_flat", "battery_rr_labelled"):
            continue
        domain = "motor" if g.startswith("motor") else "battery"
        arrays = numeric_array_paths(g)
        for p, info in sorted(inv[g].items()):
            if p == "":
                continue
            cls, dname, status, note = classify(p, info, domain)
            ddef = None
            if p in arrays:
                dname, status, note = find_definition(domain, p)
                if dname is not None:
                    cls = "bin array"
                    ddef = DEFS[domain][dname]
                elif p.endswith("bins"):
                    cls = "bin array"
                    status = "unmatched"
                else:
                    cls, status = "numeric array (not a bin array)", "n/a"
            if cls == "array":
                cls = "record list" if f"{p}[]" in inv[g] else "array"
            row = {"group": g, "path": p, "payloads": len(df), "present": info["present"], "pct": 100 * info["present"] / len(df),
                   "class": cls, "json_types": "|".join(sorted(info["types"])), "list_lengths": sorted(info["lens"]),
                   "definition": dname or "", "definition_file": DEF_FILE[domain] if dname else "", "match_status": status, "match_note": note,
                   "declared_sizes": ddef["sizes"] if ddef else "", "declared_cells": declared_cells(ddef) if ddef else "",
                   "edges": edges_text(ddef) if ddef else "", "declared_array_unit": ddef["unit"] if ddef else "",
                   "meaning": meaning_for(p, domain) if cls in ("scalar", "other (int or array)", "numeric array (not a bin array)") else "",
                   "monotonic_by_hdr_ts": cum_text(cum, g, p)}
            all_rows.append(row)
    paths = pd.DataFrame(all_rows)
    paths.to_csv(OUT / "parsing_spec_paths.csv", index=False)

    # all-zero share per bin array and per group
    def zero_share(g, path):
        vals = []
        for pl in groups[g]["payload"]:
            node = pl
            try:
                for k in path.split("."):
                    node = node[k]
            except (KeyError, TypeError):
                continue
            vals.append(sum(node) == 0)
        return pct(sum(vals), len(vals))

    # ---- tables
    def pair(g1, g2, p, col):
        a = paths[(paths.group == g1) & (paths.path == p)]
        b = paths[(paths.group == g2) & (paths.path == p)]
        fa = f"{a.iloc[0][col]:.0f}%" if len(a) and col == "pct" else (a.iloc[0][col] if len(a) else "-")
        fb = f"{b.iloc[0][col]:.0f}%" if len(b) and col == "pct" else (b.iloc[0][col] if len(b) else "-")
        return fa, fb

    def build(g1, g2, label1, label2, domain):
        sub = paths[paths.group.isin([g1, g2])]
        keys = sorted(sub.path.unique())
        scal, bins = [], []
        for p in keys:
            r = sub[sub.path == p].iloc[0]
            c1, c2 = pair(g1, g2, p, "pct")
            m1, m2 = pair(g1, g2, p, "monotonic_by_hdr_ts")
            cls = r["class"]
            if cls == "bin array":
                z = f"{zero_share(g1, p) if (paths.group == g1).any() and p in set(paths[paths.group == g1].path) else '-'} / {zero_share(g2, p) if p in set(paths[paths.group == g2].path) else '-'}"
                lens = sorted(set(sum([list(x) for x in sub[sub.path == p].list_lengths], [])))
                status = {"verified": "[verified] exact name" + (", length matches" if r["declared_cells"] != "" and lens == [r["declared_cells"]] else ", LENGTH MISMATCH"),
                          "inferred": "[inferred] " + r["match_note"] + (", length matches" if r["declared_cells"] != "" and lens == [r["declared_cells"]] else ""),
                          "unmatched": "unmatched (no definition)"}[r["match_status"]]
                bins.append({"Array path": f"`{p}`", f"% payloads ({label1} / {label2})": f"{c1} / {c2}",
                             "Definition": f"`{r['definition']}`" if r["definition"] else "none", "Match status": status,
                             "Length vs declared": (f"{lens[0] if len(lens) == 1 else lens} vs {r['declared_cells']}" + (f" (sizes {r['declared_sizes']})" if len(r["declared_sizes"]) > 1 else "")) if r["definition"] else f"{lens} vs -",
                             "Bin edges (as declared)": r["edges"] if r["edges"] else "-", "Declared unit (array)": r["declared_array_unit"] or "-",
                             f"All-zero rows ({label1} / {label2})": z, f"Monotonic % serials ({label1} / {label2})": f"{m1} / {m2}"})
            else:
                scal.append({"Path": f"`{p}`", f"% payloads ({label1} / {label2})": f"{c1} / {c2}", "Type": cls,
                             "JSON types": r["json_types"], "Meaning": r["meaning"] or ("container" if cls == "object" else ("record list (event/fault snapshots)" if cls == "record list" else "unknown")),
                             f"Monotonic % serials (decreasing pairs/pairs) ({label1} / {label2})": f"{m1} / {m2}"})
        return pd.DataFrame(scal), pd.DataFrame(bins)

    s, b = build("motor_normal", "motor_rr", "N", "RR", "motor")
    (TBL / "motor_scalars.md").write_text(md_table(s))
    (TBL / "motor_bins.md").write_text(md_table(b))
    s, b = build("battery_normal", "battery_rr_standard", "N", "RR", "battery")
    (TBL / "battery_scalars.md").write_text(md_table(s))
    (TBL / "battery_bins.md").write_text(md_table(b))

    # ---- flat layout (section level)
    flat = groups["battery_rr_flat"]
    norm = lambda k: re.sub(r"(event|fault)\d+", r"\1N", re.sub(r"cell\d+", "cellN", k))
    sections = defaultdict(lambda: {"keys": set(), "labels": [], "present": 0, "types": set()})
    for pl in flat["payload"]:
        seen = set()
        for k, v in pl.items():
            nk = norm(k)
            parent, _, last = nk.rpartition("/")
            sec = sections[parent]
            sec["keys"].add(nk)
            sec["types"].add(type(v).__name__)
            if k.startswith("/USAGE_LOG"):
                if last not in sec["labels"]:
                    sec["labels"].append(last)
            seen.add(parent)
        for p in seen:
            sections[p]["present"] += 1
    rows = []
    for parent, sec in sections.items():
        title = parent.rsplit("/", 1)[-1]
        dname = FLAT_SECTION_TO_DEF.get(title)
        labels = [x for x in sec["labels"] if not re.search(r"(?i)padding|ever.fully|^Active and pulse", x)]
        row = {"Section (collapsed: eventN/faultN/cellN)": f"`{parent}`", "Keys": len(sec["keys"]), "% flat payloads": pct(sec["present"], len(flat)),
               "Value types": "|".join(sorted(sec["types"]))}
        if dname:
            d = DEFS["battery"][dname]
            row["Candidate definition (inferred by section title)"] = f"`{dname}`"
            row["Labels vs declared cells"] = f"{len(labels)} vs {declared_cells(d)}" + ("" if len(labels) == declared_cells(d) else "  **MISMATCH**")
        else:
            row["Candidate definition (inferred by section title)"] = "-"
            row["Labels vs declared cells"] = "-"
        row["First labels"] = "; ".join(sec["labels"][:3]) if sec["labels"] else "; ".join(sorted(sec["keys"])[:3])
        rows.append(row)
    fl = pd.DataFrame(rows)
    (TBL / "battery_flat_sections.md").write_text(md_table(fl))
    fl.to_csv(OUT / "parsing_spec_flat_sections.csv", index=False)

    # ---- labelled layout (section level): usage bins are dicts keyed by text labels
    LAB_TO_DEF = {
        ("dischargeLog", "powerBins"): "powerBins", ("dischargeLog", "operatingBands"): "dischargeBandBins",
        ("dischargeLog", "durationBins"): "dischargeDurationBins", ("dischargeLog", "startTempBins"): "dischargeStartTempBins",
        ("dischargeLog", "offTimeBins"): "dischargeOffTimeBins", ("dischargeLog", "durationBetweenChargesBins"): "dischargeBtwChargesBins",
        ("chargeLog", "chargeTimeWhileInDifferentPhases"): "chargeMaintainTempBins", ("chargeLog", "chargeOperatingBands"): "chargeBandBins",
        ("chargeLog", "chargeDurationBins"): "chargeDurationBins", ("chargeLog", "chargeAmbientTemperatureForPreCustomers"): "chargeAmbientTempPreCustomerBins",
        ("chargeLog", "chargeAmbientTemperatureForCustomers"): "chargeAmbientTempCustomerBins", ("chargeLog", "lowestCellVoltageAtStart"): "minCellVoltAtChargeStartBins",
    }
    lab_df = groups["battery_rr_labelled"]
    lab_rows = []
    for p, info in sorted(inv["battery_rr_labelled"].items()):
        parts = p.split(".")
        if len(parts) == 3 and parts[0] == "usage" and info["types"] == {"dict"}:
            sample = next(iter(lab_df.payload))["usage"][parts[1]][parts[2]]
            labels = [l for l in sample if not re.search(r"(?i)padding|ever.fully", l)]
            dname = LAB_TO_DEF.get((parts[1], parts[2]))
            n_lab = len([l for l in labels if l.startswith("maint")]) if dname == "chargeMaintainTempBins" else len(labels)
            row = {"Section": f"`{p}`", "% labelled payloads": pct(info["present"], len(lab_df)), "Labels": len(labels),
                   "Candidate definition (inferred by section name)": f"`{dname}`" if dname else "-"}
            if dname:
                dc = declared_cells(DEFS["battery"][dname])
                row["Labels vs declared cells"] = f"{n_lab} vs {dc}" + ("" if n_lab == dc else "  **MISMATCH**")
            else:
                row["Labels vs declared cells"] = "-"
            row["First labels"] = "; ".join(labels[:3])
            lab_rows.append(row)
    lab_t = pd.DataFrame(lab_rows)
    (TBL / "battery_labelled_sections.md").write_text(md_table(lab_t))
    lab_t.to_csv(OUT / "parsing_spec_labelled_sections.csv", index=False)

    # ---- definition metadata table
    meta = []
    matched = {(d, x) for d in ("motor", "battery") for x in set(paths[(paths.group.str.startswith(d))].definition) if x}
    for domain, defs in DEFS.items():
        for name, d in defs.items():
            issues = []
            nm = {b["name"] for b in d["bins"]}
            if name.startswith("ddm692_") and nm == {"speed"} and d["bins"][0]["unit"] != "krpm":
                issues.append(f"dimension named 'speed' but unit is {d['bins'][0]['unit']}")
            if name == "ddm692_BarTempBins":
                issues.append("temperature array with unit krpm (likely copy error; correct unit not stated)")
            if name.startswith("ddm692_") and name != "ddm692_SpeedBins" and nm == {"speed"}:
                pass
            for dim, b in zip(d["sizes"], d["bins"]):
                n_part = len(b["partitions"])
                if b["unit"] == "enum" and n_part != dim:
                    issues.append(f"size {dim} but {n_part} enum labels")
                if b["unit"] not in ("enum", "bool") and n_part + 1 != dim:
                    issues.append(f"size {dim} but {n_part} edges (+1 = {n_part + 1})")
            if name == "dischargeBtwChargesBins":
                issues.append("bin dimension named 'off time' although the array is 'between charges'")
            used = (domain, name) in matched
            alias = [k for k, v in ALIASES.items() if v == name]
            meta.append({"Definition": f"`{name}`", "File": DEF_FILE[domain], "Declared size": d["sizes"], "Declared unit": d["unit"],
                         "Used by payloads": "yes, exact" if used and not alias else (f"yes, via inferred alias `{alias[0]}`" if alias else "NO"),
                         "Metadata issues": "; ".join(issues) if issues else "-"})
    (TBL / "definitions.md").write_text(md_table(pd.DataFrame(meta)))

    # ---- derived relationships / consistency checks (verified on the data)
    checks = []
    nm = pd.read_csv(ROOT / "normal_machines" / "Motor_Normal Machines.csv")
    rm = pd.read_csv(ROOT / "return_repair_machines" / "Motor_Return:Repair Machines.csv")
    js = lambda df: df["decoded_data"].map(json.loads)
    nd, rd = js(nm), js(rm)
    u = lambda d: d.map(lambda x: x["ddmUsage"])
    nu, ru = u(nd), u(rd)
    bsum = lambda uu, k: uu.map(lambda x: sum(x[k]["bins"]))
    add = lambda c, t, r: checks.append({"check": c, "result": t, "rows": r})
    add("Normal `cumulative_usage_duration_seconds` == sum(ddm692_PowerBins.bins)", f"{(bsum(nu, 'ddm692_PowerBins') == nm.cumulative_usage_duration_seconds).mean():.1%}", len(nm))
    add("Normal `cumulative_usage_duration_seconds` == sum(ddm692_SpeedBins.bins)", f"{(bsum(nu, 'ddm692_SpeedBins') == nm.cumulative_usage_duration_seconds).mean():.1%}", len(nm))
    add("Normal `write_count` == header.writeCount", f"{(nm.write_count == nd.map(lambda x: x['header']['writeCount'])).mean():.1%}", len(nm))
    add("Normal `ambient_pressure_pa` == ddmUsage.ambientPressure_Pa", f"{(nm.ambient_pressure_pa == nu.map(lambda x: x['ambientPressure_Pa'])).mean():.1%}", len(nm))
    add("Normal `ambient_temperature_mC` == ddmUsage.ambientTemperature_mC", f"{(nm.ambient_temperature_mC == nu.map(lambda x: x['ambientTemperature_mC'])).mean():.1%}", len(nm))
    add("RR `log_size` == header.dataSize", f"{(rm.log_size == rd.map(lambda x: x['header']['dataSize'])).mean():.1%}", len(rm))
    for label, uu in (("Normal", nu), ("RR", ru)):
        add(f"{label}: ddm692_NormSpeedBins.bins all zero", f"{(bsum(uu, 'ddm692_NormSpeedBins') == 0).mean():.1%}", len(uu))
        add(f"{label}: ddm692_ExhaustTempBins bins 8-10 all zero", f"{(uu.map(lambda x: sum(x['ddm692_ExhaustTempBins']['bins'][7:])) == 0).mean():.1%}", len(uu))
        ok = uu.map(lambda x: all(x[k]["tableSize"] == len(x[k]["bins"]) for k in x if isinstance(x[k], dict) and "bins" in x[k]))
        add(f"{label}: tableSize == len(bins) for every bin container", f"{ok.mean():.1%}", len(uu))
        edges = DEFS["motor"]["ddm692_PressBins"]["bins"][0]["partitions"]
        kpa = uu.map(lambda x: x["ambientPressure_Pa"] / 1000)
        pb = uu.map(lambda x: x["ddm692_PressureBins"]["bins"])
        idx = kpa.map(lambda a: int(np.searchsorted(edges, a, side="right")))
        add(f"{label}: ambient kPa falls in a non-empty ddm692_PressureBins bin (supports inferred Pressure~Press alias; weak)", f"{np.mean([b[i] > 0 for b, i in zip(pb, idx)]):.1%}", len(uu))
        add(f"{label}: ambient kPa falls in the modal ddm692_PressureBins bin", f"{np.mean([int(np.argmax(b)) == i for b, i in zip(pb, idx) if sum(b) > 0]):.1%}", len(uu))
    pd.DataFrame(checks).to_csv(OUT / "spec_checks.csv", index=False)
    (TBL / "checks.md").write_text(md_table(pd.DataFrame(checks)))

    # ---- battery variants by root-key signature (+ model per serial from the sessions files)
    sess = pd.concat([pd.read_csv(ROOT / "normal_machines" / "Clean Sessions_Normal Machines.csv", usecols=["anonymized_serial", "model"]),
                      pd.read_csv(ROOT / "return_repair_machines" / "Clean Sessions_Return:Repair Machines.csv", usecols=["anonymized_serial", "model"])])
    models = sess.dropna().groupby("anonymized_serial").model.agg(lambda x: "/".join(sorted(set(x))))
    var_rows = []
    for g in ("battery_normal", "battery_rr_standard", "battery_rr_labelled", "battery_rr_flat"):
        df = groups[g]
        if g == "battery_rr_flat":
            sig = df.payload.map(lambda p: "flat /SECTION/... keys")
            cells = df.payload.map(lambda p: str(sum(1 for k in p if re.fullmatch(r"/EVENT_LOGS/event0/volt/cell\d+", k))))
        else:
            sig = df.payload.map(lambda p: "root keys: " + ", ".join(sorted(p.keys())))
            cells = df.payload.map(lambda p: "/".join(str(x) for x in sorted({len(e["cellVolt"]) for e in p["eventLog"]["events"] if e["cellVolt"]})))
        tmp = df.assign(sig=sig, cells=cells, model=df.anonymized_serial.map(models).fillna("not in sessions"))
        for (sg, ce), x in tmp.groupby(["sig", "cells"]):
            var_rows.append({"Group": g, "Root-key signature": sg, "Cell-voltage array lengths": ce, "Payload rows": len(x), "Serials": x.anonymized_serial.nunique(),
                             "hdr_timestamp range": f"{x.hdr_timestamp.min():%Y-%m-%d} to {x.hdr_timestamp.max():%Y-%m-%d}",
                             "Models (from sessions)": ", ".join(sorted(set(x.model)))[:80]})
    (TBL / "battery_variants.md").write_text(md_table(pd.DataFrame(var_rows)))

    # ---- group overview
    ov = []
    for g, df in groups.items():
        ov.append({"Group": g, "Non-empty payload rows": len(df), "Serials": df.anonymized_serial.nunique(),
                   "hdr_timestamp range": f"{df.hdr_timestamp.min():%Y-%m-%d} to {df.hdr_timestamp.max():%Y-%m-%d}",
                   "Distinct JSON paths": len(inv[g]) - 1 if g != "battery_rr_flat" else len(set(norm(k) for pl in df.payload for k in pl))})
    (TBL / "overview.md").write_text(md_table(pd.DataFrame(ov)))
    # ---- cumulative-check summaries (from cumulative_check.csv / cumulative_gaps.csv)
    cc = pd.read_csv(OUT / "cumulative_check.csv")
    summ = []
    for g, x in cc.groupby("group", sort=False):
        nonconst = x[~x.constant_everywhere]
        summ.append({"Group": g, "Numeric paths checked": len(x), "Constant in all rows": int(x.constant_everywhere.sum()),
                     "Non-constant, 100% serials monotonic": int((nonconst.pct_serials_monotonic == 100).sum()),
                     "Non-constant, <100% monotonic": int((nonconst.pct_serials_monotonic < 100).sum()),
                     "Bin arrays: median % serials monotonic": f"{x[x.kind == 'array'].pct_serials_monotonic.median():g}%" if (x.kind == "array").any() else "-"})
    (TBL / "cumulative_summary.md").write_text(md_table(pd.DataFrame(summ)))
    sel = ["header.writeCount", "ddmUsage.ddm692_SpeedBins.bins", "ddmUsage.ddm692_PowerBins.bins", "ddmUsage.ddm692_ExhaustTempBins.bins",
           "ddmUsage.ddmOnButNotRunTime_s", "ddmUsage.filterWashCounter", "usage.dischargeLog.sigDischarges.allTime", "usage.chargeLog.chargerInsertions.allTime",
           "usage.dischargeLog.powerBins", "usage.dischargeLog.dischargeDurationBins", "usage.chargeLog.chargeDurationBins", "header.power_ups"]
    gcols = ["motor_normal", "motor_rr", "battery_normal_4cell", "battery_normal_7cell", "battery_rr_standard"]
    rows = []
    for path in sel:
        r = {"Path": f"`{path}`"}
        for g in gcols:
            m = cc[(cc.group == g) & (cc.path == path)]
            r[g] = "-" if m.empty else (f"{m.iloc[0].pct_serials_monotonic:g}% ({int(m.iloc[0].pairs_with_decrease)}/{int(m.iloc[0].consecutive_pairs)})" if not pd.isna(m.iloc[0].pct_serials_monotonic) else "<2 obs")
        rows.append(r)
    (TBL / "cumulative_selected.md").write_text(md_table(pd.DataFrame(rows)))
    gp = pd.read_csv(OUT / "cumulative_gaps.csv")
    (TBL / "cumulative_gaps.md").write_text(md_table(gp[["group", "payload_rows", "rows_after_identical_payload_dedup", "serials", "serials_ge2_obs", "median_obs_per_serial",
                                                        "gap_days_p10", "gap_days_median", "gap_days_p90", "pct_gaps_6_to_8_days"]]))
    print("done; tables in", TBL)


if __name__ == "__main__":
    main()
