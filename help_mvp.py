#!/usr/bin/env python3
"""HELP-inspired daily landfill water balance simulator (research prototype).

This is an independent *simplified* implementation, NOT US EPA HELP and
NOT a validated substitute for engineering or regulatory calculations.
Standard library only; all depths and fluxes are mm of water over landfill area.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Layer:
    name: str
    kind: str               # soil, waste, drain
    thickness_mm: float
    porosity: float
    field_capacity: float
    wilting_point: float
    initial_theta: float
    ksat_mm_day: float
    brooks_corey_lambda: float = 0.5
    lateral_ksat_mm_day: float = 0.0
    slope_fraction: float = 0.0
    drainage_length_m: float = 30.0

    @staticmethod
    def from_dict(d):
        layer = Layer(**d)
        if layer.kind not in ('soil', 'waste', 'drain'):
            raise ValueError(f'{layer.name}: kind must be soil, waste or drain')
        if not (0 <= layer.wilting_point < layer.field_capacity < layer.porosity <= 1):
            raise ValueError(f'{layer.name}: require 0 <= WP < FC < porosity <= 1')
        if not layer.wilting_point <= layer.initial_theta <= layer.porosity:
            raise ValueError(f'{layer.name}: invalid initial_theta')
        if layer.thickness_mm <= 0 or layer.ksat_mm_day < 0 or layer.brooks_corey_lambda <= 0:
            raise ValueError(f'{layer.name}: invalid thickness, ksat or lambda')
        if layer.kind == 'drain' and (layer.lateral_ksat_mm_day < 0 or layer.drainage_length_m <= 0 or layer.slope_fraction < 0):
            raise ValueError(f'{layer.name}: invalid lateral drainage parameters')
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


def runoff_curve_number(p_mm, cn):
    """US SCS/NRCS event runoff equation with Ia = 0.2 S (fixed CN)."""
    if p_mm <= 0:
        return 0.0
    s = 25400.0 / cn - 254.0   # mm
    ia = 0.2 * s
    return (p_mm - ia) ** 2 / (p_mm + 0.8 * s) if p_mm > ia else 0.0


def conductivity(layer: Layer, storage_mm: float):
    """Campbell-like K(theta) with Brooks-Corey effective saturation.
    The residual-water approximation here uses WP, NOT the calibrated HELP
    residual content/pore-index inference. See README's limitations.
    """
    theta = max(layer.wilting_point, min(layer.porosity, storage_mm / layer.thickness_mm))
    se = (theta - layer.wilting_point) / (layer.porosity - layer.wilting_point)
    exponent = 3.0 + 2.0 / layer.brooks_corey_lambda
    return layer.ksat_mm_day * max(0., min(1., se)) ** exponent


class HelpMVP:
    def __init__(self, cfg):
        self.cfg = cfg
        self.layers = [Layer.from_dict(x) for x in cfg['layers']]
        if not self.layers:
            raise ValueError('At least one porous layer is required')
        self.s = [x.initial_theta * x.thickness_mm for x in self.layers]
        self.swe = 0.0
        self.pending_recirculation_mm = 0.0
        self.cn = float(cfg.get('curve_number', 78))
        self.nstep = int(cfg.get('substeps_per_day', 4))
        self.root_depth = float(cfg.get('root_depth_mm', 500))
        self.snow_temp = float(cfg.get('snow_temperature_c', 0))
        self.melt_temp = float(cfg.get('melt_temperature_c', 0))
        self.melt_factor = float(cfg.get('degree_day_melt_mm_per_c_day', 3))
        self.snow_sublimation_fraction = float(cfg.get('snow_sublimation_pet_fraction', 0.15))
        self.liner = cfg.get('liner', None)
        self.rec_frac = float(cfg.get('recirculation_fraction', 0))
        self.rec_target = int(cfg.get('recirculation_target_index', len(self.layers)-1))
        if not (0 < self.cn < 100) or self.nstep < 1 or self.root_depth < 0:
            raise ValueError('Invalid curve number, substeps or root depth')
        if not (0 <= self.rec_frac <= 1) or not (0 <= self.rec_target < len(self.layers)):
            raise ValueError('Invalid recirculation fraction or target')
        if not (0 <= self.snow_sublimation_fraction <= 1) or self.melt_factor < 0:
            raise ValueError('Invalid snow parameters')
        if self.liner is not None:
            if self.liner['thickness_mm'] <= 0 or self.liner['ksat_mm_day'] < 0:
                raise ValueError('Invalid liner thickness or conductivity')
            factor = self.liner.get('geomembrane_leakage_multiplier', 1)
            if not 0 <= factor <= 1:
                raise ValueError('geomembrane_leakage_multiplier must be in [0,1]')
        self.root_weights = []
        remaining = self.root_depth
        for layer in self.layers:
            overlap = min(max(remaining, 0), layer.thickness_mm)
            self.root_weights.append(overlap)
            remaining -= overlap

    def storage(self):
        return sum(self.s) + self.swe + self.pending_recirculation_mm

    def add_at_layer(self, index, mm):
        """Inject water; capacity overflow backs upward and emerges as runoff."""
        extra = max(0.0, mm)
        for i in range(index, -1, -1):
            fit = min(extra, max(0.0, self.layers[i].sat_mm - self.s[i]))
            self.s[i] += fit
            extra -= fit
        return extra

    def extract_et(self, demand):
        """Distribute atmospheric demand in root zone, limited by WP storage."""
        if demand <= 0:
            return 0.0
        active = [i for i, w in enumerate(self.root_weights)
                  if w > 0 and self.s[i] > self.layers[i].wilt_mm]
        removed = 0.0
        remaining = demand
        # Iteration allows ET redistribution when one rooted layer dries.
        for _ in range(len(active) + 1):
            if not active or remaining <= 1e-12:
                break
            tw = sum(self.root_weights[i] for i in active)
            taken = 0.0
            for i in active:
                ask = remaining * self.root_weights[i] / tw
                actual = min(ask, max(0., self.s[i] - self.layers[i].wilt_mm))
                self.s[i] -= actual
                taken += actual
            removed += taken
            remaining -= taken
            active = [i for i in active if self.s[i] > self.layers[i].wilt_mm + 1e-12]
        return removed

    def routing_step(self, dt):
        """Transfer wet-layer excess downward; last layer drains laterally + leaks."""
        for i in range(len(self.layers) - 1):
            above, below = self.layers[i], self.layers[i+1]
            available = max(0., self.s[i] - above.field_mm)
            capacity = max(0., below.sat_mm - self.s[i+1])
            if not available or not capacity:
                continue
            # Underlying Ks cap approximates interlayer impedance.
            rate = min(conductivity(above, self.s[i]), below.ksat_mm_day)
            q = min(available, capacity, rate * dt)
            self.s[i] -= q
            self.s[i+1] += q
        bottom = self.layers[-1]
        wet = max(0., self.s[-1] - bottom.field_mm)
        if wet <= 0:
            return 0., 0., 0.
        head = min(bottom.thickness_mm, wet / (bottom.porosity - bottom.field_capacity))
        if self.liner is None:
            q_leak = conductivity(bottom, self.s[-1])
        else:
            k = self.liner['ksat_mm_day']
            thickness = self.liner['thickness_mm']
            multiplier = self.liner.get('geomembrane_leakage_multiplier', 1.0)
            q_leak = k * (1.0 + head / thickness) * multiplier if head > 0 else 0.
        q_lat = 0.0
        if bottom.kind == 'drain':
            L = bottom.drainage_length_m * 1000.0
            # Darcy-type scaling; NOT HELP's Boussinesq solution.
            q_lat = bottom.lateral_ksat_mm_day * (head / L) * (bottom.slope_fraction + head / L)
        flow = (q_leak + q_lat) * dt
        if flow <= 0:
            return 0., 0., head
        scale = min(1.0, wet / flow)
        leak = q_leak * dt * scale
        lateral = q_lat * dt * scale
        self.s[-1] -= (leak + lateral)
        return lateral, leak, head

    def day(self, weather):
        p = float(weather['precip_mm'])
        t = float(weather['temp_c'])
        pet = float(weather['pet_mm'])
        if not all(math.isfinite(x) for x in (p,t,pet)) or p < 0 or pet < 0:
            raise ValueError('Weather must have finite temp and nonnegative precip/PET')
        before = self.storage()
        rain = p if t > self.snow_temp else 0.
        snowfall = p - rain
        self.swe += snowfall
        sub = min(self.swe, pet * self.snow_sublimation_fraction)
        self.swe -= sub
        melt = min(self.swe, self.melt_factor * max(0., t - self.melt_temp))
        self.swe -= melt
        liquid = rain + melt
        direct_runoff = runoff_curve_number(liquid, self.cn)
        runoff = direct_runoff
        infiltrating = liquid - direct_runoff
        remaining_pet = pet - sub
        recycled_today = self.pending_recirculation_mm
        self.pending_recirculation_mm = 0.0
        recycled_runoff = self.add_at_layer(self.rec_target, recycled_today)
        runoff += recycled_runoff
        saturation_runoff = 0.
        lateral_total = 0.
        leak_total = 0.
        et_soil = 0.
        head_peak = 0.
        for _ in range(self.nstep):
            surface_excess = self.add_at_layer(0, infiltrating / self.nstep)
            runoff += surface_excess
            saturation_runoff += surface_excess
            et_soil += self.extract_et(remaining_pet / self.nstep)
            lat, leak, head = self.routing_step(1.0 / self.nstep)
            lateral_total += lat
            leak_total += leak
            head_peak = max(head_peak, head)
        self.pending_recirculation_mm = lateral_total * self.rec_frac
        collected = lateral_total - self.pending_recirculation_mm
        after = self.storage()
        et_total = et_soil + sub
        residual = before + p - runoff - et_total - collected - leak_total - after
        row = {
            'date': weather['date'], 'precip_mm': p, 'temp_c': t, 'pet_mm': pet,
            'rain_mm': rain, 'snowfall_mm': snowfall, 'snowmelt_mm': melt,
            'runoff_mm': runoff, 'direct_runoff_mm': direct_runoff,
            'saturation_runoff_mm': saturation_runoff,
            'recirculation_surface_runoff_mm': recycled_runoff,
            'infiltration_mm': max(0.0, infiltrating - saturation_runoff),
            'et_mm': et_total, 'leachate_collected_mm': collected,
            'liner_leakage_mm': leak_total, 'recirculated_next_day_mm': self.pending_recirculation_mm,
            'snowpack_mm': self.swe, 'soil_storage_mm': sum(self.s),
            'total_storage_mm': after, 'head_peak_mm': head_peak,
            'balance_error_mm': residual,
        }
        for layer, amount in zip(self.layers, self.s):
            row[f'theta_{layer.name}'] = amount / layer.thickness_mm
        return row


def load_weather(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError('Weather CSV is empty')
    required = {'date', 'precip_mm', 'temp_c', 'pet_mm'}
    if not required.issubset(rows[0]):
        raise ValueError(f'Weather CSV needs columns {sorted(required)}')
    previous = None
    for row in rows:
        d = date.fromisoformat(row['date'])
        if previous is not None and d != previous + timedelta(days=1):
            raise ValueError(f'Dates must be consecutive and increasing: {row["date"]}')
        previous = d
    return rows


def save_csv(path, rows):
    if not rows:
        return
    with Path(path).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def aggregation(rows, keyfn):
    groups = {}
    for r in rows:
        k = keyfn(r['date'])
        if k not in groups:
            groups[k] = []
        groups[k].append(r)
    out = []
    additive = ['precip_mm','runoff_mm','et_mm','leachate_collected_mm', 'liner_leakage_mm', 'balance_error_mm']
    for group, data in groups.items():
        r = {'period': group, 'days': len(data)}
        for col in additive:
            r[col] = round(sum(float(d[col]) for d in data), 8)
        r['avg_soil_storage_mm'] = round(sum(float(d['soil_storage_mm']) for d in data)/len(data), 5)
        r['max_head_mm'] = round(max(float(d['head_peak_mm']) for d in data), 5)
        out.append(r)
    return out


def generate_synthetic_weather(first_year, years, seed=7):
    """Synthetic seasonal weather for functional demonstrations, NOT observed data."""
    rng = random.Random(seed)
    d = date(first_year,1,1)
    end = date(first_year+years,1,1)
    rows = []
    while d < end:
        doy = d.timetuple().tm_yday
        mean_t = 7 + 15 * math.sin(2 * math.pi * (doy - 109) / 365.25)
        t = mean_t + rng.gauss(0,4)
        rain_chance = 0.42
        p = max(0., rng.gammavariate(1.15,5.8)) if rng.random() < rain_chance else 0.
        # Two deliberately synthetic storm days/year to exercise runoff routing.
        if doy in (140, 260):
            p += 45.
        pet = max(0., 2.7 + 2.7 * math.sin(2 * math.pi * (doy-82)/365.25))
        rows.append({'date':d.isoformat(),'precip_mm':round(p,3),
                     'temp_c':round(t,3),'pet_mm':round(pet,3)})
        d += timedelta(days=1)
    return rows


def run(config, weather, output):
    sim = HelpMVP(config)
    days = [sim.day(r) for r in weather]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    save_csv(output/'daily.csv', days)
    save_csv(output/'monthly.csv', aggregation(days, lambda x:x[:7]))
    save_csv(output/'annual.csv', aggregation(days, lambda x:x[:4]))
    err = max(abs(r['balance_error_mm']) for r in days)
    total = lambda col: sum(r[col] for r in days)
    summary = {'days':len(days),'precip_mm':total('precip_mm'),
               'runoff_mm':total('runoff_mm'), 'evapotranspiration_mm':total('et_mm'),
               'leachate_collected_mm':total('leachate_collected_mm'),
               'liner_leakage_mm':total('liner_leakage_mm'),
               'final_snow_mm':sim.swe, 'final_soil_storage_mm':sum(sim.s),
               'final_pending_recirculation_mm':sim.pending_recirculation_mm,
               'maximum_absolute_daily_balance_error_mm':err,
               'warning':'NOT EPA HELP. Research prototype; not for design/permitting.'}
    (output/'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False),encoding='utf-8')
    if err > 1e-7:
        raise AssertionError(f'Water balance not closed: {err} mm')
    return summary


def plot_files(out):
    try:
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise SystemExit('To plot, run: pip install matplotlib') from e
    rows = load_any_csv(Path(out)/'daily.csv')
    ds = [date.fromisoformat(r['date']) for r in rows]
    fig, axes = plt.subplots(3,1,figsize=(11,8),sharex=True)
    axes[0].bar(ds, [float(r['precip_mm']) for r in rows],width=1, label='Precipitation')
    axes[0].set_ylabel('P (mm/day)')
    axes[1].plot(ds,[float(r['leachate_collected_mm']) for r in rows],label='Collected leachate')
    axes[1].plot(ds,[float(r['liner_leakage_mm']) for r in rows],label='Liner leakage')
    axes[1].legend()
    axes[1].set_ylabel('Flux (mm/day)')
    axes[2].plot(ds,[float(r['soil_storage_mm']) for r in rows],label='Soil storage')
    axes[2].plot(ds,[float(r['snowpack_mm']) for r in rows],label='Snowpack')
    axes[2].legend()
    axes[2].set_ylabel('Storage (mm)')
    fig.suptitle('HELP-inspired prototype | Synthetic or user-provided climate')
    fig.tight_layout()
    f = Path(out)/'hydrology.png'
    fig.savefig(f,dpi=170)
    plt.close(fig)
    return f


def load_any_csv(path):
    with Path(path).open(newline='',encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd',required=True)
    sim = sub.add_parser('run',help='Run a model with config.json and daily weather CSV')
    sim.add_argument('--config',required=True)
    sim.add_argument('--weather',required=True)
    sim.add_argument('--out',default='outputs')
    w = sub.add_parser('demo-weather',help='Generate SYNTHETIC seasonal weather CSV')
    w.add_argument('--out',default='examples/weather_synthetic.csv')
    w.add_argument('--year',type=int,default=2024)
    w.add_argument('--years',type=int,default=2)
    pl = sub.add_parser('plot',help='Plot result CSV (requires matplotlib)')
    pl.add_argument('--out',default='outputs')
    args = parser.parse_args()
    if args.cmd == 'demo-weather':
        p = Path(args.out)
        p.parent.mkdir(parents=True,exist_ok=True)
        save_csv(p,generate_synthetic_weather(args.year,args.years))
        print(f'Created synthetic weather: {p}')
    elif args.cmd == 'run':
        cfg = json.loads(Path(args.config).read_text(encoding='utf-8-sig'))
        result = run(cfg,load_weather(args.weather),args.out)
        print(json.dumps(result,indent=2,ensure_ascii=False))
    elif args.cmd == 'plot':
        print(plot_files(args.out))


if __name__ == '__main__':
    main()
