# HELP 多层剖面 Python 模型 v2.3.1（三语界面）

结果图支持开始／结束日期、全部时段与最近 30／90／365 天，以及日／月／年显示。日期包含首尾两天；“最近”以模拟结果的最后一天为准。月／年仅累加所选日期内的水量，部分月份或年份不外推。逐日表同步筛选，完整汇总和 ZIP 仍覆盖全部模拟日期。切换语言保留选择，重新运行重置为新结果的完整日期范围。

本版新增包内网页版主界面 **`index.html`**，支持单击选层、增删重排、参数设置、JSON 导入导出、CSV/TSV/粘贴降水、计算与结果图表。

**推荐启动：完整解压后双击 `Start_Web.cmd`。** 需要 Python 3.10+，仅使用标准库，不必安装 Streamlit；会自动打开浏览器。首次启动默认 **English**，语言顺序为 **English → Français → 中文**；网页会记住之后的选择。

直接打开 `index.html` 可离线编辑、预览和导出配置；运行计算需使用 `Start_Web.cmd` 打开的本地页面。网页所有资源均随包提供，无 CDN 或联网字体。`web/` 文件夹必须与 `index.html` 一起保留。

详细操作见 `docs/WEB_GUIDE.md`，网页测试见 `docs/WEB_TEST_REPORT.md`。原 Streamlit 界面保留为可选入口（`Start_UI.cmd`，默认英文），使用方式如下。算法实现范围沿用 v2.2，新增界面不改变公式。

本版支持**单击层表选中 → 上移/下移/删除/编辑**，以及CSV/Excel降水导入、列映射、单位换算、预览和粘贴CSV。另加入可选的逐日CN、Modified Penman PET、HELP稳态侧排及Giroud接触缺陷公式。详细范围、输入条件和未复现部分见 `docs/V22_METHODS.md`。

新增 `examples/advanced_methods.json`、`examples/weather_energy_synthetic.csv` 和 `examples/rainfall_template.csv`。仅降水导入可设置缺失温度/PET常数；这些常数是显式假设。

界面支持中文 / Français / English，侧栏可切换语言。也可双击 `Start_UI_ZH.cmd`、`Start_UI_FR.cmd`、`Start_UI_EN.cmd` 以相应语言启动。切换保留已保存配置与上次结果；请先保存表单内的修改。三语共用同一计算核心和文件格式，用户填写的名称/id与JSON/CSV字段不自动翻译。

按用户要求，标题下的灰色副标题和黄色提示框已移除。算法资料位于“参数与算法说明”页及手册。法文入门说明见 `README_fr.md`，英文见 `README_en.md`。

三语界面，可逐层新增、删除、重排与设置参数。基于 Library 中实际下载的 `HELP_Model_Python_MVP.zip` 源码与技术说明改造。

**这是 HELP 思路启发的独立近似研究模型，不是 EPA HELP 官方代码移植，尚未通过官方 HELP 输出或实测数据验证，不能宣称算法或结果完全等效。** 水量守恒通过只说明账目闭合，不证明实际预测准确。

## 快速使用

需要 Python 3.10 或以上版本。Windows 解压后双击 `Start_UI.cmd`；首次会建立项目内虚拟环境并从 PyPI 安装界面依赖。随后浏览器打开编辑器，默认英文。若没有 Python，请先安装 Python。

也可手动运行：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-ui.txt
.venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

纯计算核心仅依赖 Python 标准库：

```powershell
python help_mvp.py validate --config examples/composite_liner.json
python help_mvp.py run --config examples/composite_liner.json --weather examples/weather_synthetic.csv --out results
python -m unittest discover -s tests -v
```

## 如何设置每一层

1. 载入样例或导入 JSON。
2. “新增层类型”选 soil、waste、drainage、barrier、geomembrane，填唯一 id，新增到底部。
3. 选中层后上下移动或删除。表格从上到下就是实际计算层序。
4. 修改适用参数后点击“保存此层参数”。更换类型会重置该层参数，因此请重新检查。
5. 保存全局设置及回灌比例/目标，下载 JSON 留存。
6. 上传连续日气象 CSV 或使用附带的两年合成气象，点击“运行模型”，下载结果 ZIP。

运行使用**已保存**的配置。表单内未保存的输入不参与运行。修改配置后，旧结果会提示重新运行。

JSON 的 `layers` 数组顺序就是层序，不限定层数或衬垫数量。删除数组元素即删除层，移动元素即重排。各层 id 保持唯一且重排时保持不变；回灌目标按 id 引用。

| 类型 | 可独立设置的字段 |
|---|---|
| soil / waste | 厚度、Ks、孔隙率、FC、WP、初始含水量、孔径指数 λ |
| drainage | 上述多孔介质参数，加侧向 Ks、坡度、排水距离 |
| barrier | 多孔介质全部参数，以近似 Darcy 公式模拟阻隔土流出 |
| geomembrane | 厚度、膜等效导水率、经验泄漏倍率；无孔隙储水，不适用 FC/WP/初始含水量 |

所有数值须有限，厚度/λ/排水距离大于零，导水率非负；多孔层要求 `0 <= WP < FC < porosity <= 1`、`0 <= initial_theta <= porosity`。允许初始含水量低于 WP，ET 不再抽取该部分水。坡度与膜倍率在 0～1 范围。未知类型、重复 id、未知或不适用字段会被拒绝。

**示例参数是人为演示值，不是 EPA 推荐材料库或经标定的场地参数。**

## 样例与模板

- `examples/unlined.json`：无衬垫自由排水。
- `examples/composite_liner.json`：土壤 / 废物 / 导排 / 膜 / 阻隔土。
- `examples/double_liner.json`：两个衬垫系统与中间泄漏检测导排。
- `examples/cover_and_base.json`：覆盖导排与底部导排。
- `examples/recirculation.json`：多导排、次日回灌。
- `examples/config.schema.json`：JSON Schema；跨字段关系仍须运行 Python 校验。
- `examples/legacy_config.json`：原 MVP 配置，供转换演示。

直接复制一个 v2 样例改写即可作为模板。`name` 可用中文；`id` 以英文字母开头，仅用字母、数字、下划线、短横线，最多64位。

## 单位与输入

气象 CSV 列：`date,precip_mm,temp_c,pet_mm`。日期 ISO `YYYY-MM-DD`，逐日连续，不得重复、跳日或倒序；降水和 PET 非负，温度有限。PET 由用户提供；不重现官方 PET 生成过程。合成气象不是加拿大或其他地点的观测记录。

厚度、水量、储水和通量采用 mm；Ks 为 mm/day；温度 °C；排水距离 m；含水量为 m³/m³；坡度为无量纲比例。单位换算：`1 cm/s = 864000 mm/day`，`1 m/s = 86400000 mm/day`。体积 `m³ = mm × area_m2 / 1000`，1公顷上 1 mm = 10 m³。

## 输出与守恒

- `daily.csv`：径流、ET、全部导排层净收集总量、底部流出、雪/层/回灌暂存量、日残差。
- `layers.csv`：按日期及稳定 id 的每层入流、垂向出流、侧向总流出、净收集、回灌份额、ET、储水、含水量、局部水头及残差。膜层入流=垂向出流，储水恒为零，theta 为空。
- `monthly.csv`、`annual.csv`：通量求和、期末储水、期间最大局部水头；储水不作为累计通量求和。
- `summary.json`：累计通量、体积、初末储量及最大残差。
- `config.json`：本次运行的完整规范配置。
- `weather.csv`：本次运行使用的日气象四列，可配合配置复算。

`bottom_leakage_mm` 表示越过**剖面最后一层**的外流。`liner_leakage_mm` 是同一数值的旧名称兼容列，不是可再次相加的另一项。无底部衬垫时它表示自由排水。各中间膜/阻隔土的穿透量见 `layers.csv` 的 `vertical_out_mm`；中间穿透是内部转移，不能与底部外流重复相加。

每个导排层都可排水。`leachate_collected_mm` 是所有导排层扣除回灌后的净收集**总量**；覆盖导排、渗滤液收集和泄漏检测的用途由层名称/id区分，请按实际用途查看逐层结果，不要把覆盖水解释成垃圾渗滤液。

日平衡：

`日初总储水 + 降水 = 日末总储水 + 径流 + ET + 净收集 + 底部外流`

总储水包括全部多孔层、雪水当量、待次日回灌的导排水。回灌是内部转移，不重复算降水或净收集。回灌目标容量不足的水直接记作显式拒收外排（兼容归入径流），不穿越衬垫向上填充其他层。

逐层平衡：

`层初储水 + 层入流 = 层末储水 + 垂向出流 + 侧向总出流 + 层ET`

当任一天或任一层残差绝对值超过 `1e-7 mm` 时计算报错。具体检查与结果见 `docs/TEST_REPORT.md`。

## 从旧版升级

```powershell
python help_mvp.py migrate --config examples/legacy_config.json --out migrated.json
python help_mvp.py run --config migrated.json --weather examples/weather_synthetic.csv --out migrated_results
```

界面也支持旧 JSON 导入。旧 `drain` 改为 `drainage`；新增稳定 id；旧回灌索引改为 id。旧 `liner` 的 `Ks × geomembrane_leakage_multiplier` 转为新底部等效 barrier 的 Ks，厚度保留，其他储水参数采用明确的演示默认值。**旧底衬没有储水，新阻隔层有储水，迁移会改变初始储量和结果，不保证数值兼容。** 若需要分别研究膜和土，请将等效 barrier 改为两个独立层并提供相应参数。

原代码及原说明保留在 `legacy/`，仅用于核对来源；运行入口是根目录 `help_mvp.py`。旧版可选 `plot` 命令由界面图表代替。

## 算法边界与下一步

模型保留原 MVP 的固定 SCS-CN、度日融雪、外部 PET 与简化含水量导水率思路；新实现逐层有限储水、任意位置导排与无储水膜闸门。不是 Richards 方程或压力场求解器。高水位只用局部层内可排水储量估计，不解析多层承压、侧壁溢流、毛细上升和复合衬垫接触。

详细公式、日内计算顺序及 EPA HELP 对照见 [技术说明](TECHNICAL_NOTES.md)。官方过程更全面，含冻土、植被、专门的侧向排水和膜/复合衬垫计算；参考 [EPA HELP 4 手册](https://www.epa.gov/land-research/help-40-user-manual)及 [HELP v3 工程说明](https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=300038SW.TXT)。

交付包中的测试检查守恒、边界、连通性、回灌和界面操作。尚无官方基准数据逐日对比，不能作为许可、工程设计或风险证明的替代品。

图表已补齐 X／Y 轴名称与单位：X 轴随日／月／年显示时间格式，Y 轴显示结果变量名称；日图使用 mm/day，月／年汇总使用 mm。
