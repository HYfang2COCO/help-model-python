# v2.2 Features and Equation-Level Checks

## Selecting and editing layers

Click any cell in the layer table to select that layer; the entire row is highlighted in blue. Move up, move down, delete, and the parameter editor below the table all act on the selected layer. After reordering, selection follows the layer's stable ID rather than treating the same row number as the original layer. A drop-down selector provides an additional option for keyboard navigation.

## Importing precipitation data

The **Run and results** view supports CSV, TSV, and XLSX files, as well as pasted CSV text. The first row must contain column names; for Excel files, the worksheet can be selected. Users can map Chinese, English, or French column names, choose the date format and precipitation units (mm, cm, or inches), and preview the normalized daily data. Missing days, duplicate dates, negative precipitation, missing values, and non-finite values are rejected. The importer does not automatically fill missing days or treat monthly or hourly values as daily values.

When only dates and precipitation are available, users must review and set constants for the missing daily air temperature and daily potential evapotranspiration (PET). These are explicit scenario assumptions, not observations inferred from precipitation. **Modified Penman** requires solar radiation (MJ/m²/day), relative humidity (0–100%), wind speed at 2 m (m/s), and air temperature. The constant PET setting and the PET input column are not used to calculate PET in this mode.

The results package includes `input_provenance.json`, which records column mappings, units, and any constants used. Normalized weather data are saved in `weather.csv`. After the weather inputs or profile change, the previous results are marked as requiring a new simulation.

## Scope of equation-level implementation

Source documentation: [HELP v3 Engineering Documentation hosted by USACE](https://dots.el.erdc.dren.mil/elmodels/pdf/help3doc.pdf), EPA/600/R-94/168b, with additional cross-checks against the [EPA HELP 4 User Manual](https://www.epa.gov/land-research/help-40-user-manual). Page references use the documents' printed page numbers.

| Component | Optional calculation in v2.2 | Parts not fully reproduced |
|---|---|---|
| Runoff | Three options: enter CN-II directly; enter CN-II and apply a slope adjustment; or derive CN from vegetation class and IR, then apply the slope adjustment. Daily moisture adjustments use Equations 26–32 and 34, followed by the SCS runoff equation. | No prediction of frozen-soil conditions. IR is supplied by the user; a complete database of the official default materials has not been implemented. |
| PET | Modified Penman Equations 47 and 54–63, including radiation and aerodynamic terms. Units are converted from MJ/m² to langleys and from m/s to km/h; output is in mm/day. | Daily relative humidity and wind replace the official quarterly/annual averages. Numerical bounds are applied to polar conditions and the radiation/cloud-cover ratio. Full snow energy exchange is not implemented. |
| Actual ET | The existing root-zone method, or separate evaporation and transpiration components partitioned using seasonal LAI; both are limited by available water storage. | LAI follows a half-sine curve over the user-defined growing season. Partitioning uses `exp(-0.5LAI)`; this is not the complete Ritchie/HELP vegetation and two-stage evaporation model. |
| Unsaturated vertical flow | Retains the Brooks–Corey/Campbell form of `K(theta)` and transfers between layers with finite storage capacity. | The wilting point (WP) remains a proxy for residual water content. The official estimation of residual water content and pore-size index, and the complete piecewise nonlinear solution, are not reproduced. |
| Lateral drainage | Adds HELP Equations 178 and 180, solved numerically for the flow rate. Horizontal layers use the limiting form in Equation 179. | `h` remains the equivalent saturated depth within the current layer. Multilayer saturated-zone weighting and the complete coupled head–leakage iteration are not implemented. |
| Barrier soil | A saturated Darcy-type flow rate, limited by capacity and the amount of drainable water. | Still uses a local-head storage bucket, rather than a complete confined hydraulic-head field. |
| Geomembrane | Giroud wetted-radius Equations 162 and 165 for good/poor contact, combined with Equations 151 and 152. Inputs include densities and areas of pinholes and installation defects. | Applies only when the membrane is directly above a low-permeability barrier layer. All six design cases, free flow through holes, geotextile contact, and the complete vapor-diffusion module are not implemented. |

The overall program remains an independent solver. Checking and implementing an individual equation does not establish equivalence of the entire model to EPA HELP. Empirical defect-leakage formulas must not be described as precise measurements of actual leakage. No comparison against official daily benchmark outputs has been completed.

## Numerical and parameter details

### Curve Number and surface conditions

The original fixed-CN mode is retained so that earlier configurations can be rerun. In the three new modes, the input CN refers to antecedent moisture condition II (AMC-II). The daily CN is calculated by projecting water storage from the existing homogeneous layers onto seven depth intervals. Their boundary fractions are `1/36, 1/6, 1/3, 1/2, 2/3, 5/6, 1`; weights follow Equation 29 and are normalized. This projection does not introduce hidden moisture states. The evaporation zone ends at the first geomembrane or barrier layer.

In slope Equation 34, length is normalized to 500 ft and slope to 0.04. The original regression data covered slopes of 0.04–0.5 and slope lengths of 50–500 ft. Values outside those ranges are extrapolations and require separate assessment. Vegetation Equation 32 uses the coefficients in Table 7. **IR is not Ks** and is not generated automatically from hydraulic conductivity; example IR values are illustrative inputs. Numerical CN values are bounded between 0.01 and 99.99, although the daily CN can reach 100 at full saturation.

### PET and actual ET

Penman parameters and imported weather inputs are recorded. On precipitation days, RH is set to 1, following the source documentation. Radiation, humidity, and wind data must be supplied; selecting the method does not generate them from precipitation. All values in the supplied [`weather_energy_synthetic.csv`](../examples/weather_energy_synthetic.csv) are synthetic demonstration data.

Seasonal LAI changes only the partitioning of PET between soil evaporation and vegetation transpiration; it does not create water. The two actual fluxes plus snow sublimation cannot exceed PET. The original root-zone method does not provide separate evaporation and transpiration outputs, so the corresponding CSV cells are left blank instead of recording an unresolved component as zero.

### Lateral flow and geomembranes

Equation 180 evaluates power terms in logarithmic form and is inverted by bisection, maintaining continuity at the critical value. Coupling the `h–L` relationship in Equations 178 and 180 to the local storage bucket still depends on the number of substeps.

The Giroud contact mode requires a barrier layer immediately below the membrane, with **barrier Ks < 86.4 mm/day (1e-4 cm/s)**. Defect density is entered as defects/ha and defect area as mm². After conversion to SI units, the model calculates the interface wetted radius and average gradient, applying the viscosity correction `0.00100/0.00114`. The wetted-area fraction is capped at 1, and total leakage cannot exceed the Darcy flux through the underlying soil. As the wetted radius approaches the hole radius, the model uses the Darcy limiting value based directly on the hole area. This treatment, including its extension to arbitrary hole areas, requires benchmark validation.

The intact portion of the membrane is still approximated using the input equivalent Ks. Giroud mode does not use the original empirical multiplier. Earlier configurations automatically retain the empirical-multiplier mode so that historical calculations are not changed without the user's selection. An example of the equation-based options is provided in [`examples/advanced_methods.json`](../examples/advanced_methods.json).
