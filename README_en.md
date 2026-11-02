# HELP Multilayer Water Balance — v2.3.1

Charts support start/end dates, Full period, Last 30/90/365 days, and day/month/year intervals. Both endpoints are included; presets end at the last simulated day. Monthly/yearly values sum only selected daily amounts, without extrapolating partial periods. The daily table follows the range; full totals and ZIP downloads keep the entire simulation. Language changes preserve the selection. A new run resets the date range to its complete results.

The package now includes a complete HTML main interface: **`index.html`**, with clickable layers, add/delete/reorder, parameter forms, JSON import/export, CSV/TSV/pasted weather, simulation, charts and result downloads.

**Extract the whole ZIP and double-click `Start_Web.cmd`.** Requires Python 3.10+, using only its standard library. No Streamlit install is needed. The browser opens automatically. The initial language is **English**, followed by **Français**, then **中文** in the selector; later selections are remembered by the web interface.

Opening `index.html` directly supports offline editing, weather preview and JSON export. Calculations require the local page opened by `Start_Web.cmd`. All web assets are included; keep the `web/` directory beside `index.html`. Excel can be saved as CSV or imported through the retained Streamlit interface.

The help page is fully trilingual. See `docs/WEB_GUIDE.md` (Chinese) and `docs/WEB_TEST_REPORT.md` for the web workflow and checks. The original Streamlit interface remains optional, with the same Python solver and v2.2 formula scope. Its instructions follow.

Click any layer cell to select its layer, then move, delete or edit it below. Rainfall import now supports CSV/TSV/XLSX, sheet and column selection, units, preview and pasted CSV. Rainfall-only input uses explicitly displayed temperature/PET constants. Modified Penman requires radiation, humidity and 2 m wind data.

Optional process settings add daily moisture-adjusted CN, Modified Penman PET, HELP steady lateral drainage equations and good/poor-contact Giroud defect equations. The extraction of actual ET with seasonal LAI remains approximate. These additions are formula-level modules within an independent solver, not complete EPA HELP equivalence. Detailed applicability and sources are in `docs/V22_METHODS.md` (Chinese).

The interface supports Chinese, French and English. Select the language in the sidebar, or start with `Start_UI_ZH.cmd`, `Start_UI_FR.cmd` or `Start_UI_EN.cmd`. The small subtitle and yellow notice formerly shown below the title have been removed. Method details remain in the help tab and technical documents.

## Start

Python 3.10+ is required. On Windows, double-click the launcher for your language. The first run creates a virtual environment inside the project and installs Streamlit from PyPI. You can also run:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-ui.txt
.venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

## Configure and run

1. Load one of the five example profiles, or import JSON.
2. Add soil, waste, drainage, barrier or geomembrane layers. Select a layer to edit, reorder or delete it.
3. Set thickness, hydraulic conductivity and applicable storage/drainage parameters. Save the layer.
4. Save global settings and any recirculation target. Stable IDs follow layers when reordered.
5. Upload consecutive daily weather (`date,precip_mm,temp_c,pet_mm`), or use the supplied two-year synthetic series.
6. Run the model and download the results ZIP.

Changing languages preserves the saved configuration and previous results. Unsaved form edits should be saved before switching. JSON/CSV keys, layer IDs and user-entered names are kept as supplied so files remain compatible between languages.

## Results

The ZIP contains the exact configuration and weather used, daily/monthly/annual balances, per-layer flows and storage, and a summary. All water quantities are depths over the site area. `m³ = mm × area_m2 / 1000`.

Each drainage layer contributes independently to collection. Intermediate liner flow is an internal transfer; only flow crossing the bottom boundary is counted as bottom outflow. `liner_leakage_mm` is an alias of `bottom_leakage_mm`, not an additional outlet. Pending next-day recirculation remains inside system storage.

Daily balance: initial storage + precipitation = final storage + runoff + ET + net collection + bottom outflow. Per-layer balances are also checked. A residual above 1e-7 mm stops the calculation.

## Methods

This is an independent approximate research model derived from the original Python MVP. It has not been validated as equivalent to EPA HELP or against field data. Fixed CN, degree-day snowmelt, externally supplied PET, bucket storage, local head estimates, Darcy-type drainage and an empirical membrane gate are used. A closed mass balance does not establish physical accuracy. Membrane defects, membrane-soil contact, frozen ground and vegetation growth are not resolved.

See `docs/UI_GUIDE_en.md`, `TECHNICAL_NOTES.md` and `docs/TEST_REPORT.md`. The detailed engineering notes and test report are in Chinese. `legacy/` preserves the original source and documentation.

The five example profiles cover unlined drainage, a composite bottom liner, double liners, separate cover/bottom drainage, and recirculation. Parameters and weather are illustrative, not site measurements. `examples/config.schema.json` describes the common JSON format.

Both chart axes are labeled. The X axis identifies date, month or year; the Y axis names the selected variable and its unit: mm/day for daily values and mm for monthly/yearly totals.
