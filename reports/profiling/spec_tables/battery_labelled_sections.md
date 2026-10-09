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
