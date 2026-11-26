# Thermal calibration (experimental core)

The interval model estimates heat loss H, effective thermal capacity C and heat-pump COP simultaneously. Input energies must be integrated over the same interval; stove energy must be useful thermal energy, not fuel mass. Resistance energy includes bathroom heating. Heat-pump energy is electrical input. Temperatures are Celsius; zero is a valid observation.

The solver requires at least 24 usable intervals, rejects poorly conditioned systems and physically implausible coefficients, and reports residual RMSE. These checks are not a statistical confidence interval. Unmeasured solar/internal gains, changing COP, sensor placement and thermal stratification can bias estimates.

Example synthetic test parameters: H=158.5 W/K, C=4 kWh/K (illustrative only), COP=3.75. These are not universal defaults or validated building measurements.

Next: connect Recorder history and energy counters, identify gaps and resets, validate on held-out days, and expose diagnostics before enabling any adaptive control.
