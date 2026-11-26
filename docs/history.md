# Historical calibration pipeline

The pure history adapter aligns timestamped temperatures and energy counters on configurable intervals, preserves valid zero Celsius readings and rejects missing, stale and decreasing counter samples. Fuel counters must represent useful heat; raw pellet mass requires conversion and a stove state/power model. Heat pump counters represent electricity; resistance counters represent useful heat.

This is the first adapter layer, not yet a live Recorder integration. Next: obtain state history via supported Home Assistant Recorder APIs in its executor, convert units, map generator-specific energy semantics, configure sampling limits and persist diagnostic estimates. Do not fit a model when a known heat source lacks usable energy history. Constant COP and unmeasured heat gains limit identifiability. No learned value should overwrite manual configuration without explicit user choice.
