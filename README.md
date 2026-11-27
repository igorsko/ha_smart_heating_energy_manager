# Smart Heating Energy Manager

Experimental Home Assistant integration for comparing heating costs and estimating building heat demand. Advisory only: never switches appliances.

License: GPL-3.0-only.

Development roadmap: configurable energy price sources, thermal model, historical calibration, forecasting, and supervised control.

## Dedicated panel

After integration setup, Smart Heating appears in the Home Assistant sidebar at `/smart-heating-energy-manager`. It shows live temperatures, estimated heat demand, electricity price, recommended generator, generator comparison and calibration diagnostics, using registry-resolved entities. The interface follows Home Assistant theme and supports Italian and English. Hide it via integration Options → Display. No external cards are required. The panel is advisory only and never operates appliances. Area discovery and editable thermometer/heating-source mappings are available. Per-zone calibration, PV/battery and historical graphs remain pending. Runtime verification on Home Assistant is pending.

## Area-first setup

Initial setup requires no parameters. The panel discovers Home Assistant areas and proposes temperature sensors and heating-capable climate entities, respecting entity-level area assignments before device-level assignments. Open integration Options → Heating zones to confirm or change each area's thermometer and heating sources. Shared heating sources can be assigned to multiple areas. Switches and scripts can be selected manually. These mappings are advisory and do not automatically create calibrated generator models. Missing prices and heat loss remain unknown, not zero. Building-level historical calibration still requires a reference indoor/outdoor sensor and configured energy sources; automatic per-zone learning is not yet implemented.

## Electrical calibration sources (0.3.10)

Onecta heating-only cumulative counters are discovered across device records only within the same integration entry and appliance prefix. Explicit meter mappings take precedence. Vertigo heating-enable switches are thermostat requests, not measured element runtime; use a dedicated electrical power or energy sensor for calibration. No nominal wattage is assumed. Missing inputs remain unknown. / I contatori Daikin vengono individuati automaticamente; per Vertigo usare un misuratore elettrico dedicato. Lo stato di abilitazione del riscaldamento non misura il consumo.

### Thermal holdout diagnostics

Calibration reports chronological out-of-sample one-step temperature MAE, RMSE, bias and persistence baseline MAE using historical measured inputs. At least 24 training and 12 valid holdout intervals are required. This diagnostic is not a live forecast validation or permission for automatic control. / La diagnostica confronta temperature ricostruite su dati storici esclusi dall'apprendimento; non abilita il controllo automatico.

In 0.3.11 the panel displays historical validation errors and the persistence baseline, and heat-pump status distinguishes selected HVAC mode from reported activity. These are advisory diagnostics, not measured live forecast accuracy. / La plancia mostra gli errori di validazione storica e distingue la modalità Daikin dall'attività effettivamente comunicata.

### Provisional historical quality gate

Learned parameters remain stored for diagnostics but are used through effective_loss only after opt-in and historical holdout validation: at least 24 training and 12 validation samples, MAE <= 0.50 °C, RMSE <= 0.75 °C, absolute bias <= 0.30 °C and MAE strictly below the persistence baseline. Older records without validation fall back to the manual or initial model. Thresholds are provisional, not proof of live forecast accuracy. / I parametri appresi vengono utilizzati solo dopo la verifica storica e il consenso configurato; i limiti sono provvisori.

### Partial calibration and meter discovery (0.3.12)

Vendor heating-period counters can be recognized even when their state class is measurement or absent, subject to appliance identity and explicit counter naming. Candidate units and state classes are exposed in diagnostics. Unmetered electric heating sources contribute zero only during recorded, freshness-limited explicit OFF intervals; enabled or unknown states invalidate the interval. Fuel sources are not inferred off this way. No actuator commands. / La calibrazione usa soltanto intervalli completi; i generatori elettrici senza misura possono contribuire zero solo durante intervalli di spegnimento documentato.

### Interval-level history selection (0.3.13)

Global per-source coverage is diagnostic rather than an exclusion threshold. Each generator uses one valid source per interval, with alternate heating-only Daikin counters and confirmed-off fallback. Missing or stale values and counter resets remain invalid. Complete joint intervals and model quality gates still apply. / La copertura viene valutata per intervallo senza sommare contatori sovrapposti; i dati mancanti non diventano zero.

### Stable Recorder states

Calibration requests the initial historical state from Recorder. Explicit OFF observations may bridge an unchanged period only when bounded by recorded OFF evidence, with no intervening unknown or active state. This assumes Recorder captured transitions; it cannot prove continuity across an unrecorded outage. Live state alone is not used to extend historical coverage. Numeric energy and temperature freshness limits remain unchanged. / Gli stati OFF invariati possono essere utilizzati tra osservazioni storiche coerenti; non si estende lo storico usando il solo stato attuale.

### Generator readiness (0.3.14)

Distinguish incomplete technical parameters from insufficient confirmed capacity. Onboarding placeholder ratings are not real equipment ratings. Economic comparison can remain provisional even when capacity-based recommendations are unavailable. / La plancia distingue parametri mancanti e potenza insufficiente, senza attribuire potenze nominali arbitrarie.

### Declared thermal capacity (0.3.15)

Explicit rated useful heating output from the selected device can enable provisional advisory recommendations and forecasts. Confirmed manual ratings take precedence. Generic electrical power, other devices and conflicting ratings are excluded. Nominal output is not measured available heat at the current outdoor temperature; incomplete efficiency inputs remain estimates. / La potenza termica nominale dichiarata viene distinta dalla potenza elettrica assorbita; le raccomandazioni restano consultive e provvisorie.

### Live heat pump input (0.3.16)

Explicit electrical input power sensors are discovered independently of nominal thermal capacity. The dashboard shows instantaneous electrical input, the configured or assumed COP, and estimated useful heat only when heating action is confirmed. Missing or stale power stays unknown; COP is not measured. / La plancia mostra assorbimento elettrico, COP utilizzato e potenza termica stimata quando l’erogazione è confermata.

### Generator configuration (0.3.17)

The advanced form uses the same calibration resolver as live monitoring. Automatic entity suggestions remain dynamic unless overridden; clear manual mappings to return to discovery. Alternative counters are shown. Technical estimates require explicit confirmation before becoming configured ratings. Duplicate name and room thermometer controls are removed from advanced generator options; room thermometers belong to zones. Vertigo heating request is not confirmed runtime. / Le associazioni automatiche sono precompilate; i parametri tecnici richiedono conferma esplicita.

### Generator hourly telemetry (0.3.18)

When an instantaneous electrical input sensor is missing, recent Recorder counter observations can provide a mean electrical power over a bounded 30–120 minute interval. Reset, stale, unchanged or invalid counters are rejected. The displayed hourly cost uses the current tariff, not a historical bill. Pellet rate, hourly fuel cost and estimated heat are shown only with explicit burning-state evidence; auxiliary electricity is excluded. / La potenza media ricavata dai contatori non è una misura istantanea. Il consumo di pellet e il costo orario sono distinti dal costo per kWh termico.
