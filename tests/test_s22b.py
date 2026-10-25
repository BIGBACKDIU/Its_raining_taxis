"""Backward holdout checks, without opening 2019 targets or scoring its models."""
import ast
import inspect
import numpy as np
import pandas as pd
from analysis import s22_data as frozen
from analysis.s22b_data import forecast_audit


def test_retrospective_forecasts_are_not_backdated():
    rows=[]
    # The valid 10:00 forecast was updated the following day, so it is unavailable at 10:30.
    for issued,start,end in [('2019-06-14 09:00','2019-06-14 09:00','2019-06-14 11:00'),
                              ('2019-06-15 08:43','2019-06-14 10:00','2019-06-14 12:00')]:
        rows.append(dict(issued=pd.Timestamp(issued),item_ts=pd.Timestamp(start),valid_start=pd.Timestamp(start),
                         valid_end=pd.Timestamp(end),area='City'))
    times=pd.DatetimeIndex(['2019-06-14 10:30','2019-06-15 09:00'])
    issues,slots=forecast_audit(pd.DataFrame(rows),times)
    assert slots.naive_rejected_future_issue.iloc[0]
    assert slots.strict_selected_issue.iloc[0]==pd.Timestamp('2019-06-14 09:00')
    assert slots.strict_eligible.iloc[0]
    assert not slots.strict_eligible.iloc[1], 'a late update cannot remain valid after expiry'
    assert issues.issued_at_or_after_end.sum()==1


def test_exact_issue_is_unavailable_and_no_invalid_fallback():
    rows=[]
    for issued,start,end in [('2019-01-01 09:00','2019-01-01 09:00','2019-01-01 12:00'),
                             ('2019-01-01 10:00','2019-01-01 07:00','2019-01-01 09:00')]:
        rows.append(dict(issued=pd.Timestamp(issued),item_ts=pd.Timestamp(start),valid_start=pd.Timestamp(start),
                         valid_end=pd.Timestamp(end),area='City'))
    _,s=forecast_audit(pd.DataFrame(rows),pd.DatetimeIndex(['2019-01-01 10:00','2019-01-01 10:30']))
    assert s.strict_eligible.iloc[0], 'at equality, select the earlier issue'
    assert not s.strict_eligible.iloc[1], 'latest issued but invalid means missing, not fallback'


def test_adapter_has_no_fit_or_tune_calls():
    import analysis.s22b_data as adapter
    tree=ast.parse(inspect.getsource(adapter))
    calls=[n.func.attr for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
    assert 'fit' not in calls and 'fit_transform' not in calls
    # Geography and target definitions are the originals; the separate adapter supplies only calendar bits.
    assert adapter.frozen.make_features is frozen.make_features


def test_2019_calendar_adapter_preserves_count_features():
    from analysis.s22b_data import features
    times=pd.date_range('2019-05-01','2019-06-06',freq='30min')
    parts=[]
    for u in frozen.UNITS:
        parts.append(pd.DataFrame(dict(ts=times,unit=u,Y=100.,city=1000.,valid=True,regime=0)))
    counts=pd.concat(parts,ignore_index=True)
    weather=counts[['ts','unit']].copy()
    for col in frozen.WEATHER:weather[col]=0.
    hm=pd.Index([how*100+month for how in range(336) for month in range(1,13)])
    pattern=dict(hm=pd.Series(1000.,index=hm),shares=pd.Series({u:.1 for u in frozen.UNITS}))
    d=features(counts,weather,pattern,60)
    original=frozen.make_features(counts,weather,pattern,60,'2019-01-01','2019-12-31 23:30')
    np.testing.assert_allclose(d.target_expected,original.target_expected)
    np.testing.assert_allclose(d[frozen.BASE[:7]],original[frozen.BASE[:7]])
    for date in ('2019-05-20','2019-06-05'):
        mask=(d.ts+pd.Timedelta('60min')).dt.normalize().eq(pd.Timestamp(date))
        assert d.loc[mask,'public'].eq(1).all() and mask.any()
    mask=(d.ts+pd.Timedelta('60min')).dt.normalize().eq(pd.Timestamp('2019-06-02'))
    assert d.loc[mask,'school'].eq(1).all() and mask.any()


def test_whole_archive_gap_is_unknown_not_dry(tmp_path,monkeypatch):
    import analysis.s22b_data as adapter
    rain=tmp_path/'rain';rain.mkdir()
    for month in range(1,13):
        prefix=f'2019-{month:02d}'
        days=pd.date_range(prefix+'-01',pd.Timestamp(prefix+'-01')+pd.offsets.MonthEnd(0))
        complete=pd.DataFrame(dict(date=days,station_id='G1',n_readings=287,mm_total=0.))
        # Jan 2 has no readings. Jan 3 is a real complete, all-dry day with no positive records.
        complete=complete[complete.date!=pd.Timestamp('2019-01-02')]
        complete.to_csv(rain/f'{prefix}_completeness.csv.gz',index=False)
        pd.DataFrame(dict(station_id=['G1'])).to_csv(rain/f'{prefix}_stations.csv.gz',index=False)
    pd.DataFrame(columns=['ts','station_id','mm']).to_csv(rain/'2019-01_readings.csv.gz',index=False)
    monkeypatch.setattr(adapter,'RAW',tmp_path)
    reader=adapter.ArchiveReadings()
    out=reader.read_csv(rain/'2019-01_readings.csv.gz',parse_dates=['ts'])
    assert len(out)==288 and out.mm.isna().all()
    assert out.ts.dt.normalize().eq(pd.Timestamp('2019-01-02')).all()
    assert not out.ts.dt.normalize().eq(pd.Timestamp('2019-01-03')).any()
