# HELP — Landfill Water Balance

[English](README_en.md) · [Français](README_fr.md) · [Bilingual overview](README.md)

### Overview

An independent Python model inspired by the **Hydrologic Evaluation of Landfill Performance (HELP)** workflow. It simulates daily water storage and movement through a configurable landfill profile, with a local web interface in **English, French and Chinese**.

### Download and start

**[Download the complete application ZIP](releases/HELP_Model_Python_v2_3_1_Time_Range_Trilingual.zip)**

1. Install **Python 3.10 or newer**.
2. Download the ZIP above and extract **all** its contents.
3. On Windows, double-click `Start_Web.cmd` inside the extracted project folder.
4. The local web interface opens in your browser. English is the initial language; use **Langue** to switch to French or Chinese.

The packaged web interface and calculation engine use the Python standard library; Streamlit is optional. On other systems, run this command from the extracted project folder:

```bash
python web_server.py --open
```

Use the complete ZIP for a runnable installation. It preserves the required `web/`, `examples/`, `docs/` and `tests/` folders. The same directory structure is also available directly in this repository. Opening `index.html` directly supports editing and previews; calculations require the local Python server.

### Features

- Click a layer to select it, then add, edit, move up/down or delete layers.
- Configure soil, waste, drainage, barrier-soil and geomembrane layers with stable IDs and type-specific fields.
- Set layer thickness, hydraulic conductivity and applicable porosity, field capacity, wilting point, initial moisture and drainage parameters.
- Import/export JSON profiles; import CSV/TSV weather or paste rainfall data. The optional Streamlit interface also supports Excel input.
- Track runoff, evapotranspiration, layer storage, interlayer flow, independent drainage collection, recirculation and bottom outflow.
- Select chart start/end dates and daily, monthly or annual display, with axis labels and units.
- Export balances, per-layer results, input data and configuration.

### Inputs and results

Daily weather uses `date,precip_mm,temp_c,pet_mm`, with consecutive ISO dates (`YYYY-MM-DD`). The interface can assist with column mapping and units. Rainfall-only inputs require explicit assumptions for missing temperature and potential evapotranspiration.

Water quantities are expressed as site-area-equivalent depth in millimetres. Daily fluxes are shown in **mm/day**; monthly and annual flux totals are in **mm**. Monthly/yearly views sum selected daily amounts, so their values and automatic vertical scales differ from the daily view. Partial periods include only the selected days.

Volume conversion: `m³ = mm × area_m2 / 1000`.

The solver checks both daily system balances and individual layer balances. Water awaiting next-day recirculation remains part of system storage.

### Methods and scope

Available options include SCS Curve Number runoff, moisture-adjusted CN, modified Penman potential evapotranspiration, simplified unsaturated flow, lateral drainage and geomembrane defect leakage formulas. Their assumptions and input requirements are documented in [the methods notes](docs/V22_METHODS.md).

**This is an independent approximation, not the official EPA HELP software.** Complete numerical equivalence to EPA HELP and accuracy against field measurements have not been established. A closed water balance verifies accounting consistency, not predictive accuracy. Example profiles and weather are illustrative synthetic data.

### Documentation and checks

- [English interface guide](docs/UI_GUIDE_en.md)
- [French interface guide](docs/UI_GUIDE_fr.md)
- [Web guide](docs/WEB_GUIDE.md) and [method details](docs/V22_METHODS.md) — detailed notes are in Chinese.
- Additional documentation, JSON templates, example profiles and tests are included in the ZIP.

From the **extracted project folder**, run:

```bash
python -m unittest discover -s tests -v
node --test tests/test_time_series.cjs
```

Node.js is used for the JavaScript checks only. Optional Python interface/schema checks require their corresponding dependencies.
