"""Selected equations checked against HELP v3 engineering documentation.

Source: https://dots.el.erdc.dren.mil/elmodels/pdf/help3doc.pdf
Equation-level functions; these do not reproduce the complete HELP solver.
"""
import math
from datetime import date


VEGETATION={'bare':(96.77,-20.80,-54.94),'poor':(93.51,-24.85,-71.92),
            'fair':(90.09,-23.73,-158.4),'good':(86.72,-43.38,-151.2),
            'excellent':(83.83,-26.91,-229.4)}


def finite(value,label,minimum=None,maximum=None):
    try:
        out=float(value)
    except (ValueError,TypeError,OverflowError) as e:
        raise ValueError(f'{label}: invalid number') from e
    if not math.isfinite(out) or (minimum is not None and out<minimum) or (maximum is not None and out>maximum):
        raise ValueError(f'{label}: outside valid range')
    return out


def amc2_cn(method,cn,slope,length_m,vegetation='good',infiltration_index=.12):
    """HELP eq32/Table7 and eq34. Inputs explicitly describe CN-II."""
    if method=='help_vegetation':
        a,b,c=VEGETATION[vegetation]
        cn=a+b*infiltration_index+c*infiltration_index**2
    if method in ('help_slope','help_vegetation'):
        standardized=(length_m/.3048/500.)**2/(slope/.04)
        cn=100.-(100.-cn)*standardized**(cn**(-.81))
    return min(99.99,max(.01,cn))


def moisture_cn(cn2,layers,storages,depth_mm):
    """Eq26-31, seven depth segments mapped to the existing uniform layer states.

    Mapping to uniform layers is a discretization approximation; no new hidden state.
    """
    cni=.3751*cn2+.002757*cn2**2-.00001639*cn2**3+.00000005143*cn2**4
    smax=25400./max(.01,cni)-254.
    usable=[]
    z=0.
    for layer,storage in zip(layers,storages):
        if layer.kind in ('barrier','geomembrane'):
            break
        end=min(depth_mm,z+layer.thickness_mm)
        if end>z:
            usable.append((z,end,layer,storage/layer.thickness_mm))
        z=end
        if z>=depth_mm:
            break
    if not usable or z<=0:
        return cn2
    ends=[0.,z/36.,z/6.,z/3.,z/2.,2*z/3.,5*z/6.,z]
    retention=weights=0.
    for lo,hi in zip(ends,ends[1:]):
        sm=fc=wp=sat=0.
        for a,b,l,theta in usable:
            overlap=max(0.,min(hi,b)-max(lo,a))
            sm+=overlap*theta; fc+=overlap*l.field_capacity
            wp+=overlap*l.wilting_point; sat+=overlap*l.porosity
        midpoint=(fc+wp)/2.
        ratio=max(0.,min(1.,1.-max(0.,sm-midpoint)/(sat-midpoint))) if sat>midpoint else 1.
        weight=1.0159*(math.exp(-4.16*lo/z)-math.exp(-4.16*hi/z))
        retention+=weight*smax*ratio
        weights+=weight
    s=retention/weights
    return min(100.,max(.01,25400./(s+254.)))


def modified_penman_pet(day,temp_c,solar_mj_m2_day,rh_percent,wind_m_s,latitude_deg,
                        precip_mm=0.,snow=False):
    """HELP equations 47,54-63 in mm/day; daily weather instead of climatology.

    Daily measured RH/wind replace HELP's quarterly/annual climatologies. Wet days
    use RH=1 as documented. Polar darkness is guarded; full snow energetics omitted.
    """
    temp=finite(temp_c,'temp_c',-80,60)
    rs=finite(solar_mj_m2_day,'solar_mj_m2_day',0,60)/.04184
    rh=finite(rh_percent,'rh_percent',0,100)/100.
    wind=finite(wind_m_s,'wind_m_s',0,100)*3.6
    latitude=finite(latitude_deg,'latitude_deg',-89,89)
    if precip_mm>0:
        rh=1.
    base=.00738*temp+.8072
    es=max(0.,33.8639*(base**8-.000019*abs(1.8*temp+48.)+.001316))
    ea=rh*es
    delta=max(0.,1.9993*(base**7-.0005793))
    gamma=.68
    d=date.fromisoformat(day) if isinstance(day,str) else day
    julian=d.timetuple().tm_yday-(182.5 if latitude<0 else 0.)
    lat=math.radians(abs(latitude))
    dd=1.+.0335*math.sin(.0172*(julian+88.2))
    sd=.4102*math.sin(.0172*(julian-80.25))
    h=math.acos(max(-1.,min(1.,-math.tan(lat)*math.tan(sd))))
    potential=max(0.,711.38*dd*(h*math.sin(lat)*math.sin(sd)+math.sin(h)*math.cos(lat)*math.cos(sd)))
    a,b=(1.2,.2) if rh<.5 else ((1.1,.1) if rh<.75 else (1.,0.))
    # Bound observed/potential radiation ratio rather than extrapolate cloud terms.
    cloud=max(0.,min(1.,a*rs/potential-b)) if potential>1e-9 else 0.
    rbo=1.171e-7*(temp+273.)**4*max(0.,.39-.05*math.sqrt(ea))
    rn=(1.-(.6 if snow else .23))*rs-rbo*cloud
    radiative=delta/(delta+gamma)*rn
    aerodynamic=15.36*gamma/(delta+gamma)*(1.+.1488*wind)*(es-ea)
    latent=67.67 if snow else 59.7-.0564*temp
    return max(0.,(radiative+aerodynamic)/latent)


def help_lateral_rate(head_mm,ksat_mm_day,slope,length_m):
    """Eq178 + numerical inverse of eq180, using average local saturated depth.

    The source relation is checked visually. At zero slope use eq179's limit.
    Does not include HELP's full coupled subprofile iteration.
    """
    if head_mm<=0 or ksat_mm_day<=0:
        return 0.
    y=head_mm/(length_m*1000.)
    alpha=math.atan(slope)
    sin,cos=math.sin(alpha),math.cos(alpha)
    if slope<=1e-12:
        return ksat_mm_day*(4*y/math.pi)**2
    critical=.4*sin*sin
    ycritical=.2*slope
    if y<ycritical:
        return ksat_mm_day*2*sin*cos*y
    c=2*math.sqrt(.4)/math.pi
    exponent_den=2*math.log(c)
    def depth(q):
        # Written in log form to retain the asymptote for large q/critical.
        power=math.exp(math.log(q/critical)/exponent_den)
        return math.pi*math.sqrt(q)/(4*cos)*c**power
    lo,hi=critical,max(critical*2.,(4*y*cos/math.pi)**2*4.)
    while depth(hi)<y:
        hi*=4.
    for _ in range(65):
        mid=(lo+hi)/2.
        if depth(mid)<y:
            lo=mid
        else:
            hi=mid
    return ksat_mm_day*(lo+hi)/2.


def giroud_contact_rate(head_mm,soil_ksat_mm_day,soil_thickness_mm,contact,
                        pinhole_density_ha,pinhole_area_mm2,defect_density_ha,defect_area_mm2):
    """Eq151/152/162/165, good/poor contact with directly underlying barrier.

    Variable defect areas use general SI radius expressions. Interfacial wetted
    fractions are summed and capped at one; no claim of all six HELP design cases.
    """
    if head_mm<=0 or soil_ksat_mm_day<=0:
        return 0.
    h=head_mm/1000.; thickness=soil_thickness_mm/1000.
    ks=soil_ksat_mm_day/86400000.
    coefficient=.26 if contact=='giroud_good' else .61
    out=0.
    for density,area in [(pinhole_density_ha,pinhole_area_mm2),(defect_density_ha,defect_area_mm2)]:
        if density<=0:
            continue
        area_m2=area/1e6
        r0=math.sqrt(area_m2/math.pi)
        radius=coefficient*area_m2**.05*h**.45*ks**(-.13)
        # Formula is outside its interface domain when radius approaches the hole.
        if radius<=r0*1.001:
            gradient=1.+h/thickness
            fraction=min(1.,density/10000.*area_m2)
        else:
            gradient=1.+h/(2.*thickness*math.log(radius/r0))
            fraction=min(1.,density/10000.*math.pi*radius**2)
        out+=soil_ksat_mm_day*gradient*fraction*(.001/.00114)
    return min(out,soil_ksat_mm_day*(1.+h/thickness))
