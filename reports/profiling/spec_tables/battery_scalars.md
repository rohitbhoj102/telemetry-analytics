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
