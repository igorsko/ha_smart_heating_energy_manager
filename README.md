# Smart Heating Energy Manager

Experimental Home Assistant integration for comparing heating costs and estimating building heat demand. Advisory only: never switches appliances.

License: GPL-3.0-only.

Development roadmap: configurable energy price sources, thermal model, historical calibration, forecasting, and supervised control.

## Dedicated panel

After integration setup, Smart Heating appears in the Home Assistant sidebar at `/smart-heating-energy-manager`. It shows live temperatures, estimated heat demand, electricity price, recommended generator, generator comparison and calibration diagnostics, using registry-resolved entities. The interface follows Home Assistant theme and supports Italian and English. Hide it via integration Options → Display. No external cards are required. The panel is advisory only and never operates appliances. Area discovery and editable thermometer/heating-source mappings are available. Per-zone calibration, PV/battery and historical graphs remain pending. Runtime verification on Home Assistant is pending.

## Area-first setup

Initial setup requires no parameters. The panel discovers Home Assistant areas and proposes temperature sensors and heating-capable climate entities, respecting entity-level area assignments before device-level assignments. Open integration Options → Heating zones to confirm or change each area's thermometer and heating sources. Shared heating sources can be assigned to multiple areas. Switches and scripts can be selected manually. These mappings are advisory and do not automatically create calibrated generator models. Missing prices and heat loss remain unknown, not zero. Building-level historical calibration still requires a reference indoor/outdoor sensor and configured energy sources; automatic per-zone learning is not yet implemented.
