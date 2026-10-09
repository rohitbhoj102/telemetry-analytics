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
