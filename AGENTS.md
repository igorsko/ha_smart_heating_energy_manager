# Architecture requirements

All installation-specific values MUST be configurable via Home Assistant UI, with options editable after setup. Never use the developer's home as universal defaults. Example configurations are clearly labelled.

- Support arbitrary numbers of zones, sensors and heat generators; no hardcoded entity IDs, vendors, fuel type, geography, currency or tariff.
- Optional capabilities: biomass, heat pump, resistance, other heat sources, PV, battery, price index. Missing capabilities must not block setup.
- Every physical and economic assumption has explicit units, validation and provenance (manual, measured, estimated or default).
- Distinguish user settings from learned values; permit locking, resetting and reviewing learned parameters. Never silently replace a manual setting.
- Expose calibration interval, minimum samples, acceptable temperature range, sensor anomaly rules, residual and conditioning thresholds, and parameter bounds as advanced settings with safe validated defaults. Zero Celsius is legitimate; do not globally discard it.
- Configurable per-generator operating constraints, comfort targets, schedules, fuel price, fuel mass, calorific value, efficiencies, COP curves, capacities and energy sensors.
- Configurable price source and contract interval, freshness, units, currency consistency, spread, grid losses, variable charges, taxes, and fixed-price fallback. Never assume PUN applies to all contracts.
- All optional device controls require explicit opt-in; advisory is default. Preserve local manufacturer safety logic and manual overrides.
- Tests must include heterogeneous installations (heat-pump only, biomass only, mixed sources, no PV, multiple zones, missing sensors and non-Italian tariff).
- Changes must include configuration migration and tests when applicable. No real household data in public fixtures.
- Physical conversion constants and mathematical invariants are not user settings. Safe manufacturer constraints must not be bypassed.

Current implementation is an initial advisory prototype: multi-generator setup, options flow, configurable calibration thresholds and history integration remain outstanding. This file defines acceptance criteria, not claims of implemented functionality.
