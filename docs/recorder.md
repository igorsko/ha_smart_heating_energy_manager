# Recorder calibration (experimental)

An optional read-only calibration diagnostic uses recorded temperature states and cumulative energy counters. Each registered heat source must have its own counter; shared meters and missing mappings are rejected to avoid double counting. A fuel generator must explicitly confirm that its energy counter is useful thermal energy. Resistance input is multiplied by configured efficiency. Heat-pump counters are electrical energy; fitted COP is aggregate, not per device.

History duration, interval and maximum sample age are configurable. Raw state history may be shorter than the selected duration because of Recorder retention. A valid zero temperature is retained. Missing readings and counter resets are rejected by the history adapter. Estimates are diagnostic only and never replace manual settings. Constant COP and omitted internal/solar gains are limitations. Pure heat-pump-only or fuel-only installations may not identify all three parameters jointly.

Power sensors and pellet mass/runtime conversion remain future work. No device control or forecast is implemented. Recorder API and config flow require runtime verification on supported Home Assistant versions.
