# Smart Heating Energy Manager

Experimental Home Assistant integration for comparing heating costs and estimating building heat demand. Advisory only: never switches appliances.

License: GPL-3.0-only.

Development roadmap: configurable energy price sources, thermal model, historical calibration, forecasting, and supervised control.

## Dedicated panel

After integration setup, Smart Heating appears in the Home Assistant sidebar at `/smart-heating-energy-manager`. It shows live temperatures, estimated heat demand, electricity price, recommended generator, generator comparison and calibration diagnostics, using registry-resolved entities. The interface follows Home Assistant theme and supports Italian and English. Hide it via integration Options → Display. No external cards are required. The panel is advisory only and never operates appliances. Zones, PV/battery and historical graphs are not yet implemented. Runtime verification on Home Assistant is pending.
