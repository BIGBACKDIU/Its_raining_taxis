"""Step 22 data and causal preprocessing. October is accessible only from the frozen scorer."""
from __future__ import annotations
import hashlib
from pathlib import Path
import importlib
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from analysis.geo import subzones, CRS
from pipeline.grid import coarsen

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw'; LOCAL=ROOT/'data/interim/s22'; TABLES=ROOT/'outputs/tables'
UNITS=['Central Area','Central','East','North','North-East','West']
FIT_END=pd.Timestamp('2025-03-31 23:30'); CAL_END=pd.Timestamp('2025-09-30 23:30')
FINAL_END=pd.Timestamp('2026-09-30 23:30'); HOLD_START=pd.Timestamp('2026-10-01'); HOLD_END=pd.Timestamp('2026-10-24 23:30')
START=pd.Timestamp('2022-04-01')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def geography():
    cells=pd.read_parquet(ROOT/'data/interim/cells.parquet')
    cells=cells[cells.eligible].sort_values('cell').copy()
    sz=subzones().to_crs(CRS)
    pts=gpd.GeoDataFrame(cells,geometry=gpd.points_from_xy(cells.lon,cells.lat),crs=4326).to_crs(CRS)
    joined=gpd.sjoin(pts,sz[['region','central_area','geometry']],predicate='within',how='left')
    assert len(joined)==374 and not joined.cell.duplicated().any()
    # Seven coastal centres lie outside MP2019. Their frozen planning-area names identify region.
    area_region=sz.drop_duplicates('planning_area').set_index('planning_area').region
    missing=joined.region.isna()
    joined.loc[missing,'region']=joined.loc[missing,'planning_area'].map(area_region)
    assert joined.region.notna().all()
    regmap={'CENTRAL REGION':'Central','EAST REGION':'East','NORTH REGION':'North',
            'NORTH-EAST REGION':'North-East','WEST REGION':'West'}
    joined['unit']=joined.region.map(regmap)
    assert joined.unit.notna().all(), joined.region.unique()
    rows=[]; shapes={}
    for u in UNITS:
        s=sz[sz.central_area.eq('Y')] if u=='Central Area' else sz[sz.region.map(regmap).eq(u)]
        shapes[u]=s.geometry.union_all()
        c=joined[joined.central_area.eq('Y')] if u=='Central Area' else joined[joined.unit.eq(u)]
        rows.extend((int(x),u) for x in c.cell)
    mapping=pd.DataFrame(rows,columns=['cell','unit'])
    assert mapping[mapping.unit!='Central Area'].cell.nunique()==374
    return mapping,shapes


def count_history(end):
    """Do not load outcome columns later than end. All cell sums use explicit ID joins."""
    end=pd.Timestamp(end); mapping,_=geography(); parts=[]
    for year in range(2022,end.year+1):
        p=pd.read_parquet(ROOT/f'data/interim/panel30_{year}.parquet',
            columns=['ts','cell','vacant','drop_main','regime_id'],
            filters=[('ts','>=',pd.Timestamp('2022-03-23')),('ts','<=',end)])
        if p.empty: continue
        assert p.groupby('ts').cell.nunique().eq(374).all()
        city=p.groupby('ts',sort=True).agg(city=('vacant','sum'),valid=('drop_main',lambda x:not x.any()),regime=('regime_id','first'))
        for u,c in mapping.groupby('unit',sort=False):
            a=p[p.cell.isin(c.cell)].groupby('ts').vacant.sum().rename('Y').to_frame()
            a=a.join(city); a['unit']=u; parts.append(a.reset_index())
    out=pd.concat(parts,ignore_index=True).sort_values(['unit','ts'])
    assert out.ts.max()<=end
    return out


def october_counts(history):
    """Only the guarded scorer may call this after the freeze has been pushed."""
    sn=pd.read_csv(TABLES/'s22_audit_snapshots.csv',parse_dates=['req_ts'])
    sn=sn[sn.usable & sn.req_ts.dt.minute.isin([0,30])]
    z=np.load(RAW/'taxi/2026-10_cells500.npz')
    p=pd.DataFrame({'snap':z['snap'],'cell':coarsen(z['cell']),'Y':z['n'].astype(float)})
    p=p[p.snap.isin(sn.snap)].groupby(['snap','cell'],as_index=False).Y.sum()
    mapping,_=geography(); eligible=mapping.cell.unique()
    city=p[p.cell.isin(eligible)].groupby('snap').Y.sum().reindex(sn.snap,fill_value=0)
    parts=[]
    for u,c in mapping.groupby('unit',sort=False):
        y=p[p.cell.isin(c.cell)].groupby('snap').Y.sum().reindex(sn.snap,fill_value=0)
        a=pd.DataFrame({'ts':sn.req_ts.to_numpy(),'unit':u,'Y':y.to_numpy(),'city':city.to_numpy(),'valid':True,'regime':-1})
        parts.append(a)
    return pd.concat([history,*parts],ignore_index=True).sort_values(['unit','ts'])


def fit_pattern(counts,end):
    """Balanced-panel Poisson cell + how*month + regime, using fitting rows only."""
    d=counts[counts.ts.between(START,pd.Timestamp(end)) & counts.valid]
    city=d.drop_duplicates('ts').copy()
    city['hm']=(city.ts.dt.day_of_week*48+city.ts.dt.hour*2+city.ts.dt.minute//30)*100+city.ts.dt.month
    a=city.groupby(['hm','regime']).city.agg(['sum','size']).reset_index()
    hi,hu=pd.factorize(a.hm); ri,ru=pd.factorize(a.regime)
    H=np.full(len(hu),np.log(city.city.mean())); R=np.zeros(len(ru))
    for iteration in range(500):
        old=H.copy()
        for idx,effect in ((hi,H),(ri,R)):
            mu=a['size'].to_numpy()*np.exp(H[hi]+R[ri])
            effect+=np.log(np.maximum(np.bincount(idx,a['sum'],minlength=len(effect)),1e-12)/np.bincount(idx,mu,minlength=len(effect)))
        ref=R[0]; R-=ref; H+=ref
        if np.max(np.abs(H-old))<1e-10: break
    shares=d.groupby('unit').Y.sum()/city.city.sum()
    return dict(hm=pd.Series(np.exp(H),index=hu),shares=shares,end=str(end),iterations=iteration+1)


def add_expected(counts,pattern):
    d=counts.sort_values(['unit','ts']).copy()
    hm=(d.ts.dt.day_of_week*48+d.ts.dt.hour*2+d.ts.dt.minute//30)*100+d.ts.dt.month
    d['city_pattern']=hm.map(pattern['hm']).to_numpy()
    city=d.drop_duplicates('ts').set_index('ts').sort_index()
    ratio=(city.city/city.city_pattern).where(city.valid)
    lev=ratio.rolling('7D',min_periods=48,closed='right').median()
    d['level']=d.ts.map(lev)
    d['pattern']=d.city_pattern*d.unit.map(pattern['shares'])
    d['expected_now']=d.pattern*d.level
    return d


def trailing_rain(depths, times):
    """Six end-labelled 5-minute depths, with no observations after the issue time."""
    return depths.rolling(6,min_periods=6).sum().reindex(times)*2


def latest_issue(issues,times):
    """One issue for all areas, strictly before t; equality is unavailable."""
    j=issues.searchsorted(times,side='left')-1
    selected=pd.Series(pd.NaT,index=times,dtype='datetime64[ns]')
    good=j>=0
    selected.loc[good]=issues[j[good]].to_numpy()
    return selected


def weather_history(end):
    """Raw 5-minute depths, right-closed windows, preceding-day health, strict issued forecasts."""
    end=pd.Timestamp(end); start=pd.Timestamp('2022-03-23')
    months=pd.period_range(start,end,freq='M').astype(str)
    # No glob can accidentally open October during development or final fitting.
    comps=[]; stations=[]; readings=[]; forecasts=[]; areas=[]
    for m in months:
        comps.append(pd.read_csv(RAW/'rain'/f'{m}_completeness.csv.gz',parse_dates=['date']))
        stations.append(pd.read_csv(RAW/'rain'/f'{m}_stations.csv.gz',parse_dates=['date']))
        readings.append(pd.read_csv(RAW/'rain'/f'{m}_readings.csv.gz',parse_dates=['ts']))
        forecasts.append(pd.read_csv(RAW/'forecast'/f'{m}_forecast.csv.gz',parse_dates=['issued','item_ts','valid_start','valid_end']))
        areas.append(pd.read_csv(RAW/'forecast'/f'{m}_areas.csv.gz'))
    comp=pd.concat(comps,ignore_index=True); st=pd.concat(stations,ignore_index=True)
    rd=pd.concat(readings,ignore_index=True); fc=pd.concat(forecasts,ignore_index=True)
    comp=comp[comp.date<=end]; st=st[st.date<=end]; rd=rd[rd.ts<=end]; fc=fc[fc.issued<=end]
    times=pd.date_range(start,end,freq='30min'); bins=pd.date_range(start-pd.Timedelta('30min'),end,freq='5min')
    gauges=sorted(st.station_id.unique()); loc=st.sort_values('date').groupby('station_id').first()[['lon','lat']].reindex(gauges)
    points=gpd.GeoSeries(gpd.points_from_xy(loc.lon,loc.lat),crs=4326).to_crs(CRS)
    # A new station is usable only once its previous day is complete; first-known coordinates are static.
    healthy=comp.assign(work=comp.n_readings.ge(.8*288)).pivot(index='date',columns='station_id',values='work').reindex(columns=gauges)
    health=healthy.reindex(bins.normalize()-pd.Timedelta('1D')).fillna(False).to_numpy(bool)
    B=np.zeros((len(bins),len(gauges)),dtype='float32')
    r=rd[rd.ts.isin(bins)&rd.station_id.isin(gauges)].drop_duplicates(['ts','station_id'])
    ti=bins.get_indexer(r.ts); gi=pd.Index(gauges).get_indexer(r.station_id)
    B[ti,gi]=r.mm.to_numpy(dtype='float32'); B[~health]=np.nan
    # Sparse archive cannot distinguish a missing midnight from a reported zero; keep that interval unknown.
    B[(bins.hour==0)&(bins.minute==0)]=np.nan
    rain=trailing_rain(pd.DataFrame(B,index=bins,columns=gauges),times)
    R=rain.to_numpy(); previous=rain.shift(1).to_numpy()
    common=np.isfinite(R)&np.isfinite(previous)
    changed=common&(previous==0)&(R>=1)
    n=common.sum(1); newshare=changed.sum(1)/np.maximum(n,1)
    coverage=np.divide(((R>0)&np.isfinite(R)).sum(1),np.isfinite(R).sum(1),out=np.full(len(R),np.nan),where=np.isfinite(R).sum(1)>0)
    _,shapes=geography(); output=[]
    for u in UNITS:
        geom=shapes[u]
        inside=np.array([geom.covers(p) for p in points])
        distances=np.array([geom.distance(p) for p in points])
        outside=~inside
        groups=[inside,outside&(distances>=2000)&(distances<5000),outside&(distances>=5000)&(distances<=10000)]
        a=pd.DataFrame({'ts':times,'unit':u,'island_wet':coverage,'coverage_change':coverage-pd.Series(coverage).shift(1).to_numpy(),
                        'onset_share':newshare,'onset_gauges':n})
        for name,mask in zip(['rain','ring2_5','ring5_10'],groups):
            vals=R[:,mask]; num=np.isfinite(vals).sum(1)
            a[name]=np.divide(np.nansum(vals,axis=1),num,out=np.full(len(R),np.nan),where=num>0)
        vals=R[:,inside]; num=np.isfinite(vals).sum(1)
        a['gauge_wet']=np.divide((vals>0).sum(1),num,out=np.full(len(R),np.nan),where=num>0)
        a['n_gauges']=num
        for k in (1,2,3): a[f'rain_lag{k}']=a.rain.shift(k)
        output.append(a)
    w=pd.concat(output,ignore_index=True)
    ar=pd.concat(areas).drop_duplicates('area',keep='first').dropna()
    ap=gpd.GeoSeries(gpd.points_from_xy(ar.lon,ar.lat),crs=4326).to_crs(CRS)
    area_units={u:ar.loc[[shapes[u].covers(p) for p in ap],'area'].tolist() for u in UNITS}
    # Peripheral forecast area labels can lie just outside a region; nearest polygon assigns all 47 areas.
    for idx,p in enumerate(ap):
        if not any(shapes[u].covers(p) for u in UNITS[1:]):
            nearest=min(UNITS[1:],key=lambda u:shapes[u].distance(p)); area_units[nearest].append(ar.iloc[idx].area)
    fc=fc.drop_duplicates(['issued','area'],keep='last').sort_values('issued')
    fc['code']=importlib.import_module('analysis.01_panel').fc_code(fc.forecast)
    issues=pd.DatetimeIndex(sorted(fc.issued.dropna().unique()))
    selected=latest_issue(issues,times)
    out=[]
    for u in UNITS:
        f=fc[fc.area.isin(area_units[u])].groupby('issued').agg(fc_mean=('code','mean'),fc_max=('code','max'),
                    valid_start=('valid_start','max'),valid_end=('valid_end','min'))
        a=f.reindex(selected.to_numpy()); a.index=times
        valid=(a.valid_start<=times)&(a.valid_end>times)&(selected.to_numpy()<times.to_numpy())
        a.loc[~valid,['fc_mean','fc_max']]=np.nan
        a['fc_age']=(pd.Series(times,index=times)-selected).dt.total_seconds()/60
        a.loc[~valid,'fc_age']=np.nan
        a['ts']=times; a['unit']=u
        out.append(a[['ts','unit','fc_mean','fc_max','fc_age']])
    return w.merge(pd.concat(out),on=['ts','unit'],validate='one_to_one')


WEATHER=['rain','rain_lag1','rain_lag2','rain_lag3','gauge_wet','ring2_5','ring5_10','coverage_change','island_wet','fc_mean','fc_max','fc_age']
BASE=['log_y','relative','log_city','city_relative','level','log_expected','pattern_change',
      'how_sin','how_cos','hod_sin','hod_cos','dow','half_hour','month','daytype','public','school']
BASE += [f'{x}_lag{k}' for k in (1,2,3) for x in ('log_y','relative','log_city','city_relative')]
BASE += [f'unit_{k}' for k in range(6)]


def make_features(counts,weather,pattern,horizon,start,end):
    d=add_expected(counts,pattern)
    d['log_y']=np.log(d.Y.clip(lower=1)); d['log_city']=np.log(d.city.clip(lower=1))
    d['relative']=np.log(d.Y.clip(lower=1)/d.expected_now.clip(lower=1))
    d['city_relative']=np.log(d.city.clip(lower=1)/(d.city_pattern*d.level).clip(lower=1))
    lookup=d.set_index(['unit','ts'])
    for k in (1,2,3):
        keys=pd.MultiIndex.from_arrays([d.unit,d.ts-pd.Timedelta(minutes=30*k)])
        for col in ['log_y','relative','log_city','city_relative','valid']:
            d[f'{col}_lag{k}']=lookup[col].reindex(keys).to_numpy()
    targetkeys=pd.MultiIndex.from_arrays([d.unit,d.ts+pd.Timedelta(minutes=horizon)])
    target=lookup[['Y','pattern','valid']].reindex(targetkeys)
    d['target_count']=target.Y.to_numpy(); d['target_expected']=target.pattern.to_numpy()*d.level
    d['target']=np.log(d.target_count.clip(lower=1)/d.target_expected.clip(lower=1))
    d['persistence']=d.relative
    d['log_expected']=np.log(d.target_expected.clip(lower=1)); d['pattern_change']=np.log(target.pattern.to_numpy()/d.pattern)
    th=d.ts+pd.Timedelta(minutes=horizon); how=th.dt.day_of_week*48+th.dt.hour*2+th.dt.minute//30
    d['how_sin']=np.sin(2*np.pi*how/336); d['how_cos']=np.cos(2*np.pi*how/336)
    d['hod_sin']=np.sin(2*np.pi*how/48); d['hod_cos']=np.cos(2*np.pi*how/48)
    d['dow']=th.dt.day_of_week; d['half_hour']=th.dt.hour*2+th.dt.minute//30; d['month']=th.dt.month
    hol=pd.read_csv(ROOT/'data/static/holidays.csv',parse_dates=['date'])
    # Inspect source column names in tests; dates are scheduled, not outcomes.
    public=set(hol.loc[hol.kind.eq('public'),'date'])
    school=set(hol.loc[hol.kind.eq('school'),'date'])
    d['public']=th.dt.normalize().isin(public).astype(int); d['school']=th.dt.normalize().isin(school).astype(int)
    d['daytype']=np.where(d.public,2,np.where(d.dow>=5,1,0))
    for k,u in enumerate(UNITS): d[f'unit_{k}']=d.unit.eq(u).astype(int)
    ok=d.ts.between(pd.Timestamp(start),pd.Timestamp(end)-pd.Timedelta(minutes=horizon)) & d.valid & target.valid.fillna(False).to_numpy(dtype=bool)
    for k in (1,2,3): ok &= d[f'valid_lag{k}'].fillna(False).astype(bool)
    ok &= d.target.notna() & d.level.notna()
    d=d[ok].merge(weather,on=['ts','unit'],how='left',validate='one_to_one')
    assert not d.duplicated(['ts','unit']).any()
    return d.reset_index(drop=True)
