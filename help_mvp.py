"""HELP-inspired configurable daily water budget. Not EPA HELP; research only."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import random
import re
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from processes import amc2_cn,moisture_cn,modified_penman_pet,help_lateral_rate,giroud_contact_rate

VERSION = '2.3.1'
KINDS = ('soil', 'waste', 'drainage', 'barrier', 'geomembrane')
COMMON = {'id', 'name', 'kind', 'thickness_mm', 'ksat_mm_day'}
POROUS = {'porosity', 'field_capacity', 'wilting_point', 'initial_theta', 'brooks_corey_lambda'}
DRAIN = {'lateral_ksat_mm_day', 'slope_fraction', 'drainage_length_m'}
MEMBRANE = {'leakage_multiplier'}
MEMBRANE_EXTRA = {'leakage_model','pinhole_density_ha','pinhole_area_mm2','defect_density_ha','defect_area_mm2'}
PROCESS_KEYS = {'runoff_method','surface_slope_fraction','surface_length_m','vegetation_class',
                'infiltration_index','pet_method','latitude_deg','lateral_method','et_extraction',
                'max_lai','growing_start_day','growing_end_day','evaporation_depth_mm'}
SETTINGS = {'schema_version', 'site_name', 'area_m2', 'curve_number', 'substeps_per_day',
            'root_depth_mm', 'snow_temperature_c', 'melt_temperature_c',
            'degree_day_melt_mm_per_c_day', 'snow_sublimation_pet_fraction',
            'recirculation_fraction', 'recirculation_target_id', 'layers'} | PROCESS_KEYS


def number(value, label, low=None, high=None, strict_low=False):
    try:
        finite = math.isfinite(value)
    except (TypeError, ValueError, OverflowError):
        finite = False
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not finite:
        raise ValueError(f'{label}: 必须为有限数值（不能是字符串、布尔值、NaN 或 Infinity）')
    if low is not None and (value <= low if strict_low else value < low):
        raise ValueError(f'{label}: 必须 {">" if strict_low else ">="} {low}')
    if high is not None and value > high:
        raise ValueError(f'{label}: 必须 <= {high}')
    return float(value)


def default_layer(kind='soil', layer_id='layer_1'):
    if kind not in KINDS:
        raise ValueError('未知层类型')
    d = dict(id=layer_id, name=layer_id, kind=kind, thickness_mm=600., ksat_mm_day=75.)
    if kind == 'geomembrane':
        return dict(d, thickness_mm=1.5, ksat_mm_day=0.001, leakage_multiplier=0.1,
                    leakage_model='empirical',pinhole_density_ha=0.,pinhole_area_mm2=.784,
                    defect_density_ha=0.,defect_area_mm2=100.)
    d.update(porosity=0.46, field_capacity=0.26, wilting_point=0.10,
             initial_theta=0.30, brooks_corey_lambda=0.55)
    if kind == 'waste':
        d.update(thickness_mm=2000., ksat_mm_day=65., porosity=0.5,
                 field_capacity=0.2, wilting_point=0.07, initial_theta=0.28)
    elif kind == 'drainage':
        d.update(thickness_mm=300., ksat_mm_day=2000., porosity=0.38,
                 field_capacity=0.06, wilting_point=0.02, initial_theta=0.12,
                 lateral_ksat_mm_day=40000., slope_fraction=0.03, drainage_length_m=30.)
    elif kind == 'barrier':
        d.update(thickness_mm=600., ksat_mm_day=0.02, porosity=0.45,
                 field_capacity=0.35, wilting_point=0.15, initial_theta=0.35)
    return d


@dataclass(frozen=True)
class Layer:
    id: str
    name: str
    kind: str
    thickness_mm: float
    ksat_mm_day: float
    porosity: float = 0.
    field_capacity: float = 0.
    wilting_point: float = 0.
    initial_theta: float = 0.
    brooks_corey_lambda: float = 0.5
    lateral_ksat_mm_day: float = 0.
    slope_fraction: float = 0.
    drainage_length_m: float = 30.
    leakage_multiplier: float = 1.
    leakage_model: str = 'empirical'
    pinhole_density_ha: float = 0.
    pinhole_area_mm2: float = .784
    defect_density_ha: float = 0.
    defect_area_mm2: float = 100.

    @staticmethod
    def from_dict(d):
        if not isinstance(d, dict):
            raise ValueError('每一层必须是 JSON 对象')
        kind = d.get('kind')
        if kind not in KINDS:
            raise ValueError(f'kind 必须是 {KINDS}')
        allowed = COMMON | (MEMBRANE if kind == 'geomembrane' else POROUS)
        optional=MEMBRANE_EXTRA if kind=='geomembrane' else set()
        if kind == 'drainage':
            allowed |= DRAIN
        if set(d) - allowed - optional:
            raise ValueError(f'{d.get("id", "layer")}: 该类型不适用的字段 {sorted(set(d)-allowed-optional)}')
        required = allowed - {'name', 'brooks_corey_lambda'}
        if required - set(d):
            raise ValueError(f'{d.get("id", "layer")}: 缺少字段 {sorted(required-set(d))}')
        ident = d['id']
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', ident):
            raise ValueError('id 须以英文字母开头，最多64位，只含字母、数字、_、-')
        name = d.get('name', ident)
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f'{ident}: name 不能为空')
        clean = dict(d, name=name)
        for k in (allowed | optional) - {'id', 'name', 'kind','leakage_model'}:
            if k in clean:
                clean[k] = number(clean[k], f'{ident}.{k}', 0)
        for k in ('thickness_mm', 'brooks_corey_lambda', 'drainage_length_m'):
            if k in clean:
                number(clean[k], f'{ident}.{k}', 0, strict_low=True)
        if kind == 'geomembrane':
            number(clean['leakage_multiplier'], f'{ident}.leakage_multiplier', 0, 1)
            if clean.get('leakage_model','empirical') not in ('empirical','giroud_good','giroud_poor'):
                raise ValueError(f'{ident}: invalid leakage_model')
            for key in ('pinhole_area_mm2','defect_area_mm2'):
                number(clean.get(key,.784 if key=='pinhole_area_mm2' else 100.),key,0,strict_low=True)
        else:
            wp, fc, por = (clean[k] for k in ('wilting_point', 'field_capacity', 'porosity'))
            if not 0 <= wp < fc < por <= 1:
                raise ValueError(f'{ident}: 要求 0 <= 萎蔫点 < 田间持水量 < 孔隙率 <= 1')
            number(clean['initial_theta'], f'{ident}.initial_theta', 0, por)
            if kind == 'drainage':
                number(clean['slope_fraction'], f'{ident}.slope_fraction', 0, 1)
        layer = Layer(**clean)
        if not math.isfinite(layer.sat_mm):
            raise ValueError(f'{ident}: 厚度与孔隙率的乘积溢出')
        return layer

    @property
    def field_mm(self):
        return self.field_capacity * self.thickness_mm

    @property
    def wilt_mm(self):
        return self.wilting_point * self.thickness_mm

    @property
    def sat_mm(self):
        return self.porosity * self.thickness_mm


def migrate_config(cfg):
    """Explicitly translate the supplied v1 MVP schema; no numeric parity claim."""
    cfg = copy.deepcopy(cfg)
    if cfg.get('schema_version') == 2:
        return cfg
    if cfg.get('schema_version') not in (None, 1):
        raise ValueError('不支持此 schema_version')
    old_layers = cfg.get('layers', [])
    used = set()
    for i, d in enumerate(old_layers):
        ident = re.sub('[^A-Za-z0-9_-]', '_', str(d.get('name', f'layer_{i+1}')))
        if not ident or not ident[0].isalpha() or not ident[0].isascii():
            ident = f'layer_{i+1}'
        ident = ident[:56]
        while ident in used:
            ident += '_x'
        used.add(ident)
        d['id'] = ident
        if d.get('kind') == 'drain':
            d['kind'] = 'drainage'
    target = cfg.pop('recirculation_target_index', max(0, len(old_layers)-1))
    if type(target) is not int or not 0 <= target < len(old_layers):
        raise ValueError('旧版 recirculation_target_index 无效')
    cfg['recirculation_target_id'] = old_layers[target]['id']
    liner = cfg.pop('liner', None)
    if liner is not None:
        # Legacy lumped basal liner becomes a named porous barrier with an
        # effective conductivity. This is intentionally documented as a change.
        k = number(liner['ksat_mm_day'], 'liner.ksat_mm_day', 0)
        factor = number(liner.get('geomembrane_leakage_multiplier', 1), 'liner.multiplier', 0, 1)
        d = default_layer('barrier', 'legacy_liner')
        while d['id'] in used:
            d['id'] += '_x'
        d.update(name='旧版底衬等效阻隔层', thickness_mm=liner['thickness_mm'],
                 ksat_mm_day=k*factor)
        old_layers.append(d)
    cfg['schema_version'] = 2
    return cfg


def validate_config(cfg):
    if not isinstance(cfg, dict):
        raise ValueError('配置必须为 JSON 对象')
    if cfg.get('schema_version') != 2 or type(cfg.get('schema_version')) is not int:
        raise ValueError('需要 schema_version: 2；旧版请先用 migrate 命令转换')
    if set(cfg) - SETTINGS:
        raise ValueError(f'未知全局字段 {sorted(set(cfg)-SETTINGS)}')
    if not isinstance(cfg.get('layers'), list) or not cfg['layers']:
        raise ValueError('至少需要一层')
    out = copy.deepcopy(cfg)
    layers = [Layer.from_dict(x) for x in out['layers']]
    if len({x.id for x in layers}) != len(layers):
        raise ValueError('各层 id 必须唯一；重排时 id 保持不变')
    if all(x.kind == 'geomembrane' for x in layers):
        raise ValueError('至少需要一个有储水能力的多孔层')
    defaults = dict(area_m2=10000., curve_number=78., substeps_per_day=24,
                    root_depth_mm=500., snow_temperature_c=0., melt_temperature_c=0.,
                    degree_day_melt_mm_per_c_day=3., snow_sublimation_pet_fraction=0.15,
                    recirculation_fraction=0., recirculation_target_id=None,
                    runoff_method='fixed',surface_slope_fraction=.04,surface_length_m=152.4,
                    vegetation_class='good',infiltration_index=.12,pet_method='provided',
                    latitude_deg=45.,lateral_method='darcy',et_extraction='legacy',
                    max_lai=3.,growing_start_day=100,growing_end_day=300,evaporation_depth_mm=150.)
    for k, value in defaults.items():
        out.setdefault(k, value)
    enums={'runoff_method':('fixed','help_user','help_slope','help_vegetation'),
           'pet_method':('provided','modified_penman'),'lateral_method':('darcy','help_steady'),
           'vegetation_class':('bare','poor','fair','good','excellent'),'et_extraction':('legacy','lai_partition')}
    for k,choices in enums.items():
        if out[k] not in choices:
            raise ValueError(f'{k}: invalid method')
    for k in defaults.keys() - {'recirculation_target_id', 'substeps_per_day'} - enums.keys():
        number(out[k], k)
    number(out['latitude_deg'],'latitude_deg',-89,89)
    number(out['surface_slope_fraction'],'surface_slope_fraction',0,1,strict_low=True)
    number(out['surface_length_m'],'surface_length_m',0,strict_low=True)
    number(out['infiltration_index'],'infiltration_index',0,.5)
    number(out['max_lai'],'max_lai',0,10)
    number(out['evaporation_depth_mm'],'evaporation_depth_mm',0,strict_low=True)
    for key in ('growing_start_day','growing_end_day'):
        if type(out[key]) is not int or not 1<=out[key]<=366:
            raise ValueError(f'{key}: require integer 1..366')
    if out['growing_start_day']==out['growing_end_day']:
        raise ValueError('Growing-season start and end must differ')
    for i,l in enumerate(layers):
        if l.kind=='geomembrane' and l.leakage_model!='empirical':
            if i+1>=len(layers) or layers[i+1].kind!='barrier' or layers[i+1].ksat_mm_day>=86.4:
                raise ValueError(f'{l.id}: Giroud contact requires an immediately underlying barrier with Ks < 86.4 mm/day')
            area=(l.pinhole_density_ha*l.pinhole_area_mm2+l.defect_density_ha*l.defect_area_mm2)/1e10
            if area>=1:
                raise ValueError(f'{l.id}: defect area must be below site area')
    number(out['area_m2'], 'area_m2', 0, strict_low=True)
    number(out['curve_number'], 'curve_number', 0, 100, strict_low=True)
    if out['curve_number'] == 100:
        raise ValueError('curve_number 必须小于100')
    for k in ('root_depth_mm', 'degree_day_melt_mm_per_c_day'):
        number(out[k], k, 0)
    for k in ('snow_sublimation_pet_fraction', 'recirculation_fraction'):
        number(out[k], k, 0, 1)
    if type(out['substeps_per_day']) is not int or not 1 <= out['substeps_per_day'] <= 1440:
        raise ValueError('substeps_per_day 须是 1..1440 的整数')
    target = out['recirculation_target_id']
    if target is not None and (not isinstance(target, str) or target not in {x.id for x in layers if x.kind != 'geomembrane'}):
        raise ValueError('回灌目标必须为现有多孔层的 id')
    if out['recirculation_fraction'] > 0 and target is None:
        raise ValueError('启用回灌时必须选择 recirculation_target_id')
    if 'site_name' in out and not isinstance(out['site_name'], str):
        raise ValueError('site_name 须是字符串')
    return out


def profile_warnings(cfg):
    warnings = []
    kinds = [d['kind'] for d in cfg['layers']]
    if kinds[0] in ('barrier', 'geomembrane'):
        warnings.append('顶层是阻隔材料：允许计算，但不是 EPA HELP 的有效顶层布置；将限制表面入渗。')
    if any(kinds[i] == kinds[i+1] and kinds[i] in ('barrier', 'geomembrane') for i in range(len(kinds)-1)):
        warnings.append('存在相邻阻隔层或膜；本程序允许自由排列，不代表符合 EPA HELP 层序规则。')
    if 'drainage' not in kinds:
        warnings.append('没有导排层，侧向收集量将为零。')
    if kinds[-1] not in ('barrier', 'geomembrane'):
        warnings.append('底边界为自由排水；bottom_leakage 表示底部流出量，不是防渗系统失效量。')
    return warnings


def runoff_curve_number(p_mm, cn):
    if p_mm <= 0:
        return 0.
    s = 25400. / cn - 254.
    return (p_mm - .2*s)**2 / (p_mm + .8*s) if p_mm > .2*s else 0.


def conductivity(layer, storage_mm):
    se = max(0., min(1., (storage_mm/layer.thickness_mm-layer.wilting_point)
                         / (layer.porosity-layer.wilting_point)))
    return layer.ksat_mm_day * se**(3.+2./layer.brooks_corey_lambda)


class HelpMVP:
    def __init__(self, cfg):
        self.cfg = validate_config(cfg)
        self.layers = [Layer.from_dict(x) for x in self.cfg['layers']]
        self.s = [x.initial_theta*x.thickness_mm for x in self.layers]
        self.swe = self.pending_recirculation_mm = 0.
        self.last_date = None
        self.layer_rows = []
        self.nstep = self.cfg['substeps_per_day']
        self.rec_target = next((i for i, x in enumerate(self.layers)
                                if x.id == self.cfg['recirculation_target_id']), None)
        remaining = self.cfg['root_depth_mm']
        self.root_weights = []
        for layer in self.layers:
            overlap = min(max(remaining, 0), layer.thickness_mm)
            self.root_weights.append(overlap if layer.kind in ('soil', 'waste') else 0.)
            remaining -= overlap
            if layer.kind in ('barrier', 'geomembrane'):
                remaining = 0.  # roots cannot cross a liner in this surrogate

    def storage(self):
        return math.fsum(self.s) + self.swe + self.pending_recirculation_mm

    def head(self, i):
        l = self.layers[i]
        if l.kind == 'geomembrane':
            return 0.
        return min(l.thickness_mm, max(0., self.s[i]-l.field_mm)/(l.porosity-l.field_capacity))

    def _destination(self, i, upstream_head, dt):
        """Return next porous receiver + rate limit through zero-storage membranes."""
        limit = math.inf
        membranes = []
        j = i+1
        while j < len(self.layers) and self.layers[j].kind == 'geomembrane':
            l = self.layers[j]
            rate = l.ksat_mm_day*(1.+upstream_head/l.thickness_mm)*l.leakage_multiplier
            if l.leakage_model!='empirical':
                barrier=self.layers[j+1]
                defect_rate=giroud_contact_rate(upstream_head,barrier.ksat_mm_day,barrier.thickness_mm,
                    l.leakage_model,l.pinhole_density_ha,l.pinhole_area_mm2,l.defect_density_ha,l.defect_area_mm2)
                # Retain explicit intact membrane contribution; multiplier is unused in this mode.
                rate=l.ksat_mm_day*(1.+upstream_head/l.thickness_mm)+defect_rate
            limit = min(limit, rate*dt)
            membranes.append(j)
            j += 1
        if j < len(self.layers):
            l = self.layers[j]
            rate = l.ksat_mm_day
            if l.kind == 'barrier':
                rate *= 1.+upstream_head/l.thickness_mm
            limit = min(limit, rate*dt, max(0., l.sat_mm-self.s[j]))
        return j, limit, membranes

    def _inject(self, index, mm, incoming):
        l = self.layers[index]
        fit = min(mm, max(0., l.sat_mm-self.s[index]))
        self.s[index] += fit
        incoming[index] += fit
        return mm-fit

    def extract_et(self, demand, et, extraction_weights=None):
        extraction_weights=self.root_weights if extraction_weights is None else extraction_weights
        active = [i for i, w in enumerate(extraction_weights) if w > 0 and self.s[i] > self.layers[i].wilt_mm]
        remaining = demand
        for _ in range(len(active)+1):
            if not active or remaining <= 1e-12:
                break
            weights = sum(extraction_weights[i] for i in active)
            taken = 0.
            for i in active:
                q = min(remaining*extraction_weights[i]/weights, max(0., self.s[i]-self.layers[i].wilt_mm))
                self.s[i] -= q
                et[i] += q
                taken += q
            remaining -= taken
            active = [i for i in active if self.s[i] > self.layers[i].wilt_mm+1e-12]
        return demand-remaining

    def routing_step(self, dt, incoming, vertical, lateral, heads):
        leakage = 0.
        for i, l in enumerate(self.layers):
            if l.kind == 'geomembrane':
                continue
            wet = max(0., self.s[i]-l.field_mm)
            h = self.head(i)
            heads[i] = max(heads[i], h)
            if wet <= 0:
                continue
            rate = l.ksat_mm_day*(1.+h/l.thickness_mm) if l.kind == 'barrier' else conductivity(l, self.s[i])
            j, limit, membranes = self._destination(i, h, dt)
            qv = min(rate*dt, limit)
            ql = 0.
            if l.kind == 'drainage':
                ratio = h/(l.drainage_length_m*1000.)
                ql = l.lateral_ksat_mm_day*ratio*(l.slope_fraction+ratio)*dt
                if self.cfg['lateral_method']=='help_steady':
                    ql=help_lateral_rate(h,l.lateral_ksat_mm_day,l.slope_fraction,l.drainage_length_m)*dt
            scale = min(1., wet/(qv+ql)) if qv+ql > 0 else 0.
            qv, ql = qv*scale, ql*scale
            self.s[i] -= qv+ql
            vertical[i] += qv
            lateral[i] += ql
            for m in membranes:
                incoming[m] += qv
                vertical[m] += qv
            if j < len(self.layers):
                self.s[j] += qv
                incoming[j] += qv
            else:
                leakage += qv
        return leakage

    def day(self, weather):
        try:
            today = date.fromisoformat(weather['date'])
            p, t, pet = (float(weather[k]) for k in ('precip_mm', 'temp_c', 'pet_mm'))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError('气象需有 ISO 日期、降水、温度、PET 数值') from e
        if self.last_date is not None and today != self.last_date+timedelta(days=1):
            raise ValueError('日期必须逐日连续且不能重复')
        if not all(math.isfinite(v) for v in (p,t,pet)) or p < 0 or pet < 0:
            raise ValueError('气象需为有限值且降水、PET 非负')
        if self.cfg['pet_method']=='modified_penman':
            pet=modified_penman_pet(weather['date'],t,weather.get('solar_mj_m2_day'),
                weather.get('rh_percent'),weather.get('wind_m_s'),self.cfg['latitude_deg'],p,
                snow=self.swe>5. or (t<=self.cfg['snow_temperature_c'] and p>5.))
        before, layer_before = self.storage(), self.s.copy()
        n = len(self.layers)
        incoming, vertical, lateral, et, heads = ([0.]*n for _ in range(5))
        rain = p if t > self.cfg['snow_temperature_c'] else 0.
        self.swe += p-rain
        sub = min(self.swe, pet*self.cfg['snow_sublimation_pet_fraction'])
        self.swe -= sub
        melt = min(self.swe, self.cfg['degree_day_melt_mm_per_c_day']*max(0., t-self.cfg['melt_temperature_c']))
        self.swe -= melt
        liquid = rain+melt
        cn=self.cfg['curve_number']
        if self.cfg['runoff_method']!='fixed':
            cn2=amc2_cn(self.cfg['runoff_method'],cn,self.cfg['surface_slope_fraction'],
                self.cfg['surface_length_m'],self.cfg['vegetation_class'],self.cfg['infiltration_index'])
            cn=moisture_cn(cn2,self.layers,self.s,self.cfg['root_depth_mm'])
        direct = runoff_curve_number(liquid, cn)
        potential = liquid-direct
        recycled_today = self.pending_recirculation_mm
        self.pending_recirculation_mm = 0.
        rejected = self._inject(self.rec_target, recycled_today, incoming) if self.rec_target is not None else 0.
        saturation = leakage = soil_et = infiltration = 0.
        evaporation=transpiration=0.
        lai=0.
        if self.cfg['et_extraction']=='lai_partition':
            start,end=self.cfg['growing_start_day'],self.cfg['growing_end_day']
            duration=(end-start)%366
            elapsed=(today.timetuple().tm_yday-start)%366
            if elapsed<=duration:
                lai=self.cfg['max_lai']*math.sin(math.pi*elapsed/duration)
        evaporation_weights=[]
        depth=0.
        for l,root in zip(self.layers,self.root_weights):
            overlap=max(0.,min(l.thickness_mm,self.cfg['evaporation_depth_mm']-depth))
            evaporation_weights.append(min(root,overlap))
            depth+=l.thickness_mm
        for _ in range(self.nstep):
            dt = 1./self.nstep
            j, cap, membranes = self._destination(-1, 0., dt)
            q = min(potential*dt, cap)
            if j < n:
                excess = self._inject(j, q, incoming)
                q -= excess
            else:
                leakage += q
            for m in membranes:
                incoming[m] += q
                vertical[m] += q
            infiltration += q
            saturation += potential*dt-q
            if self.cfg['et_extraction']=='lai_partition':
                e_demand=(pet-sub)*dt*math.exp(-.5*lai)
                e_actual=self.extract_et(e_demand,et,evaporation_weights)
                t_demand=(pet-sub)*dt-e_demand if t>0 else 0.
                t_actual=self.extract_et(t_demand,et)
                evaporation+=e_actual; transpiration+=t_actual
                soil_et+=e_actual+t_actual
            else:
                soil_et += self.extract_et((pet-sub)*dt, et)
            leakage += self.routing_step(dt, incoming, vertical, lateral, heads)
        rec_frac = self.cfg['recirculation_fraction']
        gross = math.fsum(lateral)
        self.pending_recirculation_mm = gross*rec_frac
        collected = gross-self.pending_recirculation_mm
        runoff = direct+saturation+rejected
        after = self.storage()
        residual = before+p-runoff-sub-soil_et-collected-leakage-after
        self.layer_rows = []
        for i, l in enumerate(self.layers):
            r = layer_before[i]+incoming[i]-vertical[i]-lateral[i]-et[i]-self.s[i]
            if not math.isfinite(r) or abs(r) > 1e-7 or self.s[i] < -1e-8 or self.s[i] > l.sat_mm+1e-8:
                raise ArithmeticError(f'{l.id}: 层水量平衡或储水边界失败 {r}')
            self.layer_rows.append(dict(date=today.isoformat(), layer_id=l.id, layer_name=l.name,
                                       kind=l.kind, storage_before_mm=layer_before[i], inflow_mm=incoming[i],
                                       vertical_out_mm=vertical[i], lateral_gross_mm=lateral[i],
                                       collected_mm=lateral[i]*(1-rec_frac), recirculated_mm=lateral[i]*rec_frac,
                                       et_mm=et[i], storage_mm=self.s[i],
                                       theta=self.s[i]/l.thickness_mm if l.kind != 'geomembrane' else None,
                                       head_peak_mm=heads[i], balance_error_mm=r))
        if not math.isfinite(residual) or abs(residual) > 1e-7:
            raise ArithmeticError(f'日水量平衡失败 {residual}')
        self.last_date = today
        return dict(date=today.isoformat(), precip_mm=p, temp_c=t, pet_mm=pet, effective_cn=cn,
                    lai=lai if self.cfg['et_extraction']=='lai_partition' else None,
                    soil_evaporation_mm=evaporation if self.cfg['et_extraction']=='lai_partition' else None,
                    transpiration_mm=transpiration if self.cfg['et_extraction']=='lai_partition' else None,rain_mm=rain,
                    snowfall_mm=p-rain, snowmelt_mm=melt, runoff_mm=runoff, direct_runoff_mm=direct,
                    saturation_runoff_mm=saturation, recirculation_surface_runoff_mm=rejected,
                    infiltration_mm=infiltration, et_mm=sub+soil_et, lateral_gross_mm=gross,
                    leachate_collected_mm=collected, bottom_leakage_mm=leakage,
                    liner_leakage_mm=leakage, recirculated_today_mm=recycled_today,
                    recirculated_next_day_mm=self.pending_recirculation_mm, snowpack_mm=self.swe,
                    soil_storage_mm=math.fsum(self.s), total_storage_mm=after,
                    head_peak_mm=max(heads), balance_error_mm=residual,
                    maximum_layer_balance_error_mm=max(abs(r['balance_error_mm']) for r in self.layer_rows))


def load_weather(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    validate_weather(rows)
    return rows


def validate_weather(rows):
    if not rows:
        raise ValueError('气象表为空')
    previous = None
    for row in rows:
        try:
            d = date.fromisoformat(row['date'])
            p,t,pet = (float(row[k]) for k in ('precip_mm','temp_c','pet_mm'))
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError('气象需要 date,precip_mm,temp_c,pet_mm 四列') from e
        if previous is not None and d != previous+timedelta(days=1):
            raise ValueError(f'日期不连续或重复: {d}')
        if not all(math.isfinite(x) for x in (p,t,pet)) or p < 0 or pet < 0:
            raise ValueError(f'{d}: 气象数值无效')
        previous = d


def save_csv(path, rows):
    if rows:
        with Path(path).open('w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def aggregation(rows, keyfn):
    groups = {}
    for row in rows:
        groups.setdefault(keyfn(row['date']), []).append(row)
    cols = ['precip_mm','runoff_mm','et_mm','leachate_collected_mm','bottom_leakage_mm','balance_error_mm']
    return [dict(period=k, days=len(ds), **{c:math.fsum(d[c] for d in ds) for c in cols},
                 end_storage_mm=ds[-1]['total_storage_mm'], max_head_mm=max(d['head_peak_mm'] for d in ds))
            for k,ds in groups.items()]


def simulate(config, weather):
    weather = list(weather)
    validate_weather(weather)  # validate whole forcing before mutating any state
    sim = HelpMVP(config)
    initial = sim.storage()
    days, layer_rows = [], []
    for w in weather:
        days.append(sim.day(w))
        layer_rows.extend(sim.layer_rows)
    total = lambda k: math.fsum(d[k] for d in days)
    summary = dict(version=VERSION, days=len(days), initial_storage_mm=initial,
                   final_storage_mm=sim.storage(), precip_mm=total('precip_mm'),
                   runoff_mm=total('runoff_mm'), evapotranspiration_mm=total('et_mm'),
                   leachate_collected_mm=total('leachate_collected_mm'),
                   bottom_leakage_mm=total('bottom_leakage_mm'),
                   final_pending_recirculation_mm=sim.pending_recirculation_mm,
                   maximum_absolute_daily_balance_error_mm=max(abs(d['balance_error_mm']) for d in days),
                   maximum_absolute_layer_balance_error_mm=max(abs(d['balance_error_mm']) for d in layer_rows),
                   profile_warnings=profile_warnings(sim.cfg),
                   warning='独立近似研究模型；不是 EPA HELP，尚未对官方 HELP 或实测数据验证。')
    summary['cumulative_balance_error_mm'] = initial+summary['precip_mm']-sim.storage()-sum(
        summary[k] for k in ('runoff_mm','evapotranspiration_mm','leachate_collected_mm','bottom_leakage_mm'))
    summary['area_m2'] = sim.cfg['area_m2']
    for k in ('precip_mm','runoff_mm','evapotranspiration_mm','leachate_collected_mm','bottom_leakage_mm'):
        summary[k[:-3]+'_m3'] = summary[k]*sim.cfg['area_m2']/1000.
    return dict(config=sim.cfg, weather=[dict(w,pet_mm=d['pet_mm']) for w,d in zip(weather,days)], daily=days, layers=layer_rows,
                monthly=aggregation(days, lambda x:x[:7]), annual=aggregation(days, lambda x:x[:4]), summary=summary)


def run(config, weather, output):
    result = simulate(config, weather)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for key in ('weather','daily','layers','monthly','annual'):
        save_csv(output/f'{key}.csv', result[key])
    for key in ('summary','config'):
        (output/f'{key}.json').write_text(json.dumps(result[key], ensure_ascii=False, indent=2), encoding='utf-8')
    return result['summary']


def generate_synthetic_weather(first_year, years, seed=7):
    if type(years) is not int or not 1 <= years <= 100:
        raise ValueError('years 需要是1..100整数')
    rng = random.Random(seed)
    d, end = date(first_year,1,1), date(first_year+years,1,1)
    rows = []
    while d < end:
        doy = d.timetuple().tm_yday
        t = 7+15*math.sin(2*math.pi*(doy-109)/365.25)+rng.gauss(0,4)
        p = max(0., rng.gammavariate(1.15,5.8)) if rng.random() < .42 else 0.
        if doy in (140,260):
            p += 45
        pet = max(0., 2.7+2.7*math.sin(2*math.pi*(doy-82)/365.25))
        rows.append(dict(date=d.isoformat(), precip_mm=round(p,3), temp_c=round(t,3), pet_mm=round(pet,3)))
        d += timedelta(days=1)
    return rows


def main():
    # Windows consoles and redirected output may otherwise default to cp1252.
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8',errors='backslashreplace')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('run')
    p.add_argument('--config', required=True)
    p.add_argument('--weather', required=True)
    p.add_argument('--out', default='results')
    p = sub.add_parser('validate')
    p.add_argument('--config', required=True)
    p = sub.add_parser('migrate')
    p.add_argument('--config', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('demo-weather')
    p.add_argument('--year', type=int, default=2024)
    p.add_argument('--years', type=int, default=2)
    p.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        if args.cmd == 'demo-weather':
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            save_csv(args.out, generate_synthetic_weather(args.year,args.years))
        else:
            cfg = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
            if args.cmd == 'migrate':
                cfg = validate_config(migrate_config(cfg))
                Path(args.out).parent.mkdir(parents=True, exist_ok=True)
                Path(args.out).write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
                print('已转换：底衬改为有储水的等效阻隔层；新旧结果不保证一致。')
            elif args.cmd == 'validate':
                cfg = validate_config(cfg)
                print('配置通过校验。\n'+'\n'.join(profile_warnings(cfg)))
            else:
                print(json.dumps(run(cfg, load_weather(args.weather), args.out), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as e:
        parser.exit(2, f'输入或计算错误: {e}\n')


if __name__ == '__main__':
    main()
