# Fuel measurement

Optional cumulative consumed mass counters (not remaining hopper mass) support g, kg, t and lb. The configured fuel mass unit must match fuel price quantity, calorific value and consumption rates. Useful heat is mass times calorific value times efficiency.

Alternatively, configure an operating-state entity, a separate level entity, actual heating and off states, and a multiline table such as `1=0.8` and `2=1.2` in fuel units per hour. These are illustrative values only. Unknown levels invalidate intervals; a constant rate is not silently substituted if a level table is configured. Use the actual recorded state strings. No appliance settings are changed.

The historical diagnostic prioritizes usable measured mass, measured heat energy/power, then runtime estimates. Runtime estimates assume constant consumption within each level and omit startup/transient variation unless explicitly represented by the mapped states. No data reconstruction is possible without recorded states or measurements. Coverage is not accuracy. Live Home Assistant runtime validation is pending.
