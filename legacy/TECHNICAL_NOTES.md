# Technical notes / 算法说明

## 1. Reference implementation basis

The official HELP V4.0.1 is an EPA quasi-2D model. This MVP is a separately written Python hydrologic water budget. The EPA 1994 v3 engineering documentation describes calculations; this prototype uses **some** related conceptual relationships but it does not claim official numeric equivalence.

## 2. Time sequence

For each day and `n` equal intraday substeps:

1. Classify precipitation as rainfall or snow based on daily mean temperature; update snow water equivalent (SWE).
2. Remove a bounded fraction of daily PET as snow sublimation; degree-day melt is drawn from SWE.
3. Split liquid input into direct runoff and potential infiltration using the fixed SCS curve number.
4. Inject previous day's recirculated flow to a chosen layer; return any excess above pore-space capacity upward to surface runoff.
5. For each substep, add a fraction of daily infiltrating liquid to the cover soil; extract root-zone moisture up to the wilting point; route any water exceeding field capacity down through the porous layers, capped by conductivity and underlying pore-space capacity.
6. In the bottom layer, split removable gravity water between lateral drainage and basal leakage by their calculated potential rates. Preserve mass when fluxes compete.
7. Remove the non-recirculated fraction from the landfill; store the remaining fraction for reinjection tomorrow. Verify daily balance.

## 3. Equations and units

Everything except dates and air temperature is stored as **mm water equivalent per site area**. Soil layers use `theta = water_depth_mm / thickness_mm`.

**SCS runoff:** `S = 25400/CN - 254` (mm), `Ia=0.2S`, then `Q = (P - Ia)^2 / (P + 0.8S)` when `P > Ia`, else zero.

**Unsaturated conductivity surrogate:**

`Se = clamp((theta - theta_wilt)/(theta_sat - theta_wilt), 0, 1)`

`K(theta) = Ks * Se^(3+2/lambda)`

This uses a common Campbell-like exponent. **HELP infers pore-index and residual water from retention data** and iteratively solves segment flux. This version assumes `theta_r ≈ theta_wilt`, a material simplification.

**Vertical step flux:** `q = min(water_above_FC, K(theta)*dt, next_layer_Ks*dt, receiving_pore_capacity)`.

**Bottom layer hydraulic head surrogate:** `h = min(T, max(0, storage - FC*T)/(porosity - FC))`. This intentionally bounds head by the modeled bottom layer thickness and does not resolve the upstream saturated layer stack.

**Basal liner:** `q_liner = K_liner * (1 + h/T_liner) * multiplier`, if `h>0`; otherwise 0. The `multiplier` is a user-selected heuristic. No actual Giroud defect geometry, membrane diffusion or clay/membrane interface resistance is simulated.

**Lateral drainage:** `q_lateral = K_lat*(h/L)*(slope + h/L)` when bottom layer has `kind=drain`. This matches dimensional behavior of a simplified Darcy gradient calculation but is **not** the original HELP Boussinesq/Dupuit closed form or iterative coupling.

**Water balance:** `R = Storage_before + Precipitation - (Storage_after + Runoff + ET + Collected + Leakage)` where Storage includes soil, SWE and recirculation awaiting next-day application. `|R|` should remain near floating point round-off.

## 4. Limitations especially relevant to Canadian landfills

- A crude degree-day snow model cannot reproduce HELP's SNOW-17; **frozen soils, frost depth, rain-on-snow heat balance, vegetation and variable CN are omitted**. Predictions for Ontario winters are especially preliminary.
- No capillary rise, 2D spatial discretization, underdrain backwater, high-head correction beyond drain thickness, defects in HDPE liner, composite liner flow/contact quality, or leachate temperature effects.
- Fixed daily PET misses actual radiation, wind, vapor pressure and seasonal canopy dynamics.
- No field calibration: conductivity and retention vary by waste/cover age, compaction, channels and moisture.
- This is **not** a contaminant transport, landfill gas, landfill settlement or PFAS fate model.
- For a landfill with multiple liner systems, the sequence of liners and drain layers must be modeled explicitly; this prototype has only one basal liner and can only laterally drain the bottom layer.

## 5. Plan to improve parity (recommended order)

1. Run a set of official HELP 4.0.1 baseline projects to collect daily weather, percolation, runoff, ET, drainage, and liner leakage reference curves.
2. Reproduce moisture-dependent CN adjustments, surface storage and the full temperature-sensitive snow/frozen-soil system.
3. Implement original water retention parameter inference, segment subdivision and iterative nonlinear storage routing with variable timestep.
4. Replace simplified PET/root ET with modified Penman, Ritchie evaporation, vegetation growth and interception.
5. Implement exact Boussinesq lateral drainage and coupled layer-head/leakage iterations for lined profiles.
6. Add soil/geomembrane/composite liner types (defects, interface contact, installation condition, polymer diffusivity), multiliner subprofiles and recirculation.
7. Regression-test each climate regime and layer design against official daily series, report deviations and uncertainty ranges. Use local field data to calibrate if needed.

For a true source-code migration, the official v3 FORTRAN program was described as available via NTIS (1994 engineering documentation, program identification). An original codebase would need separate acquisition/license assessment; none of that code has been copied here.
