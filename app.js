'use strict';
(() => {
  const D = window.HELP_DATA, timeSeries = window.HELP_TIME_SERIES;
  let resultView = null;
  const $ = id => document.getElementById(id);
  const clone = value => JSON.parse(JSON.stringify(value));
  const readStore = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
  const store = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* JSON export remains available. */ } };
  let lang = readStore('help-web-language', 'en');
  if (!['en', 'fr', 'zh'].includes(lang)) lang = 'en';
  const t = text => D.translations[text]?.[lang] || text;
  let cfg = clone(D.examples.composite_liner.config), activeId = cfg.layers[0].id;
  cfg.site_name = t(D.examples.composite_liner.label);
  let page = 'profile', connected = false, revision = 0, result = null, resultPage = 0, resultStale = false;
  let layerDirty = false, settingsDirty = false, mappingHeaders = [], weatherSource = '粘贴 / 本地文件';
  const mappingLabels = {date:'日期', precip_mm:'降水', temp_c:'气温', pet_mm:'PET', solar_mj_m2_day:'太阳辐射', rh_percent:'相对湿度', wind_m_s:'风速'};
  const pageLabels = {profile:'剖面设置', weather:'降水与运行', results:'结果分析', guide:'使用说明'};
  const columns = {date:'日期',precip_mm:'降水',runoff_mm:'径流',et_mm:'蒸散',leachate_collected_mm:'净收集',bottom_leakage_mm:'底部外流'};
  const colors = {soil:'#b4a078',waste:'#a7b6a0',drainage:'#80acb3',barrier:'#aa8d7d',geomembrane:'#415968'};
  const integers = new Set(['substeps_per_day','growing_start_day','growing_end_day']);
  const limits = {
    area_m2:[0,null,true],curve_number:[0,100,true,true],substeps_per_day:[1,1440],root_depth_mm:[0],
    degree_day_melt_mm_per_c_day:[0],snow_sublimation_pet_fraction:[0,1],recirculation_fraction:[0,1],
    surface_slope_fraction:[0,1,true],surface_length_m:[0,null,true],infiltration_index:[0,.5],
    latitude_deg:[-89,89],max_lai:[0,10],growing_start_day:[1,366],growing_end_day:[1,366],evaporation_depth_mm:[0,null,true],
    thickness_mm:[0,null,true],ksat_mm_day:[0],porosity:[0,1],field_capacity:[0,1],wilting_point:[0,1],initial_theta:[0,1],
    brooks_corey_lambda:[0,null,true],lateral_ksat_mm_day:[0],slope_fraction:[0,1],drainage_length_m:[0,null,true],
    leakage_multiplier:[0,1],pinhole_density_ha:[0],pinhole_area_mm2:[0,null,true],defect_density_ha:[0],defect_area_mm2:[0,null,true]
  };
  const fmt = (value, digits=2) => Number(value).toLocaleString(lang === 'zh' ? 'zh-CN' : lang, {maximumFractionDigits:digits});
  const readable = (value,digits=2) => value!==0 && Math.abs(value)<10**(-digits) ? Number(value).toLocaleString(lang==='zh'?'zh-CN':lang,{notation:'scientific',maximumFractionDigits:3}) : fmt(value,digits);
  const escapeHtml = value => String(value).replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  const fail = text => { throw new Error(t(text)); };
  const message = (text, error=false) => { $('message').textContent = text; $('message').classList.toggle('error',error); $('message').hidden = false; };
  const attempt = fn => async event => { try { await fn(event); } catch (error) { message(error.message || String(error),true); } };
  function guard() {
    if (!(layerDirty || settingsDirty)) return true;
    if (!window.confirm(t('修改尚未保存，放弃修改？'))) return false;
    renderProfile(); return true;
  }
  function changed() { revision++; resultStale = !!result; $('stale-note').hidden = !resultStale; }
  function persist() { store('help-web-profile',cfg); changed(); }
  function numeric(value, key) {
    if (value === '' || value == null || typeof value === 'boolean') fail('参数须为有限数值');
    const n = Number(value), [low, high, strictLow, strictHigh] = limits[key] || [];
    if (!Number.isFinite(n) || (integers.has(key) && !Number.isInteger(n))) fail('参数须为有限数值');
    if ((low != null && (strictLow ? n <= low : n < low)) || (high != null && (strictHigh ? n >= high : n > high))) throw new Error(`${key}: ${low ?? '−∞'} ${strictLow?'<':'≤'} x ${strictHigh?'<':'≤'} ${high ?? '∞'}`);
    return n;
  }
  function validateLayer(layer) {
    const defaults = D.defaults[layer.kind];
    if (!defaults) throw new Error('Unknown layer kind');
    if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(layer.id)) throw new Error('Invalid layer id');
    const optional = new Set(['name','brooks_corey_lambda','leakage_model','pinhole_density_ha','pinhole_area_mm2','defect_density_ha','defect_area_mm2']);
    for (const key of Object.keys(layer)) if (!(key in defaults)) throw new Error(`${layer.id}: ${key}`);
    for (const key of Object.keys(defaults)) if (!(key in layer) && !optional.has(key)) throw new Error(`${layer.id}: ${key}`);
    const out = {...clone(defaults),...layer};
    if (typeof out.name !== 'string' || !out.name.trim()) throw new Error('Invalid layer name');
    for (const key of Object.keys(D.layer_labels)) if (key in out) out[key] = numeric(out[key],key);
    if (out.kind !== 'geomembrane') {
      if (!(out.wilting_point < out.field_capacity && out.field_capacity < out.porosity && out.initial_theta <= out.porosity)) fail('要求 0 ≤ WP < FC < 孔隙率 ≤ 1，初始含水量不超过孔隙率。');
    } else if (!(out.leakage_model in D.enums.leakage_model)) throw new Error('Invalid leakage_model');
    return out;
  }
  function validateLocal(raw) {
    if (!raw || typeof raw !== 'object' || raw.schema_version !== 2 || !Array.isArray(raw.layers) || !raw.layers.length) fail('至少需要一层');
    const out = {...clone(D.examples.composite_liner.config),...clone(raw)};
    const allowed = new Set(['schema_version','site_name','layers',...Object.keys(D.settings_labels)]);
    for (const key of Object.keys(raw)) if (!allowed.has(key)) throw new Error(`Unknown setting: ${key}`);
    out.layers = raw.layers.map(validateLayer);
    if (new Set(out.layers.map(l=>l.id)).size !== out.layers.length) throw new Error('Duplicate layer id');
    if (!out.layers.some(l=>l.kind!=='geomembrane')) fail('至少需要一层');
    if (typeof out.site_name !== 'string') throw new Error('Invalid site_name');
    for (const key of Object.keys(D.settings_labels)) {
      if (D.enums[key]) { if (!(out[key] in D.enums[key])) throw new Error(`Invalid ${key}`); }
      else if (key !== 'recirculation_target_id') out[key] = numeric(out[key],key);
    }
    if (out.growing_start_day === out.growing_end_day) throw new Error('Growing-season start and end must differ');
    const targets = out.layers.filter(l=>l.kind!=='geomembrane').map(l=>l.id);
    if (out.recirculation_target_id !== null && !targets.includes(out.recirculation_target_id)) fail('启用回灌须选择现有多孔层');
    if (out.recirculation_fraction>0 && !out.recirculation_target_id) fail('启用回灌须选择现有多孔层');
    return out;
  }
  try { cfg = validateLocal(readStore('help-web-profile',cfg)); activeId=cfg.layers[0].id; } catch { /* Keep the bundled valid profile. */ }
  function options(element, values, selected) {
    element.replaceChildren();
    for (const [value,label] of Object.entries(values)) {
      const option = new Option(t(label),value); element.add(option);
    }
    element.value = selected ?? Object.keys(values)[0];
  }
  function field(container, key, label, value, choiceMap=null) {
    const wrapper=document.createElement('label'), span=document.createElement('span'); span.textContent=t(label);
    const input=document.createElement(choiceMap ? 'select':'input'); input.name=key;
    if (choiceMap) options(input,choiceMap,value??'');
    else { input.type='number'; input.required=true; input.step=integers.has(key)?'1':'any'; input.value=value;
      const [low,high,strictLow,strictHigh]=limits[key]||[];
      if (low!=null && !strictLow) input.min=low;
      if (high!=null && !strictHigh) input.max=high;
    }
    wrapper.append(span,input); container.append(wrapper); return input;
  }
  function renderStats() {
    $('site-name').value=cfg.site_name;
    $('layer-count').textContent=fmt(cfg.layers.length,0);
    $('total-depth').textContent=fmt(cfg.layers.reduce((s,l)=>s+l.thickness_mm,0)/1000,3)+' m';
    $('drain-count').textContent=fmt(cfg.layers.filter(l=>l.kind==='drainage').length,0);
    $('area-display').textContent=fmt(cfg.area_m2)+' m²';
  }
  function renderLayers() {
    const list=$('layer-list'); list.replaceChildren();
    cfg.layers.forEach((layer,index)=>{
      const row=document.createElement('button'); row.type='button'; row.className='layer-row'+(layer.id===activeId?' selected':'');
      row.setAttribute('aria-pressed',String(layer.id===activeId)); row.dataset.layerId=layer.id;
      row.innerHTML=`<span class="layer-number">${String(index+1).padStart(2,'0')}</span><span class="material ${layer.kind}" style="--material:${colors[layer.kind]}"></span><span class="layer-details"><strong>${escapeHtml(layer.name)}</strong><small>${escapeHtml(t(D.kinds[layer.kind]))} · ${escapeHtml(layer.id)}</small></span><span class="layer-values">${fmt(layer.thickness_mm,3)} mm<small>Ks ${fmt(layer.ksat_mm_day,8)}</small></span>`;
      row.addEventListener('click',()=>{if (layer.id!==activeId && guard()){activeId=layer.id;layerDirty=false;settingsDirty=false;renderProfile();}});
      list.append(row);
    });
  }
  function renderLayer() {
    const layer=cfg.layers.find(l=>l.id===activeId) || cfg.layers[0]; activeId=layer.id;
    $('editor-title').textContent=layer.name; $('layer-name').value=layer.name; $('layer-id').textContent='ID · '+layer.id;
    options($('layer-kind'),D.kinds,layer.kind); $('type-change').hidden=true;
    $('move-up').disabled=cfg.layers.indexOf(layer)===0;
    $('move-down').disabled=cfg.layers.indexOf(layer)===cfg.layers.length-1;
    $('delete-layer').disabled=cfg.layers.length===1;
    const box=$('layer-fields'); box.replaceChildren();
    if (layer.kind==='geomembrane') field(box,'leakage_model','膜缺陷方法',layer.leakage_model||'empirical',D.enums.leakage_model);
    const full={...D.defaults[layer.kind],...layer};
    for (const [key,label] of Object.entries(D.layer_labels)) if (key in full) field(box,key,label,full[key]);
    layerDirty=false;
  }
  function renderSettings() {
    const box=$('settings-fields');box.replaceChildren();
    for (const [key,label] of Object.entries(D.settings_labels)) {
      let choices=D.enums[key];
      if(key==='recirculation_target_id') choices=Object.fromEntries([['','不回灌'],...cfg.layers.filter(l=>l.kind!=='geomembrane').map(l=>[l.id,l.name])]);
      field(box,key,label,cfg[key],choices);
    }
    settingsDirty=false;
  }
  function renderProfile() {renderStats();renderLayers();renderLayer();renderSettings();}
  function showPage(next) {
    if (!(next in pageLabels)) next='profile'; page=next;
    document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!=='page-'+next);
    document.querySelectorAll('[data-page]').forEach(el=>{el.classList.toggle('active',el.dataset.page===next);el.setAttribute('aria-current',el.dataset.page===next?'page':'false');});
    $('page-title').textContent=t(pageLabels[next]);
    if (location.hash!=='#'+next) history.replaceState(null,'','#'+next);
    if(next==='results')renderResults();
  }
  function renderLanguage() {
    document.documentElement.lang=lang==='zh'?'zh-CN':lang;
    document.title='HELP · '+t('水量模拟'); $('language').value=lang;
    document.querySelectorAll('[data-t]').forEach(el=>el.textContent=t(el.dataset.t));
    options($('example'),Object.fromEntries(Object.entries(D.examples).map(([k,v])=>[k,v.label])),$('example').value||'composite_liner');
    options($('new-kind'),D.kinds,$('new-kind').value||'soil');
    $('readme-link').href=lang==='zh'?'README.md':`README_${lang}.md`;
    $('new-kind').setAttribute('aria-label',t('新增层类型'));
    document.querySelector('nav').setAttribute('aria-label',t('工作空间'));
    $('chart-variable').setAttribute('aria-label',t('水量时间曲线'));
    $('move-up').setAttribute('aria-label',t('上移一层'));$('move-down').setAttribute('aria-label',t('下移一层'));$('delete-layer').setAttribute('aria-label',t('删除此层'));
    renderProfile(); renderMapping(true); renderConnection(); renderWeatherSource(); showPage(page);
  }
  function renderConnection() {
    $('connection').classList.toggle('online',connected);
    $('connection').lastElementChild.textContent=t(connected?'计算核心已连接':'网页编辑模式');
    $('offline-note').hidden=connected;
    $('run-model').disabled=!connected;
  }
  async function api(path, payload) {
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,lang})});
    const value=await response.json(); if(!response.ok) throw new Error(value.error || response.statusText); return value;
  }
  function download(name,content,type='application/json') {
    const url=URL.createObjectURL(new Blob([content],{type})); const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function parseCSV(text) {
    if(!text.trim())fail('请选择文件或粘贴数据');
    text=text.replace(/^\uFEFF/,'');
    const first=text.split(/\r?\n/)[0];
    const delimiters=[',',';','\t'];
    const count=delimiter=>{let quoted=false,n=0;for(let i=0;i<first.length;i++){if(first[i]==='"'){if(quoted&&first[i+1]==='"')i++;else quoted=!quoted;}else if(first[i]===delimiter&&!quoted)n++;}return n;};
    const delimiter=delimiters.sort((a,b)=>count(b)-count(a))[0];
    const grid=[];let row=[],cell='',quoted=false;
    for(let i=0;i<text.length;i++){
      const c=text[i];
      if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}
      else if(c===delimiter&&!quoted){row.push(cell.trim());cell='';}
      else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell.trim());if(row.some(v=>v!==''))grid.push(row);row=[];cell='';}
      else cell+=c;
    }
    if(quoted)fail('CSV 引号未闭合');
    row.push(cell.trim());if(row.some(v=>v!==''))grid.push(row);
    const headers=grid.shift();
    if(!headers||headers.some(h=>!h)||new Set(headers).size!==headers.length||grid.some(r=>r.length!==headers.length))fail('列名须非空且唯一，数据行列数须一致。');
    if(!grid.length)fail('请选择文件或粘贴数据');
    return {headers,rows:grid.map(r=>Object.fromEntries(headers.map((h,i)=>[h,r[i]])))};
  }
  function getMapping() {return Object.fromEntries(Object.keys(mappingLabels).map(key=>[key,$('map-'+key)?.value||null]));}
  function renderMapping(preserve=false) {
    const previous=preserve?getMapping():{}; const box=$('mapping-fields');box.replaceChildren();
    for(const [key,label] of Object.entries(mappingLabels)){
      const guess=mappingHeaders.find(h=>(D.aliases[key]||[]).some(a=>a.toLocaleLowerCase()===h.toLocaleLowerCase()));
      const selected=preserve&&mappingHeaders.includes(previous[key])?previous[key]:guess||'';
      const input=field(box,key,label,selected,Object.fromEntries([['','不使用此列'],...mappingHeaders.map(h=>[h,h])])); input.id='map-'+key;
      input.addEventListener('change',()=>{changed();$('weather-preview').hidden=true;});
    }
  }
  function readColumns(preserve=false) {
    const parsed=parseCSV($('weather-text').value);
    if(JSON.stringify(parsed.headers)!==JSON.stringify(mappingHeaders)||!preserve){mappingHeaders=parsed.headers;renderMapping(preserve);}
    return parsed;
  }
  function renderWeatherSource() {$('weather-source').textContent=t(weatherSource);}
  function weatherPayload() {
    readColumns(true); const energy=cfg.pet_method==='modified_penman';
    return {text:$('weather-text').value,source:t(weatherSource),mapping:getMapping(), options:{date_format:$('date-format').value,precip_unit:$('precip-unit').value,energy,
      constant_temp_c:$('allow-constants').checked?numeric($('constant-temp').value,'temp_c'):null,
      constant_pet_mm:energy?0:($('allow-constants').checked?numeric($('constant-pet').value,'pet_mm'):null)}};
  }
  function localNormalize(payload) {
    const rows=parseCSV(payload.text).rows, m=payload.mapping,o=payload.options, energy=o.energy;
    if(!m.date||!m.precip_mm)fail('缺少日期或降水列');
    if(!m.temp_c&&o.constant_temp_c==null || (!energy&&!m.pet_mm&&o.constant_pet_mm==null))fail('缺少气温或 PET；请设置常数或映射列。');
    if(energy&&['solar_mj_m2_day','rh_percent','wind_m_s'].some(k=>!m[k]))fail('Modified Penman 需要辐射、湿度及风速列。');
    const used=['date','precip_mm','temp_c',...(energy?['solar_mj_m2_day','rh_percent','wind_m_s']:['pet_mm'])].map(k=>m[k]).filter(Boolean);
    if(new Set(used).size!==used.length)throw new Error('Each variable must use a distinct column');
    let previous=null;
    return rows.map(row=>{
      const parts=row[m.date].split(/[-/]/), order=o.date_format.split(/[-/]/), values=Object.fromEntries(order.map((k,i)=>[k,Number(parts[i])]));
      const day=new Date(Date.UTC(values['%Y'],values['%m']-1,values['%d']));
      if(parts.length!==3||!Number.isFinite(day.valueOf())||day.getUTCFullYear()!==values['%Y']||day.getUTCMonth()+1!==values['%m']||day.getUTCDate()!==values['%d']||(previous!=null&&day-previous!==86400000))fail('日期不连续、重复或格式无效');
      previous=day;
      const out={date:day.toISOString().slice(0,10)};
      for(const key of ['precip_mm','temp_c','pet_mm',...(energy?['solar_mj_m2_day','rh_percent','wind_m_s']:[])]){
        const raw=energy&&key==='pet_mm'?0:(m[key]?row[m[key]]:o[key==='temp_c'?'constant_temp_c':'constant_pet_mm']);
        if(raw==null||raw==='')fail('参数须为有限数值');
        const value=Number(String(raw).replace(',','.'));
        if(!Number.isFinite(value)||key!=='temp_c'&&value<0)fail('参数须为有限数值');out[key]=value;
      }
      out.precip_mm*=({mm:1,cm:10,inch:25.4})[o.precip_unit];
      if(energy&&(out.rh_percent>100||out.solar_mj_m2_day>60||out.wind_m_s>100))fail('参数须为有限数值');
      return out;
    });
  }
  function table(container,rows,keys,labels) {
    container.replaceChildren();const table=document.createElement('table'),head=document.createElement('thead'),header=document.createElement('tr');
    keys.forEach(k=>{const th=document.createElement('th');th.textContent=t(labels[k]||k);header.append(th);});head.append(header);table.append(head);
    const body=document.createElement('tbody');
    rows.forEach(row=>{const tr=document.createElement('tr');keys.forEach(k=>{const td=document.createElement('td');td.textContent=row[k]==null?'':typeof row[k]==='number'?readable(row[k],5):row[k];tr.append(td);});body.append(tr);});
    table.append(body);container.append(table);
  }
  async function previewWeather() {
    const payload=weatherPayload();
    const normalized=connected?(await api('/api/normalize',payload)).weather:localNormalize(payload);
    table($('weather-table'),normalized.slice(0,8),Object.keys(normalized[0]),{...mappingLabels,precip_mm:t('降水')+' (mm)',temp_c:t('气温')+' (°C)',pet_mm:'PET (mm)'});
    $('weather-days').textContent=`${normalized.length} ${t('天')} · ${normalized[0].date} → ${normalized.at(-1).date}`;
    $('weather-preview').hidden=false;
    return payload;
  }
  function renderResults() {
    $('empty-results').hidden=!!result;$('result-content').hidden=!result;$('download-results').hidden=!result;
    $('stale-note').hidden=!resultStale;
    if(!result)return;
    const s=result.summary;
    $('result-period').textContent=`${result.daily[0].date} → ${result.daily.at(-1).date} · ${s.days} ${t('天')}`;
    $('download-results').href=result.download_url;$('download-results').download='HELP_results.zip';
    const box=$('result-cards');box.replaceChildren();
    for(const [key,label] of [['precip_mm','降水'],['runoff_mm','径流'],['evapotranspiration_mm','蒸散'],['leachate_collected_mm','净收集'],['bottom_leakage_mm','底部外流']]){
      const card=document.createElement('div');card.className='result-card';card.innerHTML=`<p>${escapeHtml(t(label))}</p><b>${readable(s[key])}</b><small>mm · ${readable(s[key.replace('_mm','_m3')])} m³</small>`;box.append(card);
    }
    options($('chart-variable'),Object.fromEntries(Object.entries(columns).filter(([k])=>k!=='date')),$('chart-variable').value||'leachate_collected_mm');
    $('balance-note').textContent=`${t('逐日水量最大残差')}: ${s.maximum_absolute_daily_balance_error_mm.toExponential(3)} mm · ${t('逐层水量最大残差')}: ${s.maximum_absolute_layer_balance_error_mm.toExponential(3)} mm`;
    if (!resultView) resetResultView();
    for (const [id,key] of [['chart-start','start'],['chart-end','end']]) {
      $(id).min=result.daily[0].date; $(id).max=result.daily.at(-1).date; $(id).value=resultView[key];
    }
    options($('chart-step'),{day:'日',month:'月',year:'年'},resultView.step);
    document.querySelector('.range-presets').setAttribute('aria-label',t('图表时间范围'));
    renderResultView();
  }
  function resetResultView() {
    resultView={start:result.daily[0].date,end:result.daily.at(-1).date,step:'day'};
    resultPage=0;
  }
  function renderResultView() {
    if(!result)return;
    const error=timeSeries.rangeError(result.daily,resultView.start,resultView.end);
    $('chart-error').hidden=!error; $('chart-error').textContent=error?t(error):'';
    for(const id of ['chart-start','chart-end']) $(id).setAttribute('aria-invalid',String(!!error));
    $('result-table').closest('article').hidden=!!error;
    $('result-chart').hidden=!!error;
    if(error){$('result-chart').replaceChildren();$('chart-period').textContent='';return;}
    const rows=timeSeries.select(result.daily,resultView.start,resultView.end);
    const full=resultView.start===result.daily[0].date&&resultView.end===result.daily.at(-1).date;
    document.querySelectorAll('[data-range]').forEach(button=>{
      const expected=button.dataset.range==='all'?{start:result.daily[0].date,end:result.daily.at(-1).date}:timeSeries.recentRange(result.daily,Number(button.dataset.range));
      const active=button.dataset.range==='all'?full:!full&&expected.start===resultView.start&&expected.end===resultView.end;
      button.setAttribute('aria-pressed',String(active));
    });
    renderChart(rows);renderResultTable(rows);
  }
  function renderChart(rows) {
    if(!result)return;
    rows=rows||timeSeries.select(result.daily,resultView.start,resultView.end);
    const key=$('chart-variable').value, pointsData=timeSeries.aggregate(rows,key,resultView.step);
    const unit=resultView.step==='day'?'mm/day':'mm';
    $('chart-unit').textContent=t(resultView.step==='day'?'日水量（mm/day）':'所选时段内的汇总水量（mm）');
    $('chart-period').textContent=`${resultView.start} → ${resultView.end} · ${rows.length} ${t('天')} · ${pointsData.length} ${t('个数据点')}`;
    const xLabel=t({day:'日期（YYYY-MM-DD）',month:'月份（YYYY-MM）',year:'年份（YYYY）'}[resultView.step]);
    const yLabel=`${t(columns[key])} (${unit})`;
    const W=1000,H=360,left=104,right=35,top=26,bottom=78;
    const peak=pointsData.reduce((n,d)=>Math.max(n,d.value),0),max=peak>0?peak:1;
    const x=i=>left+(W-left-right)*(pointsData.length===1?.5:i/(pointsData.length-1));
    const y=n=>H-bottom-(H-top-bottom)*n/max;
    const points=pointsData.map((d,i)=>`${x(i).toFixed(2)},${y(d.value).toFixed(2)}`).join(' ');
    const grid=[0,.25,.5,.75,1].map(v=>`<line x1="${left}" x2="${W-right}" y1="${y(max*v)}" y2="${y(max*v)}" stroke="#e7ede2"/><text x="${left-12}" y="${y(max*v)+4}" text-anchor="end" fill="#62755e" font-size="13">${escapeHtml(readable(max*v))}</text>`).join('');
    const ticks=[...new Set(Array.from({length:Math.min(5,pointsData.length)},(_,i)=>Math.round(i*(pointsData.length-1)/Math.max(1,Math.min(5,pointsData.length)-1))))];
    const axis=ticks.map(i=>`<line x1="${x(i)}" x2="${x(i)}" y1="${H-bottom}" y2="${H-bottom+5}" stroke="#98ad92"/><text x="${x(i)}" y="${H-bottom+26}" text-anchor="${pointsData.length===1?'middle':i===0?'start':i===pointsData.length-1?'end':'middle'}" fill="#62755e" font-size="13">${pointsData[i].date}</text>`).join('');
    const axes=`<path d="M ${left} ${top} V ${H-bottom} H ${W-right}" fill="none" stroke="#98ad92" stroke-width="1"/><text class="x-axis-title" x="${(left+W-right)/2}" y="${H-14}" text-anchor="middle" fill="#354f3b" font-size="15" font-weight="500">${escapeHtml(xLabel)}</text><text class="y-axis-title" transform="translate(24 ${(top+H-bottom)/2}) rotate(-90)" text-anchor="middle" fill="#354f3b" font-size="15" font-weight="500">${escapeHtml(yLabel)}</text>`;
    const dots=pointsData.length<=366?pointsData.map((d,i)=>`<circle cx="${x(i)}" cy="${y(d.value)}" r="${pointsData.length===1?5:3}" fill="#398365"><title>${d.start} → ${d.end}: ${escapeHtml(readable(d.value,5))} ${unit} · ${d.days} ${t('天')}</title></circle>`).join(''):'';
    const label=`${t(columns[key])} · ${resultView.start} → ${resultView.end} (${unit})`;
    $('result-chart').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${escapeHtml(label)}"><title>${escapeHtml(label)}</title><desc>${escapeHtml(xLabel)}; ${escapeHtml(yLabel)}</desc>${grid}<polygon points="${x(0)},${H-bottom} ${points} ${x(pointsData.length-1)},${H-bottom}" fill="#e3eee1"/><polyline points="${points}" fill="none" stroke="#398365" stroke-width="1.8"/>${dots}${axis}${axes}</svg>`;
  }
  function renderResultTable(rows) {
    if(!result)return;
    rows=rows||timeSeries.select(result.daily,resultView.start,resultView.end);
    resultPage=Math.min(resultPage,Math.max(0,Math.ceil(rows.length/20)-1));
    const start=resultPage*20,end=Math.min(start+20,rows.length);
    table($('result-table'),rows.slice(start,end),Object.keys(columns),Object.fromEntries(Object.entries(columns).map(([k,v])=>[k,t(v)+(k==='date'?'':' (mm)')])));
    $('result-range').textContent=`${start+1}–${end} / ${rows.length}`;
    $('prev-page').disabled=resultPage===0;$('next-page').disabled=end>=rows.length;
  }
  $('language').addEventListener('change',()=>{if(guard()){lang=$('language').value;store('help-web-language',lang);renderLanguage();}else $('language').value=lang;});
  document.querySelectorAll('[data-page]').forEach(el=>el.addEventListener('click',()=>showPage(el.dataset.page)));
  document.querySelectorAll('[data-go]').forEach(el=>el.addEventListener('click',()=>showPage(el.dataset.go)));
  window.addEventListener('hashchange',()=>showPage(location.hash.slice(1)));
  $('site-name').addEventListener('change',()=>{cfg.site_name=$('site-name').value;persist();});
  $('load-example').addEventListener('click',()=>{if(guard()){const example=D.examples[$('example').value];cfg=clone(example.config);cfg.site_name=t(example.label);activeId=cfg.layers[0].id;persist();renderProfile();message(t('已载入样例'));}});
  $('layer-form').addEventListener('input',()=>{layerDirty=true;});
  $('settings-form').addEventListener('input',()=>{settingsDirty=true;});
  $('layer-kind').addEventListener('change',()=>{$('type-change').hidden=$('layer-kind').value===cfg.layers.find(l=>l.id===activeId).kind;});
  $('apply-kind').addEventListener('click',()=>{const index=cfg.layers.findIndex(l=>l.id===activeId),name=cfg.layers[index].name;cfg.layers[index]={...clone(D.defaults[$('layer-kind').value]),id:activeId,name};if(cfg.layers[index].kind==='geomembrane'&&cfg.recirculation_target_id===activeId){cfg.recirculation_target_id=null;cfg.recirculation_fraction=0;}persist();renderProfile();});
  $('layer-form').addEventListener('submit',attempt(event=>{
    event.preventDefault();const index=cfg.layers.findIndex(l=>l.id===activeId),layer={...cfg.layers[index],name:$('layer-name').value};
    if($('layer-kind').value!==layer.kind)throw new Error(t('更换类型将重置该层参数。'));
    for(const input of $('layer-fields').querySelectorAll('input,select'))layer[input.name]=input.tagName==='SELECT'?input.value:numeric(input.value,input.name);
    cfg.layers[index]=validateLayer(layer);layerDirty=false;persist();renderStats();renderLayers();renderLayer();message(t('已保存'));
  }));
  $('settings-form').addEventListener('submit',attempt(event=>{
    event.preventDefault();const updated=clone(cfg);
    for(const input of $('settings-fields').querySelectorAll('input,select'))updated[input.name]=input.tagName==='SELECT'?(input.value||null):numeric(input.value,input.name);
    cfg=validateLocal(updated);settingsDirty=false;persist();renderStats();message(t('已保存'));
  }));
  $('add-layer').addEventListener('click',()=>{if(!guard())return;const kind=$('new-kind').value;let i=1;while(cfg.layers.some(l=>l.id===`${kind}_${i}`))i++;const id=`${kind}_${i}`;cfg.layers.push({...clone(D.defaults[kind]),id,name:id});activeId=id;persist();renderProfile();});
  for(const [id,delta] of [['move-up',-1],['move-down',1]])$(id).addEventListener('click',()=>{if(!guard())return;const index=cfg.layers.findIndex(l=>l.id===activeId),next=index+delta;if(next<0||next>=cfg.layers.length)return;[cfg.layers[index],cfg.layers[next]]=[cfg.layers[next],cfg.layers[index]];persist();renderProfile();});
  $('delete-layer').addEventListener('click',()=>{if(cfg.layers.length<=1||!guard())return;const index=cfg.layers.findIndex(l=>l.id===activeId);cfg.layers.splice(index,1);if(cfg.recirculation_target_id===activeId){cfg.recirculation_target_id=null;cfg.recirculation_fraction=0;}activeId=cfg.layers[Math.min(index,cfg.layers.length-1)].id;persist();renderProfile();});
  $('validate').addEventListener('click',attempt(async()=>{if(!guard())return;const clean=validateLocal(cfg);if(connected){const value=await api('/api/validate',{config:clean});cfg=value.config;message([t('配置校验通过'),...value.warnings].join('\n'));}else message(t('配置校验通过'));store('help-web-profile',cfg);}));
  $('export-config').addEventListener('click',attempt(()=>{if(!guard())return;download('profile.json',JSON.stringify(validateLocal(cfg),null,2));}));
  $('import-config').addEventListener('click',()=>{if(guard())$('config-file').click();});
  $('config-file').addEventListener('change',attempt(async()=>{const file=$('config-file').files[0];if(!file)return;const raw=JSON.parse((await file.text()).replace(/^\uFEFF/,''));cfg=connected?(await api('/api/validate',{config:raw})).config:validateLocal(raw);activeId=cfg.layers[0].id;persist();renderProfile();message(t('配置已导入。'));$('config-file').value='';}));
  $('read-columns').addEventListener('click',attempt(()=>{readColumns();message(t('已保存'));}));
  $('import-weather').addEventListener('click',()=>$('weather-file').click());
  $('weather-file').addEventListener('change',attempt(async()=>{
    const file=$('weather-file').files[0];if(!file)return;const bytes=await file.arrayBuffer();let text;
    try{text=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{text=new TextDecoder('gb18030',{fatal:true}).decode(bytes);}
    $('weather-text').value=text;weatherSource=file.name;renderWeatherSource();readColumns();changed();$('weather-preview').hidden=true;$('weather-file').value='';
  }));
  $('sample-weather').addEventListener('click',()=>{$('weather-text').value=D.weather[cfg.pet_method];weatherSource='合成示例（非实测）';$('date-format').value='%Y-%m-%d';$('precip-unit').value='mm';readColumns();renderWeatherSource();changed();$('weather-preview').hidden=true;});
  $('weather-text').addEventListener('input',()=>{weatherSource='粘贴 / 本地文件';renderWeatherSource();changed();$('weather-preview').hidden=true;});
  $('allow-constants').addEventListener('change',()=>{$('constant-temp').disabled=$('constant-pet').disabled=!$('allow-constants').checked;});
  for(const id of ['date-format','precip-unit','constant-temp','constant-pet','allow-constants'])$(id).addEventListener('change',()=>{changed();$('weather-preview').hidden=true;});
  $('preview-weather').addEventListener('click',attempt(previewWeather));
  $('run-model').addEventListener('click',attempt(async()=>{
    if(!connected)fail('使用 Start_Web.cmd 启动后再计算');
    if(!guard())return;
    const config=validateLocal(cfg), payload=await previewWeather(), started=revision;
    $('run-model').disabled=true;$('run-model').textContent=t('正在计算…');
    try {result=await api('/api/run',{...payload,config});resetResultView();resultStale=revision!==started;showPage('results');message(t('已保存'));}
    finally {$('run-model').disabled=false;$('run-model').textContent=t('运行模型 →');}
  }));
  $('chart-variable').addEventListener('change',renderResultView);
  $('chart-controls').addEventListener('submit',event=>event.preventDefault());
  for(const [id,key] of [['chart-start','start'],['chart-end','end'],['chart-step','step']]) {
    $(id).addEventListener('change',()=>{if(!result)return;resultView[key]=$(id).value;resultPage=0;renderResultView();});
  }
  document.querySelectorAll('[data-range]').forEach(button=>button.addEventListener('click',()=>{
    if(!result)return;
    const range=button.dataset.range==='all'?{start:result.daily[0].date,end:result.daily.at(-1).date}:timeSeries.recentRange(result.daily,Number(button.dataset.range));
    Object.assign(resultView,range);$('chart-start').value=range.start;$('chart-end').value=range.end;resultPage=0;renderResultView();
  }));
  $('prev-page').addEventListener('click',()=>{resultPage=Math.max(0,resultPage-1);renderResultTable();});
  $('next-page').addEventListener('click',()=>{resultPage++;renderResultTable();});
  page=location.hash.slice(1)||'profile';renderLanguage();
  if(location.protocol==='http:'||location.protocol==='https:')fetch('api/health').then(r=>r.ok?r.json():Promise.reject()).then(v=>{connected=v.status==='ready'&&v.interface==='web';renderConnection();}).catch(()=>{connected=false;renderConnection();});
})();
