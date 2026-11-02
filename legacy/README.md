# HELP-inspired Landfill Hydrology Model — Python Research MVP

**Status:** A standalone daily water-balance simulator **inspired by** the US EPA Hydrologic Evaluation of Landfill Performance (HELP) model. **It is NOT the official HELP model, does NOT reproduce every HELP 3/4 equation, and has NOT been calibrated or validated against HELP output or field measurements.** Do not use its numbers for landfill design, environmental permitting, compliance claims, or risk certification.

## 中文概览

本项目复刻 HELP 的主要工作流程，而不是声称复制了官方程序的计算结果：逐日气象 → 雨雪划分/融雪 → SCS 曲线数径流 → 分层蒸散 → 非饱和垂向入渗 → 侧向排水与底部泄漏 → 日/月/年水量平衡。

只需 Python 3.10+，运行不依赖第三方库。制图需要 `matplotlib`。

## Quick start / 运行方式

从本项目文件夹中执行：

```bash
python help_mvp.py run --config examples/config.json --weather examples/weather_synthetic.csv --out sample_outputs
python help_mvp.py plot --out sample_outputs  # optional: pip install matplotlib
python -m unittest discover -s tests -v
```

自行生成**合成气象**：

```bash
python help_mvp.py demo-weather --year 2024 --years 2 --out examples/my_synthetic_weather.csv
```

Windows 可把 `python` 换成 `py`。

## File structure

- `help_mvp.py` — independent simulation, CSV I/O, optional plotting and command-line interface
- `examples/config.json` — **illustrative, not site-specific or calibrated** landfill configuration
- `examples/weather_synthetic.csv` — **simulated/synthetic**, not official Ottawa weather observations
- `sample_outputs/daily.csv`, `monthly.csv`, `annual.csv`, `summary.json`, `hydrology.png` — sample output from illustrative parameters
- `tests/test_help_mvp.py` — conservation, runoff, climate and validation checks
- `TECHNICAL_NOTES.md` — implementation assumptions and steps toward true HELP parity

## Required weather CSV / 日气象输入

`date,precip_mm,temp_c,pet_mm`，例如：

```csv
date,precip_mm,temp_c,pet_mm
2026-01-01,2,-8,0.4
2026-01-02,0,-6,0.5
2026-01-03,9,4,0.9
```

必须逐日连续，不能重复或跳日期。`precip_mm` 是一天的降水水当量；`temp_c` 是日平均气温；`pet_mm` 是用户**外部提供的潜在蒸散量**，本程序没有重现 HELP 官方的 Penman/PET 生成器。每天的土壤蒸散不会超过 PET。降雪通过雪储量平衡计量，融雪不会作为额外水源再计入总质量。

## Config keys / 配置

`curve_number`：固定 SCS-CN，取值 0–100（不含端点）；`root_depth_mm`：土壤蒸散可达深度；`substeps_per_day`：日内子步数，默认 4；`layers`：从地表到防渗层上方的可渗透介质列表。

每个 `layer`：

| Field | Meaning |
|---|---|
| `kind` | `soil`, `waste`, `drain` |
| `thickness_mm` | layer thickness, mm |
| `porosity` | saturated volumetric water fraction |
| `field_capacity` | field-capacity fraction |
| `wilting_point` | wilting-point fraction |
| `initial_theta` | initial volumetric water fraction |
| `ksat_mm_day` | saturated vertical conductivity, mm/day |
| `brooks_corey_lambda` | assumed retention pore index, dimensionless |
| `lateral_ksat_mm_day` | lateral conductivity, mm/day (`drain` only; currently drainage routed only from **bottom** layer) |
| `slope_fraction` | e.g. 0.03 is 3% |
| `drainage_length_m` | average lateral flow path length in metres |

`liner` 可为 `null`（底部自由排水），或 `{ "thickness_mm":600, "ksat_mm_day":0.02, "geomembrane_leakage_multiplier":0.1 }`。最后一个变量只是人为定义的相对泄漏因子，**并不是** Giroud 土工膜针孔/破损公式，也不能据此推断实际渗漏率。通常值需通过数值基准或观测校准。`recirculation_fraction` 为在第二天回灌的侧向排水比例，需配套 `recirculation_target_index` 指定回灌的层编号（从 0 开始）。

**设计限制：目前只能从最底层 `drain` 收集侧向排水，尚不支持多个独立导排子系统。**

## Key outputs / 核心结果

每日输出 `daily.csv`：

- `runoff_mm`：包括 CN 直接径流、饱和溢流以及回灌过量返回地表的总径流
- `infiltration_mm`：降雨+融雪实际进入第一层的水量，不含回灌注入
- `et_mm`：土壤蒸散与雪升华总量
- `leachate_collected_mm`：侧向流出系统、未回灌的实际收集水量
- `liner_leakage_mm`：底部流出/防渗层渗漏的近似量（有/无防渗层使用不同方法）
- `snowpack_mm`, `soil_storage_mm`, `total_storage_mm`：末日储存量；`total_storage_mm` 包括计划第二天回灌的暂存水
- `balance_error_mm`：**应接近零**的水量守恒残差

每日质量平衡：

`storage_before + precipitation = storage_after + runoff + ET + leachate_collected + liner_leakage`

月、年汇总的 `mm` 是**面积归一化水深**。换算体积：`m³ = mm × m² / 1000`。例如对 1 公顷（10,000 m²），`1 mm = 10 m³`。

## What is from HELP vs approximate?

| Model element | Status |
|---|---|
| Daily / multi-layer storage routing with substeps | **Workflow analogue**, not line-for-line HELP algorithm |
| Fixed NRCS/SCS Curve Number with Ia=0.2S | **Recognized SCS equation**; lacks HELP's moisture/slope/frozen-soil CN adjustments |
| Soil water K(theta) | **Campbell/Brooks-Corey inspired**; uses wilting-point as residual proxy and assumed lambda |
| Snowmelt | **Degree-day approximation**, not SNOW-17 |
| Actual ET | Root-zone availability-limited extraction; **not Ritchie/HELP** |
| PET input | User supplied; **not HELP modified Penman** |
| Lateral drainage | **Darcy-type approximation**, not HELP Boussinesq / Dupuit solution |
| Soil liner | **Darcy-based surrogate** with simplified head |
| Geomembrane | **User-controlled multiplier only**, not HELP Giroud defect cases |
| Recirculation | Next-day simplified injection; does not model all official configurations |
| Vegetation growth, interception, frozen ground, soil liners mid-profile | **Not implemented** |

## Grounding documents

1. US EPA, [HELP Model downloads](https://www.epa.gov/land-research/hydrologic-evaluation-landfill-performance-help-model) — official HELP 4.0.1.
2. US EPA, [HELP 4.0 User Manual](https://www.epa.gov/land-research/help-40-user-manual), January 2020.
3. Schroeder et al. (1994), [HELP v3 Engineering Documentation](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=300038SW.TXT), EPA/600/R-94/168b — sections 3 and 4.

To reach a defensible HELP replica, implement and test the engineering equations individually, obtain representative HELP 4.0.1 reference projects and daily model outputs, then compare seasonal totals, daily traces, water balance and flux sensitivities. Implement the frozen-soil and geomembrane defects modules before relying on cold-climate or lined-landfill predictions.
