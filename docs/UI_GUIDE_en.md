In results, select a date range and a day/month/year interval. Monthly and yearly values sum the selected days only. The layer table follows the dates; totals and downloads retain all simulated days.

### Edit the profile

Click any table cell to select its layer; the blue row is the active layer. Move, delete or edit it below. Import rainfall through CSV/Excel or paste CSV, then check column mapping, units and the preview.

“Calculation methods and vegetation” offers optional CN, Modified Penman, steady drainage and Giroud contact modules. The legacy descriptions below apply to the original compatible modes. Full equation-level scope is described in `docs/V22_METHODS.md`.

Add a layer of the required type, then select it to move, delete or edit it. Every layer has independent parameters. Changing the type resets that layer’s parameters. Click “Save layer parameters” before running. Global settings must also be saved.

Use “Langue” to switch languages without changing the saved profile. Start_UI_ZH.cmd, Start_UI_FR.cmd and Start_UI_EN.cmd select the initial language.

The table lists layers from top to bottom. Reordering preserves IDs; deleting the recirculation target disables recirculation. JSON import and export are in the sidebar. JSON and CSV keys are identical across all languages so files remain interchangeable.

### Parameters and units

Thickness: mm. Conductivity: mm/day. Drainage distance: m. Porosity, field capacity, wilting point and initial water content: volume fractions from 0 to 1. Required ordering: wilting point < field capacity < porosity. Membranes do not store water, so their water-content parameters are not applicable.

Weather CSV must contain date,precip_mm,temp_c,pet_mm with consecutive daily dates. Potential evapotranspiration is supplied by the user. Included synthetic weather is for demonstration only.

### Read the results

Values in mm are water depth over the whole site area. On one hectare, 1 mm equals 10 m³. Use layer IDs to distinguish cover drainage, leachate collection and leak detection.

bottom_leakage is outflow crossing the bottom of the profile; without a bottom liner it represents free drainage. liner_leakage is an alias for the same result: do not add the two. Flow through an intermediate membrane is an internal transfer, not an additional system outlet.

Recirculation is injected the next day. Pending water remains part of storage. Water rejected by a full target layer is counted as surface outflow. The daily balance includes porous storage, snow and pending recirculation.

### Methods and limitations

This independent program uses approximations: fixed CN, degree-day snowmelt, water-limited evapotranspiration, local head estimates, Darcy-type drainage and an empirical membrane leakage gate. It does not reproduce every EPA HELP equation and has not been validated against official HELP results or field measurements. Closing the water balance does not establish prediction accuracy.

Frozen soil, vegetation growth, membrane defects and membrane-soil contact are not simulated. Free layer ordering does not guarantee physical suitability or compliance with EPA HELP layer rules. Results also depend on substeps and layer discretization. See README_en.md and TECHNICAL_NOTES.md for details.
