"""Step-22 boundaries: causal expected levels, cell-ID joins and exact day-weighted metrics."""
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from analysis.s22_data import (UNITS,BASE,WEATHER,geography,make_features,fit_pattern,START)
from analysis.s22_metrics import ranked_metrics,mae_days


def test_regions_partition_eligible_ids():
    mapping,_=geography()
    ordinary=mapping[mapping.unit!='Central Area']
    assert len(ordinary)==374 and ordinary.cell.nunique()==374
    central=set(mapping[mapping.unit=='Central'].cell)
    assert set(mapping[mapping.unit=='Central Area'].cell)<=central
    assert len(mapping[mapping.unit=='Central Area'])==16


def toy_counts():
    ts=pd.date_range('2022-03-23','2022-04-12',freq='30min')
    frames=[]
    for i,u in enumerate(UNITS):
        frames.append(pd.DataFrame(dict(ts=ts,unit=u,Y=100.+i,city=1000.,valid=True,regime=0)))
    return pd.concat(frames,ignore_index=True)


def test_expected_and_features_do_not_use_future_outcomes():
    c=toy_counts(); times=c.ts.unique()
    w=c[['ts','unit']].copy()
    for x in WEATHER: w[x]=0.
    hm=pd.Index([(d*48+h)*100+4 for d in range(7) for h in range(48)])
    hm=hm.union(pd.Index([(d*48+h)*100+3 for d in range(7) for h in range(48)]))
    pattern=dict(hm=pd.Series(1000.,index=hm),shares=pd.Series({u:.1 for u in UNITS}))
    issue=pd.Timestamp('2022-04-03 12:00')
    d=make_features(c,w,pattern,60,START,'2022-04-10 23:30')
    changed=c.copy(); changed.loc[changed.ts>issue,'Y']*=10; changed.loc[changed.ts>issue,'city']*=10
    e=make_features(changed,w,pattern,60,START,'2022-04-10 23:30')
    a=d[d.ts==issue].sort_values('unit'); b=e[e.ts==issue].sort_values('unit')
    np.testing.assert_allclose(a[BASE],b[BASE])
    np.testing.assert_allclose(a.target_expected,b.target_expected)
    assert (a.target_count.to_numpy()!=b.target_count.to_numpy()).all()
    # Changes in a later training period must not enter an earlier fold's baseline.
    old=fit_pattern(c,'2022-04-03 12:00'); new=fit_pattern(changed,'2022-04-03 12:00')
    pd.testing.assert_series_equal(old['hm'],new['hm']); pd.testing.assert_series_equal(old['shares'],new['shares'])


def test_exact_bootstrap_ap_and_alert_workload():
    y=np.array([0,1,0,1,1,0]); score=np.array([.1,.8,.8,.3,.3,.2]); days=np.array([0,0,1,1,2,2])
    W=np.array([[1,1,1],[2,0,1],[0,1,2]])
    actual=ranked_metrics(y,score,days,W,.4)
    for j,dayweights in enumerate(W):
        weights=dayweights[days]
        expected=average_precision_score(y,score,sample_weight=weights)
        assert abs(actual[j,0]-expected)<1e-12
        idx=np.repeat(np.arange(len(y)),weights)
        idx=idx[np.argsort(-score[idx],kind='stable')]; k=int(np.ceil(.4*len(idx)))
        assert abs(actual[j,1]-y[idx[:k]].sum()/k)<1e-12
        assert abs(actual[j,2]-y[idx[:k]].sum()/y[idx].sum())<1e-12
    assert np.isnan(ranked_metrics(np.zeros(6),score,days,W,.4)).all()


def test_bootstrap_mae_uses_joint_day_weights():
    y=np.array([1.,2.,4.,8.]); p=np.array([1.,1.,2.,4.]); day=np.array([0,0,1,1]); W=np.array([[1,1],[2,0],[0,2]])
    np.testing.assert_allclose(mae_days(y,p,day,W),[1.75,.5,3.])


def test_rain_window_and_issued_forecast_boundaries():
    from analysis.s22_data import trailing_rain,latest_issue
    bins=pd.date_range('2022-04-01 09:25','2022-04-01 10:05',freq='5min')
    depth=pd.DataFrame({'gauge':[500.,1.,2.,3.,4.,5.,6.,7.,900.]},index=bins)
    # At 10:00, (09:30,10:00] excludes 09:30 and the future 10:05 value.
    out=trailing_rain(depth,pd.DatetimeIndex(['2022-04-01 10:00']))
    assert out.iloc[0,0]==2*(2+3+4+5+6+7)
    issues=pd.DatetimeIndex(['2022-04-01 08:00','2022-04-01 09:00','2022-04-01 10:00'])
    times=pd.DatetimeIndex(['2022-04-01 07:00','2022-04-01 09:00','2022-04-01 09:01'])
    picked=latest_issue(issues,times)
    assert pd.isna(picked.iloc[0])
    assert picked.iloc[1]==pd.Timestamp('2022-04-01 08:00')
    assert picked.iloc[2]==pd.Timestamp('2022-04-01 09:00')
