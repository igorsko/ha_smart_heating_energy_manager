# Installation-independent configuration

The generator registry core accepts zero or more heat pumps, electric resistance devices, and fuel-based devices. Fuel price is per user-defined quantity, with energy per unit and efficiency. All monetary inputs must use the same currency. It ranks single generators capable of meeting estimated demand; combined dispatch is not implemented.

The calibration settings object supports validated bounds and sample thresholds. These are Python-level interfaces, not yet Home Assistant UI options. Existing config entries remain compatible; no migration has been performed.

Next: dynamic generator and zone configuration UI, options flow, currency-aware price sensor mapping, historical calibration adapter, multi-source dispatch, runtime tests.
