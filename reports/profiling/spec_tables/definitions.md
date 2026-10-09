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
