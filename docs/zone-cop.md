# Zone thermal model and COP curves

Optional per-zone desired temperature and manually supplied heat-loss coefficient (W/K) are editable separately from basic zone mappings. Estimated steady-state heat loss is H times positive indoor-outdoor temperature difference; this is not recovery power and does not account for inter-zone heat transfer. Missing H is unknown. Zone estimates do not replace or sum into the whole-house model, avoiding double counting. No automatic per-zone identification yet.

For each heat pump an optional user/manufacturer COP curve accepts lines `outdoor Celsius=COP`. Linear interpolation inside the configured range adjusts marginal thermal cost. Outside the range or without outdoor temperature, use the manually configured COP; no extrapolation. These are configured estimates, not measured dynamic COP. Calibration still identifies only aggregate COP. Existing zone mappings and manual COP remain unchanged unless edited. No appliance commands.
