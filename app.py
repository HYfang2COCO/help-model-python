"""Chinese, French and English layer editor. Run: python -m streamlit run app.py"""
from datetime import date
import copy
import csv
import io
import json
import os
import hashlib
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

from help_mvp import (KINDS, Layer, default_layer, migrate_config, profile_warnings,
                      simulate, validate_config)

from i18n import LANGUAGES, EXAMPLES, LAYER_COLUMNS, translate, localize_error
from weather_import import read_table,guess_columns,normalize_weather,worksheet_names

st.set_page_config(page_title='HELP', layout='wide')
default_language = os.environ.get('HELP_UI_LANG', 'en')
if default_language not in LANGUAGES:
    default_language = 'en'
lang = st.sidebar.selectbox('Langue', list(LANGUAGES),
                            index=list(LANGUAGES).index(default_language),
                            format_func=lambda code: LANGUAGES[code], key='ui_language')

def t(text):
    return translate(text, lang)

ROOT = Path(__file__).resolve().parent
LABELS = {'soil':t('土壤 soil'), 'waste':t('废物 waste'), 'drainage':t('导排 drainage'),
          'barrier':t('阻隔土 barrier'), 'geomembrane':t('土工膜 geomembrane')}
FIELDS = {
    'thickness_mm':t('厚度（mm）'), 'ksat_mm_day':t('饱和导水率 / 膜等效导水率（mm/day）'),
    'porosity':t('孔隙率（体积分数）'), 'field_capacity':t('田间持水量（体积分数）'),
    'wilting_point':t('萎蔫点（体积分数）'), 'initial_theta':t('初始含水量（体积分数）'),
    'brooks_corey_lambda':t('孔径指数 λ（近似参数）'),
    'lateral_ksat_mm_day':t('侧向导水率（mm/day）'), 'slope_fraction':t('坡度（0.03 = 3%）'),
    'drainage_length_m':t('侧向排水距离（m）'), 'leakage_multiplier':t('膜泄漏倍率（0～1，经验参数）')}
FIELDS.update({key:t(label) for key,label in {
    'pinhole_density_ha':'针孔密度（个/ha）','pinhole_area_mm2':'单个针孔面积（mm²）',
    'defect_density_ha':'安装缺陷密度（个/ha）','defect_area_mm2':'单个安装缺陷面积（mm²）'}.items()})


def reset_config(cfg):
    old_rev = st.session_state.get('revision', 0)
    previous = st.session_state.get(f'selected_{old_rev}', st.session_state.get('active_id'))
    st.session_state.cfg = validate_config(cfg)
    st.session_state.revision = st.session_state.get('revision', 0)+1
    ids = [l['id'] for l in cfg['layers']]
    st.session_state.active_id = previous if previous in ids else ids[0]


def select_table_layer(table_key, revision):
    event=st.session_state.get(table_key,{})
    selection=event.get('selection',{})
    cells=selection.get('cells',[])
    rows=selection.get('rows',[])
    row=cells[-1][0] if cells else (rows[-1] if rows else None)
    if row is not None and 0 <= row < len(st.session_state.cfg['layers']):
        ident=st.session_state.cfg['layers'][row]['id']
        st.session_state.active_id=ident
        st.session_state[f'selected_{revision}']=ident
        st.session_state.form_error=None


def select_dropdown_layer(revision):
    ident=st.session_state.get(f'selected_{revision}')
    if ident is None:
        ident=st.session_state.active_id
        st.session_state[f'selected_{revision}']=ident
    if ident is not None:
        st.session_state.active_id=ident
        st.session_state.form_error=None


def save_layer(selected, revision):
    updated = copy.deepcopy(st.session_state.cfg)
    index = next(i for i,l in enumerate(updated['layers']) if l['id']==selected)
    original=updated['layers'][index]
    edited={**default_layer(original['kind'],selected),**original}
    updated['layers'][index]=edited
    edited['name'] = st.session_state[f'name_{selected}_{revision}']
    for key in FIELDS:
        if key in edited:
            edited[key] = st.session_state[f'param_{selected}_{key}_{revision}']
    if edited['kind']=='geomembrane':
        edited['leakage_model']=st.session_state[f'leakage_model_{selected}_{revision}']
    try:
        reset_config(updated)
        st.session_state.form_error = None
    except ValueError as e:
        st.session_state.form_error = str(e)


def save_global(revision, keys):
    updated = copy.deepcopy(st.session_state.cfg)
    updated['site_name'] = st.session_state[f'site_name_{revision}']
    for key in keys:
        updated[key] = st.session_state[f'global_{key}_{revision}']
    updated['substeps_per_day'] = st.session_state[f'nstep_{revision}']
    updated['recirculation_target_id'] = st.session_state[f'rec_target_{revision}']
    try:
        reset_config(updated)
        st.session_state.global_error = None
    except ValueError as e:
        st.session_state.global_error = str(e)


PROCESS_ENUMS={
    'runoff_method':('fixed','help_user','help_slope','help_vegetation'),
    'pet_method':('provided','modified_penman'),'lateral_method':('darcy','help_steady'),
    'et_extraction':('legacy','lai_partition'),'vegetation_class':('bare','poor','fair','good','excellent')}
PROCESS_NUMBERS={'surface_slope_fraction':'地表坡度（比例）','surface_length_m':'地表坡长（m）',
                 'infiltration_index':'土壤入渗相关参数 IR','latitude_deg':'纬度（°）','max_lai':'最大 LAI',
                 'growing_start_day':'生长季开始（日序 1～366）','growing_end_day':'生长季结束（日序 1～366）',
                 'evaporation_depth_mm':'表层蒸发深度（mm）'}


def save_processes(revision):
    updated=copy.deepcopy(st.session_state.cfg)
    for key in list(PROCESS_ENUMS)+list(PROCESS_NUMBERS):
        updated[key]=st.session_state[f'process_{key}_{revision}']
    try:
        reset_config(updated)
        st.session_state.process_error=None
    except ValueError as e:
        st.session_state.process_error=str(e)


def result_zip(result):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        if 'input_provenance' in result:
            z.writestr('input_provenance.json',json.dumps(result['input_provenance'],ensure_ascii=False,indent=2))
        for key in ('config', 'summary'):
            z.writestr(f'{key}.json', json.dumps(result[key], ensure_ascii=False, indent=2))
        for key in ('weather','daily','layers','monthly','annual'):
            z.writestr(f'{key}.csv', pd.DataFrame(result[key]).to_csv(index=False).encode('utf-8-sig'))
    return buffer.getvalue()


st.title(t('HELP 多层水量模型'))
if 'cfg' not in st.session_state:
    reset_config(json.loads((ROOT/'examples/composite_liner.json').read_text(encoding='utf-8')))
cfg = st.session_state.cfg
rev = st.session_state.revision

with st.sidebar:
    st.subheader(t('剖面文件'))
    examples = sorted(p for p in (ROOT/'examples').glob('*.json') if p.name not in ('legacy_config.json','config.schema.json'))
    example = st.selectbox(t('选择样例'), examples,index=next(i for i,p in enumerate(examples) if p.stem=='composite_liner'), format_func=lambda p:t(EXAMPLES.get(p.stem,p.stem)), key='example')
    if st.button(t('载入样例'), key='load_example'):
        reset_config(json.loads(example.read_text(encoding='utf-8')))
        st.rerun()
    upload = st.file_uploader(t('导入 JSON（支持旧版 MVP 配置转换）'), type=['json'])
    if st.button(t('应用导入配置'), disabled=upload is None):
        try:
            raw = json.loads(upload.getvalue().decode('utf-8-sig'))
            migrated = raw.get('schema_version') != 2
            reset_config(migrate_config(raw) if migrated else raw)
            st.session_state.import_message = 'legacy' if migrated else 'imported'
            st.rerun()
        except (ValueError,KeyError,TypeError) as e:
            st.error(localize_error(e,lang))
    if st.session_state.get('import_message'):
        st.info(t('旧版底衬已转换为有储水的等效阻隔层，新旧数值不保证一致。') if st.session_state.import_message=='legacy' else t('配置已导入。'))
    st.download_button(t('下载当前配置 JSON'), json.dumps(cfg, ensure_ascii=False, indent=2),
                       file_name='profile.json', mime='application/json')
    st.caption(t('所有示例参数及合成气象仅用于功能演示，不代表具体场地。'))

edit_tab, run_tab, notes_tab = st.tabs([t('配置剖面'), t('运行与结果'), t('参数与算法说明')])
with edit_tab:
    st.subheader(t('从上到下的层序'))
    st.caption(t('单击任意层的单元格即可选中；下方可上移、下移、删除或编辑该层。'))
    layer_frame=pd.DataFrame([{t('序号'):i+1, 'id':l['id'], t('名称'):l['name'],
                               t('类型'):LABELS[l['kind']], t('厚度 mm'):l['thickness_mm'],
                               t('Ks mm/day'):l['ksat_mm_day']} for i,l in enumerate(cfg['layers'])])
    styled=layer_frame.style.apply(lambda row:['background-color: #dbeafe; color: #0f172a' if row['id']==st.session_state.active_id else '' for _ in row],axis=1)
    table_key=f'layer_table_{rev}'
    st.dataframe(styled,hide_index=True,width='stretch',key=table_key,
                 on_select=lambda:select_table_layer(table_key,rev),selection_mode=['single-row','single-cell'])
    for warning in profile_warnings(cfg):
        st.info(t(warning))
    cols = st.columns([2,2,1])
    kind = cols[0].selectbox(t('新增层类型'), KINDS, format_func=lambda x:LABELS[x], key='add_kind')
    new_id = cols[1].text_input(t('新层唯一 id'), value=f'layer_{rev+len(cfg["layers"])}', key=f'new_id_{rev}')
    if cols[2].button(t('新增到底部'), key='add_layer'):
        try:
            updated = copy.deepcopy(cfg)
            updated['layers'].append(default_layer(kind,new_id))
            reset_config(updated)
            st.rerun()
        except ValueError as e:
            st.error(localize_error(e,lang))
    selector_key=f'selected_{rev}'
    if selector_key not in st.session_state:
        st.session_state[selector_key]=st.session_state.active_id
    selected = st.selectbox(t('选择要编辑的层'), [l['id'] for l in cfg['layers']],
                            index=None,on_change=select_dropdown_layer,args=(rev,),
                            format_func=lambda ident:next(l['name']+' · '+ident for l in cfg['layers'] if l['id']==ident),
                            key=f'selected_{rev}')
    index = next(i for i,l in enumerate(cfg['layers']) if l['id']==selected)
    layer = cfg['layers'][index]
    st.caption(t('当前选中层')+': '+layer['name']+' · '+selected)
    cols = st.columns(3)
    for direction, label, target in [(-1,t('上移一层'),cols[0]),(1,t('下移一层'),cols[1])]:
        if target.button(label, disabled=not 0 <= index+direction < len(cfg['layers']), key=f'move_{direction}'):
            updated = copy.deepcopy(cfg)
            updated['layers'][index],updated['layers'][index+direction] = updated['layers'][index+direction],updated['layers'][index]
            reset_config(updated)
            st.rerun()
    if cols[2].button(t('删除此层'), disabled=len(cfg['layers'])==1, key='delete_layer'):
        updated = copy.deepcopy(cfg)
        updated['layers'].pop(index)
        if updated.get('recirculation_target_id') == selected:
            updated['recirculation_fraction'] = 0.
            updated['recirculation_target_id'] = None
        try:
            reset_config(updated)
            st.rerun()
        except ValueError as e:
            st.error(localize_error(e,lang))
    st.caption(t('重排不改变层 id；删除回灌目标会同时关闭回灌。修改后点击保存，运行只使用已保存配置。'))
    st.subheader(t('编辑选中层'))
    change_kind = st.selectbox(t('更换此层类型'), KINDS, index=KINDS.index(layer['kind']),
                               format_func=lambda x:LABELS[x], key=f'type_{selected}_{rev}')
    if st.button(t('应用类型并重置该层参数'), disabled=change_kind==layer['kind'], key='change_type'):
        updated = copy.deepcopy(cfg)
        updated['layers'][index] = dict(default_layer(change_kind,selected), name=layer['name'])
        if change_kind=='geomembrane' and updated.get('recirculation_target_id')==selected:
            updated['recirculation_fraction'],updated['recirculation_target_id'] = 0.,None
        reset_config(updated)
        st.rerun()
    with st.form(f'layer_form_{selected}_{rev}'):
        edited = {**default_layer(layer['kind'],selected),**copy.deepcopy(layer)}
        edited['name'] = st.text_input(t('层名称'), layer['name'], key=f'name_{selected}_{rev}')
        if layer['kind']=='geomembrane':
            methods=['empirical','giroud_good','giroud_poor']
            edited['leakage_model']=st.selectbox(t('膜泄漏方法'),methods,index=methods.index(edited['leakage_model']),
                format_func=lambda x:t({'empirical':'经验倍率','giroud_good':'Giroud 良好接触','giroud_poor':'Giroud 较差接触'}[x]),key=f'leakage_model_{selected}_{rev}')
        cols = st.columns(2)
        for j,key in enumerate(k for k in FIELDS if k in edited):
            maximum = 1. if key in ('porosity','field_capacity','wilting_point','initial_theta','slope_fraction','leakage_multiplier') else None
            edited[key] = cols[j%2].number_input(FIELDS[key], min_value=0., max_value=maximum,
                                                value=float(edited[key]), format='%.10g', key=f'param_{selected}_{key}_{rev}')
        st.form_submit_button(t('保存此层参数'), on_click=save_layer, args=(selected,rev))
        if st.session_state.get('form_error'):
            st.error(localize_error(st.session_state.form_error,lang))
    with st.expander(t('全局设置与回灌'), expanded=False):
        with st.form(f'global_{rev}'):
            updated = copy.deepcopy(cfg)
            updated['site_name'] = st.text_input(t('场地名称'), cfg.get('site_name',t('自定义剖面')), key=f'site_name_{rev}')
            labels = {'area_m2':t('面积（m²）'),'curve_number':t('固定曲线数 CN（0<CN<100）'),
                      'root_depth_mm':t('根区深度（mm）'),'snow_temperature_c':t('雨雪温度阈值（°C）'),
                      'melt_temperature_c':t('融雪温度阈值（°C）'),
                      'degree_day_melt_mm_per_c_day':t('度日融雪系数（mm/°C/day）'),
                      'snow_sublimation_pet_fraction':t('雪升华 PET 比例（0～1）'),
                      'recirculation_fraction':t('导排水次日回灌比例（0～1）')}
            cols = st.columns(2)
            for j,(key,label) in enumerate(labels.items()):
                updated[key] = cols[j%2].number_input(label, value=float(cfg[key]), key=f'global_{key}_{rev}')
            updated['substeps_per_day'] = st.number_input(t('日内子步数（1～1440）'), min_value=1, max_value=1440,
                                                         value=cfg['substeps_per_day'], key=f'nstep_{rev}')
            targets = [None]+[l['id'] for l in cfg['layers'] if l['kind']!='geomembrane']
            updated['recirculation_target_id'] = st.selectbox(t('回灌目标 id'), targets,
                  index=targets.index(cfg['recirculation_target_id']), format_func=lambda x:x or t('不指定'), key=f'rec_target_{rev}')
            st.form_submit_button(t('保存全局设置'),on_click=save_global,args=(rev,list(labels)))
            if st.session_state.get('global_error'):
                st.error(localize_error(st.session_state.global_error,lang))

    with st.expander(t('计算方法与植被设置'),expanded=False):
        method_labels={'runoff_method':'径流与 CN 方法','pet_method':'PET 方法','lateral_method':'侧向排水方法',
                       'et_extraction':'蒸发与蒸腾分配','vegetation_class':'植被覆盖等级'}
        choices={'fixed':'固定 CN（旧版）','help_user':'输入 CN-II，逐日含水率修正',
                 'help_slope':'输入 CN-II，加坡度与逐日修正','help_vegetation':'植被与 IR 生成 CN，加坡度与逐日修正',
                 'provided':'外部提供 PET','modified_penman':'Modified Penman 公式',
                 'darcy':'Darcy 近似（旧版）','help_steady':'HELP 稳态排水式 178 / 180',
                 'legacy':'原有根区限水法','lai_partition':'季节 LAI 分配（近似）',
                 'bare':'裸地','poor':'差','fair':'一般','good':'良好','excellent':'优良'}
        with st.form(f'process_form_{rev}'):
            for key,values in PROCESS_ENUMS.items():
                st.selectbox(t(method_labels[key]),values,index=values.index(cfg[key]),
                    format_func=lambda x:t(choices[x]),key=f'process_{key}_{rev}')
            cols=st.columns(2)
            for j,(key,label) in enumerate(PROCESS_NUMBERS.items()):
                value=int(cfg[key]) if key.startswith('growing_') else float(cfg[key])
                cols[j%2].number_input(t(label),value=value,key=f'process_{key}_{rev}')
            st.form_submit_button(t('保存计算方法'),on_click=save_processes,args=(rev,))
            if st.session_state.get('process_error'):
                st.error(localize_error(st.session_state.process_error,lang))

with run_tab:
    st.subheader(t('日气象与运行'))
    st.caption(t('可导入完整日气象，或仅导入日期和降水，再明确设置温度与 PET。'))
    weather_file = st.file_uploader(t('导入降水或气象（CSV / Excel）'), type=['csv','tsv','txt','xlsx'],key='weather_upload')
    pasted=st.text_area(t('也可粘贴 CSV 内容'),key='weather_paste',height=110)
    st.download_button(t('下载仅降水模板'), 'date,precip_mm\n2024-01-01,5.0\n2024-01-02,0.0\n2024-01-03,12.5\n',file_name='rainfall_template.csv',mime='text/csv')
    weather=None
    provenance=None
    energy=cfg['pet_method']=='modified_penman'
    if energy:
        st.caption(t('Modified Penman 需要太阳辐射、相对湿度和 2 m 风速；PET 列与 PET 常数不参与计算。'))
    if weather_file is not None or pasted.strip():
        try:
            payload=weather_file.getvalue() if weather_file is not None else pasted.encode('utf-8')
            filename=weather_file.name if weather_file is not None else 'pasted.csv'
            file_id=hashlib.sha256(payload).hexdigest()[:12]
            if filename.lower().endswith('.xlsx'):
                names=worksheet_names(payload)
                sheet=st.selectbox(t('工作表'),names,key='weather_sheet')
                raw,_=read_table(payload,filename,sheet=sheet)
            else:
                raw,_=read_table(payload,filename)
            columns=list(raw[0])
            guessed=guess_columns(columns)
            st.dataframe(pd.DataFrame(raw).head(8),hide_index=True,width='stretch')
            mapping={}
            cols=st.columns(2)
            variables=[('date','日期列'),('precip_mm','降水列'),('temp_c','气温列'),('pet_mm','PET 列')]
            if energy:
                variables += [('solar_mj_m2_day','太阳辐射列（MJ/m²/day）'),('rh_percent','相对湿度列（%）'),('wind_m_s','2 m 风速列（m/s）')]
            for j,(key,label) in enumerate(variables):
                options=columns if key in ('date','precip_mm') else [None]+columns
                default=guessed[key] if guessed[key] in options else options[0]
                mapping[key]=cols[j%2].selectbox(t(label),options,index=options.index(default),format_func=lambda x:x if x is not None else t('使用下方常数'),key=f'weather_col_{key}_{file_id}',disabled=energy and key=='pet_mm')
            date_format=st.selectbox(t('日期格式'),['%Y-%m-%d','%Y/%m/%d','%d/%m/%Y','%m/%d/%Y'],key='date_format')
            unit=st.selectbox(t('原始降水单位'),['mm','cm','inch'],key='precip_unit')
            cols=st.columns(2)
            constant_temp=cols[0].number_input(t('未提供气温时使用的常数（°C）'),value=15.,key='import_temp',disabled=mapping['temp_c'] is not None)
            constant_pet=cols[1].number_input(t('未提供 PET 时使用的常数（mm/day）'),value=2.,min_value=0.,key='import_pet',disabled=energy or mapping['pet_mm'] is not None)
            if mapping['temp_c'] is None or (mapping['pet_mm'] is None and not energy):
                st.info(t('仅降水不能确定雨雪和蒸散；缺少的气温与 PET 将使用你在上方确认的常数。'))
            weather=normalize_weather(raw,mapping,date_format=date_format,precip_unit=unit,constant_temp_c=constant_temp,constant_pet_mm=constant_pet,energy=energy)
            provenance=dict(filename=filename,mapping=mapping,date_format=date_format,precipitation_unit=unit,constant_temp_c=constant_temp if mapping['temp_c'] is None else None,constant_pet_mm=constant_pet if mapping['pet_mm'] is None and not energy else None,pet_method=cfg['pet_method'])
            st.success(t('导入校验通过')+f': {len(weather)} '+t('天'))
            st.dataframe(pd.DataFrame(weather).head(8),hide_index=True,width='stretch')
        except (ValueError,KeyError,TypeError,OSError) as e:
            st.error(localize_error(e,lang))
    else:
        st.caption(t('未上传文件：使用随包两年合成气象。'))
        example_weather='weather_energy_synthetic.csv' if energy else 'weather_synthetic.csv'
        weather=list(csv.DictReader(io.StringIO((ROOT/'examples'/example_weather).read_text(encoding='utf-8-sig'))))
        provenance=dict(filename=example_weather,source='bundled_synthetic')
    input_signature=hashlib.sha256(json.dumps([weather,provenance],sort_keys=True,default=str).encode()).hexdigest()
    if st.button(t('运行模型'), type='primary', key='run_model',disabled=weather is None):
        try:
            st.session_state.result = simulate(cfg, weather)
            st.session_state.result_run_id = st.session_state.get('result_run_id',0)+1
            st.session_state.result['input_provenance']=provenance
            st.session_state.result_revision = rev
            st.session_state.result_input_signature=input_signature
        except (ValueError,KeyError,TypeError,ArithmeticError) as e:
            st.error(localize_error(e,lang))
    if 'result' in st.session_state:
        result = st.session_state.result
        if st.session_state.result_revision != rev or st.session_state.get('result_input_signature')!=input_signature:
            st.warning(t('配置或气象已修改：下方显示的是上次运行结果，请重新运行。下载结果内含当时输入。'))
        summary = result['summary']
        cols = st.columns(3)
        cols[0].metric(t('侧向收集总量（mm）'), f'{summary["leachate_collected_mm"]:.4f}')
        cols[1].metric(t('底部流出 / 泄漏（mm）'), f'{summary["bottom_leakage_mm"]:.6f}')
        cols[2].metric(t('最大日守恒残差（mm）'), f'{summary["maximum_absolute_daily_balance_error_mm"]:.2e}')
        st.caption(t('完整汇总和下载包含全部模拟日期；图表与逐层表按所选日期显示。'))
        first=date.fromisoformat(result['daily'][0]['date']);last=date.fromisoformat(result['daily'][-1]['date'])
        run_id=st.session_state.get('result_run_id',0)
        selected_dates=st.date_input(t('图表时间范围'),value=(first,last),min_value=first,max_value=last,key=f'chart_dates_{run_id}')
        step=st.selectbox(t('显示间隔'),['day','month','year'],index=['day','month','year'].index(st.session_state.get('chart_step','day')),format_func=lambda x:t({'day':'日','month':'月','year':'年'}[x]),key='chart_step')
        st.caption(t('月、年按所选日期内的日水量求和；首尾不足整月或整年时仅包含选中天数。'))
        if len(selected_dates)!=2:
            st.info(t('请选择有效的开始和结束日期。'))
        elif selected_dates[0]>selected_dates[1]:
            st.error(t('开始日期不能晚于结束日期。'))
        else:
            start,end=(x.isoformat() for x in selected_dates)
            daily=pd.DataFrame([row for row in result['daily'] if start<=row['date']<=end]).set_index('date')
            plotted=daily[['leachate_collected_mm','bottom_leakage_mm','runoff_mm']]
            if step!='day':
                plotted=plotted.groupby(plotted.index.str[:7 if step=='month' else 4],sort=True).sum()
            st.caption(f'{start} → {end} · {len(daily)} '+t('天')+f' · {len(plotted)} '+t('个数据点'))
            chart_unit='mm/day' if step=='day' else 'mm'
            chart_x_label=t({'day':'日期（YYYY-MM-DD）','month':'月份（YYYY-MM）','year':'年份（YYYY）'}[step])
            chart_columns={key:t(name)+' ('+chart_unit+')' for key,name in [('leachate_collected_mm','净收集'),('bottom_leakage_mm','底部外流'),('runoff_mm','径流')]}
            st.line_chart(plotted.rename(columns=chart_columns),x_label=chart_x_label,y_label=t('水量')+' ('+chart_unit+')')
            display_layers = pd.DataFrame([row for row in result['layers'] if start<=row['date']<=end])
            display_layers['kind'] = display_layers['kind'].map(LABELS)
            st.dataframe(display_layers.rename(columns={key:t(value) for key,value in LAYER_COLUMNS.items()}), hide_index=True, width='stretch')
        st.download_button(t('下载完整结果 ZIP（含配置、逐层、日/月/年与汇总）'),result_zip(result),
                           file_name='HELP_results.zip',mime='application/zip')
        st.json({**summary,'warning':t('独立近似研究模型；不是 EPA HELP，尚未对官方 HELP 或实测数据验证。'),'profile_warnings':[t(w) for w in summary['profile_warnings']]}, expanded=False)

with notes_tab:
    st.markdown((ROOT/('docs/UI_GUIDE.md' if lang=='zh' else f'docs/UI_GUIDE_{lang}.md')).read_text(encoding='utf-8'))
