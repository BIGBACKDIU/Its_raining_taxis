"""Fixed step-22 metrics and reporting; evaluates saved predictions without refitting."""
from __future__ import annotations
import numpy as np
import pandas as pd
from analysis.s22_data import ROOT,TABLES,UNITS,LOCAL
from analysis.common import SEED


def ranked_metrics(y,score,day,W,rate):
    """Exact AP with tied ranks and integer day weights; fixed-workload precision/recall."""
    order=np.argsort(-np.asarray(score),kind='stable')
    y=np.asarray(y)[order]; day=np.asarray(day)[order]; score=np.asarray(score)[order]
    ends=np.r_[np.flatnonzero(np.diff(score)!=0),len(score)-1]
    out=np.full((len(W),3),np.nan)
    for start in range(0,len(W),100):
        weights=W[start:start+100,day]
        positive=weights*y[None,:]
        tp=np.cumsum(positive,axis=1); total=np.cumsum(weights,axis=1)
        group_tp=tp[:,ends]; group_total=total[:,ends]
        inc=np.diff(np.c_[np.zeros(len(weights)),group_tp],axis=1)
        precision=np.divide(group_tp,group_total,out=np.zeros_like(group_tp,dtype=float),where=group_total>0)
        P=positive.sum(1); N=weights.sum(1)
        valid=(P>0)&(P<N)
        ap=np.divide((inc*precision).sum(1),P,out=np.full(len(P),np.nan),where=valid)
        k=np.ceil(rate*N)
        before=total-weights
        take=np.minimum(weights,np.maximum(k[:,None]-before,0))
        true_alert=(take*y[None,:]).sum(1)
        pr=np.divide(true_alert,k,out=np.full(len(P),np.nan),where=(k>0)&valid)
        recall=np.divide(true_alert,P,out=np.full(len(P),np.nan),where=valid)
        out[start:start+len(weights)]=np.c_[ap,pr,recall]
    return out


def ci(x):
    good=np.asarray(x)[np.isfinite(x)]
    return np.quantile(good,[.025,.975]) if len(good) else (np.nan,np.nan)


def mae_days(y,p,day,W):
    n=np.bincount(day,minlength=W.shape[1]); s=np.bincount(day,weights=np.abs(y-p),minlength=W.shape[1])
    den=W@n
    return np.divide(W@s,den,out=np.full(len(W),np.nan),where=den>0)


def evaluate(predictions):
    rates=pd.read_csv(TABLES/'s22_alert_rates.csv').set_index(['horizon','target','unit']).alert_rate
    days=sorted(predictions.ts.dt.normalize().unique()); day_index={d:i for i,d in enumerate(days)}
    rng=np.random.default_rng(SEED)
    weights=rng.multinomial(len(days),np.full(len(days),1/len(days)),size=1000)
    W=np.r_[np.ones((1,len(days)),dtype=int),weights]
    rows=[]; gains=[]
    for (h,target),part in predictions.groupby(['horizon','target_name'],sort=True):
        for unit in ['Pooled']+UNITS:
            a=part if unit=='Pooled' else part[part.unit.eq(unit)]
            for subset in ['all','storm']:
                d=(a if subset=='all' else a[a.storm]).sort_values(['ts','unit'],kind='stable')
                if d.empty:
                    for model in ['persistence','seasonal','linear','lightgbm']:
                        for weather in (0,1):
                            rows.append(dict(horizon=h,target=target,unit=unit,subset=subset,model=model,weather=weather,
                                             n=0,days=0,mean_vacant=np.nan,mean_expected=np.nan,floor_count=0))
                        gains.append(dict(horizon=h,target=target,unit=unit,subset=subset,model=model,n=0,
                                          no_weather=np.nan,with_weather=np.nan,gain=np.nan,lo=np.nan,hi=np.nan,
                                          defined_bootstraps=0,gain_unit='percent lower MAE' if target=='T1' else 'PR-AUC difference'))
                    continue
                y=d.truth.to_numpy(); day=d.ts.dt.normalize().map(day_index).to_numpy(int)
                base=mae_days(y,d.persistence_0.to_numpy(),day,W) if target=='T1' else None
                for model in ['persistence','seasonal','linear','lightgbm']:
                    outputs=[]
                    for weather in (0,1):
                        score=d[f'{model}_{weather}'].to_numpy()
                        row=dict(horizon=h,target=target,unit=unit,subset=subset,model=model,weather=weather,
                                 n=len(d),days=d.ts.dt.normalize().nunique(),mean_vacant=float(d.target_count.mean()),
                                 mean_expected=float(d.target_expected.mean()),floor_count=int((d.target_count<1).sum()))
                        if target=='T1':
                            b=mae_days(y,score,day,W); skill=1-b/base
                            row.update(mae=b[0],mae_lo=ci(b[1:])[0],mae_hi=ci(b[1:])[1],
                                       mae_skill=skill[0],skill_lo=ci(skill[1:])[0],skill_hi=ci(skill[1:])[1])
                            outputs.append(b)
                        else:
                            rate=float(rates.loc[h,target,unit]); b=ranked_metrics(y,score,day,W,rate)
                            row.update(base_rate=float(y.mean()),alert_rate=rate,alerts=int(np.ceil(rate*len(d))))
                            for j,name in enumerate(['pr_auc','precision','recall']):
                                lo,hi=ci(b[1:,j]); row.update({name:b[0,j],name+'_lo':lo,name+'_hi':hi})
                            outputs.append(b[:,0])
                        rows.append(row)
                    gain=100*(outputs[0]-outputs[1])/outputs[0] if target=='T1' else outputs[1]-outputs[0]
                    lo,hi=ci(gain[1:])
                    gains.append(dict(horizon=h,target=target,unit=unit,subset=subset,model=model,n=len(d),
                                      no_weather=outputs[0][0],with_weather=outputs[1][0],gain=gain[0],lo=lo,hi=hi,
                                      defined_bootstraps=int(np.isfinite(gain[1:]).sum()),
                                      gain_unit='percent lower MAE' if target=='T1' else 'PR-AUC difference'))
        print('evaluated',h,target,flush=True)
    return pd.DataFrame(rows),pd.DataFrame(gains)


def figure(gains,nstorms):
    import matplotlib.pyplot as plt
    from analysis.common import style,BLUE,ORANGE,MUTED
    style(); fig,axes=plt.subplots(2,2,figsize=(13,10),sharey=True)
    units=['Pooled']+UNITS
    for r,target in enumerate(['T1','T2_15']):
        for col,h in enumerate([30,60]):
            ax=axes[r,col]
            for offset,subset,color in [(-.13,'all',BLUE),(.13,'storm',ORANGE)]:
                q=gains[(gains.target==target)&(gains.horizon==h)&gains.model.eq('lightgbm')&gains.subset.eq(subset)].set_index('unit').reindex(units)
                y=np.arange(len(units))+offset
                ax.hlines(y,q.lo,q.hi,color=color,lw=1.1)
                ax.plot(q.gain,y,'o',markersize=4,color=color,label='All times' if subset=='all' else 'Storm windows')
            ax.axvline(0,color=MUTED,lw=.8)
            ax.axvline(5 if target=='T1' else .02,color=MUTED,lw=.7,ls='--')
            ax.set_yticks(np.arange(len(units)),units); ax.set_ylim(len(units)-.5,-.5)
            ax.set_title(f'{h} min: '+('log-relative vacant count' if target=='T1' else '15% regional shortfall'))
            ax.set_xlabel('Weather gain: % lower MAE' if target=='T1' else 'Weather gain: PR-AUC difference')
    axes[0,0].legend(loc='best',fontsize=9)
    fig.suptitle(f'Step 22: LightGBM weather gain on fresh October holdout ({nstorms} storm onsets)',fontsize=15)
    fig.text(.5,.015,'1–24 Oct 2026 | paired day-block 95% CIs (1,000 draws) | dashed = registered materiality threshold\n'
             'Pooled result includes Central Area within Central Region. Storm results descriptive if fewer than 8 onsets.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.06,1,.96])
    out=ROOT/'outputs/figures/s22_weather_gain'
    fig.savefig(str(out)+'.png',dpi=180,bbox_inches='tight'); fig.savefig(str(out)+'.svg',bbox_inches='tight'); plt.close(fig)


def write_report(stats,gains,onsets,commit,predictions):
    primary=gains[gains.model.eq('lightgbm')&gains.unit.eq('Pooled')&gains.subset.eq('storm')&gains.target.isin(['T1','T2_15'])].copy()
    primary['numerical_rule']=np.where(primary.target.eq('T1'),primary.gain>=5,primary.gain>=.02)&primary.lo.gt(0)
    primary['adequate_storm_count']=len(onsets)>=8
    primary['materiality_confirmed']=primary.numerical_rule&primary.adequate_storm_count
    primary.to_csv(TABLES/'s22_materiality.csv',index=False)
    support=stats[(stats.model=='persistence')&stats.weather.eq(0)].copy()
    support.to_csv(TABLES/'s22_support.csv',index=False)
    numeric_status='met' if primary.numerical_rule.any() else 'not met'
    status=numeric_status if len(onsets)>=8 else f'{numeric_status} numerically; confirmation unavailable (fewer than eight storms)'
    power='adequate under the registered >=8-onset rule' if len(onsets)>=8 else 'descriptive only: fewer than eight onsets'
    lines=[f'\n## Step 22: regional storm forecasting (fresh holdout; decision 150)\n',
      f'- Frozen model/code commit: `{commit}`, pushed before any October labels, storm counts or scores.',
      '- Development used only Apr 2022-Mar 2025 and calibration Apr-Sep 2025. Settings and tree counts',
      '  were fixed before refitting Apr 2022-Sep 2026. The old test year entered only that final refit,',
      '  which is separately logged; frozen analyses and their outputs remain unchanged.',
      f'- Fresh holdout: 1-24 October 2026, scored once. Storm onsets: **{len(onsets)}**; power: **{power}**.',
      '- Onsets require >=25% of the same working gauges to change from dry to >=1 mm/h within 30 min;',
      '  candidates within three hours are merged. Storm issue windows are -60 to +120 minutes.',
      '- Paired 1,000-draw issue-day bootstrap CIs. Six overlapping units; the pooled comparison is primary.',
      '  T1 is log(count / issue-time expected); T2 is a 15% shortfall, with 10%/20% checks reported.',
      '- Fixed alert workloads equal calibration base rates, not October base rates. All model x weather x',
      '  horizon x target x unit x subset combinations are retained; no holdout model selection occurred.',
      '- **Pooled LightGBM storm comparisons** (positive gain favours weather):']
    for row in primary.itertuples():
        unit='% lower MAE' if row.target=='T1' else 'PR-AUC'
        lines.append(f'  - {row.horizon} min {row.target}: {row.no_weather:.5f} without / {row.with_weather:.5f} with weather; '
                     f'gain {row.gain:+.4f} {unit}, CI [{row.lo:+.4f}, {row.hi:+.4f}].')
    lines += [f'- Registered materiality threshold: **{status}**. Numerical crossings are reported separately from the',
      '  eight-onset power requirement; 10%/20% labels and individual regions are checks, not extra primary tests.',
      '- Absolute supply and expected counts, base rates, alert counts and sample sizes are in s22_support.csv.',
      '  MAE is measured on a log ratio, not taxis. CIs are pointwise and the 24-day period cannot establish',
      '  general performance across seasons or feed regimes. Multiple-day dependence can widen uncertainty.',
      '- Sparse gauge archives omit zeros and observation timestamps: preceding-day health is causal, but',
      '  cannot prove intraday completeness. Unknown midnight intervals remain missing and are imputed from',
      '  fitting data. Seven coastal cell centres use their frozen planning-area region; Central Area keeps',
      '  the URA centre-within definition. Neither eligibility nor membership is selected using holdout outcomes.',
      '- Outputs: s22_audit_*.csv, s22_unit_cells.csv, s22_development.csv, s22_alert_rates.csv,',
      '  s22_model_manifest.csv, s22_storm_onsets.csv, s22_metrics.csv, s22_weather_gains.csv,',
      '  s22_materiality.csv, s22_support.csv; one figure s22_weather_gain.png/.svg.',
      '- These results concern vacant-taxi supply. Frozen gauge associations and earlier forecasting conclusions',
      '  remain as originally reported for their own targets, periods and spatial scales.']
    with (ROOT/'outputs/phase2_progress.md').open('a') as f: f.write('\n'.join(lines)+'\n')
    summary=[f'### Regional storm forecasting (fresh holdout)\n',
      f'A separately registered analysis forecasts the Central Area and five URA regions 30/60 minutes ahead,',
      f'using approaching rain as well as local weather. It scores 1-24 October 2026 once after a pushed model',
      f'freeze. There are {len(onsets)} storm onsets ({power}); the registered pooled materiality threshold is **{status}**.']
    for row in primary.itertuples():
        summary.append(f'At {row.horizon} min, '+(f'T1 MAE weather gain is {row.gain:+.2f}% [{row.lo:+.2f}, {row.hi:+.2f}].' if row.target=='T1'
             else f'15%-shortfall PR-AUC weather gain is {row.gain:+.4f} [{row.lo:+.4f}, {row.hi:+.4f}].'))
    q=support[(support.unit=='Pooled')&support.subset.eq('all')&support.target.eq('T1')]
    if len(q):
        x=q.iloc[0]; summary.append(f'The pooled target has {x.mean_vacant:.1f} observed versus {x.mean_expected:.1f} expected vacant taxis on average (overlapping regions).')
    summary.append('This adds two logged uses: the fixed refit of the old test year, then the fresh holdout scoring.\n'
      'All models, regions, thresholds and subsets are reported in `s22_*.csv`; paired day-block 95% CIs and `s22_weather_gain`.\n'
      'This short holdout tests regional supply forecasts, with no model changes after scoring. Alert workload is fixed to calibration base rates.\n'
      'Earlier frozen forecasting results keep their original scope.\n')
    p=ROOT/'outputs/summary.md'; text=p.read_text(); assert '### Regional storm forecasting (fresh holdout)' not in text
    p.write_text(text.replace('## 4. Caveats','\n'.join(summary)+'\n## 4. Caveats'))
