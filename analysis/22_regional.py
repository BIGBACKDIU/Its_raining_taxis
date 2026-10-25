"""Separately registered step 22. develop -> freeze -> push -> score (once).

No command reads October outcome arrays except score, whose guard verifies the pushed freeze.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import joblib
import numpy as np
import pandas as pd
from scipy.special import expit
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import average_precision_score, mean_absolute_error
from lightgbm import LGBMRegressor,LGBMClassifier,early_stopping,log_evaluation

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analysis.s22_data import (ROOT,LOCAL,TABLES,UNITS,START,FIT_END,CAL_END,FINAL_END,HOLD_START,HOLD_END,
                               BASE,WEATHER,sha,geography,count_history,october_counts,weather_history,fit_pattern,make_features)
from analysis.common import SEED,log_test_scoring

THRESHOLDS=[.15,.10,.20]
TARGETS=['T1','T2_15','T2_10','T2_20']
LINEAR_GRID=[.1,10.,1000.]
LGB_GRID=[(7,200),(15,200),(15,500),(31,500)]
FOLDS=[('2023-09-30 23:30','2023-10-01','2024-03-31 23:30'),
       ('2024-03-31 23:30','2024-04-01','2024-09-30 23:30'),
       ('2024-09-30 23:30','2024-10-01','2025-03-31 23:30')]


def label(d,target):
    if target=='T1': return d.target.to_numpy()
    threshold=int(target.split('_')[1])/100
    return (d.target_count<=(1-threshold)*d.target_expected).to_numpy(dtype=int)


def preprocessor():
    return make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),StandardScaler())


def fit_model(train,valid,target,weather,kind,setting,iterations=None):
    cols=BASE+(WEATHER if weather else [])
    transform=preprocessor(); X=transform.fit_transform(train[cols]); y=label(train,target)
    if kind=='linear':
        model=Ridge(alpha=setting) if target=='T1' else LogisticRegression(C=1/setting,max_iter=600,random_state=SEED)
        model.fit(X,y); n=0
    else:
        params=dict(n_estimators=iterations or 600,learning_rate=.04,num_leaves=setting[0],min_child_samples=setting[1],
                    reg_lambda=1.,verbosity=-1,random_state=SEED,n_jobs=1,deterministic=True,force_col_wise=True)
        model=LGBMRegressor(objective='regression_l1',**params) if target=='T1' else LGBMClassifier(objective='binary',**params)
        fitargs={}
        if valid is not None:
            fitargs=dict(eval_set=[(transform.transform(valid[cols]),label(valid,target))],
                         eval_metric='l1' if target=='T1' else 'average_precision',
                         callbacks=[early_stopping(40,first_metric_only=True,verbose=False),log_evaluation(0)])
        model.fit(X,y,**fitargs); n=model.best_iteration_ or model.n_estimators
    return dict(transform=transform,model=model,columns=cols,kind=kind,target=target,weather=weather,
                setting=setting,iterations=n)


def predict(bundle,d):
    x=bundle['transform'].transform(d[bundle['columns']])
    return bundle['model'].predict(x) if bundle['target']=='T1' else bundle['model'].predict_proba(x)[:,1]


def loss(y,p,target):
    return mean_absolute_error(y,p) if target=='T1' else -average_precision_score(y,p)


def baseline_fit(d,kind,weather):
    centre=d.persistence.to_numpy() if kind=='persistence' else np.zeros(len(d))
    correction=None
    if weather:
        cols=WEATHER+[f'unit_{k}' for k in range(6)]
        transform=preprocessor(); x=transform.fit_transform(d[cols])
        reg=Ridge(alpha=1000.).fit(x,d.target-centre)
        correction=dict(transform=transform,model=reg,columns=cols)
        centre=centre+reg.predict(x)
    residuals={u:np.sort((d.target.to_numpy()-centre)[d.unit.eq(u).to_numpy()]) for u in UNITS}
    return dict(kind=kind,weather=weather,correction=correction,residuals=residuals)


def baseline_predict(bundle,d,target):
    p=d.persistence.to_numpy().copy() if bundle['kind']=='persistence' else np.zeros(len(d))
    if bundle['correction']:
        c=bundle['correction']; p+=c['model'].predict(c['transform'].transform(d[c['columns']]))
    if target=='T1': return p
    threshold=int(target.split('_')[1])/100; out=np.full(len(d),np.nan)
    for u in UNITS:
        mask=d.unit.eq(u).to_numpy(); residual=bundle['residuals'][u]
        out[mask]=(np.searchsorted(residual,np.log(1-threshold)-p[mask],side='right')+.5)/(len(residual)+1)
    return out


def histories(end):
    LOCAL.mkdir(parents=True,exist_ok=True)
    tag=pd.Timestamp(end).strftime('%Y%m%d')
    cf=LOCAL/f'counts_{tag}.parquet'; wf=LOCAL/f'weather_{tag}.parquet'
    if cf.exists(): c=pd.read_parquet(cf)
    else:
        c=count_history(end); c.to_parquet(cf,index=False)
    if wf.exists(): w=pd.read_parquet(wf)
    else:
        w=weather_history(end); w.to_parquet(wf,index=False)
    assert c.ts.max()<=end and w.ts.max()<=end
    return c,w


def simplicity(setting,kind):
    # Larger linear penalties, fewer leaves and larger leaves are the registered tie preferences.
    return (-float(setting),) if kind=='linear' else (int(setting[0]),-int(setting[1]))


def development_job(job,fold_data,calibration):
    h,target,weather,kind=job
    grid=LINEAR_GRID if kind=='linear' else LGB_GRID
    rows=[]; candidates=[]
    for setting in grid:
        scores=[]
        for k in range(len(FOLDS)):
            a,b=fold_data[h,k]
            model=fit_model(a,b if kind=='lightgbm' else None,target,weather,kind,setting,
                            iterations=300 if kind=='lightgbm' else None)
            value=loss(label(b,target),predict(model,b),target); scores.append(value)
            rows.append(dict(stage='fold',fold=k,horizon=h,target=target,weather=weather,model=kind,
                             setting=json.dumps(setting),loss=value,iterations=model['iterations']))
        candidates.append((float(np.mean(scores)),setting))
    candidates.sort(key=lambda x:(x[0],simplicity(x[1],kind)))
    tr,ca=calibration[h]; finalists=[]
    for _,setting in candidates[:2]:
        model=fit_model(tr,ca if kind=='lightgbm' else None,target,weather,kind,setting)
        value=loss(label(ca,target),predict(model,ca),target)
        finalists.append((value,setting,model['iterations']))
        rows.append(dict(stage='calibration',fold=-1,horizon=h,target=target,weather=weather,model=kind,
                         setting=json.dumps(setting),loss=value,iterations=model['iterations']))
    finalists.sort(key=lambda x:(x[0],simplicity(x[1],kind)))
    best=finalists[0]; key=f'{h}_{target}_{int(weather)}_{kind}'
    choice=dict(setting=best[1],iterations=best[2],calibration_loss=best[0])
    return key,choice,rows


def develop():
    from concurrent.futures import ThreadPoolExecutor,as_completed
    assert not (LOCAL/'freeze.json').exists(), 'models are already frozen'
    c,w=histories(CAL_END)
    fold_data={}; calibration={}
    for h in (30,60):
        for k,(train_end,valid_start,valid_end) in enumerate(FOLDS):
            pattern=fit_pattern(c,train_end)
            tr=make_features(c,w,pattern,h,START,train_end)
            va=make_features(c,w,pattern,h,valid_start,valid_end)
            fold_data[h,k]=(tr,va)
        pattern=fit_pattern(c,FIT_END)
        calibration[h]=(make_features(c,w,pattern,h,START,FIT_END),make_features(c,w,pattern,h,'2025-04-01',CAL_END))
    rows=[]; selected={}; rates=[]; jobs=[]
    for h in (30,60):
        _,ca=calibration[h]
        for target in TARGETS:
            if target!='T1':
                for u in ['Pooled']+UNITS:
                    a=ca if u=='Pooled' else ca[ca.unit.eq(u)]
                    rates.append(dict(horizon=h,target=target,unit=u,alert_rate=float(label(a,target).mean()),n=len(a)))
            for weather in (False,True):
                for kind in ('linear','lightgbm'): jobs.append((h,target,weather,kind))
    pd.DataFrame(rates).to_csv(TABLES/'s22_alert_rates.csv',index=False)
    # Native estimators release the GIL. Independent jobs share read-only folds; each tree fit has one thread.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(development_job,job,fold_data,calibration) for job in jobs]
        for future in as_completed(futures):
            key,choice,result=future.result(); selected[key]=choice; rows.extend(result)
            (LOCAL/'selection.json').write_text(json.dumps(selected,indent=2,sort_keys=True))
            pd.DataFrame(rows).to_csv(TABLES/'s22_development.csv',index=False)
            print('chosen',key,choice,flush=True)
    assert len(selected)==32
    print('Development ends September 2025. October and old test outcomes remain unopened.',flush=True)


def freeze():
    assert not (LOCAL/'freeze.json').exists()
    selected=json.loads((LOCAL/'selection.json').read_text())
    log_test_scoring('22_regional.py --part freeze','Fixed-setting final refit on Apr 2022-Sep 2026; old test becomes training, no tuning',
                     analysis='step 22',note='Choices and alert rates fixed using fit/calibration only; fresh October outcomes unopened')
    c,w=histories(FINAL_END); pattern=fit_pattern(c,FINAL_END)
    joblib.dump(pattern,LOCAL/'pattern.joblib')
    for h in (30,60):
        d=make_features(c,w,pattern,h,START,FINAL_END)
        for weather in (False,True):
            for kind in ('persistence','seasonal'):
                joblib.dump(baseline_fit(d,kind,weather),LOCAL/f'{h}_{int(weather)}_{kind}.joblib')
            for target in TARGETS:
                for kind in ('linear','lightgbm'):
                    key=f'{h}_{target}_{int(weather)}_{kind}'; s=selected[key]
                    b=fit_model(d,None,target,weather,kind,s['setting'],iterations=s['iterations'] if kind=='lightgbm' else None)
                    joblib.dump(b,LOCAL/f'{key}.joblib')
        print('frozen horizon',h,'rows',len(d),flush=True)
    # Include preprocessing, settings, rates and every byte of executable step-22/pipeline source in freeze.
    paths=sorted(LOCAL.glob('*.joblib'))+[LOCAL/'selection.json',TABLES/'s22_alert_rates.csv']
    paths += [LOCAL/'counts_20260930.parquet',LOCAL/'weather_20260930.parquet']
    paths += [ROOT/p for p in ['analysis/s22_data.py','analysis/22_regional.py','analysis/s22_metrics.py','pipeline/fetch_month.py','analysis/common.py','analysis/geo.py','analysis/01_panel.py',
        'pipeline/grid.py','data/static/holidays.csv','data/static/phase2/subzone.geojson','outputs/tables/s22_unit_cells.csv']]
    paths += sorted(RAWFILE for folder in ['taxi','rain','forecast','logs'] for RAWFILE in (ROOT/'data/raw'/folder).glob('2026-10*'))
    manifest=pd.DataFrame([dict(path=str(p.relative_to(ROOT)),sha256=sha(p),bytes=p.stat().st_size) for p in paths])
    manifest.to_csv(TABLES/'s22_model_manifest.csv',index=False)
    (LOCAL/'freeze.json').write_text(json.dumps(dict(manifest_sha256=sha(TABLES/'s22_model_manifest.csv'),
        training_end=str(FINAL_END),fresh_holdout_unopened=True),indent=2))
    lines=['\n151. **Step-22 audit, development and frozen refit (before fresh-holdout scoring).**',
      '    October audit: 2,304/2,304 requested snapshots present; 2,302 have offsets within 10 minutes.',
      '    There are 2,130 complete gauge-days of 2,143 across all 24 dates. No October labels, storm',
      '    counts or scores were computed during this audit or development. Seven coastal cell centres',
      '    use their frozen planning-area name to join URA regions; Central Area remains the 16 cells',
      '    whose centres fall within URA Central Area. Due to the sparse archive,',
      '    unknown midnight gauge intervals are missing, not treated as dry; current-day gauge health',
      '    uses only previous-day completeness. This limitation is retained in all periods.',
      '    Settings in s22_development.csv and calibration alert fractions in s22_alert_rates.csv were',
      '    chosen using data through September 2025 only. Final refitting uses April 2022-September 2026',
      '    with no further selection or early stopping; this old-test-year use is logged. The baseline',
      '    is refitted with the same registered step-5 structure; no October regime level is fitted.',
      '    All models, transforms and executable source are frozen by the following SHA-256 hashes.',
      '    s22_model_manifest.csv repeats the hashes and byte lengths. This commit must be pushed before scoring.']
    for row in manifest.itertuples(index=False): lines.append(f'    - `{row.path}`: `{row.sha256}`')
    with (ROOT/'outputs/decisions.md').open('a') as f: f.write('\n'.join(lines)+'\n')
    print('Freeze written. Run checks, commit and PUSH before score.',flush=True)


def score():
    from analysis.s22_metrics import evaluate,figure,write_report
    manifest_path=TABLES/'s22_model_manifest.csv'
    assert (LOCAL/'freeze.json').exists()
    assert not (LOCAL/'SCORED.json').exists(), 'Fresh holdout already scored. Do not score again.'
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(), 'Freeze must be committed with a clean working tree'
    subprocess.run(['git','fetch','origin','main'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    remote=subprocess.check_output(['git','rev-parse','origin/main'],cwd=ROOT,text=True).strip()
    assert head==remote, 'Freeze must be pushed before scoring'
    manifest=pd.read_csv(manifest_path)
    assert sha(manifest_path)==json.loads((LOCAL/'freeze.json').read_text())['manifest_sha256']
    for row in manifest.itertuples(index=False): assert sha(ROOT/row.path)==row.sha256,row.path
    # Write-once marker before opening holdout targets. An interrupted run cannot silently rescore.
    marker=dict(commit=head,description='fresh holdout, scored once',started=pd.Timestamp.now(tz='Asia/Singapore').isoformat())
    fd=os.open(LOCAL/'SCORED.json',os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    with os.fdopen(fd,'w') as f: json.dump(marker,f,indent=2)
    log_test_scoring('22_regional.py --part score','fresh holdout, scored once',analysis='step 22',
                     note=f'1-24 Oct 2026; frozen commit {head}; all registered models/targets/horizons/subsets scored together')
    history=pd.read_parquet(LOCAL/'counts_20260930.parquet')
    c=october_counts(history); w=weather_history(HOLD_END)
    # October onset evaluation is first opened here, jointly with all fixed target scores.
    ws=w[w.unit.eq('Central') & w.ts.between(HOLD_START,HOLD_END)]
    candidates=ws[(ws.onset_share>=.25)&(ws.onset_gauges>=20)].ts.tolist()
    onsets=[]
    for t in candidates:
        if not onsets or (t-onsets[-1])>=pd.Timedelta('180min'): onsets.append(t)
    pd.DataFrame({'onset':onsets}).to_csv(TABLES/'s22_storm_onsets.csv',index=False)
    rows=[]; pattern=joblib.load(LOCAL/'pattern.joblib')
    for h in (30,60):
        d=make_features(c,w,pattern,h,HOLD_START,HOLD_END)
        d['storm']=False
        for t in onsets: d.loc[d.ts.between(t-pd.Timedelta('60min'),t+pd.Timedelta('120min')),'storm']=True
        for target in TARGETS:
            out=d[['ts','unit','storm','Y','expected_now','target_count','target_expected']].copy()
            out['horizon']=h; out['target_name']=target; out['truth']=label(d,target)
            for weather in (False,True):
                for kind in ('persistence','seasonal','linear','lightgbm'):
                    name=f'{h}_{int(weather)}_{kind}' if kind in ('persistence','seasonal') else f'{h}_{target}_{int(weather)}_{kind}'
                    b=joblib.load(LOCAL/f'{name}.joblib')
                    out[f'{kind}_{int(weather)}']=baseline_predict(b,d,target) if kind in ('persistence','seasonal') else predict(b,d)
            rows.append(out)
    predictions=pd.concat(rows,ignore_index=True)
    # Persist predictions once. All diagnostics/reporting use these immutable scored values.
    predictions.to_parquet(LOCAL/'holdout_predictions.parquet',index=False)
    stats,gains=evaluate(predictions)
    stats.to_csv(TABLES/'s22_metrics.csv',index=False); gains.to_csv(TABLES/'s22_weather_gains.csv',index=False)
    figure(gains,len(onsets)); write_report(stats,gains,onsets,head,predictions)
    marker.update(completed=pd.Timestamp.now(tz='Asia/Singapore').isoformat(),prediction_sha256=sha(LOCAL/'holdout_predictions.parquet'),storms=len(onsets))
    (LOCAL/'SCORED.json').write_text(json.dumps(marker,indent=2))
    print(json.dumps(marker,indent=2),flush=True)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--part',choices=['develop','freeze','score'],required=True)
    globals()[p.parse_args().part]()

if __name__=='__main__': main()
