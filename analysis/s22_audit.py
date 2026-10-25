"""Step-0 checks only for the unopened step-22 holdout. No labels or modelling."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw'
TABLES = ROOT / 'outputs/tables'


def main():
    month = '2026-10'
    sn = pd.read_csv(RAW/'taxi'/f'{month}_snapshots.csv.gz', parse_dates=['req_ts','act_ts'])
    expected = pd.date_range('2026-10-01', '2026-10-25', freq='15min', inclusive='left')
    assert not sn.req_ts.duplicated().any()
    assert sn.req_ts.isin(expected).all(), 'download extends beyond the registered holdout'
    sn['offset_min'] = (sn.act_ts-sn.req_ts).dt.total_seconds()/60
    sn['usable'] = sn.status.eq('ok') & sn.offset_min.abs().le(10)
    sn[['snap','req_ts','act_ts','status','offset_min','usable']].to_csv(TABLES/'s22_audit_snapshots.csv',index=False)
    comp = pd.read_csv(RAW/'rain'/f'{month}_completeness.csv.gz',parse_dates=['date'])
    assert comp.date.between(expected.min().normalize(),expected.max().normalize()).all()
    comp['complete'] = comp.n_readings.ge(0.8*288)
    comp.to_csv(TABLES/'s22_audit_gauges.csv',index=False)
    daily = comp.groupby('date').agg(gauges=('station_id','size'),complete=('complete','sum'),
                                     min_readings=('n_readings','min'),median_readings=('n_readings','median'))
    daily.to_csv(TABLES/'s22_audit_gauge_days.csv')
    result = dict(expected_snapshots=len(expected),requested=len(sn),usable=int(sn.usable.sum()),
                  absent_requests=len(expected.difference(sn.req_ts)),status=sn.status.value_counts().to_dict(),
                  median_offset_min=float(sn.offset_min.median()),max_abs_offset_min=float(sn.offset_min.abs().max()),
                  gauge_days=len(comp),complete_gauge_days=int(comp.complete.sum()),rain_dates=comp.date.nunique(),
                  stage='audit only: no October targets, labels, storm counts or model scores computed')
    pd.DataFrame([dict(metric=k,value=json.dumps(v) if isinstance(v,dict) else v) for k,v in result.items()]).to_csv(TABLES/'s22_audit_summary.csv',index=False)
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
