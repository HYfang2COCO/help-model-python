"""Explicit daily rainfall/weather import. No invented unlabelled weather values."""
from __future__ import annotations

import csv
import io
import math
from datetime import date, datetime
from pathlib import Path

from help_mvp import validate_weather


def worksheet_names(data):
    import openpyxl
    book=openpyxl.load_workbook(io.BytesIO(data),read_only=True,data_only=True)
    try:
        return list(book.sheetnames)
    finally:
        book.close()


def read_table(data: bytes, filename: str, sheet=None):
    """Read CSV/TSV or XLSX with a header row. Return (rows, sheet names)."""
    suffix = Path(filename).suffix.lower()
    if suffix == '.xlsx':
        try:
            import openpyxl
        except ImportError as e:
            raise ValueError('XLSX requires openpyxl; install requirements-ui.txt') from e
        book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        try:
            names = book.sheetnames
            ws = book[sheet] if sheet is not None else book[names[0]]
            values = ws.iter_rows(values_only=True)
            header = next(values, None)
            if not header:
                raise ValueError('The selected worksheet is empty')
            header = [str(v).strip() if v is not None else '' for v in header]
            if any(not k for k in header) or len(set(header)) != len(header):
                raise ValueError('Column headers must be nonempty and unique')
            rows = [dict(zip(header, row)) for row in values if any(v is not None for v in row)]
            if not rows:
                raise ValueError('The selected worksheet has no data rows')
            return rows,names
        finally:
            book.close()
    if suffix not in ('.csv','.tsv','.txt'):
        raise ValueError('Use CSV, TSV or XLSX')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('gb18030')
    try:
        dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
    except csv.Error:
        dialect=csv.excel
    reader=csv.DictReader(io.StringIO(text),dialect=dialect)
    headers=reader.fieldnames
    if not headers or any(not h.strip() for h in headers) or len(set(h.strip() for h in headers))!=len(headers):
        raise ValueError('Column headers must be nonempty and unique')
    rows=[]
    for row in reader:
        if None in row:
            raise ValueError('A row has more values than the header')
        if any(str(v or '').strip() for v in row.values()):
            rows.append({k.strip():v for k,v in row.items()})
    if not rows:
        raise ValueError('The table has no data rows')
    return rows,[]


ALIASES = {
    'date':('date','日期','时间','day','jour'),
    'precip_mm':('precip_mm','precipitation','precipitation_mm','rainfall','rainfall_mm','rain_mm','降水','降水量','降水量(mm)','降雨量','précipitations','precipitations','pluie'),
    'temp_c':('temp_c','temperature','temperature_c','气温','温度','température'),
    'pet_mm':('pet_mm','pet','etp','潜在蒸散','潜在蒸散量'),
    'solar_mj_m2_day':('solar_mj_m2_day','solar_radiation','辐射','太阳辐射','rayonnement'),
    'rh_percent':('rh_percent','relative_humidity','humidity','相对湿度','湿度','humidité'),
    'wind_m_s':('wind_m_s','wind_speed','wind','风速','vent'),
}


def guess_columns(columns):
    normalized={str(c).strip().casefold():c for c in columns}
    return {key:next((normalized[a.casefold()] for a in choices if a.casefold() in normalized),None)
            for key,choices in ALIASES.items()}


def normalize_weather(rows, mapping, *, date_format='%Y-%m-%d', precip_unit='mm',
                      constant_temp_c=None, constant_pet_mm=None,energy=False):
    """Map columns; missing T/PET require explicit user-supplied constants."""
    factor={'mm':1.,'cm':10.,'inch':25.4}.get(precip_unit)
    if factor is None:
        raise ValueError('Precipitation unit must be mm, cm or inch')
    date_column,precip_column=mapping.get('date'),mapping.get('precip_mm')
    if not date_column or not precip_column or date_column==precip_column:
        raise ValueError('Choose distinct date and precipitation columns')
    used=[mapping[k] for k in ('date','precip_mm','temp_c','pet_mm') if mapping.get(k)]
    if len(set(used))!=len(used):
        raise ValueError('Each variable must use a distinct column')
    if energy and any(not mapping.get(k) for k in ('solar_mj_m2_day','rh_percent','wind_m_s')):
        raise ValueError('Modified Penman requires solar_mj_m2_day, rh_percent and wind_m_s columns')
    output=[]
    for position,row in enumerate(rows,2):
        try:
            raw_date=row[date_column]
            if isinstance(raw_date,datetime):
                if raw_date.time()!=datetime.min.time():
                    raise ValueError('Use daily dates without a time component')
                d=raw_date.date()
            elif isinstance(raw_date,date):
                d=raw_date
            else:
                d=datetime.strptime(str(raw_date).strip(),date_format).date()
            values={}
            for key in ('precip_mm','temp_c','pet_mm'):
                col=None if energy and key=='pet_mm' else mapping.get(key)
                raw=row[col] if col else (constant_temp_c if key=='temp_c' else constant_pet_mm)
                if raw is None or isinstance(raw,bool):
                    raise ValueError(f'Missing value for {key}')
                # Comma decimals only when there is no dot; delimiter was detected earlier.
                if isinstance(raw,str):
                    raw=raw.strip().replace(',','.')
                value=float(raw)
                if not math.isfinite(value):
                    raise ValueError(f'Nonfinite {key}')
                values[key]=value*factor if key=='precip_mm' else value
            if energy:
                for key,low,high in [('solar_mj_m2_day',0,60),('rh_percent',0,100),('wind_m_s',0,100)]:
                    raw=row[mapping[key]]
                    val=float(str(raw).strip().replace(',','.'))
                    if not math.isfinite(val) or not low<=val<=high:
                        raise ValueError(f'{key}: outside valid range')
                    values[key]=val
            output.append(dict(date=d.isoformat(),**values))
        except (KeyError,TypeError,ValueError,OverflowError) as e:
            raise ValueError(f'Row {position}: {e}') from e
    validate_weather(output)
    return output
