"""2019 input adapter. Frozen step-22 preprocessing and model bytes remain untouched."""
from __future__ import annotations
import inspect
import importlib
from pathlib import Path
import numpy as np
import pandas as pd
from pipeline.grid import coarsen
from analysis import s22_data as frozen

ROOT=frozen.ROOT; RAW=frozen.RAW; TABLES=frozen.TABLES; LOCAL=ROOT/'data/interim/s22b'
START=pd.Timestamp('2019-01-01'); END=pd.Timestamp('2019-12-31 23:30')


def raw_counts():
    mapping=pd.read_csv(TABLES/'s22_unit_cells.csv'); eligible=mapping.cell.unique(); parts=[]
    audit=pd.read_csv(TABLES/'s22b_audit_snapshots.csv',parse_dates=['req_ts'])
    for m in range(1,13):
        month=f'2019-{m:02d}'; sn=audit[audit.month==month]
        z=np.load(RAW/'taxi'/f'{month}_cells500.npz')
        p=pd.DataFrame({'snap':z['snap'],'cell':coarsen(z['cell']),'Y':z['n'].astype(float)})
        p=p.groupby(['snap','cell'],as_index=False).Y.sum()
        city=p[p.cell.isin(eligible)].groupby('snap').Y.sum().reindex(sn.snap,fill_value=0)
        for u,c in mapping.groupby('unit',sort=False):
            y=p[p.cell.isin(c.cell)].groupby('snap').Y.sum().reindex(sn.snap,fill_value=0)
            parts.append(pd.DataFrame({'ts':sn.req_ts.to_numpy(),'unit':u,'Y':y.to_numpy(),
                          'city':city.to_numpy(),'valid':sn.model_usable.to_numpy(bool),'regime':0}))
    out=pd.concat(parts,ignore_index=True).sort_values(['unit','ts'])
    assert not out.duplicated(['ts','unit']).any() and out.ts.between(START,END).all()
    return out


class ArchiveReadings:
    """Supply explicit unknown depths where the archive has no observations for a whole day.

    Sparse positive-only files need completeness metadata to distinguish an all-dry day from no data.
    This changes raw input availability only; the frozen rolling windows and saved imputers do not change.
    """
    def __init__(self):
        comps=[]; stations=[]
        for month in range(1,13):
            prefix=f'2019-{month:02d}'
            comps.append(pd.read_csv(RAW/'rain'/f'{prefix}_completeness.csv.gz',parse_dates=['date']))
            stations.append(pd.read_csv(RAW/'rain'/f'{prefix}_stations.csv.gz'))
        totals=pd.concat(comps).groupby('date').n_readings.sum()
        self.missing=pd.date_range(START.normalize(),END.normalize()).difference(totals[totals>0].index)
        self.gauges=sorted(pd.concat(stations).station_id.unique())

    def read_csv(self,path,*args,**kwargs):
        data=pd.read_csv(path,*args,**kwargs)
        path=Path(path)
        if path.parent.name=='rain' and path.name.startswith('2019-') and path.name.endswith('_readings.csv.gz'):
            days=self.missing[self.missing.strftime('%Y-%m')==path.name[:7]]
            unknown=[]
            for day in days:
                times=pd.date_range(day,day+pd.Timedelta('1D'),freq='5min',inclusive='left')
                unknown.append(pd.MultiIndex.from_product([times,self.gauges],names=['ts','station_id']).to_frame(index=False).assign(mm=np.nan))
            if unknown:
                data=pd.concat([data,*unknown],ignore_index=True)
                data['ts']=pd.to_datetime(data.ts)
        return data

    def __getattr__(self,name):
        return getattr(pd,name)


def historical_weather():
    """Run the frozen function with its date range changed and unknown raw depths supplied."""
    source=inspect.getsource(frozen.weather_history)
    old="start=pd.Timestamp('2022-03-23')"
    assert source.count(old)==1, 'frozen weather source changed'
    source=source.replace(old,"start=pd.Timestamp('2019-01-01')")
    namespace=vars(frozen).copy()
    namespace['pd']=ArchiveReadings()
    exec(compile(source,'<step22b date-only weather adapter>','exec'),namespace)
    return namespace['weather_history'](END)


def features(counts,weather,pattern,horizon):
    d=frozen.make_features(counts,weather,pattern,horizon,START,END)
    # The original calendar file deliberately stays hash-frozen. Supply historical calendar values.
    hol=pd.read_csv(ROOT/'data/static/phase3/s22b/holidays_2019.csv',parse_dates=['date'])
    th=(d.ts+pd.Timedelta(minutes=horizon)).dt.normalize()
    d['public']=th.isin(hol.loc[hol.kind.eq('public'),'date']).astype(int)
    d['school']=th.isin(hol.loc[hol.kind.eq('school'),'date']).astype(int)
    d['daytype']=np.where(d.public,2,np.where(d.dow>=5,1,0))
    return d


def forecast_audit(fc,times):
    """Audit valid-but-unissued naive candidates; actual features still use the frozen strict gate."""
    fc=fc.drop_duplicates(['issued','area'],keep='last')
    issues=fc.groupby('issued').agg(item_ts=('item_ts','max'),valid_start=('valid_start','max'),
                                   valid_end=('valid_end','min'),area_rows=('area','size')).sort_index()
    issues['issued_at_or_after_end']=issues.index>=issues.valid_end
    issues['issued_after_valid_start']=issues.index>issues.valid_start
    latest=frozen.latest_issue(pd.DatetimeIndex(issues.index),times)
    selected=issues.reindex(latest.to_numpy()); selected.index=times
    valid=(selected.valid_start<=times)&(selected.valid_end>times)&(latest.to_numpy()<times.to_numpy())
    # A naive availability error is using the latest validity-matching forecast regardless of update time.
    naive=pd.Series(pd.NaT,index=times,dtype='datetime64[ns]')
    for issued,row in issues.iterrows():
        mask=(times>=row.valid_start)&(times<row.valid_end)
        naive.loc[mask]=issued
    rejected=naive.notna()&(naive.to_numpy()>=times.to_numpy())
    slots=pd.DataFrame({'ts':times,'strict_selected_issue':latest.to_numpy(),
                       'strict_eligible':np.asarray(valid),'naive_validity_issue':naive.to_numpy(),
                       'naive_rejected_future_issue':rejected.to_numpy()})
    return issues.reset_index(),slots


def audit():
    import json
    old=importlib.import_module('analysis.00_audit')
    regimes=importlib.import_module('analysis.prep_feed_regimes')
    LOCAL.mkdir(parents=True,exist_ok=True)
    snapshots=[]; comps=[]; stations=[]; forecasts=[]
    for m in range(1,13):
        month=f'2019-{m:02d}'
        sn=pd.read_csv(RAW/'taxi'/f'{month}_snapshots.csv.gz',parse_dates=['req_ts','act_ts']);sn['month']=month
        snapshots.append(sn)
        comps.append(pd.read_csv(RAW/'rain'/f'{month}_completeness.csv.gz',parse_dates=['date']))
        stations.append(pd.read_csv(RAW/'rain'/f'{month}_stations.csv.gz',parse_dates=['date']))
        forecasts.append(pd.read_csv(RAW/'forecast'/f'{month}_forecast.csv.gz',parse_dates=['issued','item_ts','valid_start','valid_end']))
    sn=pd.concat(snapshots,ignore_index=True); expected=pd.date_range(START,END,freq='30min')
    assert sn.req_ts.isin(expected).all() and not sn.req_ts.duplicated().any()
    sn['offset_min']=(sn.act_ts-sn.req_ts).dt.total_seconds()/60
    sn['ok']=sn.status.eq('ok');sn['offset_bad']=sn.ok&~sn.offset_min.abs().le(10)
    sn=old.flag_glitches(sn)
    sn['model_usable']=sn.ok&sn.offset_min.abs().le(10)
    sn.to_csv(TABLES/'s22b_audit_snapshots.csv',index=False)
    usable=sn[sn.model_usable].copy();usable['how']=usable.req_ts.dt.day_of_week*48+usable.req_ts.dt.hour*2+usable.req_ts.dt.minute//30
    profile=usable.groupby('how').n_points.median()
    usable['lr']=np.log(usable.n_points.clip(lower=1)/usable.how.map(profile))
    daily=usable.groupby(usable.req_ts.dt.normalize()).agg(n_snap=('lr','size'),lr=('lr','median'),median_count=('n_points','median'))
    daily=daily.reindex(pd.date_range('2019-01-01','2019-12-31'));daily.index.name='date'
    daily['n_snap']=daily.n_snap.fillna(0).astype(int);daily['full']=48;daily['usable']=daily.n_snap>=24
    daily.loc[~daily.usable,'lr']=np.nan
    seg=regimes.segment(daily)
    seg.to_csv(TABLES/'s22b_audit_feed_regimes.csv',index=False);daily.to_csv(TABLES/'s22b_audit_feed_daily.csv')
    comp=pd.concat(comps,ignore_index=True);st=pd.concat(stations,ignore_index=True).drop_duplicates(['date','station_id'])
    gauge=st.merge(comp,on=['date','station_id'],how='outer',validate='one_to_one')
    gauge['complete']=gauge.n_readings.ge(.8*288)
    gauge.to_csv(TABLES/'s22b_audit_gauges.csv',index=False)
    gauge_daily=gauge.groupby('date').agg(gauges=('station_id','size'),complete=('complete','sum'),
          median_readings=('n_readings','median')).reindex(pd.date_range('2019-01-01','2019-12-31'))
    gauge_daily.index.name='date'
    gauge_daily[['gauges','complete']]=gauge_daily[['gauges','complete']].fillna(0).astype(int)
    gauge_daily.to_csv(TABLES/'s22b_audit_gauge_days.csv')
    fc=pd.concat(forecasts,ignore_index=True)
    day_audit=gauge_daily.copy()
    day_audit['forecast_area_rows']=fc.groupby(fc.item_ts.dt.normalize()).size().reindex(day_audit.index,fill_value=0)
    day_audit['rain_readings']=comp.groupby('date').n_readings.sum().reindex(day_audit.index,fill_value=0)
    day_audit[(day_audit.forecast_area_rows==0)|(day_audit.rain_readings==0)].to_csv(TABLES/'s22b_audit_missing_days.csv')
    issues,slots=forecast_audit(fc,expected)
    issues.to_csv(TABLES/'s22b_audit_forecast_issues.csv',index=False)
    slots.to_csv(TABLES/'s22b_audit_forecast_slots.csv',index=False)
    sampledates=pd.to_datetime(['2019-01-15','2019-06-14','2019-09-15','2019-12-15'])
    sample=fc[fc.valid_start.dt.normalize().isin(sampledates)|fc.item_ts.dt.normalize().isin(sampledates)]
    sample.to_csv(TABLES/'s22b_audit_forecast_sample_days.csv',index=False)
    metrics=dict(requested=len(sn),expected=len(expected),usable=int(sn.model_usable.sum()),
      invalid_status=int((~sn.ok).sum()),bad_offsets=int(sn.offset_bad.sum()),median_offset=float(sn.offset_min.median()),
      max_abs_offset=float(sn.offset_min.abs().max()),positive_offsets=int((sn.ok&sn.offset_min.gt(0)).sum()),glitch_flags=int(sn.glitch.sum()),
      regimes=int(seg.kind.eq('regime').sum()),short_spells=int(seg.kind.eq('spell').sum()),
      gauge_days=len(gauge),complete_gauge_days=int(gauge.complete.sum()),unique_gauges=gauge.station_id.nunique(),
      min_daily_gauges=int(gauge_daily.gauges.min()),max_daily_gauges=int(gauge_daily.gauges.max()),
      days_without_complete_gauges=int(gauge_daily.complete.eq(0).sum()),
      days_without_rain_readings=int(day_audit.rain_readings.eq(0).sum()),
      days_without_forecast_records=int(day_audit.forecast_area_rows.eq(0).sum()),
      gauge_records_outside_2019=int((~gauge.date.between(START.normalize(),END.normalize())).sum()),
      forecast_issue_records_after_2019=int((fc.issued>END).sum()),
      forecast_area_rows=len(fc),forecast_area_records_issued_at_or_after_end=int((fc.issued>=fc.valid_end).sum()),
      forecast_area_records_issued_after_valid_start=int((fc.issued>fc.valid_start).sum()),forecast_issues=len(issues),issued_at_or_after_end=int(issues.issued_at_or_after_end.sum()),
      issued_after_valid_start=int(issues.issued_after_valid_start.sum()),
      naive_future_issue_rejections=int(slots.naive_rejected_future_issue.sum()),
      strict_forecast_slots=int(slots.strict_eligible.sum()),unavailable_forecast_slots=int((~slots.strict_eligible).sum()),
      stage='audit only; no targets, storm counts or model scores')
    pd.DataFrame([dict(metric=k,value=v) for k,v in metrics.items()]).to_csv(TABLES/'s22b_audit_summary.csv',index=False)
    print(json.dumps(metrics,indent=2))
    return metrics
