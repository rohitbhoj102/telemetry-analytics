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
